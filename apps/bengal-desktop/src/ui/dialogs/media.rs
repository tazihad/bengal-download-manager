use std::path::PathBuf;
use eframe::egui;
use tokio::sync::mpsc;
use bengal_core::format_bytes;
use bengal_media::{
    ExtractorOptions, MediaDownloadConfig, MediaExtractionResult, MediaExtractor,
};

pub struct MediaDownloaderDialog {
    pub is_open: bool,
    pub url: String,
    pub is_analyzing: bool,
    pub status_text: String,
    pub extraction_result: Option<MediaExtractionResult>,
    pub selected_format_id: Option<String>,
    pub is_audio_only: bool,
    pub audio_format: String,
    pub video_container: String,
    pub embed_thumbnail: bool,
    pub save_dir: PathBuf,

    // Async extraction receiver
    pub extract_rx: Option<mpsc::Receiver<anyhow::Result<MediaExtractionResult>>>,
}

impl Default for MediaDownloaderDialog {
    fn default() -> Self {
        Self {
            is_open: false,
            url: String::new(),
            is_analyzing: false,
            status_text: "Enter video or audio URL and click Analyze".to_string(),
            extraction_result: None,
            selected_format_id: None,
            is_audio_only: false,
            audio_format: "mp3".to_string(),
            video_container: "mp4".to_string(),
            embed_thumbnail: true,
            save_dir: bengal_core::AppPaths::default_download_dir(),
            extract_rx: None,
        }
    }
}

