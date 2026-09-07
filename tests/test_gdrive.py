from core.services.gdrive_handler import (
    is_gdrive_url,
    merge_gdrive_cookies,
    extract_filename_from_headers,
    format_bytes,
    extract_gdrive_confirmation
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

def test_extract_gdrive_confirmation_form_dangerous_file():
    html = """
    <html>
    <head><title>virus_sample.exe - Google Drive</title></head>
    <body>
    <div class="uc-warning-caption">
      Google Drive has detected that <strong>virus_sample.exe</strong> is infected with a virus.
      Only download this file if you understand the risks.
    </div>
    <form id="download-form" action="https://drive.usercontent.google.com/download" method="get">
      <input type="hidden" name="id" value="1UsrzxxPoqqq4lJoruEW53h44S0ES-H9z">
      <input type="hidden" name="export" value="download">
      <input type="hidden" name="authuser" value="0">
      <input type="hidden" name="confirm" value="t">
      <input type="hidden" name="uuid" value="b8e07d87-abf9-49ee-9ae3-eff338bae1bf">
      <input type="hidden" name="at" value="AMrWOn1RU0Ue7DNMKbS5STxxrOHB:1788744255715">
      <input type="submit" id="uc-download-link" value="Download infected file">
    </form>
    </body>
    </html>
    """
    url, filename = extract_gdrive_confirmation(html, "https://drive.google.com/uc?id=1UsrzxxPoqqq4lJoruEW53h44S0ES-H9z&export=download")
    assert url is not None
    assert "drive.usercontent.google.com/download" in url
    assert "id=1UsrzxxPoqqq4lJoruEW53h44S0ES-H9z" in url
    assert "confirm=t" in url
    assert "uuid=b8e07d87-abf9-49ee-9ae3-eff338bae1bf" in url
    assert "at=AMrWOn1RU0Ue7DNMKbS5STxxrOHB%3A1788744255715" in url or "at=AMrWOn1RU0Ue7DNMKbS5STxxrOHB:1788744255715" in url
    assert filename == "virus_sample.exe"

def test_extract_gdrive_confirmation_anchor():
    html = """
    <div>
      <span class="uc-name-size"><a href="/uc?export=download&id=abc123456789012345">large_archive.zip</a> (2.5GB)</span>
      <a id="uc-download-link" class="btn" href="https://drive.usercontent.google.com/download?id=abc123456789012345&export=download">Download anyway</a>
    </div>
    """
    url, filename = extract_gdrive_confirmation(html, "https://drive.google.com/uc?id=abc123456789012345&export=download")
    assert url is not None
    assert "confirm=t" in url
    assert filename == "large_archive.zip"

def test_extract_gdrive_confirmation_json():
    html = """
    <script>
      var data = {"downloadUrl":"https:\\/\\/drive.usercontent.google.com\\/download?id=test123456789012345\\u0026export=download"};
    </script>
    """
    url, filename = extract_gdrive_confirmation(html, "https://drive.google.com/uc?id=test123456789012345")
    assert url is not None
    assert "confirm=t" in url
    assert "id=test123456789012345" in url

