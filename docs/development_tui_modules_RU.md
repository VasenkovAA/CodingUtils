## 1. Общая идея плагинной системы

Цель: чтобы каждый инструмент (tree‑generator, comment‑extractor, выборочное удаление комментариев, анонимайзер и т.п.) был:

- полностью инкапсулирован в одном классе;
- сам описывал:
  - свою конфигурацию (state);
  - UI для ввода параметров;
  - способ построения CLI‑строки (для превью);
  - логику запуска/выполнения;
- и автоматически подхватывался TUI без изменения `tui/tui.py`.

Каркас TUI знает только:

- какие плагины зарегистрированы в `tool_registry`;
- как у выбранного плагина получить:
  - панель опций (`create_options_panel`);
  - CLI‑строку (`build_cli_preview`);
  - действие по нажатию `Send` (`run`).

Все детали конкретного инструмента — внутри плагина.

---

## 2. Структура файлов

Минимальный набор:

```text
tui/
  __init__.py
  tui.py               # основной TUI
  plugins_base.py      # базовый интерфейс плагинов + реестр
  plugins/
    __init__.py        # импортирует модули плагинов
    tree_generator.py  # пример реального плагина
```

Новый плагин создаётся как новый файл внутри `tui/plugins/`, например:

```text
tui/plugins/comment_extractor.py
tui/plugins/anonymizer.py
```

и регистрируется через `tool_registry.register(...)`.

---

## 3. Базовые сущности: ToolMeta, ToolPlugin, ToolRegistry

### 3.1. ToolMeta

`ToolMeta` описывает плагин в меню выбора инструмента:

```python
@dataclass(frozen=True)
class ToolMeta:
    id: str           # внутренний ID (строка), например "tree-generator"
    label: str        # подпись в Select, например "tree-generator"
    description: str = ""
```

- `id` — используется как значение в селекторе и ключ в реестре.
- `label` — что видит пользователь в списке методов.
- `description` — пока не используется в UI, но пригодится для подсказок/хинтов.

### 3.2. ToolPlugin

Это базовый абстрактный класс, от которого наследуются все плагины.

```python
class ToolPlugin(ABC):
    meta: ToolMeta

    def __init__(self, screen: "MainScreen") -> None:
        self.screen = screen

    @abstractmethod
    def create_options_panel(self) -> Widget:
        ...

    def build_cli_preview(self) -> str:
        return self.meta.id

    @abstractmethod
    async def run(self) -> None:
        ...

    def on_selected(self) -> None:
        pass

    def on_state_changed(self) -> None:
        if hasattr(self.screen, "update_cli_bar"):
            self.screen.update_cli_bar()
```

Обязательные методы:

- `create_options_panel(self) -> Widget`
  - возвращает корневой виджет (обычно `Container` / `Vertical` / `TabbedContent`), который будет помещён в правую панель опций.
  - внутри вы сами создаёте `Input`, `Checkbox`, `Select` и т.п., и в их `on_*_changed` меняете состояние плагина.

- `async def run(self) -> None`
  - вызывается при нажатии `Send` / `Ctrl+J`.
  - здесь вы:
    - читаете `self.state` (ваша dataclass‑конфигурация),
    - вызываете backend‑код (`ProjectTreeGenerator`, `CommentProcessor`, `anonymizer` и т.п.),
    - пишете результат в `OutputsArea`,
    - логируете шаги в `LogsArea`,
    - обрабатываете ошибки.

Необязательные, но полезные:

- `build_cli_preview(self) -> str`
  - генерирует CLI‑строку на основе `self.state`.
  - вызывается `MainScreen.update_cli_bar()` и отображается в `url-input`.
  - по умолчанию возвращает только `id` плагина, но обычно вы переопределяете, чтобы показать, какие флаги активны.

- `on_selected(self) -> None`
  - вызывается, когда пользователь выбирает этот инструмент в селекторе.
  - можно использовать, чтобы сбросить/обновить состояние, подгрузить что‑то кэшированное и т.п.

- `on_state_changed(self) -> None`
  - следует вызывать в `on_input_changed`/`on_checkbox_changed` ваших UI‑виджетов, когда меняются параметры.
  - базовая реализация дергает `screen.update_cli_bar()`, то есть обновляет CLI‑строку.

### 3.3. ToolRegistry и tool_registry

`ToolRegistry` — глобальный реестр типов плагинов:

```python
class ToolRegistry:
    def register(self, plugin_cls: Type[ToolPlugin]) -> None: ...
    def create_all(self, screen: "MainScreen") -> Dict[str, ToolPlugin]: ...
    def metas(self) -> List[ToolMeta]: ...
    def get(self, tool_id: str) -> Optional[Type[ToolPlugin]]: ...
```

Глобальный экземпляр:

```python
tool_registry = ToolRegistry()
```

Использование:

- Плагин регистрирует себя:

  ```python
  tool_registry.register(MyCoolTool)
  ```

