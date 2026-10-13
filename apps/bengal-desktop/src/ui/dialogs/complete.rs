use std::path::Path;
use eframe::egui;
use bengal_core::DownloadRecord;

#[derive(Default)]
pub struct CompleteDialog {
    pub is_open: bool,
    pub record: Option<DownloadRecord>,
}

impl CompleteDialog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(&mut self, record: DownloadRecord) {
        self.record = Some(record);
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
        self.record = None;
    }

    pub fn render(&mut self, ctx: &egui::Context) {
        if !self.is_open {
            return;
        }

        let rec = match &self.record {
            Some(r) => r.clone(),
            None => {
                self.is_open = false;
                return;
            }
        };

        let mut is_open = self.is_open;
        let mut close_clicked = false;
        let mut open_file = false;
        let mut open_folder = false;

        egui::Window::new("🎉 Download Complete")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(false)
            .default_width(450.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.heading("✔");
                    ui.vertical(|ui| {
                        ui.strong(&rec.filename);
                        ui.label(format!("Size: {}", rec.size));
                    });
                });

                ui.add_space(8.0);
                ui.label(format!("Saved to: {}", rec.path));

                ui.add_space(12.0);
                ui.separator();
                ui.horizontal(|ui| {
                    if ui.button("📂 Open Folder").clicked() {
                        open_folder = true;
                        close_clicked = true;
                    }
                    if ui.button("▶ Open File").clicked() {
                        open_file = true;
                        close_clicked = true;
                    }
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Close").clicked() {
                            close_clicked = true;
                        }
                    });
                });
            });

        if open_file {
            let _ = open::that(&rec.path);
        }
        if open_folder {
            if let Some(parent) = Path::new(&rec.path).parent() {
                let _ = open::that(parent);
            }
        }
        if close_clicked {
            is_open = false;
        }

        self.is_open = is_open;
    }
}
