use std::path::PathBuf;
use std::time::Duration;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use tokio::process::Command;
use crate::dependencies::MediaDependencies;
use crate::pot::{
    get_js_runtime_args, get_pot_env, get_pot_extractor_args, get_pot_plugin_args,
    get_youtube_fallback_client_args, get_youtube_player_client_args,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MediaFormat {
    pub format_id: String,
    pub ext: String,
    pub vcodec: String,
    pub acodec: String,
    pub height: u32,
    pub width: u32,
    pub fps: f32,
    pub filesize: u64,
    pub tbr: f64,
    pub res_label: String,
    pub format_note: String,
    pub is_video: bool,
    pub is_audio: bool,
    pub url: String,
    pub manifest_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SingleVideoInfo {
    pub title: String,
    pub id: String,
    pub uploader: String,
    pub duration: f64,
    pub thumbnail: String,
    pub webpage_url: String,
    pub formats: Vec<MediaFormat>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaylistEntry {
    pub index: usize,
    pub id: String,
    pub title: String,
    pub duration: f64,
    pub url: String,
    pub thumbnail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlaylistInfo {
    pub title: String,
    pub total_items: usize,
    pub thumbnail: String,
    pub entries: Vec<PlaylistEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MediaExtractionResult {
    Single(SingleVideoInfo),
    Playlist(PlaylistInfo),
}

#[derive(Debug, Clone, Default)]
pub struct ExtractorOptions {
    pub url: String,
    pub cookies_browser: Option<String>,
    pub cookies_file: Option<PathBuf>,
    pub referrer: Option<String>,
    pub user_agent: Option<String>,
    pub cookies: Option<String>,
    pub no_playlist: bool,
    pub playlist_start: Option<usize>,
    pub playlist_end: Option<usize>,
    pub youtube_client: Option<String>,
    pub pot_enabled: bool,
}

/// Creates a temporary Netscape cookies file from a semicolon-separated cookie header string.
pub fn create_temp_netscape_cookies(cookie_str: &str, target_url: &str) -> Option<PathBuf> {
    if cookie_str.trim().is_empty() {
        return None;
    }

    let parsed_host = url::Url::parse(target_url).ok();
    let host = parsed_host
        .as_ref()
        .and_then(|u| u.host_str())
        .unwrap_or("youtube.com")
        .to_lowercase();

    let parts: Vec<&str> = host.split('.').collect();
    let base_domain = if parts.len() >= 2 {
        format!(".{}", parts[parts.len() - 2..].join("."))
    } else {
        format!(".{}", host)
    };

    let is_yt = base_domain.contains("youtube.com") || base_domain.contains("youtu.be");
    let yt_ignore = [
        "_gcl_au", "__Secure-ROLLOUT_TOKEN", "GPS", "OTZ", "_ga", "_gid", "1P_JAR",
    ];

    let mut lines = vec![
        "# Netscape HTTP Cookie File".to_string(),
        "# https://curl.haxx.se/rfc/cookie_spec.html".to_string(),
        "".to_string(),
    ];

    let mut seen = std::collections::HashSet::new();
    for item in cookie_str.split(';') {
        let item = item.trim();
        if item.is_empty() || !item.contains('=') {
            continue;
        }
        let mut sp = item.splitn(2, '=');
        let name = sp.next().unwrap_or("").trim();
        let val = sp.next().unwrap_or("").trim();

        if name.is_empty() || !seen.insert(name.to_string()) {
            continue;
        }
        if is_yt && yt_ignore.contains(&name) {
            continue;
        }

        let is_secure = if name.starts_with("__Secure-") || name.starts_with("__Host-") {
            "TRUE"
        } else {
            "FALSE"
        };

        lines.push(format!(
            "{}\tTRUE\t/\t{}\t2147483647\t{}\t{}",
            base_domain, is_secure, name, val
        ));
    }

    if lines.len() <= 3 {
        return None;
    }

    let temp_dir = std::env::temp_dir();
    let path = temp_dir.join(format!("bengal_cookies_{}.txt", std::process::id()));
    if std::fs::write(&path, lines.join("\n")).is_ok() {
        Some(path)
    } else {
        None
    }
}

pub struct MediaExtractor;

impl MediaExtractor {
    /// Extracts media or playlist metadata using yt-dlp.
    pub async fn extract(opts: &ExtractorOptions) -> Result<MediaExtractionResult> {
        let yt_dlp_bin = MediaDependencies::ensure_ytdlp().await
            .context("Failed to locate or download yt-dlp binary")?;

        let temp_cookies = opts.cookies.as_deref().and_then(|c| create_temp_netscape_cookies(c, &opts.url));

        let build_cmd = |include_cookies: bool| {
            let mut cmd = Command::new(&yt_dlp_bin);
            cmd.arg("-J");

            if opts.no_playlist {
                cmd.arg("--no-playlist");
            } else {
                cmd.arg("--flat-playlist");
                if let Some(start) = opts.playlist_start {
                    cmd.arg("--playlist-start").arg(start.to_string());
                }
                if let Some(end) = opts.playlist_end {
                    cmd.arg("--playlist-end").arg(end.to_string());
                } else {
                    cmd.arg("--playlist-end").arg("100");
                }
            }

            cmd.arg("--no-warnings");
            cmd.arg("--remote-components").arg("ejs:github");

            for arg in get_youtube_player_client_args(opts.youtube_client.as_deref()) {
                cmd.arg(arg);
            }
            for arg in get_js_runtime_args() {
                cmd.arg(arg);
            }
            for arg in get_pot_plugin_args() {
                cmd.arg(arg);
            }

            if let Some(ffmpeg_bin) = MediaDependencies::find_tool("ffmpeg") {
                cmd.arg("--ffmpeg-location").arg(ffmpeg_bin);
            }

            if let Some(ref ref_url) = opts.referrer {
                cmd.arg("--referer").arg(ref_url);
                if let Ok(u) = url::Url::parse(ref_url) {
                    if let Some(host) = u.host_str() {
                        cmd.arg("--add-header").arg(format!("Origin:{}://{}", u.scheme(), host));
                    }
                }
            }

            if let Some(ref ua) = opts.user_agent {
                cmd.arg("--user-agent").arg(ua);
            }

            cmd.arg("--add-header").arg("Accept-Language:en-US,en;q=0.9");

            if include_cookies {
                if let Some(ref tf) = temp_cookies {
                    cmd.arg("--cookies").arg(tf);
                } else if let Some(ref cf) = opts.cookies_file {
                    if cf.exists() {
                        cmd.arg("--cookies").arg(cf);
                    }
                } else if let Some(ref cb) = opts.cookies_browser {
                    if !cb.is_empty() && cb.to_lowercase() != "none" {
                        cmd.arg("--cookies-from-browser").arg(cb.to_lowercase());
                    }
                }
            }

            for (k, v) in get_pot_env() {
                cmd.env(k, v);
            }

            cmd.arg(&opts.url);
            cmd
        };

        // First attempt with full options
        let mut cmd = build_cmd(true);
        for arg in get_pot_extractor_args(opts.pot_enabled).await {
            cmd.arg(arg);
        }

        tracing::info!("[MediaExtractor] Executing yt-dlp metadata extraction for: {}", opts.url);

        let output = tokio::time::timeout(Duration::from_secs(35), cmd.output()).await
            .map_err(|_| anyhow::anyhow!("Metadata extraction timed out after 35 seconds"))?
            .context("Failed to execute yt-dlp subprocess")?;

        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        let parsed_json: serde_json::Value = if output.status.success() {
            serde_json::from_str(&stdout).context("Failed to parse yt-dlp JSON output")?
        } else {
            // Check for bot verification or bad cookies to retry clean extraction
            let err_lower = format!("{} {}", stderr, stdout).to_lowercase();
            let is_bot_or_cookie = err_lower.contains("bot")
                || err_lower.contains("sign in")
                || err_lower.contains("429")
                || err_lower.contains("login_required")
                || err_lower.contains("cookie");

            if is_bot_or_cookie {
                tracing::warn!("[MediaExtractor] Retrying extraction with clean fallback configuration...");
                let mut retry_cmd = build_cmd(false);
                for arg in get_youtube_fallback_client_args() {
                    retry_cmd.arg(arg);
                }
                for arg in get_pot_extractor_args(opts.pot_enabled).await {
                    retry_cmd.arg(arg);
                }

                let retry_output = tokio::time::timeout(Duration::from_secs(35), retry_cmd.output()).await
                    .map_err(|_| anyhow::anyhow!("Clean retry extraction timed out after 35 seconds"))?
                    .context("Failed to execute yt-dlp retry subprocess")?;

                let retry_stdout = String::from_utf8_lossy(&retry_output.stdout);
                if retry_output.status.success() {
                    serde_json::from_str(&retry_stdout).context("Failed to parse yt-dlp retry JSON")?
                } else {
                    let retry_err = String::from_utf8_lossy(&retry_output.stderr);
                    bail!("yt-dlp extraction failed: {}", retry_err.trim());
                }
            } else {
                bail!("yt-dlp extraction failed: {}", stderr.trim());
            }
        };

        // Clean up temporary cookies file if created
        if let Some(ref tf) = temp_cookies {
            let _ = std::fs::remove_file(tf);
        }

        // Parse result into Single or Playlist
        if parsed_json.get("_type").and_then(|v| v.as_str()) == Some("playlist")
            || (parsed_json.get("entries").and_then(|v| v.as_array()).map(|a| !a.is_empty()).unwrap_or(false)
                && parsed_json.get("formats").is_none())
        {
            Ok(MediaExtractionResult::Playlist(Self::parse_playlist(&parsed_json, &opts.url)))
        } else {
            Ok(MediaExtractionResult::Single(Self::parse_single(&parsed_json, &opts.url)))
        }
    }

    fn parse_single(data: &serde_json::Value, fallback_url: &str) -> SingleVideoInfo {
        let title = data.get("title").and_then(|v| v.as_str()).unwrap_or("Untitled Media").to_string();
        let id = data.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let uploader = data.get("uploader")
            .or_else(|| data.get("channel"))
            .and_then(|v| v.as_str())
            .unwrap_or("Unknown")
            .to_string();
        let duration = data.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.0);
        let webpage_url = data.get("webpage_url").and_then(|v| v.as_str()).unwrap_or(fallback_url).to_string();

        let mut thumbnail = data.get("thumbnail").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if thumbnail.is_empty() {
            if let Some(thumbs) = data.get("thumbnails").and_then(|v| v.as_array()) {
                if let Some(last) = thumbs.last().and_then(|t| t.get("url")).and_then(|u| u.as_str()) {
                    thumbnail = last.to_string();
                }
            }
        }

        let mut formats = Vec::new();
        if let Some(raw_formats) = data.get("formats").and_then(|v| v.as_array()) {
            for fmt in raw_formats {
                let fmt_id = fmt.get("format_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                let ext = fmt.get("ext").and_then(|v| v.as_str()).unwrap_or("").to_lowercase();
                let vcodec = fmt.get("vcodec").and_then(|v| v.as_str()).unwrap_or("none").to_string();
                let acodec = fmt.get("acodec").and_then(|v| v.as_str()).unwrap_or("none").to_string();

                if ext == "mhtml" || ext == "html" || ext == "htm" || (vcodec == "none" && acodec == "none") {
                    continue;
                }

                let height = fmt.get("height").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
                let width = fmt.get("width").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
                let fps = fmt.get("fps").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
                let tbr = fmt.get("tbr").and_then(|v| v.as_f64()).unwrap_or(0.0);

                let mut filesize = fmt.get("filesize")
                    .or_else(|| fmt.get("filesize_approx"))
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);

                if filesize == 0 && duration > 0.0 && tbr > 0.0 {
                    filesize = (duration * tbr * 125.0) as u64;
                }

                let format_note = fmt.get("format_note").and_then(|v| v.as_str()).unwrap_or("").to_string();
                let url = fmt.get("url").and_then(|v| v.as_str()).unwrap_or("").to_string();
                let manifest_url = fmt.get("manifest_url").and_then(|v| v.as_str()).unwrap_or("").to_string();

                let is_video = vcodec != "none";
                let is_audio = acodec != "none";

                let res_label = if height > 0 {
                    format!("{}p", height)
                } else if width > 0 {
                    format!("{}w", width)
                } else if is_video {
                    "Video".to_string()
                } else {
                    "Audio Only".to_string()
                };

                formats.push(MediaFormat {
                    format_id: fmt_id,
                    ext,
                    vcodec,
                    acodec,
                    height,
                    width,
                    fps,
                    filesize,
                    tbr,
                    res_label,
                    format_note,
                    is_video,
                    is_audio,
                    url,
                    manifest_url,
                });
            }
        }

        // Sort formats: video first descending by height, then audio descending by bitrate
        formats.sort_by(|a, b| {
            match (a.is_video, b.is_video) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                (true, true) => {
                    b.height.cmp(&a.height).then_with(|| b.tbr.partial_cmp(&a.tbr).unwrap_or(std::cmp::Ordering::Equal))
                }
                (false, false) => {
                    b.tbr.partial_cmp(&a.tbr).unwrap_or(std::cmp::Ordering::Equal)
                }
            }
        });

        SingleVideoInfo {
            title,
            id,
            uploader,
            duration,
            thumbnail,
            webpage_url,
            formats,
        }
    }

    fn parse_playlist(data: &serde_json::Value, _fallback_url: &str) -> PlaylistInfo {
        let title = data.get("title").and_then(|v| v.as_str()).unwrap_or("Playlist").to_string();
        let mut entries = Vec::new();

        if let Some(raw_entries) = data.get("entries").and_then(|v| v.as_array()) {
            for (idx, entry) in raw_entries.iter().enumerate() {
                let id = entry.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                let item_title = entry.get("title")
                    .and_then(|v| v.as_str())
                    .unwrap_or(&format!("Item {}", idx + 1))
                    .to_string();
                let duration = entry.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let item_url = entry.get("webpage_url")
                    .or_else(|| entry.get("url"))
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| format!("https://www.youtube.com/watch?v={}", id));

                let mut entry_thumb = entry.get("thumbnail").and_then(|v| v.as_str()).unwrap_or("").to_string();
                if entry_thumb.is_empty() {
                    if let Some(thumbs) = entry.get("thumbnails").and_then(|v| v.as_array()) {
                        if let Some(last) = thumbs.last().and_then(|t| t.get("url")).and_then(|u| u.as_str()) {
                            entry_thumb = last.to_string();
                        }
                    }
                }

                entries.push(PlaylistEntry {
                    index: idx + 1,
                    id,
                    title: item_title,
                    duration,
                    url: item_url,
                    thumbnail: entry_thumb,
                });
            }
        }

        let mut thumbnail = data.get("thumbnail").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if thumbnail.is_empty() {
            if let Some(first) = entries.first() {
                thumbnail = first.thumbnail.clone();
            }
        }

        PlaylistInfo {
            title,
            total_items: entries.len(),
            thumbnail,
            entries,
        }
    }
}
