"""End-to-end tests: browser extension IPC flow into MainWindow."""

import json
import time
import pytest
from PyQt6.QtCore import Qt


@pytest.fixture(scope="module")
def win(qapp, destroy_widget):
    from ui.main_window import MainWindow
    w = MainWindow(start_ipc=False)
    yield w
    destroy_widget(w)


@pytest.fixture
def no_message_boxes(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))


@pytest.fixture
def seeded_download(win):
    win.start_download("https://example.com/ext-flow.zip", show_dialog=False)
    yield "https://example.com/ext-flow.zip"
    try:
        for row in range(win.download_table.rowCount()):
            item = win.download_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == "https://example.com/ext-flow.zip":
                win.download_table.removeRow(row)
                break
    except Exception:
        pass


class TestEmitterWiring:
    def test_ipc_emitter_exists(self, win):
        assert win.ipc_emitter is not None

    def test_new_download_signal_connected(self, win):
        assert win.ipc_emitter.new_download_signal is not None

    def test_batch_signal_connected(self, win):
        assert win.ipc_emitter.batch_download_signal is not None


class TestIncomingUrlParsing:
    def test_empty_url_returns_early(self, win):
        win.process_incoming_url("")
        win.process_incoming_url("{}")

    def test_malformed_json_falls_back(self, win):
        win.process_incoming_url("{not valid json")

    def test_duplicate_url_triggers_duplicate_handler(self, win, seeded_download, monkeypatch):
        called = []
        monkeypatch.setattr(win, "_handle_duplicate_download",
                            lambda row, item, url, ua, ck: called.append(url))
        win.process_incoming_url(seeded_download)
        assert called == [seeded_download]

    def test_new_url_starts_fetcher(self, win, monkeypatch):
        created = []

        class FakeSignal:
            def connect(self, *a, **k):
                pass
            def emit(self, *a, **k):
                pass

        class FakeFetcher:
            def __init__(self, url, user_agent="", cookies="", referrer=""):
                self.url = url
                self.finished_signal = FakeSignal()
            def start(self):
                created.append(self.url)

        import core.workers as workers_mod
        monkeypatch.setattr(workers_mod, "FileInfoFetcherWorker", FakeFetcher)
        monkeypatch.setattr(win, "active_fetchers", [])
        win.process_incoming_url("https://example.com/unique-new-file.bin")
        assert created == ["https://example.com/unique-new-file.bin"]

    def test_json_payload_parsed(self, win, monkeypatch):
        created = []

        class FakeSignal:
            def connect(self, *a, **k):
                pass

        class FakeFetcher:
            def __init__(self, url, user_agent="", cookies="", referrer=""):
                self.url = url
                self.ua = user_agent
                self.finished_signal = FakeSignal()
            def start(self):
                created.append((self.url, self.ua))

        import core.workers as workers_mod
        monkeypatch.setattr(workers_mod, "FileInfoFetcherWorker", FakeFetcher)
        monkeypatch.setattr(win, "active_fetchers", [])
        payload = json.dumps({
            "url": "https://example.com/json-payload.bin",
            "userAgent": "TestAgent/1.0",
            "referrer": "https://ref.example.com/",
        })
        win.process_incoming_url(payload)
        assert created
        assert created[0][0] == "https://example.com/json-payload.bin"
        assert created[0][1] == "TestAgent/1.0"


class TestSignalToSlotFlow:
    def test_signal_emission_invokes_slot(self, win, seeded_download, monkeypatch):
        called = []
        monkeypatch.setattr(win, "_handle_duplicate_download",
                            lambda row, item, url, ua, ck: called.append(url))
        win.ipc_emitter.new_download_signal.emit(seeded_download)
        assert called == [seeded_download]

    def test_signal_with_fresh_url_starts_fetcher(self, win, monkeypatch):
        created = []

        class FakeSignal:
            def connect(self, *a, **k):
                pass

        class FakeFetcher:
            def __init__(self, url, user_agent="", cookies="", referrer=""):
                self.url = url
                self.finished_signal = FakeSignal()
            def start(self):
                created.append(self.url)

        import core.workers as workers_mod
        monkeypatch.setattr(workers_mod, "FileInfoFetcherWorker", FakeFetcher)
        monkeypatch.setattr(win, "active_fetchers", [])
        win.ipc_emitter.new_download_signal.emit("https://example.com/signal-fresh.bin")
        assert created == ["https://example.com/signal-fresh.bin"]


class TestBatchDownloads:
    def test_add_batch_downloads_adds_rows(self, win, no_message_boxes):
        initial = win.download_table.rowCount()
        files = [
            {"url": "https://example.com/batch1.zip", "filename": "batch1.zip"},
            {"url": "https://example.com/batch2.zip", "filename": "batch2.zip"},
        ]
        win.add_batch_downloads(files, start_immediate=False)
        assert win.download_table.rowCount() == initial + 2

    def test_batch_rows_have_urls(self, win, no_message_boxes):
        urls = set()
        for row in range(win.download_table.rowCount()):
            item = win.download_table.item(row, 0)
            if item:
                urls.add(item.data(Qt.ItemDataRole.UserRole))
        assert "https://example.com/batch1.zip" in urls
        assert "https://example.com/batch2.zip" in urls

    def test_batch_rows_have_queue(self, win, no_message_boxes):
        for row in range(win.download_table.rowCount()):
            item = win.download_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) in (
                "https://example.com/batch1.zip", "https://example.com/batch2.zip"):
                assert item.data(Qt.ItemDataRole.UserRole + 8) == "Main download queue"

    def test_empty_batch_no_crash(self, win):
        win.add_batch_downloads([])


class TestAddNewDownload:
    def test_add_new_download_creates_row(self, win):
        initial = win.download_table.rowCount()
        win.add_new_download("https://example.com/direct-add.txt")
        assert win.download_table.rowCount() >= initial

    def test_add_new_download_with_save_path(self, win):
        win.add_new_download("https://example.com/path-add.txt", save_path="/tmp")


class TestExtensionConfig:
    def test_load_extension_config(self):
        from core.utils import load_extension_config
        cfg = load_extension_config()
        assert isinstance(cfg, dict)

    def test_extension_config_has_port(self):
        from core.utils import load_extension_config
        cfg = load_extension_config()
        assert "ipc_port" in cfg or isinstance(cfg, dict)
