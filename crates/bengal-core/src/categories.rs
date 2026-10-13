use std::collections::HashMap;
use std::path::PathBuf;
use crate::paths::AppPaths;

use serde::{Deserialize, Serialize};

pub const CATEGORY_COMPRESSED: &str = "Compressed";
pub const CATEGORY_DOCUMENTS: &str = "Documents";
pub const CATEGORY_MUSIC: &str = "Music";
pub const CATEGORY_PROGRAMS: &str = "Programs";
pub const CATEGORY_VIDEO: &str = "Video";
pub const CATEGORY_GENERAL: &str = "General";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum FileCategory {
    Compressed,
    Documents,
    Music,
    Programs,
    Video,
    General,
}

impl FileCategory {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Compressed => CATEGORY_COMPRESSED,
            Self::Documents => CATEGORY_DOCUMENTS,
            Self::Music => CATEGORY_MUSIC,
            Self::Programs => CATEGORY_PROGRAMS,
            Self::Video => CATEGORY_VIDEO,
            Self::General => CATEGORY_GENERAL,
        }
    }

    pub fn from_filename(filename: &str) -> Self {
        match get_category_for_filename(filename) {
            CATEGORY_COMPRESSED => Self::Compressed,
            CATEGORY_DOCUMENTS => Self::Documents,
            CATEGORY_MUSIC => Self::Music,
            CATEGORY_PROGRAMS => Self::Programs,
            CATEGORY_VIDEO => Self::Video,
            _ => Self::General,
        }
    }
}

/// Classification mappings from file extensions to standard categories.
pub fn get_category_extensions() -> HashMap<&'static str, &'static [&'static str]> {
    let mut map = HashMap::new();
    map.insert(
        CATEGORY_COMPRESSED,
        &[".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".bz2", ".xz", ".tgz", ".zst", ".cab", ".lz4"][..],
    );
    map.insert(
        CATEGORY_DOCUMENTS,
        &[".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".rtf", ".odt", ".epub", ".md"][..],
    );
    map.insert(
        CATEGORY_MUSIC,
        &[".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus", ".aiff", ".alac"][..],
    );
    map.insert(
        CATEGORY_PROGRAMS,
        &[
            ".exe", ".msi", ".deb", ".rpm", ".apk", ".appimage", ".flatpak", ".snap",
            ".sh", ".bin", ".bat", ".cmd", ".run", ".dmg", ".pkg", ".jar", ".msu"
        ][..],
    );
    map.insert(
        CATEGORY_VIDEO,
        &[".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".3gp"][..],
    );
    map
}

/// Classifies a filename into its standard category based on file extension.
pub fn get_category_for_filename(filename: &str) -> &'static str {
    let lower = filename.trim().to_lowercase();
    for (cat, exts) in get_category_extensions() {
        for ext in exts {
            if lower.ends_with(ext) {
                return cat;
            }
        }
    }
    CATEGORY_GENERAL
}

/// Returns the standard default download subfolder for a given category.
pub fn get_category_dir(category: &str) -> PathBuf {
    let base = AppPaths::default_download_dir();
    match category {
        CATEGORY_COMPRESSED => base.join("Compressed"),
        CATEGORY_DOCUMENTS => base.join("Documents"),
        CATEGORY_MUSIC => base.join("Music"),
        CATEGORY_PROGRAMS => base.join("Programs"),
        CATEGORY_VIDEO => base.join("Video"),
        _ => base,
    }
}

/// Parses human-formatted sizes (e.g. '12.5 MB', '10.00 MiB', '500 KiB') into raw bytes.
pub fn parse_size_to_bytes(text: &str) -> Option<u64> {
    let s = text.trim().trim_start_matches('~').trim().to_uppercase();
    if s.is_empty() || s == "..." || s == "UNKNOWN" {
        return None;
    }

    let units: &[(&str, u64)] = &[
        ("TIB", 1024 * 1024 * 1024 * 1024),
        ("TB", 1000 * 1000 * 1000 * 1000),
        ("GIB", 1024 * 1024 * 1024),
        ("GB", 1000 * 1000 * 1000),
        ("MIB", 1024 * 1024),
        ("MB", 1000 * 1000),
        ("KIB", 1024),
        ("KB", 1000),
        ("B", 1),
    ];

    for &(suffix, mult) in units {
        if s.ends_with(suffix) {
            let num_str = s[..s.len() - suffix.len()].trim();
            if let Ok(num) = num_str.parse::<f64>() {
                return Some((num * mult as f64) as u64);
            }
        }
    }

    s.parse::<u64>().ok()
}

/// Parses duration strings (e.g. '01:23:45', '1 hr 20 min', '45s') into seconds.
pub fn parse_duration_to_seconds(text: &str) -> Option<u64> {
    let s = text.trim();
    if s.is_empty() || s == "..." || s == "--" || s == "Unknown" {
        return None;
    }

    if s.contains(':') {
        let parts: Vec<&str> = s.split(':').collect();
        if parts.len() == 3 {
            let h = parts[0].parse::<u64>().ok()?;
            let m = parts[1].parse::<u64>().ok()?;
            let sec = parts[2].parse::<u64>().ok()?;
            return Some(h * 3600 + m * 60 + sec);
        } else if parts.len() == 2 {
            let m = parts[0].parse::<u64>().ok()?;
            let sec = parts[1].parse::<u64>().ok()?;
            return Some(m * 60 + sec);
        }
    }

    let lower = s.to_lowercase();
    if let Some(sec_str) = lower.strip_suffix('s') {
        return sec_str.trim().parse::<u64>().ok();
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_categorization() {
        assert_eq!(get_category_for_filename("archive.tar.gz"), CATEGORY_COMPRESSED);
        assert_eq!(get_category_for_filename("document.pdf"), CATEGORY_DOCUMENTS);
        assert_eq!(get_category_for_filename("song.mp3"), CATEGORY_MUSIC);
        assert_eq!(get_category_for_filename("installer.deb"), CATEGORY_PROGRAMS);
        assert_eq!(get_category_for_filename("movie.mp4"), CATEGORY_VIDEO);
        assert_eq!(get_category_for_filename("unknown.xyz"), CATEGORY_GENERAL);
    }

    #[test]
    fn test_parse_size() {
        assert_eq!(parse_size_to_bytes("10 MiB"), Some(10 * 1024 * 1024));
        assert_eq!(parse_size_to_bytes("500 KiB"), Some(500 * 1024));
        assert_eq!(parse_size_to_bytes("1.5 GiB"), Some((1.5 * 1024.0 * 1024.0 * 1024.0) as u64));
    }
}
