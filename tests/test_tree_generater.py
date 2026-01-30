import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import codingutils.tree_generater as tg


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def make_sample_tree(tmp_path: Path) -> Path:
    """
    tmp/
      src/
        main.py        # comment
        util.js        // comment
      docs/
        readme.md
      emptydir/
      .hiddenfile
      .hiddendir/
        secret.txt
      build/
        out.bin
      app.log
      ignored.txt
    """
    write(tmp_path / "src" / "main.py", "print('hi')  # hello\n")
    write(tmp_path / "src" / "util.js", "const x = 1; // hi\n")
    write(tmp_path / "docs" / "readme.md", "# Readme\n")
    (tmp_path / "emptydir").mkdir()
    write(tmp_path / ".hiddenfile", "hidden\n")
    write(tmp_path / ".hiddendir" / "secret.txt", "secret\n")
    write(tmp_path / "build" / "out.bin", "binary-ish\n")
    write(tmp_path / "app.log", "log\n")
    write(tmp_path / "ignored.txt", "ignore me\n")
    return tmp_path


def make_config(
    tmp_path: Path,
    **overrides,
) -> tg.TreeConfig:
    base = dict(
        directories=[str(tmp_path)],
        include_pattern="*",
        recursive=True,
        max_depth=None,
        exclude_dirs=set(),
        exclude_names=set(),
        exclude_patterns=set(),
        use_gitignore=False,
        custom_gitignore=None,
        output_file=None,
        format="text",
        log_file=None,
        verbose=False,
        show_hidden=False,
        show_size=False,
        show_permissions=False,
        show_last_modified=False,
        show_file_type=False,
        sort_by="name",
        sort_reverse=False,
        indent_style="tree",
        indent_size=4,
        max_width=None,
        include_statistics=False,
        include_summary=False,
        exclude_empty_dirs=False,
        follow_symlinks=False,
    )
    base.update(overrides)
    return tg.TreeConfig(**base)


# -----------------------------------------------------------------------------
# ASCII-only assertions
# -----------------------------------------------------------------------------

def assert_ascii_only(s: str) -> None:
    # allow newline/tab; otherwise ASCII range
    for ch in s:
        if ch in "\n\r\t":
            continue
        assert ord(ch) < 128, f"Non-ASCII char found: {repr(ch)}"


# =============================================================================
# Builder + TextRenderer (core)
# =============================================================================

