use std::path::PathBuf;
use anyhow::Result;
use bengal_core::AppPaths;

use crate::client::IpcClient;
use crate::protocol::IpcRequest;

pub enum SingleInstanceStatus {
    /// This is the primary instance. It should start servers and run normally.
    Primary,
    /// Another instance is already running. We notified it to raise window.
    AlreadyRunning,
}

pub struct SingleInstance;

impl SingleInstance {
    /// Check if an instance of Bengal is already running.
    /// If running, notifies it to raise its window and returns `AlreadyRunning`.
    /// Otherwise returns `Primary`.
    pub async fn check_or_acquire() -> Result<SingleInstanceStatus> {
        let mut client = IpcClient::new();
        if client.is_server_available().await {
            tracing::info!("Another Bengal Download Manager instance is already active. Notifying to raise window...");
            let _ = client.send(IpcRequest::RaiseWindow).await;
            Ok(SingleInstanceStatus::AlreadyRunning)
        } else {
            let socket_path = Self::socket_path();
            if socket_path.exists() {
                let _ = std::fs::remove_file(&socket_path);
            }
            Ok(SingleInstanceStatus::Primary)
        }
    }

    /// Path to the local UNIX domain socket
    pub fn socket_path() -> PathBuf {
        let runtime_dir = AppPaths::runtime_dir();
        runtime_dir.join("bengal.sock")
    }
}
