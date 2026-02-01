from __future__ import annotations


class PluginError(Exception):
    """Base error for plugin system."""


class PluginNotFoundError(PluginError):
    pass


class ParserNotFoundError(PluginError):
    pass
