"""
DownloadStore Module for Bengal Download Manager.
Acts as the authoritative in-memory domain repository for downloads.
Provides state mutation methods, query mechanisms, and reactive Qt signals,
decoupling download entity state from presentation widgets.
"""

import copy
import logging
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("bengal.core.download_store")


class DownloadStore(QObject):
    """
    In-memory store managing active and completed Download records.
    Acts as the source of truth between SQLite persistence and presentation views.
    """

    itemAdded = pyqtSignal(dict)
    itemUpdated = pyqtSignal(str, dict)  # (key, updates)
    itemRemoved = pyqtSignal(str)        # key
    storeReset = pyqtSignal()
    downloadsChanged = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._items: Dict[str, dict] = {}
        self._ordered_keys: List[str] = []

    def _make_key(self, item_data: dict) -> str:
        """Derives a stable unique identifier for a download record."""
        return item_data.get("url") or item_data.get("path") or str(id(item_data))

    def load_from_database(self) -> List[dict]:
        """Loads downloads from SQLite persistence into the in-memory repository."""
        try:
            from core.database import get_all_downloads
            records = get_all_downloads() or []
            self.set_all_items(records, persist=False)
            return self.get_all_items()
        except Exception as e:
            logger.warning("Failed to load downloads from database: %s", e)
            return []

    def save_to_database(self) -> None:
        """Persists all in-memory downloads into SQLite database."""
        try:
            from core.database import save_all_downloads
            save_all_downloads(self.get_all_items())
        except Exception as e:
            logger.warning("Failed to persist downloads to database: %s", e)

    def set_all_items(self, items: List[dict], persist: bool = False) -> None:
        """Replaces all in-memory items with the provided list."""
        self._items.clear()
        self._ordered_keys.clear()
        for it in items:
            k = self._make_key(it)
            self._items[k] = copy.deepcopy(it)
            self._ordered_keys.append(k)

        if persist:
            self.save_to_database()

        self.storeReset.emit()
        self.downloadsChanged.emit()

    def get_all_items(self) -> List[dict]:
        """Returns deep copies of all download records in preserved sequence."""
        return [copy.deepcopy(self._items[k]) for k in self._ordered_keys if k in self._items]

    def get_item(self, key: str) -> Optional[dict]:
        """Retrieves a copy of a download record by key or URL."""
        if key in self._items:
            return copy.deepcopy(self._items[key])
        for k, v in self._items.items():
            if v.get("url") == key or v.get("path") == key:
                return copy.deepcopy(v)
        return None

    def count(self) -> int:
        """Returns the total number of downloads in the store."""
        return len(self._ordered_keys)

    def add_item(self, item_data: dict, persist: bool = False) -> str:
        """Appends a new download to the repository."""
        k = self._make_key(item_data)
        record = copy.deepcopy(item_data)
        self._items[k] = record
        if k not in self._ordered_keys:
            self._ordered_keys.append(k)

        if persist:
            try:
                from core.database import upsert_download
                upsert_download(record)
            except Exception as e:
                logger.warning("Failed to upsert download '%s': %s", k, e)

        self.itemAdded.emit(copy.deepcopy(record))
        self.downloadsChanged.emit()
        return k

    def update_item(self, key: str, updates: dict, persist: bool = False) -> bool:
        """Applies field updates to an existing download record."""
        target_k = None
        if key in self._items:
            target_k = key
        else:
            for k, v in self._items.items():
                if v.get("url") == key or v.get("path") == key:
                    target_k = k
                    break

        if not target_k:
            return False

        self._items[target_k].update(updates)
        updated_copy = copy.deepcopy(self._items[target_k])

        if persist:
            try:
                from core.database import upsert_download
                upsert_download(updated_copy)
            except Exception as e:
                logger.warning("Failed to persist updated download '%s': %s", target_k, e)

        self.itemUpdated.emit(target_k, copy.deepcopy(updates))
        self.downloadsChanged.emit()
        return True

    def remove_item(self, key: str, persist: bool = False) -> bool:
        """Removes a download from the repository."""
        target_k = None
        if key in self._items:
            target_k = key
        else:
            for k, v in self._items.items():
                if v.get("url") == key or v.get("path") == key:
                    target_k = k
                    break

        if not target_k:
            return False

        removed_record = self._items.pop(target_k)
        if target_k in self._ordered_keys:
            self._ordered_keys.remove(target_k)

        if persist:
            try:
                from core.database import delete_download
                delete_download(removed_record.get("url", ""), removed_record.get("path", ""))
            except Exception as e:
                logger.warning("Failed to delete download '%s': %s", target_k, e)

        self.itemRemoved.emit(target_k)
        self.downloadsChanged.emit()
        return True

    def get_active_count(self, queue_name: Optional[str] = None) -> int:
        """Computes active running downloads count from in-memory state."""
        active_statuses = {"Downloading", "Downloading...", "Resuming...", "Connecting...", "Pending..."}
        count = 0
        for it in self._items.values():
            if queue_name and it.get("queue") != queue_name:
                continue
            if it.get("status") in active_statuses:
                count += 1
        return count
