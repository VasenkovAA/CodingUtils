from __future__ import annotations

from textual.widgets import ListItem, ListView, Label

from ..plugin_api import PluginSpec


class ModuleItem(ListItem):
    def __init__(self, plugin: PluginSpec) -> None:
        super().__init__()
        self.plugin = plugin
        self.label = Label(plugin.meta.name)

    def compose(self):
        yield self.label


class ModuleList(ListView):
    pass
