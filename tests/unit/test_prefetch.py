"""Unit tests for prefetch functionality, table duplicate prevention, and cache cleanup."""

import os
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidgetItem

from core.workers.aria2 import Aria2Worker
from core.workers.download import DownloadWorker


class TestPrefetchWorkers:
    def test_aria2_worker_prefetch_init(self, tmp_path):
        save_dir = str(tmp_path / "downloads")
        temp_dir = str(tmp_path / "cache")
        os.makedirs(save_dir, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)

        worker = Aria2Worker(
            url="https://example.com/file.rpm",
            row_index=0,
            save_dir=save_dir,
            filename="file.rpm",
            temp_dir=temp_dir,
            prefetch=True
        )
        assert worker.prefetch is True
        assert worker.save_path == os.path.join(temp_dir, "file.rpm.bdpart")
        assert worker.working_dir == temp_dir

    def test_aria2_worker_resume_from_prefetch(self, tmp_path):
        save_dir = str(tmp_path / "downloads")
        temp_dir = str(tmp_path / "cache")
        os.makedirs(save_dir, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)

        bdpart = os.path.join(temp_dir, "file.rpm.bdpart")
        bdpart_aria2 = bdpart + ".aria2"
        with open(bdpart, "wb") as f:
            f.write(b"data")
        with open(bdpart_aria2, "wb") as f:
            f.write(b"control")

        worker = Aria2Worker(
            url="https://example.com/file.rpm",
            row_index=0,
            save_dir=save_dir,
            filename="file.rpm",
            temp_dir=temp_dir,
            prefetch=False,
            allow_resume=True
        )
        assert os.path.exists(bdpart)
        assert os.path.exists(bdpart_aria2)

    def test_download_worker_prefetch_init(self, tmp_path):
        save_dir = str(tmp_path / "downloads")
        temp_dir = str(tmp_path / "cache")
        os.makedirs(save_dir, exist_ok=True)
        os.makedirs(temp_dir, exist_ok=True)

        worker = DownloadWorker(
            url="https://example.com/file.rpm",
            download_id=0,
            save_dir=save_dir,
            filename="file.rpm",
            temp_dir=temp_dir,
            prefetch=True
        )
        assert worker.prefetch is True
        assert worker.save_path == os.path.join(temp_dir, "file.rpm.bdpart")
        assert worker.state_file == worker.save_path + ".bdmx"


class TestMainWindowPrefetchLogic:
    @pytest.fixture
    def main_win(self, qapp):
        from ui.main_window import MainWindow
        with patch("ui.main_window.ensure_aria2", return_value=True):
            win = MainWindow(start_ipc=False)
            win.settings["show_complete_dialog"] = False
            yield win
            win.close()

    def test_add_completed_download_no_duplicates(self, main_win, tmp_path):
        url = "https://example.com/turbodm.rpm"
        filename = "turbodm.rpm"
        save_path = str(tmp_path / filename)

        # Initial row count
        init_count = main_win.download_table.rowCount()

        # Add completed download
        main_win._add_completed_download(
            url=url,
            filename=filename,
            save_path=save_path,
            size_str="4.00 MB",
            size_bytes=4194304,
            category="Programs",
            referer="https://example.com",
            user_agent="TestUA",
            cookies=""
        )

        assert main_win.download_table.rowCount() == init_count + 1
        item = main_win.download_table.item(0, 0)
        assert item.text() == filename
        assert main_win.download_table.item(0, 2).text() == "Complete"

        # Calling again for the same URL must UPDATE in-place and not create a duplicate row
        main_win._add_completed_download(
            url=url,
            filename=filename,
            save_path=save_path,
            size_str="4.00 MB",
            size_bytes=4194304,
            category="Programs",
            referer="https://example.com",
            user_agent="TestUA",
            cookies=""
        )

        assert main_win.download_table.rowCount() == init_count + 1

    def test_add_completed_download_with_show_complete_dialog(self, main_win, tmp_path):
        main_win.settings["show_complete_dialog"] = True
        url = "https://example.com/turbodm2.rpm"
        filename = "turbodm2.rpm"
        save_path = str(tmp_path / filename)

        init_count = main_win.download_table.rowCount()
        main_win._add_completed_download(
            url=url,
            filename=filename,
            save_path=save_path,
            size_str="2.78 MB",
            size_bytes=2911351,
            category="Programs",
            referer="https://example.com",
            user_agent="TestUA",
            cookies=""
        )

        assert main_win.download_table.rowCount() == init_count + 1
        assert len(main_win.active_complete_dialogs) == 1

    def test_clear_cache_files_comprehensive(self, main_win, tmp_path):
        temp_dir = str(tmp_path / "cache")
        save_dir = str(tmp_path / "downloads")
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(save_dir, exist_ok=True)

        config = {"temp_dir": temp_dir}

        # Create various cache and partial files
        files_to_create = [
            os.path.join(temp_dir, "test.rpm"),
            os.path.join(temp_dir, "test.rpm.aria2"),
            os.path.join(temp_dir, "test.rpm.bdpart"),
            os.path.join(temp_dir, "test.rpm.bdpart.aria2"),
            os.path.join(temp_dir, "test.rpm.bdpart.bdmx"),
            os.path.join(temp_dir, "test.rpm.tmpbdm"),
            os.path.join(temp_dir, "test.rpm.tmpbdm.bdmx"),
            os.path.join(save_dir, "test.rpm.aria2"),
            os.path.join(save_dir, "test.rpm.bdpart"),
        ]
        for f in files_to_create:
            with open(f, "wb") as fh:
                fh.write(b"dummy")

        item = QTableWidgetItem("test.rpm")
        item.setData(Qt.ItemDataRole.UserRole + 1, os.path.join(save_dir, "test.rpm"))

        main_win._clear_cache_files(item, config)

        for f in files_to_create:
            assert not os.path.exists(f), f"File {f} was not cleaned up"

    def test_stop_worker_entry_bare_worker(self, main_win):
        mock_worker = MagicMock(spec=DownloadWorker)
        mock_worker.isRunning.return_value = False

        main_win._stop_worker_entry(mock_worker)
        mock_worker.stop.assert_called_once()
        mock_worker.wait.assert_called()
