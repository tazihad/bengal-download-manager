pub mod crawler;

pub use crawler::{
    is_cloud_metadata_host, is_private_or_loopback_host, wildcard_to_regex, GrabberConfig,
    GrabberCrawler, GrabberEvent, GrabberFile, HTML_EXTENSIONS, MAX_PAGE_BYTES,
};

#[cfg(test)]
mod tests {
    use super::*;
    use url::Url;

    #[test]
    fn test_ssrf_cloud_metadata_detection() {
        assert!(is_cloud_metadata_host("169.254.169.254"));
        assert!(is_cloud_metadata_host("169.254.169.254:80"));
        assert!(is_cloud_metadata_host("instance-data"));
        assert!(is_cloud_metadata_host("metadata.google.internal"));
        assert!(!is_cloud_metadata_host("google.com"));
        assert!(!is_cloud_metadata_host("example.org"));
    }

    #[test]
    fn test_ssrf_private_host_detection() {
        assert!(is_private_or_loopback_host("localhost"));
        assert!(is_private_or_loopback_host("127.0.0.1"));
        assert!(is_private_or_loopback_host("127.0.0.1:8080"));
        assert!(is_private_or_loopback_host("192.168.1.100"));
        assert!(is_private_or_loopback_host("10.0.5.12"));
        assert!(is_private_or_loopback_host("::1"));
    }

    #[test]
    fn test_wildcard_regex_matching() {
        let rx = wildcard_to_regex("*.mp4").unwrap();
        assert!(rx.is_match("video.mp4"));
        assert!(rx.is_match("Movie.MP4"));
        assert!(!rx.is_match("audio.mp3"));

        let rx_name = wildcard_to_regex("track_??.flac").unwrap();
        assert!(rx_name.is_match("track_01.flac"));
        assert!(!rx_name.is_match("track_1.flac"));
    }

    #[test]
    fn test_link_extraction() {
        let base = Url::parse("https://example.com/media/").unwrap();
        let html = r##"
            <html>
                <body>
                    <a href="song.mp3">Listen</a>
                    <a href="/archive/pack.zip">Download ZIP</a>
                    <video src="clip.webm"></video>
                    <img src="https://cdn.example.com/banner.jpg" />
                    <a href="javascript:void(0)">Ignore me</a>
                    <a href="#section">Ignore hash</a>
                </body>
            </html>
        "##;
        let links = GrabberCrawler::extract_links(html, &base);
        let link_strs: Vec<String> = links.iter().map(|u| u.to_string()).collect();

        assert!(link_strs.contains(&"https://example.com/media/song.mp3".to_string()));
        assert!(link_strs.contains(&"https://example.com/archive/pack.zip".to_string()));
        assert!(link_strs.contains(&"https://example.com/media/clip.webm".to_string()));
        assert!(link_strs.contains(&"https://cdn.example.com/banner.jpg".to_string()));
        assert!(!link_strs.iter().any(|s| s.contains("javascript")));
        assert!(!link_strs.iter().any(|s| s.contains("#section")));
    }

    #[test]
    fn test_extract_filename() {
        let u1 = Url::parse("https://example.com/downloads/setup_v2.0.deb").unwrap();
        assert_eq!(GrabberCrawler::extract_filename(&u1, 1), "setup_v2.0.deb");

        let u2 = Url::parse("https://example.com/files/my%20song.flac").unwrap();
        assert_eq!(GrabberCrawler::extract_filename(&u2, 2), "my song.flac");

        let u3 = Url::parse("https://example.com/api/stream").unwrap();
        assert_eq!(GrabberCrawler::extract_filename(&u3, 3), "file_3");
    }
}
