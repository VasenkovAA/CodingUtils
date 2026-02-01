from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set, Type

from .base import BaseFormatter, BaseLLMProvider, BaseParser
from .errors import ParserNotFoundError, PluginNotFoundError

logger = logging.getLogger(__name__)


class PluginRegistry:
    def __init__(self) -> None:
        self._parsers: Dict[str, Type[BaseParser]] = {}
        self._llm_providers: Dict[str, Type[BaseLLMProvider]] = {}
        self._formatters: Dict[str, Type[BaseFormatter]] = {}

        self._plugin_configs: Dict[str, Dict[str, Any]] = {}
        self._loaded_plugins: Set[str] = set()

    def register_parser(self, parser_class: Type[BaseParser]) -> None:
        self._parsers[parser_class.name] = parser_class

    def register_llm_provider(self, provider_class: Type[BaseLLMProvider]) -> None:
        self._llm_providers[provider_class.name] = provider_class

    def register_formatter(self, formatter_class: Type[BaseFormatter]) -> None:
        self._formatters[formatter_class.name] = formatter_class

    def set_plugin_default_config(self, plugin_name: str, config: Dict[str, Any]) -> None:
        self._plugin_configs[plugin_name] = dict(config or {})

    def create_parser(self, name: Optional[str], file_extension: str, config: Optional[Dict[str, Any]] = None) -> BaseParser:
        if name:
            if name not in self._parsers:
                raise PluginNotFoundError(f"Parser '{name}' not found")
            cls = self._parsers[name]
        else:
            cls = self._resolve_parser_by_extension(file_extension)

        plugin_config = {**self._plugin_configs.get(cls.name, {}), **(config or {})}
        return cls(**plugin_config)

    def create_llm_provider(self, name: str, config) -> BaseLLMProvider:
        if name not in self._llm_providers:
            raise PluginNotFoundError(f"LLM provider '{name}' not found")
        cls = self._llm_providers[name]
        plugin_config = self._plugin_configs.get(cls.name, {})
        return cls(config=config, **plugin_config)

    def create_formatter(self, name: str, config: Optional[Dict[str, Any]] = None) -> BaseFormatter:
        if name not in self._formatters:
            raise PluginNotFoundError(f"Formatter '{name}' not found")
        cls = self._formatters[name]
        plugin_config = {**self._plugin_configs.get(cls.name, {}), **(config or {})}
        return cls(**plugin_config)

    def _resolve_parser_by_extension(self, extension: str) -> Type[BaseParser]:
        ext = (extension or "").lower()
        for parser_cls in self._parsers.values():
            try:
                if ext in [e.lower() for e in parser_cls.supported_extensions()]:
                    return parser_cls
            except Exception as e:
                logger.debug("Failed to query supported_extensions for %s: %s", parser_cls, e)

        if "generic" in self._parsers:
            return self._parsers["generic"]

        raise ParserNotFoundError(f"No parser found for extension: {extension}")

    def discover_plugins(self, plugin_dirs) -> None:
        """
        MVP: load all *.py files from dirs.
        Convention: module must define `register(registry: PluginRegistry)`.
        """
        for d in plugin_dirs or []:
            p = Path(d).expanduser()
            if not p.exists() or not p.is_dir():
                continue

            for file in sorted(p.glob("*.py")):
                if file.name.startswith("_"):
                    continue

                key = str(file.resolve())
                if key in self._loaded_plugins:
                    continue

                module_name = f"codingutils_ai_review_plugin_{abs(hash(key))}"
                spec = importlib.util.spec_from_file_location(module_name, key)
                if not spec or not spec.loader:
                    logger.warning("Cannot load plugin module: %s", key)
                    continue

                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                    register = getattr(module, "register", None)
                    if callable(register):
                        register(self)
                        self._loaded_plugins.add(key)
                    else:
                        logger.warning("Plugin module %s has no register(registry) function", key)
                except Exception as e:
                    logger.exception("Failed to load plugin %s: %s", key, e)
