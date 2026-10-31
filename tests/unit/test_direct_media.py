"""Unit tests for the Direct (no yt-dlp / no FFmpeg) media download method."""

import os

import pytest


class StubDaemonManager:
    def __init__(self, running_after_start=True):
        self.running = False
        self.running_after_start = running_after_start
        self.start_calls = 0

    def is_running(self):
        return self.running

    def start(self, *args, **kwargs):
        self.start_calls += 1
        self.running = self.running_after_start
        return self.running


class StubStatusBar:
    def __init__(self, events):
        self.events = events
        self.messages = []

    def showMessage(self, message, timeout=0):
        self.events.append("status_message")
        self.messages.append((message, timeout))


class StubMainWindow:
    def __init__(self, daemon):
        self.aria2_daemon_manager = daemon
        self.events = []
        self.download_calls = []
        self.status_bar = StubStatusBar(self.events)

    def start_aria2_daemon(self, *args, **kwargs):
        self.events.append("start_aria2_daemon")
        self.aria2_daemon_manager.running = self.aria2_daemon_manager.running_after_start

    def start_download(self, url, **kwargs):
        self.events.append("start_download")
        self.download_calls.append((url, kwargs))

    def on_file_info_fetched(self, file_info):
        # Simulate the real dialog flow: user clicks "Start Download" and
        # forward all recorded start_download arguments.
        url = file_info.pop("url")
        self.start_download(url, **file_info)

    def statusBar(self):
        return self.status_bar

    def tr(self, text):
        return text


@pytest.fixture
def stub_window(monkeypatch, tmp_path):
    from core.media import direct

    monkeypatch.setattr(direct, "_resolve_save_dir", lambda filename: str(tmp_path))
    daemon = StubDaemonManager()
    window = StubMainWindow(daemon)
    monkeypatch.setattr(
        "core.aria2_daemon.get_aria2_daemon_manager", lambda: daemon, raising=False
    )
    window.daemon = daemon
    window.save_dir = tmp_path
    return window


class TestIsDirectMethod:
    def test_accepts_only_direct(self):
        from core.media.direct import is_direct_method

        assert is_direct_method("direct") is True
        assert is_direct_method(" Direct ") is True
        assert is_direct_method("standard") is False
        assert is_direct_method("") is False
        assert is_direct_method(None) is False


class TestIsDirectDownloadableUrl:
    def test_accepts_plain_media_files(self):
        from core.media.direct import is_direct_downloadable_url

        assert is_direct_downloadable_url("https://rr1---sn.googlevideo.com/videoplayback?expire=1&itag=18")
        assert is_direct_downloadable_url("https://example.com/clip.mp4")
        assert is_direct_downloadable_url("https://example.com/clip.webm")
        assert is_direct_downloadable_url("http://example.com/track.m4a")

    def test_rejects_manifests_and_non_http_urls(self):
        from core.media.direct import is_direct_downloadable_url

        assert not is_direct_downloadable_url("https://example.com/master.m3u8")
        assert not is_direct_downloadable_url("https://example.com/manifest.mpd?token=1")
        assert not is_direct_downloadable_url("blob:https://example.com/uuid")
        assert not is_direct_downloadable_url("javascript:alert(1)")
        assert not is_direct_downloadable_url("data:video/mp4;base64,AAAA")
        assert not is_direct_downloadable_url("https://example.com/")
        assert not is_direct_downloadable_url("https://example.com")
        assert not is_direct_downloadable_url("https://example.com/page.html")
        assert not is_direct_downloadable_url("")
        assert not is_direct_downloadable_url(None)


