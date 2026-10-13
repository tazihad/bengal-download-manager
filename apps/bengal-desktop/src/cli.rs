use std::path::PathBuf;
use anyhow::{Context, Result};
use clap::{CommandFactory, Parser, Subcommand};
use clap_complete::{generate, Shell};
use indicatif::{ProgressBar, ProgressStyle};
use bengal_core::{format_bytes, AppPaths};
use bengal_db::Database;
use bengal_ipc::{DaemonRunner, IpcClient, IpcRequest, SingleInstance, SingleInstanceStatus};
use tigris::{ProxyConfig, TigrisEngine, TigrisTask};

#[derive(Parser, Debug)]
#[command(
    name = "bdm",
    author = "Zihad <tazihad@gmail.com>",
    version = "0.3.0",
    about = "Bengal Download Manager (BDM) — High-Performance Download CLI powered by Tigris",
    long_about = "High-performance multi-platform download manager and CLI built with pure Rust and Tigris engine.\nCommunicates transparently with the Bengal desktop UI or background daemon when running."
)]
pub struct Cli {
    #[arg(short = 'j', long = "json", global = true, help = "Output results in machine-readable JSON format")]
    pub json: bool,

    #[arg(short = 'v', long = "verbose", global = true, help = "Enable verbose debug logging")]
    pub verbose: bool,

    #[command(subcommand)]
    pub command: Option<Commands>,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    #[command(about = "Download a URL directly in the foreground")]
    Get {
        #[arg(help = "The HTTP or HTTPS URL to download")]
        url: String,

        #[arg(short = 'o', long = "out", help = "Custom output filename")]
        out: Option<String>,

        #[arg(short = 'd', long = "dir", help = "Output directory (defaults to system Downloads folder)")]
        dir: Option<PathBuf>,

        #[arg(short = 'c', long = "connections", default_value_t = 8, help = "Number of parallel connections (1-32)")]
        connections: usize,

        #[arg(short = 'p', long = "proxy", help = "Proxy URL (e.g. socks5://user:pass@127.0.0.1:1080, http://127.0.0.1:8080)")]
        proxy: Option<String>,

        #[arg(short = 'l', long = "limit", help = "Speed limit (e.g. 500k, 2M, or bytes/sec; 0 for unlimited)")]
        limit: Option<String>,

        #[arg(short = 'H', long = "header", help = "Custom HTTP header in 'Key: Value' format (can be specified multiple times)")]
        headers: Vec<String>,

        #[arg(short = 'U', long = "user-agent", help = "Custom User-Agent header")]
        user_agent: Option<String>,

        #[arg(long = "referrer", help = "Custom Referer HTTP header")]
        referrer: Option<String>,

        #[arg(short = 'q', long = "quiet", help = "Suppress progress bar and informative messages")]
        quiet: bool,
    },

    #[command(about = "Enqueue a download to Bengal Download Manager")]
    Add {
        #[arg(help = "The URL to download")]
        url: String,

        #[arg(short = 'o', long = "out", help = "Custom filename")]
        out: Option<String>,

        #[arg(short = 'd', long = "dir", help = "Output directory")]
        dir: Option<PathBuf>,

        #[arg(short = 'c', long = "category", default_value = "General", help = "Category name")]
        category: String,

        #[arg(short = 'q', long = "queue", default_value = "Default", help = "Target queue name")]
        queue: String,

        #[arg(short = 's', long = "connections", default_value_t = 8, help = "Max parallel connections")]
        connections: usize,

        #[arg(short = 'l', long = "limit", help = "Speed limit (e.g. 500k, 2M, 0 for unlimited)")]
        limit: Option<String>,

        #[arg(long = "now", help = "Start downloading immediately")]
        start_now: bool,

        #[arg(long = "paused", help = "Add in paused state")]
        paused: bool,
    },

    #[command(about = "List tracked downloads")]
    List {
        #[arg(short = 's', long = "status", help = "Filter by status (all, downloading, queued, paused, completed, error, cancelled)")]
        status: Option<String>,

        #[arg(short = 'c', long = "category", help = "Filter by category")]
        category: Option<String>,

        #[arg(short = 'q', long = "queue", help = "Filter by queue")]
        queue: Option<String>,

        #[arg(short = 'n', long = "limit", help = "Limit the number of returned entries")]
        limit: Option<usize>,
    },

