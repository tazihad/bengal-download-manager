use eframe::egui;
use egui_extras::{Column, TableBuilder};
use bengal_core::DownloadRecord;
use crate::ui::theme::TEXT_PRIMARY;

#[derive(Debug, Clone)]
pub enum TableAction {
    Resume(i64),
    Pause(i64),
    Restart(i64),
    Cancel(i64),
    Delete(i64, bool), // (id, delete_from_disk)
    OpenFile(i64),
    OpenFolder(i64),
    CopyUrl(String),
    Rename(i64),
    RefreshUrl(i64),
    ShowFileInfo(i64),
    ShowProperties(i64),
    ShowProgress(i64),
}

#[derive(Debug, Default)]
pub struct TableState {
    pub selected_id: Option<i64>,
}

pub fn render_download_table(
    ui: &mut egui::Ui,
    state: &mut TableState,
    records: &[DownloadRecord],
    table_height: f32,
) -> Option<TableAction> {
    let mut requested_action: Option<TableAction> = None;

    if state.selected_id.is_none() && !records.is_empty() {
        state.selected_id = Some(records[0].id);
    }

    let table = TableBuilder::new(ui)
        .striped(true)
        .resizable(true)
        .cell_layout(egui::Layout::left_to_right(egui::Align::Center))
        .column(Column::initial(260.0).at_least(180.0))                  // File Name
        .column(Column::initial(105.0).at_least(80.0))                   // Size
        .column(Column::initial(90.0).at_least(70.0))                    // Status
        .column(Column::initial(85.0).at_least(70.0))                    // Time Left
        .column(Column::initial(115.0).at_least(90.0))                   // Transfer Rate
        .column(Column::initial(90.0).at_least(70.0))                    // Last Try
        .column(Column::initial(90.0).at_least(70.0))                    // Date Added
        .min_scrolled_height(0.0)
        .max_scroll_height(table_height);

    table
        .header(26.0, |mut header| {
            header.col(|ui| { ui.label(egui::RichText::new("File Name").color(TEXT_PRIMARY).size(11.5)); });
            header.col(|ui| { ui.label(egui::RichText::new("Size").color(TEXT_PRIMARY).size(11.5)); });
            header.col(|ui| { ui.label(egui::RichText::new("Status").color(TEXT_PRIMARY).size(11.5)); });
            header.col(|ui| { ui.label(egui::RichText::new("Time Left").color(TEXT_PRIMARY).size(11.5)); });
            header.col(|ui| { ui.label(egui::RichText::new("Transfer Rate").color(TEXT_PRIMARY).size(11.5)); });
            header.col(|ui| { ui.label(egui::RichText::new("Last Try").color(TEXT_PRIMARY).size(11.5)); });
            header.col(|ui| { ui.label(egui::RichText::new("Date Added").color(TEXT_PRIMARY).size(11.5)); });
        })
        .body(|body| {
            let row_height = 28.0;
            let num_rows = records.len();

            body.rows(row_height, num_rows, |mut row| {
                let rec = &records[row.index()];
                let is_selected = state.selected_id == Some(rec.id);
                row.set_selected(is_selected);

                let is_downloading = rec.status.eq_ignore_ascii_case("downloading");
                let is_complete = rec.status.eq_ignore_ascii_case("completed") || rec.status.eq_ignore_ascii_case("complete");
                let is_paused = rec.status.eq_ignore_ascii_case("paused");
                let is_error = rec.status.eq_ignore_ascii_case("error");

                let text_color = if is_selected { egui::Color32::WHITE } else { TEXT_PRIMARY };
                let file_icon = get_file_type_icon(&rec.filename);

                // Column 1: File Name
                row.col(|ui| {
                    let label_text = format!("{} {}", file_icon, rec.filename);
                    let resp = ui.label(egui::RichText::new(&label_text).color(text_color).strong())
                        .interact(egui::Sense::click());

                    if resp.clicked() {
                        state.selected_id = Some(rec.id);
                    }
                    if resp.double_clicked() {
                        if is_complete {
                            requested_action = Some(TableAction::OpenFile(rec.id));
                        } else {
                            requested_action = Some(TableAction::ShowProgress(rec.id));
                        }
                    }

                    resp.context_menu(|ui| {
                        if is_downloading && ui.button("⏸ Pause").clicked() {
                            requested_action = Some(TableAction::Pause(rec.id));
                            ui.close_menu();
                        } else if (is_paused || is_error) && ui.button("▶ Resume").clicked() {
                            requested_action = Some(TableAction::Resume(rec.id));
                            ui.close_menu();
                        }

                        if ui.button("🔄 Restart").clicked() {
                            requested_action = Some(TableAction::Restart(rec.id));
                            ui.close_menu();
                        }

                        if ui.button("⏹ Cancel").clicked() {
                            requested_action = Some(TableAction::Cancel(rec.id));
                            ui.close_menu();
                        }

                        ui.separator();

                        if is_complete && ui.button("▶ Open File").clicked() {
                            requested_action = Some(TableAction::OpenFile(rec.id));
                            ui.close_menu();
                        }

                        if ui.button("📁 Open Containing Folder").clicked() {
                            requested_action = Some(TableAction::OpenFolder(rec.id));
                            ui.close_menu();
                        }

                        if ui.button("🔗 Copy Download Link").clicked() {
                            requested_action = Some(TableAction::CopyUrl(rec.url.clone()));
                            ui.close_menu();
                        }

                        ui.separator();

                        if ui.button("✏ Rename...").clicked() {
                            requested_action = Some(TableAction::Rename(rec.id));
                            ui.close_menu();
                        }

                        if ui.button("🔄 Refresh Download Link...").clicked() {
                            requested_action = Some(TableAction::RefreshUrl(rec.id));
                            ui.close_menu();
                        }

                        ui.separator();

                        if ui.button("🗑 Delete from List").clicked() {
                            requested_action = Some(TableAction::Delete(rec.id, false));
                            ui.close_menu();
                        }

                        if ui.button("❌ Delete File from Disk").clicked() {
                            requested_action = Some(TableAction::Delete(rec.id, true));
                            ui.close_menu();
                        }

                        ui.separator();

                        if ui.button("ℹ Properties").clicked() {
                            requested_action = Some(TableAction::ShowProperties(rec.id));
                            ui.close_menu();
                        }
                    });
                });

                // Column 2: Size
                row.col(|ui| {
                    let size_str = if !rec.size.is_empty() {
                        rec.size.clone()
                    } else {
                        rec.downloaded.clone()
                    };
                    let resp = ui.label(egui::RichText::new(&size_str).color(text_color).strong().monospace())
                        .interact(egui::Sense::click());
                    if resp.clicked() {
                        state.selected_id = Some(rec.id);
                    }
                });

                // Column 3: Status
                row.col(|ui| {
                    let status_str = if is_complete {
                        "100.00%".to_string()
                    } else if rec.progress > 0.0 || is_downloading || is_paused {
                        format!("{:.2}%", rec.progress)
                    } else if is_error {
                        "Error".to_string()
                    } else {
                        "Queued".to_string()
                    };
                    let resp = ui.label(egui::RichText::new(&status_str).color(text_color).strong().monospace())
                        .interact(egui::Sense::click());
                    if resp.clicked() {
                        state.selected_id = Some(rec.id);
                    }
                });

                // Column 4: Time Left
                row.col(|ui| {
                    let time_str = if !rec.eta.is_empty() {
                        rec.eta.clone()
                    } else if is_complete {
                        "--".to_string()
                    } else {
                        "1 min".to_string()
                    };
                    let resp = ui.label(egui::RichText::new(&time_str).color(text_color).strong().monospace())
                        .interact(egui::Sense::click());
                    if resp.clicked() {
                        state.selected_id = Some(rec.id);
                    }
                });

                // Column 5: Transfer Rate
                row.col(|ui| {
                    let spd_text = if !rec.speed.is_empty() {
                        rec.speed.clone()
                    } else if is_complete {
                        "--".to_string()
                    } else {
                        "1.38 MB/s".to_string()
                    };
                    let resp = ui.label(egui::RichText::new(&spd_text).color(text_color).strong().monospace())
                        .interact(egui::Sense::click());
                    if resp.clicked() {
                        state.selected_id = Some(rec.id);
                    }
                });

                // Column 6: Last Try
                row.col(|ui| {
                    let mut text = egui::RichText::new("Just now").color(text_color);
                    if is_downloading || is_selected { text = text.strong(); }
                    let resp = ui.label(text).interact(egui::Sense::click());
                    if resp.clicked() {
                        state.selected_id = Some(rec.id);
                    }
                });

                // Column 7: Date Added
                row.col(|ui| {
                    let mut text = egui::RichText::new("Just now").color(text_color);
                    if is_downloading || is_selected { text = text.strong(); }
                    let resp = ui.label(text).interact(egui::Sense::click());
                    if resp.clicked() {
                        state.selected_id = Some(rec.id);
                    }
                });
            });
        });

    requested_action
}

fn get_file_type_icon(filename: &str) -> &'static str {
    let lower = filename.to_lowercase();
    if lower.ends_with(".tar.xz") || lower.ends_with(".tar.gz") || lower.ends_with(".zip") || lower.ends_with(".7z") || lower.ends_with(".rar") {
        "📦"
    } else if lower.ends_with(".appimage") || lower.ends_with(".exe") || lower.ends_with(".deb") || lower.ends_with(".rpm") {
        "↗"
    } else if lower.ends_with(".mp4") || lower.ends_with(".mkv") || lower.ends_with(".webm") || lower.ends_with(".avi") {
        "🎬"
    } else if lower.ends_with(".mp3") || lower.ends_with(".flac") || lower.ends_with(".wav") || lower.ends_with(".m4a") {
        "🎵"
    } else {
        "📄"
    }
}
