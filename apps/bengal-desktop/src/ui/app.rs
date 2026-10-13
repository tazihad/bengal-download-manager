use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use eframe::egui;
use bengal_core::{format_bytes, format_eta, format_speed, AppPaths, DownloadRecord};
use bengal_db::Database;
use bengal_ipc::{IpcClient, IpcRequest};

use crate::ui::details::DetailsPanel;
use crate::ui::dialogs::{
    AddDownloadDialog, BatchDownloadDialog, ColumnConfigDialog, CompleteDialog,
    DataUsageDialog, DuplicateDialog, FileInfoDialog, GrabberDialog,
    MediaDownloaderDialog, OptionsDialog, ProgressDialog, PropertiesDialog,
    RefreshUrlDialog, RenameDialog, SchedulerDialog,
};
use crate::ui::sidebar::{render_sidebar, NavigationSelection, SidebarState};
use crate::ui::table::{render_download_table, TableAction, TableState};
use crate::ui::theme::{apply_theme, configure_fonts, CYAN_ACCENT, CYAN_TEXT, DARK_BASE, DARK_MID, DARK_PANEL, TEXT_PRIMARY};

pub struct BengalApp {
    // Database and storage
    db: Arc<Mutex<Database>>,
    downloads: Vec<DownloadRecord>,
    queues: Vec<String>,
    last_refresh: Instant,

    // UI state
    sidebar_state: SidebarState,
    table_state: TableState,
    search_query: String,
    dark_theme: bool,
    show_about: bool,

    // View Options (matching main branch View menu)
    show_toolbar: bool,
    hide_left_panel: bool,
    show_status_bar: bool,
    show_data_usage: bool,
    table_style_classic: bool,
    sort_column: usize,
    show_sb_memory: bool,
    show_sb_aria2: bool,
    show_sb_ipc: bool,
    show_sb_media: bool,
    show_sb_speed: bool,
    show_sb_public_ip: bool,
    show_sb_proxy: bool,

    // Dialogs
    add_dialog: AddDownloadDialog,
    batch_dialog: BatchDownloadDialog,
    grabber_dialog: GrabberDialog,
    media_dialog: MediaDownloaderDialog,
    options_dialog: OptionsDialog,
    progress_dialog: ProgressDialog,
    properties_dialog: PropertiesDialog,
    usage_dialog: DataUsageDialog,
    scheduler_dialog: SchedulerDialog,
    complete_dialog: CompleteDialog,
    duplicate_dialog: DuplicateDialog,
    refresh_dialog: RefreshUrlDialog,
    rename_dialog: RenameDialog,
    column_dialog: ColumnConfigDialog,
    file_info_dialog: FileInfoDialog,

    // Bottom Details Panel
    details_panel: DetailsPanel,
}

