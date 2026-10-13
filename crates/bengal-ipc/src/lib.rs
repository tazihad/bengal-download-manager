pub mod client;
pub mod daemon;
pub mod http_server;
pub mod lock;
pub mod protocol;
pub mod socket;

pub use client::IpcClient;
pub use daemon::{DaemonHandler, DaemonRunner, DaemonState};
pub use http_server::ExtensionHttpServer;
pub use lock::{SingleInstance, SingleInstanceStatus};
pub use protocol::{IpcRequest, IpcResponse};
pub use socket::{IpcHandler, IpcSocketServer};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ipc_protocol_serialization() {
        let req = IpcRequest::Add {
            url: "https://example.com/test.iso".to_string(),
            out: Some("test.iso".to_string()),
            dir: None,
            category: Some("ISO".to_string()),
            queue: None,
            connections: Some(16),
            limit: Some(1024),
            start_now: true,
        };

        let json = serde_json::to_string(&req).expect("Failed to serialize IpcRequest");
        let parsed: IpcRequest = serde_json::from_str(&json).expect("Failed to deserialize IpcRequest");

        match parsed {
            IpcRequest::Add { url, connections, .. } => {
                assert_eq!(url, "https://example.com/test.iso");
                assert_eq!(connections, Some(16));
            }
            _ => panic!("Expected Add variant"),
        }
    }

    #[test]
    fn test_ipc_response_helpers() {
        let resp = IpcResponse::ok("All good");
        assert!(resp.success);
        assert_eq!(resp.message, "All good");

        let err = IpcResponse::err("Failed");
        assert!(!err.success);
        assert_eq!(err.message, "Failed");
    }
}

