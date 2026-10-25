#!/usr/bin/env python3
"""
Bengal Download Manager - AppStream Metainfo Generator
========================================================

Standalone CLI tool for regenerating
flatpak/bd.com.zihad.BengalDownloadManager.metainfo.xml from its .in template
and translation catalogs.

Usage:
    uv run python scripts/generate_metainfo.py
    uv run python scripts/generate_metainfo.py --sync-catalogs
    uv run python scripts/generate_metainfo.py --check

This script is intentionally self-contained and does not depend on
scripts/i18n.py so it can be invoked directly from CI / build pipelines
without pulling in the full i18n toolchain.
"""

import os
import re
import copy
import glob
import argparse
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATIONS_DIR = os.path.join(ROOT_DIR, "translations")

APP_ID = "bd.com.zihad.BengalDownloadManager"
METAINFO_TEMPLATE = os.path.join(ROOT_DIR, "flatpak", f"{APP_ID}.metainfo.xml.in")
METAINFO_OUTPUT = METAINFO_TEMPLATE[:-3]  # strip trailing ".in"

# ---------------------------------------------------------------------------
# AppStream metainfo constants
# ---------------------------------------------------------------------------

METAINFO_CONTEXT = "Metainfo"
XML_LANG_ATTR = "{http://www.w3.org/XML/1998/namespace}lang"

# Top-level elements that start a new readable section in the generated file.
METAINFO_SECTION_TAGS = {
    "branding",
    "developer",
    "name",
    "description",
    "supports",
    "screenshots",
    "releases",
    "provides",
    "url",
    "translation",
    "launchable",
    "icon",
    "categories",
    "content_rating",
}