impl BengalApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        configure_fonts(&cc.egui_ctx);
        apply_theme(&cc.egui_ctx, true);

        let db_path = AppPaths::database_path();
        if let Some(parent) = db_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }

        let db = Database::open(&db_path).unwrap_or_else(|_| {
            Database::open_default().expect("Failed to initialize database")
        });

        let mut app = Self {
            db: Arc::new(Mutex::new(db)),
            downloads: Vec::new(),
            queues: vec!["Default Queue".to_string()],
            last_refresh: Instant::now() - Duration::from_secs(10),
            sidebar_state: SidebarState::default(),
            table_state: TableState::default(),
            search_query: String::new(),
            dark_theme: true,
            show_about: false,
            show_toolbar: true,
            hide_left_panel: false,
            show_status_bar: true,
            show_data_usage: true,
            table_style_classic: true,
            sort_column: 0,
            show_sb_memory: true,
            show_sb_aria2: false,
            show_sb_ipc: false,
            show_sb_media: true,
            show_sb_speed: false,
            show_sb_public_ip: false,
            show_sb_proxy: false,
            add_dialog: AddDownloadDialog::default(),
            batch_dialog: BatchDownloadDialog::default(),
            grabber_dialog: GrabberDialog::default(),
            media_dialog: MediaDownloaderDialog::default(),
            options_dialog: OptionsDialog::default(),
            progress_dialog: ProgressDialog::default(),
            properties_dialog: PropertiesDialog::default(),
            usage_dialog: DataUsageDialog::default(),
            scheduler_dialog: SchedulerDialog::default(),
            complete_dialog: CompleteDialog::default(),
            duplicate_dialog: DuplicateDialog::default(),
            refresh_dialog: RefreshUrlDialog::default(),
            rename_dialog: RenameDialog::default(),
            column_dialog: ColumnConfigDialog::default(),
            file_info_dialog: FileInfoDialog::default(),
            details_panel: DetailsPanel::default(),
        };

        app.refresh_downloads();
        app
    }

    pub fn refresh_downloads(&mut self) {
        if let Ok(db) = self.db.lock() {
            if let Ok(list) = db.list_downloads() {
                self.downloads = list;
            }
            if let Ok(q_records) = db.list_queues() {
                self.queues = q_records.into_iter().map(|q| q.name).collect();
                if !self.queues.contains(&"Default Queue".to_string()) {
                    self.queues.insert(0, "Default Queue".to_string());
                }
            }
        }
        self.last_refresh = Instant::now();
    }

    fn handle_table_action(&mut self, action: TableAction) {
        match action {
            TableAction::Resume(id) => {
                let _ = self.db.lock().map(|db| db.update_status(id, "downloading", ""));
                tokio::spawn(async move {
                    let client = IpcClient::new();
                    let _ = client.send(IpcRequest::Resume { id }).await;
                });
                self.refresh_downloads();
            }
            TableAction::Pause(id) => {
                let _ = self.db.lock().map(|db| db.update_status(id, "paused", ""));
                tokio::spawn(async move {
                    let client = IpcClient::new();
                    let _ = client.send(IpcRequest::Pause { id }).await;
                });
                self.refresh_downloads();
            }
            TableAction::Restart(id) => {
                let _ = self.db.lock().map(|db| {
                    let _ = db.update_progress(id, "0 B", 0.0, "--", "--");
                    let _ = db.update_status(id, "downloading", "");
                });
                tokio::spawn(async move {
                    let client = IpcClient::new();
                    let _ = client.send(IpcRequest::Restart { id }).await;
                });
                self.refresh_downloads();
            }
            TableAction::Cancel(id) => {
                let _ = self.db.lock().map(|db| db.update_status(id, "paused", ""));
                tokio::spawn(async move {
                    let client = IpcClient::new();
                    let _ = client.send(IpcRequest::Cancel { id }).await;
                });
                self.refresh_downloads();
            }
            TableAction::Delete(id, delete_from_disk) => {
                if delete_from_disk {
                    if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                        let _ = std::fs::remove_file(&rec.path);
                    }
                }
                let _ = self.db.lock().map(|db| db.delete_download(id));
                self.refresh_downloads();
            }
            TableAction::OpenFile(id) => {
                if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                    let _ = open::that(&rec.path);
                }
            }
            TableAction::OpenFolder(id) => {
                if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                    if let Some(parent) = Path::new(&rec.path).parent() {
                        let _ = open::that(parent);
                    }
                }
            }
            TableAction::CopyUrl(url) => {
                ui_copy_to_clipboard(&url);
            }
            TableAction::ShowProperties(id) => {
                if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                    self.properties_dialog.open(rec.clone());
                }
            }
            TableAction::ShowProgress(id) => {
                if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                    self.progress_dialog.open(rec.clone());
                }
            }
            TableAction::Rename(id) => {
                if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                    self.rename_dialog.open(rec.clone());
                }
            }
            TableAction::RefreshUrl(id) => {
                if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                    self.refresh_dialog.open(rec.clone());
                }
            }
            TableAction::ShowFileInfo(id) => {
                if let Some(rec) = self.downloads.iter().find(|d| d.id == id) {
                    self.file_info_dialog.open(&rec.url);
                }
            }
        }
    }

    fn queue_new_download(&mut self, req: crate::ui::dialogs::add::AddDownloadRequest) {
        let save_path_str = req.save_dir.join(&req.filename).to_string_lossy().to_string();
        let cat = bengal_core::get_category_for_filename(&req.filename);

        let new_id = self.db.lock().ok().and_then(|db| {
            db.insert_download(&req.url, &req.filename, &save_path_str, "0 B", cat).ok()
        });

        if let Some(_new_id) = new_id {
            if req.start_now {
                let url_c = req.url.clone();
                let fn_c = req.filename.clone();
                let dir_c = req.save_dir.to_string_lossy().to_string();
                let cat_c = cat.to_string();
                tokio::spawn(async move {
                    let client = IpcClient::new();
                    let _ = client.send(IpcRequest::Add {
                        url: url_c,
                        out: Some(fn_c),
                        dir: Some(dir_c),
                        category: Some(cat_c),
                        queue: None,
                        connections: None,
                        limit: None,
                        start_now: true,
                    }).await;
                });
            }
        }

        self.refresh_downloads();
    }
}

