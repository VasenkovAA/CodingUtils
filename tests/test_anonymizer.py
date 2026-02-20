import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import re
import pytest


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from codingutils import anonymizer as anon
except ImportError as e:
    print(f"Import error: {e}")
    raise






@pytest.fixture
def sample_text_file(tmp_path):
    """Создаёт текстовый файл с тестовым содержимым."""
    f = tmp_path / "test.txt"
    f.write_text("hello world\npassword=secret\napi_key=sk-1234567890abcdef\n")
    return f


@pytest.fixture
def sample_ipynb_file(tmp_path):
    """Создаёт Jupyter notebook с разными ячейками."""
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "source": ["# This is a comment\n", "x = 1\n"],
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": ["output line\n", "secret=42\n"],
                    }
                ],
            },
            {
                "cell_type": "markdown",
                "source": ["# Markdown cell\n", "password=admin\n"],
            },
        ],
        "metadata": {"kernelspec": {"name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 4,
    }
    p = tmp_path / "test.ipynb"
    p.write_text(json.dumps(notebook), encoding="utf-8")
    return p


def make_config(tmp_path, **overrides) -> anon.AnonymizerConfig:
    """Создаёт конфиг с базовыми значениями."""
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
        builtin_rules=set(),
        rules_file=None,
        env_files=[],
        mode="replace",
        replacement="[REDACTED]",
        scan_notebooks=True,
        scan_outputs=True,
        scan_metadata=False,
        detect_system_info=False,
        username_placeholder="[USER]",
        home_placeholder="[HOME]",
        hostname_placeholder="[HOST]",
        project_root_placeholder="[PROJECT_ROOT]",
        preview_mode=False,
        export_matches=None,
        log_file=None,
        use_cache=True,
        keep_backups=False,
        backup_dir=None,
        overwrite_backups=False,
        directory_recursion={},
        split_streams=False,
    )
    base.update(overrides)
    return anon.AnonymizerConfig(**base)


class DummyProgress:
    """Заглушка для ProgressReporter."""
    def __init__(self, total, description="", **kwargs):
        self.total = total
        self.description = description

    def __enter__(self):
        return self

    def update(self, n=1):
        pass

    def __exit__(self, *args):
        pass






class TestLoadBuiltinRules:
    def test_all_groups(self):
        rules = anon.load_builtin_rules({"all"})
        assert len(rules) > 0
        names = {r.name for r in rules}
        assert "AWS Access Key" in names
        assert "Email address" in names
        assert "Windows user profile path" in names

    def test_credentials_group(self):
        rules = anon.load_builtin_rules({"credentials"})
        names = {r.name for r in rules}
        assert "AWS Access Key" in names
        assert "Email address" not in names
        assert "Windows user profile path" not in names

    def test_pii_group(self):
        rules = anon.load_builtin_rules({"pii"})
        names = {r.name for r in rules}
        assert "Email address" in names
        assert "AWS Access Key" not in names

    def test_system_group(self):
        rules = anon.load_builtin_rules({"system"})
        names = {r.name for r in rules}
        assert "Windows user profile path" in names
        assert "Email address" not in names

    def test_unknown_group(self):
        rules = anon.load_builtin_rules({"unknown"})
        assert rules == []


