use eframe::egui;
use bengal_core::DownloadRecord;

#[derive(Default)]
pub struct RenameDialog {
    pub is_open: bool,
    pub record: Option<DownloadRecord>,
    pub new_filename: String,
}

impl RenameDialog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(&mut self, record: DownloadRecord) {
        self.new_filename = record.filename.clone();
        self.record = Some(record);
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
        self.record = None;
        self.new_filename.clear();
    }

    /// Renders dialog and returns `Some((id, new_filename))` if user confirms rename.
    pub fn render(&mut self, ctx: &egui::Context) -> Option<(i64, String)> {
        if !self.is_open {
            return None;
        }

        let rec = match &self.record {
            Some(r) => r.clone(),
            None => {
                self.is_open = false;
                return None;
            }
        };

        let mut is_open = self.is_open;
        let mut confirmed = false;
        let mut cancel_clicked = false;

        egui::Window::new("✏ Rename Download")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(false)
            .default_width(380.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.label(format!("Current Name: {}", rec.filename));
                ui.add_space(4.0);

                ui.label("New File Name:");
                ui.add(egui::TextEdit::singleline(&mut self.new_filename));

                ui.add_space(12.0);
                ui.separator();
                ui.horizontal(|ui| {
                    if ui.button("Rename").clicked() && !self.new_filename.trim().is_empty() {
                        confirmed = true;
                    }
                    if ui.button("Cancel").clicked() {
                        cancel_clicked = true;
                    }
                });
            });

        if confirmed || cancel_clicked {
            is_open = false;
        }

        self.is_open = is_open;

        if confirmed {
            Some((rec.id, self.new_filename.trim().to_string()))
        } else {
            None
        }
    }
}