class TestBuildDirectFilename:
    def test_strips_path_hostile_characters(self):
        from core.media.direct import build_direct_filename

        name = build_direct_filename('My: "great" / clip?', "https://x.com/v.mp4", "mp4")
        assert "/" not in name
        assert ":" not in name
        assert '"' not in name
        assert "?" not in name
        assert name.endswith(".mp4")

    def test_prefers_requested_extension(self):
        from core.media.direct import build_direct_filename

        assert build_direct_filename("Song", "https://x.com/a.mp4", "m4a").endswith(".m4a")
        assert build_direct_filename("Song", "https://x.com/a.mp4", ".webm").endswith(".webm")

    def test_infers_extension_from_url(self):
        from core.media.direct import build_direct_filename

        assert build_direct_filename("Clip", "https://x.com/path/clip.webm").endswith(".webm")

    def test_defaults_to_mp4_for_signed_urls(self):
        from core.media.direct import build_direct_filename

        name = build_direct_filename("Clip", "https://x.com/videoplayback?expire=1")
        assert name.endswith(".mp4")

    def test_replaces_generic_titles(self):
        from core.media.direct import build_direct_filename

        assert build_direct_filename("youtube", "https://x.com/v.mp4").startswith("video")
        assert build_direct_filename("", "https://x.com/v.mp4").startswith("video")

    def test_does_not_duplicate_extension_from_title(self):
        from core.media.direct import build_direct_filename

        assert build_direct_filename("Holiday.mp4", "https://x.com/v.mp4") == "Holiday.mp4"

    def test_caps_long_titles(self):
        from core.media.direct import build_direct_filename

        name = build_direct_filename("A" * 400, "https://x.com/v.mp4")
        assert len(name) <= 100
        assert name.endswith(".mp4")


class TestStartDirectDownload:
    def test_unsupported_url_falls_through_without_dispatch(self, stub_window):
        from core.media.direct import start_direct_download

        handled = start_direct_download(
            stub_window, {"url": "https://example.com/master.m3u8", "title": "Clip"}
        )

        assert handled is False
        assert stub_window.events == []
        assert stub_window.download_calls == []

    def test_page_extract_no_longer_defers_direct_stream_urls(self, stub_window):
        from core.media.direct import start_direct_download

        # pageExtract no longer defers; resolved stream URLs are dispatched directly
        # (the extension resolves YouTube page URLs server-side via /resolve-direct
        # before sending them here).
        handled = start_direct_download(
            stub_window,
            {
                "url": "https://rr1---sn.googlevideo.com/videoplayback?expire=1&itag=18",
                "title": "Clip",
                "pageExtract": True,
                "audioUrl": "",
            },
        )

        assert handled is True
        assert len(stub_window.download_calls) == 1
        sent_url, kwargs = stub_window.download_calls[0]
        assert sent_url == "https://rr1---sn.googlevideo.com/videoplayback?expire=1&itag=18"

    def test_dispatches_url_unchanged_to_aria2(self, stub_window):
        from core.media.direct import start_direct_download

        url = "https://rr1---sn.googlevideo.com/videoplayback?expire=1&itag=18&sig=abc"
        handled = start_direct_download(
            stub_window,
            {
                "url": url,
                "title": "My Clip",
                "ext": "mp4",
                "sizeStr": "12 MB",
                "userAgent": "TestAgent/1.0",
                "cookies": "a=1",
                "referrer": "https://www.youtube.com/watch?v=1",
            },
        )

        assert handled is True
        assert len(stub_window.download_calls) == 1
        sent_url, kwargs = stub_window.download_calls[0]
        assert sent_url == url
        assert kwargs["prefetch"] is False
        assert kwargs["supports_range"] is True
        assert kwargs["custom_filename"].endswith(".mp4")
        assert kwargs["size_data"] == ("12 MB",)
        assert kwargs["referer"] == "https://www.youtube.com/watch?v=1"
        assert kwargs["user_agent"] == "TestAgent/1.0"
        assert kwargs["cookies"] == "a=1"

    def test_start_aria2_daemon_runs_before_dispatch(self, stub_window):
        from core.media.direct import start_direct_download

        assert stub_window.daemon.is_running() is False
        start_direct_download(stub_window, {"url": "https://x.com/v.mp4", "title": "Clip"})

        assert stub_window.events == ["start_aria2_daemon", "start_download"]
        assert stub_window.daemon.is_running() is True

    def test_running_daemon_is_not_restarted(self, stub_window):
        from core.media.direct import start_direct_download

        stub_window.daemon.running = True
        start_direct_download(stub_window, {"url": "https://x.com/v.mp4", "title": "Clip"})

        assert stub_window.events == ["start_download"]

    def test_unavailable_aria2_cancels_without_falling_through(self, stub_window):
        from core.media.direct import start_direct_download

        stub_window.daemon.running_after_start = False
        handled = start_direct_download(
            stub_window, {"url": "https://x.com/v.mp4", "title": "Clip"}
        )

        assert handled is True
        assert stub_window.download_calls == []
        assert "status_message" in stub_window.events
        assert stub_window.events.index("start_aria2_daemon") < stub_window.events.index(
            "status_message"
        )
        assert "Aria2" in stub_window.status_bar.messages[0][0]

    def test_audio_goes_to_music_category(self, stub_window, monkeypatch, tmp_path):
        from core.media import direct

        created = {}

        def fake_resolve(filename):
            created["filename"] = filename
            created["dir"] = str(tmp_path / "Music")
            os.makedirs(created["dir"], exist_ok=True)
            return created["dir"]

        monkeypatch.setattr(direct, "_resolve_save_dir", fake_resolve)
        direct.start_direct_download(
            stub_window, {"url": "https://x.com/track.m4a", "title": "Song", "ext": "m4a"}
        )

        assert created["filename"].endswith(".m4a")
        assert stub_window.download_calls[0][1]["custom_save_dir"] == created["dir"]


