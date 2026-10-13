use std::path::Path;
use std::sync::{Arc, Mutex};
use rusqlite::{params, Connection, Result};
use bengal_core::{AppPaths, DownloadRecord};

#[derive(Clone)]
pub struct Database {
    conn: Arc<Mutex<Connection>>,
}

impl Database {
    /// Opens the database at the standard XDG data path.
    pub fn open_default() -> anyhow::Result<Self> {
        AppPaths::ensure_dirs()?;
        let path = AppPaths::database_path();
        Self::open(&path)
    }

    /// Opens the database at a specified file path.
    pub fn open(path: &Path) -> anyhow::Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let conn = Connection::open(path)?;

        // Performance optimizations matching current Python database configuration
        conn.execute_batch(
            "PRAGMA journal_mode = WAL;
             PRAGMA synchronous = NORMAL;
             PRAGMA foreign_keys = ON;
             PRAGMA busy_timeout = 5000;
             PRAGMA temp_store = MEMORY;",
        )?;

        let db = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        db.init_schema()?;
        Ok(db)
    }

    /// Initializes tables, indices, and defaults matching Bengal Download Manager schema.
    pub fn init_schema(&self) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS queues (
                name TEXT PRIMARY KEY,
                position INTEGER NOT NULL DEFAULT 0,
                mode TEXT NOT NULL DEFAULT 'onetime',
                is_default INTEGER NOT NULL DEFAULT 0,
                max_concurrent INTEGER NOT NULL DEFAULT 4,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position INTEGER NOT NULL DEFAULT 0,
                url TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                size TEXT NOT NULL DEFAULT '',
                downloaded TEXT NOT NULL DEFAULT '0 B',
                status TEXT NOT NULL DEFAULT 'queued',
                progress REAL NOT NULL DEFAULT 0.0,
                speed TEXT NOT NULL DEFAULT '',
                eta TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'General',
                queue TEXT NOT NULL DEFAULT 'Default',
                connections INTEGER NOT NULL DEFAULT 8,
                created_at TEXT NOT NULL DEFAULT '',
                finished_at TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads (status);
            CREATE INDEX IF NOT EXISTS idx_downloads_queue ON downloads (queue);

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                path TEXT NOT NULL DEFAULT '',
                extensions TEXT NOT NULL DEFAULT '',
                is_system INTEGER NOT NULL DEFAULT 0
            );",
        )?;
        Ok(())
    }

    /// Inserts a new download into the database and returns its assigned ID.
    pub fn insert_download(
        &self,
        url: &str,
        filename: &str,
        path: &str,
        size: &str,
        category: &str,
    ) -> Result<i64> {
        let conn = self.conn.lock().unwrap();
        let now = chrono::Utc::now().to_rfc3339();

        conn.execute(
            "INSERT INTO downloads (url, filename, path, size, category, status, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, 'queued', ?6)",
            params![url, filename, path, size, category, now],
        )?;

        Ok(conn.last_insert_rowid())
    }

    /// Lists all downloads ordered by position/id.
    pub fn list_downloads(&self) -> Result<Vec<DownloadRecord>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, position, url, filename, path, size, downloaded, status, progress, speed, eta, category, queue, connections, created_at, finished_at, error_message
             FROM downloads ORDER BY id DESC",
        )?;

        let rows = stmt.query_map([], |row| {
            Ok(DownloadRecord {
                id: row.get(0)?,
                position: row.get(1)?,
                url: row.get(2)?,
                filename: row.get(3)?,
                path: row.get(4)?,
                size: row.get(5)?,
                downloaded: row.get(6)?,
                status: row.get(7)?,
                progress: row.get(8)?,
                speed: row.get(9)?,
                eta: row.get(10)?,
                category: row.get(11)?,
                queue: row.get(12)?,
                connections: row.get(13)?,
                created_at: row.get(14)?,
                finished_at: row.get(15)?,
                error_message: row.get(16)?,
            })
        })?;

        let mut list = Vec::new();
        for r in rows {
            list.push(r?);
        }
        Ok(list)
    }

    /// Retrieves a single download record by its ID.
    pub fn get_download(&self, id: i64) -> Result<Option<DownloadRecord>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, position, url, filename, path, size, downloaded, status, progress, speed, eta, category, queue, connections, created_at, finished_at, error_message
             FROM downloads WHERE id = ?1",
        )?;

        let mut rows = stmt.query(params![id])?;
        if let Some(row) = rows.next()? {
            Ok(Some(DownloadRecord {
                id: row.get(0)?,
                position: row.get(1)?,
                url: row.get(2)?,
                filename: row.get(3)?,
                path: row.get(4)?,
                size: row.get(5)?,
                downloaded: row.get(6)?,
                status: row.get(7)?,
                progress: row.get(8)?,
                speed: row.get(9)?,
                eta: row.get(10)?,
                category: row.get(11)?,
                queue: row.get(12)?,
                connections: row.get(13)?,
                created_at: row.get(14)?,
                finished_at: row.get(15)?,
                error_message: row.get(16)?,
            }))
        } else {
            Ok(None)
        }
    }

    /// Updates dynamic progress fields for a download.
    pub fn update_progress(
        &self,
        id: i64,
        downloaded: &str,
        progress: f64,
        speed: &str,
        eta: &str,
    ) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE downloads SET downloaded = ?1, progress = ?2, speed = ?3, eta = ?4 WHERE id = ?5",
            params![downloaded, progress, speed, eta, id],
        )?;
        Ok(())
    }

    /// Updates the status and optional error message of a download.
    pub fn update_status(&self, id: i64, status: &str, error_message: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let finished_at = if status == "completed" {
            chrono::Utc::now().to_rfc3339()
        } else {
            String::new()
        };

        conn.execute(
            "UPDATE downloads SET status = ?1, error_message = ?2, finished_at = CASE WHEN ?3 != '' THEN ?3 ELSE finished_at END WHERE id = ?4",
            params![status, error_message, finished_at, id],
        )?;
        Ok(())
    }

    /// Deletes a download record from the database.
    pub fn delete_download(&self, id: i64) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM downloads WHERE id = ?1", params![id])?;
        Ok(())
    }

    /// Updates the filename and path of a download record.
    pub fn update_filename(&self, id: i64, new_filename: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT path FROM downloads WHERE id = ?1")?;
        let current_path: Option<String> = stmt.query_row(params![id], |row| row.get(0)).ok();

        let new_path = if let Some(p) = current_path {
            let path_buf = std::path::PathBuf::from(p);
            let parent = path_buf.parent().unwrap_or_else(|| std::path::Path::new(""));
            parent.join(new_filename).to_string_lossy().to_string()
        } else {
            new_filename.to_string()
        };

        conn.execute(
            "UPDATE downloads SET filename = ?1, path = ?2 WHERE id = ?3",
            params![new_filename, new_path, id],
        )?;
        Ok(())
    }

    /// Updates the URL of a download record (e.g. on link refresh).
    pub fn update_url(&self, id: i64, new_url: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE downloads SET url = ?1 WHERE id = ?2",
            params![new_url, id],
        )?;
        Ok(())
    }

    /// Lists all download queues.
    pub fn list_queues(&self) -> Result<Vec<QueueRecord>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT name, position, mode, is_default, max_concurrent FROM queues ORDER BY position ASC, name ASC",
        )?;

        let rows = stmt.query_map([], |row| {
            Ok(QueueRecord {
                name: row.get(0)?,
                position: row.get(1)?,
                mode: row.get(2)?,
                is_default: row.get::<_, i64>(3)? != 0,
                max_concurrent: row.get(4)?,
            })
        })?;

        let mut list = Vec::new();
        for r in rows {
            list.push(r?);
        }
        if list.is_empty() {
            list.push(QueueRecord {
                name: "Default".to_string(),
                position: 0,
                mode: "onetime".to_string(),
                is_default: true,
                max_concurrent: 4,
            });
        }
        Ok(list)
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct QueueRecord {
    pub name: String,
    pub position: i64,
    pub mode: String,
    pub is_default: bool,
    pub max_concurrent: i64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_in_memory_db() {
        let conn = Connection::open_in_memory().unwrap();
        let db = Database {
            conn: Arc::new(Mutex::new(conn)),
        };
        db.init_schema().unwrap();

        let id = db
            .insert_download(
                "https://example.com/test.zip",
                "test.zip",
                "/tmp/test.zip",
                "10 MB",
                "Compressed",
            )
            .unwrap();
        assert_eq!(id, 1);

        let item = db.get_download(1).unwrap().unwrap();
        assert_eq!(item.filename, "test.zip");
        assert_eq!(item.status, "queued");

        db.update_status(1, "completed", "").unwrap();
        let item_updated = db.get_download(1).unwrap().unwrap();
        assert_eq!(item_updated.status, "completed");
    }
}
