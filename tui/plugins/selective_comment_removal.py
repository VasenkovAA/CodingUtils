from __future__ import annotations

import asyncio
import io
import json
import shlex
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Static,
    TabPane,
    TextArea,
)

from codingutils.comment_extractor import (
    CommentExtractorConfig,
    CommentProcessor,
    CommentStyle,
    CommentScanner,
    CommentMatch,
)
from codingutils.common_utils import FileContentDetector, FileType, safe_write

from tui.plugins_base import ToolMeta, ToolPlugin, tool_registry


# Тип-ключ комментария: координаты внутри файла/ячейки
CommentKey = Tuple[int, int, int, int, Optional[int]]


def _split_space_separated(value: str) -> List[str]:
    """Разбить строку по пробелам, поддерживая кавычки (shlex)."""
    value = (value or "").strip()
    if not value:
        return []
    try:
        return shlex.split(value)
    except ValueError:
        return value.split()


def _shorten_comment_text(text: str, width: int = 80) -> str:
    """Обрезать комментарий до удобочитаемой длины."""
    text = " ".join((text or "").split())
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


@dataclass
class SelectiveCommentRemovalState:
    """Конфигурация сканирования (то, что пользователь задаёт в UI)."""

    # Что сканируем
    directories: str = "."                # пробел-разделитель, можно несколько директорий
    pattern: str = "*.py"                # маски файлов, например: "*.py *.ipynb"
    recursive: bool = True
    use_gitignore: bool = True

    # Фильтры исключений
    exclude_dirs: str = ".git .hg .svn .venv .idea __pycache__"
    exclude_names: str = ""              # маски имён файлов
    exclude_patterns: str = ""           # маски путей

    # Парсер комментариев
    comment_symbols: str = ""            # override: "//" или "/* */" или "// /* */"
    exclude_comment_pattern: str = ""    # префикс, исключающий комментарий (например "##")
    language_filter: str = ""            # фильтр по языку текста комментария ("en", "ru", ...)


class _CommentsList(VerticalScroll):
    """Виджет со списком комментариев и чекбоксами для выбора."""

    def __init__(
        self,
        comments: List[Dict[str, Any]],
        selected_indices: Set[int],
    ) -> None:
        super().__init__(id="scr-comments-list")
        self._comments = comments
        self._selected_indices = selected_indices

    def compose(self) -> ComposeResult:
        total = len(self._comments)
        file_count = len({c["file"] for c in self._comments}) if self._comments else 0

        yield Label(f"[b]Comments:[/b] {total} in {file_count} files")
        with Horizontal():
            yield Button("Select all", id="scr-select-all")
            yield Button("Clear selection", id="scr-select-none")
        yield Static("")  # небольшой отступ

        for idx, c in enumerate(self._comments):
            rel = c.get("relative_path") or Path(c["file"]).name
            line = c.get("start_line")
            text = c.get("text") or c.get("raw", "").strip()
            summary = _shorten_comment_text(text)
            label = f"{rel}:{line}: {summary}"
            yield Checkbox(label, id=f"comment-{idx}", value=(idx in self._selected_indices))

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        cid = event.checkbox.id or ""
        if not cid.startswith("comment-"):
            return
        try:
            idx = int(cid.split("-", 1)[1])
        except ValueError:
            return

        if event.value:
            self._selected_indices.add(idx)
        else:
            self._selected_indices.discard(idx)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scr-select-all":
            self._selected_indices.clear()
            self._selected_indices.update(range(len(self._comments)))
            for cb in self.query(Checkbox):
                if cb.id and cb.id.startswith("comment-"):
                    cb.value = True
        elif event.button.id == "scr-select-none":
            self._selected_indices.clear()
            for cb in self.query(Checkbox):
                if cb.id and cb.id.startswith("comment-"):
                    cb.value = False


