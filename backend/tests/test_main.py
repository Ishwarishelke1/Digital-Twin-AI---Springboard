"""
tests/test_main.py — main.py's frontend-serving guard.

Real bug this covers: `dist/` existing without `dist/assets/` (an interrupted
build, a partial copy into an image layer) used to crash the whole app at
import time with an unhandled RuntimeError from StaticFiles' own constructor —
found by accident when tests_integration/ failed to even collect after a
leftover `dist/` from an earlier build was in exactly this state. The fix
checks index.html and assets/ specifically, not just that the directory exists.
"""
from pathlib import Path

from main import _is_frontend_build_complete


def test_no_dist_directory_at_all(tmp_path):
    assert _is_frontend_build_complete(tmp_path / "does-not-exist") is False


def test_empty_dist_directory(tmp_path):
    assert _is_frontend_build_complete(tmp_path) is False


def test_dist_with_only_index_html_no_assets(tmp_path):
    """The exact scenario that used to crash the app at import time."""
    (tmp_path / "index.html").write_text("<html></html>")
    assert _is_frontend_build_complete(tmp_path) is False


def test_dist_with_only_assets_no_index_html(tmp_path):
    (tmp_path / "assets").mkdir()
    assert _is_frontend_build_complete(tmp_path) is False


def test_dist_with_assets_as_a_file_not_a_directory(tmp_path):
    """A stray file named `assets` (not the real build output directory)
    must not be mistaken for it."""
    (tmp_path / "assets").write_text("not a real assets directory")
    (tmp_path / "index.html").write_text("<html></html>")
    assert _is_frontend_build_complete(tmp_path) is False


def test_a_genuine_complete_build(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('ok')")
    (tmp_path / "index.html").write_text("<html></html>")
    assert _is_frontend_build_complete(tmp_path) is True