def test_text_tree_basic_ascii(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(
        root,
        show_size=True,
        include_statistics=True,
        include_summary=True,
    )
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "PROJECT TREE:" in out
    assert "|-- " in out or "`-- " in out
    assert "src/" in out
    assert "main.py" in out
    assert "docs/" in out
    assert "STATISTICS:" in out
    assert "SUMMARY:" in out

    # ASCII only (no unicode tree, no emojis)
    assert_ascii_only(out)


def test_max_width_truncates_with_ascii_ellipsis(tmp_path):
    root = tmp_path
    longname = "a" * 100 + ".txt"
    write(root / longname, "x")

    cfg = make_config(root, show_size=False, max_width=40)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "..." in out
    assert_ascii_only(out)


def test_show_hidden_default_hides_hidden(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, show_hidden=False)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert ".hiddenfile" not in out
    assert ".hiddendir" not in out
    assert_ascii_only(out)


def test_show_hidden_true_includes_hidden(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, show_hidden=True)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert ".hiddenfile" in out
    assert ".hiddendir/" in out
    assert "secret.txt" in out
    assert_ascii_only(out)


def test_exclude_dir_excludes_entire_subtree(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, exclude_dirs={"build"})
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "build/" not in out
    assert "out.bin" not in out


def test_exclude_name_glob_excludes_files(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, exclude_names={"*.log"})
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "app.log" not in out


def test_exclude_pattern_excludes_by_relative_path(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, exclude_patterns={"docs/*"})
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "docs/" not in out
    assert "readme.md" not in out


def test_include_pattern_applies_only_to_files(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, include_pattern="*.py")
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    # dirs still exist; only files filtered
    assert "src/" in out
    assert "main.py" in out
    assert "util.js" not in out


def test_exclude_empty_dirs_prunes(tmp_path):
    root = make_sample_tree(tmp_path)

    # emptydir should disappear if exclude_empty_dirs=True
    cfg = make_config(root, exclude_empty_dirs=True)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "emptydir/" not in out


def test_metadata_permissions_mtime_filetype(tmp_path):
    root = tmp_path
    p = write(root / "x.exe", "abc")  # known binary extension shortcut
    # stable mtime
    os.utime(p, (1700000000, 1700000000))

    cfg = make_config(
        root,
        show_size=True,
        show_permissions=True,
        show_last_modified=True,
        show_file_type=True,
    )
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    # should contain size + date + permissions + "binary"
    assert "x.exe" in out
    assert "B)" in out or "KB)" in out
    assert "binary" in out
    assert "2023-" in out or "2024-" in out or "2025-" in out or "2026-" in out  # depends on timestamp/tz
    assert "(" in out and ")" in out
    assert_ascii_only(out)


# =============================================================================
# Gitignore integration
# =============================================================================

def test_gitignore_auto_discovery_excludes(tmp_path):
    root = make_sample_tree(tmp_path)
    # ignore ignored.txt
    write(root / ".gitignore", "ignored.txt\n")

    cfg = make_config(root, use_gitignore=True)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "ignored.txt" not in out


def test_gitignore_custom_file_excludes(tmp_path):
    root = make_sample_tree(tmp_path)
    gi = write(root / "custom.ignore", "app.log\n")

    cfg = make_config(root, custom_gitignore=gi, use_gitignore=False)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert "app.log" not in out


# =============================================================================
# Multiple roots (COMBINED VIEW)
# =============================================================================

def test_multiple_roots_combined_view(tmp_path):
    dir1 = tmp_path / "p1"
    dir2 = tmp_path / "p2"
    dir1.mkdir()
    dir2.mkdir()
    write(dir1 / "a.py", "x=1\n")
    write(dir2 / "b.py", "x=2\n")

    cfg = make_config(tmp_path, directories=[str(dir1), str(dir2)], show_size=False)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([dir1, dir2])

    # virtual root is not printed explicitly, but both roots must appear
    assert "p1/" in out
    assert "p2/" in out
    assert "a.py" in out
    assert "b.py" in out
    assert_ascii_only(out)


# =============================================================================
# Renderers: JSON / XML / Markdown
# =============================================================================

def test_json_renderer_produces_valid_json(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, format="json", include_statistics=True, show_size=True)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert_ascii_only(out)
    data = json.loads(out)

    assert "tree" in data
    assert "statistics" in data
    assert data["statistics"]["files"] >= 1
    assert data["tree"]["kind"] in ("directory", "file")


def test_xml_renderer_produces_parseable_xml(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, format="xml", include_statistics=True, show_size=True)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    # XML may contain utf-8 declaration; still ASCII in our produced content mostly, but paths can be ASCII
    # We ensure it's parseable.
    ET.fromstring(out.encode("utf-8"))
    assert "<project_structure" in out


def test_markdown_renderer_basic(tmp_path):
    root = make_sample_tree(tmp_path)

    cfg = make_config(root, format="markdown", include_statistics=True, max_width=80)
    gen = tg.ProjectTreeGenerator(cfg)
    out = gen.generate([root])

    assert out.startswith("# Project Structure")
    assert "- Root:" in out
    assert "## Statistics" in out
    assert_ascii_only(out)


# =============================================================================
# Output writing
# =============================================================================

def test_write_output_to_file(tmp_path):
    root = make_sample_tree(tmp_path)

    out_file = tmp_path / "tree.txt"
    cfg = make_config(root, output_file=out_file, include_statistics=False)
    gen = tg.ProjectTreeGenerator(cfg)

    content = gen.generate([root])
    gen.write_output(content)

    assert out_file.exists()
    assert "PROJECT TREE:" in out_file.read_text(encoding="utf-8")


# =============================================================================
# CLI helpers + main()
# =============================================================================

def test_parse_arguments_and_create_config(tmp_path):
    args = tg.parse_arguments(
        [
            str(tmp_path),
            "-p", "*.py",
            "-r",
            "--format", "text",
            "--show-hidden",
            "-ed", "venv",
            "-en", "*.log",
            "-ep", "docs/*",
            "-ig",
            "--no-gitignore",
            "--sort-by", "name",
            "--sort-reverse",
            "--indent-style", "tree",
            "--indent-size", "2",
            "--max-width", "100",
            "--no-statistics",
            "--no-summary",
            "--log-file", str(tmp_path / "run.log"),
            "-v",
        ]
    )
    cfg = tg.create_config_from_args(args)

    assert cfg.directories == [str(tmp_path)]
    assert cfg.include_pattern == "*.py"
    assert cfg.recursive is True
    assert cfg.show_hidden is True
    assert "venv" in cfg.exclude_dirs
    assert "*.log" in cfg.exclude_names
    assert "docs/*" in cfg.exclude_patterns
    assert cfg.use_gitignore is False  # because --no-gitignore
    assert cfg.sort_reverse is True
    assert cfg.include_statistics is False
    assert cfg.include_summary is False
    assert cfg.verbose is True
    assert cfg.log_file.name == "run.log"


def test_main_success(tmp_path, capsys):
    root = make_sample_tree(tmp_path)

    # call main with argv; make sure we pass -r and a pattern to keep it simple
    rc = tg.main([str(root), "-r", "-p", "*", "--no-statistics", "--no-summary"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "PROJECT TREE:" in out
    assert_ascii_only(out)


def test_main_nonexistent_path_returns_1(capsys):
    rc = tg.main(["/nonexistent_path_hopefully_12345", "-r"])
    assert rc == 1
    # error goes to stderr via logging, stdout may be empty
    _ = capsys.readouterr()
