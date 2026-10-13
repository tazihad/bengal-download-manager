use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use anyhow::{Context, Result};
use futures_util::StreamExt;
use tokio::fs::OpenOptions;
use tokio::io::{AsyncSeekExt, AsyncWriteExt, SeekFrom};
use crate::limiter::RateLimiter;

#[derive(Debug, Clone)]
pub struct SegmentInfo {
    pub index: usize,
    pub start_byte: u64,
    pub end_byte: u64,
    pub initial_downloaded: u64,
}

pub struct SegmentWorker {
    pub info: SegmentInfo,
    pub url: String,
    pub client: reqwest::Client,
    pub file_path: PathBuf,
    pub downloaded_counter: Arc<AtomicU64>,
    pub rate_limiter: Option<Arc<RateLimiter>>,
    pub cancel_flag: Arc<AtomicBool>,
}

impl SegmentWorker {
    pub async fn run(self) -> Result<()> {
        let resume_offset = self.info.start_byte + self.info.initial_downloaded;
        if resume_offset > self.info.end_byte {
            return Ok(()); // Chunk already complete
        }

        let range_header = format!("bytes={}-{}", resume_offset, self.info.end_byte);
        let response = self
            .client
            .get(&self.url)
            .header("Range", &range_header)
            .send()
            .await
            .context("Segment HTTP request failed")?
            .error_for_status()
            .context("Server returned error status for chunk range")?;

        let mut file = OpenOptions::new()
            .write(true)
            .open(&self.file_path)
            .await
            .context("Failed to open pre-allocated file for chunk writing")?;

        file.seek(SeekFrom::Start(resume_offset))
            .await
            .context("Failed to seek file to chunk offset")?;

        let mut stream = response.bytes_stream();

        while let Some(chunk_result) = stream.next().await {
            if self.cancel_flag.load(Ordering::Relaxed) {
                break;
            }

            let chunk = chunk_result.context("Failed to read chunk from stream")?;
            let len = chunk.len();

            if let Some(limiter) = &self.rate_limiter {
                limiter.acquire(len).await;
            }

            file.write_all(&chunk)
                .await
                .context("Failed to write chunk data to disk")?;

            self.downloaded_counter.fetch_add(len as u64, Ordering::Relaxed);
        }

        file.flush().await.context("Failed to flush chunk data")?;
        Ok(())
    }
}
