# Полное руководство пользователя: `file-merger`

`file-merger` (модуль `codingutils/merger.py`) — CLI‑утилита для объединения содержимого многих файлов в один выходной файл. Поддерживает фильтрацию (включая `.gitignore`), лимиты размеров, постобработку строк, безопасную запись результата и управление бэкапами выходного файла.

---

## Содержание

1. [Введение](#введение)
2. [Основные возможности](#основные-возможности)
3. [Установка и запуск](#установка-и-запуск)
4. [Быстрый старт](#быстрый-старт)
5. [Синтаксис команды](#синтаксис-команды)
6. [Выбор файлов: directories, recursive, max-depth, pattern](#выбор-файлов-directories-recursive-max-depth-pattern)
7. [Фильтрация и исключения](#фильтрация-и-исключения)
8. [Поддержка .gitignore](#поддержка-gitignore)
9. [Режим preview](#режим-preview)
10. [Формат выходного файла](#формат-выходного-файла)
11. [Заголовки файлов и `--compact-file-headers`](#заголовки-файлов-и---compact-file-headers)
12. [Постобработка содержимого (line numbers, remove empty, dedupe)](#постобработка-содержимого-line-numbers-remove-empty-dedupe)
13. [Ограничения по размеру (max-file-size, max-total-size)](#ограничения-по-размеру-max-file-size-max-total-size)
14. [Бинарные файлы](#бинарные-файлы)
15. [Бэкапы выходного файла](#бэкапы-выходного-файла)
16. [Логи и отладка](#логи-и-отладка)
17. [Примеры (рецепты)](#примеры-рецепты)
18. [Частые проблемы](#частые-проблемы)

---

## Введение

`file-merger` предназначен для задач вида:

- собрать исходники проекта в один файл (для анализа, ревью, LLM/архива);
- собрать конфиги в один документ;
- собрать часть репозитория по шаблону (например `*.py`, `*.md`);
- получить “снимок” файлов с учётом `.gitignore` и исключений.

---

## Основные возможности

### Поиск и фильтрация
- несколько директорий одновременно (позиционные аргументы)
- рекурсивный обход (`-r`)
- паттерн включения файлов (`-p`)
- исключения: директории/имена/пути (`-ed/-en/-ep`)
- поддержка `.gitignore` (`-ig` / `-gi` / `--no-gitignore`)

### Формирование результата
- глобальная мета‑шапка (список файлов, настройки)
- заголовки перед каждым файлом
- **compact mode** для заголовков: `--compact-file-headers` (см. ниже)
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

### 2) Предпросмотр перед мержем
```bash
file-merger src tests -r -p "*.py" --preview
```

### 3) Учесть `.gitignore`
```bash
file-merger . -r -ig -p "*" -o merged.txt
```

### 4) Сделать заголовки компактнее (без relpath и даты)
```bash
file-merger . -r -p "*.py" -o merged.txt --compact-file-headers
```

---

## Синтаксис команды

```bash
file-merger [DIRECTORY ...] [OPTIONS]
```

- `DIRECTORY ...` — директории (0..N). Если не указано — `.`.
- Выходной файл задаётся `-o/--output`.

---

## Выбор файлов: directories, recursive, max-depth, pattern

### `DIRECTORY ...`
Одна или несколько директорий:

```bash
file-merger src tests docs -r -p "*.md" -o docs.txt
```

### `-r / --recursive`
Включить рекурсивный обход:

```bash
file-merger . -r -p "*.txt" -o merged.txt
```

### `--max-depth`
Ограничить глубину обхода (работает совместно с `-r`):

```bash
file-merger . -r --max-depth 3 -p "*.py" -o merged.txt
```

### `-p / --pattern`
Паттерн включения для файлов (glob по basename):

```bash
file-merger . -r -p "*.py" -o py.txt
file-merger . -r -p "test_*.py" -o tests.txt
```

Примечание: один `-p` на запуск (в текущей версии). Если нужно несколько расширений — запускайте несколько раз или используйте `-p "*" + exclude`.

---

## Фильтрация и исключения

Как и в других утилитах проекта:

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
Новый флаг делает заголовок короче: **убирает “строку с относительным путём” и строку `Modified:`**.

То есть вместо:

- `FILE X/Y: <relative_path>`
- `Modified: ...`

будет:

- `FILE X/Y: <filename>`
- (Modified строки нет)

Пример:
```bash
file-merger . -r -p "*.py" -o merged.txt --compact-file-headers
```

Когда это полезно:
- если относительные пути и даты “шумят” и не нужны;
- если вы делаете merge для дальнейшего анализа/LLM и хотите меньше служебного текста.

---

## Постобработка содержимого (line numbers, remove empty, dedupe)

Все опции применяются **к каждому файлу отдельно** (per-file).

### `--add-line-numbers`
Добавляет номера строк внутри каждого файла:

```bash
file-merger src -r -p "*.py" --add-line-numbers -o merged.txt
```

Нумерация начинается заново для каждого файла.

### `--remove-empty-lines`
Убирает пустые/пробельные строки:

```bash
file-merger . -r -p "*.txt" --remove-empty-lines -o merged.txt
```

### `--deduplicate`
Удаляет повторяющиеся строки **внутри одного файла** (не глобально по всему merged‑output):

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
Ограничивает суммарный размер выбранных файлов. Если следующий файл “не помещается” — он будет пропущен с причиной `max_total_size`.

Пример:
```bash
file-merger . -r -p "*.py" --max-total-size 20MB -o merged.txt
```

Важно:
- выбор файлов идёт в порядке списка (по умолчанию — порядок обхода; с `--sort-files` — детерминированный).

---

## Бинарные файлы

По умолчанию бинарные файлы **не мержатся как байты**, вместо них вставляется плейсхолдер:

```
[BINARY FILE: something.exe]
Size: 1.23 MB
SHA256: ...
Binary content is not merged.
```

### Управление бинарным поведением

- `--no-binary-placeholders` — бинарники пропускаются почти молча (вставляется короткая строка `[BINARY FILE SKIPPED]`).
- `--no-binary-hash` — не считать SHA256.

Примеры:
```bash
file-merger . -r -p "*" --no-binary-hash -o merged.txt
file-merger . -r -p "*" --no-binary-placeholders -o merged.txt
```

---

## Бэкапы выходного файла

Бэкапы касаются **только** файла `--output`, если он уже существует и вы делаете реальный merge (не preview).

### `--keep-backups`
Сохранять бэкап рядом с output:

```bash
file-merger . -r -p "*.py" -o merged.txt --keep-backups
```

Получится `merged.txt.bak`.

### `--backup-dir PATH`
Сохранять бэкапы в отдельную директорию:

```bash
file-merger . -r -p "*.py" -o merged.txt --backup-dir .backups
```

### `--overwrite-backups`
По умолчанию, если бэкап уже существует — создаётся версия:
- `merged.txt.bak.1`, `merged.txt.bak.2`, ...

Чтобы перезаписывать существующий `.bak`:

```bash
file-merger . -r -p "*.py" -o merged.txt --backup-dir .backups --overwrite-backups
```

---

## Логи и отладка

### `--log-file`
Записать логи в файл:

```bash
file-merger . -r -p "*.py" -o merged.txt --log-file run.log
```

### `-v / --verbose`
Включить debug‑логи:

```bash
file-merger . -r -p "*.py" -o merged.txt -v --log-file debug.log
```

Важно:
- merged content **не попадает** в лог, только в `--output`.

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

### 3) Документация из markdown
```bash
file-merger docs -r -p "*.md" \
  --remove-empty-lines \
  -o docs_merged.md
```

### 4) Компактный merge для LLM
```bash
file-merger . -r -ig -p "*.py" \
  --no-metadata \
  --compact-file-headers \
  --remove-empty-lines \
  -o code_for_llm.txt
```

### 5) Ограничить общий размер
```bash
file-merger . -r -p "*" --max-total-size 50MB -o merged.txt --preview
file-merger . -r -p "*" --max-total-size 50MB -o merged.txt
```

---

## Частые проблемы

### “No files found to merge”
Проверьте:
- вы указали `-r` если хотите рекурсивно
- паттерн `-p` не слишком узкий
- исключения `-ed/-en/-ep` не вырезали всё
- `.gitignore` не отфильтровал все файлы (попробуйте `--no-gitignore`)

### “Почему output файл попал внутрь merged?”
В production‑версии утилита исключает `--output` из входных файлов автоматически. Если видите иначе — вероятно запущена старая версия.

### “Кодировка ломается”
Утилита пытается определить кодировку автоматически. Если UTF‑8 не подходит — падает в `latin-1` с `errors=replace`.
Если вам принципиально нужен строгий режим — можно добавить в будущем флаг `--strict-encoding` (сейчас его нет).

### “Слишком большой merged.txt”
Используйте:
- `--max-file-size`, `--max-total-size`
- `--preview` для оценки
- более точный `-p`
- исключения тяжёлых директорий: `-ed node_modules -ed dist -ed build`
