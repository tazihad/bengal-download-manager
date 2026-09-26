"""
Unit tests for VideoThumbnailManager and video thumbnail functionality.
"""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.video_thumbnail import (
    get_ffmpeg_path,
    get_thumbnail_cache_path,
    delete_thumbnail,
    cleanup_orphaned_thumbnails,
    generate_video_thumbnail_sync,
    VideoThumbnailManager,
)


def test_get_ffmpeg_path_prefers_local():
    """Verify get_ffmpeg_path searches app directories and system PATH."""
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        path = get_ffmpeg_path()
        assert path is not None
        assert "ffmpeg" in path


def test_thumbnail_cache_path_generation():
    """Verify deterministic cache filename generation based on file stats."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"test video content dummy")
        tmp_name = f.name

    try:
        thumb1 = get_thumbnail_cache_path(tmp_name)
        thumb2 = get_thumbnail_cache_path(tmp_name)
        assert thumb1 == thumb2
        assert thumb1.endswith(".jpg")
        assert "thumb_" in thumb1
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def test_delete_thumbnail():
    """Verify cached thumbnail is purged correctly on deletion."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
        vf.write(b"video content")
        vname = vf.name

    try:
        thumb_path = get_thumbnail_cache_path(vname)
        assert thumb_path is not None
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        with open(thumb_path, "wb") as f:
            f.write(b"fake jpg")
        assert os.path.exists(thumb_path)

        delete_thumbnail(vname)
        assert not os.path.exists(thumb_path)
    finally:
        if os.path.exists(vname):
            os.remove(vname)


def test_cleanup_orphaned_thumbnails():
    """Verify orphaned thumbnails are cleared when they don't match any active filepath."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf1, \
         tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf2:
        vf1.write(b"video 1")
        vf2.write(b"video 2")
        v1 = vf1.name
        v2 = vf2.name

    try:
        thumb1 = get_thumbnail_cache_path(v1)
        thumb2 = get_thumbnail_cache_path(v2)
        os.makedirs(os.path.dirname(thumb1), exist_ok=True)
        with open(thumb1, "wb") as f:
            f.write(b"thumb1")
        with open(thumb2, "wb") as f:
            f.write(b"thumb2")

        # Keep only v1 as active
        cleanup_orphaned_thumbnails({v1})
        assert os.path.exists(thumb1)
        assert not os.path.exists(thumb2)
    finally:
        for f in (v1, v2):
            if os.path.exists(f):
                os.remove(f)


def test_generate_video_thumbnail_sync_mock(monkeypatch):
    """Verify generate_video_thumbnail_sync invokes ffmpeg with fast seek and low resource params."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf, \
         tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as of:
        vf.write(b"video data")
        video_path = vf.name
        out_path = of.name

    try:
        called_cmd = []

        def mock_run(cmd, **kwargs):
            called_cmd.extend(cmd)
            # simulate output creation
            with open(out_path, "wb") as f:
                f.write(b"dummy image data")
            res = MagicMock()
            res.returncode = 0
            return res

        monkeypatch.setattr("subprocess.run", mock_run)
        success = generate_video_thumbnail_sync(video_path, out_path, ffmpeg_bin="/mock/ffmpeg")
        assert success is True
        assert "-ss" in called_cmd
        assert "-vframes" in called_cmd
        assert "-threads" in called_cmd
        assert "1" in called_cmd
        assert "-an" in called_cmd
        assert "-sn" in called_cmd
        assert "-dn" in called_cmd
    finally:
        for p in (video_path, out_path):
            if os.path.exists(p):
                os.remove(p)


def test_youtube_video_id_and_thumbnail_url():
    """Verify YouTube video ID extraction and thumbnail URL generation."""
    from core.video_thumbnail import extract_youtube_video_id, get_youtube_thumbnail_url

    test_cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share", "dQw4w9WgXcQ"),
        ("https://example.com/video.mp4", None),
    ]

    for url, expected_id in test_cases:
        vid = extract_youtube_video_id(url)
        assert vid == expected_id
        thumb = get_youtube_thumbnail_url(url)
        if expected_id:
            assert thumb == f"https://i.ytimg.com/vi/{expected_id}/hqdefault.jpg"
        else:
            assert thumb is None


def test_register_thumbnail_file():
    """Verify register_thumbnail_file associates custom thumbnail with a video path."""
    from core.video_thumbnail import register_thumbnail_file, get_thumbnail_cache_path

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        tf.write(b"jpeg dummy data")
        thumb_file = tf.name

    video_path = "/home/user/Videos/downloading_video.mp4"
    try:
        register_thumbnail_file(video_path, thumb_file)
        cached_p = get_thumbnail_cache_path(video_path)
        assert cached_p is not None
        assert os.path.exists(cached_p)
    finally:
        if os.path.exists(thumb_file):
            os.remove(thumb_file)

