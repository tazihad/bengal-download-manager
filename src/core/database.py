"""
SQLite database engine for Bengal Download Manager.
Handles high-performance WAL-mode persistence for download records, queues,
and full-text search indexing.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from . import utils

logger = logging.getLogger(__name__)

_DB_LOCK = threading.RLock()


def get_db_path() -> str:
    """Returns the absolute path to the SQLite downloads database."""
    return os.path.join(utils.get_data_dir(), "downloads.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Creates and configures an optimized SQLite connection.
    Enables WAL journal mode, NORMAL synchronous mode, and foreign keys.
    """
    target_path = db_path or get_db_path()
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    conn = sqlite3.connect(
        target_path,
        timeout=10.0,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    
    with conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA cache_size = -64000;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA temp_store = MEMORY;")
    
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes the database schema, indexes, and triggers."""
    with _DB_LOCK:
        conn = get_db_connection(db_path)
        try:
            with conn:
                # Queues Table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS queues (
                        name TEXT PRIMARY KEY,
                        position INTEGER NOT NULL DEFAULT 0,
                        mode TEXT NOT NULL DEFAULT 'onetime',
                        is_default INTEGER NOT NULL DEFAULT 0,
                        max_concurrent INTEGER NOT NULL DEFAULT 4,
                        config_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL DEFAULT ''
                    );
                """)

                # Downloads Table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        position INTEGER NOT NULL DEFAULT 0,
                        url TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        path TEXT NOT NULL,
                        size TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'Queued',
                        time_left TEXT NOT NULL DEFAULT '',
                        rate TEXT NOT NULL DEFAULT '',
                        last_try TEXT NOT NULL DEFAULT '',
                        date_added TEXT NOT NULL DEFAULT '',
                        queue_name TEXT NOT NULL DEFAULT 'Main download queue',
                        extra_data TEXT NOT NULL DEFAULT '{}'
                    );
                """)

                # Daily Data Usage Table (Keeps current month only)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS daily_data_usage (
                        date TEXT PRIMARY KEY,
                        bytes_downloaded INTEGER NOT NULL DEFAULT 0,
                        files_count INTEGER NOT NULL DEFAULT 0
                    );
                """)

                # Indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_status_queue ON downloads (status, queue_name);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_position ON downloads (position ASC);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_date_added ON downloads (date_added DESC);")

                # FTS5 Virtual Table and triggers (gracefully ignore if FTS5 is not supported)
                try:
                    conn.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS downloads_fts USING fts5(
                            filename,
                            url,
                            queue_name,
                            content='downloads',
                            content_rowid='id'
                        );
                    """)
                    conn.execute("""
                        CREATE TRIGGER IF NOT EXISTS downloads_ai AFTER INSERT ON downloads BEGIN
                            INSERT INTO downloads_fts(rowid, filename, url, queue_name)
                            VALUES (new.id, new.filename, new.url, new.queue_name);
                        END;
                    """)
                    conn.execute("""
                        CREATE TRIGGER IF NOT EXISTS downloads_ad AFTER DELETE ON downloads BEGIN
                            INSERT INTO downloads_fts(downloads_fts, rowid, filename, url, queue_name)
                            VALUES('delete', old.id, old.filename, old.url, old.queue_name);
                        END;
                    """)
                    conn.execute("""
                        CREATE TRIGGER IF NOT EXISTS downloads_au AFTER UPDATE ON downloads BEGIN
                            INSERT INTO downloads_fts(downloads_fts, rowid, filename, url, queue_name)
                            VALUES('delete', old.id, old.filename, old.url, old.queue_name);
                            INSERT INTO downloads_fts(rowid, filename, url, queue_name)
                            VALUES (new.id, new.filename, new.url, new.queue_name);
                        END;
                    """)
                except Exception as e:
                    logger.debug("[DB] FTS5 initialization skipped/not supported: %s", e)

            # Seed default queues if empty
            _seed_default_queues_if_needed(conn)
        finally:
            conn.close()


def _seed_default_queues_if_needed(conn: sqlite3.Connection) -> None:
    """Seeds default queue records if the queues table is empty."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM queues")
    count = cur.fetchone()[0]
    if count == 0:
        from core.queue_manager import DEFAULT_QUEUES
        now = str(time.time())
        with conn:
            for idx, q in enumerate(DEFAULT_QUEUES):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO queues 
                    (name, position, mode, is_default, max_concurrent, config_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q.get("name", "Main download queue"),
                        idx,
                        q.get("mode", "onetime"),
                        1 if q.get("default", False) else 0,
                        q.get("max_concurrent", 4),
                        json.dumps(q),
                        now
                    )
                )