# Element tag -> translator-facing hint shown in Qt Linguist.
METAINFO_TAG_HINTS = {
    "name": "Application name (product name, usually kept as-is)",
    "summary": "One-line summary shown in app catalogs",
    "p": "App description paragraph",
    "li": "App description feature bullet",
    "caption": "Screenshot caption",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_text(value: Optional[str]) -> str:
    """Collapse XML whitespace so template and catalog strings compare equal."""
    return " ".join((value or "").split())


def _metainfo_translatable_nodes(root: ET.Element) -> List[ET.Element]:
    """Return the nodes of the template that app catalogs localize."""
    nodes: List[ET.Element] = []
    for tag in ("name", "summary"):
        element = root.find(tag)
        if element is not None:
            nodes.append(element)

    description = root.find("description")
    if description is not None:
        nodes.extend(el for el in description.iter() if el.tag in ("p", "li"))

    screenshots = root.find("screenshots")
    if screenshots is not None:
        nodes.extend(screenshots.iter("caption"))

    return nodes


def metainfo_units() -> List[Tuple[str, str]]:
    """Return ordered (translator hint, English text) pairs from the template."""
    root = ET.parse(METAINFO_TEMPLATE).getroot()
    units: List[Tuple[str, str]] = []
    seen = set()
    for element in _metainfo_translatable_nodes(root):
        text = _normalize_text(element.text)
        if not text or text in seen:
            continue
        seen.add(text)
        units.append((METAINFO_TAG_HINTS.get(element.tag, "App catalog text"), text))
    return units


def sync_metainfo_catalogs() -> int:
    """
    Ensure every translations/bdm_*.ts catalog carries the current Metainfo
    strings so translators see them next to the in-app UI strings.
    Returns the number of newly added strings.
    """
    units = metainfo_units()
    if not units:
        return 0

    added_total = 0
    for ts_path in sorted(glob.glob(os.path.join(TRANSLATIONS_DIR, "bdm_*.ts"))):
        is_english = os.path.basename(ts_path) == "bdm_en.ts"
        tree = ET.parse(ts_path)
        root = tree.getroot()

        context = None
        for ctx in root.findall("context"):
            if ctx.findtext("name") == METAINFO_CONTEXT:
                context = ctx
                break
        if context is None:
            context = ET.SubElement(root, "context")
            ET.SubElement(context, "name").text = METAINFO_CONTEXT

        existing = {}
        for message in context.findall("message"):
            source = _normalize_text(message.findtext("source"))
            if source:
                existing[source] = message

        added = 0
        for hint, text in units:
            if text in existing:
                continue
            message = ET.SubElement(context, "message")
            ET.SubElement(message, "source").text = text
            translation = ET.SubElement(message, "translation")
            if is_english:
                translation.text = text
            added += 1
            added_total += 1

        if added:
            ET.indent(tree, space="  ")
            tree.write(ts_path, encoding="utf-8", xml_declaration=True)

    return added_total


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _load_metainfo_translations() -> Dict[str, Dict[str, str]]:
    """Collect {xml:lang: {english source: localized text}} from the .ts catalogs."""
    translations: Dict[str, Dict[str, str]] = {}
    for ts_path in sorted(glob.glob(os.path.join(TRANSLATIONS_DIR, "bdm_*.ts"))):
        code = os.path.basename(ts_path)[len("bdm_"):-len(".ts")]
        if code == "en":
            continue

        mapping: Dict[str, str] = {}
        try:
            root = ET.parse(ts_path).getroot()
        except ET.ParseError:
            continue
        for context in root.findall("context"):
            if context.findtext("name") != METAINFO_CONTEXT:
                continue
            for message in context.findall("message"):
                source = _normalize_text(message.findtext("source"))
                translation = message.find("translation")
                if not source or translation is None:
                    continue
                if translation.attrib.get("type") in ("unfinished", "obsolete"):
                    continue
                value = _normalize_text(translation.text)
                if value:
                    mapping[source] = value
        if mapping:
            translations[_xml_lang(code)] = mapping
    return translations


def _xml_lang(code: str) -> str:
    """Map a BCP-47-ish language code to an xml:lang value."""
    if "_" in code:
        return code
    return code


def _localized_metainfo_copy(element: ET.Element, mapping: Dict[str, str]) -> Optional[ET.Element]:
    """
    Deep-copy a translatable template element and swap in any translated text.
    Returns None when the given language has nothing to say about it.
    """
    clone = copy.deepcopy(element)
    applied = False

    if element.tag in ("name", "summary", "caption"):
        text = _normalize_text(element.text)
        if text in mapping:
            clone.text = mapping[text]
            applied = True
        return clone if applied else None

    source_nodes = [el for el in element.iter() if el.tag in ("p", "li")]
    clone_nodes = [el for el in clone.iter() if el.tag in ("p", "li")]
    for source_node, clone_node in zip(source_nodes, clone_nodes):
        text = _normalize_text(source_node.text)
        if text in mapping:
            clone_node.text = mapping[text]
            applied = True

    return clone if applied else None


def render_metainfo() -> str:
    """Render the distributable AppStream file from the template and catalogs."""
    tree = ET.parse(METAINFO_TEMPLATE)
    root = tree.getroot()
    translations = _load_metainfo_translations()

    anchors: List[ET.Element] = []
    for tag in ("name", "summary", "description"):
        element = root.find(tag)
        if element is not None:
            anchors.append(element)
    screenshots = root.find("screenshots")
    if screenshots is not None:
        anchors.extend(list(screenshots))

    parents = {child: parent for parent in root.iter() for child in parent}

    for anchor in anchors:
        parent = parents.get(anchor)
        if parent is None:
            continue
        insert_at = list(parent).index(anchor) + 1

        for lang in sorted(translations):
            clone = _localized_metainfo_copy(anchor, translations[lang])
            if clone is None:
                continue
            clone.set(XML_LANG_ATTR, lang)
            parent.insert(insert_at, clone)
            insert_at += 1

    ET.indent(tree, space="  ")
    body = ET.tostring(root, encoding="unicode")

    # Keep the generated file reviewable: blank line before each top-level
    # section, but not between xml:lang variants of the same element.
    lines: List[str] = []
    for line in body.splitlines():
        match = re.match(r"^  <([A-Za-z_]+)", line)
        if (
            lines
            and match
            and match.group(1) in METAINFO_SECTION_TAGS
            and "xml:lang=" not in line
        ):
            lines.append("")
        lines.append(line)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate_metainfo(write: bool = True) -> bool:
    """
    Regenerate flatpak/<app-id>.metainfo.xml from the .in template.
    Returns True when the on-disk file is (or was made) up to date.
    """
    if not os.path.exists(METAINFO_TEMPLATE):
        print(f"Error: template not found: {METAINFO_TEMPLATE}", file=sys.stderr)
        return False

    rendered = render_metainfo()
    current = ""
    if os.path.exists(METAINFO_OUTPUT):
        with open(METAINFO_OUTPUT, "r", encoding="utf-8") as f:
            current = f.read()

    if not write:
        return rendered == current

    if rendered != current:
        with open(METAINFO_OUTPUT, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"✓ AppStream metadata regenerated: {METAINFO_OUTPUT}")
    else:
        print(f"✓ AppStream metadata already up to date: {METAINFO_OUTPUT}")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate flatpak/<app-id>.metainfo.xml from its .in template "
            "and translation catalogs."
        )
    )
    parser.add_argument(
        "--sync-catalogs",
        action="store_true",
        help="Add missing AppStream metadata strings to translations/bdm_*.ts",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the generated metainfo.xml is out of date",
    )
    args = parser.parse_args()

    if args.sync_catalogs:
        added = sync_metainfo_catalogs()
        print(f"✓ Synced {added} AppStream metadata strings into translations/bdm_*.ts")

    if args.check:
        if generate_metainfo(write=False):
            print(f"✓ {os.path.basename(METAINFO_OUTPUT)} is up to date")
        else:
            print(
                f"✗ {os.path.basename(METAINFO_OUTPUT)} is out of date. "
                f"Run: uv run python {os.path.basename(__file__)}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        generate_metainfo()


if __name__ == "__main__":
    main()
