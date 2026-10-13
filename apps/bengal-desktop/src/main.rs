mod cli;
pub mod ui;

use clap::Parser;
use cli::{run_cli, Cli};
use bengal_core::{setup_process_identity, AppPaths};
use bengal_db::Database;
use bengal_ipc::DaemonRunner;
use ui::BengalApp;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 1. Ensure process identifies as bengal-download-manager in Linux/BSD task monitors
    setup_process_identity("bengal-download-manager");

    // 2. Inspect invocation
    let args: Vec<String> = std::env::args().collect();
    let invoked_name = std::path::Path::new(&args[0])
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("");

    let is_cli = invoked_name == "bdm" || (args.len() > 1 && is_cli_subcommand(&args[1]));

    if is_cli {
        let cli = Cli::parse();
        run_cli(cli).await
    } else {
        // Desktop GUI mode entry point
        // Check single-instance locking
        match bengal_ipc::SingleInstance::check_or_acquire().await? {
            bengal_ipc::SingleInstanceStatus::AlreadyRunning => {
                println!("Bengal Download Manager is already running. Focused existing window.");
                return Ok(());
            }
            bengal_ipc::SingleInstanceStatus::Primary => {}
        }

        // Spawn background IPC socket and extension HTTP server
        let db_path = AppPaths::database_path();
        if let Some(parent) = db_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }

        if let Ok(db) = Database::open(&db_path) {
            let daemon = DaemonRunner::new(56800, db);
            tokio::spawn(async move {
                if let Err(e) = daemon.run().await {
                    tracing::error!("[IPC Server] Daemon error: {}", e);
                }
            });
        }

        let native_options = eframe::NativeOptions {
            viewport: eframe::egui::ViewportBuilder::default()
                .with_title("Bengal Download Manager")
                .with_app_id("bd.com.zihad.BengalDownloadManager")
                .with_inner_size([1040.0, 680.0])
                .with_min_inner_size([720.0, 480.0]),
            ..Default::default()
        };

        eframe::run_native(
            "Bengal Download Manager",
            native_options,
            Box::new(|cc| Ok(Box::new(BengalApp::new(cc)))),
        )
        .map_err(|e| anyhow::anyhow!("GUI runtime error: {}", e))
    }
}

fn is_cli_subcommand(arg: &str) -> bool {
    matches!(
        arg,
        "get" | "add" | "list" | "status" | "pause" | "pause-all"
        | "resume" | "resume-all" | "cancel" | "restart" | "delete"
        | "queue" | "config" | "daemon" | "completions" | "help"
        | "--help" | "-h" | "--version" | "-V" | "--json" | "-j" | "--verbose" | "-v"
    )
}
