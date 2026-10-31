"""Unit tests for the SABR session relay (validation, capability, command build)."""

import base64
import json
import os

import pytest

from core.media import sabr


def make_session(**overrides):
    session = {
        "videoId": "U-o5jaxPL-M",
        "serverAbrStreamingUrl": (
            "https://rr1---sn-ab5szn7l.googlevideo.com/videoplayback"
            "?expire=2000000000&ip=8.8.8.8&id=U-o5jaxPL-M&sabr=1&itag=299"
        ),
        "videoPlaybackUstreamerConfig": "Ct4BEqUDAv8BIHqQALh6nQ==",
        "clientInfo": {"clientName": 1, "clientVersion": "2.20260101.00.00"},
        "formats": [
            {
                "itag": 299,
                "mimeType": "video/mp4",
                "contentLength": "10000000",
                "approxDurationMs": "60000",
            },
            {
                "itag": 140,
                "mimeType": "audio/mp4",
                "contentLength": "1000000",
                "audioTrack": {"audioIsDefault": True},
            },
        ],
        "videoItag": 299,
        "audioItag": 140,
        "requestBody": base64.b64encode(b"\x08\x01\x12\x04poTn").decode(),
    }
    session.update(overrides)
    return session


@pytest.fixture(autouse=True)
def _reset_capability_cache():
    sabr._CAPABILITY_CACHE.update(ts=0.0, value=False)
    yield
    sabr._CAPABILITY_CACHE.update(ts=0.0, value=False)


class TestValidateSabrSession:
    def test_accepts_well_formed_session(self):
        result = sabr.validate_sabr_session(make_session())
        assert result is not None
        assert result["videoId"] == "U-o5jaxPL-M"
        assert result["videoItag"] == 299
        assert result["audioItag"] == 140
        assert len(result["formats"]) == 2

    def test_validation_is_idempotent_on_normalized_output(self):
        first = sabr.validate_sabr_session(make_session())
        second = sabr.validate_sabr_session(first)
        assert second == first

    def test_accepts_audio_only_session(self):
        result = sabr.validate_sabr_session(make_session(videoItag=None))
        assert result is not None
        assert result["videoItag"] is None
        assert len(result["formats"]) == 1

    @pytest.mark.parametrize("raw", [None, "str", 42, [], {}])
    def test_rejects_non_dict_payloads(self, raw):
        assert sabr.validate_sabr_session(raw) is None

    def test_rejects_bad_video_id(self):
        assert sabr.validate_sabr_session(make_session(videoId="short")) is None
        assert sabr.validate_sabr_session(make_session(videoId="a" * 12)) is None

    def test_rejects_non_googlevideo_or_non_sabr_urls(self):
        assert sabr.validate_sabr_session(
            make_session(serverAbrStreamingUrl="https://evil.com/videoplayback?sabr=1")
        ) is None
        assert sabr.validate_sabr_session(
            make_session(serverAbrStreamingUrl="https://googlevideo.com.evil.net/videoplayback?sabr=1")
        ) is None
        assert sabr.validate_sabr_session(
            make_session(serverAbrStreamingUrl="https://rr1.sn.googlevideo.com/videoplayback?itag=140")
        ) is None
        assert sabr.validate_sabr_session(
            make_session(serverAbrStreamingUrl="http://rr1.sn.googlevideo.com/videoplayback?sabr=1")
        ) is None
        assert sabr.validate_sabr_session(
            make_session(serverAbrStreamingUrl="https://rr1.sn.googlevideo.com/videoplayback?sabr=1x")
        ) is None

    def test_rejects_hostile_ustreamer_config(self):
        assert sabr.validate_sabr_session(make_session(videoPlaybackUstreamerConfig="bad chars!")) is None
        assert sabr.validate_sabr_session(make_session(videoPlaybackUstreamerConfig="")) is None

    def test_requires_formats(self):
        assert sabr.validate_sabr_session(make_session(formats=[])) is None
        assert sabr.validate_sabr_session(make_session(formats=[{"itag": 140, "mimeType": "audio/mp4"}] * 151)) is None

    def test_requires_audio_itag_present(self):
        assert sabr.validate_sabr_session(make_session(audioItag=None)) is None
        assert sabr.validate_sabr_session(make_session(audioItag=999)) is None

    def test_rejects_video_itag_without_matching_track(self):
        assert sabr.validate_sabr_session(make_session(videoItag=137)) is None

    def test_prefers_default_audio_track_over_variants(self):
        session = make_session(formats=[
            {"itag": 299, "mimeType": "video/mp4", "contentLength": "5"},
            {"itag": 140, "mimeType": "audio/mp4", "contentLength": "5",
             "audioTrack": {"audioIsDefault": False}},
            {"itag": 140, "mimeType": "audio/mp4", "contentLength": "9",
             "audioTrack": {"audioIsDefault": True}},
            {"itag": 140, "mimeType": "audio/mp4", "contentLength": "7", "isDrc": True},
        ])
        result = sabr.validate_sabr_session(session)
        assert result is not None
        audio = [f for f in result["formats"] if f["mimeType"] == "audio/mp4"][0]
        assert audio["audioTrack"]["audioIsDefault"] is True

    def test_rejects_drc_only_audio_candidates(self):
        session = make_session(formats=[
            {"itag": 299, "mimeType": "video/mp4", "contentLength": "5"},
            {"itag": 140, "mimeType": "audio/mp4", "contentLength": "5", "isDrc": True},
        ])
        assert sabr.validate_sabr_session(session) is None

    def test_request_body_size_and_encoding_limits(self):
        assert sabr.validate_sabr_session(make_session(requestBody="!!!not b64!!!")) is None
        assert sabr.validate_sabr_session(make_session(requestBody="")) == sabr.validate_sabr_session(make_session(requestBody=None))
        huge = base64.b64encode(b"\x00" * 300000).decode()
        assert sabr.validate_sabr_session(make_session(requestBody=huge)) is None

    def test_request_body_optional(self):
        assert sabr.validate_sabr_session(make_session(requestBody=None)) is not None


