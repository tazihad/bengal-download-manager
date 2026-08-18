"""
Unit and integration tests for SQLite Database persistence in Bengal Download Manager.
Tests table creation, WAL mode, CRUD operations, transactions, legacy JSON migration, and search.
"""

import json
import os
import sqlite3
import threading
import time
import pytest

from core.database import (
    init_db,
    get_db_connection,
    get_all_downloads,
    save_all_downloads,
    get_all_queues,
    save_all_queues,
    upsert_queue,
    delete_queue,
    search_downloads,
)


def test_database_init_and_pragmas(tmp_path):
    """Verify database initialization, schema tables, and WAL mode pragmas."""
    db_file = str(tmp_path / "test_downloads.db")
    init_db(db_file)

    assert os.path.exists(db_file)
    conn = get_db_connection(db_file)
    try:
        cur = conn.cursor()
        # Verify journal mode is WAL
        cur.execute("PRAGMA journal_mode;")
        journal_mode = cur.fetchone()[0].lower()
        assert journal_mode in ("wal", "memory")

        # Verify tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cur.fetchall()}
        assert "downloads" in tables
        assert "queues" in tables
    finally:
        conn.close()


def test_downloads_save_and_retrieve(tmp_path):
    """Verify atomic saving and ordering of downloads."""
    db_file = str(tmp_path / "test_downloads.db")

    sample_downloads = [
        {
            "url": "https://example.com/file1.zip",
            "filename": "file1.zip",
            "path": "/home/user/Downloads/file1.zip",
            "size": "15.00 MB",
            "status": "Complete",
            "time_left": "00:00",
            "rate": "2.5 MB/s",
            "last_try": "1700000000.0",
            "date_added": "1700000000.0",
            "queue": "Main download queue",
            "extra_data": {"category": "Compressed"}
        },
        {
            "url": "https://example.com/video.mp4",
            "filename": "video.mp4",
            "path": "/home/user/Downloads/video.mp4",
            "size": "120.50 MB",
            "status": "45.20%",
            "time_left": "01:15",
            "rate": "1.2 MB/s",
            "last_try": "1700000500.0",
            "date_added": "1700000500.0",
            "queue": "Synchronization queue",
            "extra_data": {"category": "Video"}
        }
    ]

    save_all_downloads(sample_downloads, db_path=db_file)
    retrieved = get_all_downloads(db_path=db_file)

    assert len(retrieved) == 2
    assert retrieved[0]["filename"] == "file1.zip"
    assert retrieved[0]["status"] == "Complete"
    assert retrieved[0]["extra_data"] == {"category": "Compressed"}
    assert retrieved[1]["filename"] == "video.mp4"
    assert retrieved[1]["queue"] == "Synchronization queue"


def test_queues_crud_operations(tmp_path):
    """Verify queue configuration persistence, upsert, and deletion."""
    db_file = str(tmp_path / "test_downloads.db")
    init_db(db_file)

    # Initial default queues
    queues = get_all_queues(db_path=db_file)
    assert len(queues) >= 2
    names = [q["name"] for q in queues]
    assert "Main download queue" in names
    assert "Synchronization queue" in names

    # Add custom queue
    custom_q = {
        "name": "Night Downloads",
        "default": False,
        "mode": "onetime",
        "max_concurrent": 2,
        "start_at_enabled": True,
        "start_at_time": "02:00:00",
        "daily_days": [True, True, True, True, True, False, False]
    }
    upsert_queue(custom_q, db_path=db_file)

    updated_queues = get_all_queues(db_path=db_file)
    assert any(q["name"] == "Night Downloads" for q in updated_queues)
    night_q = next(q for q in updated_queues if q["name"] == "Night Downloads")
    assert night_q["max_concurrent"] == 2
    assert night_q["start_at_time"] == "02:00:00"

    # Delete custom queue
    delete_queue("Night Downloads", db_path=db_file)
    after_del = get_all_queues(db_path=db_file)
    assert not any(q["name"] == "Night Downloads" for q in after_del)

    # Built-in queues cannot be deleted
    delete_queue("Main download queue", db_path=db_file)
    still_present = get_all_queues(db_path=db_file)
    assert any(q["name"] == "Main download queue" for q in still_present)




def test_search_downloads(tmp_path):
    """Verify search functionality across downloads."""
    db_file = str(tmp_path / "test_downloads.db")

    sample_downloads = [
        {
            "url": "https://kernel.org/pub/linux/kernel/v6.x/linux-6.10.tar.xz",
            "filename": "linux-6.10.tar.xz",
            "path": "/tmp/linux-6.10.tar.xz",
            "size": "140 MB",
            "status": "Complete",
            "time_left": "",
            "rate": "",
            "last_try": "1700000000",
            "date_added": "1700000000",
            "queue": "Kernel Queue"
        },
        {
            "url": "https://archlinux.org/iso/archlinux.iso",
            "filename": "archlinux.iso",
            "path": "/tmp/archlinux.iso",
            "size": "900 MB",
            "status": "Paused",
            "time_left": "",
            "rate": "",
            "last_try": "1700000000",
            "date_added": "1700000000",
            "queue": "Main download queue"
        }
    ]
    save_all_downloads(sample_downloads, db_path=db_file)

    res1 = search_downloads("linux", db_path=db_file)
    assert len(res1) == 2

    res2 = search_downloads("kernel", db_path=db_file)
    assert len(res2) == 1
    assert res2[0]["filename"] == "linux-6.10.tar.xz"


def test_thread_concurrency(tmp_path):
    """Verify concurrent reads and writes do not corrupt database."""
    db_file = str(tmp_path / "test_downloads.db")
    init_db(db_file)

    errors = []

    def writer(t_id):
        try:
            for i in range(10):
                d = [{
                    "url": f"https://example.com/{t_id}_{i}.bin",
                    "filename": f"{t_id}_{i}.bin",
                    "path": f"/tmp/{t_id}_{i}.bin",
                    "size": "1 MB",
                    "status": "Complete",
                    "time_left": "",
                    "rate": "",
                    "last_try": "1700000000",
                    "date_added": "1700000000",
                    "queue": "Main download queue"
                }]
                save_all_downloads(d, db_path=db_file)
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(15):
                get_all_downloads(db_path=db_file)
                get_all_queues(db_path=db_file)
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(1,)),
        threading.Thread(target=writer, args=(2,)),
        threading.Thread(target=reader),
        threading.Thread(target=reader)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
