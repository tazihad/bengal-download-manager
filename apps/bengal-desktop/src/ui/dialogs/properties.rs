use std::path::PathBuf;
use eframe::egui;
use bengal_core::DownloadRecord;

#[derive(Default)]
pub struct PropertiesDialog {
    pub is_open: bool,
    pub record: Option<DownloadRecord>,
    pub sha256_hash: Option<String>,
}

impl PropertiesDialog {
    pub fn open(&mut self, rec: DownloadRecord) {
        self.is_open = true;
        self.record = Some(rec);
        self.sha256_hash = None;
    }

    pub fn close(&mut self) {
        self.is_open = false;
        self.record = None;
        self.sha256_hash = None;
    }

    pub fn render(&mut self, ctx: &egui::Context) {
        if !self.is_open {
            return;
        }

        let mut is_open = self.is_open;
        let mut compute_hash = false;

        let rec = match &self.record {
            Some(r) => r.clone(),
            None => {
                self.is_open = false;
                return;
            }
        };

        let path_buf = PathBuf::from(&rec.path);

        let mut close_clicked = false;

        egui::Window::new(format!("ℹ Properties: {}", rec.filename))
            .open(&mut is_open)
            .collapsible(false)
            .resizable(true)
            .default_width(500.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.add_space(4.0);

                ui.horizontal(|ui| {
                    ui.label("File Name:");
                    ui.strong(&rec.filename);
                });

                ui.add_space(4.0);
                ui.horizontal(|ui| {
                    ui.label("Status:");
                    ui.label(&rec.status);
                });

                ui.add_space(4.0);
                ui.horizontal(|ui| {
                    ui.label("Size:");
                    ui.monospace(&rec.size);
                });

                ui.add_space(4.0);
                ui.horizontal(|ui| {
                    ui.label("Local Path:");
                    ui.monospace(&rec.path);
                });

                ui.add_space(4.0);
                ui.label("Download URL:");
                let mut url_disp = rec.url.clone();
                ui.text_edit_multiline(&mut url_disp);

                ui.add_space(4.0);
                ui.label(format!("Category: {}", if !rec.category.is_empty() { &rec.category } else { "General" }));

                ui.add_space(8.0);
                ui.separator();
                ui.add_space(4.0);

                if let Some(hash) = &self.sha256_hash {
                    ui.horizontal(|ui| {
                        ui.label("SHA-256:");
                        ui.monospace(hash);
                    });
                } else if path_buf.exists() && ui.button("Calculate SHA-256 Checksum").clicked() {
                    compute_hash = true;
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
        if compute_hash {
            if let Ok(bytes) = std::fs::read(&path_buf) {
                let digest = ring::digest::digest(&ring::digest::SHA256, &bytes);
                let hex_str: String = digest.as_ref().iter().map(|b| format!("{:02x}", b)).collect();
                self.sha256_hash = Some(hex_str);
            }
        }
    }
}
