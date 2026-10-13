pub mod app;
pub mod details;
pub mod dialogs;
pub mod sidebar;
pub mod table;
pub mod theme;

pub use app::BengalApp;

pub fn copy_to_clipboard(text: &str) {
    if let Ok(mut ctx) = arboard::Clipboard::new() {
        let _ = ctx.set_text(text);
    }
}
