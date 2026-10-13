use std::path::PathBuf;
use eframe::egui;

#[derive(Debug, Clone)]
pub struct AddDownloadRequest {
    pub url: String,
    pub filename: String,
    pub save_dir: PathBuf,
    pub start_now: bool,
    pub max_segments: usize,
    pub speed_limit_bps: u64,
    pub referrer: Option<String>,
    pub user_agent: Option<String>,
    pub cookies: Option<String>,
    pub proxy: Option<String>,
}

pub struct AddDownloadDialog {
    pub is_open: bool,
    pub url: String,
    pub filename: String,
    pub save_dir: PathBuf,
    pub start_now: bool,
    pub show_advanced: bool,
    pub max_segments: usize,
    pub speed_limit_kb: u64,
    pub referrer: String,
    pub user_agent: String,
    pub cookies: String,
    pub proxy: String,
}

impl Default for AddDownloadDialog {
    fn default() -> Self {
        Self {
            is_open: false,
            url: String::new(),
            filename: String::new(),
            save_dir: bengal_core::AppPaths::default_download_dir(),
            start_now: true,
            show_advanced: false,
            max_segments: 8,
            speed_limit_kb: 0,
            referrer: String::new(),
            user_agent: String::new(),
            cookies: String::new(),
            proxy: String::new(),
        }
    }
}

impl AddDownloadDialog {
    pub fn open(&mut self, prefill_url: Option<&str>) {
        self.is_open = true;
        if let Some(u) = prefill_url {
            self.url = u.to_string();
            self.update_filename_from_url();
        }
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    fn update_filename_from_url(&mut self) {
        if let Ok(parsed) = url::Url::parse(&self.url) {
            let path = parsed.path().trim_end_matches('/');
            if let Some(base) = path.split('/').next_back() {
                if let Ok(decoded) = percent_encoding::percent_decode_str(base).decode_utf8() {
                    if !decoded.is_empty() && decoded.contains('.') {
                        self.filename = decoded.to_string();
                    }
                }
            }
        }
    }

    pub fn render(&mut self, ctx: &egui::Context) -> Option<AddDownloadRequest> {
        if !self.is_open {
            return None;
        }

        let mut submitted_request = None;
        let mut is_open = self.is_open;

        egui::Window::new("➕ Add New Download")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(false)
            .default_width(520.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.add_space(4.0);

                // URL row
                ui.horizontal(|ui| {
                    ui.label("Download URL:");
                    let resp = ui.text_edit_singleline(&mut self.url);
                    if resp.changed() {
                        self.update_filename_from_url();
                    }
                });

                ui.add_space(6.0);

                // File name row
                ui.horizontal(|ui| {
                    ui.label("File Name:");
                    ui.text_edit_singleline(&mut self.filename);
                });

                ui.add_space(6.0);

                // Save directory row
                ui.horizontal(|ui| {
                    ui.label("Save Directory:");
                    let mut dir_str = self.save_dir.to_string_lossy().to_string();
                    ui.text_edit_singleline(&mut dir_str);
                    if ui.button("Browse...").clicked() {
                        if let Some(chosen) = rfd::FileDialog::new().pick_folder() {
                            self.save_dir = chosen;
                        }
                    }
                });

                ui.add_space(6.0);

                // Category preview
                let cat = if !self.filename.is_empty() {
                    bengal_core::get_category_for_filename(&self.filename)
                } else {
                    bengal_core::CATEGORY_GENERAL
                };
                ui.label(format!("Auto-detected Category: {}", cat));

                ui.add_space(8.0);
                ui.checkbox(&mut self.start_now, "Start download immediately");

                ui.add_space(8.0);
                ui.collapsing("⚙ Advanced Connection Options", |ui| {
                    ui.horizontal(|ui| {
                        ui.label("Connections / Segments:");
                        ui.add(egui::Slider::new(&mut self.max_segments, 1..=32));
                    });

                    ui.horizontal(|ui| {
                        ui.label("Speed Limit (KB/s):");
                        ui.add(egui::DragValue::new(&mut self.speed_limit_kb).speed(100));
                        if self.speed_limit_kb == 0 {
                            ui.label("(Unlimited)");
                        }
                    });

                    ui.horizontal(|ui| {
                        ui.label("Referrer URL:");
                        ui.text_edit_singleline(&mut self.referrer);
                    });

                    ui.horizontal(|ui| {
                        ui.label("User Agent:");
                        ui.text_edit_singleline(&mut self.user_agent);
                    });

                    ui.horizontal(|ui| {
                        ui.label("Cookies:");
                        ui.text_edit_singleline(&mut self.cookies);
                    });

                    ui.horizontal(|ui| {
                        ui.label("Proxy URL:");
                        ui.text_edit_singleline(&mut self.proxy);
                    });
                });

                ui.add_space(12.0);
                ui.separator();
                ui.add_space(6.0);

                // Actions row
                ui.horizontal(|ui| {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Cancel").clicked() {
                            self.is_open = false;
                        }

                        let can_submit = !self.url.trim().is_empty();
                        if ui.add_enabled(can_submit, egui::Button::new("Download")).clicked() {
                            let name = if self.filename.trim().is_empty() {
                                "download_file".to_string()
                            } else {
                                self.filename.clone()
                            };

                            submitted_request = Some(AddDownloadRequest {
                                url: self.url.trim().to_string(),
                                filename: name,
                                save_dir: self.save_dir.clone(),
                                start_now: self.start_now,
                                max_segments: self.max_segments,
                                speed_limit_bps: self.speed_limit_kb * 1024,
                                referrer: if self.referrer.is_empty() { None } else { Some(self.referrer.clone()) },
                                user_agent: if self.user_agent.is_empty() { None } else { Some(self.user_agent.clone()) },
                                cookies: if self.cookies.is_empty() { None } else { Some(self.cookies.clone()) },
                                proxy: if self.proxy.is_empty() { None } else { Some(self.proxy.clone()) },
                            });

                            self.is_open = false;
                        }
                    });
                });
            });

        self.is_open = is_open;
        submitted_request
    }
}
