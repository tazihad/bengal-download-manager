use eframe::egui;
use tigris::{ProbeResult, ProxyConfig, TigrisEngine};

#[derive(Default)]
pub struct FileInfoDialog {
    pub is_open: bool,
    pub url: String,
    pub is_probing: bool,
    pub probe_result: Option<ProbeResult>,
    pub error_message: Option<String>,
}

impl FileInfoDialog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(&mut self, url: &str) {
        self.url = url.to_string();
        self.is_open = true;
        self.is_probing = true;
        self.probe_result = None;
        self.error_message = None;

        let url_clone = url.to_string();
        // Probe asynchronously
        tokio::spawn(async move {
            let _ = TigrisEngine::probe(&url_clone, &ProxyConfig::Direct).await;
        });
    }

    pub fn close(&mut self) {
        self.is_open = false;
        self.probe_result = None;
        self.error_message = None;
    }

    pub fn render(&mut self, ctx: &egui::Context) {
        if !self.is_open {
            return;
        }

        let mut is_open = self.is_open;
        let mut close_clicked = false;

        egui::Window::new("ℹ Remote File Information")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(true)
            .default_width(450.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.label("Remote URL:");
                ui.monospace(&self.url);
                ui.add_space(8.0);

                if let Some(res) = &self.probe_result {
                    ui.group(|ui| {
                        ui.horizontal(|ui| {
                            ui.label("Suggested Filename:");
                            ui.strong(&res.suggested_filename);
                        });
                        ui.horizontal(|ui| {
                            ui.label("Content-Type:");
                            ui.monospace(&res.content_type);
                        });
                        ui.horizontal(|ui| {
                            ui.label("Total Size:");
                            let size_str = res.total_size.map(bengal_core::format_bytes).unwrap_or_else(|| "Unknown / Streaming".to_string());
                            ui.monospace(size_str);
                        });
                        ui.horizontal(|ui| {
                            ui.label("Resume & Range Support:");
                            if res.supports_ranges {
                                ui.colored_label(egui::Color32::from_rgb(0, 200, 0), "✔ Yes (Multi-Segment Acceleration Supported)");
                            } else {
                                ui.colored_label(egui::Color32::from_rgb(200, 150, 0), "⚠ No (Single Stream Only)");
                            }
                        });
                    });
                } else if let Some(err) = &self.error_message {
                    ui.colored_label(egui::Color32::RED, format!("Error probing URL: {}", err));
                } else {
                    ui.horizontal(|ui| {
                        ui.spinner();
                        ui.label("Probing remote server headers...");
                    });
                }

                ui.add_space(12.0);
                ui.separator();
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button("Close").clicked() {
                        close_clicked = true;
                    }
                });
            });

        if close_clicked {
            is_open = false;
        }
        self.is_open = is_open;
    }
}
