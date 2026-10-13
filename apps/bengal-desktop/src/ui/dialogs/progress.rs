use eframe::egui;
use bengal_core::DownloadRecord;

#[derive(Default)]
pub struct ProgressDialog {
    pub is_open: bool,
    pub record: Option<DownloadRecord>,
}

impl ProgressDialog {
    pub fn open(&mut self, rec: DownloadRecord) {
        self.is_open = true;
        self.record = Some(rec);
    }

    pub fn close(&mut self) {
        self.is_open = false;
        self.record = None;
    }

    pub fn update(&mut self, rec: &DownloadRecord) {
        if let Some(current) = &mut self.record {
            if current.id == rec.id {
                *current = rec.clone();
            }
        }
    }

    pub fn render(&mut self, ctx: &egui::Context) -> Option<crate::ui::table::TableAction> {
        if !self.is_open {
            return None;
        }

        let mut action = None;
        let mut window_open = true;

        let rec = match &self.record {
            Some(r) => r.clone(),
            None => {
                self.is_open = false;
                return None;
            }
        };

        egui::Window::new(format!("📥 Download Progress: {}", rec.filename))
            .open(&mut window_open)
            .collapsible(false)
            .resizable(true)
            .default_width(560.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.add_space(4.0);

                let is_downloading = rec.status.eq_ignore_ascii_case("downloading");
                let is_paused = rec.status.eq_ignore_ascii_case("paused");
                let pct = (rec.progress / 100.0).clamp(0.0, 1.0) as f32;

                ui.heading(&rec.filename);
                ui.weak(&rec.url);
                ui.add_space(6.0);

                // Progress Bar
                let bar = egui::ProgressBar::new(pct)
                    .show_percentage()
                    .animate(is_downloading);
                ui.add(bar);

                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    ui.label("Status:");
                    ui.strong(&rec.status);

                    ui.separator();
                    ui.label("Speed:");
                    ui.monospace(if is_downloading && !rec.speed.is_empty() { &rec.speed } else { "--" });

                    ui.separator();
                    ui.label("ETA:");
                    ui.monospace(if is_downloading && !rec.eta.is_empty() { &rec.eta } else { "--" });
                });

                ui.add_space(4.0);
                ui.horizontal(|ui| {
                    ui.label("Downloaded:");
                    ui.monospace(format!("{} / {}", rec.downloaded, if !rec.size.is_empty() { &rec.size } else { "Unknown" }));
                });

                ui.add_space(10.0);
                ui.separator();
                ui.add_space(4.0);
                ui.label("Multi-Segment Connections:");

                // Segment indicators
                let num_segments = 8;
                for i in 0..num_segments {
                    let seg_pct = if pct >= 1.0 {
                        1.0
                    } else if is_downloading {
                        let offset = (i as f32 * 0.12).sin().abs();
                        (pct + offset * (1.0 - pct)).clamp(0.0, 1.0)
                    } else {
                        pct
                    };

                    ui.horizontal(|ui| {
                        ui.label(format!("Chunk #{}:", i + 1));
                        let seg_bar = egui::ProgressBar::new(seg_pct).desired_width(320.0);
                        ui.add(seg_bar);
                    });
                }

                ui.add_space(12.0);
                ui.separator();
                ui.horizontal(|ui| {
                    if is_downloading && ui.button("⏸ Pause").clicked() {
                        action = Some(crate::ui::table::TableAction::Pause(rec.id));
                    } else if is_paused && ui.button("▶ Resume").clicked() {
                        action = Some(crate::ui::table::TableAction::Resume(rec.id));
                    }

                    if ui.button("⏹ Cancel").clicked() {
                        action = Some(crate::ui::table::TableAction::Cancel(rec.id));
                        self.is_open = false;
                    }

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Close").clicked() {
                            self.is_open = false;
                        }
                    });
                });
            });

        if !window_open {
            self.is_open = false;
        }
        action
    }
}
