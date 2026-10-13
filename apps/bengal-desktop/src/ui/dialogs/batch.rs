use std::path::PathBuf;
use eframe::egui;
use bengal_core::pattern::BatchPattern;

#[derive(Debug, Clone)]
pub struct BatchItem {
    pub url: String,
    pub filename: String,
    pub selected: bool,
}

pub struct BatchDownloadDialog {
    pub is_open: bool,
    pub pattern_input: String,
    pub urls_text: String,
    pub items: Vec<BatchItem>,
    pub save_dir: PathBuf,
    pub start_now: bool,
}

impl Default for BatchDownloadDialog {
    fn default() -> Self {
        Self {
            is_open: false,
            pattern_input: String::new(),
            urls_text: String::new(),
            items: Vec::new(),
            save_dir: bengal_core::AppPaths::default_download_dir(),
            start_now: true,
        }
    }
}

impl BatchDownloadDialog {
    pub fn open(&mut self) {
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    fn update_items(&mut self) {
        self.items.clear();

        // 1. Check pattern input
        if !self.pattern_input.trim().is_empty() {
            if let Ok(expanded) = BatchPattern::expand_expression(&self.pattern_input) {
                for u in expanded {
                    let fname = derive_filename(&u);
                    self.items.push(BatchItem {
                        url: u,
                        filename: fname,
                        selected: true,
                    });
                }
            }
        }

        // 2. Parse multiline URLs
        for line in self.urls_text.lines() {
            let clean = line.trim();
            if clean.starts_with("http://") || clean.starts_with("https://") {
                let fname = derive_filename(clean);
                self.items.push(BatchItem {
                    url: clean.to_string(),
                    filename: fname,
                    selected: true,
                });
            }
        }
    }

    pub fn render(&mut self, ctx: &egui::Context) -> Option<Vec<crate::ui::dialogs::add::AddDownloadRequest>> {
        if !self.is_open {
            return None;
        }

        let mut submitted_requests = None;
        let mut is_open = self.is_open;

        egui::Window::new("📑 Batch Download")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(true)
            .default_width(640.0)
            .default_height(500.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.add_space(4.0);

                ui.label("Pattern Syntax (e.g. https://example.com/file_[01-10].mp4 or [a-e]):");
                let resp_pat = ui.text_edit_singleline(&mut self.pattern_input);
                if resp_pat.changed() {
                    self.update_items();
                }

                ui.add_space(8.0);
                ui.label("Or paste URLs (one per line):");
                let resp_text = ui.add(
                    egui::TextEdit::multiline(&mut self.urls_text)
                        .desired_rows(4)
                        .desired_width(f32::INFINITY),
                );
                if resp_text.changed() {
                    self.update_items();
                }

                ui.add_space(8.0);

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

                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    ui.label(format!("Discovered Items: {}", self.items.len()));
                    if ui.button("Select All").clicked() {
                        for item in &mut self.items {
                            item.selected = true;
                        }
                    }
                    if ui.button("Unselect All").clicked() {
                        for item in &mut self.items {
                            item.selected = false;
                        }
                    }
                });

                ui.add_space(4.0);

                // Preview list
                egui::ScrollArea::vertical()
                    .max_height(200.0)
                    .show(ui, |ui| {
                        for (idx, item) in self.items.iter_mut().enumerate() {
                            ui.horizontal(|ui| {
                                ui.checkbox(&mut item.selected, "");
                                ui.label(format!("{}.", idx + 1));
                                ui.label(&item.filename);
                                ui.weak(&item.url);
                            });
                        }
                    });

                ui.add_space(8.0);
                ui.checkbox(&mut self.start_now, "Start downloads immediately");

                ui.add_space(8.0);
                ui.separator();
                ui.add_space(4.0);

                // Actions row
                ui.horizontal(|ui| {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Cancel").clicked() {
                            self.is_open = false;
                        }

                        let selected_count = self.items.iter().filter(|i| i.selected).count();
                        let can_submit = selected_count > 0;

                        if ui
                            .add_enabled(
                                can_submit,
                                egui::Button::new(format!("Add Selected ({})", selected_count)),
                            )
                            .clicked()
                        {
                            let mut reqs = Vec::new();
                            for item in &self.items {
                                if item.selected {
                                    reqs.push(crate::ui::dialogs::add::AddDownloadRequest {
                                        url: item.url.clone(),
                                        filename: item.filename.clone(),
                                        save_dir: self.save_dir.clone(),
                                        start_now: self.start_now,
                                        max_segments: 8,
                                        speed_limit_bps: 0,
                                        referrer: None,
                                        user_agent: None,
                                        cookies: None,
                                        proxy: None,
                                    });
                                }
                            }
                            submitted_requests = Some(reqs);
                            self.is_open = false;
                        }
                    });
                });
            });

        self.is_open = is_open;
        submitted_requests
    }
}

fn derive_filename(u: &str) -> String {
    if let Ok(parsed) = url::Url::parse(u) {
        let path = parsed.path().trim_end_matches('/');
        if let Some(base) = path.split('/').next_back() {
            if let Ok(decoded) = percent_encoding::percent_decode_str(base).decode_utf8() {
                if !decoded.is_empty() && decoded.contains('.') {
                    return decoded.to_string();
                }
            }
        }
    }
    "batch_file".to_string()
}
