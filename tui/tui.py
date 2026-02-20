import asyncio
from pathlib import Path
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
    Tree,
)
from textual.widgets.tree import TreeNode
from textual.reactive import reactive
from textual.message import Message

# =========================================================
# Messages
# =========================================================

class TreePathsChanged(Message):
    """Сообщение об изменении путей tree-generator"""

    def __init__(self, paths: str):
        self.paths = paths
        super().__init__()


class TreeRecursiveChanged(Message):
    """Сообщение об изменении рекурсивного флага tree-generator"""

    def __init__(self, recursive: bool):
        self.recursive = recursive
        super().__init__()


class TreeMaxDepthChanged(Message):
    """Сообщение об изменении максимальной глубины tree-generator"""

    def __init__(self, max_depth: str):
        self.max_depth = max_depth
        super().__init__()


class TreePatternsChanged(Message):
    """Сообщение об изменении паттернов tree-generator"""

    def __init__(self, patterns: str):
        self.patterns = patterns
        super().__init__()


class TreeFormatChanged(Message):
    """Сообщение об изменении формата вывода tree-generator"""

    def __init__(self, format: str):
        self.format = format
        super().__init__()


class TreeOutputFileChanged(Message):
    """Сообщение об изменении файла вывода tree-generator"""

    def __init__(self, output_file: str):
        self.output_file = output_file
        super().__init__()


class TreeExcludeDirsChanged(Message):
    """Сообщение об изменении исключений директорий по имени сегмента пути"""

    def __init__(self, exclude_dirs: str):
        self.exclude_dirs = exclude_dirs
        super().__init__()


class TreeExcludeNamesChanged(Message):
    """Сообщение об изменении исключений по базовому имени"""

    def __init__(self, exclude_names: str):
        self.exclude_names = exclude_names
        super().__init__()


class TreeExcludePatternsChanged(Message):
    """Сообщение об изменении исключений по паттерну"""

    def __init__(self, exclude_patterns: str):
        self.exclude_patterns = exclude_patterns
        super().__init__()


class TreeExcludeEmptyDirsChanged(Message):
    """Сообщение об изменении флага исключения пустых директорий"""

    def __init__(self, exclude_empty_dirs: bool):
        self.exclude_empty_dirs = exclude_empty_dirs
        super().__init__()


class TreeGitignoreAutoChanged(Message):
    """Сообщение об изменении флага авто-поиска .gitignore"""

    def __init__(self, gitignore_auto: bool):
        self.gitignore_auto = gitignore_auto
        super().__init__()


class TreeGitignoreSpecifyChanged(Message):
    """Сообщение об изменении пути к специфичному .gitignore"""

    def __init__(self, gitignore_specify: str):
        self.gitignore_specify = gitignore_specify
        super().__init__()


class TreeGitignoreDisableChanged(Message):
    """Сообщение об изменении флага отключения .gitignore"""

    def __init__(self, gitignore_disable: bool):
        self.gitignore_disable = gitignore_disable
        super().__init__()


class TreeShowSizeChanged(Message):
    """Сообщение об изменении флага показа размера файлов"""

    def __init__(self, show_size: bool):
        self.show_size = show_size
        super().__init__()


class TreeShowPermissionsChanged(Message):
    """Сообщение об изменении флага показа прав доступа"""

    def __init__(self, show_permissions: bool):
        self.show_permissions = show_permissions
        super().__init__()


class TreeShowLastModifiedChanged(Message):
    """Сообщение об изменении флага показа даты изменения"""

    def __init__(self, show_last_modified: bool):
        self.show_last_modified = show_last_modified
        super().__init__()


class TreeShowFileTypeChanged(Message):
    """Сообщение об изменении флага показа типа файла"""

    def __init__(self, show_file_type: bool):
        self.show_file_type = show_file_type
        super().__init__()


class TreeShowHiddenChanged(Message):
    """Сообщение об изменении флага показа скрытых файлов"""

    def __init__(self, show_hidden: bool):
        self.show_hidden = show_hidden
        super().__init__()


class TreeSortByChanged(Message):
    """Сообщение об изменении параметра сортировки"""

    def __init__(self, sort_by: str):
        self.sort_by = sort_by
        super().__init__()


