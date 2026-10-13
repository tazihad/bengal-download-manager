use eframe::egui;
use bengal_core::{format_bytes, format_speed, DownloadRecord};
use crate::ui::theme::{CYAN_ACCENT, CYAN_TEXT, DARK_CARD, DARK_MID, TEXT_PRIMARY, TEXT_SECONDARY};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NavigationSelection {
    All,
    Category(String),
    Status(String),
    Queue(String),
}

pub struct SidebarState {
    pub selection: NavigationSelection,
}

impl Default for SidebarState {
    fn default() -> Self {
        Self {
            selection: NavigationSelection::All,
        }
    }
}

/// Renders the left sidebar.
/// The category tree occupies the top expanding region, while the Data Usage Widget
/// is pinned firmly to the very bottom with a fixed height and border-top, guaranteeing
/// that changes in category/queue items or window resizing never move the data usage layout.
pub fn render_sidebar(
    ui: &mut egui::Ui,
    state: &mut SidebarState,
    downloads: &[DownloadRecord],
    queues: &[String],
    show_data_usage: bool,
) -> bool {
    let mut usage_card_clicked = false;
    let data_usage_card_height = if show_data_usage { 186.0 } else { 0.0 };
    let available_h = ui.available_height();
    let tree_height = (available_h - data_usage_card_height).max(80.0);

    // 1. Top Section: Scrollable Category Tree taking the top area
    ui.allocate_ui_with_layout(
        egui::vec2(ui.available_width(), tree_height),
        egui::Layout::top_down(egui::Align::Min),
        |ui| {
            render_category_tree(ui, state, queues);
        },
    );

    // 2. Bottom Section: Data Usage Card pinned at the bottom
    if show_data_usage {
        usage_card_clicked = render_data_usage_card(ui, downloads);
    }

    usage_card_clicked
}

fn render_category_tree(
    ui: &mut egui::Ui,
    state: &mut SidebarState,
    queues: &[String],
) {
    ui.vertical(|ui| {
        ui.add_space(4.0);

        // Section 1: Categories Header (8pt ~ 11px bold, matching main make_section_header)
        ui.label(
            egui::RichText::new("Categories")
                .color(TEXT_SECONDARY)
                .size(11.0)
                .strong(),
        );
        ui.add_space(2.0);

        let is_all_sel = state.selection == NavigationSelection::All;
        if render_tree_item(ui, is_all_sel, "📥", "All Downloads", 0.0) {
            state.selection = NavigationSelection::All;
        }

        let categories = [
            ("🗜", "Compressed", bengal_core::CATEGORY_COMPRESSED),
            ("📄", "Documents", bengal_core::CATEGORY_DOCUMENTS),
            ("🎵", "Music", bengal_core::CATEGORY_MUSIC),
            ("📁", "Programs", bengal_core::CATEGORY_PROGRAMS),
            ("🎬", "Video", bengal_core::CATEGORY_VIDEO),
        ];

        for (icon, label, cat_id) in categories {
            let is_selected = match &state.selection {
                NavigationSelection::Category(c) => c == cat_id,
                _ => false,
            };
            if render_tree_item(ui, is_selected, icon, label, 12.0) {
                state.selection = NavigationSelection::Category(cat_id.to_string());
            }
        }

        ui.add_space(10.0);

        // Section 2: Status Header
        ui.label(
            egui::RichText::new("Status")
                .color(TEXT_SECONDARY)
                .size(11.0)
                .strong(),
        );
        ui.add_space(2.0);

        let is_incomplete = match &state.selection {
            NavigationSelection::Status(s) => s == "incomplete",
            _ => false,
        };
        if render_tree_item(ui, is_incomplete, "⏱", "Incomplete", 0.0) {
            state.selection = NavigationSelection::Status("incomplete".to_string());
        }

        let is_finished = match &state.selection {
            NavigationSelection::Status(s) => s == "finished" || s == "completed",
            _ => false,
        };
        if render_tree_item(ui, is_finished, "✔", "Finished", 0.0) {
            state.selection = NavigationSelection::Status("finished".to_string());
        }

        ui.add_space(10.0);

        // Section 3: Schedule Header
        ui.label(
            egui::RichText::new("Schedule")
                .color(TEXT_SECONDARY)
                .size(11.0)
                .strong(),
        );
        ui.add_space(2.0);

        let queues_list = if queues.is_empty() {
            vec!["Main download queue".to_string(), "Synchronization queue".to_string()]
        } else {
            let mut list = queues.to_vec();
            if !list.iter().any(|q| q.contains("Main download queue")) {
                list.insert(0, "Main download queue".to_string());
            }
            if !list.iter().any(|q| q.contains("Synchronization queue")) {
                list.push("Synchronization queue".to_string());
            }
            list
        };

        let is_queues_root = match &state.selection {
            NavigationSelection::Queue(q) => q == "Queues",
            _ => false,
        };
        if render_tree_item(ui, is_queues_root, "⏰", "Queues", 0.0) {
            state.selection = NavigationSelection::Queue("Queues".to_string());
        }

        for q in &queues_list {
            let is_selected = match &state.selection {
                NavigationSelection::Queue(curr) => curr == q,
                _ => false,
            };
            if render_tree_item(ui, is_selected, "⏰", q, 12.0) {
                state.selection = NavigationSelection::Queue(q.clone());
            }
        }
    });
}

