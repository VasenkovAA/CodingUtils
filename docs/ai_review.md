# Руководство пользователя: `ai-review` (CodingUtils)

## 1. Что это такое

`ai-review` — CLI-инструмент, который:

1) Находит файлы в проекте с учётом фильтров (паттерны, исключения, `.gitignore`).
2) Разбирает код (парсеры) и выделяет элементы для ревью (функции/классы/файлы).
3) Строит промт из шаблонов и отправляет в LLM (локально через LM Studio или в облако).
4) Сохраняет результаты в `reviews/` с версионированием и ведёт хеши (skip unchanged).

---

## 2. Установка

### 2.1. Из исходников (рекомендуется для разработки)
```bash
python -m venv venv
source venv/bin/activate
pip install -e .
```

### 2.2. Зависимости
Для работы YAML-конфигурации нужен PyYAML:
- `PyYAML>=6.0`

Проверь:
```bash
python -c "import yaml; print('yaml ok')"
```

---

## 3. Запуск: быстрый старт

### 3.1. Dry run (без реальных запросов в LLM)
Самый безопасный тест, чтобы проверить, что пайплайн работает, файлы находятся и результаты сохраняются:

```bash
ai-review ./src --dry-run --include "*.py" -r
```

Что произойдёт:
- ревью будет генерироваться встроенным провайдером `mock` (без сети),
- результаты появятся в `./reviews`,
- создастся `./reviews/summary.md` и `./reviews/.review_hashes.json`.

### 3.2. Запуск по профилю из `.codingutils.yaml`
```bash
ai-review . --profile oos-20b-local
```

---

## 4. LM Studio + локальная модель oos-20B (полный пример)

### 4.1. Подготовь LM Studio
1) Загрузи модель **oos-20B** в LM Studio.
2) Запусти локальный сервер в режиме **OpenAI-compatible**.
   Обычно endpoint: `http://localhost:1234/v1`

Проверка (пример):
```bash
curl http://localhost:1234/v1/models
```

### 4.2. Пример `.codingutils.yaml` (профиль для oos-20B)
Создай в корне проекта файл `.codingutils.yaml`:

```yaml
version: 2

globals:
  output:
    directory: "./reviews"
    formatter: "markdown"
    versioning: "incremental"

profiles:
  oos-20b-local:
    # Список паттернов (предпочтительный способ)
    include_patterns:
      - "*.py"
      - "*.ts"
      - "*.tsx"

    recursive: true
    use_gitignore: true

    exclude_dirs: ["venv", ".venv", ".git", "__pycache__", "node_modules", "dist", "build"]

    processing:
      method: "functions"        # functions | classes | files
      skip_unchanged: true
      force: false
      max_workers: 2
      max_input_tokens: 3000
      max_memory_mb: 500
      token_method: "approximate"  # approximate | tiktoken
      continue_on_error: true

    llm:
      provider: "lmstudio"       # mock | lmstudio | openai
      api_base: "http://localhost:1234/v1"
      model: "oos-20B"
      temperature: 0.2
      max_output_tokens: 512
      context_window: 8192
      timeout: 60
      max_retries: 3

    prompt:
      system_prompt: "prompts/system.md"
      user_prompt: "prompts/review.md"
      include_context: false
      context_files: []
      placeholders:
        project_name: "MyProject"

plugins:
  auto_discover: true
  plugin_dirs:
    - "./.codingutils/plugins"
    - "~/.codingutils/plugins"
```

### 4.3. Промты (минимально)
Создай папку `prompts/` рядом с `.codingutils.yaml`:

`prompts/system.md`
```md
You are a senior software engineer performing a code review.
Be concise, specific, and actionable.
```

`prompts/review.md`
```md
Review the following {{element_type}} "{{element_name}}" from {{filepath}}.

Rules:
- Focus on correctness, readability, maintainability.
- Provide concrete fixes. If you suggest code, show a short snippet.
- If you see security concerns, highlight them explicitly.

CODE:
{{code}}
```

### 4.4. Запуск
```bash
ai-review . --profile oos-20b-local
```

---

## 5. CLI: полный справочник

Команда (в текущей схеме entry_points):
### `ai-review`

