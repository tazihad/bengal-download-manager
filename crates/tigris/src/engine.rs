use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use anyhow::{Context, Result};
use reqwest::header::{CONTENT_DISPOSITION, CONTENT_LENGTH};
use crate::alloc::preallocate_file;
use crate::chunk::{SegmentInfo, SegmentWorker};
use crate::limiter::RateLimiter;
use crate::proxy::ProxyConfig;

#[derive(Debug, Clone)]
pub struct ProbeResult {
    pub total_size: Option<u64>,
    pub supports_ranges: bool,
    pub suggested_filename: String,
    pub content_type: String,
}

#[derive(Debug, Clone)]
pub struct TigrisTask {
    pub url: String,
    pub target_path: PathBuf,
    pub num_connections: usize,
    pub proxy: ProxyConfig,
    pub speed_limit: u64,
}

#[derive(Debug, Clone)]
pub struct ProgressUpdate {
    pub total_bytes: Option<u64>,
    pub downloaded_bytes: u64,
    pub speed_bytes_sec: u64,
    pub eta_seconds: u64,
    pub progress_percent: f64,
}

pub struct TigrisHandle {
    pub cancel_flag: Arc<AtomicBool>,
    pub downloaded_counter: Arc<AtomicU64>,
    pub total_size: Option<u64>,
}

impl TigrisHandle {
    pub fn cancel(&self) {
        self.cancel_flag.store(true, Ordering::Relaxed);
    }
}

pub struct TigrisEngine;

impl TigrisEngine {
    /// Probes a remote URL to inspect total file size, range support, and filename.
    pub async fn probe(url: &str, proxy: &ProxyConfig) -> Result<ProbeResult> {
        let client = proxy.build_client(15)?;

        let resp = match client.head(url).send().await {
            Ok(r) if r.status().is_success() => r,
            _ => {
                // Fallback to GET with Range: bytes=0-0 if HEAD is disallowed
                client
                    .get(url)
                    .header("Range", "bytes=0-0")
                    .send()
                    .await
                    .context("Failed to probe remote URL via GET")?
            }
        };

        let headers = resp.headers();

        // 1. Detect size
        let total_size = if let Some(val) = headers.get(CONTENT_LENGTH) {
            val.to_str().ok().and_then(|s| s.parse::<u64>().ok())
        } else {
            None
        };

        // 2. Detect range support
        let supports_ranges = headers
            .get("Accept-Ranges")
            .and_then(|v| v.to_str().ok())
            .map(|s| s.eq_ignore_ascii_case("bytes"))
            .unwrap_or(false)
            || resp.status() == reqwest::StatusCode::PARTIAL_CONTENT;

        // 3. Extract filename from Content-Disposition or URL path
        let mut suggested_filename = String::new();
        if let Some(cd) = headers.get(CONTENT_DISPOSITION) {
            if let Ok(cd_str) = cd.to_str() {
                if let Some(pos) = cd_str.find("filename=") {
                    let mut name = &cd_str[pos + 9..];
                    name = name.trim_matches(|c| c == '"' || c == '\'');
                    if let Some(end) = name.find(';') {
                        name = &name[..end];
                    }
                    suggested_filename = name.trim().to_string();
                }
            }
        }

        if suggested_filename.is_empty() {
            if let Ok(parsed_url) = url::Url::parse(url) {
                if let Some(segments) = parsed_url.path_segments() {
                    if let Some(last) = segments.last() {
                        let unquoted = percent_encoding::percent_decode_str(last).decode_utf8_lossy();
                        if !unquoted.is_empty() && !unquoted.ends_with('/') {
                            suggested_filename = unquoted.to_string();
                        }
                    }
                }
            }
        }

        if suggested_filename.is_empty() {
            suggested_filename = "download.bin".to_string();
        }

        let content_type = headers
            .get("Content-Type")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("application/octet-stream")
            .to_string();

        Ok(ProbeResult {
            total_size,
            supports_ranges,
            suggested_filename,
            content_type,
        })
    }

