# Полное руководство пользователя: `tree-generator`

`tree-generator` (модуль `codingutils.tree_generater`) — кроссплатформенная утилита для построения дерева проекта с умной фильтрацией и выводом в нескольких форматах.
Стиль флагов и подход к фильтрации **согласованы с `comment_extractor`**.

---

## Содержание

1. [Что это и для чего](#что-это-и-для-чего)
2. [Установка и запуск](#установка-и-запуск)
3. [Быстрый старт](#быстрый-старт)
4. [Синтаксис команды](#синтаксис-команды)
5. [Вывод и форматы (text/json/xml/markdown)](#вывод-и-форматы-textjsonxmlmarkdown)
6. [Поиск файлов: directories, recursive, max-depth, pattern](#поиск-файлов-directories-recursive-max-depth-pattern)
7. [Фильтрация и исключения](#фильтрация-и-исключения)
8. [Поддержка .gitignore](#поддержка-gitignore)
9. [Скрытые файлы и директории](#скрытые-файлы-и-директории)
10. [Показ метаданных: size, permissions, last-modified, file-type](#показ-метаданных-size-permissions-last-modified-file-type)
11. [Сортировка](#сортировка)
12. [Стиль отступов и ограничение ширины](#стиль-отступов-и-ограничение-ширины)
13. [Статистика и summary](#статистика-и-summary)
14. [Логи (stderr) и лог-файл](#логи-stderr-и-лог-файл)
15. [Готовые сценарии (рецепты)](#готовые-сценарии-рецепты)
16. [Ограничения и важные нюансы](#ограничения-и-важные-нюансы)
17. [Частые проблемы](#частые-проблемы)

---

## Что это и для чего

`tree-generator` строит дерево файлов/директорий и помогает:

- быстро понять структуру репозитория;
- подготовить “снимок структуры” для документации/ревью;
- сравнивать разные версии проекта (несколько корней);
- смотреть состав проекта с учётом `.gitignore` и собственных фильтров;
- получать статистику (количество файлов/директорий, общий размер, исключенные элементы).

---

## Установка и запуск

### Требования
- Python 3.10+

### Запуск

Дальше в документации я использую имя `tree-generator` как “команду”.

---

## Быстрый старт

### 1) Дерево текущей папки (не рекурсивно)
```bash
tree-generator .
```

### 2) Рекурсивно по проекту
```bash
tree-generator . -r
```

### 3) Только Python файлы
```bash
tree-generator . -r -p "*.py"
```

### 4) С учетом `.gitignore`
```bash
tree-generator . -r -ig
```

### 5) JSON для дальнейшей обработки
```bash
tree-generator . -r --format json --output structure.json
```

---

## Синтаксис команды

```bash
tree-generator [DIRECTORY ...] [OPTIONS]
```

- `DIRECTORY ...` — один или несколько путей. По умолчанию: `.`
  Пример:
  ```bash
  tree-generator src tests
  ```

---

## Вывод и форматы (text/json/xml/markdown)

### `--format` (`-f`)
Доступные значения:
- `text` (по умолчанию) — ASCII дерево
- `json` — валидный JSON (один объект)
- `xml` — валидный XML документ
- `markdown` — Markdown‑список

Примеры:

#### Text
```bash
tree-generator . -r --format text
```

#### JSON
```bash
tree-generator . -r --format json
```

#### XML
```bash
tree-generator . -r --format xml
```

#### Markdown
```bash
tree-generator . -r --format markdown
```

### `--output` (`-o`)
Если указан, результат пишется в файл:

```bash
tree-generator . -r -o tree.txt
tree-generator . -r --format json -o tree.json
```

Если `--output` не указан — вывод идёт в `stdout`.

---

## Поиск файлов: directories, recursive, max-depth, pattern

### `-r / --recursive`
Включает рекурсивный обход.

```bash
tree-generator . -r
```

Если флаг не указан — отображается только верхний уровень (1 директория).

### `--max-depth`
Ограничение глубины рекурсии (работает совместно с `-r`):

```bash
tree-generator . -r --max-depth 2
```

Правило:
- `0` — только корневая директория
- `1` — корень + его прямые элементы
- `2` — ещё на один уровень глубже, и т.д.

### `-p / --pattern`
Паттерн включения для **файлов** (glob по имени файла).
Директории при этом не исчезают сами по себе — они будут показаны, если не исключены фильтрами.

```bash
tree-generator . -r -p "*.py"
tree-generator . -r -p "test_*.py"
```

Важно: в текущей версии `-p` один. Для нескольких расширений — несколько запусков:

```bash
tree-generator src -r -p "*.py" -o py_tree.txt
tree-generator src -r -p "*.js" -o js_tree.txt
```

---

## Фильтрация и исключения

Есть три механизма исключения (как в `comment_extractor`):

### `-ed / --exclude-dir NAME`
Исключить директории по имени сегмента пути (любой уровень):

```bash
tree-generator . -r -ed venv -ed node_modules -ed __pycache__
```

### `-en / --exclude-name GLOB`
Исключить по basename (имя файла или директории), glob:

```bash
tree-generator . -r -en "*.log" -en "*.pyc"
```

### `-ep / --exclude-pattern GLOB`
Исключить по “пути относительно корня” или basename.

Примеры:
```bash
tree-generator . -r -ep "docs/*"
tree-generator . -r -ep "**/migrations/*"
tree-generator . -r -ep "src/*test*"
```

#### Важная особенность
Если вы указываете паттерн вида `docs/*`, то утилита исключит:
- и содержимое `docs/*`,
- и саму директорию `docs/` (чтобы “исключить поддерево” работало ожидаемо).

---

## Поддержка gitignore

### Включить авто‑поиск `.gitignore`
```bash
tree-generator . -r -ig
# или
tree-generator . -r --use-gitignore
```

### Указать конкретный `.gitignore`
```bash
tree-generator . -r -gi /path/to/.gitignore
```

### Отключить `.gitignore`
```bash
tree-generator . -r --no-gitignore
```

---

## Скрытые файлы и директории

По умолчанию скрытые элементы (начинающиеся с `.`) не показываются.

### Показать скрытые
```bash
tree-generator . -r --show-hidden
```

Скрытыми считаются любые сегменты пути под корнем:
- `.git/`, `.idea/`, `.env`, `.github/workflows/...` и т.п.

---

## Показ метаданных: size, permissions, last-modified, file-type

Метаданные включаются флагами и добавляются в круглых скобках после имени.

### `--show-size`
Показ размера файлов:

```bash
tree-generator . -r --show-size
```

Размер выводится в удобном формате (B/KB/MB/…).

### `--show-permissions`
Показ прав доступа (best-effort, зависит от OS/FS):

```bash
tree-generator . -r --show-permissions
```

### `--show-last-modified`
Показ даты изменения:

```bash
tree-generator . -r --show-last-modified
```

### `--show-file-type`
Показ типа файла (text/binary/unknown).

```bash
tree-generator . -r --show-file-type
```

Важно:
- Этот режим может быть медленнее, потому что тип может определяться по содержимому (не только по расширению).

---

## Сортировка

### `--sort-by`
Варианты:
- `name` (по умолчанию)
- `size`
- `modified`
- `type`

```bash
tree-generator . -r --sort-by size
```

### `--sort-reverse`
Разворот порядка:

```bash
tree-generator . -r --sort-by size --sort-reverse
```

Примечание:
- директории всегда идут перед файлами (в рамках сортировки ключей), чтобы дерево было читаемым.

---

## Стиль отступов и ограничение ширины

### `--indent-style`
Варианты:
- `tree` (ASCII дерево): `|--` и ``--`
- `spaces` — отступы пробелами
- `dashes` — отступы дефисами

Примеры:

```bash
tree-generator . -r --indent-style tree
tree-generator . -r --indent-style spaces --indent-size 2
tree-generator . -r --indent-style dashes --indent-size 3
```

### `--indent-size`
Используется только для `spaces` и `dashes`.

### `--max-width`
Обрезает строки до указанной ширины, добавляя `...`:

```bash
tree-generator . -r --max-width 100
```

---

## Статистика и summary

По умолчанию выводятся:

- `STATISTICS`
- `SUMMARY`

### Отключить статистику
```bash
tree-generator . -r --no-statistics
```

### Отключить summary
```bash
tree-generator . -r --no-summary
```

Поля статистики:
- Directories — число директорий в выводе
- Files — число файлов в выводе
- Total Size — суммарный размер файлов (по показанным файлам)
- Excluded Items — сколько элементов отфильтровано
- Processing Time — время генерации

---

## Логи (stderr) и лог-файл

### `--log-file`
Логи пишутся в `stderr`. Если нужно сохранить лог отдельно:

```bash
tree-generator . -r --log-file run.log
```

### `-v / --verbose`
Больше деталей в логах:

```bash
tree-generator . -r -v --log-file debug.log
```

Важно:
- дерево/JSON/XML/Markdown идут в `stdout` или `--output`
- логи всегда отдельно (stderr / log-file), поэтому файлы `--output` “чистые”

---

## Готовые сценарии (рецепты)

### 1) Структура проекта “как в git”
```bash
tree-generator . -r -ig
```

### 2) Быстрый обзор (2 уровня)
```bash
tree-generator . -r -ig --max-depth 2
```

### 3) Только исходники Python
```bash
tree-generator . -r -ig -p "*.py" -ed venv -ed __pycache__
```

### 4) Экспорт для документации (Markdown)
```bash
tree-generator . -r -ig --format markdown -o STRUCTURE.md
```

### 5) Экспорт для скриптов/аналитики (JSON)
```bash
tree-generator . -r -ig --format json -o structure.json
jq '.statistics' structure.json
```

### 6) Сравнить два каталога (одним запуском)
```bash
tree-generator /path/to/v1 /path/to/v2 -r --max-depth 3
```

---

## Ограничения и важные нюансы

1) `--pattern` применяется только к файлам. Директории могут остаться “пустыми” в выводе, если в них нет подходящих файлов (если вы не включили `--exclude-empty-dirs`).

2) `--exclude-empty-dirs` удаляет из дерева директории, которые стали пустыми **после применения фильтров**.

3) На некоторых файловых системах/в контейнерах права (`--show-permissions`) могут быть недоступны или нестабильны — утилита работает best‑effort.

4) При включении `--show-file-type` инструмент может работать заметно медленнее на больших репозиториях.

---

## Частые проблемы

### “Почему нет рекурсии?”
Потому что рекурсия включается флагом `-r`:

```bash
tree-generator . -r
```

### “Почему не исключилась директория `docs/`, если я указал `-ep docs/*`?”
В этой версии **должна исключиться** и директория, и содержимое. Если не исключилась:
- проверьте, что корень запуска — это тот каталог, относительно которого вы хотите матчить (`docs/*` относится к корню запуска)
- попробуйте `-ep "docs*"` если структура другая

### “Файл `--output` содержит мусор/логи”
Так быть не должно: логи идут в stderr или `--log-file`. Если видите “мусор” — скорее всего вы перенаправили stderr в stdout (`2>&1`).

---

## Справка по флагам (коротко)

- Вход:
  - `DIRECTORY ...`
  - `-r/--recursive`
  - `--max-depth`
  - `-p/--pattern`

- Исключения:
  - `-ed/--exclude-dir`
  - `-en/--exclude-name`
  - `-ep/--exclude-pattern`
  - `--exclude-empty-dirs`

- Gitignore:
  - `-ig/--use-gitignore`
  - `-gi/--gitignore`
  - `--no-gitignore`

- Метаданные:
  - `--show-size`
  - `--show-permissions`
  - `--show-last-modified`
  - `--show-file-type`
  - `--show-hidden`

- Сортировка/стиль:
  - `--sort-by`, `--sort-reverse`
  - `--indent-style`, `--indent-size`
  - `--max-width`

- Вывод/логи:
  - `-f/--format`
  - `-o/--output`
  - `--log-file`
  - `-v/--verbose`
