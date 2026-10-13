use std::net::SocketAddr;
use std::sync::Arc;
use anyhow::{Context, Result};
use axum::{
    extract::{Json, State},
    http::{Method, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Router,
};
use serde::Deserialize;
use tower_http::cors::{Any, CorsLayer};

use crate::protocol::IpcRequest;
use crate::socket::IpcHandler;

#[derive(Clone)]
pub struct AppState {
    pub handler: Arc<dyn IpcHandler>,
    pub port: u16,
}

#[derive(Debug, Deserialize)]
pub struct DownloadPayload {
    pub url: String,
    #[serde(default)]
    pub filename: Option<String>,
    #[serde(default, rename = "userAgent")]
    pub user_agent: Option<String>,
    #[serde(default)]
    pub cookies: Option<String>,
    #[serde(default)]
    pub referrer: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default, rename = "savePath")]
    pub save_path: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BatchPayload {
    #[serde(default)]
    pub links: Option<Vec<String>>,
    #[serde(default)]
    pub urls: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct JsonRpcRequest {
    #[serde(default)]
    pub jsonrpc: String,
    #[serde(default)]
    pub id: serde_json::Value,
    pub method: String,
    #[serde(default)]
    pub params: Vec<serde_json::Value>,
}

pub struct ExtensionHttpServer {
    port: u16,
    handler: Arc<dyn IpcHandler>,
}

impl ExtensionHttpServer {
    pub fn new(port: u16, handler: Arc<dyn IpcHandler>) -> Self {
        Self { port, handler }
    }

    pub async fn run(&self) -> Result<()> {
        let (listener, effective_port) = match tokio::net::TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], self.port))).await {
            Ok(l) => (l, self.port),
            Err(e) if self.port != 56900 => {
                tracing::warn!("[IPC] Primary port {} busy ({}), trying fallback port 56900...", self.port, e);
                let fallback = tokio::net::TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 56900))).await
                    .with_context(|| format!("Failed to bind both primary port {} and fallback port 56900", self.port))?;
                (fallback, 56900)
            }
            Err(e) => return Err(e).with_context(|| format!("Failed to bind Extension HTTP listener on 127.0.0.1:{}", self.port)),
        };

        let state = AppState {
            handler: Arc::clone(&self.handler),
            port: effective_port,
        };

        let cors = CorsLayer::new()
            .allow_origin(Any)
            .allow_methods([Method::GET, Method::POST, Method::OPTIONS])
            .allow_headers(Any);

        let app = Router::new()
            .route("/", get(handle_root).post(handle_download))
            .route("/download", post(handle_download))
            .route("/batch", post(handle_batch))
            .route("/import-links", post(handle_batch))
            .route("/tab-update", post(handle_notify))
            .route("/media", post(handle_notify))
            .route("/media-sizes", post(handle_notify))
            .route("/probe-media", post(handle_notify))
            .route("/jsonrpc", post(handle_jsonrpc))
            .layer(cors)
            .with_state(state);

        tracing::info!("[IPC] Extension HTTP server listening on http://127.0.0.1:{}", effective_port);

        axum::serve(listener, app).await.context("Extension HTTP server terminated")
    }
}

async fn handle_root(State(state): State<AppState>) -> impl IntoResponse {
    let body = serde_json::json!({
        "status": "Bengal DM is running",
        "version": "0.3.0",
        "ipc_port": state.port,
        "configured_ipc_port": state.port,
        "is_fallback": false,
        "engine": "tigris",
        "aria2": {
            "port": state.port,
            "token": ""
        }
    });
    Json(body)
}

async fn handle_download(
    State(state): State<AppState>,
    Json(payload): Json<DownloadPayload>,
) -> impl IntoResponse {
    tracing::info!("[IPC] Received extension download for: {}", payload.url);

    let req = IpcRequest::Add {
        url: payload.url,
        out: payload.filename,
        dir: payload.save_path,
        category: payload.category,
        queue: None,
        connections: None,
        limit: None,
        start_now: true,
    };

    let resp = state.handler.handle(req).await;
    if resp.success {
        (StatusCode::OK, Json(serde_json::json!({
            "status": "success",
            "message": resp.message,
            "data": resp.data
        })))
    } else {
        (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({
            "status": "error",
            "message": resp.message
        })))
    }
}

async fn handle_batch(
    State(state): State<AppState>,
    Json(payload): Json<BatchPayload>,
) -> impl IntoResponse {
    let raw_links = payload.links.or(payload.urls).unwrap_or_default();
    let count = raw_links.len();
    tracing::info!("[IPC] Received batch of {} links", count);

    for link in raw_links {
        let req = IpcRequest::Add {
            url: link,
            out: None,
            dir: None,
            category: Some("Batch".to_string()),
            queue: None,
            connections: None,
            limit: None,
            start_now: false,
        };
        let _ = state.handler.handle(req).await;
    }

    Json(serde_json::json!({
        "status": "batch_received",
        "count": count
    }))
}

async fn handle_notify() -> impl IntoResponse {
    Json(serde_json::json!({ "status": "acknowledged" }))
}

async fn handle_jsonrpc(
    State(state): State<AppState>,
    Json(req): Json<JsonRpcRequest>,
) -> impl IntoResponse {
    let id = req.id.clone();

    match req.method.as_str() {
        "aria2.getVersion" => {
            Json(serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": {
                    "version": "0.3.0 (Tigris)",
                    "enabledFeatures": ["AsyncDNS", "BitTorrent", "FirefoxExtension", "ChromeMV3"]
                }
            }))
        }
        "aria2.getGlobalStat" => {
            Json(serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": {
                    "downloadSpeed": "0",
                    "uploadSpeed": "0",
                    "numActive": "0",
                    "numWaiting": "0",
                    "numStopped": "0"
                }
            }))
        }
        "aria2.tellActive" => {
            Json(serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": []
            }))
        }
        "aria2.tellWaiting" | "aria2.tellStopped" => {
            Json(serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": []
            }))
        }
        "aria2.addUri" => {
            let mut target_url = None;
            for param in &req.params {
                if let Some(arr) = param.as_array() {
                    if let Some(first) = arr.first().and_then(|v| v.as_str()) {
                        target_url = Some(first.to_string());
                        break;
                    }
                }
            }

            if let Some(url) = target_url {
                let add_req = IpcRequest::Add {
                    url,
                    out: None,
                    dir: None,
                    category: None,
                    queue: None,
                    connections: None,
                    limit: None,
                    start_now: true,
                };
                let resp = state.handler.handle(add_req).await;
                let gid = resp.data.and_then(|d| d.get("id").and_then(|v| v.as_i64())).unwrap_or(1);
                Json(serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": format!("{:016x}", gid)
                }))
            } else {
                Json(serde_json::json!({
                    "jsonrpc": "2.0",
                    "id": id,
                    "error": { "code": -32602, "message": "Invalid params: URI array missing" }
                }))
            }
        }
        _ => {
            Json(serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": "OK"
            }))
        }
    }
}