impl MediaDownloaderDialog {
    pub fn open(&mut self, prefill_url: Option<&str>) {
        self.is_open = true;
        if let Some(u) = prefill_url {
            self.url = u.to_string();
        }
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    pub fn analyze(&mut self) {
        if self.url.trim().is_empty() {
            self.status_text = "Please enter a valid URL".to_string();
            return;
        }

        self.is_analyzing = true;
        self.status_text = "Analyzing media metadata with yt-dlp...".to_string();
        self.extraction_result = None;
        self.selected_format_id = None;

        let opts = ExtractorOptions {
            url: self.url.trim().to_string(),
            cookies_browser: None,
            cookies_file: None,
            referrer: None,
            user_agent: None,
            cookies: None,
            no_playlist: false,
            playlist_start: None,
            playlist_end: Some(50),
            youtube_client: None,
            pot_enabled: true,
        };

        let (tx, rx) = mpsc::channel(1);
        self.extract_rx = Some(rx);

        tokio::spawn(async move {
            let res = MediaExtractor::extract(&opts).await;
            let _ = tx.send(res).await;
        });
    }

    pub fn poll_events(&mut self) {
        if let Some(rx) = &mut self.extract_rx {
            if let Ok(res) = rx.try_recv() {
                self.is_analyzing = false;
                match res {
                    Ok(result) => {
                        match &result {
                            MediaExtractionResult::Single(info) => {
                                self.status_text = format!("Found: {}", info.title);
                                if let Some(best) = info.formats.first() {
                                    self.selected_format_id = Some(best.format_id.clone());
                                }
                            }
                            MediaExtractionResult::Playlist(pl) => {
                                self.status_text = format!("Playlist: {} ({} items)", pl.title, pl.total_items);
                            }
                        }
                        self.extraction_result = Some(result);
                    }
                    Err(e) => {
                        self.status_text = format!("Analysis failed: {}", e);
                    }
                }
            }
        }
    }

    pub fn render(&mut self, ctx: &egui::Context) -> Option<MediaDownloadConfig> {
        if !self.is_open {
            return None;
        }

        self.poll_events();

        let mut start_config = None;
        let mut is_open = self.is_open;

        egui::Window::new("🎬 Media Downloader (yt-dlp Engine)")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(true)
            .default_width(700.0)
            .default_height(560.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.add_space(4.0);

                // URL row and Analyze button
                ui.horizontal(|ui| {
                    ui.label("Media URL:");
                    ui.add(egui::TextEdit::singleline(&mut self.url).desired_width(450.0));

                    if ui.add_enabled(!self.is_analyzing, egui::Button::new("Analyze")).clicked() {
                        self.analyze();
                    }
                });

                ui.add_space(4.0);
                ui.strong(&self.status_text);
                ui.add_space(8.0);
                ui.separator();

                // Extraction Result Area
                if let Some(res) = &self.extraction_result {
                    match res {
                        MediaExtractionResult::Single(info) => {
                            ui.heading(&info.title);
                            ui.label(format!("Uploader: {} | Duration: {:.0}s", info.uploader, info.duration));

                            ui.add_space(6.0);
                            ui.horizontal(|ui| {
                                ui.checkbox(&mut self.is_audio_only, "Extract Audio Only");

                                if self.is_audio_only {
                                    ui.label("Format:");
                                    egui::ComboBox::from_id_salt("audio_fmt")
                                        .selected_text(&self.audio_format)
                                        .show_ui(ui, |ui| {
                                            ui.selectable_value(&mut self.audio_format, "mp3".to_string(), "MP3");
                                            ui.selectable_value(&mut self.audio_format, "m4a".to_string(), "M4A (AAC)");
                                            ui.selectable_value(&mut self.audio_format, "flac".to_string(), "FLAC");
                                            ui.selectable_value(&mut self.audio_format, "opus".to_string(), "Opus");
                                        });
                                } else {
                                    ui.label("Container:");
                                    egui::ComboBox::from_id_salt("video_fmt")
                                        .selected_text(&self.video_container)
                                        .show_ui(ui, |ui| {
                                            ui.selectable_value(&mut self.video_container, "mp4".to_string(), "MP4");
                                            ui.selectable_value(&mut self.video_container, "mkv".to_string(), "MKV");
                                            ui.selectable_value(&mut self.video_container, "webm".to_string(), "WebM");
                                        });
                                }

                                ui.checkbox(&mut self.embed_thumbnail, "Embed Thumbnail");
                            });

                            ui.add_space(6.0);
                            ui.label("Available Streams & Formats:");

                            // Formats table
                            egui::ScrollArea::vertical()
                                .max_height(200.0)
                                .show(ui, |ui| {
                                    for fmt in &info.formats {
                                        let is_sel = self.selected_format_id.as_deref() == Some(&fmt.format_id);
                                        let sz = if fmt.filesize > 0 { format_bytes(fmt.filesize) } else { "--".to_string() };
                                        let label = format!("{} | {} | {} | {}", fmt.res_label, fmt.ext.to_uppercase(), fmt.format_note, sz);

                                        if ui.selectable_label(is_sel, label).clicked() {
                                            self.selected_format_id = Some(fmt.format_id.clone());
                                        }
                                    }
                                });
                        }
                        MediaExtractionResult::Playlist(pl) => {
                            ui.heading(&pl.title);
                            ui.label(format!("Total Items: {}", pl.total_items));

                            egui::ScrollArea::vertical()
                                .max_height(260.0)
                                .show(ui, |ui| {
                                    for entry in &pl.entries {
                                        ui.horizontal(|ui| {
                                            ui.label(format!("{}.", entry.index));
                                            ui.label(&entry.title);
                                            ui.weak(&entry.url);
                                        });
                                    }
                                });
                        }
                    }
                }

                ui.add_space(8.0);
                ui.separator();
                ui.add_space(4.0);

                // Save directory row
                ui.horizontal(|ui| {
                    ui.label("Save Directory:");
                    let mut dir_str = self.save_dir.to_string_lossy().to_string();
                    ui.text_edit_singleline(&mut dir_str);
                    if ui.button("Browse...").clicked() {
                        if let Some(chosen) = rfd::FileDialog::new().pick_folder() {
                            self.save_dir = chosen;
                        }
                    }
                });

                ui.add_space(10.0);

                // Action buttons
                ui.horizontal(|ui| {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Close").clicked() {
                            self.close();
                        }

                        let can_download = self.extraction_result.is_some() && !self.is_analyzing;
                        if ui.add_enabled(can_download, egui::Button::new("Download Media")).clicked() {
                            let format_spec = if self.is_audio_only {
                                "bestaudio/best".to_string()
                            } else if let Some(ref fid) = self.selected_format_id {
                                format!("{}+bestaudio/best", fid)
                            } else {
                                "bestvideo+bestaudio/best".to_string()
                            };

                            let filename = match &self.extraction_result {
                                Some(MediaExtractionResult::Single(s)) => Some(format!("{}.{}", s.title, if self.is_audio_only { &self.audio_format } else { &self.video_container })),
                                _ => None,
                            };

                            start_config = Some(MediaDownloadConfig {
                                url: self.url.clone(),
                                save_dir: self.save_dir.clone(),
                                filename,
                                format_spec,
                                is_audio_only: self.is_audio_only,
                                audio_format: Some(self.audio_format.clone()),
                                merge_output_format: Some(self.video_container.clone()),
                                cookies_browser: None,
                                cookies_file: None,
                                cookies: None,
                                referrer: None,
                                user_agent: None,
                                max_connections: 8,
                                rate_limit_bytes: 0,
                                embed_thumbnail: self.embed_thumbnail,
                                pot_enabled: true,
                            });

                            self.close();
                        }
                    });
                });
            });

        self.is_open = is_open;
        start_config
    }
}