class TreeSortReverseChanged(Message):
    """Сообщение об изменении флага обратной сортировки"""

    def __init__(self, sort_reverse: bool):
        self.sort_reverse = sort_reverse
        super().__init__()


class TreeIndentStyleChanged(Message):
    """Сообщение об изменении стиля отступов"""

    def __init__(self, indent_style: str):
        self.indent_style = indent_style
        super().__init__()


class TreeIndentSizeChanged(Message):
    """Сообщение об изменении размера отступов"""

    def __init__(self, indent_size: str):
        self.indent_size = indent_size
        super().__init__()


class TreeMaxWidthChanged(Message):
    """Сообщение об изменении максимальной ширины"""

    def __init__(self, max_width: str):
        self.max_width = max_width
        super().__init__()


class TreeLogFileChanged(Message):
    """Сообщение об изменении файла логов"""

    def __init__(self, log_file: str):
        self.log_file = log_file
        super().__init__()


class TreeVerboseChanged(Message):
    """Сообщение об изменении флага подробного вывода"""

    def __init__(self, verbose: bool):
        self.verbose = verbose
        super().__init__()


# =========================================================
# Header
# =========================================================

class AppHeader(Horizontal):
    def compose(self) -> ComposeResult:
        yield Label("[b]Posting[/] [dim]v2.0.0[/]", id="app-title")
        yield Label("user@localhost", id="app-user-host")


# =========================================================
# Method selector
# =========================================================

class CommandSelector(Select):
    def __init__(self):
        super().__init__(
            [
                ("tree-generator", "tree-generator"),
                ("comment-extractor", "comment-extractor"),
                ("file-merger", "file-merger"),
            ],
            value="tree-generator",
            allow_blank=False,
            id="method-selector",
        )


# =========================================================
# Command bar
# =========================================================

class CommandBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield CommandSelector()
        yield Input(id="url-input")
        yield Button("Send", variant="primary", id="send-button")
        yield Static("", id="response-status")


# =========================================================
# File system tree
# =========================================================

class FileSystemTree(Tree):
    def __init__(self, root_path: Path):
        super().__init__(root_path.name, id="collection-tree")
        self.root_path = root_path.resolve()
        self.loaded_paths = set()

    def on_mount(self) -> None:
        self.root.data = self.root_path
        asyncio.create_task(self.load_children(self.root))

    async def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        if node.data and node.data not in self.loaded_paths:
            await self.load_children(node)

    async def load_children(self, node: TreeNode) -> None:
        path = node.data
        if not path or not path.is_dir():
            return

        self.loaded_paths.add(path)
        node.remove_children()

        try:
            items = await asyncio.to_thread(list, path.iterdir())
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

            for item in items:
                if item.name.startswith("."):
                    continue

                if item.is_dir():
                    child = node.add(item.name)
                    child.data = item
                    child.add_leaf("...")
                else:
                    leaf = node.add_leaf(item.name)
                    leaf.data = item

        except PermissionError:
            node.add_leaf("Permission denied")