class TestSabrSessionDispatch:
    @staticmethod
    def _session():
        import base64

        from core.media.sabr import validate_sabr_session

        return validate_sabr_session({
            "videoId": "U-o5jaxPL-M",
            "serverAbrStreamingUrl": (
                "https://rr1---sn-ab5szn7l.googlevideo.com/videoplayback"
                "?expire=2000000000&id=U-o5jaxPL-M&sabr=1"
            ),
            "videoPlaybackUstreamerConfig": "Ct4BEqUDAv8B",
            "clientInfo": {"clientName": 1, "clientVersion": "2.20260101.00.00"},
            "formats": [
                {"itag": 299, "mimeType": "video/mp4", "contentLength": "10000000"},
                {"itag": 140, "mimeType": "audio/mp4", "contentLength": "1000000"},
            ],
            "videoItag": 299,
            "audioItag": 140,
            "requestBody": base64.b64encode(b"\x08\x01").decode(),
        })

    def test_valid_session_dispatches_without_aria2(self, stub_window):
        from core.media.direct import start_direct_download

        session = self._session()
        handled = start_direct_download(
            stub_window,
            {
                "url": session["serverAbrStreamingUrl"],
                "title": "SABR Clip",
                "ext": "mp4",
                "method": "direct",
                "sabr": session,
            },
        )

        assert handled is True
        assert "start_aria2_daemon" not in stub_window.events
        assert len(stub_window.download_calls) == 1
        sent_url, kwargs = stub_window.download_calls[0]
        assert sent_url == session["serverAbrStreamingUrl"]
        assert kwargs["sabr_session"]["videoId"] == "U-o5jaxPL-M"
        assert kwargs["supports_range"] is False
        assert kwargs["prefetch"] is False
        assert kwargs["custom_filename"].endswith(".mp4")

    def test_size_falls_back_to_session_content_lengths(self, stub_window):
        from core.media.direct import start_direct_download

        session = self._session()
        start_direct_download(
            stub_window,
            {"url": session["serverAbrStreamingUrl"], "title": "SABR", "ext": "mp4", "sabr": session},
        )
        _, kwargs = stub_window.download_calls[0]
        assert kwargs["size_data"][0].startswith("10.49")  # 11,000,000 bytes

    def test_invalid_session_payload_is_rejected(self, stub_window):
        from core.media.direct import start_direct_download

        handled = start_direct_download(
            stub_window,
            {
                "url": "https://rr1.sn.googlevideo.com/videoplayback?sabr=1",
                "title": "Bad",
                "sabr": {"videoId": "not-valid"},
            },
        )

        assert handled is False
        assert stub_window.download_calls == []

    def test_sabr_url_without_session_still_gated(self, stub_window):
        from core.media.direct import start_direct_download

        handled = start_direct_download(
            stub_window,
            {"url": "https://rr1.sn.googlevideo.com/videoplayback?sabr=1&itag=299", "title": "No session"},
        )
        assert handled is False
