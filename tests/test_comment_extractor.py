import json
import logging
from pathlib import Path

import codingutils.comment_extractor as ce


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def make_config(tmp_path: Path, **overrides) -> ce.CommentExtractorConfig:
    base = dict(
        directories=[str(tmp_path)],
        include_pattern="*",
        recursive=False,
        use_gitignore=False,
        custom_gitignore=None,
        remove_comments=False,
        preview_mode=False,
        use_cache=True,
        export_file=None,
        log_file=None,
    )
    base.update(overrides)
    return ce.CommentExtractorConfig(**base)


class DummyProgress:
    def __init__(self, total: int, description: str = "X", **kwargs):
        self.total = total
        self.description = description

    def __enter__(self):
        return self

    def update(self, n: int = 1):
        return None

    def __exit__(self, exc_type, exc, tb):
        return None


# =============================================================================
# CommentStyle
# =============================================================================

def test_commentstyle_from_override_variants():
    s1 = ce.CommentStyle.from_override("//")
    assert s1.line_markers == ("//",)
    assert s1.block_markers == ()

    s2 = ce.CommentStyle.from_override("/* */")
    assert s2.line_markers == ()
    assert s2.block_markers == (("/*", "*/"),)

    s3 = ce.CommentStyle.from_override("// /* */")
    assert s3.line_markers == ("//",)
    assert s3.block_markers == (("/*", "*/"),)


def test_commentstyle_from_extension_monkeypatch(monkeypatch):
    def fake_get_comment_style(_path):
        return {"line": "#", "block": ("/*", "*/"), "alt_block": ("'''", "'''")}

    monkeypatch.setattr(ce.FileContentDetector, "get_comment_style", fake_get_comment_style)

    style = ce.CommentStyle.from_extension(".x")
    assert style.line_markers == ("#",)
    assert ("/*", "*/") in style.block_markers
    assert ("'''", "'''") in style.block_markers


# =============================================================================
# _StringScanner
# =============================================================================

def test_string_scanner_ignores_tokens_inside_quotes_and_handles_escapes():
    s = r'print("a // b")  // real'
    pos, tok = ce._StringScanner.find_next_token_outside_strings(s, 0, ["//"])
    assert tok == "//"
    assert s[pos:] == "// real"

    s2 = r'print("a \" // still") // real'
    pos2, tok2 = ce._StringScanner.find_next_token_outside_strings(s2, 0, ["//"])
    assert tok2 == "//"
    assert s2[pos2:] == "// real"


# =============================================================================
# CommentScanner (line)
# =============================================================================

def test_scanner_line_comment_remove():
    style = ce.CommentStyle(line_markers=("#",), block_markers=())
    scanner = ce.CommentScanner(style)

    out, matches, removed = scanner.scan_and_strip(
        ["x = 1  # hi\n"], remove=True, should_remove=lambda m: True
    )

    assert removed == 1
    assert len(matches) == 1
    assert matches[0].kind == "line"
    assert matches[0].text == "hi"
    assert out == ["x = 1\n"]


def test_scanner_line_comment_inside_string_not_detected():
    style = ce.CommentStyle(line_markers=("#",), block_markers=())
    scanner = ce.CommentScanner(style)

    out, matches, removed = scanner.scan_and_strip(
        ['x = "# not a comment"\n'], remove=True, should_remove=lambda m: True
    )
    assert removed == 0
    assert matches == []
    assert out == ['x = "# not a comment"\n']


def test_scanner_line_exclude_pattern_does_not_remove_second_hash():
    style = ce.CommentStyle(line_markers=("#",), block_markers=())
    scanner = ce.CommentScanner(style, exclude_comment_pattern="##")

    out, matches, removed = scanner.scan_and_strip(
        ["## keep\n", "# remove\n"],
        remove=True,
        should_remove=lambda m: True,
    )

    assert removed == 1
    assert len(matches) == 1
    assert matches[0].text == "remove"
    assert out == ["## keep\n", "\n"]


def test_scanner_should_remove_false_keeps_comment_even_in_remove_mode():
    style = ce.CommentStyle(line_markers=("#",), block_markers=())
    scanner = ce.CommentScanner(style)

    out, matches, removed = scanner.scan_and_strip(
        ["x = 1  # hi\n"], remove=True, should_remove=lambda m: False
    )

    assert removed == 0
    assert len(matches) == 1
    assert out == ["x = 1  # hi\n"]