class FileBrowser(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("[b]File System[/]", classes="section-title")
        yield FileSystemTree(Path.cwd())


# =========================================================
# Options tabs for tree-generator
# =========================================================

class InputTab(Vertical):
    """Вкладка Input для tree-generator"""
    
    def compose(self) -> ComposeResult:
        yield Label("Paths (space-separated):")
        yield Input(
            placeholder="src tests",
            id="tree-paths-input"
        )
        
        main_screen = self.app.screen
        if hasattr(main_screen, 'tree_recursive'):
            recursive_value = main_screen.tree_recursive
        else:
            recursive_value = False
            
        yield Checkbox(
            "Recursive (-r)",
            value=recursive_value,
            id="tree-recursive-checkbox"
        )
        
        yield Label("Max depth (--max-depth):")
        yield Input(
            placeholder="2",
            id="tree-max-depth-input"
        )
        
        yield Label("Patterns (space-separated):")
        yield Input(
            placeholder="*.py",
            id="tree-patt-input"
        )
    
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tree-paths-input":
            self.post_message(TreePathsChanged(event.value))
        elif event.input.id == "tree-patt-input":
            self.post_message(TreePatternsChanged(event.value))
        elif event.input.id == "tree-max-depth-input":
            self.post_message(TreeMaxDepthChanged(event.value))
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "tree-recursive-checkbox":
            self.post_message(TreeRecursiveChanged(event.value))


class OutputLogsTab(Vertical):
    """Вкладка Output/logs для tree-generator"""
    
    def compose(self) -> ComposeResult:
        yield Label("Output format:")
        
        main_screen = self.app.screen
        if hasattr(main_screen, 'tree_format'):
            format_value = main_screen.tree_format
        else:
            format_value = "empty"
            
        yield Select(
            [
                ("empty", "empty"),
                ("text", "text"),
                ("json", "json"),
                ("xml", "xml"),
                ("markdown", "markdown"),
            ],
            value=format_value,
            allow_blank=False,
            id="tree-format-select"
        )
        
        yield Label("Output to file (-o):")
        yield Input(
            placeholder="test.json",
            id="tree-output-file-input"
        )
        
        yield Label("Logs (stderr) and log file (--log-file):")
        yield Input(
            placeholder="tree.log",
            id="tree-log-file-input"
        )
        
        main_screen = self.app.screen
        if hasattr(main_screen, 'tree_verbose'):
            verbose_value = main_screen.tree_verbose
        else:
            verbose_value = False
            
        yield Checkbox(
            "More details in the logs (-v)",
            value=verbose_value,
            id="tree-verbose-checkbox"
        )
    
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "tree-format-select":
            self.post_message(TreeFormatChanged(event.value))
    
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tree-output-file-input":
            self.post_message(TreeOutputFileChanged(event.value))
        elif event.input.id == "tree-log-file-input":
            self.post_message(TreeLogFileChanged(event.value))
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "tree-verbose-checkbox":
            self.post_message(TreeVerboseChanged(event.value))


class ExclusionsTab(Vertical):
    """Вкладка Exclusions для tree-generator"""
    
    def compose(self) -> ComposeResult:
        yield Label("Exclude directories by path segment name (-ed):")
        yield Input(
            placeholder=".git node_modules",
            id="tree-exclude-dirs-input"
        )
        
        yield Label("Exclude by basename (file or directory name) (-en):")
        yield Input(
            placeholder="*.log *.tmp",
            id="tree-exclude-names-input"
        )
        
        yield Label("Exclude by pattern (-ep):")
        yield Input(
            placeholder="test_* temp_*",
            id="tree-exclude-patterns-input"
        )
        
        main_screen = self.app.screen
        if hasattr(main_screen, 'tree_exclude_empty_dirs'):
            exclude_empty_value = main_screen.tree_exclude_empty_dirs
        else:
            exclude_empty_value = False
            
        yield Checkbox(
            "Exclude empty directories (--exclude-empty-dirs)",
            value=exclude_empty_value,
            id="tree-exclude-empty-dirs-checkbox"
        )
    
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tree-exclude-dirs-input":
            self.post_message(TreeExcludeDirsChanged(event.value))
        elif event.input.id == "tree-exclude-names-input":
            self.post_message(TreeExcludeNamesChanged(event.value))
        elif event.input.id == "tree-exclude-patterns-input":
            self.post_message(TreeExcludePatternsChanged(event.value))
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "tree-exclude-empty-dirs-checkbox":
            self.post_message(TreeExcludeEmptyDirsChanged(event.value))


class GitignoreTab(Vertical):
    """Вкладка Gitignore для tree-generator"""
    
    def compose(self) -> ComposeResult:
        main_screen = self.app.screen
        
        if hasattr(main_screen, 'tree_gitignore_auto'):
            gitignore_auto_value = main_screen.tree_gitignore_auto
        else:
            gitignore_auto_value = False
            
        yield Checkbox(
            "Enable auto-search for .gitignore (-ig)",
            value=gitignore_auto_value,
            id="tree-gitignore-auto-checkbox"
        )
        
        yield Label("Specify a specific .gitignore (-gi):")
        yield Input(
            placeholder="/path/to/.gitignore",
            id="tree-gitignore-specify-input"
        )
        
        if hasattr(main_screen, 'tree_gitignore_disable'):
            gitignore_disable_value = main_screen.tree_gitignore_disable
        else:
            gitignore_disable_value = False
            
        yield Checkbox(
            "Disable .gitignore (--no-gitignore)",
            value=gitignore_disable_value,
            id="tree-gitignore-disable-checkbox"
        )
    
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tree-gitignore-specify-input":
            self.post_message(TreeGitignoreSpecifyChanged(event.value))
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "tree-gitignore-auto-checkbox":
            self.post_message(TreeGitignoreAutoChanged(event.value))
        elif event.checkbox.id == "tree-gitignore-disable-checkbox":
            self.post_message(TreeGitignoreDisableChanged(event.value))


class MetadataTab(Vertical):
    """Вкладка Metadata для tree-generator"""
    
    def compose(self) -> ComposeResult:
        main_screen = self.app.screen
        
        # Чекбокс для показа размера файлов
        if hasattr(main_screen, 'tree_show_size'):
            show_size_value = main_screen.tree_show_size
        else:
            show_size_value = False
            
        yield Checkbox(
            "Show file sizes (--show-size)",
            value=show_size_value,
            id="tree-show-size-checkbox"
        )
        
        # Чекбокс для показа прав доступа
        if hasattr(main_screen, 'tree_show_permissions'):
            show_permissions_value = main_screen.tree_show_permissions
        else:
            show_permissions_value = False
            
        yield Checkbox(
            "Show permissions (--show-permissions)",
            value=show_permissions_value,
            id="tree-show-permissions-checkbox"
        )
        
        # Чекбокс для показа даты изменения
        if hasattr(main_screen, 'tree_show_last_modified'):
            show_last_modified_value = main_screen.tree_show_last_modified
        else:
            show_last_modified_value = False
            
        yield Checkbox(
            "Show modified date (--show-last-modified)",
            value=show_last_modified_value,
            id="tree-show-last-modified-checkbox"
        )
        
        # Чекбокс для показа типа файла
        if hasattr(main_screen, 'tree_show_file_type'):
            show_file_type_value = main_screen.tree_show_file_type
        else:
            show_file_type_value = False
            
        yield Checkbox(
            "Show file type (text/binary/unknown) (--show-file-type)",
            value=show_file_type_value,
            id="tree-show-file-type-checkbox"
        )
        
        # Чекбокс для показа скрытых файлов
        if hasattr(main_screen, 'tree_show_hidden'):
            show_hidden_value = main_screen.tree_show_hidden
        else:
            show_hidden_value = False
            
        yield Checkbox(
            "Show hidden (--show-hidden)",
            value=show_hidden_value,
            id="tree-show-hidden-checkbox"
        )
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "tree-show-size-checkbox":
            self.post_message(TreeShowSizeChanged(event.value))
        elif event.checkbox.id == "tree-show-permissions-checkbox":
            self.post_message(TreeShowPermissionsChanged(event.value))
        elif event.checkbox.id == "tree-show-last-modified-checkbox":
            self.post_message(TreeShowLastModifiedChanged(event.value))
        elif event.checkbox.id == "tree-show-file-type-checkbox":
            self.post_message(TreeShowFileTypeChanged(event.value))
        elif event.checkbox.id == "tree-show-hidden-checkbox":
            self.post_message(TreeShowHiddenChanged(event.value))


class SortingStyleTab(Vertical):
    """Вкладка Sorting/Style для tree-generator"""
    
    indent_style = reactive("empty")
    
    def compose(self) -> ComposeResult:
        main_screen = self.app.screen
        
        yield Label("Sorting (--sort-by):")
        if hasattr(main_screen, 'tree_sort_by'):
            sort_by_value = main_screen.tree_sort_by
        else:
            sort_by_value = "empty"
            
        yield Select(
            [
                ("empty", "empty"),
                ("name", "name"),
                ("size", "size"),
                ("modified", "modified"),
                ("type", "type"),
            ],
            value=sort_by_value,
            allow_blank=False,
            id="tree-sort-by-select"
        )
        
        if hasattr(main_screen, 'tree_sort_reverse'):
            sort_reverse_value = main_screen.tree_sort_reverse
        else:
            sort_reverse_value = False
            
        yield Checkbox(
            "Reverse order (--sort-reverse)",
            value=sort_reverse_value,
            id="tree-sort-reverse-checkbox"
        )
        
        yield Label("Max width (--max-width):")
            
        yield Input(
            placeholder="80",
            id="tree-max-width-input"
        )

        yield Label("Indent style (--indent-style):")
        if hasattr(main_screen, 'tree_indent_style'):
            indent_style_value = main_screen.tree_indent_style
        else:
            indent_style_value = "empty"
            
        self.indent_style = indent_style_value
        yield Select(
            [
                ("empty", "empty"),
                ("tree", "tree"),
                ("spaces", "spaces"),
                ("dashes", "dashes"),
            ],
            value=indent_style_value,
            allow_blank=False,
            id="tree-indent-style-select"
        )
        
        # Контейнер для зависимых опций (размер отступов)
        with Container(id="indent-size-container"):
            yield Label("Indent size (--indent-size):", id="indent-size-label")
            if hasattr(main_screen, 'tree_indent_size'):
                indent_size_value = main_screen.tree_indent_size
            else:
                indent_size_value = ""
            yield Input(
                placeholder="4",
                value=indent_size_value,
                id="tree-indent-size-input"
            )
        
    def on_mount(self) -> None:
        self.update_indent_size_visibility()
    
    def update_indent_size_visibility(self) -> None:
        """Обновляет видимость контейнера для размера отступов"""
        container = self.query_one("#indent-size-container")
        
        if self.indent_style in ["spaces", "dashes"]:
            container.display = True
        else:
            container.display = False
    
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "tree-sort-by-select":
            self.post_message(TreeSortByChanged(event.value))
        elif event.select.id == "tree-indent-style-select":
            self.indent_style = event.value
            self.update_indent_size_visibility()
            self.post_message(TreeIndentStyleChanged(event.value))
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "tree-sort-reverse-checkbox":
            self.post_message(TreeSortReverseChanged(event.value))
    
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tree-max-width-input":
            self.post_message(TreeMaxWidthChanged(event.value))
        elif event.input.id == "tree-indent-size-input":
            self.post_message(TreeIndentSizeChanged(event.value))


# =========================================================
# Options tabs for comment-extractor
# =========================================================

class CommentExtractorInputTab(Vertical):
    """Вкладка Input для comment-extractor"""
    
    def compose(self) -> ComposeResult:
        yield Static("Comment extractor input options will be available soon...", classes="placeholder")


class CommentExtractorOutputLogsTab(Vertical):
    """Вкладка Output/logs для comment-extractor"""
    
    def compose(self) -> ComposeResult:
        yield Static("Comment extractor output/logs options will be available soon...", classes="placeholder")


# =========================================================
# Options tabs for file-merger
# =========================================================

class FileMergerInputTab(Vertical):
    """Вкладка Input для file-merger"""
    
    def compose(self) -> ComposeResult:
        yield Static("File merger input options will be available soon...", classes="placeholder")


class FileMergerOutputLogsTab(Vertical):
    """Вкладка Output/logs для file-merger"""
    
    def compose(self) -> ComposeResult:
        yield Static("File merger output/logs options will be available soon...", classes="placeholder")


# =========================================================
# Редакторы для каждого метода
# =========================================================

class TreeGeneratorEditor(Container):
    """Редактор для tree-generator"""
    
    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Input", id="input"):
                yield InputTab()
            with TabPane("Output/logs", id="output-logs"):
                yield OutputLogsTab()
            with TabPane("Exclusions", id="exclusions"):
                yield ExclusionsTab()
            with TabPane("Gitignore", id="gitignore"):
                yield GitignoreTab()
            with TabPane("Metadata", id="metadata"):
                yield MetadataTab()
            with TabPane("Sorting/Style", id="sorting-style"):
                yield SortingStyleTab()


class CommentExtractorEditor(Container):
    """Редактор для comment-extractor"""
    
    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Input", id="input"):
                yield CommentExtractorInputTab()
            with TabPane("Output/logs", id="output-logs"):
                yield CommentExtractorOutputLogsTab()


class FileMergerEditor(Container):
    """Редактор для file-merger"""
    
    def compose(self) -> ComposeResult:
        with TabbedContent():
            with TabPane("Input", id="input"):
                yield FileMergerInputTab()
            with TabPane("Output/logs", id="output-logs"):
                yield FileMergerOutputLogsTab()


# =========================================================
# Options editor (динамически меняется в зависимости от метода)
# =========================================================

class OptionsEditor(Container):
    """Редактор запросов, который меняет содержимое в зависимости от выбранного метода"""
    
    def compose(self) -> ComposeResult:
        yield TreeGeneratorEditor()
    
    def update_editor(self) -> None:
        """Обновляет содержимое редактора в зависимости от выбранного метода"""
        main_screen = self.app.screen
        if not hasattr(main_screen, 'selected_method'):
            return
        
        self.remove_children()
        
        if main_screen.selected_method == "tree-generator":
            self.mount(TreeGeneratorEditor())
        elif main_screen.selected_method == "comment-extractor":
            self.mount(CommentExtractorEditor())
        elif main_screen.selected_method == "file-merger":
            self.mount(FileMergerEditor())


# =========================================================
# Outputs & Logs
# =========================================================

class OutputsArea(TextArea):
    def __init__(self):
        super().__init__(
            text="Output will appear here...",
            read_only=True,
            language="text",
            id="outputs-area",
        )


class LogsArea(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("[b]Execution Logs[/]", classes="logs-header")

    def add_log(self, level: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.mount(Static(f"[{level}] {ts} {message}"))
        self.scroll_end()


class ResponseArea(Container):
    def compose(self) -> ComposeResult:
        with TabbedContent(initial="outputs"):
            with TabPane("Outputs", id="outputs"):
                yield OutputsArea()
            with TabPane("Logs", id="logs"):
                yield LogsArea()


# =========================================================
# App body
# =========================================================

class AppBody(Horizontal):
    def compose(self) -> ComposeResult:
        yield FileBrowser(classes="section")
        with Vertical(id="main-content"):
            yield OptionsEditor(classes="section")
            yield ResponseArea(classes="section")


# =========================================================
# Main screen (STATE OWNER)
# =========================================================

class MainScreen(Screen):

    selected_method = reactive("tree-generator")
    tree_paths = reactive("")
    tree_recursive = reactive(False)
    tree_max_depth = reactive("")
    tree_patterns = reactive("")
    tree_format = reactive("empty")
    tree_output_file = reactive("")
    tree_exclude_dirs = reactive("")
    tree_exclude_names = reactive("")
    tree_exclude_patterns = reactive("")
    tree_exclude_empty_dirs = reactive(False)
    tree_gitignore_auto = reactive(False)
    tree_gitignore_specify = reactive("")
    tree_gitignore_disable = reactive(False)
    tree_show_size = reactive(False)
    tree_show_permissions = reactive(False)
    tree_show_last_modified = reactive(False)
    tree_show_file_type = reactive(False)
    tree_show_hidden = reactive(False)
    tree_sort_by = reactive("empty")
    tree_sort_reverse = reactive(False)
    tree_indent_style = reactive("empty")
    tree_indent_size = reactive("")
    tree_max_width = reactive("")
    tree_log_file = reactive("")
    tree_verbose = reactive(False)

    BINDINGS = [
        Binding("ctrl+j", "send_request", "Send"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield CommandBar()
        yield AppBody()
        yield Footer()

    # ---------- state coordination ----------

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "method-selector":
            old_method = self.selected_method
            self.selected_method = event.value
            
            if old_method == "tree-generator" and event.value != "tree-generator":
                self.tree_paths = ""
                self.tree_recursive = False
                self.tree_max_depth = ""
                self.tree_patterns = ""
                self.tree_format = "empty"
                self.tree_output_file = ""
                self.tree_exclude_dirs = ""
                self.tree_exclude_names = ""
                self.tree_exclude_patterns = ""
                self.tree_exclude_empty_dirs = False
                self.tree_gitignore_auto = False
                self.tree_gitignore_specify = ""
                self.tree_gitignore_disable = False
                self.tree_show_size = False
                self.tree_show_permissions = False
                self.tree_show_last_modified = False
                self.tree_show_file_type = False
                self.tree_show_hidden = False
                self.tree_sort_by = "empty"
                self.tree_sort_reverse = False
                self.tree_indent_style = "empty"
                self.tree_indent_size = ""
                self.tree_max_width = ""
                self.tree_log_file = ""
                self.tree_verbose = False
            
            request_editor = self.query_one(OptionsEditor)
            request_editor.update_editor()
        elif event.select.id == "tree-sort-by-select":
            self.tree_sort_by = event.value
        elif event.select.id == "tree-indent-style-select":
            self.tree_indent_style = event.value
            
    def on_tree_paths_changed(self, message: TreePathsChanged) -> None:
        self.tree_paths = message.paths

    def on_tree_recursive_changed(self, message: TreeRecursiveChanged) -> None:
        self.tree_recursive = message.recursive

    def on_tree_max_depth_changed(self, message: TreeMaxDepthChanged) -> None:
        self.tree_max_depth = message.max_depth

    def on_tree_patterns_changed(self, message: TreePatternsChanged) -> None:
        self.tree_patterns = message.patterns

    def on_tree_format_changed(self, message: TreeFormatChanged) -> None:
        self.tree_format = message.format

    def on_tree_output_file_changed(self, message: TreeOutputFileChanged) -> None:
        self.tree_output_file = message.output_file

    def on_tree_exclude_dirs_changed(self, message: TreeExcludeDirsChanged) -> None:
        self.tree_exclude_dirs = message.exclude_dirs

    def on_tree_exclude_names_changed(self, message: TreeExcludeNamesChanged) -> None:
        self.tree_exclude_names = message.exclude_names

    def on_tree_exclude_patterns_changed(self, message: TreeExcludePatternsChanged) -> None:
        self.tree_exclude_patterns = message.exclude_patterns

    def on_tree_exclude_empty_dirs_changed(self, message: TreeExcludeEmptyDirsChanged) -> None:
        self.tree_exclude_empty_dirs = message.exclude_empty_dirs

    def on_tree_gitignore_auto_changed(self, message: TreeGitignoreAutoChanged) -> None:
        self.tree_gitignore_auto = message.gitignore_auto

    def on_tree_gitignore_specify_changed(self, message: TreeGitignoreSpecifyChanged) -> None:
        self.tree_gitignore_specify = message.gitignore_specify

    def on_tree_gitignore_disable_changed(self, message: TreeGitignoreDisableChanged) -> None:
        self.tree_gitignore_disable = message.gitignore_disable

    def on_tree_show_size_changed(self, message: TreeShowSizeChanged) -> None:
        self.tree_show_size = message.show_size

    def on_tree_show_permissions_changed(self, message: TreeShowPermissionsChanged) -> None:
        self.tree_show_permissions = message.show_permissions

    def on_tree_show_last_modified_changed(self, message: TreeShowLastModifiedChanged) -> None:
        self.tree_show_last_modified = message.show_last_modified

    def on_tree_show_file_type_changed(self, message: TreeShowFileTypeChanged) -> None:
        self.tree_show_file_type = message.show_file_type

    def on_tree_show_hidden_changed(self, message: TreeShowHiddenChanged) -> None:
        self.tree_show_hidden = message.show_hidden

    def on_tree_sort_by_changed(self, message: TreeSortByChanged) -> None:
        self.tree_sort_by = message.sort_by

    def on_tree_sort_reverse_changed(self, message: TreeSortReverseChanged) -> None:
        self.tree_sort_reverse = message.sort_reverse

    def on_tree_indent_style_changed(self, message: TreeIndentStyleChanged) -> None:
        self.tree_indent_style = message.indent_style

    def on_tree_indent_size_changed(self, message: TreeIndentSizeChanged) -> None:
        self.tree_indent_size = message.indent_size

    def on_tree_max_width_changed(self, message: TreeMaxWidthChanged) -> None:
        self.tree_max_width = message.max_width

    def on_tree_log_file_changed(self, message: TreeLogFileChanged) -> None:
        self.tree_log_file = message.log_file

    def on_tree_verbose_changed(self, message: TreeVerboseChanged) -> None:
        self.tree_verbose = message.verbose

    def watch_selected_method(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_paths(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_recursive(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_max_depth(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_patterns(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_format(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_output_file(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_exclude_dirs(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_exclude_names(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_exclude_patterns(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_exclude_empty_dirs(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_gitignore_auto(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_gitignore_specify(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_gitignore_disable(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_show_size(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_show_permissions(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_show_last_modified(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_show_file_type(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_show_hidden(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_sort_by(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_sort_reverse(self, _: bool) -> None:
        self._update_url_bar()

    def watch_tree_indent_style(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_indent_size(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_max_width(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_log_file(self, _: str) -> None:
        self._update_url_bar()

    def watch_tree_verbose(self, _: bool) -> None:
        self._update_url_bar()

    def _update_url_bar(self) -> None:
        url_input = self.query_one("#url-input", Input)

        parts = [self.selected_method]
        
        if self.selected_method == "tree-generator":
            if self.tree_paths:
                parts.append(self.tree_paths)
            
            if self.tree_recursive:
                parts.append("-r")
            
            if self.tree_max_depth:
                parts.append("--max-depth")
                parts.append(self.tree_max_depth)
            
            if self.tree_patterns:
                parts.append("-p")
                parts.append(f'"{self.tree_patterns}"')
            
            if self.tree_exclude_dirs:
                parts.append("-ed")
                parts.append(f'"{self.tree_exclude_dirs}"')
            
            if self.tree_exclude_names:
                parts.append("-en")
                parts.append(f'"{self.tree_exclude_names}"')
            
            if self.tree_exclude_patterns:
                parts.append("-ep")
                parts.append(f'"{self.tree_exclude_patterns}"')
            
            if self.tree_exclude_empty_dirs:
                parts.append("--exclude-empty-dirs")
            
            if self.tree_gitignore_auto:
                parts.append("-ig")
            
            if self.tree_gitignore_specify:
                parts.append("-gi")
                parts.append(self.tree_gitignore_specify)
            
            if self.tree_gitignore_disable:
                parts.append("--no-gitignore")
            
            if self.tree_show_size:
                parts.append("--show-size")
            
            if self.tree_show_permissions:
                parts.append("--show-permissions")
            
            if self.tree_show_last_modified:
                parts.append("--show-last-modified")
            
            if self.tree_show_file_type:
                parts.append("--show-file-type")
            
            if self.tree_show_hidden:
                parts.append("--show-hidden")
            
            if self.tree_sort_by != "empty":
                parts.append("--sort-by")
                parts.append(self.tree_sort_by)
            
            if self.tree_sort_reverse:
                parts.append("--sort-reverse")
            
            if self.tree_indent_style != "empty":
                parts.append("--indent-style")
                parts.append(self.tree_indent_style)
            
            if self.tree_indent_size and self.tree_indent_style in ["spaces", "dashes"]:
                parts.append("--indent-size")
                parts.append(self.tree_indent_size)
            
            if self.tree_max_width:
                parts.append("--max-width")
                parts.append(self.tree_max_width)
            
            if self.tree_format != "empty":
                parts.append("-f")
                parts.append(self.tree_format)
            
            if self.tree_output_file:
                parts.append("-o")
                parts.append(self.tree_output_file)
            
            if self.tree_log_file:
                parts.append("--log-file")
                parts.append(self.tree_log_file)
            
            if self.tree_verbose:
                parts.append("-v")
                
        elif self.selected_method == "comment-extractor":
            pass
        elif self.selected_method == "file-merger":
            pass

        url_input.value = " ".join(parts)

    # ---------- actions ----------

    def action_send_request(self) -> None:
        logs = self.query_one(LogsArea)
        logs.add_log("INFO", f"Run: {self.query_one('#url-input').value}")


# =========================================================
# App
# =========================================================

class PostingReplicaApp(App):
    CSS_PATH = "styles.css"
    TITLE = "Posting TUI Replica"

    def on_mount(self) -> None:
        self.push_screen(MainScreen())


if __name__ == "__main__":
    PostingReplicaApp().run()