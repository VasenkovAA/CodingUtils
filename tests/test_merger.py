import builtins
import json
from pathlib import Path

import codingutils.merger as mg


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

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


def write_text(p: Path, text: str, encoding="utf-8") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding=encoding)
    return p


def write_bytes(p: Path, data: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def make_config(tmp_path: Path, **overrides) -> mg.MergerConfig:
    base = dict(
        directories=[str(tmp_path)],
        recursive=True,
        include_pattern="*",
        max_depth=None,
        exclude_dirs=set(),
        exclude_names=set(),
        exclude_patterns=set(),
        use_gitignore=False,
        custom_gitignore=None,
        output_file=tmp_path / "merged.txt",
        encoding="utf-8",
        preview_mode=False,
        include_headers=True,
        include_metadata=True,
        compact_file_headers=False,
        add_line_numbers=False,
        remove_empty_lines=False,
        deduplicate_lines=False,
        sort_files=False,
        max_file_size=None,
        max_total_size=None,
        keep_backups=False,
        backup_dir=None,
        overwrite_backups=False,
        include_binary_placeholders=True,
        hash_binary_files=True,
        hash_chunk_size=1024,
        follow_symlinks=False,
    )
    base.update(overrides)
    return mg.MergerConfig(**base)


# =============================================================================
# parse_size_string
# =============================================================================

def test_parse_size_string_units_and_bytes():
    assert mg.parse_size_string("1KB") == 1024
    assert mg.parse_size_string("2MB") == 2 * 1024 * 1024
    assert mg.parse_size_string("1.5GB") == int(1.5 * 1024 * 1024 * 1024)
    assert mg.parse_size_string("10") == 10
    assert mg.parse_size_string("10B") == 10


# =============================================================================
# CLI parsing / config creation
# =============================================================================

def test_parse_arguments_and_create_config(tmp_path):
    args = mg.parse_arguments([
        str(tmp_path),
        "-r",
        "-p", "*.py",
        "-o", str(tmp_path / "out.txt"),
        "--encoding", "utf-8",
        "-ed", "venv",
        "-en", "*.log",
        "-ep", "docs/*",
        "-ig",
        "--no-gitignore",
        "--preview",
        "--no-headers",
        "--no-metadata",
        "--compact-file-headers",
        "--add-line-numbers",
        "--remove-empty-lines",
        "--deduplicate",
        "--sort-files",
        "--max-file-size", "10KB",
        "--max-total-size", "20KB",
        "--keep-backups",
        "--backup-dir", str(tmp_path / ".baks"),
        "--overwrite-backups",
        "--no-binary-placeholders",
        "--no-binary-hash",
        "--log-file", str(tmp_path / "run.log"),
        "-v",
    ])
    cfg = mg.create_config_from_args(args)

    assert cfg.directories == [str(tmp_path)]
    assert cfg.recursive is True
    assert cfg.include_pattern == "*.py"
    assert cfg.output_file.name == "out.txt"
    assert cfg.encoding == "utf-8"
    assert cfg.preview_mode is True
    assert cfg.include_headers is False
    assert cfg.include_metadata is False
    assert cfg.compact_file_headers is True
    assert cfg.add_line_numbers is True
    assert cfg.remove_empty_lines is True
    assert cfg.deduplicate_lines is True
    assert cfg.sort_files is True
    assert cfg.max_file_size == 10 * 1024
    assert cfg.max_total_size == 20 * 1024

    # backup-dir implies keep_backups
    assert cfg.keep_backups is True
    assert cfg.backup_dir.name == ".baks"
    assert cfg.overwrite_backups is True

    assert cfg.include_binary_placeholders is False
    assert cfg.hash_binary_files is False


# =============================================================================
# find_files / selection
# =============================================================================

def test_find_files_excludes_output_and_backup_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    write_text(tmp_path / "a.txt", "a\n")
    out_file = tmp_path / "merged.txt"
    out_file.write_text("old\n", encoding="utf-8")

    backup_dir = tmp_path / ".baks"
    write_text(backup_dir / "should_not_be_input.txt", "x\n")

    cfg = make_config(tmp_path, output_file=out_file, backup_dir=backup_dir, keep_backups=True)
    merger = mg.SmartFileMerger(cfg)

    files = merger.find_files()
    # output file excluded from inputs
    assert out_file.resolve() not in [f.resolve() for f in files]
    # backup dir excluded
    assert all(".baks" not in str(f) for f in files)


def test_select_files_max_file_and_total(tmp_path):
    # 10 bytes
    f1 = write_text(tmp_path / "f1.txt", "x" * 10)
    # 30 bytes => must be skipped by max_file_size
    f2 = write_text(tmp_path / "f2.txt", "x" * 30)
    # 20 bytes => fits max_file_size, but exceeds max_total_size after f1
    f3 = write_text(tmp_path / "f3.txt", "x" * 20)

    cfg = make_config(tmp_path, max_file_size=25, max_total_size=25)
    merger = mg.SmartFileMerger(cfg)
    merger._resolve_roots()

    selected, skipped = merger.select_files([f1, f2, f3])

    assert f1 in selected
    assert (f2, "max_file_size") in skipped
    assert (f3, "max_total_size") in skipped


def test_preview_report_mentions_skipped(tmp_path):
    f1 = write_text(tmp_path / "f1.txt", "x" * 10)
    f2 = write_text(tmp_path / "f2.txt", "x" * 20)

    cfg = make_config(tmp_path, max_total_size=15)
    merger = mg.SmartFileMerger(cfg)
    merger._resolve_roots()

    rep = merger.preview_report([f1, f2])
    assert "MERGE PREVIEW" in rep
    assert "SKIPPED" in rep
    assert "max_total_size" in rep


# =============================================================================
# merge: transforms + headers
# =============================================================================

def test_merge_transforms_line_numbers_dedupe_remove_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    # file with duplicates + empty lines
    write_text(tmp_path / "a.txt", "A\n\nA\nB\n")
    write_text(tmp_path / "b.txt", "X\n\nY\n")

    out = tmp_path / "merged.txt"

    cfg = make_config(
        tmp_path,
        output_file=out,
        include_metadata=True,
        include_headers=True,
        add_line_numbers=True,
        remove_empty_lines=True,
        deduplicate_lines=True,
        sort_files=True,
    )
    merger = mg.SmartFileMerger(cfg)
    assert merger.merge() is True

    content = out.read_text(encoding="utf-8")

    # metadata header present
    assert "MERGED FILE REPORT" in content
    assert "FILE LIST:" in content
    # per-file headers
    assert "FILE 1/" in content
    assert "Size:" in content
    assert "Encoding:" in content
    assert "Modified:" in content

    # transformed content:
    # - empty lines removed (no standalone blank from source)
    # - A deduped in a.txt (only one A line remains)
    assert "A\n" in content
    assert content.count("A\n") == 1  # note: line-numbered becomes "   1: A\n"; this checks literal
    assert "   1: A" in content
    assert "   2: B" in content


def test_compact_file_headers_omits_relpath_and_modified(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    write_text(tmp_path / "src" / "main.py", "print('hi')\n")

    out = tmp_path / "merged.txt"
    cfg = make_config(
        tmp_path,
        output_file=out,
        include_metadata=False,     # avoid relpath appearing in metadata file list
        include_headers=True,
        compact_file_headers=True,
        include_pattern="*.py",
    )

    merger = mg.SmartFileMerger(cfg)
    assert merger.merge() is True

    content = out.read_text(encoding="utf-8")
    # header uses filename, not relative path
    assert "FILE 1/1: main.py" in content
    assert "src/main.py" not in content
    # no Modified line in compact mode
    assert "Modified:" not in content


# =============================================================================
# binary behavior
# =============================================================================

def test_binary_placeholder_with_and_without_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    binf = write_bytes(tmp_path / "x.exe", b"\x00\x01\x02abc")  # noqa F841
    out = tmp_path / "merged.txt"

    # with hash
    cfg = make_config(
        tmp_path,
        output_file=out,
        include_metadata=False,
        include_headers=False,
        include_pattern="*.exe",
        hash_binary_files=True,
        include_binary_placeholders=True,
    )
    merger = mg.SmartFileMerger(cfg)
    assert merger.merge() is True
    content = out.read_text(encoding="utf-8")
    assert "[BINARY FILE: x.exe]" in content
    assert "SHA256:" in content
    assert "Binary content is not merged." in content

    # without hash
    out2 = tmp_path / "merged2.txt"
    cfg2 = make_config(
        tmp_path,
        output_file=out2,
        include_metadata=False,
        include_headers=False,
        include_pattern="*.exe",
        hash_binary_files=False,
        include_binary_placeholders=True,
    )
    merger2 = mg.SmartFileMerger(cfg2)
    assert merger2.merge() is True
    content2 = out2.read_text(encoding="utf-8")
    assert "[BINARY FILE: x.exe]" in content2
    assert "SHA256:" not in content2


def test_no_binary_placeholders(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    write_bytes(tmp_path / "x.exe", b"\x00\x01\x02abc")
    out = tmp_path / "merged.txt"

    cfg = make_config(
        tmp_path,
        output_file=out,
        include_metadata=False,
        include_headers=False,
        include_pattern="*.exe",
        include_binary_placeholders=False,
    )
    merger = mg.SmartFileMerger(cfg)
    assert merger.merge() is True
    content = out.read_text(encoding="utf-8")
    assert "[BINARY FILE SKIPPED]" in content


# =============================================================================
# decode fallback branch (force detect_encoding to return utf-8)
# =============================================================================

def test_decode_fallback_to_latin1(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    # invalid utf-8 prefix
    p = write_bytes(tmp_path / "bad.txt", b"\xff\xfeabc\n") # noqa F841
    out = tmp_path / "merged.txt"

    monkeypatch.setattr(mg.FileContentDetector, "detect_encoding", lambda _p: "utf-8")

    cfg = make_config(tmp_path, output_file=out, include_metadata=False, include_headers=False, include_pattern="*.txt")
    merger = mg.SmartFileMerger(cfg)
    assert merger.merge() is True

    content = out.read_text(encoding="utf-8")
    assert "abc" in content  # decoded somehow; latin-1 will show prefix chars too, but abc must remain


# =============================================================================
# _iter_processed_lines error branches
# =============================================================================

def test_iter_processed_lines_permission_error(monkeypatch, tmp_path):
    p = write_text(tmp_path / "secret.txt", "secret\n")

    cfg = make_config(tmp_path, include_metadata=False, include_headers=False)
    merger = mg.SmartFileMerger(cfg)
    merger._resolve_roots()

    real_open = builtins.open

    def fake_open(path, mode="r", *args, **kwargs):
        # block reading this file only
        if Path(path).resolve() == p.resolve() and "r" in mode:
            raise PermissionError("denied")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    out = "".join(list(merger._iter_processed_lines(p)))
    assert "permission denied" in out.lower()


def test_iter_processed_lines_file_not_found(tmp_path):
    missing = tmp_path / "nope.txt"
    cfg = make_config(tmp_path, include_metadata=False, include_headers=False)
    merger = mg.SmartFileMerger(cfg)
    merger._resolve_roots()

    out = "".join(list(merger._iter_processed_lines(missing)))
    assert "file not found" in out.lower()


# =============================================================================
# backups
# =============================================================================

def test_output_backup_adjacent_versioning(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    # input file
    write_text(tmp_path / "a.txt", "A\n")
    out = tmp_path / "merged.txt"

    # create existing output (so backup is made)
    out.write_text("OLD\n", encoding="utf-8")

    cfg = make_config(
        tmp_path,
        output_file=out,
        include_metadata=False,
        include_headers=False,
        keep_backups=True,
        overwrite_backups=False,
    )
    merger = mg.SmartFileMerger(cfg)
    assert merger.merge() is True

    bak = tmp_path / "merged.txt.bak"
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == "OLD\n"

    # second run should create .bak.1
    out.write_text("OLD2\n", encoding="utf-8")
    merger2 = mg.SmartFileMerger(cfg)
    assert merger2.merge() is True

    bak1 = tmp_path / "merged.txt.bak.1"
    assert bak1.exists()


def test_output_backup_dir_and_overwrite(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    write_text(tmp_path / "a.txt", "A\n")
    out = tmp_path / "merged.txt"
    out.write_text("OLD\n", encoding="utf-8")

    bd = tmp_path / ".baks"

    cfg = make_config(
        tmp_path,
        output_file=out,
        include_metadata=False,
        include_headers=False,
        keep_backups=True,
        backup_dir=bd,
        overwrite_backups=True,
    )
    merger = mg.SmartFileMerger(cfg)
    assert merger.merge() is True

    # Because out is not under cwd typically, backup path falls back to <backup_dir>/<name>.bak
    bak = bd / "merged.txt.bak"
    assert bak.exists()


# =============================================================================
# .ipynb (Jupyter Notebook) tests
# =============================================================================

def create_sample_ipynb(tmp_path: Path, name: str = "sample.ipynb") -> Path:
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["# Test Notebook\n", "This is a markdown cell."],
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "source": ["import numpy as np\n", "print('Hello')"],
                "outputs": [{"output_type": "stream", "text": ["Hello\n"]}],
            },
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3"}},
        "nbformat": 4,
        "nbformat_minor": 4,
    }

    notebook_path = tmp_path / name
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")
    return notebook_path


def test_ipynb_not_treated_as_binary(tmp_path):
    create_sample_ipynb(tmp_path)

    cfg = make_config(tmp_path, include_pattern="*.ipynb")
    merger = mg.SmartFileMerger(cfg)

    ipynb_files = list(tmp_path.glob("*.ipynb"))
    assert len(ipynb_files) == 1
    assert merger._is_binary_fast(ipynb_files[0]) is False
    assert merger._is_binary(ipynb_files[0]) is False


def test_ipynb_basic_processing(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    create_sample_ipynb(tmp_path)
    out_file = tmp_path / "merged.txt"

    cfg = make_config(
        tmp_path,
        output_file=out_file,
        include_headers=False,
        include_metadata=False,
        include_pattern="*.ipynb",
    )
    merger = mg.SmartFileMerger(cfg)

    assert merger.merge() is True
    content = out_file.read_text(encoding="utf-8")

    assert "[NOTEBOOK:" in content
    assert "# Test Notebook" in content
    assert "import numpy as np" in content
    assert "print('Hello')" in content
    lines = content.split("\n")
    assert "Hello" not in [
        line.strip()
        for line in lines
        if line.strip() and line.strip() != "print('Hello')"
    ]


def test_ipynb_extracts_markdown_and_code_only(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    notebook = {
        "cells": [
            {"cell_type": "raw", "source": ["RAW: ignored"]},
            {"cell_type": "markdown", "source": ["## Markdown cell"]},
            {
                "cell_type": "code",
                "source": ["x = 1"],
                "outputs": [{"text": ["output"]}],
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4,
    }

    notebook_path = tmp_path / "test.ipynb"
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")

    out_file = tmp_path / "merged.txt"
    cfg = make_config(
        tmp_path,
        output_file=out_file,
        include_headers=False,
        include_metadata=False,
        include_pattern="*.ipynb",
    )
    merger = mg.SmartFileMerger(cfg)

    assert merger.merge() is True
    content = out_file.read_text(encoding="utf-8")

    assert "## Markdown cell" in content
    assert "x = 1" in content
    assert "RAW: ignored" not in content
    assert "output" not in content


def test_ipynb_malformed_json_handling(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    notebook_path = tmp_path / "bad.ipynb"
    notebook_path.write_text("{ invalid json }", encoding="utf-8")

    out_file = tmp_path / "merged.txt"
    cfg = make_config(
        tmp_path,
        output_file=out_file,
        include_headers=False,
        include_metadata=False,
        include_pattern="*.ipynb",
    )
    merger = mg.SmartFileMerger(cfg)

    assert merger.merge() is True
    content = out_file.read_text(encoding="utf-8")
    assert "ERROR" in content or "Invalid JSON" in content


def test_ipynb_empty_notebook_handling(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    notebook = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 4}
    notebook_path = tmp_path / "empty.ipynb"
    notebook_path.write_text(json.dumps(notebook), encoding="utf-8")

    out_file = tmp_path / "merged.txt"
    cfg = make_config(
        tmp_path,
        output_file=out_file,
        include_headers=False,
        include_metadata=False,
        include_pattern="*.ipynb",
    )
    merger = mg.SmartFileMerger(cfg)

    assert merger.merge() is True
    content = out_file.read_text(encoding="utf-8")
    assert "0/0 cells extracted" in content


def test_ipynb_with_mixed_file_types(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    create_sample_ipynb(tmp_path)
    py_file = tmp_path / "script.py"
    py_file.write_text("# Python file\nprint('test')", encoding="utf-8")

    out_file = tmp_path / "merged.txt"
    cfg = make_config(
        tmp_path,
        output_file=out_file,
        include_pattern="*",
        include_headers=False,
        include_metadata=False,
    )
    merger = mg.SmartFileMerger(cfg)

    assert merger.merge() is True
    content = out_file.read_text(encoding="utf-8")

    assert "[NOTEBOOK:" in content
    assert "# Python file" in content


def test_ipynb_respects_file_size_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    create_sample_ipynb(tmp_path)

    cfg = make_config(
        tmp_path,
        output_file=tmp_path / "merged.txt",
        include_pattern="*.ipynb",
        max_file_size=10,
    )
    merger = mg.SmartFileMerger(cfg)

    files = merger.find_files()
    selected, skipped = merger.select_files(files)

    assert len(selected) == 0
    assert len(skipped) == 1
    assert skipped[0][1] == "max_file_size"


def test_ipynb_preview_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    create_sample_ipynb(tmp_path)

    cfg = make_config(
        tmp_path,
        output_file=tmp_path / "merged.txt",
        include_pattern="*.ipynb",
        preview_mode=True,
    )
    merger = mg.SmartFileMerger(cfg)

    result = merger.merge()
    assert result is True
    assert not cfg.output_file.exists()

    files = merger.find_files()
    preview = merger.preview_report(files)
    assert "MERGE PREVIEW" in preview
    assert "sample.ipynb" in preview


def test_ipynb_source_formats(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    notebook1 = {
        "cells": [{"cell_type": "code", "source": "x = 1\ny = 2"}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4,
    }

    notebook2 = {
        "cells": [{"cell_type": "code", "source": ["x = 1\n", "y = 2\n"]}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4,
    }

    tmp_path.joinpath("string.ipynb").write_text(
        json.dumps(notebook1), encoding="utf-8"
    )
    tmp_path.joinpath("list.ipynb").write_text(json.dumps(notebook2), encoding="utf-8")

    out_file = tmp_path / "merged.txt"
    cfg = make_config(
        tmp_path,
        output_file=out_file,
        include_headers=False,
        include_metadata=False,
        include_pattern="*.ipynb",
    )
    merger = mg.SmartFileMerger(cfg)

    assert merger.merge() is True
    content = out_file.read_text(encoding="utf-8")

    assert "x = 1" in content
    assert "y = 2" in content
    assert content.count("x = 1") == 2


def test_ipynb_unicode_support(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": [
                    "# Unicode test\n",
                    "Russian text: привет\n",
                    "Special characters: café ☕ > < &",
                ],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 4,
    }

    notebook_path = tmp_path / "unicode.ipynb"
    notebook_path.write_text(json.dumps(notebook, ensure_ascii=False), encoding="utf-8")

    out_file = tmp_path / "merged.txt"
    cfg = make_config(
        tmp_path,
        output_file=out_file,
        include_headers=False,
        include_metadata=False,
        include_pattern="*.ipynb",
    )
    merger = mg.SmartFileMerger(cfg)

    assert merger.merge() is True
    content = out_file.read_text(encoding="utf-8")

    assert "Russian text: привет" in content
    assert "café ☕" in content


# =============================================================================
# main()
# =============================================================================

def test_main_success(monkeypatch, tmp_path):
    monkeypatch.setattr(mg, "ProgressReporter", DummyProgress)

    write_text(tmp_path / "a.py", "print(1)\n")
    out = tmp_path / "out.txt"

    rc = mg.main([str(tmp_path), "-r", "-p", "*.py", "-o", str(out), "--no-metadata", "--no-headers"])
    assert rc == 0
    assert out.exists()
    assert "print(1)" in out.read_text(encoding="utf-8")


def test_main_nonexistent_path_returns_1(tmp_path):
    out = tmp_path / "out.txt"
    rc = mg.main(["/nonexistent_path_hopefully_12345", "-r", "-p", "*", "-o", str(out), "--no-metadata", "--no-headers"])
    assert rc == 1
