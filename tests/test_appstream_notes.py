"""
Unit tests for AppStream release notes generation and version synchronization.
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET

# Ensure repository root is in sys.path so 'scripts' can be imported during tests
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.generate_appstream_notes import (
    clean_commit_message,
    format_appstream_xml,
)
from scripts.sync_version import update_metainfo


def test_clean_commit_message():
    assert clean_commit_message("feat(snap): add common-id") == "Snap Package: Add common-id"
    assert clean_commit_message("fix(ui): resolve custom title bar rendering") == "User Interface: Resolve custom title bar rendering"
    assert clean_commit_message("perf(core): optimize chunk streaming") == "Engine: Optimize chunk streaming"
    assert clean_commit_message("perf: optimize chunk streaming") == "Optimize chunk streaming"
    assert clean_commit_message("fix(wayland): resolve ctypes function prototype cache mutation segfault on KDE Plasma") == "Wayland Display: Resolve crash on KDE Plasma on KDE Plasma"
    assert clean_commit_message("chore(release): bump version to 0.2.99") is None
    assert clean_commit_message("Merge pull request #165 from tazihad/feat") is None
    assert clean_commit_message("ci: update github actions") is None
    assert clean_commit_message("regular commit message without type") == "Regular commit message without type"


def test_format_appstream_xml():
    notes = ["Feature A", "Bug fix B & C"]
    xml_str = format_appstream_xml("0.2.99", "2026-10-21", notes)
    
    # Must be valid XML
    root = ET.fromstring(xml_str)
    assert root.tag == "release"
    assert root.attrib["version"] == "0.2.99"
    assert root.attrib["date"] == "2026-10-21"
    
    desc = root.find("description")
    assert desc is not None
    ul = desc.find("ul")
    assert ul is not None
    items = ul.findall("li")
    assert len(items) == 2
    assert items[0].text == "Feature A"
    assert items[1].text == "Bug fix B & C"


def test_update_metainfo_preserves_history(monkeypatch):
    sample_metainfo = """<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>bd.com.zihad.BengalDownloadManager</id>
  <releases>
    <release version="0.2.98" date="2026-10-18">
      <description>
        <p>Changes:</p>
        <ul>
          <li>Previous note</li>
        </ul>
      </description>
    </release>
  </releases>
</component>
"""
    with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
        tf.write(sample_metainfo)
        temp_path = tf.name

    try:
        import scripts.sync_version as sv
        monkeypatch.setattr(sv, "METAINFO_FILE", temp_path)

        sv.update_metainfo("0.2.99", custom_notes=["New feature in 0.2.99"])

        with open(temp_path, "r", encoding="utf-8") as f:
            updated = f.read()

        # Both releases should be present
        assert 'release version="0.2.99"' in updated
        assert 'release version="0.2.98"' in updated
        assert 'New feature in 0.2.99' in updated
        assert 'Previous note' in updated

        # Check valid XML
        tree = ET.fromstring(updated)
        releases = tree.find("releases")
        release_elems = releases.findall("release")
        assert len(release_elems) == 2
        assert release_elems[0].attrib["version"] == "0.2.99"
        assert release_elems[1].attrib["version"] == "0.2.98"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
