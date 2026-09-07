import pytest
from core.services.gdrive_handler import (
    is_gdrive_url,
    merge_gdrive_cookies,
    extract_filename_from_headers,
    format_bytes
)

def test_is_gdrive_url():
    assert is_gdrive_url("https://drive.google.com/file/d/123/view") is True
    assert is_gdrive_url("https://drive.usercontent.google.com/download?id=abc&export=download") is True
    assert is_gdrive_url("https://docs.google.com/uc?id=xyz") is True
    assert is_gdrive_url("https://example.com/file.zip") is False
    assert is_gdrive_url("") is False
    assert is_gdrive_url(None) is False

def test_extract_filename_from_headers():
    headers = {"Content-Disposition": 'attachment; filename="test_video.mkv"'}
    assert extract_filename_from_headers(headers) == "test_video.mkv"

    # RFC 5987 UTF-8
    headers_utf8 = {"Content-Disposition": "attachment; filename*=UTF-8''my%20file.pdf"}
    assert extract_filename_from_headers(headers_utf8) == "my file.pdf"

    # Fallback to URL
    assert extract_filename_from_headers({}, "https://example.com/archive.zip") == "archive.zip"
    assert extract_filename_from_headers({}, "https://drive.usercontent.google.com/download") == "Google_Drive_File"

def test_format_bytes():
    assert "8.21 MB" in format_bytes(8607934)
    assert "1.00 KB" in format_bytes(1024)
    assert "500.00 B" in format_bytes(500)

def test_merge_gdrive_cookies():
    # If cookies already contain OSID, it should retain them
    existing = "OSID=test_osid_val; __Secure-OSID=test_sec; SID=test_sid"
    merged = merge_gdrive_cookies(existing)
    assert "OSID=test_osid_val" in merged
    assert "__Secure-OSID=test_sec" in merged
