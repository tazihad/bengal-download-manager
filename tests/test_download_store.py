"""
Unit tests for the deep DownloadStore module.
"""

import pytest
from core.download_store import DownloadStore


def test_download_store_crud():
    """Verify in-memory CRUD operations and signal emissions."""
    store = DownloadStore()
    assert store.count() == 0

    added = []
    updated = []
    removed = []

    store.itemAdded.connect(lambda item: added.append(item))
    store.itemUpdated.connect(lambda key, diff: updated.append((key, diff)))
    store.itemRemoved.connect(lambda key: removed.append(key))

    # Add item
    dl_1 = {
        "url": "https://example.com/file1.zip",
        "path": "/downloads/file1.zip",
        "filename": "file1.zip",
        "status": "Queued",
        "size": "10 MB",
        "queue": "Main download queue",
    }
    key1 = store.add_item(dl_1, persist=False)
    assert key1 == "https://example.com/file1.zip"
    assert store.count() == 1
    assert len(added) == 1
    assert added[0]["filename"] == "file1.zip"

    # Get item
    retrieved = store.get_item(key1)
    assert retrieved is not None
    assert retrieved["status"] == "Queued"

    # Update item
    assert store.update_item(key1, {"status": "Downloading", "rate": "1.5 MB/s"}, persist=False)
    assert len(updated) == 1
    assert updated[0][0] == key1
    assert updated[0][1]["status"] == "Downloading"

    # Active count
    assert store.get_active_count() == 1
    assert store.get_active_count("Main download queue") == 1
    assert store.get_active_count("Other queue") == 0

    # Remove item
    assert store.remove_item(key1, persist=False)
    assert len(removed) == 1
    assert removed[0] == key1
    assert store.count() == 0
    assert store.get_item(key1) is None


def test_download_store_reset():
    """Verify set_all_items resets store and emits storeReset signal."""
    store = DownloadStore()
    resets = []
    store.storeReset.connect(lambda: resets.append(True))

    batch = [
        {"url": f"https://example.com/{i}.zip", "filename": f"{i}.zip", "status": "Complete"}
        for i in range(5)
    ]
    store.set_all_items(batch, persist=False)
    assert store.count() == 5
    assert len(resets) == 1
    items = store.get_all_items()
    assert len(items) == 5
    assert items[2]["filename"] == "2.zip"
