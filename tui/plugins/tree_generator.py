
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from asyncio import to_thread

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Input, Static, TextArea, Checkbox

from codingutils.tree_generater import TreeConfig, ProjectTreeGenerator

from tui.plugins_base import ToolPlugin, ToolMeta, tool_registry


@dataclass
class TreeToolState:
    directories: str = ""
    recursive: bool = True
    pattern: str = "*"


class TreeGeneratorTool(ToolPlugin):
    """Минимальный плагин для tree-generator."""

    meta = ToolMeta(
        id="tree-generator",
        label="tree-generator",
        description="ASCII project tree generator",
    )

    def __init__(self, screen: "MainScreen") -> None: #noqa F821
        super().__init__(screen)
        self.state = TreeToolState()



    def create_options_panel(self) -> Vertical:
        plugin = self

        class _TreeOptions(Vertical):
            """Простая панель: директории, паттерн и флаг recursive."""

            def compose(self) -> ComposeResult:
                yield Label("Directories (space-separated):")
                yield Input(
                    id="tree-dirs-input",
                    placeholder=".",
                    value=plugin.state.directories,
                )

                yield Label("Pattern (-p / --pattern):")
                yield Input(
                    id="tree-pattern-input",
                    placeholder="*",
                    value=plugin.state.pattern,
                )

                yield Checkbox(
                    "Recursive (-r)",
                    value=plugin.state.recursive,
                    id="tree-recursive-checkbox",
                )

                yield Static(
                    "Minimal tree-generator options. "
                    "Advanced flags можно добавить позже внутри этого плагина.",
                    classes="hint",
                )

            def on_input_changed(self, event: Input.Changed) -> None:
                if event.input.id == "tree-dirs-input":
                    plugin.state.directories = event.value
                    plugin.on_state_changed()
                elif event.input.id == "tree-pattern-input":
                    plugin.state.pattern = event.value
                    plugin.on_state_changed()

            def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
                if event.checkbox.id == "tree-recursive-checkbox":
                    plugin.state.recursive = event.value
                    plugin.on_state_changed()

        return _TreeOptions()



    def build_cli_preview(self) -> str:
        s = self.state
        parts = [self.meta.id]

        dirs = s.directories.strip()
        if dirs:
            parts.append(dirs)

        if s.recursive:
            parts.append("-r")

        if s.pattern.strip() and s.pattern.strip() != "*":
            parts.append("-p")
            parts.append(f'"{s.pattern.strip()}"')

        return " ".join(parts)



    async def run(self) -> None:
        """Выполнить tree-generator с текущей конфигурацией."""


        logs = self.screen.query_one("#logs-area")
        outputs = self.screen.query_one("#outputs-area", TextArea)

        logs.add_log("INFO", f"Running: {self.build_cli_preview()}")

        s = self.state
        dirs = s.directories.split() if s.directories.strip() else ["."]
        pattern = s.pattern or "*"

        cfg = TreeConfig(
            directories=dirs,
            include_pattern=pattern,
            recursive=s.recursive,
            max_depth=None,
            exclude_dirs=set(),
            exclude_names=set(),
            exclude_patterns=set(),
            use_gitignore=False,
            custom_gitignore=None,
        )

        gen = ProjectTreeGenerator(cfg)

        try:
            content = await to_thread(gen.generate, [Path(d) for d in dirs])
            outputs.text = content
            logs.add_log("INFO", "tree-generator finished")
        except Exception as e:
            logs.add_log("ERROR", f"tree-generator failed: {e!r}")



tool_registry.register(TreeGeneratorTool)
