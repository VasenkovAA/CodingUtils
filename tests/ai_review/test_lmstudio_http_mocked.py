from __future__ import annotations

import json
from pathlib import Path


from codingutils.ai_reviewer import main as cli_main


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._bytes = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_lmstudio_provider_openai_compatible_mocked_http(tmp_path: Path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    (proj / "prompts").mkdir()
    (proj / "prompts" / "u.md").write_text("{{code}}", encoding="utf-8")

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
      provider: "lmstudio"
      api_base: "http://localhost:1234/v1"
      model: "oos-20B"
      max_output_tokens: 10
    prompt:
      user_prompt: "prompts/u.md"
    output:
      directory: "./reviews"
""".strip(),
        encoding="utf-8",
    )

    import codingutils.ai_review.plugins.llm.openai_compatible as mod

    def fake_urlopen(req, timeout=None):
        payload = {
            "choices": [
                {"message": {"content": "HTTP_MOCK_REVIEW"}}
            ]
        }
        return _FakeHTTPResponse(payload)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.chdir(proj)

    rc = cli_main(["--config", str(cfg), "--profile", "p", str(proj / "src")])
    assert rc == 0

    reviews = list((proj / "reviews").glob("**/review_*_*.md"))
    assert reviews, "No review files produced"
    text = reviews[0].read_text(encoding="utf-8")
    assert "HTTP_MOCK_REVIEW" in text
