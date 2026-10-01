"""Integration tests: DownloadStore + database."""

import os
import pytest


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test_downloads.db")
    return p


class TestDatabaseBasics:
    def test_init_db_creates_file(self, db_path):
        from core.database import init_db
        init_db(db_path)
        assert os.path.exists(db_path)

    def test_save_and_get_downloads(self, db_path):
        from core.database import init_db, save_all_downloads, get_all_downloads
        init_db(db_path)
        downloads = [
            {"url": "https://a.com/1.zip", "filename": "1.zip", "path": "/tmp/1.zip",
             "size": "1 MB", "status": "Complete", "queue": "Main"},
            {"url": "https://b.com/2.mp4", "filename": "2.mp4", "path": "/tmp/2.mp4",
             "size": "10 MB", "status": "Downloading", "queue": "Main"},
        ]
        save_all_downloads(downloads, db_path=db_path)
        loaded = get_all_downloads(db_path=db_path)
        assert len(loaded) == 2
        assert loaded[0]["filename"] == "1.zip"
        assert loaded[1]["filename"] == "2.mp4"

    def test_save_replaces_existing(self, db_path):
        from core.database import init_db, save_all_downloads, get_all_downloads
        init_db(db_path)
        save_all_downloads([{"url": "https://x.com/a", "filename": "a"}], db_path=db_path)
        save_all_downloads([{"url": "https://y.com/b", "filename": "b"}], db_path=db_path)
        loaded = get_all_downloads(db_path=db_path)
        assert len(loaded) == 1
        assert loaded[0]["filename"] == "b"

    def test_empty_save(self, db_path):
        from core.database import init_db, save_all_downloads, get_all_downloads
        init_db(db_path)
        save_all_downloads([], db_path=db_path)
        assert get_all_downloads(db_path=db_path) == []

    def test_queue_crud(self, db_path):
        from core.database import init_db, upsert_queue, get_all_queues, delete_queue
        init_db(db_path)
        initial = get_all_queues(db_path=db_path)
        q = {"name": "My Queue", "mode": "daily", "max_concurrent": 3, "config_json": "{}"}
        upsert_queue(q, db_path=db_path)
        queues = get_all_queues(db_path=db_path)
        assert len(queues) == len(initial) + 1
        assert any(x["name"] == "My Queue" for x in queues)

        delete_queue("My Queue", db_path=db_path)
        queues = get_all_queues(db_path=db_path)
        assert len(queues) == len(initial)

    def test_save_all_queues(self, db_path):
        from core.database import init_db, save_all_queues, get_all_queues
        init_db(db_path)
        queues = [
            {"name": "Q1", "mode": "onetime", "max_concurrent": 4},
            {"name": "Q2", "mode": "sync", "max_concurrent": 2},
        ]
        save_all_queues(queues, db_path=db_path)
        loaded = get_all_queues(db_path=db_path)
        assert len(loaded) == 2

    def test_search_downloads(self, db_path):
        from core.database import init_db, save_all_downloads, search_downloads
        init_db(db_path)
        save_all_downloads([
            {"url": "https://a.com/ubuntu.iso", "filename": "ubuntu.iso"},
            {"url": "https://b.com/arch.iso", "filename": "arch.iso"},
            {"url": "https://c.com/song.mp3", "filename": "song.mp3"},
        ], db_path=db_path)
        results = search_downloads("ubuntu", db_path=db_path)
        assert len(results) >= 1
        assert any("ubuntu" in r.get("filename", "") for r in results)


class TestDownloadStore:
    @pytest.fixture
    def store(self, qapp):
        from core.download_store import DownloadStore
        s = DownloadStore()
        yield s

    def test_initially_empty(self, store):
        assert store.count() == 0

    def test_add_item(self, store):
        key = store.add_item({"url": "https://a.com/f.zip", "filename": "f.zip"})
        assert store.count() == 1
        assert store.get_item(key) is not None

    def test_add_item_emits_signal(self, store, qapp):
        received = []
        store.itemAdded.connect(received.append)
        store.add_item({"url": "https://a.com/f.zip"})
        assert len(received) == 1

    def test_get_all_items(self, store):
        store.add_item({"url": "https://a.com/1"})
        store.add_item({"url": "https://b.com/2"})
        items = store.get_all_items()
        assert len(items) == 2

    def test_update_item(self, store):
        key = store.add_item({"url": "https://a.com/f", "status": "Downloading"})
        result = store.update_item(key, {"status": "Complete"})
        assert result is True
        assert store.get_item(key)["status"] == "Complete"

    def test_update_item_by_url(self, store):
        store.add_item({"url": "https://a.com/f", "status": "Downloading"})
        result = store.update_item("https://a.com/f", {"status": "Complete"})
        assert result is True

    def test_update_missing_returns_false(self, store):
        assert store.update_item("missing", {"status": "x"}) is False

    def test_update_emits_signal(self, store, qapp):
        key = store.add_item({"url": "https://a.com/f"})
        received = []
        store.itemUpdated.connect(lambda k, u: received.append(k))
        store.update_item(key, {"status": "Done"})
        assert received

    def test_remove_item(self, store):
        key = store.add_item({"url": "https://a.com/f"})
        result = store.remove_item(key)
        assert result is True
        assert store.count() == 0

    def test_remove_missing_returns_false(self, store):
        assert store.remove_item("missing") is False

    def test_remove_emits_signal(self, store, qapp):
        key = store.add_item({"url": "https://a.com/f"})
        received = []
        store.itemRemoved.connect(received.append)
        store.remove_item(key)
        assert received

    def test_set_all_items(self, store):
        items = [
            {"url": "https://a.com/1"},
            {"url": "https://b.com/2"},
        ]
        store.set_all_items(items)
        assert store.count() == 2

    def test_set_all_items_emits_reset(self, store, qapp):
        received = []
        store.storeReset.connect(lambda: received.append(True))
        store.set_all_items([])
        assert received

    def test_downloads_changed_signal(self, store, qapp):
        received = []
        store.downloadsChanged.connect(lambda: received.append(True))
        store.add_item({"url": "https://a.com/f"})
        assert received

    def test_get_active_count(self, store):
        store.add_item({"url": "https://a.com/1", "status": "Downloading"})
        store.add_item({"url": "https://b.com/2", "status": "Complete"})
        store.add_item({"url": "https://c.com/3", "status": "Paused"})
        assert store.get_active_count() == 1

    def test_get_active_count_with_queue_filter(self, store):
        store.add_item({"url": "https://a.com/1", "status": "Downloading", "queue": "Q1"})
        store.add_item({"url": "https://b.com/2", "status": "Downloading", "queue": "Q2"})
        assert store.get_active_count(queue_name="Q1") == 1

    def test_get_item_returns_copy(self, store):
        key = store.add_item({"url": "https://a.com/f", "status": "x"})
        item = store.get_item(key)
        item["status"] = "modified"
        assert store.get_item(key)["status"] == "x"

    def test_get_item_by_path(self, store):
        store.add_item({"url": "https://a.com/f", "path": "/tmp/file.zip"})
        item = store.get_item("/tmp/file.zip")
        assert item is not None
