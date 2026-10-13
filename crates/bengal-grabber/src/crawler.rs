use std::collections::{HashSet, VecDeque};
use std::net::{IpAddr, ToSocketAddrs};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use anyhow::{bail, Context, Result};
use regex::Regex;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;
use url::Url;

use bengal_core::categories::FileCategory;

pub const MAX_PAGE_BYTES: usize = 16 * 1024 * 1024; // 16 MiB
pub const HTML_EXTENSIONS: &[&str] = &[
    "", "html", "htm", "php", "asp", "aspx", "jsp", "cgi", "shtml", "pl",
];

/// Checks if host is an AWS, GCP, Azure, or OpenStack cloud instance metadata address.
pub fn is_cloud_metadata_host(host: &str) -> bool {
    let clean = host.split(':').next().unwrap_or("").trim().to_lowercase();
    if clean == "169.254.169.254" || clean == "instance-data" || clean == "metadata.google.internal" {
        return true;
    }
    if let Ok(ip) = clean.parse::<IpAddr>() {
        match ip {
            IpAddr::V4(ipv4) => {
                let octets = ipv4.octets();
                octets[0] == 169 && octets[1] == 254 // Link-local / cloud metadata
            }
            IpAddr::V6(ipv6) => ipv6.is_unicast_link_local(),
        }
    } else {
        false
    }
}

/// SSRF Gate: Checks if host is loopback, link-local, RFC-1918, or cloud metadata.
pub fn is_private_or_loopback_host(host: &str) -> bool {
    let clean = host.split(':').next().unwrap_or("").trim().to_lowercase();
    if clean.is_empty() || clean == "localhost" || clean == "127.0.0.1" || clean == "::1" || clean == "0.0.0.0" {
        return true;
    }

    if let Ok(ip) = clean.parse::<IpAddr>() {
        return is_ip_private_or_loopback(ip);
    }

    // DNS lookup verification
    let socket_str = format!("{}:80", clean);
    if let Ok(addrs) = socket_str.to_socket_addrs() {
        for socket_addr in addrs {
            if is_ip_private_or_loopback(socket_addr.ip()) {
                return true;
            }
        }
    }

    false
}

fn is_ip_private_or_loopback(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ipv4) => {
            let o = ipv4.octets();
            ipv4.is_loopback()
                || ipv4.is_unspecified()
                || (o[0] == 10)                                      // 10.0.0.0/8
                || (o[0] == 172 && (16..=31).contains(&o[1]))        // 172.16.0.0/12
                || (o[0] == 192 && o[1] == 168)                      // 192.168.0.0/16
                || (o[0] == 169 && o[1] == 254)                      // 169.254.0.0/16 (link local)
        }
        IpAddr::V6(ipv6) => {
            ipv6.is_loopback()
                || ipv6.is_unspecified()
                || ipv6.is_unicast_link_local()
        }
    }
}

