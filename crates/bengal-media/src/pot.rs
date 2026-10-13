use std::path::PathBuf;
use std::time::Duration;
use bengal_core::AppPaths;
use crate::dependencies::MediaDependencies;

pub const DEFAULT_POT_PROVIDER_URL: &str = "http://127.0.0.1:4416";
pub const DYNAMIC_YOUTUBE_CLIENTS: &str = "mweb,android,ios,web_creator,web_embedded,web_safari,tv_embedded,visionos,web";

/// Returns path to Deno binary from Bengal DM media download tools (`$XDG_DATA_HOME/bengal/bin/deno`)
/// or system `$PATH`.
pub fn get_deno_executable_path() -> Option<PathBuf> {
    MediaDependencies::find_tool("deno")
}

/// Returns environment variables for yt-dlp subprocesses.
/// Injects the DENO executable path so bgutil-ytdlp-pot-provider can find it without PATH dependency.
pub fn get_pot_env() -> Vec<(String, String)> {
    let mut env = Vec::new();
    if let Some(deno_path) = get_deno_executable_path() {
        env.push(("DENO".to_string(), deno_path.to_string_lossy().to_string()));
    }
    env
}

/// Checks if a bgutil-ytdlp-pot-provider HTTP server is reachable and active.
/// Returns: (is_available, status_message_or_version)
pub async fn check_pot_provider_status(base_url: Option<&str>, timeout: Duration) -> (bool, String) {
    let raw_url = base_url.unwrap_or(DEFAULT_POT_PROVIDER_URL).trim().trim_end_matches('/');
    let clean_url = if !raw_url.starts_with("http://") && !raw_url.starts_with("https://") {
        format!("http://{}", raw_url)
    } else {
        raw_url.to_string()
    };

    let ping_url = format!("{}/ping", clean_url);
    let client = reqwest::Client::builder()
        .timeout(timeout)
        .build();

    let client = match client {
        Ok(c) => c,
        Err(e) => return (false, format!("Client build error: {}", e)),
    };

    match client.get(&ping_url).header("User-Agent", "BengalDownloadManager").send().await {
        Ok(resp) => {
            if resp.status().is_success() {
                if let Ok(text) = resp.text().await {
                    if let Ok(json) = serde_json::from_str::<serde_json::Value>(&text) {
                        let ver = json.get("version")
                            .or_else(|| json.get("status"))
                            .and_then(|v| v.as_str())
                            .unwrap_or("Active");
                        return (true, format!("Connected ({})", ver));
                    }
                }
                (true, "Connected (Active)".to_string())
            } else {
                (false, format!("HTTP status {}", resp.status()))
            }
        }
        Err(e) => (false, format!("Not reachable: {}", e)),
    }
}

/// Quick check to determine if local bgutil POT daemon is running.
pub async fn is_pot_provider_available(base_url: Option<&str>, timeout: Duration) -> bool {
    let (available, _) = check_pot_provider_status(base_url, timeout).await;
    available
}

/// Returns `--plugin-dirs` arguments if any `yt_dlp_plugins` package is discoverable
/// in `bin_dir()` or `$XDG_DATA_HOME/bengal/plugins/`.
pub fn get_pot_plugin_args() -> Vec<String> {
    let mut plugin_dirs = Vec::new();

    let bin_dir = MediaDependencies::bin_dir();
    if bin_dir.join("yt_dlp_plugins").is_dir() {
        plugin_dirs.push(bin_dir);
    }

    let plugins_base = AppPaths::data_dir().join("plugins");
    if plugins_base.join("yt_dlp_plugins").is_dir() && !plugin_dirs.contains(&plugins_base) {
        plugin_dirs.push(plugins_base);
    }

    let mut args = Vec::new();
    for d in plugin_dirs {
        args.push("--plugin-dirs".to_string());
        args.push(d.to_string_lossy().to_string());
    }
    args
}

/// Returns `--extractor-args` for YouTube player clients.
pub fn get_youtube_player_client_args(custom_client: Option<&str>) -> Vec<String> {
    let client = custom_client.unwrap_or("auto").trim();
    let client_lower = client.to_lowercase();

    if client_lower == "auto"
        || client_lower == "dynamic"
        || client_lower.contains("dynamic")
        || client.is_empty()
    {
        return vec![
            "--extractor-args".to_string(),
            format!("youtube:player_client={}", DYNAMIC_YOUTUBE_CLIENTS),
        ];
    }

    if client_lower == "default" || client_lower == "none" || client_lower == "yt-dlp default" {
        return Vec::new();
    }

    vec![
        "--extractor-args".to_string(),
        format!("youtube:player_client={}", client),
    ]
}

/// Returns resilient multi-client player client extractor arguments for retry attempts.
pub fn get_youtube_fallback_client_args() -> Vec<String> {
    vec![
        "--extractor-args".to_string(),
        format!("youtube:player_client={}", DYNAMIC_YOUTUBE_CLIENTS),
    ]
}

/// Builds the appropriate yt-dlp `--extractor-args` for PO token handling.
pub async fn get_pot_extractor_args(pot_enabled: bool) -> Vec<String> {
    if !pot_enabled {
        return vec![
            "--extractor-args".to_string(),
            "youtube:fetch_pot=never".to_string(),
        ];
    }

    // 1. Check if local bgutil HTTP daemon is running
    if is_pot_provider_available(Some(DEFAULT_POT_PROVIDER_URL), Duration::from_millis(300)).await {
        return vec![
            "--extractor-args".to_string(),
            format!("youtubepot-bgutilhttp:base_url={}", DEFAULT_POT_PROVIDER_URL),
            "--extractor-args".to_string(),
            format!("youtubepot:base_url={}", DEFAULT_POT_PROVIDER_URL),
        ];
    }

    // 2. Check if Deno is available
    if get_deno_executable_path().is_some() {
        return Vec::new();
    }

    // 3. Check if Node.js is available
    if MediaDependencies::find_in_system_path("node").is_some() {
        return Vec::new();
    }

    // 4. If no JS engine is present, disable fetch_pot to prevent format corruption
    vec![
        "--extractor-args".to_string(),
        "youtube:fetch_pot=never".to_string(),
    ]
}

/// Return `--js-runtimes` argument for yt-dlp if deno, node, or bun is available.
pub fn get_js_runtime_args() -> Vec<String> {
    if let Some(deno_bin) = get_deno_executable_path() {
        return vec![
            "--js-runtimes".to_string(),
            format!("deno:{}", deno_bin.to_string_lossy()),
        ];
    }
    if let Some(node_bin) = MediaDependencies::find_in_system_path("node") {
        return vec![
            "--js-runtimes".to_string(),
            format!("node:{}", node_bin.to_string_lossy()),
        ];
    }
    if let Some(bun_bin) = MediaDependencies::find_in_system_path("bun") {
        return vec![
            "--js-runtimes".to_string(),
            format!("bun:{}", bun_bin.to_string_lossy()),
        ];
    }
    Vec::new()
}