class SelectiveCommentRemovalTool(ToolPlugin):
    """Интерактивный поиск и выборочное удаление комментариев."""

    meta = ToolMeta(
        id="selective-comment-removal",
        label="selective-comment-removal",
        description="Interactive scan and selective removal of comments",
    )

    def __init__(self, screen: "MainScreen") -> None:  # type: ignore[name-defined] #noqa F821
        super().__init__(screen)
        self.state = SelectiveCommentRemovalState()

        # Результаты последнего сканирования
        self._scan_results: List[Dict[str, Any]] = []
        # Индексы выбранных пользователем комментариев (_scan_results[idx])
        self._selected_indices: Set[int] = set()

    # ------------------------------------------------------------------ UI

    def create_options_panel(self) -> Widget:
        plugin = self

        class _OptionsPanel(Vertical):
            def compose(self) -> ComposeResult:
                yield Label("[b]Selective comment removal[/]", classes="section-title")

                yield Label("Directories (space-separated):")
                yield Input(plugin.state.directories, id="scr-dirs")

                yield Label('File patterns (e.g. "*.py *.ipynb"):')
                yield Input(plugin.state.pattern, id="scr-pattern")

                yield Checkbox("Recursive", value=plugin.state.recursive, id="scr-recursive")
                yield Checkbox("Use .gitignore", value=plugin.state.use_gitignore, id="scr-gitignore")

                yield Label("Exclude directories (names, space-separated):")
                yield Input(plugin.state.exclude_dirs, id="scr-exclude-dirs")

                yield Label("Exclude file names (glob, space-separated):")
                yield Input(plugin.state.exclude_names, id="scr-exclude-names")

                yield Label("Exclude path patterns (glob, space-separated):")
                yield Input(plugin.state.exclude_patterns, id="scr-exclude-patterns")

                yield Label("Override comment symbols (optional, e.g. '//' or '/* */'):")
                yield Input(plugin.state.comment_symbols, id="scr-comment-symbols")

                yield Label('Exclude comments starting with (e.g. "##") (optional):')
                yield Input(plugin.state.exclude_comment_pattern, id="scr-exclude-comment-pattern")

                yield Label('Language filter for scanning (e.g. "en" or "ru") (optional):')
                yield Input(plugin.state.language_filter, id="scr-language-filter")

                yield Static(
                    "Press [b]Send[/b] (Ctrl+J) to scan comments.\n"
                    "Then open the [b]Details[/b] tab, select comments\n"
                    "using checkboxes and click [b]Delete selected comments[/b].",
                    classes="hint",
                )

                yield Button("Delete selected comments", id="scr-delete-selected", variant="error")

            def on_input_changed(self, event: Input.Changed) -> None:
                mapping = {
                    "scr-dirs": "directories",
                    "scr-pattern": "pattern",
                    "scr-exclude-dirs": "exclude_dirs",
                    "scr-exclude-names": "exclude_names",
                    "scr-exclude-patterns": "exclude_patterns",
                    "scr-comment-symbols": "comment_symbols",
                    "scr-exclude-comment-pattern": "exclude_comment_pattern",
                    "scr-language-filter": "language_filter",
                }
                field = mapping.get(event.input.id or "")
                if field:
                    setattr(plugin.state, field, event.value)
                    plugin.on_state_changed()

            def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
                if event.checkbox.id == "scr-recursive":
                    plugin.state.recursive = event.value
                elif event.checkbox.id == "scr-gitignore":
                    plugin.state.use_gitignore = event.value
                else:
                    return
                plugin.on_state_changed()

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "scr-delete-selected":
                    # отдельная асинхронная операция удаления
                    asyncio.create_task(plugin.apply_selected_deletion())

        return _OptionsPanel()

    def build_cli_preview(self) -> str:
        """Показать пример CLI-команды comment_extractor с текущими настройками."""
        parts: List[str] = ["comment-extractor"]

        if self.state.recursive:
            parts.append("-r")

        if self.state.pattern.strip():
            parts.extend(["-p", self.state.pattern])

        if self.state.comment_symbols.strip():
            parts.extend(["-c", self.state.comment_symbols])

        if self.state.exclude_comment_pattern.strip():
            parts.extend(["-e", self.state.exclude_comment_pattern])

        if self.state.language_filter.strip():
            parts.extend(["-l", self.state.language_filter])

        if self.state.use_gitignore:
            parts.append("--use-gitignore")

        dirs = _split_space_separated(self.state.directories)
        parts.extend(dirs or ["."])

        return " ".join(shlex.quote(p) for p in parts)

    # ------------------------------------------------------------------ Вспомогательные методы

    def _build_config_for_scan(self) -> CommentExtractorConfig:
        """Построить CommentExtractorConfig для шага сканирования."""
        dirs = _split_space_separated(self.state.directories) or ["."]
        patterns = self.state.pattern.strip() or "*"

        return CommentExtractorConfig(
            directories=dirs,
            include_pattern=patterns,
            recursive=self.state.recursive,
            exclude_dirs=set(_split_space_separated(self.state.exclude_dirs)),
            exclude_names=set(_split_space_separated(self.state.exclude_names)),
            exclude_patterns=set(_split_space_separated(self.state.exclude_patterns)),
            use_gitignore=self.state.use_gitignore,
            custom_gitignore=None,
            comment_symbols=self.state.comment_symbols or None,
            exclude_comment_pattern=self.state.exclude_comment_pattern or None,
            language_filter=self.state.language_filter or None if self.state.language_filter.strip() else None,
            remove_comments=False,
            preview_mode=True,
            export_file=None,
            log_file=None,
            use_cache=False,
            directory_recursion={},
            split_streams=True,
        )

    def _update_details_panel(self, widget: Optional[Widget]) -> None:
        """Заменить содержимое вкладки Details."""
        pane = self.screen.query_one("#details", TabPane)
        pane.remove_children()
        if widget is None:
            pane.mount(Static("No details", id="details-placeholder"))
        else:
            pane.mount(widget)

    def _render_details(self) -> None:
        """Построить список комментариев в Details."""
        if not self._scan_results:
            self._update_details_panel(None)
            return

        comments_widget = _CommentsList(self._scan_results, self._selected_indices)
        self._update_details_panel(comments_widget)

    # ------------------------------------------------------------------ Основные действия

    async def run(self) -> None:
        """Шаг 1: поиск всех комментариев по текущей конфигурации."""
        logs = self.screen.query_one("#logs-area")
        outputs = self.screen.query_one("#outputs-area", TextArea)

        logs.add_log("INFO", "Scanning comments...")

        config = self._build_config_for_scan()

        def _do_scan() -> Dict[str, Any]:
            processor = CommentProcessor(config)
            buf = io.StringIO()
            # Глушим прогресс и возможные print'ы в stdout/stderr
            with redirect_stdout(buf), redirect_stderr(buf):
                return processor.process_files()

        try:
            result = await asyncio.to_thread(_do_scan)
        except Exception as e:
            logs.add_log("ERROR", f"Comment scan failed: {e!r}")
            return

        comments: List[Dict[str, Any]] = result.get("comments", [])
        self._scan_results = comments
        self._selected_indices.clear()

        total_files = int(result.get("total_files", 0))
        total_comments = int(result.get("total_comments", len(comments)))

        outputs.text = (
            f"Scan finished.\n\n"
            f"Files processed: {total_files}\n"
            f"Comments found: {total_comments}\n\n"
            "Open the 'Details' tab to select comments for removal."
        )

        logs.add_log("INFO", f"Scan complete: {total_comments} comments in {total_files} files.")
        self._render_details()

    async def apply_selected_deletion(self) -> None:
        """Шаг 2: удалить только выбранные пользователем комментарии."""
        logs = self.screen.query_one("#logs-area")
        outputs = self.screen.query_one("#outputs-area", TextArea)

        if not self._scan_results:
            logs.add_log("WARNING", "Nothing to delete: run scan first.")
            return
        if not self._selected_indices:
            logs.add_log("WARNING", "No comments selected for deletion.")
            return

        # Собираем: файл -> множество ключей комментариев
        targets: Dict[Path, Set[CommentKey]] = {}
        for idx in self._selected_indices:
            if idx < 0 or idx >= len(self._scan_results):
                continue
            c = self._scan_results[idx]
            file_path = Path(c["file"]).resolve()
            key: CommentKey = (
                int(c["start_line"]),
                int(c["start_col"]),
                int(c["end_line"]),
                int(c["end_col"]),
                c.get("cell_index"),
            )
            targets.setdefault(file_path, set()).add(key)

        total_targets = sum(len(v) for v in targets.values())
        logs.add_log(
            "INFO",
            f"Removing {total_targets} selected comments from {len(targets)} files...",
        )

        def _do_apply() -> Tuple[int, int]:
            removed_total = 0
            affected_files = 0

            for path, keys in targets.items():
                if not keys:
                    continue
                if path.suffix.lower() == ".ipynb":
                    removed = self._apply_to_ipynb(path, keys)
                else:
                    removed = self._apply_to_text_file(path, keys)
                if removed > 0:
                    affected_files += 1
                    removed_total += removed

            return removed_total, affected_files

        try:
            removed_total, affected_files = await asyncio.to_thread(_do_apply)
        except Exception as e:
            logs.add_log("ERROR", f"Failed to delete comments: {e!r}")
            return

        logs.add_log(
            "INFO",
            f"Removed {removed_total} comments in {affected_files} files.",
        )
        outputs.text = (
            f"Removed {removed_total} comments in {affected_files} files.\n"
            "You can run another scan to verify the result."
        )

        # После применения обнуляем результаты и чистим Details
        self._scan_results = []
        self._selected_indices.clear()
        self._update_details_panel(None)

    # ------------------------------------------------------------------ Низкоуровневое применение к файлам

    def _apply_to_text_file(self, file_path: Path, keys: Set[CommentKey]) -> int:
        """Удалить выбранные комментарии из обычного текстового файла."""
        if not keys:
            return 0

        if FileContentDetector.detect_file_type(file_path) != FileType.TEXT:
            return 0

        encoding = FileContentDetector.detect_encoding(file_path)
        try:
            with open(file_path, "r", encoding=encoding, errors="strict") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            encoding = "latin-1"
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()

        # Выбираем стиль комментариев
        if self.state.comment_symbols.strip():
            style = CommentStyle.from_override(self.state.comment_symbols)
        else:
            style = CommentStyle.from_extension(file_path.suffix)
        if not style.line_markers and not style.block_markers:
            style = CommentStyle(line_markers=("#",), block_markers=())

        scanner = CommentScanner(
            style,
            exclude_comment_pattern=self.state.exclude_comment_pattern or None,
        )

        keys_local = set(keys)

        def should_remove(m: CommentMatch) -> bool:
            key: CommentKey = (m.start_line, m.start_col, m.end_line, m.end_col, m.cell_index)
            return key in keys_local

        out_lines, _matches, removed_count = scanner.scan_and_strip(
            lines,
            remove=True,
            should_remove=should_remove,
        )

        if removed_count <= 0:
            return 0

        ok = safe_write(file_path, "".join(out_lines), encoding=encoding, backup=True)
        if not ok:
            raise RuntimeError(f"Failed to write updated file: {file_path}")
        return removed_count

    def _apply_to_ipynb(self, file_path: Path, keys: Set[CommentKey]) -> int:
        """Удалить выбранные комментарии из Jupyter Notebook (.ipynb)."""
        if not keys:
            return 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                notebook = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to read notebook {file_path}: {e}") from e

        # Определяем язык ядра и стиль комментариев
        dummy_cfg = CommentExtractorConfig(
            directories=[str(file_path.parent)],
            include_pattern="*",
            recursive=False,
        )
        cp = CommentProcessor(dummy_cfg)
        kernel_lang = cp._get_kernel_language(notebook)  # type: ignore[attr-defined]
        extension = cp.KERNEL_LANGUAGE_TO_EXTENSION.get(kernel_lang, ".py")

        if self.state.comment_symbols.strip():
            style = CommentStyle.from_override(self.state.comment_symbols)
        else:
            style = CommentStyle.from_extension(extension)
        if not style.line_markers and not style.block_markers:
            style = CommentStyle(line_markers=("#",), block_markers=())

        # Разбиваем нужные ключи по ячейкам
        keys_by_cell: Dict[int, Set[CommentKey]] = {}
        for start_line, start_col, end_line, end_col, cell_index in keys:
            if cell_index is None:
                continue
            idx = int(cell_index)
            keys_by_cell.setdefault(idx, set()).add(
                (start_line, start_col, end_line, end_col, cell_index)
            )

        total_removed = 0
        modified = False

        cells = notebook.get("cells", [])
        for cell_idx, cell in enumerate(cells):
            if cell.get("cell_type") != "code":
                continue

            cell_keys = keys_by_cell.get(cell_idx)
            if not cell_keys:
                continue

            source = cell.get("source", [])
            if isinstance(source, str):
                lines = source.splitlines(keepends=True)
            elif isinstance(source, list):
                lines: List[str] = []
                for line in source:
                    if isinstance(line, str):
                        if not line.endswith("\n"):
                            line = line + "\n"
                        lines.append(line)
                    else:
                        lines.append(str(line) + "\n")
            else:
                continue

            if not lines:
                continue

            scanner = CommentScanner(
                style,
                exclude_comment_pattern=self.state.exclude_comment_pattern or None,
            )

            cell_keys_local = cell_keys

            def should_remove(m: CommentMatch) -> bool:
                key: CommentKey = (m.start_line, m.start_col, m.end_line, m.end_col, m.cell_index)
                return key in cell_keys_local

            out_lines, _matches, removed_count = scanner.scan_and_strip(
                lines,
                remove=True,
                should_remove=should_remove,
                cell_index=cell_idx,
            )

            if removed_count > 0:
                total_removed += removed_count
                modified = True
                if isinstance(source, str):
                    cell["source"] = "".join(out_lines)
                else:
                    cell["source"] = out_lines

        if not modified:
            return 0

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(notebook, f, ensure_ascii=False, indent=1)
        except Exception as e:
            raise RuntimeError(f"Failed to write notebook {file_path}: {e}") from e

        return total_removed


tool_registry.register(SelectiveCommentRemovalTool)
