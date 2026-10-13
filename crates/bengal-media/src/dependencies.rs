use std::path::PathBuf;
use std::process::Command;
use anyhow::{Context, Result};
use bengal_core::AppPaths;

#[derive(Debug, Clone)]
pub struct ToolInfo {
    pub name: String,
    pub path: Option<PathBuf>,
    pub version: Option<String>,
    pub available: bool,
    pub role: String,
}

pub struct MediaDependencies;

impl MediaDependencies {
    /// Returns the local application bin directory: `$XDG_DATA_HOME/bengal/bin/`
    pub fn bin_dir() -> PathBuf {
        AppPaths::data_dir().join("bin")
    }

    /// Finds the path to a specific binary (`yt-dlp`, `ffmpeg`, `ffprobe`, `deno`, `AtomicParsley`).
    /// Searches the application `bin_dir()` first, then falls back to system `$PATH`.
    pub fn find_tool(name: &str) -> Option<PathBuf> {
        let exe_name = if cfg!(windows) {
            format!("{}.exe", name)
        } else {
            name.to_string()
        };

        // 1. Check local app bin directory
        let local_path = Self::bin_dir().join(&exe_name);
        if local_path.is_file() {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(meta) = local_path.metadata() {
                    if meta.permissions().mode() & 0o111 != 0 {
                        return Some(local_path);
                    }
                }
            }
            #[cfg(not(unix))]
            return Some(local_path);
        }

        // 2. Check system PATH
        Self::find_in_system_path(&exe_name)
    }

    /// Searches system `$PATH` for the given executable name.
    pub fn find_in_system_path(exe_name: &str) -> Option<PathBuf> {
        if let Some(paths) = std::env::var_os("PATH") {
            for dir in std::env::split_paths(&paths) {
                let full = dir.join(exe_name);
                if full.is_file() {
                    #[cfg(unix)]
                    {
                        use std::os::unix::fs::PermissionsExt;
                        if let Ok(meta) = full.metadata() {
                            if meta.permissions().mode() & 0o111 != 0 {
                                return Some(full);
                            }
                        }
                    }
                    #[cfg(not(unix))]
                    return Some(full);
                }
            }
        }
        None
    }

    /// Queries the version string of a tool.
    pub fn get_tool_version(path: &PathBuf, version_flag: &str) -> Option<String> {
        let output = Command::new(path).arg(version_flag).output().ok()?;
        if output.status.success() {
            let out_str = String::from_utf8_lossy(&output.stdout);
            let first_line = out_str.lines().next().unwrap_or("").trim();
            Some(first_line.to_string())
        } else {
            None
        }
    }

    /// Inspects the presence and versions of all media tools.
    pub fn inspect_all() -> Vec<ToolInfo> {
        let tools = [
            ("yt-dlp", "--version", "Core Video & Audio Extractor"),
            ("ffmpeg", "-version", "Stream Multiplexer & Transcoder"),
            ("ffprobe", "-version", "Stream Analyzer & Inspector"),
            ("deno", "--version", "Modern JS Runtime (YouTube Cipher)"),
            ("AtomicParsley", "-v", "Metadata & Artwork Tagger"),
        ];

        let mut results = Vec::new();
        for (name, flag, role) in tools {
            let path = Self::find_tool(name);
            let version = path.as_ref().and_then(|p| Self::get_tool_version(p, flag));
            let available = path.is_some();
            results.push(ToolInfo {
                name: name.to_string(),
                path,
                version,
                available,
                role: role.to_string(),
            });
        }
        results
    }

    /// Downloads the latest official yt-dlp binary if not present.
    pub async fn ensure_ytdlp() -> Result<PathBuf> {
        if let Some(existing) = Self::find_tool("yt-dlp") {
            return Ok(existing);
        }

        let bin_dir = Self::bin_dir();
        std::fs::create_dir_all(&bin_dir).context("Failed to create Bengal bin directory")?;

        let (url, filename) = if cfg!(target_os = "windows") {
            ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", "yt-dlp.exe")
        } else if cfg!(target_arch = "aarch64") {
            ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64", "yt-dlp")
        } else {
            ("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux", "yt-dlp")
        };

        let target_path = bin_dir.join(filename);
        tracing::info!("[Media] Downloading yt-dlp from {} to {}", url, target_path.display());

        let client = reqwest::Client::new();
        let bytes = client.get(url).send().await?.bytes().await?;
        std::fs::write(&target_path, &bytes)?;

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = std::fs::metadata(&target_path)?.permissions();
            perms.set_mode(0o755);
            std::fs::set_permissions(&target_path, perms)?;
        }

        tracing::info!("[Media] Successfully installed yt-dlp at {}", target_path.display());
        Ok(target_path)
    }
}
