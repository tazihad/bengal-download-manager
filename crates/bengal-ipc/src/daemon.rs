use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use anyhow::{Context, Result};
use tokio::sync::Mutex;
use bengal_core::{format_bytes, AppPaths};
use bengal_db::Database;
use tigris::{ProxyConfig, TigrisEngine, TigrisTask};

use crate::http_server::ExtensionHttpServer;
use crate::protocol::{IpcRequest, IpcResponse};
use crate::socket::{IpcHandler, IpcSocketServer};

pub struct ActiveTask {
    pub cancel_flag: Arc<AtomicBool>,
}

pub struct DaemonState {
    pub db: Arc<Database>,
    pub active_tasks: Mutex<HashMap<i64, ActiveTask>>,
}

impl DaemonState {
    pub fn new(db: Database) -> Self {
        Self {
            db: Arc::new(db),
            active_tasks: Mutex::new(HashMap::new()),
        }
    }
}

pub struct DaemonHandler {
    state: Arc<DaemonState>,
}

impl DaemonHandler {
    pub fn new(state: Arc<DaemonState>) -> Self {
        Self { state }
    }
}

impl IpcHandler for DaemonHandler {
    fn handle(&self, req: IpcRequest) -> std::pin::Pin<Box<dyn std::future::Future<Output = IpcResponse> + Send>> {
        let state = Arc::clone(&self.state);
        Box::pin(async move {
            match req {
                IpcRequest::Ping => IpcResponse::ok("pong"),
                IpcRequest::RaiseWindow => IpcResponse::ok("Daemon is headless; window raise acknowledged"),
                IpcRequest::Add {
                    url,
                    out,
                    dir,
                    category,
                    queue,
                    connections,
                    limit,
                    start_now,
                } => {
                    let cat = category.unwrap_or_else(|| "General".to_string());
                    let q = queue.unwrap_or_else(|| "Default".to_string());
                    let conns = connections.unwrap_or(8).clamp(1, 32);
                    let speed_limit = limit.unwrap_or(0);

                    // Probe URL
                    let probe = match TigrisEngine::probe(&url, &ProxyConfig::Direct).await {
                        Ok(p) => p,
                        Err(e) => return IpcResponse::err(format!("URL probe failed: {}", e)),
                    };

                    let filename = out.unwrap_or(probe.suggested_filename);
                    let save_dir = dir
                        .map(std::path::PathBuf::from)
                        .unwrap_or_else(AppPaths::default_download_dir);

                    let _ = std::fs::create_dir_all(&save_dir);
                    let target_path = save_dir.join(&filename);
                    let size_str = probe.total_size.map(format_bytes).unwrap_or_default();

                    let id = match state.db.insert_download(
                        &url,
                        &filename,
                        &target_path.to_string_lossy(),
                        &size_str,
                        &cat,
                    ) {
                        Ok(id) => id,
                        Err(e) => return IpcResponse::err(format!("Database insert failed: {}", e)),
                    };

                    if start_now {
                        let _ = state.db.update_status(id, "downloading", "");
                        let cancel_flag = Arc::new(AtomicBool::new(false));
                        {
                            let mut tasks = state.active_tasks.lock().await;
                            tasks.insert(id, ActiveTask { cancel_flag: Arc::clone(&cancel_flag) });
                        }

                        let task = TigrisTask {
                            url: url.clone(),
                            target_path: target_path.clone(),
                            num_connections: conns,
                            proxy: ProxyConfig::Direct,
                            speed_limit,
                        };

                        let state_clone = Arc::clone(&state);
                        tokio::spawn(async move {
                            let db = Arc::clone(&state_clone.db);
                            let res = TigrisEngine::download(task, move |update| {
                                let _ = db.update_progress(
                                    id,
                                    &format_bytes(update.downloaded_bytes),
                                    update.progress_percent,
                                    &format!("{}/s", format_bytes(update.speed_bytes_sec)),
                                    &format!("{}s", update.eta_seconds),
                                );
                            }).await;

                            {
                                let mut tasks = state_clone.active_tasks.lock().await;
                                tasks.remove(&id);
                            }

                            match res {
                                Ok(_) => {
                                    let _ = state_clone.db.update_status(id, "completed", "");
                                }
                                Err(e) => {
                                    if cancel_flag.load(Ordering::Relaxed) {
                                        let _ = state_clone.db.update_status(id, "paused", "");
                                    } else {
                                        let _ = state_clone.db.update_status(id, "error", &e.to_string());
                                    }
                                }
                            }
                        });
                    }

                    IpcResponse::ok_with_data(
                        format!("Added download #{} ({})", id, filename),
                        serde_json::json!({
                            "id": id,
                            "filename": filename,
                            "path": target_path.to_string_lossy(),
                            "size": size_str,
                            "category": cat,
                            "queue": q,
                            "started": start_now
                        }),
                    )
                }
                IpcRequest::Pause { id } => {
                    let mut tasks = state.active_tasks.lock().await;
                    if let Some(task) = tasks.remove(&id) {
                        task.cancel_flag.store(true, Ordering::Relaxed);
                    }
                    let _ = state.db.update_status(id, "paused", "");
                    IpcResponse::ok(format!("Paused download #{}", id))
                }
                IpcRequest::PauseAll => {
                    let mut tasks = state.active_tasks.lock().await;
                    for (_, task) in tasks.drain() {
                        task.cancel_flag.store(true, Ordering::Relaxed);
                    }
                    if let Ok(list) = state.db.list_downloads() {
                        for item in list {
                            if item.status == "downloading" {
                                let _ = state.db.update_status(item.id, "paused", "");
                            }
                        }
                    }
                    IpcResponse::ok("Paused all active downloads")
                }
                IpcRequest::Resume { id } => {
                    if let Ok(Some(item)) = state.db.get_download(id) {
                        if item.status == "completed" {
                            return IpcResponse::err(format!("Download #{} is already completed", id));
                        }
                        let _ = state.db.update_status(id, "downloading", "");
                        let cancel_flag = Arc::new(AtomicBool::new(false));
                        {
                            let mut tasks = state.active_tasks.lock().await;
                            tasks.insert(id, ActiveTask { cancel_flag: Arc::clone(&cancel_flag) });
                        }

                        let task = TigrisTask {
                            url: item.url.clone(),
                            target_path: std::path::PathBuf::from(&item.path),
                            num_connections: (item.connections.max(1) as usize).clamp(1, 32),
                            proxy: ProxyConfig::Direct,
                            speed_limit: 0,
                        };

                        let state_clone = Arc::clone(&state);
                        tokio::spawn(async move {
                            let db = Arc::clone(&state_clone.db);
                            let res = TigrisEngine::download(task, move |update| {
                                let _ = db.update_progress(
                                    id,
                                    &format_bytes(update.downloaded_bytes),
                                    update.progress_percent,
                                    &format!("{}/s", format_bytes(update.speed_bytes_sec)),
                                    &format!("{}s", update.eta_seconds),
                                );
                            }).await;

                            {
                                let mut tasks = state_clone.active_tasks.lock().await;
                                tasks.remove(&id);
                            }

                            match res {
                                Ok(_) => {
                                    let _ = state_clone.db.update_status(id, "completed", "");
                                }
                                Err(e) => {
                                    if cancel_flag.load(Ordering::Relaxed) {
                                        let _ = state_clone.db.update_status(id, "paused", "");
                                    } else {
                                        let _ = state_clone.db.update_status(id, "error", &e.to_string());
                                    }
                                }
                            }
                        });
                        IpcResponse::ok(format!("Resumed download #{}", id))
                    } else {
                        IpcResponse::err(format!("Download #{} not found", id))
                    }
                }
                IpcRequest::ResumeAll => {
                    let mut resumed = 0;
                    if let Ok(list) = state.db.list_downloads() {
                        for item in list {
                            if item.status == "paused" || item.status == "queued" {
                                let id = item.id;
                                let _ = state.db.update_status(id, "downloading", "");
                                let cancel_flag = Arc::new(AtomicBool::new(false));
                                {
                                    let mut tasks = state.active_tasks.lock().await;
                                    tasks.insert(id, ActiveTask { cancel_flag: Arc::clone(&cancel_flag) });
                                }

                                let task = TigrisTask {
                                    url: item.url.clone(),
                                    target_path: std::path::PathBuf::from(&item.path),
                                    num_connections: (item.connections.max(1) as usize).clamp(1, 32),
                                    proxy: ProxyConfig::Direct,
                                    speed_limit: 0,
                                };

                                let state_clone = Arc::clone(&state);
                                tokio::spawn(async move {
                                    let db = Arc::clone(&state_clone.db);
                                    let res = TigrisEngine::download(task, move |update| {
                                        let _ = db.update_progress(
                                            id,
                                            &format_bytes(update.downloaded_bytes),
                                            update.progress_percent,
                                            &format!("{}/s", format_bytes(update.speed_bytes_sec)),
                                            &format!("{}s", update.eta_seconds),
                                        );
                                    }).await;

                                    {
                                        let mut tasks = state_clone.active_tasks.lock().await;
                                        tasks.remove(&id);
                                    }

                                    if res.is_ok() {
                                        let _ = state_clone.db.update_status(id, "completed", "");
                                    } else if cancel_flag.load(Ordering::Relaxed) {
                                        let _ = state_clone.db.update_status(id, "paused", "");
                                    } else {
                                        let _ = state_clone.db.update_status(id, "error", "");
                                    }
                                });
                                resumed += 1;
                            }
                        }
                    }
                    IpcResponse::ok(format!("Resumed {} downloads", resumed))
                }
                IpcRequest::Cancel { id } => {
                    {
                        let mut tasks = state.active_tasks.lock().await;
                        if let Some(task) = tasks.remove(&id) {
                            task.cancel_flag.store(true, Ordering::Relaxed);
                        }
                    }
                    let _ = state.db.update_status(id, "cancelled", "");
                    IpcResponse::ok(format!("Cancelled download #{}", id))
                }
                IpcRequest::Restart { id } => {
                    {
                        let mut tasks = state.active_tasks.lock().await;
                        if let Some(task) = tasks.remove(&id) {
                            task.cancel_flag.store(true, Ordering::Relaxed);
                        }
                    }
                    if let Ok(Some(item)) = state.db.get_download(id) {
                        let path = std::path::PathBuf::from(&item.path);
                        let _ = std::fs::remove_file(&path);
                        let part_path = path.with_extension(format!("{}.bdpart", path.extension().and_then(|s| s.to_str()).unwrap_or("")));
                        let _ = std::fs::remove_file(&part_path);

                        let _ = state.db.update_status(id, "queued", "");
                        let _ = state.db.update_progress(id, "0 B", 0.0, "", "");
                        IpcResponse::ok(format!("Restarted download #{}", id))
                    } else {
                        IpcResponse::err(format!("Download #{} not found", id))
                    }
                }
                IpcRequest::Delete { id, delete_file } => {
                    {
                        let mut tasks = state.active_tasks.lock().await;
                        if let Some(task) = tasks.remove(&id) {
                            task.cancel_flag.store(true, Ordering::Relaxed);
                        }
                    }
                    if delete_file {
                        if let Ok(Some(item)) = state.db.get_download(id) {
                            let path = std::path::PathBuf::from(&item.path);
                            let _ = std::fs::remove_file(&path);
                            let part_path = path.with_extension(format!("{}.bdpart", path.extension().and_then(|s| s.to_str()).unwrap_or("")));
                            let _ = std::fs::remove_file(&part_path);
                        }
                    }
                    match state.db.delete_download(id) {
                        Ok(_) => IpcResponse::ok(format!("Deleted download #{}", id)),
                        Err(e) => IpcResponse::err(format!("Failed to delete: {}", e)),
                    }
                }
                IpcRequest::Status { id } => {
                    match state.db.get_download(id) {
                        Ok(Some(item)) => IpcResponse::ok_with_data("Found", serde_json::to_value(&item).unwrap_or_default()),
                        Ok(None) => IpcResponse::err(format!("Download #{} not found", id)),
                        Err(e) => IpcResponse::err(format!("Database error: {}", e)),
                    }
                }
                IpcRequest::List { status, category, queue, limit } => {
                    match state.db.list_downloads() {
                        Ok(mut list) => {
                            if let Some(s) = status {
                                list.retain(|item| item.status.eq_ignore_ascii_case(&s));
                            }
                            if let Some(c) = category {
                                list.retain(|item| item.category.eq_ignore_ascii_case(&c));
                            }
                            if let Some(q) = queue {
                                list.retain(|item| item.queue.eq_ignore_ascii_case(&q));
                            }
                            if let Some(n) = limit {
                                list.truncate(n);
                            }
                            IpcResponse::ok_with_data("OK", serde_json::to_value(&list).unwrap_or_default())
                        }
                        Err(e) => IpcResponse::err(format!("Database error: {}", e)),
                    }
                }
            }
        })
    }
}

pub struct DaemonRunner {
    pub port: u16,
    pub handler: Arc<DaemonHandler>,
}

impl DaemonRunner {
    pub fn new(port: u16, db: Database) -> Self {
        let state = Arc::new(DaemonState::new(db));
        let handler = Arc::new(DaemonHandler::new(state));
        Self { port, handler }
    }

    pub async fn run(&self) -> Result<()> {
        let socket_server = IpcSocketServer::new(Arc::clone(&self.handler) as Arc<dyn IpcHandler>);
        let http_server = ExtensionHttpServer::new(self.port, Arc::clone(&self.handler) as Arc<dyn IpcHandler>);

        tracing::info!("[Daemon] Starting Bengal Download Manager background engine...");

        tokio::select! {
            res = socket_server.run() => {
                res.context("IPC socket server terminated unexpectedly")
            }
            res = http_server.run() => {
                res.context("Extension HTTP server terminated unexpectedly")
            }
        }
    }
}
