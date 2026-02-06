# Полное руководство пользователя: `file-merger`

`file-merger` (модуль `codingutils/merger.py`) — CLI‑утилита для объединения содержимого многих файлов в один выходной файл. Поддерживает фильтрацию (включая `.gitignore`), лимиты размеров, постобработку строк, безопасную запись результата и управление бэкапами выходного файла.

---

## Содержание

1. [Введение](#введение)
2. [Основные возможности](#основные-возможности)
3. [Установка и запуск](#установка-и-запуск)
4. [Быстрый старт](#быстрый-старт)
5. [Синтаксис команды](#синтаксис-команды)
6. [Выбор файлов: directories, recursive, max-depth, pattern, -d/-dr](#выбор-файлов-directories-recursive-max-depth-pattern--ddr)
7. [Фильтрация и исключения](#фильтрация-и-исключения)
8. [Поддержка .gitignore](#поддержка-gitignore)
9. [Режим preview](#режим-preview)
10. [Формат выходного файла](#формат-выходного-файла)
11. [Заголовки файлов и `--compact-file-headers`](#заголовки-файлов-и---compact-file-headers)
12. [Постобработка содержимого (line numbers, remove empty, dedupe)](#постобработка-содержимого-line-numbers-remove-empty-dedupe)
13. [Ограничения по размеру (max-file-size, max-total-size)](#ограничения-по-размеру-max-file-size-max-total-size)
14. [Jupyter Notebook (`.ipynb`)](#jupyter-notebook-ipynb)
15. [Бинарные файлы](#бинарные-файлы)
16. [Бэкапы выходного файла](#бэкапы-выходного-файла)
17. [Логи и отладка (в т.ч. split streams)](#логи-и-отладка-в-тч-split-streams)
18. [Примеры (рецепты)](#примеры-рецепты)
19. [Частые проблемы](#частые-проблемы)

---

## Введение

`file-merger` предназначен для задач вида:

- собрать исходники проекта в один файл (для анализа, ревью, LLM/архива);
- собрать конфиги/логи в один документ;
- собрать часть репозитория по шаблону (например `*.py`, `*.md`);
- получить “снимок” файлов с учётом `.gitignore` и исключений;
- собрать контент из Jupyter Notebook (`.ipynb`) в читабельном виде (markdown+code).

---

## Основные возможности

### Поиск и фильтрация
- несколько директорий одновременно (позиционные аргументы)
- **несколько паттернов включения** (`-p "*.py" "*.txt"` или `-p "*.py *.txt"`)
- рекурсивный обход по умолчанию (`-r`)
- **пер‑директория рекурсия**: `-dr dir1 -d dir2` (dir1 рекурсивно, dir2 нет)
- исключения: директории/имена/пути (`-ed/-en/-ep`)
- поддержка `.gitignore` (`-ig` / `-gi` / `--no-gitignore`)

### Формирование результата
- глобальная мета‑шапка (список файлов, настройки)
- заголовки перед каждым файлом
- **compact mode** для заголовков: `--compact-file-headers`
- постобработка текста: номера строк, удаление пустых строк, дедупликация строк

### Безопасная запись
- запись в `output.tmp` и атомарная замена `--output`
- опциональные бэкапы прежнего `--output`:
  - `--keep-backups`
  - `--backup-dir`
  - `--overwrite-backups`

---

## Установка и запуск

### Требования
- Python 3.10+

### Запуск
В зависимости от упаковки:

```bash
file-merger --help
# или
python -m codingutils.merger --help
```

В этом документе используется команда `file-merger`.

---

## Быстрый старт

### 1) Собрать все `.py` рекурсивно из `src/` в один файл
```bash
file-merger src -r -p "*.py" -o merged.py.txt
```

### 2) Несколько паттернов (py + txt)
```bash
file-merger src -r -p "*.py" "*.txt" -o merged.txt
# или одной строкой:
file-merger src -r -p "*.py *.txt" -o merged.txt
```

### 3) Разная рекурсия для разных директорий
```bash
file-merger -dr src -d docs -p "*.py" "*.md" -o merged.txt
# src будет рекурсивно, docs только верхний уровень
```

### 4) Предпросмотр перед мержем
```bash
file-merger src tests -r -p "*.py" --preview
```

### 5) Учесть `.gitignore`
```bash
file-merger . -r -ig -p "*" -o merged.txt
```

### 6) Режим для GUI/обёрток: разделить stdout/stderr
```bash
file-merger . -r -p "*.py" -o merged.txt --split-streams
# stdout: прогресс + краткий OK summary
# stderr: логи/ошибки
```

---

## Синтаксис команды

```bash
file-merger [DIRECTORY ...] [OPTIONS]
```

- `DIRECTORY ...` — директории (0..N). Если не указано — `.`.
- Выходной файл задаётся `-o/--output`.
- Если используете `-d/-dr`, вы можете смешивать их с позиционными директориями.

---

## Выбор файлов: directories, recursive, max-depth, pattern, -d/-dr

### `DIRECTORY ...`
Одна или несколько директорий:

```bash
file-merger src tests docs -r -p "*.md" -o docs.txt
```

### `-r / --recursive`
Включить рекурсивный обход “по умолчанию”:

```bash
file-merger . -r -p "*.txt" -o merged.txt
```

### `-d / --dir` и `-dr / --dir-recursive` (пер‑директория рекурсия)
Позволяет задать режим обхода **для конкретной директории**:

- `-dr DIR` — DIR обходить рекурсивно
- `-d DIR` — DIR обходить НЕрекурсивно (только 1 уровень)

Пример:
```bash
file-merger -dr dir1 -d dir2 -p "*.py" -o merged.txt
```

Поведение:
- если заданы `-d/-dr`, то для этих директорий режим берётся из этих флагов;
- для остальных директорий действует “дефолт” из `-r` (или нерекурсивно, если `-r` не задан).

### `--max-depth`
Ограничить глубину обхода (актуально для рекурсивных обходов):

```bash
file-merger . -r --max-depth 3 -p "*.py" -o merged.txt
```

### `-p / --pattern` (несколько паттернов)
Паттерны включения файлов (glob по basename). Поддерживается несколько:

```bash
file-merger . -r -p "*.py" "*.txt" -o merged.txt
file-merger . -r -p "*.py *.txt *.*" -o merged.txt
```

Семантика:
- файл включается, если его имя совпадает **хотя бы с одним** паттерном (логика OR).
- паттерны применяются к basename (имени файла), не к полному пути.

---

## Фильтрация и исключения

### `-ed / --exclude-dir NAME`
Исключить директорию по имени сегмента пути:

```bash
file-merger . -r -ed venv -ed node_modules -ed __pycache__
```

### `-en / --exclude-name GLOB`
Исключить по имени файла (glob по basename):

```bash
file-merger . -r -en "*.log" -en "*.pyc"
```

### `-ep / --exclude-pattern GLOB`
Исключить по относительному пути или basename:

```bash
file-merger . -r -ep "docs/*" -ep "**/migrations/*"
```

---

## Поддержка gitignore

### Авто‑поиск `.gitignore`
```bash
file-merger . -r -ig -p "*" -o merged.txt
```

### Указать конкретный `.gitignore`
```bash
file-merger . -r -gi /path/to/.gitignore -p "*" -o merged.txt
```

### Отключить gitignore
```bash
file-merger . -r --no-gitignore -p "*" -o merged.txt
```

---

## Режим preview

### `--preview`
Показывает отчёт:
- сколько файлов найдено
- сколько выбрано (после лимитов)
- какие будут пропущены и почему
- список выбранных файлов (первые N)

Пример:
```bash
file-merger . -r -p "*.py" --max-total-size 10MB --preview
```

Preview **не пишет выходной файл** и не делает бэкапы.

---

## Формат выходного файла

Файл `--output` формируется последовательно:

1) (опционально) глобальная мета‑шапка `MERGED FILE REPORT`
2) для каждого файла:
   - (опционально) заголовок файла
   - содержимое файла (после обработки)
   - пустая строка-разделитель
3) (опционально) footer `MERGE COMPLETE`

### Управление мета‑шапкой и footer
- `--no-metadata` — отключает мета‑шапку и footer.

---

## Заголовки файлов и `--compact-file-headers`

По умолчанию при `include_headers=True` каждый файл получает блок заголовка примерно такого вида:

```
----------------------------------------
FILE 3/10: src/main.py
Size: 12.34 KB | Encoding: utf-8
Modified: 2026-01-30 12:34:56
========================================

<content...>
```

### `--compact-file-headers`
Делает заголовок короче:
- вместо `FILE X/Y: <relative_path>` будет `FILE X/Y: <filename>`
- строка `Modified:` не выводится

Пример:
```bash
file-merger . -r -p "*.py" -o merged.txt --compact-file-headers
```

---

## Постобработка содержимого (line numbers, remove empty, dedupe)

Все опции применяются **к каждому файлу отдельно** (per-file).

### `--add-line-numbers`
```bash
file-merger src -r -p "*.py" --add-line-numbers -o merged.txt
```

### `--remove-empty-lines`
```bash
file-merger . -r -p "*.txt" --remove-empty-lines -o merged.txt
```

### `--deduplicate`
Удаляет повторяющиеся строки **внутри одного файла**:

```bash
file-merger . -r -p "*.txt" --deduplicate -o merged.txt
```

---

## Ограничения по размеру (max-file-size, max-total-size)

### `--max-file-size`
Если файл больше лимита — он не мержится. В результат вставляется строка:

```
[FILE SKIPPED: exceeds max_file_size ...]
```

Пример:
```bash
file-merger . -r -p "*" --max-file-size 2MB -o merged.txt
```

### `--max-total-size`
Ограничивает суммарный размер выбранных файлов.

Пример:
```bash
file-merger . -r -p "*.py" --max-total-size 20MB -o merged.txt
```

---

## Jupyter Notebook (`.ipynb`)

Если среди входных файлов есть `.ipynb`, `file-merger` обрабатывает их специальным образом:

- notebook **не считается бинарным**
- извлекается содержимое только из `cell_type in ("markdown", "code")`
- `raw` ячейки игнорируются
- outputs/результаты выполнения кода **не включаются**
- в merged-output добавляется заголовок вида:
  - `[NOTEBOOK: <relative_path>]`
- добавляется строка вида:
  - `X/Y cells extracted`
- при некорректном JSON добавляется текст с `ERROR`/`Invalid JSON`

---

## Бинарные файлы

По умолчанию бинарные файлы не мержатся как байты, вместо них вставляется плейсхолдер:

```
[BINARY FILE: something.exe]
Size: 1.23 MB
SHA256: ...
Binary content is not merged.
```

### Управление бинарным поведением
- `--no-binary-placeholders` — бинарники пропускаются с коротким маркером `[BINARY FILE SKIPPED]`
- `--no-binary-hash` — не считать SHA256

---

## Бэкапы выходного файла

Бэкапы касаются **только** файла `--output`, если он уже существует и вы делаете реальный merge (не preview).

### `--keep-backups`
```bash
file-merger . -r -p "*.py" -o merged.txt --keep-backups
```

### `--backup-dir PATH`
```bash
file-merger . -r -p "*.py" -o merged.txt --backup-dir .backups
```

### `--overwrite-backups`
```bash
file-merger . -r -p "*.py" -o merged.txt --backup-dir .backups --overwrite-backups
```

---

## Логи и отладка (в т.ч. split streams)

### `--log-file`
Записать логи в файл:

```bash
file-merger . -r -p "*.py" -o merged.txt --log-file run.log
```

### `-v / --verbose`
Включить debug-логи:

```bash
file-merger . -r -p "*.py" -o merged.txt -v --log-file debug.log
```

### `--split-streams` (для GUI/обёрток)
Флаг для удобного разделения выводов по потокам:

- **stdout**: прогресс + краткое итоговое сообщение (OK summary)
- **stderr**: логи/ошибки/предупреждения

Пример:
```bash
file-merger . -r -p "*.py" -o merged.txt --split-streams
```

Важно:
- содержимое merged всегда пишется в `--output`, не в stdout.

---

## Примеры (рецепты)

### 1) Снимок проекта (как git)
```bash
file-merger . -r -ig -p "*" \
  -ed venv -ed node_modules -ed __pycache__ \
  -en "*.pyc" -en "*.log" \
  -o snapshot.txt --keep-backups
```

### 2) Только исходники без тестов
```bash
file-merger . -r -ig -p "*.py" \
  -ep "tests/*" -ep "**/tests/*" \
  -o src_only.txt
```

### 3) Markdown + Python (мультипаттерн)
```bash
file-merger . -r -p "*.md" "*.py" -o docs_and_code.txt
```

### 4) Разная рекурсия для разных частей репозитория
```bash
file-merger -dr src -d docs -p "*.py" "*.md" -o merged.txt
```

### 5) Компактный merge для LLM
```bash
file-merger . -r -ig -p "*.py" \
  --no-metadata \
  --compact-file-headers \
  --remove-empty-lines \
  -o code_for_llm.txt
```

---

## Частые проблемы

### “No files found to merge”
Проверьте:
- вы указали `-r` если хотите рекурсивно
- паттерн(ы) `-p` не слишком узкие
- исключения `-ed/-en/-ep` не вырезали всё
- `.gitignore` не отфильтровал все файлы (попробуйте `--no-gitignore`)