    /// Executes a download with parallel segment workers and a progress callback.
    pub async fn download<F>(
        task: TigrisTask,
        mut on_progress: F,
    ) -> Result<()>
    where
        F: FnMut(ProgressUpdate) + Send + 'static,
    {
        let probe = Self::probe(&task.url, &task.proxy).await?;
        let client = task.proxy.build_client(30)?;

        let total_size = probe.total_size;
        let downloaded_counter = Arc::new(AtomicU64::new(0));
        let cancel_flag = Arc::new(AtomicBool::new(false));

        let rate_limiter = if task.speed_limit > 0 {
            Some(Arc::new(RateLimiter::new(task.speed_limit)))
        } else {
            None
        };

        // Determine segment count
        let num_connections = if probe.supports_ranges && total_size.unwrap_or(0) > 1024 * 1024 {
            task.num_connections.clamp(1, 32)
        } else {
            1
        };

        // Pre-allocate target file if size is known
        if let Some(size) = total_size {
            preallocate_file(&task.target_path, size)
                .context("Failed to pre-allocate target file")?;
        }

        // Divide file into byte segments
        let mut workers = Vec::new();

        if let Some(size) = total_size {
            let chunk_size = size / (num_connections as u64);
            for i in 0..num_connections {
                let start_byte = (i as u64) * chunk_size;
                let end_byte = if i == num_connections - 1 {
                    size - 1
                } else {
                    ((i as u64) + 1) * chunk_size - 1
                };

                let worker = SegmentWorker {
                    info: SegmentInfo {
                        index: i,
                        start_byte,
                        end_byte,
                        initial_downloaded: 0,
                    },
                    url: task.url.clone(),
                    client: client.clone(),
                    file_path: task.target_path.clone(),
                    downloaded_counter: Arc::clone(&downloaded_counter),
                    rate_limiter: rate_limiter.clone(),
                    cancel_flag: Arc::clone(&cancel_flag),
                };
                workers.push(worker);
            }
        } else {
            // Unknown size: single stream worker
            let worker = SegmentWorker {
                info: SegmentInfo {
                    index: 0,
                    start_byte: 0,
                    end_byte: u64::MAX - 1,
                    initial_downloaded: 0,
                },
                url: task.url.clone(),
                client: client.clone(),
                file_path: task.target_path.clone(),
                downloaded_counter: Arc::clone(&downloaded_counter),
                rate_limiter: rate_limiter.clone(),
                cancel_flag: Arc::clone(&cancel_flag),
            };
            workers.push(worker);
        }

        // Spawn progress reporting task
        let progress_cancel = Arc::clone(&cancel_flag);
        let progress_counter = Arc::clone(&downloaded_counter);
        let progress_handle = tokio::spawn(async move {
            let mut last_bytes = 0u64;
            let mut last_time = Instant::now();

            while !progress_cancel.load(Ordering::Relaxed) {
                tokio::time::sleep(Duration::from_millis(250)).await;

                let current_bytes = progress_counter.load(Ordering::Relaxed);
                let now = Instant::now();
                let elapsed_secs = now.duration_since(last_time).as_secs_f64();

                let speed = if elapsed_secs > 0.0 {
                    ((current_bytes.saturating_sub(last_bytes) as f64) / elapsed_secs) as u64
                } else {
                    0
                };

                last_bytes = current_bytes;
                last_time = now;

                let (eta, percent) = if let Some(total) = total_size {
                    let rem = total.saturating_sub(current_bytes);
                    let eta_secs = if speed > 0 { rem / speed } else { 0 };
                    let pct = ((current_bytes as f64) / (total as f64)) * 100.0;
                    (eta_secs, pct.min(100.0))
                } else {
                    (0, 0.0)
                };

                on_progress(ProgressUpdate {
                    total_bytes: total_size,
                    downloaded_bytes: current_bytes,
                    speed_bytes_sec: speed,
                    eta_seconds: eta,
                    progress_percent: percent,
                });

                if let Some(total) = total_size {
                    if current_bytes >= total {
                        break;
                    }
                }
            }
        });

        // Run segment workers concurrently
        let mut tasks = Vec::new();
        for worker in workers {
            tasks.push(tokio::spawn(async move { worker.run().await }));
        }

        // Wait for all workers to finish
        for task in tasks {
            let res = task.await.context("Worker task panicked")?;
            res.context("Worker chunk error")?;
        }

        cancel_flag.store(true, Ordering::Relaxed);
        let _ = progress_handle.await;

        Ok(())
    }
}
