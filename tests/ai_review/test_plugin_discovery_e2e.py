from __future__ import annotations

from pathlib import Path

from codingutils.ai_reviewer import main as cli_main


def test_plugin_discovery_custom_formatter(tmp_path: Path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    (proj / "prompts").mkdir()
    (proj / "prompts" / "u.md").write_text("{{code}}", encoding="utf-8")

    plugin_dir = proj / ".codingutils" / "plugins"
    plugin_dir.mkdir(parents=True)
    import textwrap

    (plugin_dir / "plain_formatter.py").write_text(
        textwrap.dedent(
        """
        from codingutils.ai_review.plugins.base import BaseFormatter

        class PlainFormatter(BaseFormatter):
            name = "plain"

            @classmethod
            def get_supported_config_keys(cls):
                return []

            def format_review(self, review) -> str:
                return "PLAIN:" + review.review_text

            def format_summary(self, summary) -> str:
                return "PLAIN_SUMMARY"

        def register(registry):
            registry.register_formatter(PlainFormatter)
        """
        ).lstrip(),
        encoding="utf-8",
    )

    cfg = proj / ".codingutils.yaml"
    cfg.write_text(
        """
profiles:
  p:
    include_patterns: ["*.py"]
    processing:
      method: "functions"
      skip_unchanged: false
    llm:
      provider: "mock"
      model: "mock"
    prompt:
      user_prompt: "prompts/u.md"
    output:
      directory: "./reviews"
      formatter: "plain"

plugins:
  auto_discover: true
  plugin_dirs:
    - "./.codingutils/plugins"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.chdir(proj)

    rc = cli_main(["--config", str(cfg), "--profile", "p", str(proj / "src")])
    assert rc == 0

    summary = (proj / "reviews" / "summary.md").read_text(encoding="utf-8")
    assert "PLAIN_SUMMARY" in summary

    reviews = list((proj / "reviews").glob("**/review_*_*.md"))
    assert reviews
    assert reviews[0].read_text(encoding="utf-8").startswith("PLAIN:")
