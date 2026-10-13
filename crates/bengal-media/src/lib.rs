pub mod dependencies;
pub mod pot;
pub mod extractor;
pub mod worker;

pub use dependencies::{MediaDependencies, ToolInfo};
pub use extractor::{
    ExtractorOptions, MediaExtractionResult, MediaExtractor, MediaFormat, PlaylistEntry,
    PlaylistInfo, SingleVideoInfo,
};
pub use pot::{
    check_pot_provider_status, get_deno_executable_path, get_js_runtime_args,
    get_pot_extractor_args, get_pot_plugin_args, get_youtube_player_client_args,
    is_pot_provider_available, DEFAULT_POT_PROVIDER_URL, DYNAMIC_YOUTUBE_CLIENTS,
};
pub use worker::{
    parse_eta_to_seconds, parse_size_str_to_bytes, MediaDownloadConfig, MediaDownloadProgress,
    MediaDownloadWorker,
};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pot_player_client_args() {
        let dynamic = get_youtube_player_client_args(Some("auto"));
        assert_eq!(dynamic.len(), 2);
        assert_eq!(dynamic[0], "--extractor-args");
        assert!(dynamic[1].contains("mweb,android,ios"));

        let custom = get_youtube_player_client_args(Some("android,ios"));
        assert_eq!(custom.len(), 2);
        assert_eq!(custom[1], "youtube:player_client=android,ios");

        let default_args = get_youtube_player_client_args(Some("default"));
        assert!(default_args.is_empty());
    }

    #[test]
    fn test_parse_size_bytes() {
        assert_eq!(parse_size_str_to_bytes("15.50MiB"), 15 * 1024 * 1024 + 524288);
        assert_eq!(parse_size_str_to_bytes("1.5GiB"), (1.5 * 1024.0 * 1024.0 * 1024.0) as u64);
        assert_eq!(parse_size_str_to_bytes("500KiB"), 500 * 1024);
        assert_eq!(parse_size_str_to_bytes("1024B"), 1024);
    }

    #[test]
    fn test_parse_eta_seconds() {
        assert_eq!(parse_eta_to_seconds("01:30"), Some(90));
        assert_eq!(parse_eta_to_seconds("01:02:03"), Some(3723));
        assert_eq!(parse_eta_to_seconds("invalid"), None);
    }

    #[test]
    fn test_netscape_cookies_generation() {
        let cookie_str = "SID=abc123xyz; HSID=def456uvw; _ga=tracking_ignore";
        let path = extractor::create_temp_netscape_cookies(cookie_str, "https://www.youtube.com/watch?v=test");
        assert!(path.is_some());
        let p = path.unwrap();
        assert!(p.exists());
        let content = std::fs::read_to_string(&p).unwrap();
        assert!(content.contains(".youtube.com"));
        assert!(content.contains("SID\tabc123xyz"));
        assert!(!content.contains("_ga")); // Filtered out ignore cookie
        let _ = std::fs::remove_file(p);
    }
}
