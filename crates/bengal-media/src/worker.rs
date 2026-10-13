use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use anyhow::{bail, Context, Result};
use regex::Regex;
use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::mpsc;

use crate::dependencies::MediaDependencies;
use crate::extractor::create_temp_netscape_cookies;
use crate::pot::{
    get_js_runtime_args, get_pot_env, get_pot_extractor_args, get_pot_plugin_args,
    get_youtube_player_client_args,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MediaDownloadProgress {
    pub downloaded_bytes: u64,
    pub total_bytes: u64,
    pub percentage: f32,
    pub speed_bps: f64,
    pub eta_secs: Option<u64>,
    pub status: String,
    pub output_file: Option<PathBuf>,
}

#[derive(Debug, Clone)]
pub struct MediaDownloadConfig {
    pub url: String,
    pub save_dir: PathBuf,
    pub filename: Option<String>,
    pub format_spec: String,
    pub is_audio_only: bool,
    pub audio_format: Option<String>,
    pub merge_output_format: Option<String>,
    pub cookies_browser: Option<String>,
    pub cookies_file: Option<PathBuf>,
    pub cookies: Option<String>,
    pub referrer: Option<String>,
    pub user_agent: Option<String>,
    pub max_connections: usize,
    pub rate_limit_bytes: u64,
    pub embed_thumbnail: bool,
    pub pot_enabled: bool,
}

impl Default for MediaDownloadConfig {
    fn default() -> Self {
        Self {
            url: String::new(),
            save_dir: PathBuf::from("."),
            filename: None,
            format_spec: "bestvideo+bestaudio/best".to_string(),
            is_audio_only: false,
            audio_format: None,
            merge_output_format: None,
            cookies_browser: None,
            cookies_file: None,
            cookies: None,
            referrer: None,
            user_agent: None,
            max_connections: 8,
            rate_limit_bytes: 0,
            embed_thumbnail: true,
            pot_enabled: true,
        }
    }
}

pub fn parse_size_str_to_bytes(s: &str) -> u64 {
    let clean = s.trim().to_uppercase();
    let units = [
        ("GIB", 1024 * 1024 * 1024),
        ("GB", 1000 * 1000 * 1000),
        ("MIB", 1024 * 1024),
        ("MB", 1000 * 1000),
        ("KIB", 1024),
        ("KB", 1000),
        ("B", 1),
    ];

    for (unit, factor) in units {
        if clean.ends_with(unit) {
            let num_str = clean.trim_end_matches(unit).trim();
            if let Ok(num) = num_str.parse::<f64>() {
                return (num * factor as f64) as u64;
            }
        }
    }

    clean.chars().filter(|c| c.is_ascii_digit()).collect::<String>()
        .parse::<u64>().unwrap_or(0)
}

pub fn parse_eta_to_seconds(s: &str) -> Option<u64> {
    let parts: Vec<&str> = s.trim().split(':').collect();
    match parts.len() {
        2 => {
            let mins: u64 = parts[0].parse().ok()?;
            let secs: u64 = parts[1].parse().ok()?;
            Some(mins * 60 + secs)
        }
        3 => {
            let hrs: u64 = parts[0].parse().ok()?;
            let mins: u64 = parts[1].parse().ok()?;
            let secs: u64 = parts[2].parse().ok()?;
            Some(hrs * 3600 + mins * 60 + secs)
        }
        _ => None,
    }
}

pub struct MediaDownloadWorker {
    config: MediaDownloadConfig,
    cancel_flag: Arc<AtomicBool>,
}

impl MediaDownloadWorker {
    pub fn new(config: MediaDownloadConfig) -> (Self, Arc<AtomicBool>) {
        let cancel_flag = Arc::new(AtomicBool::new(false));
        (
            Self {
                config,
                cancel_flag: Arc::clone(&cancel_flag),
            },
            cancel_flag,
        )
    }

    /// Spawns yt-dlp download subprocess and streams progress updates through the provided channel.
    pub async fn run(self, progress_tx: mpsc::Sender<MediaDownloadProgress>) -> Result<PathBuf> {
        let yt_dlp_bin = MediaDependencies::ensure_ytdlp().await
            .context("Failed to find or download yt-dlp binary")?;

        std::fs::create_dir_all(&self.config.save_dir)
            .context("Failed to create save directory")?;

        let temp_dir = bengal_core::AppPaths::cache_dir().join("downloads");
        std::fs::create_dir_all(&temp_dir).ok();

        let temp_cookies = self.config.cookies.as_deref().and_then(|c| create_temp_netscape_cookies(c, &self.config.url));

        let output_tmpl = match &self.config.filename {
            Some(name) if !name.trim().is_empty() => {
                let stem = Path::new(name).file_stem().and_then(|s| s.to_str()).unwrap_or(name);
                format!("{}.%(ext)s", stem)
            }
            _ => {
                if self.config.is_audio_only {
                    "%(title).100B [%(id)s].%(ext)s".to_string()
                } else {
                    "%(title).100B [%(id)s]%(height& [{}p]|)s.%(ext)s".to_string()
                }
            }
        };

        let mut cmd = Command::new(&yt_dlp_bin);
        cmd.arg("--newline")
            .arg("--no-warnings")
            .arg("--progress-delta").arg("0.1")
            .arg("--remote-components").arg("ejs:github")
            .arg("--restrict-filenames")
            .arg("--paths").arg(format!("home:{}", self.config.save_dir.to_string_lossy()))
            .arg("--paths").arg(format!("temp:{}", temp_dir.to_string_lossy()))
            .arg("--continue")
            .arg("--no-keep-fragments")
            .arg("--format").arg(&self.config.format_spec)
            .arg("-o").arg(&output_tmpl);

        for arg in get_youtube_player_client_args(None) {
            cmd.arg(arg);
        }
        for arg in get_js_runtime_args() {
            cmd.arg(arg);
        }
        for arg in get_pot_plugin_args() {
            cmd.arg(arg);
        }
        for arg in get_pot_extractor_args(self.config.pot_enabled).await {
            cmd.arg(arg);
        }

        if let Some(ffmpeg_bin) = MediaDependencies::find_tool("ffmpeg") {
            cmd.arg("--ffmpeg-location").arg(ffmpeg_bin);
        }

        if self.config.embed_thumbnail {
            cmd.arg("--embed-thumbnail")
                .arg("--convert-thumbnails").arg("png");
        }

        if self.config.is_audio_only {
            cmd.arg("-x");
            if let Some(ref afmt) = self.config.audio_format {
                if afmt != "auto" && afmt != "best" {
                    cmd.arg("--audio-format").arg(afmt)
                        .arg("--audio-quality").arg("0");
                }
            }
        } else if let Some(ref mfmt) = self.config.merge_output_format {
            if mfmt != "auto" && mfmt != "best" {
                cmd.arg("--merge-output-format").arg(mfmt);
            }
        }

        if self.config.max_connections > 1 {
            cmd.arg("--concurrent-fragments").arg(self.config.max_connections.to_string());
        }

        if self.config.rate_limit_bytes > 0 {
            cmd.arg("--limit-rate").arg(self.config.rate_limit_bytes.to_string());
        }

        if let Some(ref ref_url) = self.config.referrer {
            cmd.arg("--referer").arg(ref_url);
        }
        if let Some(ref ua) = self.config.user_agent {
            cmd.arg("--user-agent").arg(ua);
        }
        cmd.arg("--add-header").arg("Accept-Language:en-US,en;q=0.9");

        if let Some(ref tf) = temp_cookies {
            cmd.arg("--cookies").arg(tf);
        } else if let Some(ref cf) = self.config.cookies_file {
            if cf.exists() {
                cmd.arg("--cookies").arg(cf);
            }
        } else if let Some(ref cb) = self.config.cookies_browser {
            if !cb.is_empty() && cb.to_lowercase() != "none" {
                cmd.arg("--cookies-from-browser").arg(cb.to_lowercase());
            }
        }

        for (k, v) in get_pot_env() {
            cmd.env(k, v);
        }

        cmd.arg(&self.config.url);

        cmd.stdout(Stdio::piped());
        cmd.stderr(Stdio::piped());

        tracing::info!("[MediaWorker] Launching yt-dlp download for {}", self.config.url);

        let mut child = cmd.spawn().context("Failed to spawn yt-dlp child process")?;
        let stdout = child.stdout.take().context("Failed to capture child stdout")?;

        let mut reader = BufReader::new(stdout).lines();

        let re_dest = Regex::new(r"(?i)\[(?:download|aria2c)\]\s+Destination:\s+([^\r\n]+)").unwrap();
        let re_merge = Regex::new(r#"(?i)\[(?:Merger|ExtractAudio|VideoRemuxer)\]\s+(?:Merging formats into|Remuxing video into)?\s*"?([^"\r\n]+\.(?:mp4|mkv|webm|mp3|m4a|flv|avi))"?"#).unwrap();
        let re_move = Regex::new(r#"(?i)\[MoveFiles\]\s+Moving file\s+"?[^"]+"?\s+to\s+"?([^"\r\n]+)"?"#).unwrap();
        let re_progress = Regex::new(r"\[download\]\s+([0-9.]+)%\s+of\s+~?\s*([0-9.]+\s*[KMGT]?i?B)(?:\s+at\s+([0-9.]+\s*[KMGT]?i?B/s))?(?:\s+ETA\s+([0-9:]+))?").unwrap();

        let mut final_path: Option<PathBuf> = None;
        let mut last_progress = MediaDownloadProgress {
            downloaded_bytes: 0,
            total_bytes: 0,
            percentage: 0.0,
            speed_bps: 0.0,
            eta_secs: None,
            status: "Starting...".to_string(),
            output_file: None,
        };

        while let Some(line) = reader.next_line().await? {
            if self.cancel_flag.load(Ordering::Relaxed) {
                tracing::info!("[MediaWorker] Cancellation requested. Killing child process.");
                let _ = child.kill().await;
                if let Some(ref tf) = temp_cookies {
                    let _ = std::fs::remove_file(tf);
                }
                bail!("Download cancelled by user");
            }

            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }

            if let Some(cap) = re_dest.captures(trimmed) {
                let dest = cap.get(1).map(|m| m.as_str().trim()).unwrap_or("");
                let p = PathBuf::from(dest);
                if !dest.ends_with(".part") && !dest.ends_with(".ytdl") {
                    final_path = Some(p.clone());
                    last_progress.output_file = Some(p);
                }
            } else if let Some(cap) = re_merge.captures(trimmed) {
                let merge_file = cap.get(1).map(|m| m.as_str().trim()).unwrap_or("");
                let p = PathBuf::from(merge_file);
                final_path = Some(p.clone());
                last_progress.output_file = Some(p);
                last_progress.status = "Merging streams...".to_string();
                let _ = progress_tx.send(last_progress.clone()).await;
            } else if let Some(cap) = re_move.captures(trimmed) {
                let move_dest = cap.get(1).map(|m| m.as_str().trim()).unwrap_or("");
                let p = PathBuf::from(move_dest);
                final_path = Some(p.clone());
                last_progress.output_file = Some(p);
            } else if let Some(cap) = re_progress.captures(trimmed) {
                let pct: f32 = cap.get(1).and_then(|m| m.as_str().parse().ok()).unwrap_or(0.0);
                let total_str = cap.get(2).map(|m| m.as_str()).unwrap_or("");
                let total = parse_size_str_to_bytes(total_str);
                let downloaded = ((pct / 100.0) * total as f32) as u64;

                let speed_bps = if let Some(sp) = cap.get(3) {
                    let clean_sp = sp.as_str().trim_end_matches("/s");
                    parse_size_str_to_bytes(clean_sp) as f64
                } else {
                    0.0
                };

                let eta = cap.get(4).and_then(|m| parse_eta_to_seconds(m.as_str()));

                last_progress.percentage = pct;
                last_progress.total_bytes = total;
                last_progress.downloaded_bytes = downloaded;
                last_progress.speed_bps = speed_bps;
                last_progress.eta_secs = eta;
                last_progress.status = format!("Downloading: {:.1}%", pct);

                let _ = progress_tx.send(last_progress.clone()).await;
            }
        }

        let status = child.wait().await?;
        if let Some(ref tf) = temp_cookies {
            let _ = std::fs::remove_file(tf);
        }

        if !status.success() {
            bail!("yt-dlp exited with status: {}", status);
        }

        last_progress.percentage = 100.0;
        last_progress.status = "Complete".to_string();
        let _ = progress_tx.send(last_progress).await;

        let resolved_file = final_path.unwrap_or_else(|| self.config.save_dir.join("media_download"));
        tracing::info!("[MediaWorker] Media download completed: {}", resolved_file.display());
        Ok(resolved_file)
    }
}