class TestLoadRulesFromFile:
    def test_json(self, tmp_path):
        rules_data = [
            {
                "name": "Test Rule",
                "pattern": r"test\d+",
                "replacement": "[TEST]",
                "mode": "hash",
                "case_sensitive": False,
                "whole_word": True,
                "scope": [".py", ".txt"],
                "confidence": "high",
            }
        ]
        f = tmp_path / "rules.json"
        f.write_text(json.dumps(rules_data), encoding="utf-8")

        rules = anon.load_rules_from_file(f)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.name == "Test Rule"
        assert rule.pattern == r"\btest\d+\b"
        assert rule.replacement == "[TEST]"
        assert rule.mode == "hash"
        assert rule.case_sensitive is False
        assert rule.whole_word is True
        assert rule.scope == [".py", ".txt"]
        assert rule.confidence == "high"
        assert rule.enabled is True

    def test_yaml(self, tmp_path):
        pytest.importorskip("yaml", reason="PyYAML not installed")
        import yaml
        rules_data = [
            {
                "name": "YAML Rule",
                "pattern": r"secret",
                "replacement": "[SECRET]",
            }
        ]
        f = tmp_path / "rules.yaml"
        with open(f, "w", encoding="utf-8") as fp:
            yaml.dump(rules_data, fp)

        rules = anon.load_rules_from_file(f)
        assert len(rules) == 1
        assert rules[0].name == "YAML Rule"

    def test_missing_fields_skipped(self, tmp_path):
        rules_data = [{"pattern": r"x"}]
        f = tmp_path / "bad.json"
        f.write_text(json.dumps(rules_data), encoding="utf-8")
        rules = anon.load_rules_from_file(f)
        assert rules == []

    def test_invalid_format(self, tmp_path):
        f = tmp_path / "bad.txt"
        f.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported rules file format"):
            anon.load_rules_from_file(f)


