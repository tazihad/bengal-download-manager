use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use eframe::egui;
use tokio::sync::mpsc;
use bengal_core::format_bytes;
use bengal_grabber::{GrabberConfig, GrabberCrawler, GrabberEvent, GrabberFile};

pub struct GrabberItem {
    pub file: GrabberFile,
    pub selected: bool,
}

pub struct GrabberDialog {
    pub is_open: bool,
    pub start_url: String,
    pub explore_depth: usize,
    pub stay_same_domain: bool,
    pub stay_same_path: bool,
    pub dont_explore_parent_dirs: bool,
    pub hide_duplicates: bool,
    pub include_patterns: String,
    pub exclude_patterns: String,
    pub save_dir: PathBuf,

    // Runtime state
    pub is_crawling: bool,
    pub status_text: String,
    pub items: Vec<GrabberItem>,
    pub cancel_flag: Option<Arc<AtomicBool>>,
    pub event_rx: Option<mpsc::Receiver<GrabberEvent>>,
}

impl Default for GrabberDialog {
    fn default() -> Self {
        Self {
            is_open: false,
            start_url: String::new(),
            explore_depth: 1,
            stay_same_domain: true,
            stay_same_path: false,
            dont_explore_parent_dirs: true,
            hide_duplicates: true,
            include_patterns: "*.*".to_string(),
            exclude_patterns: String::new(),
            save_dir: bengal_core::AppPaths::default_download_dir(),
            is_crawling: false,
            status_text: "Ready to crawl".to_string(),
            items: Vec::new(),
            cancel_flag: None,
            event_rx: None,
        }
    }
}

impl GrabberDialog {
    pub fn open(&mut self) {
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
        self.stop_crawl();
    }

    pub fn stop_crawl(&mut self) {
        if let Some(flag) = &self.cancel_flag {
            flag.store(true, Ordering::Relaxed);
        }
        self.is_crawling = false;
        self.status_text = "Crawl stopped".to_string();
    }

    pub fn start_crawl(&mut self) {
        if self.start_url.trim().is_empty() {
            self.status_text = "Please enter a valid start URL".to_string();
            return;
        }

        self.items.clear();
        self.is_crawling = true;
        self.status_text = "Starting crawl...".to_string();

        let inc_patterns = self.include_patterns
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();

        let exc_patterns = self.exclude_patterns
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();

        let config = GrabberConfig {
            start_url: self.start_url.trim().to_string(),
            explore_depth: self.explore_depth,
            stay_same_domain: self.stay_same_domain,
            stay_same_path: self.stay_same_path,
            dont_explore_parent_dirs: self.dont_explore_parent_dirs,
            hide_duplicates: self.hide_duplicates,
            allow_private_hosts: true,
            file_include_patterns: inc_patterns,
            file_exclude_patterns: exc_patterns,
            min_size_bytes: 0,
            max_size_bytes: 0,
            user_agent: "Mozilla/5.0 (compatible; BengalGrabber/1.0)".to_string(),
        };

        let (crawler, cancel_flag) = GrabberCrawler::new(config);
        self.cancel_flag = Some(cancel_flag);

        let (tx, rx) = mpsc::channel(100);
        self.event_rx = Some(rx);

        tokio::spawn(async move {
            let _ = crawler.run(tx).await;
        });
    }

    pub fn poll_events(&mut self) {
        if let Some(rx) = &mut self.event_rx {
            while let Ok(event) = rx.try_recv() {
                match event {
                    GrabberEvent::Progress(p) => {
                        self.status_text = p;
                    }
                    GrabberEvent::FileFound(f) => {
                        self.items.push(GrabberItem {
                            file: f,
                            selected: true,
                        });
                    }
                    GrabberEvent::MetadataUpdated { url, size_bytes } => {
                        if let Some(item) = self.items.iter_mut().find(|i| i.file.url == url) {
                            item.file.size = size_bytes;
                        }
                    }
                    GrabberEvent::Finished { total_files, pages_crawled } => {
                        self.is_crawling = false;
                        self.status_text = format!("Finished: {} files discovered across {} pages", total_files, pages_crawled);
                    }
                    GrabberEvent::Failed(err) => {
                        self.is_crawling = false;
                        self.status_text = format!("Error: {}", err);
                    }
                }
            }
        }
    }

