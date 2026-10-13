use serde::{Deserialize, Serialize};

/// Request sent from a CLI client or external tool to the running Bengal instance.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "action", content = "payload")]
pub enum IpcRequest {
    /// Add a new download
    Add {
        url: String,
        out: Option<String>,
        dir: Option<String>,
        category: Option<String>,
        queue: Option<String>,
        connections: Option<usize>,
        limit: Option<u64>,
        start_now: bool,
    },
    /// Pause a specific download
    Pause { id: i64 },
    /// Pause all active downloads
    PauseAll,
    /// Resume a specific download
    Resume { id: i64 },
    /// Resume all paused downloads
    ResumeAll,
    /// Cancel an active download
    Cancel { id: i64 },
    /// Restart a download from scratch
    Restart { id: i64 },
    /// Delete a download record (optionally remove file from disk)
    Delete { id: i64, delete_file: bool },
    /// Query download status
    Status { id: i64 },
    /// List downloads with filters
    List {
        status: Option<String>,
        category: Option<String>,
        queue: Option<String>,
        limit: Option<usize>,
    },
    /// Raise and focus the GUI window
    RaiseWindow,
    /// Health ping
    Ping,
}

/// Response returned from the running Bengal instance back to the client.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IpcResponse {
    pub success: bool,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
}

impl IpcResponse {
    pub fn ok(message: impl Into<String>) -> Self {
        Self {
            success: true,
            message: message.into(),
            data: None,
        }
    }

    pub fn ok_with_data(message: impl Into<String>, data: serde_json::Value) -> Self {
        Self {
            success: true,
            message: message.into(),
            data: Some(data),
        }
    }

    pub fn err(message: impl Into<String>) -> Self {
        Self {
            success: false,
            message: message.into(),
            data: None,
        }
    }
}