class TestLoadEnvRules:
    def test_basic(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "DB_PASSWORD=secret123\nAPI_KEY=abc456\nQUOTED='quoted_val'\n#comment\nEMPTY=\n",
            encoding="utf-8",
        )
        rules = anon.load_env_rules([env_file])
        assert len(rules) == 3
        patterns = [r.pattern for r in rules]

        assert any("secret123" in p for p in patterns)
        assert any("abc456" in p for p in patterns)
        assert any("quoted_val" in p for p in patterns)

    def test_multiple_files(self, tmp_path):
        f1 = tmp_path / ".env1"
        f1.write_text("VAL1=aaa\n")
        f2 = tmp_path / ".env2"
        f2.write_text("VAL2=bbb\n")
        rules = anon.load_env_rules([f1, f2])
        assert len(rules) == 2

    def test_duplicates(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("SAME=dup\nSAME=dup\n")
        rules = anon.load_env_rules([f])
        assert len(rules) == 1


class TestDynamicSystemRules:
    def test_username(self, monkeypatch):
        monkeypatch.setattr("os.getlogin", lambda: "testuser")
        config = make_config(Path("."), detect_system_info=True)
        rules = anon.create_dynamic_system_rules(config)
        assert any(r.name == "system_username" for r in rules)
        username_rule = next(r for r in rules if r.name == "system_username")
        assert r"\btestuser\b" in username_rule.pattern

    def test_home(self, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: Path("/home/testuser"))
        config = make_config(Path("."), detect_system_info=True, home_placeholder="[HOME]")
        rules = anon.create_dynamic_system_rules(config)
        home_rule = next((r for r in rules if r.name == "system_home"), None)
        assert home_rule is not None

        assert r"/home/testuser" in home_rule.pattern

    def test_hostname(self, monkeypatch):
        monkeypatch.setattr("socket.gethostname", lambda: "myhost")
        config = make_config(Path("."), detect_system_info=True)
        rules = anon.create_dynamic_system_rules(config)
        assert any(r.name == "system_hostname" for r in rules)

    def test_project_root(self, tmp_path, monkeypatch):
        root = tmp_path / "project"
        root.mkdir()
        config = make_config(root, directories=[str(root)], detect_system_info=True)
        rules = anon.create_dynamic_system_rules(config)
        root_rule = next((r for r in rules if r.name == "system_project_root"), None)
        assert root_rule is not None

        assert re.escape(str(root)) in root_rule.pattern






class TestAnonymizerRule:
    def test_compile_whole_word(self):
        rule = anon.AnonymizerRule(name="test", pattern="foo", whole_word=True)
        assert rule.pattern == r"\bfoo\b"
        assert rule.compile().pattern == r"\bfoo\b"

    def test_compile_case_insensitive(self):
        rule = anon.AnonymizerRule(name="test", pattern="foo", case_sensitive=False)
        assert rule.compile().flags & re.IGNORECASE

    def test_invalid_regex_raises(self):
        with pytest.raises(ValueError):
            anon.AnonymizerRule(name="bad", pattern="[unclosed")

    def test_enabled_default(self):
        rule = anon.AnonymizerRule(name="test", pattern="x")
        assert rule.enabled is True






class TestAnonymizerScanner:
    def test_replace_single_rule(self, tmp_path):
        rules = [anon.AnonymizerRule(name="test", pattern=r"secret", replacement="[REDACTED]")]
        scanner = anon.AnonymizerScanner(rules, "replace", "[GLOBAL]")
        lines = ["line with secret inside\n", "no match\n"]
        new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "dummy")
        assert new_lines == ["line with [REDACTED] inside\n", "no match\n"]
        assert len(matches) == 1
        assert matches[0].rule_name == "test"
        assert matches[0].matched_text == "secret"
        assert matches[0].replacement_text == "[REDACTED]"

    def test_replace_with_backref(self, tmp_path):
        rules = [anon.AnonymizerRule(name="test", pattern=r"(pass)=(\w+)", replacement=r"\1=[REDACTED]")]
        scanner = anon.AnonymizerScanner(rules, "replace", "[GLOBAL]")
        lines = ["pass=12345\n"]
        new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "dummy")
        assert new_lines == ["pass=[REDACTED]\n"]
        assert matches[0].replacement_text == "pass=[REDACTED]"

    def test_remove_line_mode(self, tmp_path):
        rules = [anon.AnonymizerRule(name="test", pattern=r"secret", mode="remove-line")]
        scanner = anon.AnonymizerScanner(rules, "replace", "[GLOBAL]")
        lines = ["line with secret\n", "keep this\n"]
        new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "dummy")
        assert new_lines == ["keep this\n"]
        assert len(matches) == 1
        assert matches[0].replacement_text is None

    def test_hash_mode(self, tmp_path):
        rules = [anon.AnonymizerRule(name="test", pattern=r"secret", mode="hash")]
        scanner = anon.AnonymizerScanner(rules, "replace", "[GLOBAL]")
        lines = ["secret\n"]
        new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "dummy")

        assert new_lines[0].startswith("[HASH:")
        assert matches[0].replacement_text is not None

    def test_multiple_rules_order(self, tmp_path):
        rules = [
            anon.AnonymizerRule(name="first", pattern=r"foo", replacement="bar"),
            anon.AnonymizerRule(name="second", pattern=r"bar", replacement="baz"),
        ]
        scanner = anon.AnonymizerScanner(rules, "replace", "[GLOBAL]")
        lines = ["foo\n"]
        new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "dummy")

        assert new_lines == ["baz\n"]
        assert len(matches) == 2

    def test_scope_filter(self, tmp_path):
        rules = [
            anon.AnonymizerRule(name="py_only", pattern=r"secret", scope=[".py"]),
            anon.AnonymizerRule(name="any", pattern=r"secret"),
        ]
        scanner = anon.AnonymizerScanner(rules, "replace", "[REDACTED]")
        lines = ["secret\n"]

        new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "dummy.txt")
        assert new_lines == ["[REDACTED]\n"]
        assert len(matches) == 1
        assert matches[0].rule_name == "any"

    def test_cell_index_and_field_passed(self, tmp_path):
        rules = [anon.AnonymizerRule(name="test", pattern=r"x")]
        scanner = anon.AnonymizerScanner(rules, "replace", "[R]")
        lines = ["x\n"]
        _, matches = scanner.scan_lines(lines, file_path=tmp_path / "dummy", cell_index=42, field="source")
        assert matches[0].cell_index == 42
        assert matches[0].field == "source"






