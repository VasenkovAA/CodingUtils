from pathlib import Path

from codingutils.ai_review.core.models.config import PromptConfig
from codingutils.ai_review.core.models.domain import CodeElement
from codingutils.ai_review.infrastructure import PromptEngineer


def test_prompt_engineer_basic_substitution(tmp_path: Path):
    prompt = tmp_path / "u.txt"
    prompt.write_text("FN={{element_name}} FILE={{filepath}}\n{{code}}", encoding="utf-8")

    cfg = PromptConfig(user_prompt=str(prompt))
    pe = PromptEngineer(cfg)

    file_path = tmp_path / "a.py"
    file_path.write_text("def f():\n    return 1\n", encoding="utf-8")

    elem = CodeElement(
        type=CodeElement.Type.FUNCTION,
        name="f",
        content="def f():\n    return 1\n",
        file_path=file_path,
        language="python",
    )

    msgs = pe.build_messages(elem)
    assert len(msgs) == 1
    assert "FN=f" in msgs[0]["content"]
    assert "def f()" in msgs[0]["content"]


def test_prompt_engineer_include_context_only_if_placeholder_present(tmp_path: Path):
    # В шаблоне нет {{context}} => даже если include_context=True, файл не должен читаться "как контекст"
    prompt = tmp_path / "u.txt"
    prompt.write_text("NO_CONTEXT\n{{code}}", encoding="utf-8")

    cfg = PromptConfig(user_prompt=str(prompt), include_context=True)
    pe = PromptEngineer(cfg)

    file_path = tmp_path / "a.py"
    file_path.write_text("ORIGINAL_FILE", encoding="utf-8")

    elem = CodeElement(
        type=CodeElement.Type.FILE,
        name="a.py",
        content="ELEMENT_SNIPPET",
        file_path=file_path,
        language="python",
    )

    msgs = pe.build_messages(elem)
    assert "ORIGINAL_FILE" not in msgs[0]["content"]
    assert "ELEMENT_SNIPPET" in msgs[0]["content"]

    # Теперь шаблон с {{context}} => должен появиться ORIGINAL_FILE
    prompt2 = tmp_path / "u2.txt"
    prompt2.write_text("CTX={{context}}\nCODE={{code}}", encoding="utf-8")

    cfg2 = PromptConfig(user_prompt=str(prompt2), include_context=True)
    pe2 = PromptEngineer(cfg2)
    msgs2 = pe2.build_messages(elem)
    assert "ORIGINAL_FILE" in msgs2[0]["content"]
    assert "ELEMENT_SNIPPET" in msgs2[0]["content"]


def test_prompt_engineer_context_files(tmp_path: Path, monkeypatch):
    cwd = tmp_path
    monkeypatch.chdir(cwd)

    extra = cwd / "config.yaml"
    extra.write_text("x: 1", encoding="utf-8")

    prompt = cwd / "u.txt"
    prompt.write_text("FILES:\n{{context_files}}", encoding="utf-8")

    cfg = PromptConfig(user_prompt=str(prompt), context_files=["*.yaml"])
    pe = PromptEngineer(cfg)

    file_path = cwd / "a.py"
    file_path.write_text("pass", encoding="utf-8")

    elem = CodeElement(
        type=CodeElement.Type.FILE,
        name="a.py",
        content="pass",
        file_path=file_path,
        language="python",
    )

    msgs = pe.build_messages(elem)
    assert "config.yaml" in msgs[0]["content"]
    assert "x: 1" in msgs[0]["content"]