- TUI (`MainScreen`) создаёт экземпляры:

  ```python
  self.plugins = tool_registry.create_all(self)
  ```

- Селектор методов (`CommandSelector`) строит список вариантов:

  ```python
  metas = tool_registry.metas()
  options = [(m.label, m.id) for m in metas]
  ```

---

## 4. Жизненный цикл плагина в TUI

1. При запуске TUI:
   - импортируется `tui.plugins` (который импортирует все плагины);
   - каждый плагин модулем вызывает `tool_registry.register(...)`.

2. При создании `MainScreen`:
   - `self.plugins` инициализируется пустым словарём;
   - при первом обращении к `current_tool`:
     - `tool_registry.create_all(self)` создаёт по одному экземпляру каждого плагина,
     - в `selected_tool_id` записывается первый ID.

3. `OptionsEditor.on_mount()` вызывается рано, он делает:
   - `screen.current_tool` → плагины гарантированно инициализируются;
   - `tool.create_options_panel()` → панель опций отображается.

4. Пользователь взаимодействует с полями:
   - ваши виджеты внутри `create_options_panel` обновляют `self.state`,
   - вызывают `self.on_state_changed()` → обновляется CLI‑строка.

5. Нажатие `Send` / `Ctrl+J`:
   - `MainScreen.action_send_request()` вызывает `await current_tool.run()`;
   - плагин выполняет свою задачу, пишет вывод в `OutputsArea` и логи в `LogsArea`.

6. Смена инструмента в селекторе:
   - `MainScreen.selected_tool_id` меняется;
   - вызывается `tool.on_selected()`;
   - `OptionsEditor.update_editor()` перерисовывает панель опций под новый плагин;
   - CLI‑строка обновляется.

---

## 5. Как обратиться к Outputs/Logs/Details из плагина

У плагина есть доступ к `self.screen` (экземпляр `MainScreen`), а через него можно найти нужные области.

- **OutputsArea** (`TextArea`, id=`"outputs-area"`):

  ```python
  from textual.widgets import TextArea

  outputs = self.screen.query_one("#outputs-area", TextArea)
  outputs.text = "Some output..."
  ```

- **LogsArea** (`LogsArea`, id=`"logs-area"`), у него есть метод `add_log(level, message)`:

  ```python
  logs = self.screen.query_one("#logs-area")
  logs.add_log("INFO", "Starting my plugin...")
  logs.add_log("ERROR", f"Something went wrong: {e!r}")
  ```

- **Details** вкладка (резерв для интерактивных инструментов):

  Внутри `ResponseArea` есть метод:

  ```python
  class ResponseArea(Container):
      def set_details_widget(self, widget: Static | None) -> None:
          ...
  ```

  Плагин может:

  ```python
  from textual.widgets import Static
  from tui.tui import ResponseArea  # или через self.screen.query

  response_area = self.screen.query_one(ResponseArea)
  response_area.set_details_widget(Static("Detailed info here"))
  ```

  или смонтировать более сложный виджет (например, таблицу с чекбоксами для выборочного удаления).

---

## 6. Пример: как написать простой плагин с нуля

Допустим, вы хотите сделать плагин `echo`, который:

- имеет одно поле `text`;
- показывает его в CLI‑строке (`echo "..."`);
- по нажатию `Send` просто пишет этот текст в `Outputs` и лог.

### 6.1. Создать файл `tui/plugins/echo.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Input, Static, TextArea

from tui.plugins_base import ToolPlugin, ToolMeta, tool_registry


@dataclass
class EchoState:
    text: str = ""


class EchoTool(ToolPlugin):
    meta = ToolMeta(
        id="echo",
        label="echo",
        description="Simple echo tool",
    )

    def __init__(self, screen: "MainScreen") -> None:  # type: ignore[name-defined]
        super().__init__(screen)
        self.state = EchoState()

    def create_options_panel(self) -> Vertical:
        plugin = self

        class _EchoOptions(Vertical):
            def compose(self) -> ComposeResult:
                yield Label("Text to echo:")
                yield Input(
                    id="echo-text-input",
                    placeholder="Hello, world!",
                    value=plugin.state.text,
                )
                yield Static("This tool just prints the text to Outputs/Logs.")

            def on_input_changed(self, event: Input.Changed) -> None:
                if event.input.id == "echo-text-input":
                    plugin.state.text = event.value
                    plugin.on_state_changed()

        return _EchoOptions()

    def build_cli_preview(self) -> str:
        text = self.state.text.strip()
        if text:
            return f'echo "{text}"'
        return "echo"

    async def run(self) -> None:
        logs = self.screen.query_one("#logs-area")
        outputs = self.screen.query_one("#outputs-area", TextArea)

        text = self.state.text or ""
        logs.add_log("INFO", f"Echo: {text!r}")
        outputs.text = text