class TestAnonymizerProcessorBasic:
    def test_find_files_excludes_notebooks_if_disabled(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.ipynb").touch()
        config = make_config(tmp_path, scan_notebooks=False)
        proc = anon.AnonymizerProcessor(config)
        files = proc.find_files()
        assert len(files) == 1
        assert files[0].suffix == ".py"

    def test_process_text_file_replace(self, monkeypatch, tmp_path, sample_text_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret", replacement="[REDACTED]")
        proc = anon.AnonymizerProcessor(make_config(tmp_path))
        proc.rules = [rule]

        matches, modified = proc.process_file(sample_text_file)
        assert len(matches) == 1
        assert matches[0].matched_text == "secret"
        assert modified is True

        content = sample_text_file.read_text()
        assert "secret" not in content
        assert "[REDACTED]" in content

    def test_process_text_file_preview_no_change(self, monkeypatch, tmp_path, sample_text_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret")
        config = make_config(tmp_path, preview_mode=True)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        original_content = sample_text_file.read_text()
        matches, modified = proc.process_file(sample_text_file)

        assert len(matches) == 1
        assert modified is False
        assert sample_text_file.read_text() == original_content

    def test_process_file_cache(self, monkeypatch, tmp_path, sample_text_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret")

        config = make_config(tmp_path, use_cache=True, preview_mode=True)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        original_scanner = anon.AnonymizerScanner
        call_count = 0

        def fake_scanner(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_scanner(*args, **kwargs)

        monkeypatch.setattr(anon, "AnonymizerScanner", fake_scanner)
        proc._cache = {}

        m1, mod1 = proc.process_file(sample_text_file)
        m2, mod2 = proc.process_file(sample_text_file)

        assert call_count == 1

    def test_backup_created_when_modified(self, monkeypatch, tmp_path, sample_text_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret")
        config = make_config(tmp_path, keep_backups=True)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        matches, modified = proc.process_file(sample_text_file)
        assert modified is True
        backup = sample_text_file.with_name(sample_text_file.name + ".bak")
        assert backup.exists()


class TestAnonymizerProcessorNotebook:
    def test_process_notebook_source_only(self, monkeypatch, tmp_path, sample_ipynb_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"password", replacement="[PWD]")
        config = make_config(tmp_path, scan_outputs=False)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        matches, modified = proc.process_file(sample_ipynb_file)

        assert len(matches) == 1
        assert all(m.field == "source" for m in matches)
        assert modified is True


        nb = json.loads(sample_ipynb_file.read_text(encoding="utf-8"))










        assert len(matches) == 1
        assert matches[0].cell_index == 1
        assert matches[0].field == "source"

    def test_process_notebook_outputs(self, monkeypatch, tmp_path, sample_ipynb_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret", replacement="[SECRET]")
        config = make_config(tmp_path, scan_outputs=True)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        matches, modified = proc.process_file(sample_ipynb_file)


        assert len(matches) == 1
        assert matches[0].field == "text"
        assert modified is True


        nb = json.loads(sample_ipynb_file.read_text(encoding="utf-8"))
        output_text = nb["cells"][0]["outputs"][0]["text"]
        assert "secret" not in "".join(output_text)
        assert "[SECRET]" in "".join(output_text)

    def test_notebook_metadata_scan(self, monkeypatch, tmp_path):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        notebook = {
            "cells": [],
            "metadata": {"custom": "secret_metadata"},
        }
        nb_file = tmp_path / "meta.ipynb"
        nb_file.write_text(json.dumps(notebook), encoding="utf-8")

        rule = anon.AnonymizerRule(name="test", pattern=r"secret")
        config = make_config(tmp_path, scan_metadata=True)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        matches, modified = proc.process_file(nb_file)

        assert len(matches) == 0


    def test_notebook_preview_no_changes(self, monkeypatch, tmp_path, sample_ipynb_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret")
        config = make_config(tmp_path, preview_mode=True)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        original_content = sample_ipynb_file.read_text()
        matches, modified = proc.process_file(sample_ipynb_file)
        assert modified is False
        assert sample_ipynb_file.read_text() == original_content

    def test_notebook_invalid_json(self, tmp_path, caplog):
        bad_file = tmp_path / "bad.ipynb"
        bad_file.write_text("{ invalid json }", encoding="utf-8")
        config = make_config(tmp_path)
        proc = anon.AnonymizerProcessor(config)
        with caplog.at_level(logging.ERROR):
            matches, modified = proc.process_file(bad_file)
        assert matches == []
        assert modified is False
        assert "Failed to read notebook" in caplog.text


class TestAnonymizerProcessorIntegration:
    def test_process_files_export_matches(self, monkeypatch, tmp_path, sample_text_file):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret")
        export_file = tmp_path / "matches.json"
        config = make_config(tmp_path, export_matches=export_file)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]

        result = proc.process_files()
        assert result["total_files"] == 1
        assert result["total_matches"] == 1
        assert export_file.exists()
        data = json.loads(export_file.read_text())
        assert data["total_matches"] == 1

    def test_process_files_no_files(self, tmp_path):
        config = make_config(tmp_path, include_pattern="*.none")
        proc = anon.AnonymizerProcessor(config)
        result = proc.process_files()
        assert result["total_files"] == 0

    def test_split_streams_logging(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)
        rule = anon.AnonymizerRule(name="test", pattern=r"secret")
        config = make_config(tmp_path, split_streams=True)
        proc = anon.AnonymizerProcessor(config)
        proc.rules = [rule]


        result = proc.process_files()
        captured = capsys.readouterr()









class TestParseArguments:
    def test_minimal(self):
        args = anon.parse_arguments([])
        assert args.directories == []
        assert args.pattern == '*'
        assert args.recursive is False

    def test_full(self, tmp_path):
        argv = [
            str(tmp_path),
            "-r",
            "-p", "*.py", "*.txt",
            "--max-depth", "3",
            "-ed", "venv",
            "-en", "*.log",
            "-ep", "docs/*",
            "-ig",
            "--gitignore", str(tmp_path / ".gitignore"),
            "--builtin-rules", "credentials,pii",
            "--rules-file", str(tmp_path / "rules.yaml"),
            "--env-file", str(tmp_path / ".env1"), "--env-file", str(tmp_path / ".env2"),
            "--mode", "hash",
            "--replacement", "[HIDDEN]",
            "--no-scan-notebooks",
            "--no-scan-outputs",
            "--scan-metadata",
            "--no-detect-system",
            "--username-placeholder", "[USERNAME]",
            "--home-placeholder", "[HOME_DIR]",
            "--hostname-placeholder", "[HOSTNAME]",
            "--project-root-placeholder", "[PROJ]",
            "--preview",
            "--export-matches", str(tmp_path / "out.json"),
            "-o", str(tmp_path / "log.txt"),
            "-v",
            "--split-streams",
            "--no-cache",
            "--keep-backups",
            "--backup-dir", str(tmp_path / "bak"),
            "--overwrite-backups",
        ]
        args = anon.parse_arguments(argv)
        assert args.directories == [str(tmp_path)]
        assert args.recursive is True
        assert args.pattern == '*.py *.txt'
        assert args.max_depth == 3
        assert args.exclude_dirs == ["venv"]
        assert args.exclude_names == ["*.log"]
        assert args.exclude_patterns == ["docs/*"]
        assert args.use_gitignore is True
        assert args.gitignore == tmp_path / ".gitignore"
        assert args.builtin_rules == "credentials,pii"
        assert args.rules_file == tmp_path / "rules.yaml"
        assert args.env_files == [tmp_path / ".env1", tmp_path / ".env2"]
        assert args.mode == "hash"
        assert args.replacement == "[HIDDEN]"
        assert args.scan_notebooks is False
        assert args.scan_outputs is False
        assert args.scan_metadata is True
        assert args.detect_system_info is False
        assert args.username_placeholder == "[USERNAME]"
        assert args.home_placeholder == "[HOME_DIR]"
        assert args.hostname_placeholder == "[HOSTNAME]"
        assert args.project_root_placeholder == "[PROJ]"
        assert args.preview is True
        assert args.export_matches == tmp_path / "out.json"
        assert args.output == tmp_path / "log.txt"
        assert args.verbose is True
        assert args.split_streams is True
        assert args.no_cache is True
        assert args.keep_backups is True
        assert args.backup_dir == tmp_path / "bak"
        assert args.overwrite_backups is True


class TestCreateConfigFromArgs:
    def test_basic(self, tmp_path, monkeypatch):
        args = anon.parse_arguments([str(tmp_path), "-p", "*.py", "--builtin-rules", "credentials"])
        cfg = anon.create_config_from_args(args)
        assert cfg.directories == [str(tmp_path)]
        assert cfg.include_pattern == "*.py"
        assert cfg.builtin_rules == {"credentials"}

    def test_directory_recursion(self, tmp_path):
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()
        args = anon.parse_arguments([
            "-dr", str(d1),
            "-d", str(d2),
            str(tmp_path),
        ])
        cfg = anon.create_config_from_args(args)

        assert len(cfg.directory_recursion) == 2

        d1_resolved = d1.resolve()
        d2_resolved = d2.resolve()
        assert cfg.directory_recursion[d1_resolved] is True
        assert cfg.directory_recursion[d2_resolved] is False






class TestMain:
    def test_success(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(anon, "_configure_logging", lambda *a, **k: None)
        monkeypatch.setattr(anon, "ProgressReporter", DummyProgress)


        f = tmp_path / "test.txt"
        f.write_text("secret\n")

        class DummyProcessor:
            def __init__(self, cfg):
                self.cfg = cfg

            def process_files(self):
                return {"total_files": 1, "total_matches": 1, "modified_files": 1, "matches": []}

        monkeypatch.setattr(anon, "AnonymizerProcessor", DummyProcessor)

        rc = anon.main([str(tmp_path), "--preview"])
        assert rc == 0
        out, err = capsys.readouterr()



    def test_keyboard_interrupt(self, monkeypatch):
        monkeypatch.setattr(anon, "_configure_logging", lambda *a, **k: None)

        def raise_kb(*args):
            raise KeyboardInterrupt()

        monkeypatch.setattr(anon, "AnonymizerProcessor", raise_kb)

        rc = anon.main([])
        assert rc == 130

    def test_fatal_error(self, monkeypatch):
        monkeypatch.setattr(anon, "_configure_logging", lambda *a, **k: None)

        def raise_error(*args):
            raise RuntimeError("boom")

        monkeypatch.setattr(anon, "AnonymizerProcessor", raise_error)

        rc = anon.main([])
        assert rc == 1






def test_rule_disabled(tmp_path):
    rule = anon.AnonymizerRule(name="test", pattern=r"x", enabled=False)
    scanner = anon.AnonymizerScanner([rule], "replace", "[R]")
    lines = ["x\n"]
    new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "d")
    assert new_lines == ["x\n"]
    assert matches == []


def test_remove_line_with_multiple_matches(tmp_path):
    rules = [anon.AnonymizerRule(name="test", pattern=r"bad", mode="remove-line")]
    scanner = anon.AnonymizerScanner(rules, "replace", "[R]")
    lines = ["good line\n", "bad line with bad word\n", "another good\n"]
    new_lines, matches = scanner.scan_lines(lines, file_path=tmp_path / "d")
    assert new_lines == ["good line\n", "another good\n"]
    assert len(matches) == 1


    assert matches[0].matched_text == "bad"


def test_hash_consistency(tmp_path):
    rules = [anon.AnonymizerRule(name="test", pattern=r"secret", mode="hash")]
    scanner = anon.AnonymizerScanner(rules, "replace", "[R]")
    lines = ["secret\n"]
    new_lines, _ = scanner.scan_lines(lines, file_path=tmp_path / "d")

    h1 = new_lines[0].strip()
    new_lines2, _ = scanner.scan_lines(["secret\n"], file_path=tmp_path / "d")
    h2 = new_lines2[0].strip()
    assert h1 == h2
    assert h1.startswith("[HASH:")
    assert len(h1) > 8