use eframe::egui;
use bengal_core::DownloadRecord;

#[derive(Default)]
pub struct RefreshUrlDialog {
    pub is_open: bool,
    pub record: Option<DownloadRecord>,
    pub new_url: String,
}

impl RefreshUrlDialog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(&mut self, record: DownloadRecord) {
        self.new_url = record.url.clone();
        self.record = Some(record);
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
        self.record = None;
        self.new_url.clear();
    }

    /// Renders dialog and returns `Some((download_id, new_url))` if user confirms refresh.
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

        egui::Window::new("🔄 Refresh Download Address")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(true)
            .default_width(480.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.label(format!("Refreshing download link for: {}", rec.filename));
                ui.weak("Replace an expired temporary download link without losing already downloaded progress.");
                ui.add_space(8.0);

                ui.label("Existing (Expired) URL:");
                ui.add(egui::TextEdit::singleline(&mut rec.url.clone()).interactive(false));

                ui.add_space(8.0);
                ui.label("New Download URL:");
                ui.add(egui::TextEdit::singleline(&mut self.new_url).hint_text("Paste new renewed URL here..."));

                ui.add_space(12.0);
                ui.separator();
                ui.horizontal(|ui| {
                    if ui.button("Save New URL").clicked() && !self.new_url.trim().is_empty() {
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
            Some((rec.id, self.new_url.trim().to_string()))
        } else {
            None
        }
    }
}