def get_all_downloads(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all downloads from the database ordered by position ASC."""
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, position, url, filename, path, size, status, time_left, rate, last_try, date_added, queue_name, extra_data
                FROM downloads
                ORDER BY position ASC, id ASC
            """)
            rows = cur.fetchall()
            downloads = []
            for r in rows:
                extra = {}
                try:
                    extra = json.loads(r["extra_data"]) if r["extra_data"] else {}
                except Exception:
                    pass
                
                downloads.append({
                    "id": r["id"],
                    "url": r["url"],
                    "filename": r["filename"],
                    "path": r["path"],
                    "size": r["size"],
                    "status": r["status"],
                    "time_left": r["time_left"],
                    "rate": r["rate"],
                    "last_try": r["last_try"],
                    "date_added": r["date_added"],
                    "queue": r["queue_name"],
                    "extra_data": extra
                })
            return downloads
        finally:
            conn.close()


def save_all_downloads(downloads: List[Dict[str, Any]], db_path: Optional[str] = None) -> None:
    """
    Atomically saves all downloads into the database.
    Replaces current table contents while preserving positions.
    """
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                conn.execute("DELETE FROM downloads;")
                for idx, d in enumerate(downloads):
                    extra = d.get("extra_data", {})
                    extra_json = json.dumps(extra) if isinstance(extra, dict) else "{}"
                    conn.execute(
                        """
                        INSERT INTO downloads 
                        (position, url, filename, path, size, status, time_left, rate, last_try, date_added, queue_name, extra_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            idx,
                            d.get("url", ""),
                            d.get("filename", "Unknown"),
                            d.get("path", ""),
                            d.get("size", ""),
                            d.get("status", "0.00%"),
                            d.get("time_left", ""),
                            d.get("rate", ""),
                            str(d.get("last_try", "")),
                            str(d.get("date_added", "")),
                            d.get("queue", "Main download queue"),
                            extra_json
                        )
                    )
        except Exception as e:
            logger.error("[DB] Failed to save downloads: %s", e)
        finally:
            conn.close()


def get_all_queues(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all queue configurations ordered by position."""
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT name, position, mode, is_default, max_concurrent, config_json, created_at
                FROM queues
                ORDER BY position ASC, created_at ASC
            """)
            rows = cur.fetchall()
            queues = []
            for r in rows:
                try:
                    q_data = json.loads(r["config_json"])
                except Exception:
                    q_data = {}
                q_data["name"] = r["name"]
                q_data["mode"] = r["mode"]
                q_data["default"] = bool(r["is_default"])
                q_data["max_concurrent"] = r["max_concurrent"]
                queues.append(q_data)
            return queues
        finally:
            conn.close()


def save_all_queues(queues: List[Dict[str, Any]], db_path: Optional[str] = None) -> None:
    """
    Atomically saves all queue definitions to the database.
    """
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            now = str(time.time())
            with conn:
                conn.execute("DELETE FROM queues;")
                for idx, q in enumerate(queues):
                    name = q.get("name", f"Queue #{idx+1}")
                    mode = q.get("mode", "onetime")
                    is_def = 1 if q.get("default", False) else 0
                    max_c = q.get("max_concurrent", 4)
                    config_json = json.dumps(q)
                    conn.execute(
                        """
                        INSERT INTO queues 
                        (name, position, mode, is_default, max_concurrent, config_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (name, idx, mode, is_def, max_c, config_json, now)
                    )
        except Exception as e:
            logger.error("[DB] Failed to save queues: %s", e)
        finally:
            conn.close()


def upsert_queue(queue_dict: Dict[str, Any], position: Optional[int] = None, db_path: Optional[str] = None) -> None:
    """Inserts or updates a single queue configuration."""
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            name = queue_dict.get("name")
            if not name:
                return
            mode = queue_dict.get("mode", "onetime")
            is_def = 1 if queue_dict.get("default", False) else 0
            max_c = queue_dict.get("max_concurrent", 4)
            config_json = json.dumps(queue_dict)
            now = str(time.time())
            
            with conn:
                if position is None:
                    cur = conn.cursor()
                    cur.execute("SELECT position FROM queues WHERE name = ?", (name,))
                    row = cur.fetchone()
                    if row:
                        pos = row[0]
                    else:
                        cur.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM queues")
                        pos = cur.fetchone()[0]
                else:
                    pos = position

                conn.execute(
                    """
                    INSERT INTO queues (name, position, mode, is_default, max_concurrent, config_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        mode=excluded.mode,
                        is_default=excluded.is_default,
                        max_concurrent=excluded.max_concurrent,
                        config_json=excluded.config_json;
                    """,
                    (name, pos, mode, is_def, max_c, config_json, now)
                )
        finally:
            conn.close()


def delete_queue(name: str, db_path: Optional[str] = None) -> None:
    """Deletes a queue by name."""
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                conn.execute("DELETE FROM queues WHERE name = ? AND is_default = 0;", (name,))
        finally:
            conn.close()


def search_downloads(query: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Performs full-text search across filename, url, and queue."""
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            cur = conn.cursor()
            like_pat = f"%{query}%"
            cur.execute(
                """
                SELECT id, position, url, filename, path, size, status, time_left, rate, last_try, date_added, queue_name, extra_data
                FROM downloads
                WHERE filename LIKE ? OR url LIKE ? OR queue_name LIKE ?
                ORDER BY position ASC, id ASC
                """,
                (like_pat, like_pat, like_pat)
            )
            rows = cur.fetchall()

            downloads = []
            for r in rows:
                downloads.append({
                    "id": r["id"],
                    "url": r["url"],
                    "filename": r["filename"],
                    "path": r["path"],
                    "size": r["size"],
                    "status": r["status"],
                    "time_left": r["time_left"],
                    "rate": r["rate"],
                    "last_try": r["last_try"],
                    "date_added": r["date_added"],
                    "queue": r["queue_name"]
                })
            return downloads
        finally:
            conn.close()


def cleanup_old_data_usage(current_month: Optional[str] = None, db_path: Optional[str] = None) -> None:
    """Removes daily data usage records from prior months, preserving only the current month."""
    if not current_month:
        from datetime import datetime
        current_month = datetime.now().strftime("%Y-%m")
    with _DB_LOCK:
        init_db(db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                conn.execute(
                    "DELETE FROM daily_data_usage WHERE substr(date, 1, 7) != ?;",
                    (current_month,)
                )
        finally:
            conn.close()


def record_daily_usage(date_str: str, bytes_count: int, files_count: int = 0, db_path: Optional[str] = None) -> None:
    """Records or updates daily data usage for a specific date (YYYY-MM-DD), ensuring usage never decreases."""
    if not date_str or bytes_count < 0:
        return
    with _DB_LOCK:
        init_db(db_path)
        cleanup_old_data_usage(db_path=db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO daily_data_usage (date, bytes_downloaded, files_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        bytes_downloaded = MAX(bytes_downloaded, excluded.bytes_downloaded),
                        files_count = MAX(files_count, excluded.files_count);
                """, (date_str, int(bytes_count), int(files_count)))
        finally:
            conn.close()


def add_daily_usage(date_str: str, bytes_count: int, files_count: int = 1, db_path: Optional[str] = None) -> None:
    """Atomically increments daily data usage for date_str when a download completes."""
    if not date_str or bytes_count <= 0:
        return
    with _DB_LOCK:
        init_db(db_path)
        cleanup_old_data_usage(db_path=db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                conn.execute("""
                    INSERT INTO daily_data_usage (date, bytes_downloaded, files_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        bytes_downloaded = bytes_downloaded + excluded.bytes_downloaded,
                        files_count = files_count + excluded.files_count;
                """, (date_str, int(bytes_count), int(files_count)))
        finally:
            conn.close()


def get_month_daily_usage(month_str: Optional[str] = None, db_path: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """
    Returns a mapping of YYYY-MM-DD -> {'bytes': int, 'files': int} for the specified month
    (defaults to current month). Automatically cleans up older months.
    Reconciles with completed downloads recorded in the downloads table.
    """
    from datetime import datetime
    if not month_str:
        month_str = datetime.now().strftime("%Y-%m")

    with _DB_LOCK:
        init_db(db_path)
        cleanup_old_data_usage(current_month=month_str, db_path=db_path)
        conn = get_db_connection(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT date, bytes_downloaded, files_count FROM daily_data_usage WHERE substr(date, 1, 7) = ? ORDER BY date ASC;",
                (month_str,)
            )
            rows = cur.fetchall()
            result: Dict[str, Dict[str, int]] = {}
            for r in rows:
                result[r["date"]] = {
                    "bytes": int(r["bytes_downloaded"] or 0),
                    "files": int(r["files_count"] or 0)
                }

            # Accurately aggregate all completed downloads from downloads table for this month
            cur.execute("""
                SELECT size, last_try, date_added
                FROM downloads
                WHERE status IN ('Complete', 'Finished')
            """)
            dl_rows = cur.fetchall()
            from core.services.theme_service import parse_size_to_bytes
            dl_by_date: Dict[str, Dict[str, int]] = {}
            for dl in dl_rows:
                ts_str = dl["last_try"] or dl["date_added"]
                if not ts_str:
                    continue
                try:
                    ts = float(ts_str)
                    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    if dt.startswith(month_str):
                        b = int(parse_size_to_bytes(dl["size"] or "0"))
                        if dt not in dl_by_date:
                            dl_by_date[dt] = {"bytes": 0, "files": 0}
                        dl_by_date[dt]["bytes"] += b
                        dl_by_date[dt]["files"] += 1
                except Exception:
                    pass

            # Merge any completed downloads from downloads table using MAX so cleared items are preserved
            for dt, stats in dl_by_date.items():
                if dt not in result:
                    result[dt] = stats
                    try:
                        cur.execute("""
                            INSERT INTO daily_data_usage (date, bytes_downloaded, files_count)
                            VALUES (?, ?, ?)
                            ON CONFLICT(date) DO UPDATE SET
                                bytes_downloaded = MAX(bytes_downloaded, excluded.bytes_downloaded),
                                files_count = MAX(files_count, excluded.files_count);
                        """, (dt, stats["bytes"], stats["files"]))
                    except Exception:
                        pass
                else:
                    if stats["bytes"] > result[dt]["bytes"] or stats["files"] > result[dt]["files"]:
                        result[dt]["bytes"] = max(result[dt]["bytes"], stats["bytes"])
                        result[dt]["files"] = max(result[dt]["files"], stats["files"])
                        try:
                            cur.execute("""
                                UPDATE daily_data_usage
                                SET bytes_downloaded = ?, files_count = ?
                                WHERE date = ?;
                            """, (result[dt]["bytes"], result[dt]["files"], dt))
                        except Exception:
                            pass

            conn.commit()
            return result
        finally:
            conn.close()


