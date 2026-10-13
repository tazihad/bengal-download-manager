use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RefreshLinkRequest {
    pub download_id: i64,
    pub old_url: String,
    pub new_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RefreshLinkResult {
    pub success: bool,
    pub message: String,
    pub size_matched: bool,
}