#### 5.1. Входные директории
```bash
ai-review [DIRECTORIES...]
```
Если директории не указаны — по умолчанию `"."`.

#### 5.2. Фильтрация файлов

- `-r, --recursive` — рекурсивный обход
- `--max-depth N` — максимальная глубина
- `-p, --pattern PATTERN` — одиночный include_pattern (наследие)
- `--include PATTERN` — можно указывать много раз (аналог YAML `include_patterns`)
- `-ed, --exclude-dir DIRNAME` — повторяемое исключение директорий по имени
- `-en, --exclude-name MASK` — исключение по имени (fnmatch)
- `-ep, --exclude-pattern MASK` — исключение по имени или относительному пути
- `-ig, --use-gitignore` — применять `.gitignore` (автопоиск)
- `--gitignore FILE` — явно указать `.gitignore`

Пример:
```bash
ai-review . -r --include "*.py" --include "*.ts" -ed venv -ed node_modules -ig
```

#### 5.3. Конфиг / профили
- `--config FILE` — путь к YAML
- `--profile NAME` — имя профиля из `profiles:`

#### 5.4. Метод ревью
- `--method {functions|classes|files|multi_file}`
`multi_file` пока не реализован как отдельный режим (enum есть, полноценной логики склейки нескольких файлов — нет).

#### 5.5. LLM настройки
- `--llm-provider NAME` — `mock|lmstudio|openai|...`
- `--model NAME`
- `--api-base URL`
- `--api-key KEY`
- `--temperature FLOAT`
- `--max-output-tokens INT`
- `--context-window INT`

#### 5.6. Промты / контекст
- `--system-prompt FILE_OR_TEXT`
- `--user-prompt FILE` (в текущей версии ожидается существующий файл)
- `--include-context` — разрешить `{{context}}` (подхват всего файла) если плейсхолдер реально есть в шаблоне
- `--context-file GLOB` — можно несколько раз, используется если в шаблоне есть `{{context_files}}`

#### 5.7. Output
- `--output-dir DIR`
- `--formatter NAME`

#### 5.8. Производительность
- `--max-workers N` — параллельные запросы в LLM
- `--max-input-tokens N` — лимит входных токенов (оценка)
- `--batch-size N` — задел, пока батчинг не используется (MVP)

#### 5.9. Режимы
- `--dry-run` — принудительно включает провайдер `mock`
- `--force` — ревью делать даже если элемент не изменился
- `--skip-unchanged` / `--no-skip-unchanged`
- `--clean` — удалить output_dir и выйти
- `--verbose` — подробные логи

---

## 6. Конфигурация `.codingutils.yaml` (полный разбор)

### 6.1. Где лежит конфиг и как ищется
Если не указан `--config`, инструмент ищет:
- `.codingutils.yaml` или `.codingutils.yml`
- начиная с текущей директории вверх до корня.

### 6.2. Приоритет настроек (важно)
1) CLI overrides
2) Профиль `profiles.<name>`
3) `globals`

### 6.3. Неизвестные ключи
Если в YAML ключ неизвестен — он **игнорируется**, но пишется warning в лог.

### 6.4. Секции YAML
Поддерживаются (логически):
- `globals:`
- `profiles:`
- `plugins:` (может быть на верхнем уровне; он подмешивается как глобальный defaults)

#### 6.4.1. Профили и `extends`
Можно наследовать настройки:

```yaml
profiles:
  base:
    include_patterns: ["*.py"]
    llm:
      provider: "lmstudio"
      model: "oos-20B"

  security:
    extends: base
    processing:
      method: "files"
      skip_unchanged: false
    llm:
      temperature: 0.1
```

---

## 7. Фильтрация файлов: include_patterns, include_pattern и brace-expansion

### 7.1. `include_patterns` (список) — рекомендуемый способ
```yaml
include_patterns:
  - "*.py"
  - "*.pyi"
  - "*.ts"
```

### 7.2. `include_pattern` (одна строка) — наследие
```yaml
include_pattern: "*.py"
```

### 7.3. Brace-expansion
Поддерживается форма:
- `*.{py,pyi,pyw}` → разворачивается в список паттернов