# =============================================================================
# CommentScanner (block)
# =============================================================================

def test_scanner_block_single_line_remove():
    style = ce.CommentStyle(line_markers=(), block_markers=(("/*", "*/"),))
    scanner = ce.CommentScanner(style)

    out, matches, removed = scanner.scan_and_strip(
        ["a /*c*/ b\n"], remove=True, should_remove=lambda m: True
    )

    assert removed == 1
    assert len(matches) == 1
    assert matches[0].kind == "block"
    assert matches[0].text == "c"
    assert out == ["a  b\n"]


def test_scanner_block_multi_line_remove_preserves_line_count():
    style = ce.CommentStyle(line_markers=(), block_markers=(("/*", "*/"),))
    scanner = ce.CommentScanner(style)

    out, matches, removed = scanner.scan_and_strip(
        ["a /* start\n", "middle\n", "end */ b\n"],
        remove=True,
        should_remove=lambda m: True,
    )

    assert removed == 1
    assert len(matches) == 1
    assert out == ["a\n", "\n", " b\n"]


def test_scanner_block_then_line_comment_same_line_removed_both():
    style = ce.CommentStyle(line_markers=("//",), block_markers=(("/*", "*/"),))
    scanner = ce.CommentScanner(style)

    out, matches, removed = scanner.scan_and_strip(
        ["a /*c*/ b //d\n"], remove=True, should_remove=lambda m: True
    )

    assert removed == 2
    assert [m.kind for m in matches] == ["block", "line"]
    assert out == ["a  b\n"]


def test_scanner_unclosed_block_comment_remove_warns_and_strips_to_eof(caplog):
    style = ce.CommentStyle(line_markers=(), block_markers=(("/*", "*/"),))
    scanner = ce.CommentScanner(style)

    with caplog.at_level(logging.WARNING):
        out, matches, removed = scanner.scan_and_strip(
            ["x /* start\n", "still in block\n"],
            remove=True,
            should_remove=lambda m: True,
        )

    assert "Unclosed block comment" in caplog.text
    assert matches == []
    # remove-mode: prefix kept, rest blank lines
    assert out == ["x\n", "\n"]
    assert removed == 0


def test_scanner_unclosed_block_comment_keep_original(caplog):
    style = ce.CommentStyle(line_markers=(), block_markers=(("/*", "*/"),))
    scanner = ce.CommentScanner(style)

    with caplog.at_level(logging.WARNING):
        out, matches, removed = scanner.scan_and_strip(
            ["x /* start\n", "still in block\n"],
            remove=False,
            should_remove=lambda m: True,
        )

    assert "Unclosed block comment" in caplog.text
    assert matches == []
    assert out == ["x /* start\n", "still in block\n"]
    assert removed == 0


# =============================================================================
# Config warnings (langdetect)
# =============================================================================

def test_config_warns_when_langdetect_missing(monkeypatch, caplog, tmp_path):
    monkeypatch.setattr(ce, "LANGDETECT_AVAILABLE", False)
    with caplog.at_level(logging.WARNING):
        _ = make_config(tmp_path, language_filter="en")
    assert "langdetect not available" in caplog.text


# =============================================================================
# CommentProcessor.process_file
# =============================================================================

def test_processor_skips_binary(monkeypatch, tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"\x00\x01\x02")

    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.BINARY)

    proc = ce.CommentProcessor(make_config(tmp_path))
    removed, matches = proc.process_file(f)
    assert removed == 0
    assert matches == []