class TestSessionHelpers:
    def test_session_size_bytes_sums_content_lengths(self):
        session = sabr.validate_sabr_session(make_session())
        assert sabr.session_size_bytes(session) == 11000000

    def test_helper_script_ships_beside_module(self):
        path = sabr.get_helper_path()
        assert os.path.isfile(path)
        assert path.endswith("sabr_download.mjs")


class TestRuntimeCapability:
    def test_available_when_all_pieces_present(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sabr, "get_deno_executable_path", lambda: str(tmp_path / "deno"))
        monkeypatch.setattr(sabr, "get_tool_path", lambda name: str(tmp_path / "ffmpeg"))
        assert sabr.sabr_runtime_available() is True

    def test_unavailable_without_deno(self, monkeypatch):
        monkeypatch.setattr(sabr, "get_deno_executable_path", lambda: "")
        assert sabr.sabr_runtime_available() is False

    def test_unavailable_without_ffmpeg(self, monkeypatch):
        monkeypatch.setattr(sabr, "get_deno_executable_path", lambda: "/usr/bin/deno")
        monkeypatch.setattr(sabr, "get_tool_path", lambda name: "")
        monkeypatch.setattr(sabr.shutil, "which", lambda name: None)
        assert sabr.sabr_runtime_available() is False

    def test_result_is_cached(self, monkeypatch):
        calls = []
        monkeypatch.setattr(sabr, "get_deno_executable_path", lambda: calls.append(1) or "")
        sabr.sabr_runtime_available()
        sabr.sabr_runtime_available()
        assert len(calls) == 1


class TestCommandBuild:
    def test_build_command_shape(self, monkeypatch):
        monkeypatch.setattr(sabr, "get_deno_executable_path", lambda: "/opt/bin/deno")
        cmd = sabr.build_command("/tmp/s.json", "/tmp/0.part", "/tmp/1.part")
        assert cmd[0] == "/opt/bin/deno"
        assert cmd[1:3] == ["run", "--no-lock"]
        assert "--session" in cmd and cmd[cmd.index("--session") + 1] == "/tmp/s.json"
        assert cmd[cmd.index("--video-out") + 1] == "/tmp/0.part"
        assert cmd[cmd.index("--audio-out") + 1] == "/tmp/1.part"
        assert cmd[cmd.index("--session") - 1] == sabr.get_helper_path()

    def test_write_session_file_roundtrip(self):
        session = sabr.validate_sabr_session(make_session())
        path = sabr.write_session_file(session)
        try:
            assert oct(os.stat(path).st_mode & 0o777) == "0o600"
            with open(path, encoding="utf-8") as fh:
                assert json.load(fh) == session
        finally:
            os.remove(path)


class TestSabrStreamWorkerContract:
    def test_worker_constructs_from_session(self, qapp, tmp_path):
        from core.workers.sabr_stream import SabrStreamWorker

        session = sabr.validate_sabr_session(make_session())
        worker = SabrStreamWorker(
            session, 3, str(tmp_path), "clip.mp4",
            user_agent="UA/1.0", temp_dir=str(tmp_path),
        )
        assert worker.row_index == 3
        assert worker.target_path == os.path.join(str(tmp_path), "clip.mp4")
        assert worker.total_bytes == 11000000
        assert worker.video_path.endswith(".video.mp4")
        assert worker.audio_path.endswith(".audio.m4a")
        assert worker._track_totals == {299: 10000000, 140: 1000000}

    def test_progress_event_maps_tracks(self, qapp, tmp_path):
        from core.workers.sabr_stream import SabrStreamWorker

        session = sabr.validate_sabr_session(make_session())
        worker = SabrStreamWorker(session, 0, str(tmp_path), "clip.mp4")

        progress = []
        segments = []
        worker.main_progress_signal.connect(lambda row, data: progress.append((row, data)))
        worker.segment_update_signal.connect(
            lambda idx, done, total, speed, label: segments.append((idx, done, total, label))
        )

        worker._emit_progress({
            "ev": "progress",
            "downloaded": 500000,
            "total": 11000000,
            "tracks": {"299": 450000, "140": 50000},
        })

        assert progress, "main_progress_signal was not emitted"
        row, data = progress[-1]
        assert data[0] == "clip.mp4"
        assert data[5] == 500000
        assert data[6] == 11000000
        assert segments[0][:3] == (0, 450000, 10000000)
        assert segments[1][:3] == (1, 50000, 1000000)