Рекомендуется использовать либо список, либо brace.

---

## 8. Методы ревью: functions / classes / files

### 8.1. `functions`
- Python: функции + методы (`Class.method`)
- JS/TS: `function foo()`, `const bar = () =>`, методы класса `User.getName`

### 8.2. `classes`
- Python: `class X: ...` как единый элемент
- JS/TS: `class X { ... }`

### 8.3. `files`
Файл целиком как один элемент.

---

## 9. Парсеры (встроенные)

### 9.1. PythonParser (`provider=python`)
- через `ast`
- поддерживает `.py`, `.pyw`, `.pyi`

### 9.2. JavaScriptParser (`provider=javascript`)
- регулярки + простая балансировка `{}` (MVP)
- поддерживает `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`

Ограничения (нормально для MVP):
- сложные случаи (regex literals, template strings с `${...}` внутри блоков) могут ломать “идеальную” нарезку.

### 9.3. GenericParser
fallback для всего остального. Сейчас он возвращает whole-file.

---

## 10. LLM провайдеры (встроенные)

### 10.1. `mock`
- не делает сетевых запросов
- полезен для тестов и проверки пайплайна

### 10.2. `lmstudio`
- OpenAI-compatible endpoint
- по умолчанию ожидает `http://localhost:1234/v1` (если не указать `api_base`)

### 10.3. `openai`
- OpenAI API
- требует ключ (через `--api-key` или `OPENAI_API_KEY`)
- endpoint `https://api.openai.com/v1` (по умолчанию)

---

## 11. Prompt Engineering (как работают промты)

### 11.1. System prompt и user prompt
- `system_prompt` — опционально
- `user_prompt` — обязателен (файл)

### 11.2. Плейсхолдеры (переменные в шаблоне)
В `user_prompt` (и system, если хочешь) можно использовать:

- `{{code}}` — содержимое элемента (функция/класс/файл)
- `{{filename}}` — имя файла
- `{{filepath}}` — относительный путь (от cwd)
- `{{language}}` — язык (из парсера/расширения)
- `{{element_name}}` — имя элемента (например `C.m`)
- `{{element_type}}` — `function|method|class|file`
- `{{timestamp}}` — ISO timestamp

Дополнительно:
- `{{context}}` — полный файл, если `include_context: true` **и** этот плейсхолдер присутствует в шаблоне
- `{{context_files}}` — содержимое дополнительных файлов (glob patterns), если плейсхолдер присутствует

### 11.3. placeholders из конфига
Можно задать дополнительные переменные:
```yaml
prompt:
  placeholders:
    project_name: "MyProject"
    review_style: "strict"
```
И использовать в шаблоне: `{{project_name}}`.

---

## 12. Output: структура результатов

По умолчанию: `./reviews`

Содержимое:
- `reviews/summary.md` — сводка
- `reviews/.review_hashes.json` — хеши элементов (для skip_unchanged)
- `reviews/errors.log` — ошибки (если были)
- `reviews/<relative/path/to/file>/review_<N>_<element>.md` — ревью
- `reviews/<relative/path/to/file>/review_<N>_<element>.bak` — бэкап кода элемента

### 12.1. Версионирование
Сейчас реализован **incremental**:
- для одинакового `element_name` в одной директории будут `review_1_...`, `review_2_...`, и т.д.

---

## 13. Skip unchanged / Force (инкрементальный режим)

### 13.1. Как работает
Для каждого элемента формируется `element_id = "<file_path>:<element_name>"`.
В `.review_hashes.json` хранится SHA256 от `element.content`.

- если `skip_unchanged: true` и хеш совпадает → элемент пропускается
- если `--force` или `force: true` → ревью делается всегда

### 13.2. Пример “быстрой проверки только изменившегося”
```yaml
profiles:
  changed-only:
    extends: oos-20b-local
    processing:
      skip_unchanged: true
      max_workers: 4
```

---

## 14. Пользовательские плагины (полная инструкция)

### 14.1. Где размещать
Укажи директории в YAML:

```yaml
plugins:
  auto_discover: true
  plugin_dirs:
    - "./.codingutils/plugins"
    - "~/.codingutils/plugins"
```

