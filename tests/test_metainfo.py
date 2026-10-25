"""
Unit tests for AppStream metainfo localization (.metainfo.xml.in -> .metainfo.xml).
"""

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import scripts.i18n as i18n


TS_HEADER = '<?xml version="1.0" encoding="utf-8"?>\n<TS version="2.1">\n'


def _write_catalog(path, entries, language="bn_BD"):
    """Write a minimal Qt .ts catalog containing Metainfo messages."""
    messages = []
    for source, translation, kind in entries:
        attrs = f' type="{kind}"' if kind else ""
        messages.append(
            "        <message>\n"
            f"            <source>{source}</source>\n"
            f"            <translation{attrs}>{translation}</translation>\n"
            "        </message>"
        )
    content = (
        TS_HEADER.replace("<TS version=\"2.1\">", f'<TS version="2.1" language="{language}">')
        + "    <context>\n"
        "        <name>Metainfo</name>\n"
        + "\n".join(messages)
        + "\n    </context>\n</TS>\n"
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def test_template_and_generated_file_are_in_sync():
    """flatpak/<id>.metainfo.xml must always match the .in template + catalogs."""
    assert os.path.exists(i18n.METAINFO_TEMPLATE), "metainfo .in template is missing"
    assert i18n.generate_metainfo(write=False), (
        "flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml is out of date. "
        "Run: uv run python scripts/i18n.py metainfo"
    )


def test_template_covers_name_summary_description_and_captions():
    units = i18n.metainfo_units()
    texts = [text for _hint, text in units]

    assert "Bengal Download Manager" in texts
    assert "High speed downloader" in texts
    # One feature bullet and one screenshot caption must be translatable too
    assert any(text.startswith("Multi-threaded segment acceleration") for text in texts)
    assert any("dark mode" in text for text in texts)
    # The developer name belongs to a person and must not be exported
    assert "tazihad" not in texts


def test_release_notes_are_not_translatable():
    root = ET.parse(i18n.METAINFO_OUTPUT).getroot()
    releases = root.find("releases").findall("release")

    assert releases, "release history must not be empty"
    for release in releases:
        description = release.find("description")
        assert description is not None
        assert description.attrib.get("translate") == "no"


def test_render_injects_xml_lang_translations(tmp_path, monkeypatch):
    catalog_dir = tmp_path / "translations"
    catalog_dir.mkdir()

    _write_catalog(
        str(catalog_dir / "bdm_bn.ts"),
        [
            ("Bengal Download Manager", "বেঙ্গল ডাউনলোড ম্যানেজার", None),
            ("High speed downloader", "উচ্চ গতির ডাউনলোডার", None),
            (
                "Multi-threaded segment acceleration for maximum speed",
                "সর্বোচ্চ গতির জন্য মাল্টি-থ্রেডেড সেগমেন্ট অ্যাক্সিলারেশন",
                None,
            ),
            # Unfinished entries must be skipped, not exported half-baked
            ("Proxy support, speed limits, and automatic category sorting", "অসম্পূর্ণ", "unfinished"),
        ],
    )

    monkeypatch.setattr(i18n, "TRANSLATIONS_DIR", str(catalog_dir))
    rendered = i18n.render_metainfo()
    root = ET.fromstring(rendered.split("\n", 1)[1])

    names = {el.attrib.get(i18n.XML_LANG_ATTR): el.text for el in root.findall("name")}
    assert names.get("bn") == "বেঙ্গল ডাউনলোড ম্যানেজার"

    summaries = {el.attrib.get(i18n.XML_LANG_ATTR): el.text for el in root.findall("summary")}
    assert summaries.get("bn") == "উচ্চ গতির ডাউনলোডার"

    localized = [
        el for el in root.findall("description") if el.attrib.get(i18n.XML_LANG_ATTR) == "bn"
    ]
    assert len(localized) == 1
    bullets = [li.text for li in localized[0].iter("li")]
    assert "সর্বোচ্চ গতির জন্য মাল্টি-থ্রেডেড সেগমেন্ট অ্যাক্সিলারেশন" in bullets
    # Untranslated and unfinished strings keep the English source text
    assert "Proxy support, speed limits, and automatic category sorting" in bullets
    assert "অসম্পূর্ণ" not in rendered

    # Release notes are shared across all languages, never duplicated
    release_descriptions = [
        el for el in root.find("releases").iter("description")
        if el.attrib.get(i18n.XML_LANG_ATTR)
    ]
    assert release_descriptions == []


def test_xml_lang_uses_bcp47_tags(tmp_path, monkeypatch):
    catalog_dir = tmp_path / "translations"
    catalog_dir.mkdir()
    _write_catalog(
        str(catalog_dir / "bdm_zh_CN.ts"),
        [("High speed downloader", "高速下载器", None)],
        language="zh_CN",
    )

    monkeypatch.setattr(i18n, "TRANSLATIONS_DIR", str(catalog_dir))
    rendered = i18n.render_metainfo()

    assert 'xml:lang="zh-CN"' in rendered
    assert 'xml:lang="zh_CN"' not in rendered


def test_sync_metainfo_catalogs_adds_missing_units(tmp_path, monkeypatch):
    catalog_dir = tmp_path / "translations"
    catalog_dir.mkdir()
    catalog = catalog_dir / "bdm_en.ts"
    catalog.write_text(TS_HEADER + "</TS>\n", encoding="utf-8")

    monkeypatch.setattr(i18n, "TRANSLATIONS_DIR", str(catalog_dir))
    added = i18n.sync_metainfo_catalogs()
    assert added == len(i18n.metainfo_units())

    root = ET.parse(str(catalog)).getroot()
    context = next(ctx for ctx in root.findall("context") if ctx.findtext("name") == "Metainfo")
    sources = {message.findtext("source") for message in context.findall("message")}
    assert "Bengal Download Manager" in sources

    # Idempotent: a second run must not duplicate or rewrite anything
    assert i18n.sync_metainfo_catalogs() == 0


@pytest.mark.skipif(shutil.which("appstreamcli") is None, reason="appstreamcli not installed")
def test_generated_metainfo_validates():
    result = subprocess.run(
        ["appstreamcli", "validate", "--pedantic", "--no-net", i18n.METAINFO_OUTPUT],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
