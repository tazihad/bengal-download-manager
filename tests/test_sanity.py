"""
Sanity tests for Bengal Download Manager.
Verifies core package imports, version definitions, and basic utility functions.
"""

import os
import sys


def test_version_defined():
    """Verify application version is defined and non-empty."""
    from core.version import VERSION
    assert VERSION
    assert isinstance(VERSION, str)


def test_core_imports():
    """Verify core modules can be imported without errors."""
    import core.utils
    import core.config
    import core.categories
    from core.utils import format_bytes
    from core.categories import parse_size_to_bytes
    assert format_bytes(1024) == "1.00 KB"
    assert parse_size_to_bytes("1.00 KB") == 1024


def test_media_extractor_helpers():
    """Verify media extractor resolution and container helpers."""
    from core.media.extractor import get_effective_resolution, determine_media_container_ext
    # Landscape
    assert get_effective_resolution({"width": 1920, "height": 1080}) == 1080
    # Portrait
    assert get_effective_resolution({"width": 1080, "height": 1920}) == 1080
    assert get_effective_resolution({"width": 720, "height": 1280}) == 720
    # Container resolution
    assert determine_media_container_ext([{"ext": "mp4"}, {"ext": "webm"}]) == ".mkv"
    assert determine_media_container_ext([{"ext": "mp4"}, {"ext": "m4a"}]) == ".mp4"
    assert determine_media_container_ext([{"ext": "webm"}, {"ext": "webm"}]) == ".webm"