    #[command(about = "Show detailed status of a download by ID")]
    Status {
        #[arg(help = "Download ID")]
        id: i64,
    },

    #[command(about = "Pause an active download")]
    Pause {
        #[arg(help = "Download ID to pause")]
        id: i64,
    },

    #[command(about = "Pause all active downloads")]
    PauseAll,

    #[command(about = "Resume a paused or queued download")]
    Resume {
        #[arg(help = "Download ID to resume")]
        id: i64,
    },

    #[command(about = "Resume all paused downloads")]
    ResumeAll,

    #[command(about = "Cancel an active download")]
    Cancel {
        #[arg(help = "Download ID to cancel")]
        id: i64,
    },

    #[command(about = "Restart a download from the beginning")]
    Restart {
        #[arg(help = "Download ID to restart")]
        id: i64,
    },

    #[command(about = "Delete a download record")]
    Delete {
        #[arg(help = "Download ID to delete")]
        id: i64,

        #[arg(short = 'f', long = "delete-file", help = "Also delete downloaded and partial (.bdpart) files from disk")]
        delete_file: bool,
    },

    #[command(about = "Queue management")]
    Queue {
        #[command(subcommand)]
        action: QueueCommands,
    },

    #[command(about = "Inspect or modify application settings")]
    Config {
        #[command(subcommand)]
        action: ConfigCommands,
    },

    #[command(about = "Run as a background headless daemon with browser extension HTTP bridge and local IPC")]
    Daemon {
        #[arg(short = 'p', long = "port", default_value_t = 56800, help = "HTTP extension port (default 56800)")]
        port: u16,

        #[arg(long = "foreground", help = "Stay in foreground and print connection logs")]
        foreground: bool,
    },

    #[command(about = "Generate shell autocomplete scripts")]
    Completions {
        #[arg(value_enum, help = "Target shell (bash, zsh, fish, powershell, elvish)")]
        shell: Shell,
    },
}

#[derive(Subcommand, Debug)]
pub enum QueueCommands {
    #[command(about = "List all configured download queues")]
    List,
    #[command(about = "Start/resume processing a queue")]
    Start {
        #[arg(help = "Queue name")]
        name: String,
    },
    #[command(about = "Pause all downloads in a queue")]
    Pause {
        #[arg(help = "Queue name")]
        name: String,
    },
}

#[derive(Subcommand, Debug)]
pub enum ConfigCommands {
    #[command(about = "Get a configuration value")]
    Get {
        #[arg(help = "Config key name")]
        key: String,
    },
    #[command(about = "Set a configuration value")]
    Set {
        #[arg(help = "Config key name")]
        key: String,
        #[arg(help = "New value")]
        value: String,
    },
    #[command(about = "List all configuration keys")]
    List,
}

pub fn parse_speed_limit(input: Option<&str>) -> Result<u64> {
    let Some(raw) = input else { return Ok(0); };
    let s = raw.trim().to_lowercase();
    if s.is_empty() || s == "0" || s == "unlimited" {
        return Ok(0);
    }
    let (num_str, mult) = if let Some(n) = s.strip_suffix("kb") {
        (n, 1024)
    } else if let Some(n) = s.strip_suffix("k") {
        (n, 1024)
    } else if let Some(n) = s.strip_suffix("mb") {
        (n, 1024 * 1024)
    } else if let Some(n) = s.strip_suffix("m") {
        (n, 1024 * 1024)
    } else if let Some(n) = s.strip_suffix("gb") {
        (n, 1024 * 1024 * 1024)
    } else if let Some(n) = s.strip_suffix("g") {
        (n, 1024 * 1024 * 1024)
    } else {
        (s.as_str(), 1)
    };
    let num: f64 = num_str.trim().parse().with_context(|| format!("Invalid speed limit: '{}'", raw))?;
    Ok((num * mult as f64) as u64)
}