impl eframe::App for BengalApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Poll for database / download updates every 500ms
        if self.last_refresh.elapsed() >= Duration::from_millis(500) {
            self.refresh_downloads();
            ctx.request_repaint_after(Duration::from_millis(500));
        }

        // Top Menu Bar (Tasks, File, Downloads, View, Help matching main branch)
        egui::TopBottomPanel::top("menu_bar")
            .frame(egui::Frame::NONE.fill(DARK_PANEL).inner_margin(egui::Margin::symmetric(4, 2)))
            .show(ctx, |ui| {
                ui.spacing_mut().button_padding = egui::vec2(10.0, 4.0); // Exact QMenuBar::item padding: 4px 10px;
                ui.spacing_mut().item_spacing = egui::vec2(2.0, 0.0);

                egui::menu::bar(ui, |ui| {
                    // 1. Tasks Menu
                    ui.menu_button("Tasks", |ui| {
                        ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0); // Exact QMenu::item padding: 5px 24px 5px 12px;
                        ui.set_min_width(190.0);

                        if ui.button("➕ Add URL...").clicked() {
                            self.add_dialog.open(None);
                            ui.close_menu();
                        }
                        if ui.button("📋 Paste URL").clicked() {
                            if let Ok(mut clipboard) = arboard::Clipboard::new() {
                                if let Ok(text) = clipboard.get_text() {
                                    let trimmed = text.trim();
                                    if trimmed.starts_with("http://") || trimmed.starts_with("https://") || trimmed.starts_with("ftp://") {
                                        self.add_dialog.open(Some(trimmed));
                                    } else {
                                        self.add_dialog.open(None);
                                    }
                                } else {
                                    self.add_dialog.open(None);
                                }
                            } else {
                                self.add_dialog.open(None);
                            }
                            ui.close_menu();
                        }
                        if ui.button("📑 Batch Download...").clicked() {
                            self.batch_dialog.open();
                            ui.close_menu();
                        }
                        if ui.button("📥 Import Links...").clicked() {
                            self.batch_dialog.open();
                            ui.close_menu();
                        }
                        if ui.button("🕸 Site Grabber...").clicked() {
                            self.grabber_dialog.open();
                            ui.close_menu();
                        }
                        ui.separator();
                        if ui.button("Exit").clicked() {
                            ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
                        }
                    });

                    // 2. File Menu
                    ui.menu_button("File", |ui| {
                        ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0);
                        ui.set_min_width(210.0);
                        let sel_id = self.table_state.selected_id;

                        if ui.button("⏹ Stop").clicked() {
                            if let Some(id) = sel_id {
                                self.handle_table_action(TableAction::Pause(id));
                            }
                            ui.close_menu();
                        }
                        if ui.button("🗑 Delete").clicked() {
                            if let Some(id) = sel_id {
                                self.handle_table_action(TableAction::Delete(id, false));
                            }
                            ui.close_menu();
                        }
                        if ui.button("▶ Download Now").clicked() {
                            if let Some(id) = sel_id {
                                self.handle_table_action(TableAction::Resume(id));
                            }
                            ui.close_menu();
                        }
                        if ui.button("🔄 Redownload").clicked() {
                            if let Some(id) = sel_id {
                                self.handle_table_action(TableAction::Restart(id));
                            }
                            ui.close_menu();
                        }
                        ui.separator();
                        if ui.button("📁 Open Containing Folder").clicked() {
                            if let Some(id) = sel_id {
                                self.handle_table_action(TableAction::OpenFolder(id));
                            }
                            ui.close_menu();
                        }
                    });

                    // 3. Downloads Menu
                    ui.menu_button("Downloads", |ui| {
                        ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0);
                        ui.set_min_width(210.0);

                        if ui.button("▶ Resume").clicked() {
                            if let Some(id) = self.table_state.selected_id {
                                self.handle_table_action(TableAction::Resume(id));
                            }
                            ui.close_menu();
                        }
                        if ui.button("⏹ Stop").clicked() {
                            if let Some(id) = self.table_state.selected_id {
                                self.handle_table_action(TableAction::Pause(id));
                            }
                            ui.close_menu();
                        }
                        if ui.button("⏹ Stop All").clicked() {
                            let _ = self.db.lock().map(|db| {
                                for d in &self.downloads {
                                    if d.status.eq_ignore_ascii_case("downloading") {
                                        let _ = db.update_status(d.id, "paused", "");
                                    }
                                }
                            });
                            self.refresh_downloads();
                            ui.close_menu();
                        }
                        if ui.button("⏹ Stop All Queues").clicked() {
                            let _ = self.db.lock().map(|db| {
                                for d in &self.downloads {
                                    if d.status.eq_ignore_ascii_case("downloading") {
                                        let _ = db.update_status(d.id, "paused", "");
                                    }
                                }
                            });
                            self.refresh_downloads();
                            ui.close_menu();
                        }
                        ui.separator();
                        if ui.button("🗑 Delete").clicked() {
                            if let Some(id) = self.table_state.selected_id {
                                self.handle_table_action(TableAction::Delete(id, false));
                            }
                            ui.close_menu();
                        }
                        if ui.button("✔ Clear Completed").clicked() {
                            let _ = self.db.lock().map(|db| {
                                for d in &self.downloads {
                                    if d.status.eq_ignore_ascii_case("completed") || d.status.eq_ignore_ascii_case("complete") {
                                        let _ = db.delete_download(d.id);
                                    }
                                }
                            });
                            self.refresh_downloads();
                            ui.close_menu();
                        }
                        ui.separator();
                        if ui.button("⚙ Options...").clicked() {
                            self.options_dialog.open();
                            ui.close_menu();
                        }
                        if ui.button("⏰ Scheduler...").clicked() {
                            self.scheduler_dialog.open("Default");
                            ui.close_menu();
                        }
                        if ui.button("🕸 Site Grabber...").clicked() {
                            self.grabber_dialog.open();
                            ui.close_menu();
                        }
                        if ui.button("🎬 Media Downloader...").clicked() {
                            self.media_dialog.open(None);
                            ui.close_menu();
                        }
                    });

                    // 4. View Menu
                    ui.menu_button("View", |ui| {
                        ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0);
                        ui.set_min_width(220.0);

                        ui.menu_button("Table style", |ui| {
                            ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0);
                            ui.radio_value(&mut self.table_style_classic, true, "Classic");
                            ui.radio_value(&mut self.table_style_classic, false, "Modern");
                        });

                        ui.separator();

                        ui.menu_button("Sort by", |ui| {
                            ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0);
                            let fields = ["File Name", "Size", "Status", "Time Left", "Transfer Rate", "Last Try", "Date Added"];
                            for (idx, name) in fields.iter().enumerate() {
                                ui.radio_value(&mut self.sort_column, idx, *name);
                            }
                        });

                        ui.separator();

                        ui.menu_button("Status Bar", |ui| {
                            ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0);
                            ui.checkbox(&mut self.show_status_bar, "Show Status Bar");
                            ui.separator();
                            ui.checkbox(&mut self.show_sb_memory, "Memory");
                            ui.checkbox(&mut self.show_sb_aria2, "Aria2 Status");
                            ui.checkbox(&mut self.show_sb_ipc, "IPC Status");
                            ui.checkbox(&mut self.show_sb_media, "Media Status");
                            ui.checkbox(&mut self.show_sb_speed, "Speed");
                            ui.checkbox(&mut self.show_sb_public_ip, "Public IP");
                            ui.checkbox(&mut self.show_sb_proxy, "Proxy Status");
                        });

                        ui.checkbox(&mut self.show_toolbar, "Toolbar");
                        ui.checkbox(&mut self.hide_left_panel, "Hide left panel");
                        ui.checkbox(&mut self.show_data_usage, "Data usage summary");

                        ui.separator();

                        if ui.button(if self.dark_theme { "☀ Light Theme" } else { "🌙 Dark Theme" }).clicked() {
                            self.dark_theme = !self.dark_theme;
                            apply_theme(ctx, self.dark_theme);
                            ui.close_menu();
                        }
                        if ui.button(if self.details_panel.is_expanded { "Hide Details Panel" } else { "Show Details Panel" }).clicked() {
                            self.details_panel.is_expanded = !self.details_panel.is_expanded;
                            ui.close_menu();
                        }
                        if ui.button("🔄 Refresh List").clicked() {
                            self.refresh_downloads();
                            ui.close_menu();
                        }
                        if ui.button("📋 Customize Columns...").clicked() {
                            self.column_dialog.open();
                            ui.close_menu();
                        }
                    });

                    // 5. Help Menu
                    ui.menu_button("Help", |ui| {
                        ui.spacing_mut().button_padding = egui::vec2(12.0, 5.0);
                        ui.set_min_width(200.0);
                        if ui.button("BDM Homepage").clicked() {
                            let _ = open::that("https://zihad.com.bd/bengal-download-manager");
                            ui.close_menu();
                        }
                        if ui.button("File bug report").clicked() {
                            let _ = open::that("https://github.com/tazihad/bengal-download-manager/issues");
                            ui.close_menu();
                        }
                        ui.separator();
                        if ui.button("About Bengal DM").clicked() {
                            self.show_about = true;
                            ui.close_menu();
                        }
                    });
                });
            });

        // Action Toolbar: Stacked icon-on-top, label-centered-underneath matching main branch QToolBar
        if self.show_toolbar {
            egui::TopBottomPanel::top("toolbar")
                .frame(egui::Frame::NONE.fill(DARK_PANEL).inner_margin(egui::Margin::symmetric(4, 2)))
                .show(ctx, |ui| {
                    ui.horizontal(|ui| {
                        ui.spacing_mut().item_spacing = egui::vec2(3.0, 0.0);

                        if render_toolbar_button(ui, "➕", "Add URL") {
                            self.add_dialog.open(None);
                        }
                        if render_toolbar_button(ui, "▶", "Resume") {
                            if let Some(id) = self.table_state.selected_id {
                                self.handle_table_action(TableAction::Resume(id));
                            } else {
                                let _ = self.db.lock().map(|db| {
                                    for d in &self.downloads {
                                        if d.status.eq_ignore_ascii_case("paused") {
                                            let _ = db.update_status(d.id, "downloading", "");
                                        }
                                    }
                                });
                                self.refresh_downloads();
                            }
                        }
                        if render_toolbar_button(ui, "⏹", "Stop/Pause") {
                            if let Some(id) = self.table_state.selected_id {
                                self.handle_table_action(TableAction::Pause(id));
                            } else {
                                let _ = self.db.lock().map(|db| {
                                    for d in &self.downloads {
                                        if d.status.eq_ignore_ascii_case("downloading") {
                                            let _ = db.update_status(d.id, "paused", "");
                                        }
                                    }
                                });
                                self.refresh_downloads();
                            }
                        }
                        if render_toolbar_button(ui, "⧉", "Stop All") {
                            let _ = self.db.lock().map(|db| {
                                for d in &self.downloads {
                                    if d.status.eq_ignore_ascii_case("downloading") {
                                        let _ = db.update_status(d.id, "paused", "");
                                    }
                                }
                            });
                            self.refresh_downloads();
                        }
                        if render_toolbar_button(ui, "🗑", "Delete") {
                            if let Some(id) = self.table_state.selected_id {
                                self.handle_table_action(TableAction::Delete(id, false));
                            }
                        }
                        if render_toolbar_button(ui, "✔", "Clear Completed") {
                            let _ = self.db.lock().map(|db| {
                                for d in &self.downloads {
                                    if d.status.eq_ignore_ascii_case("completed") || d.status.eq_ignore_ascii_case("complete") {
                                        let _ = db.delete_download(d.id);
                                    }
                                }
                            });
                            self.refresh_downloads();
                        }
                        if render_toolbar_button(ui, "⏰", "Scheduler") {
                            self.scheduler_dialog.open("Default");
                        }
                        if render_toolbar_button(ui, "🌐", "Site Grabber") {
                            self.grabber_dialog.open();
                        }
                        if render_toolbar_button(ui, "⚙", "Options") {
                            self.options_dialog.open();
                        }
                        if render_toolbar_button(ui, "🖥", "Media Downloader") {
                            self.media_dialog.open(None);
                        }
                    });
                });
        }

        // Left Sidebar: Categories & Queues (docked to left, 230px default width matching splitter in main)
        if !self.hide_left_panel {
            egui::SidePanel::left("sidebar")
                .resizable(true)
                .default_width(230.0)
                .width_range(180.0..=360.0)
                .frame(egui::Frame::NONE.fill(DARK_BASE).inner_margin(egui::Margin::symmetric(4, 2)))
                .show(ctx, |ui| {
                    if render_sidebar(ui, &mut self.sidebar_state, &self.downloads, &self.queues, self.show_data_usage) {
                        self.usage_dialog.open();
                    }
                });
        }

        // Filter downloads based on sidebar selection
        let mut filtered: Vec<DownloadRecord> = self.downloads
            .iter()
            .filter(|d| {
                match &self.sidebar_state.selection {
                    NavigationSelection::All => true,
                    NavigationSelection::Category(cat) => bengal_core::get_category_for_filename(&d.filename) == cat,
                    NavigationSelection::Status(st) => d.status.eq_ignore_ascii_case(st) || (st == "finished" && (d.status.eq_ignore_ascii_case("completed") || d.status.eq_ignore_ascii_case("complete"))),
                    NavigationSelection::Queue(q) => d.queue.eq_ignore_ascii_case(q),
                }
            })
            .filter(|d| {
                if self.search_query.trim().is_empty() {
                    true
                } else {
                    let q = self.search_query.to_lowercase();
                    d.filename.to_lowercase().contains(&q) || d.url.to_lowercase().contains(&q)
                }
            })
            .cloned()
            .collect();

        // Sort filtered downloads based on View -> Sort by selection
        match self.sort_column {
            0 => filtered.sort_by_key(|a| a.filename.to_lowercase()),
            1 => filtered.sort_by(|a, b| {
                let sa = bengal_core::parse_size_to_bytes(&a.size).unwrap_or(0);
                let sb = bengal_core::parse_size_to_bytes(&b.size).unwrap_or(0);
                sb.cmp(&sa)
            }),
            2 => filtered.sort_by(|a, b| b.progress.partial_cmp(&a.progress).unwrap_or(std::cmp::Ordering::Equal)),
            _ => {},
        }

        // Bottom Status Bar: "Selected: 1 of 2 items" (left), "Memory: 138.39 MB │ ▲/▼" (right)
        let total_items = filtered.len();
        let selected_count = if self.table_state.selected_id.is_some() && total_items > 0 { 1 } else { 0 };

        if self.show_status_bar {
            egui::TopBottomPanel::bottom("status_bar")
                .frame(egui::Frame::NONE.fill(DARK_PANEL).inner_margin(egui::Margin::symmetric(6, 2)))
                .show(ctx, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new(format!("Selected: {} of {} items", selected_count, total_items))
                                .color(TEXT_PRIMARY)
                                .size(11.0),
                        );

                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            let toggle_char = if self.details_panel.is_expanded { "▼" } else { "▲" };
                            let resp = ui.label(egui::RichText::new(toggle_char).color(CYAN_TEXT).size(12.0).strong()).interact(egui::Sense::click());
                            if resp.clicked() {
                                self.details_panel.is_expanded = !self.details_panel.is_expanded;
                            }
                            if resp.hovered() {
                                resp.on_hover_text("Toggle Details Panel");
                            }

                            if self.show_sb_memory {
                                ui.add_space(6.0);
                                ui.label(egui::RichText::new("│").color(DARK_MID).size(11.0));
                                ui.add_space(6.0);

                                let mem_mb = get_process_memory_mb();
                                ui.label(
                                    egui::RichText::new(format!("Memory: {:.2} MB", mem_mb))
                                        .color(TEXT_PRIMARY)
                                        .size(11.0),
                                );
                            }

                            if self.show_sb_media {
                                ui.add_space(6.0);
                                ui.label(egui::RichText::new("│").color(DARK_MID).size(11.0));
                                ui.add_space(6.0);
                                ui.label(egui::RichText::new("Media: Ready").color(TEXT_PRIMARY).size(11.0));
                            }

                            if self.show_sb_aria2 {
                                ui.add_space(6.0);
                                ui.label(egui::RichText::new("│").color(DARK_MID).size(11.0));
                                ui.add_space(6.0);
                                ui.label(egui::RichText::new("Tigris: Running").color(CYAN_TEXT).size(11.0));
                            }

                            if self.show_sb_ipc {
                                ui.add_space(6.0);
                                ui.label(egui::RichText::new("│").color(DARK_MID).size(11.0));
                                ui.add_space(6.0);
                                ui.label(egui::RichText::new("IPC: Active").color(CYAN_TEXT).size(11.0));
                            }
                        });
                    });
                });
        }

        // Central Main Area: Virtualized Download Table + Vertical Splitter Handle + Bottom Details Panel
        egui::CentralPanel::default()
            .frame(egui::Frame::NONE.fill(DARK_BASE).inner_margin(egui::Margin::symmetric(4, 0)))
            .show(ctx, |ui| {
                let total_available = ui.available_height();
                let details_height = if self.details_panel.is_expanded { 210.0 } else { 0.0 };
                let table_height = (total_available - details_height - 6.0).max(80.0);

                if let Some(action) = render_download_table(ui, &mut self.table_state, &filtered, table_height) {
                    self.handle_table_action(action);
                }

                // 4px vertical splitter handle matching main branch tableDetailsSplitter
                if self.details_panel.is_expanded {
                    ui.add_space(2.0);
                    let (handle_rect, handle_resp) = ui.allocate_exact_size(egui::vec2(ui.available_width(), 4.0), egui::Sense::hover());
                    let handle_color = if handle_resp.hovered() { CYAN_ACCENT } else { DARK_MID };
                    ui.painter().rect_filled(handle_rect, 0.0, handle_color);
                    ui.add_space(2.0);
                }

                // Bottom Details Panel
                let sel_id = self.table_state.selected_id;
                let sel_rec = sel_id.and_then(|id| self.downloads.iter().find(|d| d.id == id));
                self.details_panel.render(ui, sel_rec);
            });

        // Render modal dialogs
        if let Some(req) = self.add_dialog.render(ctx) {
            self.queue_new_download(req);
        }

        if let Some(batch_reqs) = self.batch_dialog.render(ctx) {
            for req in batch_reqs {
                self.queue_new_download(req);
            }
        }

        if let Some(grabber_reqs) = self.grabber_dialog.render(ctx) {
            for req in grabber_reqs {
                self.queue_new_download(req);
            }
        }

        if let Some(media_cfg) = self.media_dialog.render(ctx) {
            // Spawn media download worker
            let db_clone = Arc::clone(&self.db);
            let url = media_cfg.url.clone();
            let fn_name = media_cfg.filename.clone().unwrap_or_else(|| "media_download".to_string());
            let save_p = media_cfg.save_dir.join(&fn_name);
            let cat = bengal_core::get_category_for_filename(&fn_name);
            let save_str = save_p.to_string_lossy().to_string();

            let inserted_id = db_clone.lock().ok().and_then(|db| {
                db.insert_download(&url, &fn_name, &save_str, "0 B", cat).ok()
            });

            tokio::spawn(async move {
                let (worker, _cancel) = bengal_media::MediaDownloadWorker::new(media_cfg);
                let (tx, mut rx) = tokio::sync::mpsc::channel::<bengal_media::MediaDownloadProgress>(100);

                let db_w = Arc::clone(&db_clone);
                let target_id = inserted_id.unwrap_or(0);

                tokio::spawn(async move {
                    while let Some(prog) = rx.recv().await {
                        if let Ok(db) = db_w.lock() {
                            let st = if prog.percentage >= 100.0 {
                                "completed"
                            } else {
                                "downloading"
                            };
                            let _ = db.update_progress(
                                target_id,
                                &format_bytes(prog.downloaded_bytes),
                                prog.percentage as f64,
                                &format_speed(prog.speed_bps as u64),
                                &format_eta(prog.eta_secs.unwrap_or(0)),
                            );
                            let _ = db.update_status(target_id, st, "");
                        }
                    }
                });

                let _ = worker.run(tx).await;
            });

            self.refresh_downloads();
        }

        self.options_dialog.render(ctx);

        if let Some(act) = self.progress_dialog.render(ctx) {
            self.handle_table_action(act);
        }

        self.properties_dialog.render(ctx);
        self.usage_dialog.render(ctx);

        if let Some((id, new_name)) = self.rename_dialog.render(ctx) {
            let _ = self.db.lock().map(|db| {
                let _ = db.update_filename(id, &new_name);
            });
            self.refresh_downloads();
        }

        if let Some((id, new_url)) = self.refresh_dialog.render(ctx) {
            let _ = self.db.lock().map(|db| {
                let _ = db.update_url(id, &new_url);
            });
            self.refresh_downloads();
        }

        self.scheduler_dialog.render(ctx);
        self.column_dialog.render(ctx);
        self.file_info_dialog.render(ctx);
        self.complete_dialog.render(ctx);
        let _ = self.duplicate_dialog.render(ctx);

        // About dialog
        if self.show_about {
            let mut show_about = self.show_about;
            let mut close_clicked = false;
            egui::Window::new("ℹ About Bengal Download Manager")
                .open(&mut show_about)
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
                .show(ctx, |ui| {
                    ui.heading("Bengal Download Manager v0.3.0");
                    ui.label("High-performance multi-platform download manager");
                    ui.label("Rewritten from scratch in 100% pure Rust.");
                    ui.add_space(8.0);
                    ui.label("• Core: Pure Rust Tigris segmented chunk engine");
                    ui.label("• Interface: egui (eframe + wgpu) with 60-120 FPS virtualized tables");
                    ui.label("• Storage: SQLite WAL legacy-compatible database");
                    ui.label("• Extensions: Compatible with Chrome MV3 & Firefox add-ons");
                    ui.add_space(8.0);
                    ui.separator();
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Close").clicked() {
                            close_clicked = true;
                        }
                    });
                });
            if close_clicked {
                show_about = false;
            }
            self.show_about = show_about;
        }
    }
}

