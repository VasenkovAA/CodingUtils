from pathlib import Path

import pytest

from codingutils.ai_review.plugins import PluginRegistry
from codingutils.ai_review.plugins.base import BaseParser
from codingutils.ai_review.plugins.errors import ParserNotFoundError

from codingutils.ai_review.core.models.config import LLMConfig

from codingutils.ai_review.plugins.base import BaseFormatter, BaseLLMProvider
from codingutils.ai_review.plugins.errors import PluginNotFoundError


class PyParser(BaseParser):
    name = "python"

    @classmethod
    def get_supported_config_keys(cls):
        return []

    @classmethod
    def supported_extensions(cls):
        return [".py"]

    def parse_functions(self, file_path):
        return []

    def parse_classes(self, file_path):
        return []


def test_registry_resolve_parser_by_extension():
    reg = PluginRegistry()
    reg.register_parser(PyParser)

    p = reg.create_parser(name=None, file_extension=".py")
    assert isinstance(p, PyParser)


def test_registry_parser_not_found():
    reg = PluginRegistry()
    with pytest.raises(ParserNotFoundError):
        reg.create_parser(name=None, file_extension=".unknown")


def test_discover_plugins(tmp_path: Path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()

    plugin_file = plugin_dir / "my_plugin.py"
    plugin_file.write_text(
        """
from codingutils.ai_review.plugins.base import BaseParser

class TxtParser(BaseParser):
    name = "txt"

    @classmethod
    def get_supported_config_keys(cls):
        return []

    @classmethod
    def supported_extensions(cls):
        return [".txt"]

    def parse_functions(self, file_path):
        return []

    def parse_classes(self, file_path):
        return []

def register(registry):
    registry.register_parser(TxtParser)
""".strip(),
        encoding="utf-8",
    )

    reg = PluginRegistry()
    reg.discover_plugins([plugin_dir])

    parser = reg.create_parser(name=None, file_extension=".txt")
    assert parser.__class__.__name__ == "TxtParser"


class DummyParser(BaseParser):
    name = "dummy_parser"

    @classmethod
    def get_supported_config_keys(cls):
        return []

    @classmethod
    def supported_extensions(cls):
        return [".x"]

    def parse_functions(self, file_path):
        return []

    def parse_classes(self, file_path):
        return []


class DummyProvider(BaseLLMProvider):
    name = "dummy_llm"

    @classmethod
    def get_supported_config_keys(cls):
        return ["extra"]

    def __init__(self, config: LLMConfig, extra=None, **kwargs):
        super().__init__(config=config, **kwargs)
        self.extra = extra

    async def complete(self, messages):
        return "ok"

    def estimate_tokens(self, text: str) -> int:
        return 1


class DummyFormatter(BaseFormatter):
    name = "dummy_fmt"

    @classmethod
    def get_supported_config_keys(cls):
        return ["prefix"]

    def __init__(self, prefix="P:"):
        self.prefix = prefix

    def format_review(self, review) -> str:
        return f"{self.prefix}{review.review_text}"

    def format_summary(self, summary) -> str:
        return f"{self.prefix}{summary.total_elements}"


def test_registry_create_llm_provider_with_default_config():
    reg = PluginRegistry()
    reg.register_llm_provider(DummyProvider)
    reg.set_plugin_default_config("dummy_llm", {"extra": "zzz"})

    provider = reg.create_llm_provider("dummy_llm", config=LLMConfig())
    assert provider.extra == "zzz"


def test_registry_create_formatter_and_override_config():
    reg = PluginRegistry()
    reg.register_formatter(DummyFormatter)
    reg.set_plugin_default_config("dummy_fmt", {"prefix": "A:"})

    fmt = reg.create_formatter("dummy_fmt", config={"prefix": "B:"})
    assert fmt.prefix == "B:"


def test_registry_create_parser_by_name():
    reg = PluginRegistry()
    reg.register_parser(DummyParser)

    p = reg.create_parser(name="dummy_parser", file_extension=".x")
    assert isinstance(p, DummyParser)


def test_registry_plugin_not_found_errors():
    reg = PluginRegistry()
    with pytest.raises(PluginNotFoundError):
        reg.create_llm_provider("missing", config=LLMConfig())
    with pytest.raises(PluginNotFoundError):
        reg.create_formatter("missing")
    with pytest.raises(PluginNotFoundError):
        reg.create_parser(name="missing", file_extension=".py")