def test_processor_extract_only_no_write(monkeypatch, tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1  # hi\n", encoding="utf-8")

    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    monkeypatch.setattr(ce.FileContentDetector, "detect_encoding", lambda _p: "utf-8")

    def boom_safe_write(*args, **kwargs):
        raise AssertionError("safe_write must not be called in extract-only mode")

    monkeypatch.setattr(ce, "safe_write", boom_safe_write)

    proc = ce.CommentProcessor(make_config(tmp_path, remove_comments=False))
    removed, matches = proc.process_file(f)

    assert removed == 0
    assert len(matches) == 1
    assert matches[0].text == "hi"
    assert f.read_text(encoding="utf-8") == "x = 1  # hi\n"


def test_processor_remove_writes(monkeypatch, tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1  # hi\n", encoding="utf-8")

    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    monkeypatch.setattr(ce.FileContentDetector, "detect_encoding", lambda _p: "utf-8")

    captured = {}

    def fake_safe_write(path, content, encoding="utf-8", backup=True, **kwargs):
        captured["path"] = Path(path)
        captured["content"] = content
        Path(path).write_text(content, encoding=encoding)
        return True

    monkeypatch.setattr(ce, "safe_write", fake_safe_write)

    proc = ce.CommentProcessor(make_config(tmp_path, remove_comments=True, preview_mode=False))
    removed, matches = proc.process_file(f)

    assert removed == 1
    assert len(matches) == 1
    assert captured["content"] == "x = 1\n"
    assert f.read_text(encoding="utf-8") == "x = 1\n"


def test_processor_preview_mode_does_not_write(monkeypatch, tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1  # hi\n", encoding="utf-8")

    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    monkeypatch.setattr(ce.FileContentDetector, "detect_encoding", lambda _p: "utf-8")

    def boom_safe_write(*args, **kwargs):
        raise AssertionError("safe_write must not be called in preview mode")

    monkeypatch.setattr(ce, "safe_write", boom_safe_write)

    proc = ce.CommentProcessor(make_config(tmp_path, remove_comments=True, preview_mode=True))
    removed, matches = proc.process_file(f)

    assert removed == 1  # would remove
    assert len(matches) == 1
    assert f.read_text(encoding="utf-8") == "x = 1  # hi\n"


def test_process_file_unicode_decode_fallback(monkeypatch, tmp_path, caplog):
    f = tmp_path / "bad.txt"
    f.write_bytes(b"\xff\xfe# comment\n")  # invalid utf-8

    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    monkeypatch.setattr(ce.FileContentDetector, "detect_encoding", lambda _p: "utf-8")

    proc = ce.CommentProcessor(make_config(tmp_path))

    with caplog.at_level(logging.WARNING):
        removed, matches = proc.process_file(f)

    assert "falling back to latin-1" in caplog.text
    assert removed == 0
    assert len(matches) == 1


def test_processor_cache_by_mtime(monkeypatch, tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1  # hi\n", encoding="utf-8")

    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    monkeypatch.setattr(ce.FileContentDetector, "detect_encoding", lambda _p: "utf-8")

    created = {"n": 0}

    class StubScanner:
        def __init__(self, *a, **k):
            created["n"] += 1

        def scan_and_strip(self, lines, *, remove, should_remove):
            m = ce.CommentMatch(
                kind="line",
                start_line=1,
                start_col=7,
                end_line=1,
                end_col=11,
                raw="# hi",
                text="hi",
            )
            return list(lines), [m], 0

    monkeypatch.setattr(ce, "CommentScanner", StubScanner)

    proc = ce.CommentProcessor(make_config(tmp_path, use_cache=True))
    r1 = proc.process_file(f)
    r2 = proc.process_file(f)

    assert created["n"] == 1
    assert r1[0] == r2[0] == 0
    assert r1[1][0].text == "hi"


# =============================================================================
# Language filter
# =============================================================================

def test_language_filter_match_and_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "LANGDETECT_AVAILABLE", True)
    monkeypatch.setattr(ce, "detect", lambda s: "en")

    proc = ce.CommentProcessor(make_config(tmp_path, language_filter="en", remove_comments=True))
    assert proc._should_remove_comment("This is a sufficiently long english sentence.") is True

    monkeypatch.setattr(ce, "detect", lambda s: "ru")
    assert proc._should_remove_comment("This is a sufficiently long english sentence.") is False


def test_language_filter_short_text_does_not_call_detect(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "LANGDETECT_AVAILABLE", True)

    def boom(_s):
        raise AssertionError("detect() must not be called")

    monkeypatch.setattr(ce, "detect", boom)

    proc = ce.CommentProcessor(make_config(tmp_path, language_filter="en", min_langdetect_len=50, remove_comments=True))
    assert proc._should_remove_comment("short") is True


def test_language_filter_exception_defaults_to_remove(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "LANGDETECT_AVAILABLE", True)

    class DummyLangDetectException(Exception):
        pass

    monkeypatch.setattr(ce, "LangDetectException", DummyLangDetectException)

    def raise_exc(_s):
        raise DummyLangDetectException("fail")

    monkeypatch.setattr(ce, "detect", raise_exc)

    proc = ce.CommentProcessor(make_config(tmp_path, language_filter="en", remove_comments=True))
    assert proc._should_remove_comment("This is a sufficiently long sentence for detection.") is True


def test_normalize_for_langdetect():
    s = ce.CommentProcessor._normalize_for_langdetect("def hello(): return 1 !!!")
    assert "def" not in s.lower()
    assert "return" not in s.lower()


# =============================================================================
# find_files / process_files / export
# =============================================================================

def test_find_files_integration(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x=1 #c\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nope\n", encoding="utf-8")

    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)

    proc = ce.CommentProcessor(make_config(tmp_path, include_pattern="*.py", recursive=False))
    files = proc.find_files()
    assert (tmp_path / "a.py") in files
    assert (tmp_path / "b.txt") not in files


def test_process_files_no_files(monkeypatch, tmp_path):
    proc = ce.CommentProcessor(make_config(tmp_path))
    monkeypatch.setattr(proc, "find_files", lambda: [])
    res = proc.process_files()
    assert res["total_files"] == 0


def test_process_files_export_json_jsonl_txt(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "ProgressReporter", DummyProgress)
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    monkeypatch.setattr(ce.FileContentDetector, "detect_encoding", lambda _p: "utf-8")

    (tmp_path / "a.py").write_text("x = 1  # hi\n", encoding="utf-8")

    # json
    export_json = tmp_path / "out.json"
    proc = ce.CommentProcessor(make_config(tmp_path, include_pattern="*.py", export_file=export_json))
    res = proc.process_files()
    assert res["total_files"] == 1
    payload = json.loads(export_json.read_text(encoding="utf-8"))
    assert payload["total_comments"] == 1

    # jsonl
    export_jsonl = tmp_path / "out.jsonl"
    proc2 = ce.CommentProcessor(make_config(tmp_path, include_pattern="*.py", export_file=export_jsonl))
    proc2.process_files()
    lines = export_jsonl.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 1
    assert json.loads(lines[0])["text"] == "hi"

    # txt
    export_txt = tmp_path / "out.txt"
    proc3 = ce.CommentProcessor(make_config(tmp_path, include_pattern="*.py", export_file=export_txt))
    proc3.process_files()
    assert "EXTRACTED COMMENTS REPORT" in export_txt.read_text(encoding="utf-8")


def test_export_error_is_logged(monkeypatch, tmp_path, caplog):
    proc = ce.CommentProcessor(make_config(tmp_path))
    comments = [{
        "file": "a.py",
        "relative_path": "a.py",
        "kind": "line",
        "start_line": 1,
        "start_col": 0,
        "end_line": 1,
        "end_col": 1,
        "text": "x",
        "raw": "#x",
    }]

    def bad_open(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr("builtins.open", bad_open)

    with caplog.at_level(logging.ERROR):
        proc._export_comments(comments, tmp_path / "x.txt")
    assert "Failed to export comments" in caplog.text


# =============================================================================
# Gitignore root selection
# =============================================================================

def test_create_walker_uses_first_dir_as_gitignore_root(monkeypatch, tmp_path):
    captured = {}

    class DummyGitIgnoreParser:
        def __init__(self, root_dir=None):
            captured["root_dir"] = root_dir

        def load_from_file(self, *a, **k):
            return True

    monkeypatch.setattr(ce, "GitIgnoreParser", DummyGitIgnoreParser)

    _ = ce.CommentProcessor(make_config(tmp_path, use_gitignore=True))
    assert captured["root_dir"] == tmp_path.resolve()


# =============================================================================
# CLI: parse_arguments / create_config_from_args / main
# =============================================================================

def test_parse_arguments_and_create_config(monkeypatch, tmp_path):
    argv = [
        str(tmp_path),
        "--pattern", "*.py",
        "--recursive",
        "--use-gitignore",
        "--no-gitignore",
        "--remove-comments",
        "--preview",
        "--export-comments", str(tmp_path / "c.txt"),
        "--output", str(tmp_path / "log.txt"),
        "--comment-symbols", "// /* */",
        "--exclude-comment-pattern", "##",
        "--min-langdetect-len", "42",
        "--log-file", str(tmp_path / "legacy.txt"),
    ]
    args = ce.parse_arguments(argv)
    assert args.pattern == "*.py"
    assert args.recursive is True
    assert args.no_gitignore is True

    monkeypatch.setattr(ce, "LANGDETECT_AVAILABLE", False)
    cfg = ce.create_config_from_args(args)

    assert cfg.include_pattern == "*.py"
    assert cfg.recursive is True
    assert cfg.use_gitignore is False
    assert cfg.custom_gitignore is None
    assert cfg.remove_comments is True
    assert cfg.preview_mode is True
    assert cfg.export_file == tmp_path / "c.txt"
    assert cfg.log_file == tmp_path / "log.txt"
    assert cfg.comment_symbols == "// /* */"
    assert cfg.exclude_comment_pattern == "##"
    assert cfg.min_langdetect_len == 42


def test_main_success_prints_summary(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ce, "_configure_logging", lambda *a, **k: None)

    class DummyProcessor:
        def __init__(self, cfg):
            self.cfg = cfg

        def process_files(self):
            return {"total_files": 2, "total_comments": 3, "removed_comments": 1, "comments": []}

    monkeypatch.setattr(ce, "CommentProcessor", DummyProcessor)

    rc = ce.main([str(tmp_path), "--pattern", "*.py", "--remove-comments"])
    assert rc == 0
    assert "Removed 1 comments in 2 files" in capsys.readouterr().out


def test_main_keyboard_interrupt_during_processing(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "_configure_logging", lambda *a, **k: None)

    class DummyProcessor:
        def __init__(self, cfg):
            self.cfg = cfg

        def process_files(self):
            raise KeyboardInterrupt()

    monkeypatch.setattr(ce, "CommentProcessor", DummyProcessor)
    rc = ce.main([str(tmp_path)])
    assert rc == 130


def test_main_fatal_error(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "_configure_logging", lambda *a, **k: None)

    class DummyProcessor:
        def __init__(self, cfg):
            raise RuntimeError("boom")

    monkeypatch.setattr(ce, "CommentProcessor", DummyProcessor)
    rc = ce.main([str(tmp_path)])
    assert rc == 1


# =============================================================================
# Jupyter Notebook (.ipynb) tests
# =============================================================================

def test_ipynb_basic_processing(tmp_path, monkeypatch):
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "source": ["# Comment in Python\n", "print('Hello')\n", "x = 1 + 2  # calculation"]
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    notebook_path = tmp_path / "test.ipynb"
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")
    
    config = make_config(tmp_path, include_pattern="*.ipynb", remove_comments=False)
    proc = ce.CommentProcessor(config)
    
    removed, matches = proc.process_file(notebook_path)
    
    assert removed == 0
    assert len(matches) == 2
    assert any("Comment in Python" in m.text for m in matches)
    assert any("calculation" in m.text for m in matches)


def test_ipynb_remove_comments(tmp_path, monkeypatch):
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    
    original_content = "# Comment\nprint('Hello')\n"
    notebook = {
        "cells": [{
            "cell_type": "code",
            "execution_count": 1,
            "source": original_content.splitlines(keepends=True)
        }],
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    notebook_path = tmp_path / "test.ipynb"
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")
    
    config = make_config(tmp_path, include_pattern="*.ipynb", remove_comments=True, preview_mode=False)
    proc = ce.CommentProcessor(config)
    
    removed, matches = proc.process_file(notebook_path)
    
    assert removed == 1
    assert len(matches) == 1
    
    modified_content = json.loads(notebook_path.read_text(encoding="utf-8"))
    cell_source = modified_content["cells"][0]["source"]
    if isinstance(cell_source, list):
        cell_text = "".join(cell_source)
    else:
        cell_text = cell_source
    
    assert "# Comment" not in cell_text
    assert "print('Hello')" in cell_text


def test_ipynb_preview_mode_no_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    
    original_source = "# Comment\nprint('Hello')\n"
    notebook = {
        "cells": [{
            "cell_type": "code",
            "execution_count": 1,
            "source": original_source.splitlines(keepends=True)
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    notebook_path = tmp_path / "test.ipynb"
    original_json = json.dumps(notebook)
    notebook_path.write_text(original_json, encoding="utf-8")
    
    config = make_config(tmp_path, include_pattern="*.ipynb", remove_comments=True, preview_mode=True)
    proc = ce.CommentProcessor(config)
    
    removed, matches = proc.process_file(notebook_path)
    
    assert removed == 1
    assert len(matches) == 1
    
    assert notebook_path.read_text(encoding="utf-8") == original_json


def test_ipynb_different_cell_types(tmp_path, monkeypatch):
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["# This is markdown, not processed"]
            },
            {
                "cell_type": "raw",
                "source": ["RAW data, ignored"]
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "source": ["# Comment in code cell\n", "x = 1"]
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    notebook_path = tmp_path / "test.ipynb"
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")
    
    config = make_config(tmp_path, include_pattern="*.ipynb", remove_comments=False)
    proc = ce.CommentProcessor(config)
    
    removed, matches = proc.process_file(notebook_path)
    
    assert len(matches) == 1
    assert matches[0].text == "Comment in code cell"


def test_ipynb_malformed_json_handling(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    
    notebook_path = tmp_path / "bad.ipynb"
    notebook_path.write_text("{ invalid json }", encoding="utf-8")
    
    config = make_config(tmp_path, include_pattern="*.ipynb", remove_comments=False)
    proc = ce.CommentProcessor(config)
    
    removed, matches = proc.process_file(notebook_path)
    
    assert removed == 0
    assert len(matches) == 0
    assert "Invalid JSON" in caplog.text or "ERROR" in caplog.text


def test_ipynb_unicode_support(tmp_path, monkeypatch):
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    
    notebook = {
        "cells": [{
            "cell_type": "code",
            "execution_count": 1,
            "source": ["# Russian comment: привет мир\n", "# Emoji: 🚀 ⭐ 🌟\n", "print('test')"]
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    notebook_path = tmp_path / "unicode.ipynb"
    notebook_path.write_text(json.dumps(notebook, ensure_ascii=False), encoding="utf-8")
    
    config = make_config(tmp_path, include_pattern="*.ipynb", remove_comments=False)
    proc = ce.CommentProcessor(config)
    
    removed, matches = proc.process_file(notebook_path)
    
    assert len(matches) == 2
    assert any("Russian comment: привет мир" in m.text for m in matches)
    assert any("Emoji: 🚀 ⭐ 🌟" in m.text for m in matches)


def test_ipynb_with_mixed_file_types(tmp_path, monkeypatch):
    monkeypatch.setattr(ce.FileContentDetector, "detect_file_type", lambda _p: ce.FileType.TEXT)
    
    notebook = {
        "cells": [{"cell_type": "code", "source": ["# Notebook comment\n", "x = 1"]}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    notebook_path = tmp_path / "test.ipynb"
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")
    
    py_file = tmp_path / "script.py"
    py_file.write_text("# Python comment\nprint('test')", encoding="utf-8")
    
    config = make_config(tmp_path, include_pattern="*", remove_comments=False)
    proc = ce.CommentProcessor(config)
    
    class MockProgressReporter:
        def __init__(self, total, description="", **kwargs): pass
        def __enter__(self): return self
        def update(self, n=1): pass
        def __exit__(self, exc_type, exc_val, exc_tb): pass
    
    monkeypatch.setattr(ce, "ProgressReporter", MockProgressReporter)
    
    result = proc.process_files()
    
    assert result["total_files"] == 2
    assert result["total_comments"] == 2


def test_get_kernel_language_from_language_info():
    processor = ce.CommentProcessor(make_config(Path("/tmp")))
    
    notebook_data = {
        "metadata": {
            "language_info": {
                "name": "python",
                "version": "3.9.0"
            }
        }
    }
    
    language = processor._get_kernel_language(notebook_data)
    assert language == "python"


def test_get_kernel_language_from_kernelspec_language():
    processor = ce.CommentProcessor(make_config(Path("/tmp")))
    
    notebook_data = {
        "metadata": {
            "kernelspec": {
                "language": "julia",
                "name": "julia-1.8"
            }
        }
    }
    
    language = processor._get_kernel_language(notebook_data)
    assert language == "julia"


def test_get_kernel_language_from_kernelspec_name():
    processor = ce.CommentProcessor(make_config(Path("/tmp")))
    
    notebook_data = {
        "metadata": {
            "kernelspec": {
                "name": "python3"
            }
        }
    }
    
    language = processor._get_kernel_language(notebook_data)
    assert language == "python"


def test_get_kernel_language_fallback_to_python():
    processor = ce.CommentProcessor(make_config(Path("/tmp")))
    
    notebook_data = {
        "metadata": {}
    }
    
    language = processor._get_kernel_language(notebook_data)
    assert language == "python"
