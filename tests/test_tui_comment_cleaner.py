"""Smoke tests for TUI imports and comment_cleaner engines (no live terminal UI)."""

from __future__ import annotations

from pathlib import Path


def test_import_tui_app() -> None:
    import codingutils.tui.app  # noqa: F401


def test_scan_engine_helpers() -> None:
    from codingutils.tui.builtin_modules.comment_cleaner.scan_engine import (
        make_context,
        make_signature,
    )

    lines = ["line0\n", "line1\n", "line2\n"]
    before, after = make_context(lines, 2, 2, before=1, after=1)
    assert "line0" in before
    assert "line2" in after

    sig = make_signature("line", "text", "b", "a", None)
    assert len(sig) == 40


def test_scan_text_file_finds_line_comment(tmp_path: Path) -> None:
    from codingutils.tui.builtin_modules.comment_cleaner.decisions import DecisionsDB
    from codingutils.tui.builtin_modules.comment_cleaner.models import CleanerSettings
    from codingutils.tui.builtin_modules.comment_cleaner.scan_engine import scan_text_file

    p = tmp_path / "sample.py"
    p.write_text("# hello\nx = 1\n", encoding="utf-8")
    settings = CleanerSettings()
    decisions = DecisionsDB.empty()
    items = scan_text_file(p, settings, decisions, rel_path="sample.py", prefixes=[])
    assert len(items) >= 1
    assert any("hello" in it.text for it in items)


def test_preview_diff_no_deletions_unchanged(tmp_path: Path) -> None:
    from codingutils.tui.builtin_modules.comment_cleaner.apply_engine import preview_diff_file
    from codingutils.tui.builtin_modules.comment_cleaner.models import CleanerSettings

    p = tmp_path / "sample.py"
    p.write_text("# keep\ny = 2\n", encoding="utf-8")
    pr = preview_diff_file(p, "sample.py", CleanerSettings(), delete_keys=set())
    assert pr.error == ""
    assert pr.changed is False
    assert pr.removed_count == 0
