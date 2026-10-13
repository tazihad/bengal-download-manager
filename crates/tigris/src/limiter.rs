use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;
use tokio::sync::Mutex;

/// Token bucket bandwidth throttler for global or per-download speed limits.
pub struct RateLimiter {
    bytes_per_sec: AtomicU64,
    state: Mutex<LimiterState>,
}

struct LimiterState {
    tokens: f64,
    last_update: Instant,
}

impl RateLimiter {
    pub fn new(bytes_per_sec: u64) -> Self {
        Self {
            bytes_per_sec: AtomicU64::new(bytes_per_sec),
            state: Mutex::new(LimiterState {
                tokens: bytes_per_sec as f64,
                last_update: Instant::now(),
            }),
        }
    }

    pub fn set_speed_limit(&self, bytes_per_sec: u64) {
        self.bytes_per_sec.store(bytes_per_sec, Ordering::Relaxed);
    }

    pub async fn acquire(&self, count: usize) {
        let limit = self.bytes_per_sec.load(Ordering::Relaxed);
        if limit == 0 {
            return; // No limit
        }

        let needed = count as f64;
        let mut state = self.state.lock().await;

        let now = Instant::now();
        let elapsed = now.duration_since(state.last_update).as_secs_f64();
        state.last_update = now;

        // Refill tokens
        state.tokens += elapsed * (limit as f64);
        if state.tokens > (limit as f64) * 2.0 {
            state.tokens = (limit as f64) * 2.0; // Max burst of 2 seconds
        }

        state.tokens -= needed;

        if state.tokens < 0.0 {
            // Must sleep to satisfy rate
            let sleep_secs = (-state.tokens) / (limit as f64);
            let sleep_dur = std::time::Duration::from_secs_f64(sleep_secs);
            drop(state); // Drop lock while sleeping
            tokio::time::sleep(sleep_dur).await;
        }
    }
}