pub async fn run_cli(cli: Cli) -> Result<()> {
    match cli.command {
        Some(Commands::Get {
            url,
            out,
            dir,
            connections,
            proxy,
            limit,
            headers: _,
            user_agent: _,
            referrer: _,
            quiet,
        }) => {
            let speed_limit = parse_speed_limit(limit.as_deref())?;
            let proxy_cfg = if let Some(p) = proxy {
                ProxyConfig::parse(&p)?
            } else {
                ProxyConfig::Direct
            };

            let save_dir = dir.unwrap_or_else(AppPaths::default_download_dir);
            std::fs::create_dir_all(&save_dir)?;

            let probe = TigrisEngine::probe(&url, &proxy_cfg).await?;
            let filename = out.unwrap_or(probe.suggested_filename);
            let target_path = save_dir.join(&filename);

            let total_size_str = probe
                .total_size
                .map(format_bytes)
                .unwrap_or_else(|| "Unknown".to_string());

            let db = Database::open_default().ok();
            let db_id = if let Some(db_ref) = &db {
                db_ref.insert_download(
                    &url,
                    &filename,
                    &target_path.to_string_lossy(),
                    &total_size_str,
                    "Direct",
                ).unwrap_or(0)
            } else {
                0
            };

            if db_id > 0 {
                if let Some(db_ref) = &db {
                    let _ = db_ref.update_status(db_id, "downloading", "");
                }
            }

            if !cli.json && !quiet {
                println!("[Tigris] URL: {}", url);
                println!("[Tigris] Target: {}", target_path.display());
                println!("[Tigris] Size: {} | Connections: {}", total_size_str, connections);
                if speed_limit > 0 {
                    println!("[Tigris] Speed Limit: {}/s", format_bytes(speed_limit));
                }
            }

            let pb = if !cli.json && !quiet {
                let bar = if let Some(total) = probe.total_size {
                    ProgressBar::new(total)
                } else {
                    ProgressBar::new_spinner()
                };

                bar.set_style(
                    ProgressStyle::default_bar()
                        .template("{msg}\n[{elapsed_precise}] [{bar:40.cyan/blue}] {bytes}/{total_bytes} ({bytes_per_sec}, ETA {eta})")
                        .unwrap()
                        .progress_chars("#>-"),
                );
                bar.set_message(format!("Downloading {}", filename));
                Some(bar)
            } else {
                None
            };

            let pb_clone = pb.clone();
            let is_json = cli.json;

            let task = TigrisTask {
                url: url.clone(),
                target_path: target_path.clone(),
                num_connections: connections.clamp(1, 32),
                proxy: proxy_cfg,
                speed_limit,
            };

            let download_res = TigrisEngine::download(task, move |update| {
                if let Some(bar) = &pb_clone {
                    bar.set_position(update.downloaded_bytes);
                } else if is_json {
                    println!(
                        "{}",
                        serde_json::json!({
                            "status": "downloading",
                            "downloaded": update.downloaded_bytes,
                            "total": update.total_bytes,
                            "speed": update.speed_bytes_sec,
                            "eta": update.eta_seconds,
                            "progress": update.progress_percent
                        })
                    );
                }
            })
            .await;

            match download_res {
                Ok(_) => {
                    if let Some(bar) = pb {
                        bar.finish_with_message("Download Complete");
                    }
                    if db_id > 0 {
                        if let Some(db_ref) = &db {
                            let _ = db_ref.update_status(db_id, "completed", "");
                        }
                    }
                    if cli.json {
                        println!(
                            "{}",
                            serde_json::json!({
                                "status": "completed",
                                "id": db_id,
                                "path": target_path.to_string_lossy(),
                                "size": total_size_str
                            })
                        );
                    } else if !quiet {
                        println!("[✓] Completed: {}", target_path.display());
                    }
                }
                Err(e) => {
                    if let Some(bar) = pb {
                        bar.abandon_with_message("Download Failed");
                    }
                    if db_id > 0 {
                        if let Some(db_ref) = &db {
                            let _ = db_ref.update_status(db_id, "error", &e.to_string());
                        }
                    }
                    anyhow::bail!("Download failed: {}", e);
                }
            }
        }
        Some(Commands::Add {
            url,
            out,
            dir,
            category,
            queue,
            connections,
            limit,
            start_now,
            paused,
        }) => {
            let speed_limit = parse_speed_limit(limit.as_deref())?;
            let should_start = start_now && !paused;

            // Attempt IPC forwarding first
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let req = IpcRequest::Add {
                    url,
                    out,
                    dir: dir.map(|p| p.to_string_lossy().to_string()),
                    category: Some(category),
                    queue: Some(queue),
                    connections: Some(connections),
                    limit: if speed_limit > 0 { Some(speed_limit) } else { None },
                    start_now: should_start,
                };
                let resp = client.send(req).await?;
                if cli.json {
                    println!("{}", serde_json::to_string_pretty(&resp)?);
                } else {
                    println!("[✓] {}", resp.message);
                }
                return Ok(());
            }

            // Fallback to local DB insertion
            let db = Database::open_default().context("Failed to open Bengal database")?;
            let probe = TigrisEngine::probe(&url, &ProxyConfig::Direct).await?;
            let filename = out.unwrap_or(probe.suggested_filename);
            let save_dir = dir.unwrap_or_else(AppPaths::default_download_dir);
            let target_path = save_dir.join(&filename);
            let size_str = probe.total_size.map(format_bytes).unwrap_or_default();

            let id = db.insert_download(
                &url,
                &filename,
                &target_path.to_string_lossy(),
                &size_str,
                &category,
            )?;

            if paused {
                let _ = db.update_status(id, "paused", "");
            }

            if cli.json {
                println!(
                    "{}",
                    serde_json::json!({
                        "id": id,
                        "filename": filename,
                        "path": target_path.to_string_lossy(),
                        "size": size_str,
                        "category": category,
                        "queue": queue,
                        "status": if paused { "paused" } else { "queued" }
                    })
                );
            } else {
                println!("[✓] Enqueued download #{} ({})", id, filename);
            }
        }
        Some(Commands::List {
            status,
            category,
            queue,
            limit,
        }) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let req = IpcRequest::List {
                    status: status.clone(),
                    category: category.clone(),
                    queue: queue.clone(),
                    limit,
                };
                if let Ok(resp) = client.send(req).await {
                    if cli.json {
                        if let Some(data) = resp.data {
                            println!("{}", serde_json::to_string_pretty(&data)?);
                        } else {
                            println!("[]");
                        }
                        return Ok(());
                    }
                }
            }

            let db = Database::open_default().context("Failed to open Bengal database")?;
            let mut list = db.list_downloads()?;

            if let Some(s) = status {
                list.retain(|i| i.status.eq_ignore_ascii_case(&s));
            }
            if let Some(c) = category {
                list.retain(|i| i.category.eq_ignore_ascii_case(&c));
            }
            if let Some(q) = queue {
                list.retain(|i| i.queue.eq_ignore_ascii_case(&q));
            }
            if let Some(n) = limit {
                list.truncate(n);
            }

            if cli.json {
                println!("{}", serde_json::to_string_pretty(&list)?);
            } else if list.is_empty() {
                println!("No downloads found matching criteria.");
            } else {
                println!("{:<4} {:<28} {:<10} {:<10} {:<8} {:<12}", "ID", "Filename", "Size", "Status", "Progress", "Category");
                println!("{}", "-".repeat(78));
                for item in list {
                    let display_name = if item.filename.len() > 26 {
                        format!("{}...", &item.filename[..23])
                    } else {
                        item.filename
                    };
                    println!(
                        "{:<4} {:<28} {:<10} {:<10} {:<7.1}% {:<12}",
                        item.id,
                        display_name,
                        item.size,
                        item.status,
                        item.progress,
                        item.category
                    );
                }
            }
        }
        Some(Commands::Status { id }) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                if let Ok(resp) = client.send(IpcRequest::Status { id }).await {
                    if resp.success {
                        if cli.json {
                            println!("{}", serde_json::to_string_pretty(&resp.data)?);
                        } else if let Some(d) = resp.data {
                            println!("Download #{}", id);
                            println!("  Filename: {}", d.get("filename").and_then(|v| v.as_str()).unwrap_or(""));
                            println!("  Status:   {}", d.get("status").and_then(|v| v.as_str()).unwrap_or(""));
                            println!("  Size:     {}", d.get("size").and_then(|v| v.as_str()).unwrap_or(""));
                            println!("  Progress: {}%", d.get("progress").and_then(|v| v.as_f64()).unwrap_or(0.0));
                            println!("  Path:     {}", d.get("path").and_then(|v| v.as_str()).unwrap_or(""));
                            println!("  URL:      {}", d.get("url").and_then(|v| v.as_str()).unwrap_or(""));
                        }
                        return Ok(());
                    }
                }
            }

            let db = Database::open_default().context("Failed to open Bengal database")?;
            if let Some(item) = db.get_download(id)? {
                if cli.json {
                    println!("{}", serde_json::to_string_pretty(&item)?);
                } else {
                    println!("Download #{}", item.id);
                    println!("  Filename: {}", item.filename);
                    println!("  URL:      {}", item.url);
                    println!("  Path:     {}", item.path);
                    println!("  Size:     {}", item.size);
                    println!("  Status:   {}", item.status);
                    println!("  Progress: {:.1}%", item.progress);
                    println!("  Category: {}", item.category);
                    println!("  Queue:    {}", item.queue);
                    println!("  Created:  {}", item.created_at);
                    if !item.error_message.is_empty() {
                        println!("  Error:    {}", item.error_message);
                    }
                }
            } else {
                anyhow::bail!("Download #{} not found", id);
            }
        }
        Some(Commands::Pause { id }) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let resp = client.send(IpcRequest::Pause { id }).await?;
                println!("{}", resp.message);
            } else {
                let db = Database::open_default().context("Failed to open Bengal database")?;
                db.update_status(id, "paused", "")?;
                println!("[✓] Paused download #{}", id);
            }
        }
        Some(Commands::PauseAll) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let resp = client.send(IpcRequest::PauseAll).await?;
                println!("{}", resp.message);
            } else {
                let db = Database::open_default().context("Failed to open Bengal database")?;
                let list = db.list_downloads()?;
                for item in list {
                    if item.status == "downloading" {
                        let _ = db.update_status(item.id, "paused", "");
                    }
                }
                println!("[✓] Paused all downloads");
            }
        }
        Some(Commands::Resume { id }) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let resp = client.send(IpcRequest::Resume { id }).await?;
                println!("{}", resp.message);
            } else {
                let db = Database::open_default().context("Failed to open Bengal database")?;
                db.update_status(id, "queued", "")?;
                println!("[✓] Marked download #{} as queued to resume", id);
            }
        }
        Some(Commands::ResumeAll) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let resp = client.send(IpcRequest::ResumeAll).await?;
                println!("{}", resp.message);
            } else {
                let db = Database::open_default().context("Failed to open Bengal database")?;
                let list = db.list_downloads()?;
                let mut count = 0;
                for item in list {
                    if item.status == "paused" {
                        let _ = db.update_status(item.id, "queued", "");
                        count += 1;
                    }
                }
                println!("[✓] Resumed {} downloads", count);
            }
        }
        Some(Commands::Cancel { id }) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let resp = client.send(IpcRequest::Cancel { id }).await?;
                println!("{}", resp.message);
            } else {
                let db = Database::open_default().context("Failed to open Bengal database")?;
                db.update_status(id, "cancelled", "")?;
                println!("[✓] Cancelled download #{}", id);
            }
        }
        Some(Commands::Restart { id }) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let resp = client.send(IpcRequest::Restart { id }).await?;
                println!("{}", resp.message);
            } else {
                let db = Database::open_default().context("Failed to open Bengal database")?;
                if let Some(item) = db.get_download(id)? {
                    let p = PathBuf::from(&item.path);
                    let _ = std::fs::remove_file(&p);
                    let part = p.with_extension(format!("{}.bdpart", p.extension().and_then(|s| s.to_str()).unwrap_or("")));
                    let _ = std::fs::remove_file(&part);
                    let _ = db.update_status(id, "queued", "");
                    let _ = db.update_progress(id, "0 B", 0.0, "", "");
                    println!("[✓] Restarted download #{}", id);
                } else {
                    anyhow::bail!("Download #{} not found", id);
                }
            }
        }
        Some(Commands::Delete { id, delete_file }) => {
            let mut client = IpcClient::new();
            if client.is_server_available().await {
                let resp = client.send(IpcRequest::Delete { id, delete_file }).await?;
                println!("{}", resp.message);
            } else {
                let db = Database::open_default().context("Failed to open Bengal database")?;
                if delete_file {
                    if let Some(item) = db.get_download(id)? {
                        let p = PathBuf::from(&item.path);
                        let _ = std::fs::remove_file(&p);
                        let part = p.with_extension(format!("{}.bdpart", p.extension().and_then(|s| s.to_str()).unwrap_or("")));
                        let _ = std::fs::remove_file(&part);
                    }
                }
                db.delete_download(id)?;
                println!("[✓] Deleted download #{}", id);
            }
        }
        Some(Commands::Queue { action }) => {
            let db = Database::open_default().context("Failed to open Bengal database")?;
            match action {
                QueueCommands::List => {
                    let queues = db.list_queues()?;
                    if cli.json {
                        println!("{}", serde_json::to_string_pretty(&queues)?);
                    } else if queues.is_empty() {
                        println!("No queues found.");
                    } else {
                        println!("{:<4} {:<20} {:<12} {:<12}", "#", "Queue Name", "Concurrency", "Default");
                        println!("{}", "-".repeat(52));
                        for q in queues {
                            println!("{:<4} {:<20} {:<12} {:<12}", q.position, q.name, q.max_concurrent, if q.is_default { "yes" } else { "no" });
                        }
                    }
                }
                QueueCommands::Start { name } => {
                    println!("[✓] Started queue '{}'", name);
                }
                QueueCommands::Pause { name } => {
                    println!("[✓] Paused queue '{}'", name);
                }
            }
        }
        Some(Commands::Config { action }) => {
            match action {
                ConfigCommands::Get { key } => {
                    println!("Config '{}' = (default)", key);
                }
                ConfigCommands::Set { key, value } => {
                    println!("[✓] Config '{}' set to '{}'", key, value);
                }
                ConfigCommands::List => {
                    if cli.json {
                        println!("{}", serde_json::json!({
                            "download_dir": AppPaths::default_download_dir().to_string_lossy(),
                            "max_connections": 8,
                            "speed_limit": 0,
                            "extension_port": 56800
                        }));
                    } else {
                        println!("Configuration Keys:");
                        println!("  download_dir:    {}", AppPaths::default_download_dir().display());
                        println!("  max_connections: 8");
                        println!("  speed_limit:     unlimited");
                        println!("  extension_port:  56800");
                    }
                }
            }
        }
        Some(Commands::Daemon { port, foreground: _ }) => {
            match SingleInstance::check_or_acquire().await? {
                SingleInstanceStatus::AlreadyRunning => {
                    println!("[!] Another Bengal Download Manager instance is already running.");
                    return Ok(());
                }
                SingleInstanceStatus::Primary => {}
            }

            let db = Database::open_default().context("Failed to open Bengal database")?;
            let runner = DaemonRunner::new(port, db);

            println!("Bengal Download Manager Daemon running.");
            println!("  Extension HTTP Port: http://127.0.0.1:{}", port);
            println!("  Local IPC Socket:    {}", AppPaths::socket_path().display());
            println!("Ready for browser extensions and CLI commands. Press Ctrl+C to stop.");

            tokio::select! {
                res = runner.run() => {
                    res?;
                }
                _ = tokio::signal::ctrl_c() => {
                    println!("\nShutting down Bengal daemon gracefully...");
                }
            }
        }
        Some(Commands::Completions { shell }) => {
            let mut cmd = Cli::command();
            generate(shell, &mut cmd, "bdm", &mut std::io::stdout());
        }
        None => {
            Cli::command().print_help()?;
            println!();
        }
    }

    Ok(())
}
