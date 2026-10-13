use eframe::egui;

#[derive(Debug, Clone)]
pub struct ColumnSettings {
    pub show_size: bool,
    pub show_status: bool,
    pub show_progress: bool,
    pub show_speed: bool,
    pub show_eta: bool,
    pub show_category: bool,
}

impl Default for ColumnSettings {
    fn default() -> Self {
        Self {
            show_size: true,
            show_status: true,
            show_progress: true,
            show_speed: true,
            show_eta: true,
            show_category: true,
        }
    }
}

#[derive(Default)]
pub struct ColumnConfigDialog {
    pub is_open: bool,
    pub settings: ColumnSettings,
}

impl ColumnConfigDialog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(&mut self) {
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    pub fn render(&mut self, ctx: &egui::Context) {
        if !self.is_open {
            return;
        }

        let mut is_open = self.is_open;
        let mut close_clicked = false;

        egui::Window::new("⚙ Customize Table Columns")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(false)
            .default_width(320.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.label("Select the columns to display in the main downloads list:");
                ui.add_space(8.0);

                ui.add_enabled_ui(false, |ui| {
                    let mut always_true = true;
                    ui.checkbox(&mut always_true, "File Name (Required)");
                });

                ui.checkbox(&mut self.settings.show_size, "File Size");
                ui.checkbox(&mut self.settings.show_status, "Status");
                ui.checkbox(&mut self.settings.show_progress, "Progress %");
                ui.checkbox(&mut self.settings.show_speed, "Transfer Speed");
                ui.checkbox(&mut self.settings.show_eta, "Estimated Time (ETA)");
                ui.checkbox(&mut self.settings.show_category, "Category");

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
