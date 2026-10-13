use eframe::egui;
use bengal_core::{CompletionAction, QueueScheduleConfig};

pub struct SchedulerDialog {
    pub is_open: bool,
    pub config: QueueScheduleConfig,
    pub selected_queue: String,
    pub start_time_str: String,
    pub stop_time_str: String,
}

impl Default for SchedulerDialog {
    fn default() -> Self {
        Self {
            is_open: false,
            config: QueueScheduleConfig::default(),
            selected_queue: "Default".to_string(),
            start_time_str: "02:00".to_string(),
            stop_time_str: "06:00".to_string(),
        }
    }
}

impl SchedulerDialog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(&mut self, queue_name: &str) {
        self.is_open = true;
        self.selected_queue = queue_name.to_string();
        self.config.name = queue_name.to_string();
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
        let mut save_clicked = false;

        egui::Window::new(format!("⏰ Queue Scheduler: {}", self.selected_queue))
            .open(&mut is_open)
            .collapsible(false)
            .resizable(false)
            .default_width(460.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.heading(format!("Queue: {}", self.selected_queue));
                ui.add_space(4.0);

                ui.group(|ui| {
                    ui.label("Queue Concurrency");
                    ui.horizontal(|ui| {
                        ui.label("Max active downloads:");
                        ui.add(egui::Slider::new(&mut self.config.max_concurrent, 1..=16));
                    });
                });

                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.checkbox(&mut self.config.enabled, "Enable scheduled start and stop times");
                    ui.add_space(4.0);

                    ui.add_enabled_ui(self.config.enabled, |ui| {
                        ui.horizontal(|ui| {
                            ui.label("Start Time (24h):");
                            ui.add(egui::TextEdit::singleline(&mut self.start_time_str).desired_width(70.0));
                            ui.label("Stop Time (24h):");
                            ui.add(egui::TextEdit::singleline(&mut self.stop_time_str).desired_width(70.0));
                        });

                        ui.add_space(4.0);
                        ui.label("Active Days:");
                        ui.horizontal(|ui| {
                            let day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
                            for (idx, name) in day_names.iter().enumerate() {
                                ui.checkbox(&mut self.config.days[idx], *name);
                            }
                        });
                    });
                });

                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.label("Action on Queue Completion:");
                    ui.horizontal(|ui| {
                        ui.radio_value(&mut self.config.on_completion, CompletionAction::None, "Do nothing");
                        ui.radio_value(&mut self.config.on_completion, CompletionAction::QuitBengal, "Quit BDM");
                        ui.radio_value(&mut self.config.on_completion, CompletionAction::Sleep, "Sleep");
                        ui.radio_value(&mut self.config.on_completion, CompletionAction::Shutdown, "Shutdown");
                    });
                });

                ui.add_space(12.0);
                ui.separator();
                ui.horizontal(|ui| {
                    if ui.button("Save Schedule").clicked() {
                        save_clicked = true;
                    }
                    if ui.button("Cancel").clicked() {
                        close_clicked = true;
                    }
                });
            });

        if save_clicked {
            self.config.start_time = Some(self.start_time_str.clone());
            self.config.stop_time = Some(self.stop_time_str.clone());
            is_open = false;
        }

        if close_clicked {
            is_open = false;
        }

        self.is_open = is_open;
    }
}