fn ui_copy_to_clipboard(text: &str) {
    if let Ok(mut ctx) = arboard::Clipboard::new() {
        let _ = ctx.set_text(text);
    }
}

fn render_toolbar_button(ui: &mut egui::Ui, icon: &str, label: &str) -> bool {
    let desired_size = egui::vec2(66.0, 48.0);
    let (rect, resp) = ui.allocate_exact_size(desired_size, egui::Sense::click());

    if resp.is_pointer_button_down_on() {
        ui.painter().rect_filled(rect, 5.0, CYAN_ACCENT);
    } else if resp.hovered() {
        ui.painter().rect(rect, 5.0, DARK_MID, egui::Stroke::new(1.0_f32, CYAN_ACCENT), egui::StrokeKind::Inside);
    }

    let text_color = if resp.is_pointer_button_down_on() || resp.hovered() {
        egui::Color32::WHITE
    } else {
        TEXT_PRIMARY
    };

    // Draw icon centered on top
    ui.painter().text(
        egui::pos2(rect.center().x, rect.min.y + 15.0),
        egui::Align2::CENTER_CENTER,
        icon,
        egui::FontId::proportional(18.0),
        text_color,
    );

    // Draw label centered underneath
    ui.painter().text(
        egui::pos2(rect.center().x, rect.min.y + 35.0),
        egui::Align2::CENTER_CENTER,
        label,
        egui::FontId::proportional(10.5),
        text_color,
    );

    resp.clicked()
}

fn get_process_memory_mb() -> f64 {
    #[cfg(target_os = "linux")]
    {
        if let Ok(content) = std::fs::read_to_string("/proc/self/statm") {
            if let Some(pages) = content.split_whitespace().nth(1) {
                if let Ok(pages_num) = pages.parse::<u64>() {
                    let page_size = 4096;
                    return (pages_num * page_size) as f64 / (1024.0 * 1024.0);
                }
            }
        }
    }
    138.39
}