### 14.2. Формат плагина
Это обычный `.py` файл, который должен содержать функцию:

```python
def register(registry):
    registry.register_formatter(...)
    registry.register_parser(...)
    registry.register_llm_provider(...)
```

### 14.3. Пример: кастомный форматер `plain`
`./.codingutils/plugins/plain_formatter.py`
```python
from codingutils.ai_review.plugins.base import BaseFormatter

class PlainFormatter(BaseFormatter):
    name = "plain"

    @classmethod
    def get_supported_config_keys(cls):
        return []

    def format_review(self, review) -> str:
        return "PLAIN:" + review.review_text

    def format_summary(self, summary) -> str:
        return "PLAIN_SUMMARY"

def register(registry):
    registry.register_formatter(PlainFormatter)
```

И в YAML:
```yaml
globals:
  output:
    formatter: "plain"
```

---

## 15. Рекомендации по качеству и производительности

### 15.1. Подбор метода ревью
- Большие проекты: начни с `functions` (меньше токенов, быстрее)
- Security / архитектура: `files` + контекстные файлы

### 15.2. Токены и лимиты
- `processing.max_input_tokens` — ограничивает вход (оценка)
- `llm.max_output_tokens` — ограничивает ответ
- если задан `llm.context_window`, проверяется:
  `max_input_tokens + max_output_tokens <= context_window`

### 15.3. Параллелизм
- `max_workers` увеличивает скорость, но:
  - локальная модель может начать “тормозить”
  - облачные API могут упереться в rate limit (в MVP это не полностью реализовано)

---

## 16. Безопасность

- Не добавляй `.env` / секреты в `context_files`, если не уверен.
- Для OpenAI ключ лучше хранить в env:
  ```bash
  export OPENAI_API_KEY="..."
  ```
- `include_context` может отправлять в LLM полный файл, включая случайные секреты внутри кода/комментариев.

---

## 17. Troubleshooting (частые проблемы)

### 17.1. `Formatter 'X' not found`
Причины:
- не зарегистрирован встроенный/пользовательский форматер
- plugin discovery не сработал (неверный путь, синтаксическая ошибка в плагине)

Проверка:
- включи `--verbose` и смотри логи
- убедись, что в плагине есть `register(registry)` и нет ошибок импорта

### 17.2. `User prompt not found`
`prompt.user_prompt` должен быть существующим файлом. Проверь относительный путь:
- относительные пути резолвятся относительно директории конфига `.codingutils.yaml`

### 17.3. Не находятся файлы
Проверь:
- `-r` / `recursive: true`
- `include_patterns` действительно совпадают (fnmatch)
- `.gitignore` не отрезает нужные файлы

### 17.4. LM Studio не отвечает
Проверь:
- `api_base` (обычно `http://localhost:1234/v1`)
- что endpoint `/v1/chat/completions` доступен
- что модель загружена в LM Studio

---

## 18. Ограничения текущей версии (честно)
- `multi_file` как режим пока не реализован (нет склейки нескольких файлов в один контекст-элемент).
- rate limiting / retries / backoff пока минимальны.
- JS/TS парсер эвристический (MVP).

---

# Приложение A: готовые конфиги

## A1) Минимальный локальный dry-run (без YAML)
```bash
ai-review . --dry-run --include "*.py" -r --user-prompt prompts/review.md
```

## A2) Профиль “только Python”
```yaml
profiles:
  python:
    include_patterns: ["*.py", "*.pyi"]
    recursive: true
    processing:
      method: "functions"
    llm:
      provider: "lmstudio"
      model: "oos-20B"
    prompt:
      user_prompt: "prompts/review.md"
```

## A3) Профиль “security files”
```yaml
profiles:
  security:
    include_patterns: ["*.py", "*.js", "*.ts", "*.yaml", "*.yml"]
    processing:
      method: "files"
      skip_unchanged: false
    llm:
      provider: "lmstudio"
      model: "oos-20B"
      temperature: 0.1
      max_output_tokens: 800
    prompt:
      user_prompt: "prompts/security.md"
      include_context: true
      context_files: [".env*", "config/*.yml", "config/*.yaml"]
```
