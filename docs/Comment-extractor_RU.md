# `comment_extractor` — руководство пользователя

`comment_extractor` — CLI‑утилита для поиска, выгрузки и (опционально) удаления комментариев в исходном коде. Она умеет:

- находить файлы по директориям, паттернам и исключениям;
- учитывать `.gitignore` (по желанию);
- извлекать строчные и блочные комментарии (включая многострочные блоки);
- удалять комментарии в безопасном режиме (с резервными копиями по флагам);
- экспортировать найденные комментарии в `.txt`, `.json`, `.jsonl`;
- ограничивать удаление по языку комментариев (`langdetect`, опционально);
- обрабатывать Jupyter Notebook (`.ipynb`) — извлекает/удаляет комментарии в **code**‑ячейках.

---

## Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Установка](#установка)
3. [Командная строка: синтаксис](#командная-строка-синтаксис)
4. [Режимы работы: поиск / preview / удаление](#режимы-работы-поиск--preview--удаление)
5. [Выбор файлов: директории, рекурсия, паттерны, -d/-dr](#выбор-файлов-директории-рекурсия-паттерны--ddr)
6. [Исключения: exclude-dir / exclude-name / exclude-pattern](#исключения-exclude-dir--exclude-name--exclude-pattern)
7. [Поддержка `.gitignore`](#поддержка-gitignore)
8. [Как определяется синтаксис комментариев](#как-определяется-синтаксис-комментариев)
9. [Исключение комментариев по префиксу](#исключение-комментариев-по-префиксу)
10. [Языковая фильтрация удаления (langdetect)](#языковая-фильтрация-удаления-langdetect)
11. [Jupyter Notebook (`.ipynb`)](#jupyter-notebook-ipynb)
12. [Резервные копии (backup)](#резервные-копии-backup)
13. [Экспорт результатов](#экспорт-результатов)
14. [Логи, подробность и split streams](#логи-подробность-и-split-streams)
15. [Ограничения и важные замечания](#ограничения-и-важные-замечания)
16. [Рецепты (готовые сценарии)](#рецепты-готовые-сценарии)
17. [Частые проблемы](#частые-проблемы)

---

## Быстрый старт

### 1) Найти комментарии в текущей папке (без рекурсии)
```bash
comment-extractor
```

### 2) Рекурсивно по проекту
```bash
comment-extractor . -r
```

### 3) Только Python-файлы
```bash
comment-extractor . -r -p "*.py"
```

### 4) Несколько паттернов (py + js)
```bash
comment-extractor . -r -p "*.py" "*.js"
# или одной строкой:
comment-extractor . -r -p "*.py *.js"
```

### 5) Разная рекурсия для разных директорий
```bash
comment-extractor -dr src -d docs -p "*.py" "*.md"
# src рекурсивно, docs только верхний уровень
```

### 6) Предпросмотр удаления (ничего не изменяет)
```bash
comment-extractor . -r -p "*.py" --remove-comments --preview
```

### 7) Реальное удаление + сохранение бэкапов рядом с файлами
```bash
comment-extractor . -r -p "*.py" --remove-comments --keep-backups
```

---

## Установка

### Требования
- Python 3.10+

### Опционально: языковая фильтрация
Если нужен флаг `--language`, установите `langdetect`:

```bash
pip install langdetect
```

Проверка:
```bash
python -c "import langdetect; print('langdetect OK')"
```

---

## Командная строка: синтаксис

### Общий вид
```bash
comment-extractor [DIRECTORY ...] [OPTIONS]
```

- `DIRECTORY ...` — одна или несколько директорий. Если не указаны — используется текущая (`.`).
- Большинство опций можно комбинировать.
- Дополнительно можно использовать `-d/-dr` (см. ниже) и смешивать их с позиционными директориями.

### Справка
```bash
comment-extractor --help
```

---

## Режимы работы: поиск / preview / удаление

Утилита может работать в трёх основных сценариях:

### A) Только поиск (по умолчанию)
- Находит комментарии и печатает их в вывод.
- Файлы не меняются.

```bash
comment-extractor src -r -p "*.js"
```

### B) Preview удаления (`--remove-comments --preview`)
- Вычисляет, какие комментарии **были бы удалены**.
- Файлы не меняются.

```bash
comment-extractor src -r -p "*.js" --remove-comments --preview
```

### C) Реальное удаление (`--remove-comments`)
- Удаляет комментарии из файлов.
- При необходимости делает резервные копии (см. раздел про бэкапы).

```bash
comment-extractor src -r -p "*.js" --remove-comments
```

---

## Выбор файлов: директории, рекурсия, паттерны, -d/-dr

### `DIRECTORY ...`
Примеры:

```bash
comment-extractor src
comment-extractor src tests
comment-extractor /path/to/project -r
```

### `-r / --recursive`
Рекурсивный обход “по умолчанию”:

```bash
comment-extractor . -r
```

### `-d / --dir` и `-dr / --dir-recursive` (пер‑директория рекурсия)
Позволяет указать режим обхода для конкретной директории:

- `-dr DIR` — DIR обходить рекурсивно
- `-d DIR` — DIR обходить НЕрекурсивно (только верхний уровень)

Пример:
```bash
comment-extractor -dr src -d docs -p "*.py" "*.md"
```

Поведение:
- для директорий, перечисленных через `-d/-dr`, режим рекурсии берётся оттуда;
- для остальных директорий действует “дефолт” из `-r` (если не задан — нерекурсивно).

### `-p / --pattern` (несколько паттернов)
Паттерны включения файлов (glob по basename). Поддерживается несколько вариантов передачи:

```bash
comment-extractor . -r -p "*.py" "*.js"
comment-extractor . -r -p "*.py *.js *.*"
```

Семантика:
- файл включается, если его имя совпадает **хотя бы с одним** паттерном (логика OR).

### `--max-depth`
Ограничение глубины обхода при рекурсивном поиске:

```bash
comment-extractor . -r --max-depth 3
```

---

## Исключения: exclude-dir / exclude-name / exclude-pattern

Исключения применяются на этапе поиска файлов.

### `-ed / --exclude-dir NAME`
Исключает директории по имени сегмента пути:

```bash
comment-extractor . -r -ed venv -ed node_modules -ed __pycache__
```

### `-en / --exclude-name GLOB`
Исключает файлы по имени (basename) через glob:

```bash
comment-extractor . -r -en "*.min.js" -en "*.pyc"
```

### `-ep / --exclude-pattern GLOB`
Исключает по пути (паттерн может матчить относительный путь и имя):

```bash
comment-extractor . -r -ep "tests/*" -ep "**/migrations/*"
```

---

## Поддержка gitignore

### Авто-поиск `.gitignore`
```bash
comment-extractor . -r -ig
# или
comment-extractor . -r --use-gitignore
```

### Использовать конкретный `.gitignore`
```bash
comment-extractor . -r -gi /path/to/.gitignore
```

### Полностью отключить `.gitignore`
```bash
comment-extractor . -r --no-gitignore
```

---

## Как определяется синтаксис комментариев

По умолчанию утилита выбирает “стиль комментариев” по расширению файла через `FileContentDetector.get_comment_style()`.

Примерно (упрощённо):
- `.py` → `#` (и потенциально тройные кавычки как блочный маркер — см. замечания ниже)
- `.js/.ts/.java/.c/.cpp` → `//` и `/* */`
- `.sql` → `--` и `/* */`
- `.html/.xml` → `<!-- -->`
- `.css` → `/* */`

### Принудительное переопределение: `-c / --comment-symbols`
Формат задаётся строкой (лучше всегда брать в кавычки):

1) Только строчный комментарий:
```bash
comment-extractor . -r -p "*.conf" -c "#"
```

2) Только блочный:
```bash
comment-extractor . -r -p "*.tmpl" -c "/* */"
```

3) Строчный + блочный:
```bash
comment-extractor . -r -p "*.txt" -c "# /* */"
```

---

## Исключение комментариев по префиксу

### `-e / --exclude-comment-pattern PREFIX`

Иногда в проекте есть “служебные” комментарии, которые нельзя удалять/учитывать. Например:
- `##` — особые метки
- `#!` — shebang
- `# noqa`, `# fmt: off` и т.п.

Пример: игнорировать комментарии, начинающиеся с `##`:
```bash
comment-extractor . -r -p "*.py" -e "##"
```

Важно:
- это **один** префикс на запуск;
- применяется к “сырым данным комментария” начиная с маркера (`#`, `//`, `/*`, …).

---

## Языковая фильтрация удаления (langdetect)

### Что делает `--language`
Флаг `--language` влияет на то, **какие комментарии будут удаляться** (и на счётчик removed).
Если `langdetect` недоступен, фильтрация автоматически игнорируется (будут удаляться все подходящие комментарии).

Пример: удалять только русские комментарии:
```bash
comment-extractor . -r -p "*.py" --remove-comments --language ru
```

Preview:
```bash
comment-extractor . -r -p "*.py" --remove-comments --preview --language ru
```

### `--min-langdetect-len`
Минимальная длина текста (после нормализации), при которой запускается `langdetect`.
Короткие комментарии часто классифицируются нестабильно, поэтому короткие строки по умолчанию “проходят” как удаляемые.

```bash
comment-extractor . -r -p "*.py" --remove-comments --language en --min-langdetect-len 40
```

---

## Jupyter Notebook (`.ipynb`)

`.ipynb` поддерживаются:

- утилита читает notebook как JSON
- определяет “язык ядра” (kernel language) по metadata (`language_info` / `kernelspec`) и выбирает подходящий стиль комментариев
- обрабатывает **только `cell_type == "code"`**
- markdown/raw ячейки не обрабатываются

Пример:
```bash
comment-extractor . -r -p "*.ipynb"
comment-extractor . -r -p "*.ipynb" --remove-comments --preview
```

---

## Резервные копии (backup)

### Когда создаются бэкапы
Бэкап создаётся **только если одновременно**:
- включено реальное удаление: `--remove-comments`
- **нет** `--preview`
- действительно есть что удалить (removed_count > 0)
- включено сохранение бэкапов: `--keep-backups` или `--backup-dir`

### `--keep-backups`
Сохранять бэкапы рядом с изменёнными файлами:

```bash
comment-extractor . -r -p "*.py" --remove-comments --keep-backups
```

Пример:
- `src/main.py` → `src/main.py.bak`

### `--backup-dir PATH`
Сохранять бэкапы в отдельную директорию с сохранением структуры относительно “базы” (первой директории из списка входных директорий):

```bash
comment-extractor . -r -p "*.py" --remove-comments --backup-dir .backups
```

Пример:
- `src/main.py` → `.backups/src/main.py.bak`

Если определить относительный путь не удалось, бэкап будет сохранён как:
- `.backups/<filename>.bak`

### `--overwrite-backups`
По умолчанию, если бэкап уже существует — создаётся версия `.bak.1`, `.bak.2` и т.д.

Чтобы всегда держать только последний бэкап:

```bash
comment-extractor . -r -p "*.py" --remove-comments --backup-dir .backups --overwrite-backups
```

---

## Экспорт результатов

### `--export-comments PATH`
Экспортирует найденные комментарии. Формат зависит от расширения:

- `.txt` — текстовый отчёт
- `.json` — структурированный JSON
- `.jsonl` — JSON Lines (по одному объекту на строку)

Примеры:

```bash
comment-extractor . -r -p "*.py" --export-comments comments.json
comment-extractor . -r -p "*.py" --export-comments comments.jsonl
comment-extractor . -r -p "*.py" --export-comments comments.txt
```

Экспорт + preview удаления:
```bash
comment-extractor src -r -p "*.js" --remove-comments --preview --export-comments audit.json
```

### Структура JSON (пример)
`comments.json` содержит объект:

```json
{
  "generated_at": "2026-01-30 12:34:56",
  "total_comments": 123,
  "comments": [
    {
      "file": "/abs/path/src/main.py",
      "relative_path": "src/main.py",
      "kind": "line",
      "start_line": 10,
      "start_col": 15,
      "end_line": 10,
      "end_col": 40,
      "text": "TODO: refactor",
      "raw": "# TODO: refactor",
      "cell_index": null
    }
  ]
}
```

`cell_index` заполняется только для `.ipynb`.

---

## Логи, подробность и split streams

### `-o / --output FILE` и `--log-file FILE`
- `--output` — файл логов (сообщения утилиты).
- `--log-file` — legacy-алиас для `--output`.

```bash
comment-extractor . -r -o run.log
comment-extractor . -r --log-file run.log
```

### `-v / --verbose`
Более подробный вывод (debug-информация):

```bash
comment-extractor . -r -v
```

### `--split-streams` (для GUI/обёрток)
Разделяет “основной вывод” и диагностику:

- **stdout**: найденные комментарии (строки вида `file:line: text`)
- **stderr**: прогресс, предупреждения, ошибки, служебные логи

Пример:
```bash
comment-extractor . -r -p "*.py" --split-streams
```

---

## Ограничения и важные замечания

1) **Парсинг “вне строк” — эвристика.**
Утилита старается игнорировать маркеры комментариев внутри строк (`"..."`, `'...'`, `` `...` ``), но это не полноценный парсер языка.

2) **Python и тройные кавычки.**
Тройные кавычки могут трактоваться как блочные маркеры (в зависимости от `FileContentDetector`), что может пересечься с docstring/строковыми литералами.
Рекомендация: для `.py` сначала `--preview`, затем проверка `git diff`.

3) **Незакрытые блочные комментарии.**
Если блок начался и не закрылся до EOF:
- в режиме удаления — утилита вырезает его “до конца файла”, сохраняя количество строк;
- в режиме поиска — ничего не меняет, но пишет warning.

---

## Рецепты (готовые сценарии)

### 1) “Сканировать проект как git”
```bash
comment-extractor . -r -ig
```

### 2) Удалить комментарии только в `src/`, не трогая зависимости/сборки
```bash
comment-extractor src -r -ig \
  -ed venv -ed node_modules -ed dist -ed build \
  -p "*.py" \
  --remove-comments --preview

# затем реальный запуск:
comment-extractor src -r -ig \
  -ed venv -ed node_modules -ed dist -ed build \
  -p "*.py" \
  --remove-comments --backup-dir .backups
```

### 3) Несколько типов файлов за один запуск
```bash
comment-extractor . -r -p "*.py" "*.js" "*.ts" --export-comments comments.json
```

### 4) Разная рекурсия для разных директорий
```bash
comment-extractor -dr src -d docs -p "*.py" "*.md"
```

### 5) Удалить только английские комментарии (langdetect)
```bash
comment-extractor . -r -p "*.js" --remove-comments --language en --backup-dir .backups
```

---

## Частые проблемы

### “Почему нет `.bak`?”
Проверьте:
- вы не используете `--preview`
- реально что‑то было удалено (иначе файл не переписывается)
- вы включили бэкапы: `--keep-backups` или `--backup-dir`

### “Я указал `--language`, но ничего не изменилось”
- убедитесь, что установлен `langdetect`
- проверьте `--min-langdetect-len` (слишком большой порог может привести к “всегда удалять” для коротких — но не к “ничего не удалять”)
- помните: фильтрация влияет на удаление; если язык не совпал, комментарии остаются
