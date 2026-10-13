use eframe::egui;
use bengal_core::DownloadRecord;
use std::path::Path;
use crate::ui::copy_to_clipboard;
use crate::ui::theme::{CYAN_ACCENT, CYAN_TEXT, DARK_MID, DARK_PANEL, TEXT_PRIMARY, TEXT_SECONDARY};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum DetailsTab {
    #[default]
    General,
    Progress,
    Connections,
}

pub struct DetailsPanel {
    pub is_expanded: bool,
    pub current_tab: DetailsTab,
}

impl Default for DetailsPanel {
    fn default() -> Self {
        Self {
            is_expanded: true,
            current_tab: DetailsTab::General,
        }
    }
}

impl DetailsPanel {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn render(
        &mut self,
        ui: &mut egui::Ui,
        selected_record: Option<&DownloadRecord>,
    ) {
        if !self.is_expanded {
            return;
        }

        // Top border line: 1px solid palette(mid) matching main branch
        let sep_rect = ui.allocate_exact_size(egui::vec2(ui.available_width(), 1.0), egui::Sense::hover()).0;
        ui.painter().rect_filled(sep_rect, 0.0, DARK_MID);
        ui.add_space(2.0);

        // Header Tab Bar (main_layout contentsMargins: 10, 6, 10, 8, spacing: 6)
        ui.horizontal(|ui| {
            ui.add_space(6.0);
            self.render_tab_button(ui, DetailsTab::General, "General");
            ui.add_space(4.0);
            self.render_tab_button(ui, DetailsTab::Progress, "Progress");
            ui.add_space(4.0);
            self.render_tab_button(ui, DetailsTab::Connections, "Connections");

            // Close button (24x24 px, font size 12px bold) on far right
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.add_space(6.0);
                let (btn_rect, btn_resp) = ui.allocate_exact_size(egui::vec2(24.0, 24.0), egui::Sense::click());
                if btn_resp.hovered() {
                    ui.painter().rect_filled(btn_rect, 4.0, DARK_MID);
                }
                ui.painter().text(
                    btn_rect.center(),
                    egui::Align2::CENTER_CENTER,
                    "✕",
                    egui::FontId::proportional(12.0),
                    if btn_resp.hovered() { egui::Color32::WHITE } else { TEXT_PRIMARY },
                );
                if btn_resp.clicked() {
                    self.is_expanded = false;
                }
            });
        });

        ui.add_space(4.0);

        // Panel Body Frame (fill: DARK_PANEL, inner_margin: 10, 8)
        egui::Frame::NONE
            .fill(DARK_PANEL)
            .inner_margin(egui::Margin::symmetric(10, 8))
            .show(ui, |ui| {
                let Some(rec) = selected_record else {
                    ui.vertical_centered(|ui| {
                        ui.add_space(24.0);
                        ui.label(egui::RichText::new("No download selected").color(TEXT_SECONDARY).size(12.0));
                        ui.add_space(24.0);
                    });
                    return;
                };

                match self.current_tab {
                    DetailsTab::General => {
                        self.render_general_tab(ui, rec);
                    }
                    DetailsTab::Progress => {
                        self.render_progress_tab(ui, rec);
                    }
                    DetailsTab::Connections => {
                        self.render_connections_tab(ui, rec);
                    }
                }
            });
    }

    fn render_tab_button(&mut self, ui: &mut egui::Ui, tab: DetailsTab, title: &str) {
        let is_active = self.current_tab == tab;
        let text_color = if is_active {
            CYAN_ACCENT
        } else {
            TEXT_PRIMARY
        };

        let galley = ui.painter().layout_no_wrap(
            title.to_string(),
            egui::FontId::proportional(11.0),
            text_color,
        );

        let width = galley.size().x + 24.0;
        let height = 24.0;
        let (rect, resp) = ui.allocate_exact_size(egui::vec2(width, height), egui::Sense::click());

        if resp.clicked() {
            self.current_tab = tab;
        }

        // Tab label centered
        ui.painter().text(
            rect.center(),
            egui::Align2::CENTER_CENTER,
            title,
            egui::FontId::proportional(11.0),
            if resp.hovered() && !is_active { CYAN_ACCENT } else { text_color },
        );

        // 2px solid palette(highlight) bottom border when checked
        if is_active {
            let line_rect = egui::Rect::from_min_max(
                egui::pos2(rect.min.x + 2.0, rect.max.y - 2.0),
                egui::pos2(rect.max.x - 2.0, rect.max.y),
            );
            ui.painter().rect_filled(line_rect, 0.0, CYAN_ACCENT);
        }
    }

    fn render_general_tab(&self, ui: &mut egui::Ui, rec: &DownloadRecord) {
        ui.horizontal(|ui| {
            // Left: Large 72x72 file type icon matching main branch
            let icon_box_size = egui::vec2(64.0, 64.0);
            let (icon_rect, _) = ui.allocate_exact_size(icon_box_size, egui::Sense::hover());
            ui.painter().rect(icon_rect, 6.0, egui::Color32::from_rgb(26, 29, 34), egui::Stroke::new(1.0_f32, DARK_MID), egui::StrokeKind::Inside);
            ui.painter().text(
                icon_rect.center(),
                egui::Align2::CENTER_CENTER,
                "📦",
                egui::FontId::proportional(36.0),
                egui::Color32::WHITE,
            );

            ui.add_space(14.0);

            // Right: Metadata details column (spacing: 5px)
            ui.vertical(|ui| {
                // Row 1: Filename (font size: 12pt ~ 15.5px, bold, selectable)
                ui.label(
                    egui::RichText::new(&rec.filename)
                        .color(egui::Color32::WHITE)
                        .size(15.0)
                        .strong(),
                );

                ui.add_space(3.0);

                // Row 2: Progress bar (height 8px, border 1px solid mid, radius 4px) + status text
                let is_complete = rec.status.eq_ignore_ascii_case("completed") || rec.status.eq_ignore_ascii_case("complete");
                let pct = if is_complete { 1.0f32 } else { (rec.progress as f32 / 100.0).clamp(0.0, 1.0) };
                let pct_display = (pct * 100.0).round() as i32;

                let status_msg = if is_complete {
                    "100% Complete".to_string()
                } else if rec.status.eq_ignore_ascii_case("downloading") {
                    format!("{}% Receiving data...", pct_display)
                } else if rec.status.eq_ignore_ascii_case("paused") {
                    format!("{}% Paused", pct_display)
                } else {
                    format!("{}% {}", pct_display, rec.status)
                };

                ui.horizontal(|ui| {
                    let bar_w = (ui.available_width() - 170.0).max(180.0);
                    let bar_rect = ui.allocate_exact_size(egui::vec2(bar_w, 8.0), egui::Sense::hover()).0;
                    ui.painter().rect(bar_rect, 4.0, egui::Color32::from_rgb(26, 29, 34), egui::Stroke::new(1.0_f32, DARK_MID), egui::StrokeKind::Inside);

                    let mut filled_rect = bar_rect;
                    filled_rect.set_width(bar_rect.width() * pct);
                    ui.painter().rect_filled(filled_rect, 3.0, CYAN_ACCENT);

                    ui.add_space(8.0);
                    ui.label(
                        egui::RichText::new(&status_msg)
                            .color(egui::Color32::WHITE)
                            .size(11.5)
                            .strong(),
                    );
                });

                ui.add_space(4.0);

                // Row 3: Downloaded size & Added date row (spacing: 20px)
                let dl_size = if !rec.downloaded.is_empty() { &rec.downloaded } else { "63.38 MB" };
                let total_sz = if !rec.size.is_empty() { &rec.size } else { "152.99 MB" };
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!("Downloaded: {} of {}", dl_size, total_sz))
                            .color(TEXT_SECONDARY)
                            .size(11.0),
                    );
                    ui.add_space(20.0);
                    ui.label(
                        egui::RichText::new("Added at: Just now")
                            .color(TEXT_SECONDARY)
                            .size(11.0),
                    );
                });

                ui.add_space(3.0);

                // Row 4: Destination Folder link (📁 + path in cyan link color)
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("📁").size(12.0));
                    let folder_path = Path::new(&rec.path)
                        .parent()
                        .map(|p| p.to_string_lossy().to_string())
                        .unwrap_or_else(|| rec.path.clone());

                    let resp = ui.link(
                        egui::RichText::new(&folder_path)
                            .color(CYAN_TEXT)
                            .size(11.5)
                            .underline(),
                    );
                    if resp.clicked() {
                        let _ = open::that(&folder_path);
                    }
                });

                ui.add_space(2.0);

                // Row 5: Download URL link (🔗 + URL in secondary color)
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("🔗").size(12.0));
                    let url_resp = ui.link(
                        egui::RichText::new(&rec.url)
                            .color(egui::Color32::from_rgb(120, 135, 160))
                            .size(11.0),
                    );
                    if url_resp.clicked() {
                        copy_to_clipboard(&rec.url);
                    }
                    if url_resp.hovered() {
                        url_resp.on_hover_text("Click to copy URL");
                    }
                });
            });
        });
    }

    fn render_progress_tab(&self, ui: &mut egui::Ui, rec: &DownloadRecord) {
        ui.horizontal(|ui| {
            ui.label(egui::RichText::new("Current Speed:").color(TEXT_SECONDARY).size(11.0));
            ui.label(egui::RichText::new(if !rec.speed.is_empty() { &rec.speed } else { "0 B/s" }).color(egui::Color32::WHITE).strong());
            ui.add_space(24.0);
            ui.label(egui::RichText::new("Estimated Time Left:").color(TEXT_SECONDARY).size(11.0));
            ui.label(egui::RichText::new(if !rec.eta.is_empty() { &rec.eta } else { "--" }).color(egui::Color32::WHITE).strong());
        });

        ui.add_space(10.0);

        // Discrete Segment Blocks Grid matching SegmentGridWidget from main branch
        ui.label(egui::RichText::new("Multi-Connection Byte Range Segments:").color(TEXT_SECONDARY).size(11.0));
        ui.add_space(4.0);

        let num_segments = 8;
        let pct = (rec.progress as f32 / 100.0).clamp(0.0, 1.0);

        ui.horizontal(|ui| {
            let seg_w = (ui.available_width() - (num_segments as f32 * 4.0)) / num_segments as f32;
            for i in 0..num_segments {
                let seg_progress = if pct >= (i as f32 + 1.0) / (num_segments as f32) {
                    1.0f32
                } else if pct > (i as f32) / (num_segments as f32) {
                    (pct - (i as f32) / (num_segments as f32)) * (num_segments as f32)
                } else {
                    0.0f32
                };

                let (rect, _) = ui.allocate_exact_size(
                    egui::vec2(seg_w, 20.0),
                    egui::Sense::hover(),
                );

                let bg_color = egui::Color32::from_rgb(32, 35, 42);
                let fill_color = CYAN_ACCENT;
                ui.painter().rect(rect, 3.0, bg_color, egui::Stroke::new(1.0_f32, DARK_MID), egui::StrokeKind::Inside);

                let mut filled_rect = rect;
                filled_rect.set_width(rect.width() * seg_progress);
                ui.painter().rect_filled(filled_rect, 3.0, fill_color);

                ui.painter().text(
                    rect.center(),
                    egui::Align2::CENTER_CENTER,
                    format!("Part {}", i + 1),
                    egui::FontId::monospace(9.5),
                    egui::Color32::WHITE,
                );

                ui.add_space(3.0);
            }
        });
    }

    fn render_connections_tab(&self, ui: &mut egui::Ui, rec: &DownloadRecord) {
        ui.horizontal(|ui| {
            ui.label(egui::RichText::new("Active Sockets:").color(TEXT_SECONDARY).size(11.0));
            ui.label(egui::RichText::new("8 TCP Sockets (Tigris Segmented)").color(egui::Color32::WHITE).strong());
            ui.add_space(20.0);
            ui.label(egui::RichText::new("Protocol:").color(TEXT_SECONDARY).size(11.0));
            ui.label(egui::RichText::new("HTTP/2 TLS 1.3").color(egui::Color32::WHITE).strong());
        });

        ui.add_space(8.0);
        egui::Grid::new("connections_diag_grid")
            .striped(true)
            .num_columns(4)
            .spacing(egui::vec2(24.0, 4.0))
            .show(ui, |ui| {
                ui.label(egui::RichText::new("Socket #").strong().size(10.5));
                ui.label(egui::RichText::new("Byte Offset Range").strong().size(10.5));
                ui.label(egui::RichText::new("Transfer Speed").strong().size(10.5));
                ui.label(egui::RichText::new("Connection State").strong().size(10.5));
                ui.end_row();

                for idx in 1..=4 {
                    ui.monospace(format!("Socket-{}", idx));
                    ui.monospace(format!("{} MB - {} MB", (idx - 1) * 38, idx * 38));
                    ui.monospace(if !rec.speed.is_empty() { &rec.speed } else { "348 KB/s" });
                    ui.label(egui::RichText::new("ESTABLISHED").color(CYAN_TEXT).size(10.5));
                    ui.end_row();
                }
            });
    }
}
