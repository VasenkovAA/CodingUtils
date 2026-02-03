from __future__ import annotations

from pathlib import Path


from codingutils.ai_reviewer import main as cli_main


def _make_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    src = proj / "src"
    src.mkdir(parents=True)

    (src / "a.py").write_text(
        "def f():\n"
        "    return 1\n\n"
        "class C:\n"
        "    def m(self):\n"
        "        return 2\n",
        encoding="utf-8",
    )

    (src / "b.ts").write_text(
        "export function foo(x: number) { return x + 1 }\n"
        "const bar = (y) => y * 2;\n",
        encoding="utf-8",
    )

    prompts = proj / "prompts"
    prompts.mkdir()

    (prompts / "system.md").write_text(
        "You are a senior engineer. Provide actionable review.\n",
        encoding="utf-8",
    )
    (prompts / "python_review.md").write_text(
        "Review {{element_type}} {{element_name}} in {{filepath}}\n\n{{code}}\n",
        encoding="utf-8",
    )

    return proj


def _write_config(proj: Path, *, output_dir_name: str = "reviews") -> Path:
    cfg = proj / ".codingutils.yaml"
    cfg.write_text(
        f"""
version: 2

globals:
  output:
    directory: "./{output_dir_name}"
    versioning: "incremental"
    preserve_structure: true
    formatter: "markdown"

profiles:
  oos-20b-local:
    # Важно: список паттернов (как ты хотел)
    include_patterns:
      - "*.py"
      - "*.ts"
    recursive: true

    processing:
      method: "functions"
      skip_unchanged: true
      max_workers: 2
      max_input_tokens: 2000

    llm:
      provider: "lmstudio"
      api_base: "http://localhost:1234/v1"
      model: "oos-20B"
      temperature: 0.2
      max_output_tokens: 256
      context_window: 8192

    prompt:
      system_prompt: "prompts/system.md"
      user_prompt: "prompts/python_review.md"
      include_context: false
""".strip(),
        encoding="utf-8",
    )
    return cfg


def _count_reviews(reviews_dir: Path) -> int:
    return len(list(reviews_dir.glob("**/review_*_*.md")))


def test_cli_dry_run_e2e(tmp_path: Path, monkeypatch):
    proj = _make_project(tmp_path)
    cfg = _write_config(proj)

    monkeypatch.chdir(proj)

    rc = cli_main(
        [
            "--config",
            str(cfg),
            "--profile",
            "oos-20b-local",
            "--dry-run",
            str(proj / "src"),
        ]
    )
    assert rc == 0

    out_dir = proj / "reviews"
    assert out_dir.exists()
    assert (out_dir / "summary.md").exists()
    assert (out_dir / ".review_hashes.json").exists()

    assert _count_reviews(out_dir) >= 2


def test_cli_skip_unchanged_then_force_creates_new_versions(tmp_path: Path, monkeypatch):
    proj = _make_project(tmp_path)
    cfg = _write_config(proj)

    monkeypatch.chdir(proj)


    rc1 = cli_main(["--config", str(cfg), "--profile", "oos-20b-local", "--dry-run", str(proj / "src")])
    assert rc1 == 0
    out_dir = proj / "reviews"
    n1 = _count_reviews(out_dir)
    assert n1 > 0

    rc2 = cli_main(["--config", str(cfg), "--profile", "oos-20b-local", "--dry-run", str(proj / "src")])
    assert rc2 == 0
    n2 = _count_reviews(out_dir)
    assert n2 == n1

    rc3 = cli_main(
        ["--config", str(cfg), "--profile", "oos-20b-local", "--dry-run", "--force", str(proj / "src")]
    )
    assert rc3 == 0
    n3 = _count_reviews(out_dir)
    assert n3 > n2


def test_cli_clean(tmp_path: Path, monkeypatch):
    proj = _make_project(tmp_path)
    cfg = _write_config(proj)

    monkeypatch.chdir(proj)

    rc1 = cli_main(["--config", str(cfg), "--profile", "oos-20b-local", "--dry-run", str(proj / "src")])
    assert rc1 == 0
    assert (proj / "reviews").exists()

    rc2 = cli_main(["--config", str(cfg), "--profile", "oos-20b-local", "--clean"])
    assert rc2 == 0
    assert not (proj / "reviews").exists()
