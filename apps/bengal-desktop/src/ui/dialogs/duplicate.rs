use eframe::egui;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DuplicateAction {
    None,
    Overwrite,
    AutoRename,
    Cancel,
}

pub struct DuplicateDialog {
    pub is_open: bool,
    pub filename: String,
    pub path: String,
    pub chosen_action: DuplicateAction,
}

impl Default for DuplicateDialog {
    fn default() -> Self {
        Self {
            is_open: false,
            filename: String::new(),
            path: String::new(),
            chosen_action: DuplicateAction::None,
        }
    }
}

impl DuplicateDialog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(&mut self, filename: &str, path: &str) {
        self.filename = filename.to_string();
        self.path = path.to_string();
        self.chosen_action = DuplicateAction::None;
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    pub fn render(&mut self, ctx: &egui::Context) -> DuplicateAction {
        if !self.is_open {
            return DuplicateAction::None;
        }

        let mut is_open = self.is_open;
        let mut action = DuplicateAction::None;

        egui::Window::new("⚠ File Already Exists")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(false)
            .default_width(420.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.label(format!("A file named '{}' already exists at:", self.filename));
                ui.monospace(&self.path);
                ui.add_space(8.0);
                ui.label("How would you like to proceed?");
                ui.add_space(12.0);

                ui.horizontal(|ui| {
                    if ui.button("Overwrite").clicked() {
                        action = DuplicateAction::Overwrite;
                    }
                    if ui.button("Auto-Rename (Add Number)").clicked() {
                        action = DuplicateAction::AutoRename;
                    }
                    if ui.button("Cancel").clicked() {
                        action = DuplicateAction::Cancel;
                    }
                });
            });

        if action != DuplicateAction::None {
            is_open = false;
        }

        self.is_open = is_open;
        action
    }
}