    pub fn render(&mut self, ctx: &egui::Context) -> Option<Vec<crate::ui::dialogs::add::AddDownloadRequest>> {
        if !self.is_open {
            return None;
        }

        self.poll_events();

        let mut submitted_requests = None;
        let mut is_open = self.is_open;

        egui::Window::new("🕸 Site Grabber")
            .open(&mut is_open)
            .collapsible(false)
            .resizable(true)
            .default_width(720.0)
            .default_height(580.0)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.add_space(4.0);

                // URL and crawl controls
                ui.horizontal(|ui| {
                    ui.label("Start URL:");
                    ui.add(egui::TextEdit::singleline(&mut self.start_url).desired_width(400.0));

                    if !self.is_crawling {
                        if ui.button("▶ Start Crawl").clicked() {
                            self.start_crawl();
                        }
                    } else if ui.button("⏹ Stop").clicked() {
                        self.stop_crawl();
                    }
                });

                ui.add_space(6.0);

                // Crawl limits and boundary filters
                ui.horizontal(|ui| {
                    ui.label("Explore Depth:");
                    ui.add(egui::Slider::new(&mut self.explore_depth, 1..=5));

                    ui.checkbox(&mut self.stay_same_domain, "Same Domain");
                    ui.checkbox(&mut self.dont_explore_parent_dirs, "No Parent Dirs");
                    ui.checkbox(&mut self.hide_duplicates, "Hide Duplicates");
                });

                ui.add_space(4.0);

                // Pattern filters
                ui.horizontal(|ui| {
                    ui.label("Include Patterns:");
                    ui.text_edit_singleline(&mut self.include_patterns);

                    ui.label("Exclude Patterns:");
                    ui.text_edit_singleline(&mut self.exclude_patterns);
                });

                ui.add_space(8.0);
                ui.separator();
                ui.add_space(4.0);

                // Status message and batch selection buttons
                ui.horizontal(|ui| {
                    ui.strong(&self.status_text);
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Unselect All").clicked() {
                            for item in &mut self.items {
                                item.selected = false;
                            }
                        }
                        if ui.button("Select All").clicked() {
                            for item in &mut self.items {
                                item.selected = true;
                            }
                        }
                        ui.label(format!("Found: {}", self.items.len()));
                    });
                });

                ui.add_space(4.0);

                // Discovered items list
                egui::ScrollArea::vertical()
                    .max_height(260.0)
                    .show(ui, |ui| {
                        for item in &mut self.items {
                            ui.horizontal(|ui| {
                                ui.checkbox(&mut item.selected, "");
                                ui.label(&item.file.filename);
                                let sz_text = if item.file.size > 0 {
                                    format_bytes(item.file.size as u64)
                                } else {
                                    "--".to_string()
                                };
                                ui.monospace(sz_text);
                                ui.weak(&item.file.url);
                            });
                        }
                    });

                ui.add_space(8.0);

                // Save directory
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

                ui.add_space(8.0);
                ui.separator();
                ui.add_space(4.0);

                // Action buttons
                ui.horizontal(|ui| {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui.button("Close").clicked() {
                            self.close();
                        }

                        let selected_count = self.items.iter().filter(|i| i.selected).count();
                        let can_submit = selected_count > 0;

                        if ui
                            .add_enabled(
                                can_submit,
                                egui::Button::new(format!("Download Selected ({})", selected_count)),
                            )
                            .clicked()
                        {
                            let mut reqs = Vec::new();
                            for item in &self.items {
                                if item.selected {
                                    reqs.push(crate::ui::dialogs::add::AddDownloadRequest {
                                        url: item.file.url.clone(),
                                        filename: item.file.filename.clone(),
                                        save_dir: self.save_dir.clone(),
                                        start_now: true,
                                        max_segments: 8,
                                        speed_limit_bps: 0,
                                        referrer: Some(item.file.source_page.clone()),
                                        user_agent: None,
                                        cookies: None,
                                        proxy: None,
                                    });
                                }
                            }
                            submitted_requests = Some(reqs);
                            self.close();
                        }
                    });
                });
            });

        self.is_open = is_open;
        submitted_requests
    }
}
