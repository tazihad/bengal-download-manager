"""Unit tests for core.categories."""

import time
import pytest

from core.categories import (
    get_category_for_filename,
    get_all_categories,
    parse_size_to_bytes,
    parse_time_to_sec,
    format_timestamp_relative,
    CATEGORY_EXTENSIONS,
)


class TestGetCategoryForFilename:
    def test_zip_is_compressed(self):
        assert get_category_for_filename("archive.zip") == "Compressed"

    def test_rar_is_compressed(self):
        assert get_category_for_filename("archive.rar") == "Compressed"

    def test_pdf_is_documents(self):
        assert get_category_for_filename("report.pdf") == "Documents"

    def test_mp3_is_music(self):
        assert get_category_for_filename("song.mp3") == "Music"

    def test_exe_is_programs(self):
        assert get_category_for_filename("setup.exe") == "Programs"

    def test_mp4_is_video(self):
        assert get_category_for_filename("movie.mp4") == "Video"

    def test_unknown_is_general(self):
        assert get_category_for_filename("file.xyzunknown") == "General"

    def test_empty_is_general(self):
        assert get_category_for_filename("") == "General"

    def test_none_is_general(self):
        assert get_category_for_filename(None) == "General"

    def test_case_insensitive(self):
        assert get_category_for_filename("ARCHIVE.ZIP") == "Compressed"


class TestGetAllCategories:
    def test_returns_five_categories(self):
        cats = get_all_categories()
        assert len(cats) == 5

    def test_contains_expected(self):
        cats = get_all_categories()
        for expected in ["Compressed", "Documents", "Music", "Programs", "Video"]:
            assert expected in cats

    def test_matches_extensions_dict(self):
        assert get_all_categories() == list(CATEGORY_EXTENSIONS.keys())


class TestParseSizeToBytes:
    def test_kb(self):
        assert parse_size_to_bytes("1.00 KB") == 1024.0

    def test_mb(self):
        assert parse_size_to_bytes("500 MB") == 500 * 1024 * 1024

    def test_gib(self):
        assert parse_size_to_bytes("1 GiB") == 1024 ** 3

    def test_tb(self):
        assert parse_size_to_bytes("1 TB") == 1024 ** 4

    def test_bare_bytes(self):
        assert parse_size_to_bytes("1024") == 1024.0

    def test_tilde_prefix(self):
        assert parse_size_to_bytes("~12.5 MiB") == 12.5 * 1024 * 1024

    def test_empty_returns_zero(self):
        assert parse_size_to_bytes("") == 0.0

    def test_dots_returns_zero(self):
        assert parse_size_to_bytes("...") == 0.0

    def test_none_returns_zero(self):
        assert parse_size_to_bytes(None) == 0.0

    def test_invalid_returns_zero(self):
        assert parse_size_to_bytes("Size unavailable") == 0.0


class TestParseTimeToSec:
    def test_hhmmss(self):
        assert parse_time_to_sec("01:00:00") == 3600.0

    def test_mmss(self):
        assert parse_time_to_sec("02:30") == 150.0

    def test_dashes(self):
        assert parse_time_to_sec("--") == 0.0

    def test_dots(self):
        assert parse_time_to_sec("...") == 0.0

    def test_empty(self):
        assert parse_time_to_sec("") == 0.0

    def test_hr_unit(self):
        assert parse_time_to_sec("2 hr") == 7200.0

    def test_min_unit(self):
        assert parse_time_to_sec("30 min") == 1800.0

    def test_none(self):
        assert parse_time_to_sec(None) == 0.0


class TestFormatTimestampRelative:
    def test_empty(self):
        assert format_timestamp_relative("") == "..."

    def test_dots(self):
        assert format_timestamp_relative("...") == "..."

    def test_just_now(self):
        now = str(time.time())
        assert format_timestamp_relative(now) == "Just now"

    def test_old_timestamp_formatted(self):
        old = str(time.time() - 86400)
        result = format_timestamp_relative(old)
        assert result != "..."
        assert result != "Just now"

    def test_non_numeric_passthrough(self):
        assert format_timestamp_relative("not-a-timestamp") == "not-a-timestamp"
