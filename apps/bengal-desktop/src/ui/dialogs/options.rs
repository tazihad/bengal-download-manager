use std::path::PathBuf;
use eframe::egui;
use bengal_media::{MediaDependencies, ToolInfo};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OptionsTab {
    General,
    Engine,
    Network,
    MediaTools,
}

pub struct OptionsDialog {
    pub is_open: bool,
    pub current_tab: OptionsTab,

    // General
    pub default_download_dir: PathBuf,
    pub dark_theme: bool,
    pub notifications_enabled: bool,

    // Engine
    pub max_concurrent_downloads: usize,
    pub default_segments: usize,
    pub preallocate_disk: bool,

    // Network
    pub global_speed_limit_kb: u64,
    pub proxy_mode: String,
    pub proxy_url: String,
    pub extension_port: u16,

    // Media Tools
    pub media_tools: Vec<ToolInfo>,
}

impl Default for OptionsDialog {
    fn default() -> Self {
        Self {
            is_open: false,
            current_tab: OptionsTab::General,
            default_download_dir: bengal_core::AppPaths::default_download_dir(),
            dark_theme: true,
            notifications_enabled: true,
            max_concurrent_downloads: 3,
            default_segments: 8,
            preallocate_disk: true,
            global_speed_limit_kb: 0,
            proxy_mode: "Direct".to_string(),
            proxy_url: String::new(),
            extension_port: 56800,
            media_tools: Vec::new(),
        }
    }
}

impl OptionsDialog {
    pub fn open(&mut self) {
        self.is_open = true;
        self.refresh_tools();
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    pub fn refresh_tools(&mut self) {
        self.media_tools = MediaDependencies::inspect_all();
    }

    pub fn render(&mut self, ctx: &egui::Context) {
        if !self.is_open {
            return;
        }

        let mut window_open = true;
        let mut need_refresh_tools = false;

        egui::Window::new("⚙ Preferences & Options")
            .open(&mut window_open)
            .collapsible(false)
            .resizable(false)
            .default_width(620.0)
            .default_height(460.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.selectable_value(&mut self.current_tab, OptionsTab::General, "General");
                    ui.selectable_value(&mut self.current_tab, OptionsTab::Engine, "Engine (Tigris)");
                    ui.selectable_value(&mut self.current_tab, OptionsTab::Network, "Network & Proxy");
                    ui.selectable_value(&mut self.current_tab, OptionsTab::MediaTools, "Media Tools");
                });

                ui.separator();
                ui.add_space(8.0);

                match self.current_tab {
                    OptionsTab::General => {
                        ui.heading("General Settings");
                        ui.add_space(6.0);

                        ui.horizontal(|ui| {
                            ui.label("Default Download Directory:");
                            let mut s = self.default_download_dir.to_string_lossy().to_string();
                            ui.text_edit_singleline(&mut s);
                            if ui.button("Browse...").clicked() {
                                if let Some(dir) = rfd::FileDialog::new().pick_folder() {
                                    self.default_download_dir = dir;
                                }
                            }
                        });

                        ui.add_space(8.0);
                        ui.checkbox(&mut self.dark_theme, "Enable Dark Theme");
                        ui.checkbox(&mut self.notifications_enabled, "Desktop Notifications on Completion");
                    }
                    OptionsTab::Engine => {
                        ui.heading("Tigris Engine Settings");
                        ui.add_space(6.0);

                        ui.horizontal(|ui| {
                            ui.label("Max Concurrent Downloads:");
                            ui.add(egui::Slider::new(&mut self.max_concurrent_downloads, 1..=10));
                        });

                        ui.horizontal(|ui| {
                            ui.label("Default Connections per File:");
                            ui.add(egui::Slider::new(&mut self.default_segments, 1..=32));
                        });

                        ui.add_space(8.0);
                        ui.checkbox(&mut self.preallocate_disk, "Pre-allocate Disk Space (posix_fallocate)");
                    }
                    OptionsTab::Network => {
                        ui.heading("Network & Extension Connectivity");
                        ui.add_space(6.0);

                        ui.horizontal(|ui| {
                            ui.label("Global Speed Limit (KB/s):");
                            ui.add(egui::DragValue::new(&mut self.global_speed_limit_kb).speed(100));
                            if self.global_speed_limit_kb == 0 {
                                ui.label("(Unlimited)");
                            }
                        });

                        ui.add_space(8.0);
                        ui.horizontal(|ui| {
                            ui.label("Proxy Mode:");
                            egui::ComboBox::from_id_salt("proxy_mode_sel")
                                .selected_text(&self.proxy_mode)
                                .show_ui(ui, |ui| {
                                    ui.selectable_value(&mut self.proxy_mode, "Direct".to_string(), "Direct (No Proxy)");
                                    ui.selectable_value(&mut self.proxy_mode, "HTTP".to_string(), "HTTP Proxy");
                                    ui.selectable_value(&mut self.proxy_mode, "SOCKS5".to_string(), "SOCKS5 Proxy");
                                });
                        });

                        if self.proxy_mode != "Direct" {
                            ui.horizontal(|ui| {
                                ui.label("Proxy Address:");
                                ui.text_edit_singleline(&mut self.proxy_url);
                            });
                        }

                        ui.add_space(8.0);
                        ui.horizontal(|ui| {
                            ui.label("Browser Extension Port:");
                            ui.add(egui::DragValue::new(&mut self.extension_port));
                            ui.label("(Default: 56800)");
                        });
                    }
                    OptionsTab::MediaTools => {
                        ui.heading("External Media Tools Inspector");
                        ui.add_space(4.0);

                        for tool in &self.media_tools {
                            ui.group(|ui| {
                                ui.horizontal(|ui| {
                                    let status_glyph = if tool.available { "✔ Available" } else { "✖ Missing" };
                                    let col = if tool.available { egui::Color32::from_rgb(52, 168, 83) } else { egui::Color32::from_rgb(234, 67, 53) };

                                    ui.strong(&tool.name);
                                    ui.colored_label(col, status_glyph);
                                    if let Some(v) = &tool.version {
                                        ui.weak(v);
                                    }
                                });
                                ui.label(&tool.role);
                                if let Some(p) = &tool.path {
                                    ui.weak(format!("Path: {}", p.display()));
                                }
                            });
                            ui.add_space(2.0);
                        }

                        ui.add_space(8.0);
                        if ui.button("🔄 Refresh Tools").clicked() {
                            need_refresh_tools = true;
                        }
                    }
                }

                ui.add_space(16.0);
                ui.separator();
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button("OK").clicked() {
                        self.is_open = false;
                    }
                });
            });

        if !window_open {
            self.is_open = false;
        }
        if need_refresh_tools {
            self.refresh_tools();
        }
    }
}
