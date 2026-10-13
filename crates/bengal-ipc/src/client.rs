use std::path::PathBuf;
use anyhow::{Context, Result};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use bengal_core::AppPaths;

use crate::protocol::{IpcRequest, IpcResponse};

#[derive(Debug, Default)]
pub struct IpcClient {
    socket_path: PathBuf,
}

impl IpcClient {
    pub fn new() -> Self {
        let runtime_dir = AppPaths::runtime_dir();
        let socket_path = runtime_dir.join("bengal.sock");
        Self { socket_path }
    }

    /// Check if the IPC daemon/GUI server is active and responding to Ping.
    pub async fn is_server_available(&mut self) -> bool {
        match self.send(IpcRequest::Ping).await {
            Ok(resp) => resp.success,
            Err(_) => false,
        }
    }

    /// Send an IPC request and receive the response.
    #[cfg(unix)]
    pub async fn send(&self, request: IpcRequest) -> Result<IpcResponse> {
        let stream = tokio::net::UnixStream::connect(&self.socket_path)
            .await
            .with_context(|| format!("Could not connect to Bengal socket at {}", self.socket_path.display()))?;

        let (read_half, mut write_half) = stream.into_split();
        let mut reader = BufReader::new(read_half);

        let mut payload = serde_json::to_string(&request)?;
        payload.push('\n');

        write_half.write_all(payload.as_bytes()).await?;
        write_half.flush().await?;

        let mut line = String::new();
        let bytes_read = reader.read_line(&mut line).await?;
        if bytes_read == 0 {
            anyhow::bail!("Server closed connection without responding");
        }

        let resp: IpcResponse = serde_json::from_str(line.trim())
            .with_context(|| format!("Failed to parse IPC server response: '{}'", line.trim()))?;

        Ok(resp)
    }

    /// Send an IPC request on Windows using TCP 56801 loopback.
    #[cfg(windows)]
    pub async fn send(&self, request: IpcRequest) -> Result<IpcResponse> {
        let stream = tokio::net::TcpStream::connect("127.0.0.1:56801")
            .await
            .context("Could not connect to Bengal Windows IPC loopback port 56801")?;

        let (read_half, mut write_half) = stream.into_split();
        let mut reader = BufReader::new(read_half);

        let mut payload = serde_json::to_string(&request)?;
        payload.push('\n');

        write_half.write_all(payload.as_bytes()).await?;
        write_half.flush().await?;

        let mut line = String::new();
        let bytes_read = reader.read_line(&mut line).await?;
        if bytes_read == 0 {
            anyhow::bail!("Server closed connection without responding");
        }

        let resp: IpcResponse = serde_json::from_str(line.trim())
            .with_context(|| format!("Failed to parse IPC server response: '{}'", line.trim()))?;

        Ok(resp)
    }
}
