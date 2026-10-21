#!/usr/bin/env python3
"""
AppStream Release Notes Generator for Bengal Download Manager.
Extracts Conventional Commits between Git tags and formats them into
valid AppStream XML (<description><p>...</p><ul><li>...</li></ul></description>).
"""

import html
import os
import re
import subprocess
from typing import List, Optional, Tuple

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Conventional Commit mapping to user-friendly category labels
CATEGORY_MAP = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "perf": "Performance",
    "refactor": "Improvements",
    "docs": "Documentation",
}

# User-friendly scope mappings
SCOPE_MAP = {
    "ui": "User Interface",
    "gui": "User Interface",
    "i18n": "Translations",
    "theme": "Appearance",
    "core": "Engine",
    "download": "Downloads",
    "wayland": "Wayland Display",
    "snap": "Snap Package",
    "flatpak": "Flatpak Package",
    "portal": "System Integration",
    "proxy": "Proxy",
}

# Commits to exclude from user-facing AppStream changelog
EXCLUDE_PREFIXES = (
    "chore(release)",
    "chore: release",
    "merge pull request",
    "merge branch",
    "test",
    "ci",
)


def get_sorted_git_tags() -> List[str]:
    """Returns all 'v*' semver tags sorted descending."""
    try:
        raw = subprocess.check_output(
            ["git", "tag", "-l", "v*"],
            cwd=ROOT_DIR,
            text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()
        tags = [t.strip() for t in raw if t.strip()]

        def parse_tag(t: str) -> Tuple[int, int, int, int, int]:
            m = re.match(r"^v?([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([a-zA-Z]+)\.([0-9]+))?$", t)
            if not m:
                return (0, 0, 0, 0, 0)
            is_stable = 1 if not m.group(4) else 0
            return (
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                is_stable,
                int(m.group(5) or 0),
            )

        tags.sort(key=parse_tag, reverse=True)
        return tags
    except Exception:
        return []


def get_previous_tag(target_version: Optional[str] = None) -> Optional[str]:
    """
    Finds the tag preceding target_version.
    If target_version is None or matches the highest tag, returns the tag before it.
    """
    tags = get_sorted_git_tags()
    if not tags:
        return None

    if not target_version:
        return tags[0] if len(tags) > 0 else None

    clean_target = target_version.lstrip("v")
    for i, tag in enumerate(tags):
        if tag.lstrip("v") == clean_target:
            if i + 1 < len(tags):
                return tags[i + 1]
            return None
    # If target_version is not yet tagged, previous tag is the latest existing tag
    return tags[0]


def get_git_commits(from_ref: Optional[str], to_ref: str = "HEAD") -> List[str]:
    """Retrieves commit subjects between from_ref and to_ref."""
    try:
        if from_ref:
            cmd = ["git", "log", f"{from_ref}..{to_ref}", "--pretty=format:%s"]
        else:
            cmd = ["git", "log", "-n", "10", "--pretty=format:%s", to_ref]
        raw = subprocess.check_output(cmd, cwd=ROOT_DIR, text=True, stderr=subprocess.DEVNULL)
        return [c.strip() for c in raw.splitlines() if c.strip()]
    except Exception:
        return []


def make_human_friendly(text: str) -> str:
    """Replaces common developer jargon with user-centric descriptions."""
    # Simplify technical phrases
    replacements = [
        (r"\bctypes function prototype cache mutation segfault\b", "crash on KDE Plasma"),
        (r"\bsegfault\b", "crash"),
        (r"\bdeadlock\b", "freeze"),
        (r"\bmnemonics\b", "keyboard shortcuts"),
        (r"\bconjuncts\b", "complex characters"),
        (r"\bCSD\b", "window title bar"),
        (r"\bIPC\b", "browser communication"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def clean_commit_message(msg: str) -> Optional[str]:
    """
    Cleans commit message: strips git chore noise, extracts scope and description.
    Formats into human-friendly, user-facing release notes.
    Returns None if commit should be excluded.
    """
    lower = msg.lower()
    for prefix in EXCLUDE_PREFIXES:
        if lower.startswith(prefix):
            return None

    # Match conventional commit pattern: type(scope)!: message or type: message
    m = re.match(r"^([a-zA-Z]+)(?:\(([^)]+)\))?!?:\s*(.+)$", msg)
    if m:
        ctype = m.group(1).lower()
        if ctype in ("test", "tests", "ci", "chore"):
            return None

        scope_raw = m.group(2)
        desc = m.group(3).strip()

        # Simplify technical jargon
        desc = make_human_friendly(desc)

        # Capitalize first letter of description
        if desc:
            desc = desc[0].upper() + desc[1:]

        if scope_raw:
            friendly_scope = SCOPE_MAP.get(scope_raw.lower(), scope_raw.capitalize())
            return f"{friendly_scope}: {desc}"
        elif ctype in CATEGORY_MAP:
            return f"{desc}"
        return f"{ctype.capitalize()}: {desc}"

    # Non-conventional commit - clean and return
    clean = make_human_friendly(msg.strip())
    return clean[0].upper() + clean[1:] if clean else None


def generate_notes_from_git(
    version: str,
    from_ref: Optional[str] = None,
    to_ref: str = "HEAD",
) -> List[str]:
    """Generates a list of human-readable bullet points for the release notes."""
    if not from_ref:
        from_ref = get_previous_tag(version)

    commits = get_git_commits(from_ref, to_ref)
    notes: List[str] = []
    seen = set()

    for c in commits:
        cleaned = clean_commit_message(c)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            notes.append(cleaned)

    if not notes:
        notes.append("General maintenance, bug fixes, and performance improvements.")

    return notes


def format_markdown_notes(
    version: str,
    notes: List[str],
) -> str:
    """Formats release notes as clean Markdown bullet points."""
    clean_version = version.lstrip("v").split("-")[0]
    lines = [
        f"### 🚀 What's New in v{clean_version}\n"
    ]
    for item in notes:
        lines.append(f"- {item}")
    return "\n".join(lines)


def format_appstream_xml(
    version: str,
    release_date: str,
    notes: List[str],
    indent: str = "    ",
) -> str:
    """
    Builds a strictly valid AppStream <release> tag with <description><ul><li>.
    Escapes special XML characters.
    """
    clean_version = version.lstrip("v").split("-")[0]
    lines = [
        f'{indent}<release version="{clean_version}" date="{release_date}">',
        f"{indent}  <description>",
        f"{indent}    <p>Bengal Download Manager {clean_version} changes:</p>",
        f"{indent}    <ul>",
    ]
    for item in notes:
        escaped_item = html.escape(item)
        lines.append(f"{indent}      <li>{escaped_item}</li>")
    lines.append(f"{indent}    </ul>")
    lines.append(f"{indent}  </description>")
    lines.append(f"{indent}</release>")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import datetime

    parser = argparse.ArgumentParser(description="Generate AppStream & Markdown release notes.")
    parser.add_argument("--version", default="0.2.99", help="Target release version")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Release date (YYYY-MM-DD)")
    parser.add_argument("--from-tag", default=None, help="Starting git tag")
    parser.add_argument("--to-ref", default="HEAD", help="Ending git ref")
    parser.add_argument("--format", choices=["xml", "markdown"], default="xml", help="Output format")
    args = parser.parse_args()

    bullet_notes = generate_notes_from_git(args.version, args.from_tag, args.to_ref)
    if args.format == "markdown":
        print(format_markdown_notes(args.version, bullet_notes))
    else:
        xml_output = format_appstream_xml(args.version, args.date, bullet_notes)
        print(xml_output)
