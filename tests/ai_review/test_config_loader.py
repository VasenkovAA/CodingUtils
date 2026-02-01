from pathlib import Path

import pytest

from codingutils.ai_review.core.config_loader import load_ai_review_config, find_config_file

def test_include_patterns_list(tmp_path: Path):
    cfg_file = tmp_path / ".codingutils.yaml"
    cfg_file.write_text(
        """
profiles:
  python:
    include_patterns: ["*.py", "*.pyw"]
""".strip(),
        encoding="utf-8",
    )

    cfg = load_ai_review_config(config_path=cfg_file, profile="python")
    assert cfg.include_patterns == ["*.py", "*.pyw"]
    assert cfg.filter_config.include_pattern == "*"


def test_profile_extends_and_merge(tmp_path: Path):
    cfg_file = tmp_path / ".codingutils.yaml"
    cfg_file.write_text(
        """
version: 2
globals:
  processing:
    max_input_tokens: 1000

profiles:
  base:
    include_pattern: "*.py"
    processing:
      method: "functions"
  child:
    extends: base
    processing:
      max_input_tokens: 1500
""".strip(),
        encoding="utf-8",
    )

    cfg = load_ai_review_config(config_path=cfg_file, profile="child")
    assert cfg.filter_config.include_pattern == "*.py"
    assert cfg.processing.max_input_tokens == 1500


def test_profile_cycle_detection(tmp_path: Path):
    cfg_file = tmp_path / ".codingutils.yaml"
    cfg_file.write_text(
        """
profiles:
  a:
    extends: b
  b:
    extends: a
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_ai_review_config(config_path=cfg_file, profile="a")
def test_find_config_file_walks_up(tmp_path: Path):
    root = tmp_path / "root"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)

    cfg = root / ".codingutils.yaml"
    cfg.write_text("version: 2\n", encoding="utf-8")

    found = find_config_file(nested)
    assert found == cfg


def test_normalize_output_directory_and_llm_max_tokens(tmp_path: Path):
    cfg_file = tmp_path / ".codingutils.yaml"
    cfg_file.write_text(
        """
globals:
  output:
    directory: "./out_reviews"
  llm:
    max_tokens: 123
""".strip(),
        encoding="utf-8",
    )

    cfg = load_ai_review_config(config_path=cfg_file)
    assert cfg.output.output_dir.name == "out_reviews"
    assert cfg.llm.max_output_tokens == 123


def test_unknown_keys_are_warning_not_error(tmp_path: Path, caplog):
    cfg_file = tmp_path / ".codingutils.yaml"
    cfg_file.write_text(
        """
globals:
  some_unknown_key: 123
""".strip(),
        encoding="utf-8",
    )

    caplog.clear()
    load_ai_review_config(config_path=cfg_file)
    assert any("Unknown config key ignored" in r.message for r in caplog.records)


def test_missing_profile_raises(tmp_path: Path):
    cfg_file = tmp_path / ".codingutils.yaml"
    cfg_file.write_text("profiles: {}", encoding="utf-8")
    with pytest.raises(KeyError):
        load_ai_review_config(config_path=cfg_file, profile="nope")