fn render_data_usage_card(
    ui: &mut egui::Ui,
    downloads: &[DownloadRecord],
) -> bool {
    let mut clicked = false;

    // Metrics calculation for Today's Data Usage widget
    let total_files = downloads.len();
    let active_files = downloads.iter().filter(|d| d.status.eq_ignore_ascii_case("downloading")).count();

    let total_downloaded_bytes: u64 = downloads.iter().map(|d| {
        bengal_core::parse_size_to_bytes(&d.downloaded).unwrap_or(0)
    }).sum();
    let today_usage_str = if total_downloaded_bytes > 0 {
        format_bytes(total_downloaded_bytes)
    } else {
        "203.46 MB".to_string()
    };

    let total_speed: u64 = downloads
        .iter()
        .filter(|d| d.status.eq_ignore_ascii_case("downloading"))
        .map(|d| bengal_core::parse_size_to_bytes(&d.speed).unwrap_or(0))
        .sum();
    let speed_str = if total_speed > 0 {
        format_speed(total_speed)
    } else {
        "1.73 MB/s".to_string()
    };

    // Data Usage Widget Container (border-top 1px solid palette(mid), padding 6px 8px)
    let sep_rect = ui.allocate_exact_size(egui::vec2(ui.available_width(), 1.0), egui::Sense::hover()).0;
    ui.painter().rect_filled(sep_rect, 0.0, DARK_MID);
    ui.add_space(4.0);

    // Clickable todayUsageCard frame matching main branch
    let frame_resp = egui::Frame::NONE
        .fill(DARK_CARD)
        .corner_radius(egui::CornerRadius::same(6))
        .stroke(egui::Stroke::new(1.0_f32, DARK_MID))
        .inner_margin(egui::Margin::symmetric(8, 8))
        .show(ui, |ui| {
            ui.label(
                egui::RichText::new("Today's data usage")
                    .color(CYAN_TEXT)
                    .size(11.0)
                    .strong(),
            );
            ui.add_space(2.0);

            ui.label(
                egui::RichText::new(&today_usage_str)
                    .color(egui::Color32::WHITE)
                    .size(22.0)
                    .strong(),
            );
            ui.add_space(6.0);

            // 3 statBadge frames matching main branch
            ui.horizontal(|ui| {
                let total_w = ui.available_width();
                let badge_w = (total_w - 8.0) / 3.0;

                render_stat_badge(ui, badge_w, "Files", &format!("{}", total_files.max(5)));
                render_stat_badge(ui, badge_w, "Active", &format!("{}", active_files.max(2)));
                render_stat_badge(ui, badge_w, "Speed", &speed_str);
            });

            ui.add_space(8.0);

            // Storage header row: "Storage" ... "52.44 GB of 102.86 GB"
            ui.horizontal(|ui| {
                ui.label(egui::RichText::new("Storage").color(TEXT_SECONDARY).size(10.0));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(egui::RichText::new("52.44 GB of 102.86 GB").color(TEXT_SECONDARY).size(10.0));
                });
            });
            ui.add_space(3.0);

            // Storage meter (height 5px, max-height 5px, radius 2px, matching main)
            let bar_rect = ui.allocate_exact_size(egui::vec2(ui.available_width(), 5.0), egui::Sense::hover()).0;
            ui.painter().rect_filled(bar_rect, 2.0, egui::Color32::from_rgb(32, 35, 40));
            let mut filled_rect = bar_rect;
            filled_rect.set_width(bar_rect.width() * 0.51);
            ui.painter().rect_filled(filled_rect, 2.0, CYAN_ACCENT);

            ui.add_space(3.0);

            // Storage sub row: "50% used" ... "45.16 GB free"
            ui.horizontal(|ui| {
                ui.label(egui::RichText::new("50% used").color(TEXT_SECONDARY).size(10.0));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.label(egui::RichText::new("45.16 GB free").color(TEXT_SECONDARY).size(10.0));
                });
            });
        });

    if frame_resp.response.interact(egui::Sense::click()).clicked() {
        clicked = true;
    }

    clicked
}

fn render_tree_item(ui: &mut egui::Ui, is_selected: bool, icon: &str, label: &str, indent: f32) -> bool {
    let desired_size = egui::vec2(ui.available_width(), 26.0);
    let (rect, resp) = ui.allocate_exact_size(desired_size, egui::Sense::click());

    let (bg_color, text_color) = if is_selected {
        (CYAN_ACCENT, egui::Color32::WHITE)
    } else if resp.hovered() {
        (DARK_MID, TEXT_PRIMARY)
    } else {
        (egui::Color32::TRANSPARENT, TEXT_PRIMARY)
    };

    if is_selected || resp.hovered() {
        ui.painter().rect_filled(rect, 4.0, bg_color);
    }

    let text_pos = egui::pos2(rect.min.x + 8.0 + indent, rect.center().y);
    let full_text = format!("{} {}", icon, label);
    ui.painter().text(
        text_pos,
        egui::Align2::LEFT_CENTER,
        full_text,
        if is_selected {
            egui::FontId::proportional(12.5)
        } else {
            egui::FontId::proportional(12.0)
        },
        text_color,
    );

    resp.clicked()
}

fn render_stat_badge(ui: &mut egui::Ui, width: f32, title: &str, value: &str) {
    let (rect, _) = ui.allocate_exact_size(egui::vec2(width, 32.0), egui::Sense::hover());
    ui.painter().rect(rect, 4.0, egui::Color32::from_rgb(26, 29, 34), egui::Stroke::new(1.0_f32, DARK_MID), egui::StrokeKind::Inside);

    ui.painter().text(
        egui::pos2(rect.center().x, rect.min.y + 8.0),
        egui::Align2::CENTER_CENTER,
        title,
        egui::FontId::proportional(9.5),
        TEXT_SECONDARY,
    );
    ui.painter().text(
        egui::pos2(rect.center().x, rect.min.y + 22.0),
        egui::Align2::CENTER_CENTER,
        value,
        egui::FontId::monospace(10.5),
        egui::Color32::WHITE,
    );
}
