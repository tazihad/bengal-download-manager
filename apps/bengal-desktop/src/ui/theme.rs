use eframe::egui;

/// Exact Bengal Download Manager color palette derived from main branch theme_service
pub const CYAN_ACCENT: egui::Color32 = egui::Color32::from_rgb(0, 132, 209);  // #0084d1 (KDE Breeze / BDM Blue)
pub const CYAN_TEXT: egui::Color32 = egui::Color32::from_rgb(14, 165, 233);    // #0ea5e9 (Vivid Cyan Accent)
pub const DARK_BG: egui::Color32 = egui::Color32::from_rgb(32, 35, 38);        // #202326 (Window background in main)
pub const DARK_PANEL: egui::Color32 = egui::Color32::from_rgb(32, 35, 38);     // #202326 (Toolbar, status bar, details panel)
pub const DARK_BASE: egui::Color32 = egui::Color32::from_rgb(20, 22, 24);      // #141618 (Tree and Table base background in main)
pub const DARK_MID: egui::Color32 = egui::Color32::from_rgb(42, 46, 50);       // #2a2e32 (Borders, separators, hover in main)
pub const DARK_CARD: egui::Color32 = egui::Color32::from_rgb(20, 22, 24);      // #141618 (Sidebar card background in main)
pub const TEXT_PRIMARY: egui::Color32 = egui::Color32::from_rgb(239, 240, 241); // #eff0f1 (Window text in main)
pub const TEXT_SECONDARY: egui::Color32 = egui::Color32::from_rgb(154, 160, 166); // Placeholder / secondary text

/// Sets up OpenType tabular figures (`tnum`) and font sizes across egui.
pub fn configure_fonts(ctx: &egui::Context) {
    let fonts = egui::FontDefinitions::default();
    ctx.set_fonts(fonts);
}

/// Applies Bengal Download Manager's custom theme palette to egui.
pub fn apply_theme(ctx: &egui::Context, dark_mode: bool) {
    if dark_mode {
        let mut visuals = egui::Visuals::dark();
        visuals.panel_fill = DARK_BG;
        visuals.window_fill = DARK_PANEL;
        visuals.faint_bg_color = DARK_MID;
        visuals.extreme_bg_color = DARK_BASE;
        visuals.widgets.noninteractive.bg_fill = DARK_BG;
        visuals.widgets.inactive.bg_fill = DARK_MID;
        visuals.widgets.hovered.bg_fill = egui::Color32::from_rgb(52, 57, 63);
        visuals.widgets.active.bg_fill = CYAN_ACCENT;
        visuals.selection.bg_fill = CYAN_ACCENT;
        visuals.selection.stroke = egui::Stroke::new(1.0_f32, CYAN_ACCENT);

        visuals.window_corner_radius = egui::CornerRadius::same(6);
        visuals.widgets.noninteractive.corner_radius = egui::CornerRadius::same(4);
        visuals.widgets.inactive.corner_radius = egui::CornerRadius::same(4);
        visuals.widgets.hovered.corner_radius = egui::CornerRadius::same(4);
        visuals.widgets.active.corner_radius = egui::CornerRadius::same(4);

        ctx.set_visuals(visuals);
    } else {
        let mut visuals = egui::Visuals::light();
        visuals.panel_fill = egui::Color32::from_rgb(240, 240, 240);
        visuals.window_fill = egui::Color32::from_rgb(255, 255, 255);
        visuals.faint_bg_color = egui::Color32::from_rgb(245, 245, 245);
        visuals.extreme_bg_color = egui::Color32::from_rgb(255, 255, 255);
        visuals.widgets.noninteractive.bg_fill = egui::Color32::from_rgb(255, 255, 255);
        visuals.widgets.inactive.bg_fill = egui::Color32::from_rgb(238, 241, 244);
        visuals.widgets.hovered.bg_fill = egui::Color32::from_rgb(225, 230, 236);
        visuals.widgets.active.bg_fill = CYAN_ACCENT;
        visuals.selection.bg_fill = CYAN_ACCENT;
        visuals.selection.stroke = egui::Stroke::new(1.0_f32, CYAN_ACCENT);

        visuals.window_corner_radius = egui::CornerRadius::same(6);
        visuals.widgets.noninteractive.corner_radius = egui::CornerRadius::same(4);
        visuals.widgets.inactive.corner_radius = egui::CornerRadius::same(4);
        visuals.widgets.hovered.corner_radius = egui::CornerRadius::same(4);
        visuals.widgets.active.corner_radius = egui::CornerRadius::same(4);

        ctx.set_visuals(visuals);
    }
}

pub fn status_color(status: &str) -> egui::Color32 {
    match status.to_lowercase().as_str() {
        "downloading" => egui::Color32::from_rgb(52, 168, 83),  // Google Green
        "paused" => egui::Color32::from_rgb(251, 188, 4),      // Amber Yellow
        "completed" | "complete" => CYAN_TEXT,                 // Vivid Cyan
        "error" => egui::Color32::from_rgb(234, 67, 53),       // Danger Red
        _ => egui::Color32::from_rgb(154, 160, 166),           // Slate Muted / Queued
    }
}

pub fn status_icon(status: &str) -> &'static str {
    match status.to_lowercase().as_str() {
        "downloading" => "⬇",
        "paused" => "⏸",
        "completed" | "complete" => "✔",
        "error" => "✖",
        _ => "⏳",
    }
}