tool_registry.register(EchoTool)
```

### 6.2. Подключить плагин

В `tui/plugins/__init__.py`:

```python
from . import tree_generator  # noqa: F401
from . import echo            # noqa: F401   <-- добавить эту строку
```

Запуск:

```bash
cd ~/sources/CodingUtils
python -m tui.tui
```

Теперь в селекторе должен появиться `echo`. Работу с этим плагином каркас TUI реализует автоматически.

---

## 7. Возможности для более сложных плагинов

Плагинная архитектура уже позволяет делать:

1. **Интерактивные инструменты со сложным UI**:
   - в `create_options_panel` вы можете построить `TabbedContent` с множеством вкладок;
   - во `ResponseArea` можно вывести интерактивный «детальный» вид:
     - таблицу найденных комментариев/секретов;
     - дерево файлов;
     - чекбоксы для выборочного применения изменений и т.п.

2. **Интеграция с существующими backend‑модулями**:
   - `tree-generator` уже интегрирован через `ProjectTreeGenerator` и `TreeConfig`;
   - аналогично можно сделать плагин для `comment_extractor.CommentProcessor`;
   - для будущей функции «выборочного удаления комментариев» можно:
     - сначала прогнать сканирование (только сбор `CommentMatch`),
     - представить результаты в Details‑таблице,
     - позволить пользователю отметить, что удалять,
     - и затем в `run` или отдельной кнопке «Apply» выполнить модификации.

3. **Богатый логгинг и визуальный фидбек**:
   - логи через `logs.add_log(level, message)` — видны сразу в отдельной вкладке;
   - при ошибках плагин не должен падать — просто логировать `ERROR` и, при необходимости, показывать сообщение в `Outputs` или Details.

4. **Безопасное внедрение новых плагинов**:
   - если при инициализации плагина в `__init__` случится ошибка — `ToolRegistry.create_all` её залогирует в stderr и просто не добавит этот плагин, не ломая остальные;
   - если в `create_options_panel` плагин кинет исключение — `OptionsEditor` поймает его и покажет `Failed to create options panel: ...`;
   - если в `run` вы не перехватили исключение — `MainScreen.action_send_request` поймает и залогирует `Tool '...' failed: ...`.

---

## 8. Рекомендации и лучшие практики

1. **Храните состояние в dataclass’е**
   Для каждого плагина удобно завести `@dataclass`:

   ```python
   @dataclass
   class MyToolState:
       directories: str = ""
       pattern: str = "*.py"
       recursive: bool = True
       # и т.д.
   ```

   и в `__init__`:

   ```python
   self.state = MyToolState()
   ```

   Это делает состояние плагина явным и удобным для обновления/сериализации.

2. **Обновляйте CLI‑строку через `on_state_changed`**
   В каждом обработчике изменений UI:

   ```python
   plugin.state.some_field = value
   plugin.on_state_changed()
   ```

   Это автоматически обновит строку `url-input` через `MainScreen.update_cli_bar()`.

3. **Логируйте всё важное**
   В `run` используйте:

   ```python
   logs = self.screen.query_one("#logs-area")
   logs.add_log("INFO", "Starting job")
   logs.add_log("ERROR", f"Failed to do X: {e!r}")
   ```

   Это поможет отлаживать плагины и видеть, что происходит.

4. **Отделяйте сканирование и применение изменений**
   Для сложных инструментов (комментарии/секреты) удобно разделить:

   - `scan()` — только поиск, вывод результатов в Details;
   - `apply()` — применение к выбранным элементам.

   Тогда `run()` может вызывать `scan()`, а отдельная кнопка/действие — `apply()`.

5. **Не полагайтесь на глобальное состояние**
   Всё, что нужно плагину, храните в `self.state` и через `self.screen` (MainScreen). Не трогайте напрямую другие плагины.

6. **Не меняйте код `tui/tui.py` ради нового плагина**
   Если для добавления плагина приходится лезть в `MainScreen` или `OptionsEditor` — архитектурно что‑то пошло не так. Стремитесь к тому, чтобы всё было в `tui/plugins/...` и `tui/plugins/__init__.py`.

---

## 9. Добавление нового «боевого» плагина: краткий чек‑лист

1. Создать файл `tui/plugins/my_tool.py`.
2. Импортировать базу:

   ```python
   from tui.plugins_base import ToolPlugin, ToolMeta, tool_registry
   ```

3. Описать состояние (dataclass).
4. Описать класс `MyTool(ToolPlugin)`:
   - `meta = ToolMeta(...)`;
   - `__init__(self, screen)` — инициализировать `self.state`;
   - `create_options_panel` — построить UI и связать его с `self.state`;
   - `build_cli_preview` — собрать CLI на основе `self.state`;
   - `async def run(self)` — вызвать backend‑код, записать вывод/логи.
5. В конце файла зарегистрировать:

   ```python
   tool_registry.register(MyTool)
   ```

6. В `tui/plugins/__init__.py` добавить:

   ```python
   from . import my_tool  # noqa: F401
   ```

7. Запустить:

   ```bash
   cd ~/sources/CodingUtils
   python -m tui.tui
   ```

   Убедиться, что новый инструмент появился в селекторе и работает.
