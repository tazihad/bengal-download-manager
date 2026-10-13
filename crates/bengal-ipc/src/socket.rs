use std::path::PathBuf;
use std::sync::Arc;
use anyhow::{Context, Result};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use bengal_core::AppPaths;

use crate::protocol::{IpcRequest, IpcResponse};

/// Trait implemented by application components (GUI, Daemon) to handle IPC requests.
pub trait IpcHandler: Send + Sync + 'static {
    fn handle(&self, req: IpcRequest) -> std::pin::Pin<Box<dyn std::future::Future<Output = IpcResponse> + Send>>;
}

pub struct IpcSocketServer {
    socket_path: PathBuf,
    handler: Arc<dyn IpcHandler>,
}

impl IpcSocketServer {
    pub fn new(handler: Arc<dyn IpcHandler>) -> Self {
        let runtime_dir = AppPaths::runtime_dir();
        let socket_path = runtime_dir.join("bengal.sock");
        Self {
            socket_path,
            handler,
        }
    }

    pub fn socket_path(&self) -> &PathBuf {
        &self.socket_path
    }

    #[cfg(unix)]
    pub async fn run(&self) -> Result<()> {
        if let Some(parent) = self.socket_path.parent() {
            std::fs::create_dir_all(parent).context("Failed to create socket directory")?;
        }

        // Remove stale socket file if it exists
        if self.socket_path.exists() {
            let _ = std::fs::remove_file(&self.socket_path);
        }

        let listener = tokio::net::UnixListener::bind(&self.socket_path)
            .with_context(|| format!("Failed to bind UNIX domain socket at {}", self.socket_path.display()))?;

        tracing::info!("[IPC] Listening on UNIX domain socket: {}", self.socket_path.display());

        loop {
            match listener.accept().await {
                Ok((stream, _addr)) => {
                    let handler = Arc::clone(&self.handler);
                    tokio::spawn(async move {
                        if let Err(e) = Self::handle_client(stream, handler).await {
                            tracing::debug!("[IPC] Client connection error: {}", e);
                        }
                    });
                }
                Err(e) => {
                    tracing::error!("[IPC] Accept failed: {}", e);
                    tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
                }
            }
        }
    }

    #[cfg(windows)]
    pub async fn run(&self) -> Result<()> {
        // On Windows fallback to loopback TCP port 56801
        let addr = "127.0.0.1:56801";
        let listener = tokio::net::TcpListener::bind(addr).await
            .with_context(|| format!("Failed to bind local IPC TCP port {}", addr))?;

        tracing::info!("[IPC] Listening on Windows local IPC port: {}", addr);

        loop {
            match listener.accept().await {
                Ok((stream, _)) => {
                    let handler = Arc::clone(&self.handler);
                    tokio::spawn(async move {
                        let (read_half, mut write_half) = stream.into_split();
                        let mut reader = BufReader::new(read_half);
                        let mut line = String::new();
                        while let Ok(bytes) = reader.read_line(&mut line).await {
                            if bytes == 0 { break; }
                            let trimmed = line.trim();
                            if !trimmed.is_empty() {
                                let resp = match serde_json::from_str::<IpcRequest>(trimmed) {
                                    Ok(req) => handler.handle(req).await,
                                    Err(e) => IpcResponse::err(format!("Invalid IPC JSON: {}", e)),
                                };
                                let mut serialized = serde_json::to_string(&resp).unwrap_or_default();
                                serialized.push('\n');
                                if write_half.write_all(serialized.as_bytes()).await.is_err() { break; }
                            }
                            line.clear();
                        }
                    });
                }
                Err(e) => {
                    tracing::error!("[IPC] Accept error: {}", e);
                }
            }
        }
    }

    #[cfg(unix)]
    async fn handle_client(stream: tokio::net::UnixStream, handler: Arc<dyn IpcHandler>) -> Result<()> {
        let (read_half, mut write_half) = stream.into_split();
        let mut reader = BufReader::new(read_half);
        let mut line = String::new();

        while let Ok(bytes) = reader.read_line(&mut line).await {
            if bytes == 0 {
                break;
            }
            let trimmed = line.trim();
            if !trimmed.is_empty() {
                let resp = match serde_json::from_str::<IpcRequest>(trimmed) {
                    Ok(req) => handler.handle(req).await,
                    Err(e) => IpcResponse::err(format!("Invalid IPC JSON: {}", e)),
                };

                let mut serialized = serde_json::to_string(&resp)?;
                serialized.push('\n');
                write_half.write_all(serialized.as_bytes()).await?;
            }
            line.clear();
        }

        Ok(())
    }
}

impl Drop for IpcSocketServer {
    fn drop(&mut self) {
        #[cfg(unix)]
        if self.socket_path.exists() {
            let _ = std::fs::remove_file(&self.socket_path);
        }
    }
}