/// Converts a wildcard pattern (e.g. `*.jpg`, `track_??.mp3`) into a compiled regex.
pub fn wildcard_to_regex(pattern: &str) -> Result<Regex> {
    let p = pattern.trim();
    if p.is_empty() || p == "*.*" || p == "*" {
        return Regex::new("^.*$").context("Failed to compile wildcard regex");
    }

    let mut escaped = String::new();
    escaped.push('^');
    for ch in p.chars() {
        match ch {
            '*' => escaped.push_str(".*"),
            '?' => escaped.push('.'),
            '.' | '+' | '^' | '$' | '(' | ')' | '[' | ']' | '{' | '}' | '|' | '\\' => {
                escaped.push('\\');
                escaped.push(ch);
            }
            _ => escaped.push(ch),
        }
    }
    escaped.push('$');

    Regex::new(&format!("(?i){}", escaped)).context("Failed to compile wildcard regex")
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrabberConfig {
    pub start_url: String,
    pub explore_depth: usize,
    pub stay_same_domain: bool,
    pub stay_same_path: bool,
    pub dont_explore_parent_dirs: bool,
    pub hide_duplicates: bool,
    pub allow_private_hosts: bool,
    pub file_include_patterns: Vec<String>,
    pub file_exclude_patterns: Vec<String>,
    pub min_size_bytes: i64,
    pub max_size_bytes: i64,
    pub user_agent: String,
}

impl Default for GrabberConfig {
    fn default() -> Self {
        Self {
            start_url: String::new(),
            explore_depth: 1,
            stay_same_domain: true,
            stay_same_path: false,
            dont_explore_parent_dirs: true,
            hide_duplicates: true,
            allow_private_hosts: true,
            file_include_patterns: vec!["*.*".to_string()],
            file_exclude_patterns: Vec::new(),
            min_size_bytes: 0,
            max_size_bytes: 0,
            user_agent: "Mozilla/5.0 (compatible; BengalGrabber/1.0)".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrabberFile {
    pub url: String,
    pub filename: String,
    pub source_page: String,
    pub size: i64,
    pub extension: String,
    pub category: FileCategory,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GrabberEvent {
    Progress(String),
    FileFound(GrabberFile),
    MetadataUpdated { url: String, size_bytes: i64 },
    Finished { total_files: usize, pages_crawled: usize },
    Failed(String),
}

pub struct GrabberCrawler {
    config: GrabberConfig,
    cancel_flag: Arc<AtomicBool>,
}

impl GrabberCrawler {
    pub fn new(config: GrabberConfig) -> (Self, Arc<AtomicBool>) {
        let cancel_flag = Arc::new(AtomicBool::new(false));
        (
            Self {
                config,
                cancel_flag: Arc::clone(&cancel_flag),
            },
            cancel_flag,
        )
    }

    /// Extracts URLs from an HTML document string.
    pub fn extract_links(html: &str, base_url: &Url) -> Vec<Url> {
        let mut links = Vec::new();
        let re_link = Regex::new(r#"(?i)<(?:a|area|video|audio|source|iframe|embed|img)\b[^>]*(?:href|src|data-src|data-original)\s*=\s*["']([^"'\s>]+)["']"#).unwrap();

        for cap in re_link.captures_iter(html) {
            if let Some(m) = cap.get(1) {
                let raw = m.as_str().trim();
                if raw.is_empty()
                    || raw.starts_with("javascript:")
                    || raw.starts_with("mailto:")
                    || raw.starts_with("tel:")
                    || raw.starts_with('#')
                    || raw.contains("/_h5ai/")
                {
                    continue;
                }

                if let Ok(resolved) = base_url.join(raw) {
                    if resolved.scheme() == "http" || resolved.scheme() == "https" {
                        links.push(resolved);
                    }
                }
            }
        }

        links
    }

    pub fn is_html_url(url: &Url) -> bool {
        let path = url.path().to_lowercase();
        if path.is_empty() || path.ends_with('/') {
            return true;
        }

        if let Some(ext) = path.split('.').last() {
            HTML_EXTENSIONS.contains(&ext)
        } else {
            true
        }
    }

    pub fn extract_filename(url: &Url, counter: usize) -> String {
        let path = url.path().trim_end_matches('/');
        let base = path.split('/').last().unwrap_or("");
        let decoded = percent_encoding::percent_decode_str(base)
            .decode_utf8_lossy()
            .to_string();

        if decoded.is_empty() || !decoded.contains('.') {
            format!("file_{}", counter)
        } else {
            decoded
        }
    }

    fn is_safe_host(&self, host: &str) -> bool {
        if is_cloud_metadata_host(host) {
            return false;
        }
        if !self.config.allow_private_hosts && is_private_or_loopback_host(host) {
            return false;
        }
        true
    }

    /// Executes the crawler asynchronously, streaming events to `event_tx`.
    pub async fn run(self, event_tx: mpsc::Sender<GrabberEvent>) -> Result<Vec<GrabberFile>> {
        let raw_start = self.config.start_url.trim();
        if raw_start.is_empty() {
            let msg = "Start URL cannot be empty".to_string();
            let _ = event_tx.send(GrabberEvent::Failed(msg.clone())).await;
            bail!(msg);
        }

        let start_url = match Url::parse(raw_start) {
            Ok(u) => u,
            Err(_) => {
                let formatted = format!("https://{}", raw_start);
                Url::parse(&formatted).context("Failed to parse start URL")?
            }
        };

        let root_domain = start_url.host_str().unwrap_or("").to_lowercase();
        if !self.is_safe_host(&root_domain) {
            let msg = "Start URL is blocked by security policy".to_string();
            let _ = event_tx.send(GrabberEvent::Failed(msg.clone())).await;
            bail!(msg);
        }

        let start_path_prefix = {
            let path = start_url.path();
            if path.ends_with('/') {
                path.to_string()
            } else if let Some(last_slash) = path.rfind('/') {
                path[..=last_slash].to_string()
            } else {
                "/".to_string()
            }
        };

        let mut include_regexes = Vec::new();
        for p in &self.config.file_include_patterns {
            if let Ok(rx) = wildcard_to_regex(p) {
                include_regexes.push(rx);
            }
        }

        let mut exclude_regexes = Vec::new();
        for p in &self.config.file_exclude_patterns {
            if let Ok(rx) = wildcard_to_regex(p) {
                exclude_regexes.push(rx);
            }
        }

        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(10))
            .user_agent(&self.config.user_agent)
            .redirect(reqwest::redirect::Policy::limited(5))
            .build()
            .context("Failed to initialize crawler HTTP client")?;

        let mut queue = VecDeque::new();
        queue.push_back((start_url.clone(), 0usize, "".to_string()));

        let mut seen_pages: HashSet<String> = HashSet::new();
        let mut seen_result_keys: HashSet<String> = HashSet::new();
        let mut discovered_files: Vec<GrabberFile> = Vec::new();
        let mut pages_crawled = 0usize;

        while let Some((curr_url, depth, _source_page)) = queue.pop_front() {
            if self.cancel_flag.load(Ordering::Relaxed) {
                let _ = event_tx.send(GrabberEvent::Progress("Crawl cancelled".to_string())).await;
                break;
            }

            let mut norm_url = curr_url.clone();
            norm_url.set_fragment(None);
            let norm_str = norm_url.to_string();

            if !seen_pages.insert(norm_str) {
                continue;
            }

            let progress_msg = format!("Exploring {} (depth {}/{})...", curr_url, depth, self.config.explore_depth);
            let _ = event_tx.send(GrabberEvent::Progress(progress_msg)).await;

            // Fetch page
            let resp = match client.get(curr_url.as_str()).send().await {
                Ok(r) => r,
                Err(e) => {
                    tracing::debug!("[Grabber] Error fetching {}: {}", curr_url, e);
                    continue;
                }
            };

            let final_url = resp.url().clone();
            let content_type = resp.headers()
                .get(reqwest::header::CONTENT_TYPE)
                .and_then(|h| h.to_str().ok())
                .unwrap_or("")
                .to_lowercase();

            if !content_type.contains("text") && !content_type.contains("html") && !content_type.contains("xml") {
                continue;
            }

            let body_bytes = match resp.bytes().await {
                Ok(b) => b,
                Err(_) => continue,
            };

            if body_bytes.len() > MAX_PAGE_BYTES {
                continue;
            }

            pages_crawled += 1;
            let html_text = String::from_utf8_lossy(&body_bytes);
            let links = Self::extract_links(&html_text, &final_url);

            for link in links {
                if self.cancel_flag.load(Ordering::Relaxed) {
                    break;
                }

                let link_host = link.host_str().unwrap_or("").to_lowercase();

                // Domain check
                if self.config.stay_same_domain && link_host != root_domain && !link_host.ends_with(&format!(".{}", root_domain)) {
                    continue;
                }

                // Path & Parent Dir check
                let link_path = link.path();
                if self.config.dont_explore_parent_dirs && !link_path.starts_with(&start_path_prefix) {
                    continue;
                }
                if self.config.stay_same_path && !link_path.starts_with(&start_path_prefix) {
                    continue;
                }

                // SSRF check
                if !self.is_safe_host(&link_host) {
                    continue;
                }

                if Self::is_html_url(&link) {
                    if depth + 1 <= self.config.explore_depth {
                        let mut next_norm = link.clone();
                        next_norm.set_fragment(None);
                        if !seen_pages.contains(&next_norm.to_string()) {
                            queue.push_back((link, depth + 1, final_url.to_string()));
                        }
                    }
                } else {
                    let filename = Self::extract_filename(&link, discovered_files.len() + 1);
                    let ext = filename.split('.').last().unwrap_or("").to_lowercase();
                    let full_url_str = link.to_string();

                    // Pattern matching
                    let passes_exclude = !exclude_regexes.iter().any(|rx| rx.is_match(&filename) || rx.is_match(&full_url_str));
                    if !passes_exclude {
                        continue;
                    }

                    let passes_include = include_regexes.is_empty() || include_regexes.iter().any(|rx| rx.is_match(&filename) || rx.is_match(&full_url_str));
                    if !passes_include {
                        continue;
                    }

                    let dup_key = if self.config.hide_duplicates {
                        filename.to_lowercase()
                    } else {
                        full_url_str.clone()
                    };

                    if !seen_result_keys.insert(dup_key) {
                        continue;
                    }

                    let category = FileCategory::from_filename(&filename);
                    let grabber_file = GrabberFile {
                        url: full_url_str.clone(),
                        filename: filename.clone(),
                        source_page: final_url.to_string(),
                        size: -1,
                        extension: ext,
                        category,
                    };

                    discovered_files.push(grabber_file.clone());
                    let _ = event_tx.send(GrabberEvent::FileFound(grabber_file)).await;

                    // Asynchronously probe file size via HEAD
                    let client_probe = client.clone();
                    let tx_probe = event_tx.clone();
                    let min_size = self.config.min_size_bytes;
                    let max_size = self.config.max_size_bytes;

                    tokio::spawn(async move {
                        if let Ok(head_resp) = client_probe.head(&full_url_str).send().await {
                            if let Some(cl) = head_resp.headers().get(reqwest::header::CONTENT_LENGTH) {
                                if let Ok(cl_str) = cl.to_str() {
                                    if let Ok(size_bytes) = cl_str.parse::<i64>() {
                                        if min_size > 0 && size_bytes < min_size {
                                            return;
                                        }
                                        if max_size > 0 && size_bytes > max_size {
                                            return;
                                        }
                                        let _ = tx_probe.send(GrabberEvent::MetadataUpdated {
                                            url: full_url_str,
                                            size_bytes,
                                        }).await;
                                    }
                                }
                            }
                        }
                    });
                }
            }
        }

        let _ = event_tx.send(GrabberEvent::Finished {
            total_files: discovered_files.len(),
            pages_crawled,
        }).await;

        Ok(discovered_files)
    }
}
