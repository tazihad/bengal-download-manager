use eframe::egui;
use bengal_core::{format_bytes, parse_size_to_bytes};

#[derive(Default)]
pub struct DataUsageDialog {
    pub is_open: bool,
    pub today_bytes: u64,
    pub week_bytes: u64,
    pub month_bytes: u64,
    pub total_bytes: u64,
}

impl DataUsageDialog {
    pub fn open(&mut self) {
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    pub fn update_stats(&mut self, downloads: &[bengal_core::DownloadRecord]) {
        let mut tot = 0u64;
        for d in downloads {
            if let Some(b) = parse_size_to_bytes(&d.downloaded) {
                tot += b;
            }
        }
        self.total_bytes = tot;
        self.month_bytes = tot;
        self.week_bytes = tot;
        self.today_bytes = tot;
    }

    pub fn render(&mut self, ctx: &egui::Context) {
        if !self.is_open {
            return;
        }

        let mut window_open = true;

        egui::Window::new("📊 Network Data Usage")
            .open(&mut window_open)
            .collapsible(false)
            .resizable(false)
            .default_width(450.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.add_space(4.0);
                ui.heading("Bandwidth Accounting");
                ui.add_space(6.0);

                ui.group(|ui| {
                    ui.horizontal(|ui| {
                        ui.label("Today:");
                        ui.monospace(format_bytes(self.today_bytes));
                    });
                    ui.horizontal(|ui| {
                        ui.label("This Week:");
                        ui.monospace(format_bytes(self.week_bytes));
                    });
                    ui.horizontal(|ui| {
                        ui.label("This Month:");
                        ui.monospace(format_bytes(self.month_bytes));
                    });
                    ui.separator();
                    ui.horizontal(|ui| {
                        ui.strong("Total Downloaded:");
                        ui.monospace(format_bytes(self.total_bytes));
                    });
                });

                ui.add_space(12.0);
                ui.separator();
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button("Close").clicked() {
                        self.is_open = false;
                    }
                });
            });

        if !window_open {
            self.is_open = false;
        }
    }
}
