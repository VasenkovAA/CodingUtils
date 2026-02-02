from __future__ import annotations

from .registry import PluginRegistry

from .parsers.python_parser import PythonParser
from .parsers.generic_parser import GenericParser

from .formatters.markdown_formatter import MarkdownFormatter

from .llm.mock_provider import MockLLMProvider
from .llm.openai_compatible import OpenAIClient, LMStudioClient


def register_builtin_plugins(registry: PluginRegistry) -> PluginRegistry:
    registry.register_parser(PythonParser)
    registry.register_parser(GenericParser)

    registry.register_formatter(MarkdownFormatter)

    registry.register_llm_provider(MockLLMProvider)
    registry.register_llm_provider(OpenAIClient)
    registry.register_llm_provider(LMStudioClient)

    return registry
