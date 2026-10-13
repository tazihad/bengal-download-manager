use serde::{Deserialize, Serialize};
use crate::types::format_bytes;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataUsageEntry {
    pub date: String,
    pub bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct UsageSummary {
    pub today_bytes: u64,
    pub week_bytes: u64,
    pub month_bytes: u64,
    pub total_bytes: u64,
    pub monthly_quota: Option<u64>,
}

impl UsageSummary {
    pub fn is_quota_exceeded(&self) -> bool {
        if let Some(quota) = self.monthly_quota {
            self.month_bytes >= quota
        } else {
            false
        }
    }

    pub fn quota_percentage(&self) -> f64 {
        if let Some(quota) = self.monthly_quota {
            if quota > 0 {
                return (self.month_bytes as f64 / quota as f64) * 100.0;
            }
        }
        0.0
    }

    pub fn formatted_today(&self) -> String {
        format_bytes(self.today_bytes)
    }

    pub fn formatted_week(&self) -> String {
        format_bytes(self.week_bytes)
    }

    pub fn formatted_month(&self) -> String {
        format_bytes(self.month_bytes)
    }

    pub fn formatted_total(&self) -> String {
        format_bytes(self.total_bytes)
    }
}
