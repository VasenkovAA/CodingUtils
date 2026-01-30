# `comment_extractor` — руководство пользователя

`comment_extractor` — CLI‑утилита для поиска, выгрузки и (опционально) удаления комментариев в исходном коде. Она умеет:

- находить файлы по директориям, паттерну и исключениям;
- учитывать `.gitignore` (по желанию);
- извлекать строчные и блочные комментарии (включая многострочные блоки);
- удалять комментарии в безопасном режиме (с резервными копиями по флагам);
- экспортировать найденные комментарии в `.txt`, `.json`, `.jsonl`;
- ограничивать удаление по языку комментариев (`langdetect`, опционально).

---

## Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Установка](#установка)
3. [Командная строка: синтаксис](#командная-строка-синтаксис)
4. [Режимы работы: поиск / preview / удаление](#режимы-работы-поиск--preview--удаление)
5. [Выбор файлов: директории, рекурсия, паттерн](#выбор-файлов-директории-рекурсия-паттерн)
6. [Исключения: exclude-dir / exclude-name / exclude-pattern](#исключения-exclude-dir--exclude-name--exclude-pattern)
7. [Поддержка `.gitignore`](#поддержка-gitignore)
8. [Как определяется синтаксис комментариев](#как-определяется-синтаксис-комментариев)
9. [Исключение комментариев по префиксу](#исключение-комментариев-по-префиксу)
10. [Языковая фильтрация удаления (langdetect)](#языковая-фильтрация-удаления-langdetect)
11. [Резервные копии (backup)](#резервные-копии-backup)
12. [Экспорт результатов](#экспорт-результатов)
13. [Логи и уровни подробности](#логи-и-уровни-подробности)
14. [Ограничения и важные замечания](#ограничения-и-важные-замечания)
15. [Рецепты (готовые сценарии)](#рецепты-готовые-сценарии)
16. [Частые проблемы](#частые-проблемы)

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

### 4) Предпросмотр удаления (ничего не изменяет)
```bash
comment-extractor . -r -p "*.py" --remove-comments --preview
```

### 5) Реальное удаление + сохранение бэкапов рядом с файлами
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

### Справка
```bash
comment-extractor --help
```

---

## Режимы работы: поиск / preview / удаление

Утилита может работать в трёх основных сценариях:

### A) Только поиск (по умолчанию)
- Находит комментарии и печатает их в stdout.
- Файлы не меняются.

```bash
comment-extractor src -r -p "*.js"
```

### B) Preview удаления (`--remove-comments --preview`)
- Вычисляет, какие комментарии **были бы удалены**, и считает статистику.
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

## Выбор файлов: директории, рекурсия, паттерн

### `DIRECTORY ...`
Примеры:

```bash
comment-extractor src
comment-extractor src tests
comment-extractor /path/to/project -r
```

### `-r / --recursive`
Рекурсивный обход:

```bash
comment-extractor . -r
```

### `-p / --pattern`
Файловый паттерн (glob по имени файла, например `*.py`, `*.js`):

```bash
comment-extractor . -r -p "*.py"
comment-extractor src -p "test_*.py"
```

Важно:
- В текущей версии `--pattern` принимает **один** паттерн за запуск.
- Если нужно обработать несколько расширений — обычно делают несколько запусков:

```bash
comment-extractor src -r -p "*.py" --export-comments py.json
comment-extractor src -r -p "*.js" --export-comments js.json
```

### `--max-depth`
Ограничение глубины обхода при `-r`:

```bash
comment-extractor . -r --max-depth 3
```

---

## Исключения: exclude-dir / exclude-name / exclude-pattern

Исключения применяются на этапе поиска файлов.

### `-ed / --exclude-dir NAME`
Исключает директории по имени сегмента пути (например `venv`, `node_modules`):

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

## Поддержка `.gitignore`

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
- `.py` → `#` (+ в вашей экосистеме могут поддерживаться тройные кавычки как блочный маркер)
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
- `#!` — shebang в скриптах
- `# noqa`/`# fmt: off` и т.п. (зависит от вашего стиля)

Пример: игнорировать комментарии, начинающиеся с `##`:
```bash
comment-extractor . -r -p "*.py" -e "##"
```

Важно:
- это **один** префикс на запуск;
- применяется к “сырым данным комментария” с позиции маркера;
- если строка начинается с исключаемого префикса (например `## ...`), она **не будет** считаться комментарием, и утилита не будет пытаться “найти второй #”.

---

## Языковая фильтрация удаления (langdetect)

### Что делает `--language`
Флаг `--language` влияет **на удаление** (и счётчик removed), но не обязательно на “видимость” комментариев в выводе/экспорте.

Пример: удалять только русские комментарии:
```bash
comment-extractor . -r -p "*.py" --remove-comments --language ru
```

Preview того же сценария:
```bash
comment-extractor . -r -p "*.py" --remove-comments --preview --language ru
```

### `--min-langdetect-len`
Минимальная длина текста (после очистки), при которой запускается `langdetect`.
Короткие комментарии часто классифицируются нестабильно, поэтому по умолчанию короткие строки “проходят” как удаляемые.

Пример: считать язык только для длинных комментариев:
```bash
comment-extractor . -r -p "*.py" --remove-comments --language en --min-langdetect-len 40
```

---

## Резервные копии (backup)


### Когда вообще создаются бэкапы
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
- `src/main.py` → бэкап `src/main.py.bak`

### `--backup-dir PATH`
Сохранять бэкапы в отдельную директорию, **с сохранением структуры** относительно “базовой директории”.

```bash
comment-extractor . -r -p "*.py" --remove-comments --backup-dir .backups
```

Пример:
- исходник: `src/main.py`
- бэкап: `.backups/src/main.py.bak`

> База для относительного пути — первая директория из списка `DIRECTORY ...`. Если определить относительный путь не удалось, бэкап будет сохранён просто как `<backup-dir>/<filename>.bak`.

### `--overwrite-backups`
По умолчанию, если бэкап уже существует, создаётся версия `.bak.1`, `.bak.2` …

```bash
comment-extractor . -r -p "*.py" --remove-comments --backup-dir .backups
comment-extractor . -r -p "*.py" --remove-comments --backup-dir .backups
# -> .backups/src/main.py.bak и .backups/src/main.py.bak.1
```

Если вы хотите всегда держать только последний бэкап:

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

#### Экспорт в JSON
```bash
comment-extractor . -r -p "*.py" --export-comments comments.json
```

#### Экспорт в JSONL
```bash
comment-extractor . -r --export-comments comments.jsonl
```

#### Экспорт + preview
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
      "raw": "# TODO: refactor"
    }
  ]
}
```

---

## Логи и уровни подробности

### `-o / --output FILE`
Записать лог в файл:

```bash
comment-extractor . -r -o run.log
```

### `--log-file FILE`
Устаревший алиас для `--output` (оставлен для совместимости).

### `-v / --verbose`
Более подробный вывод (debug‑информация):

```bash
comment-extractor . -r -v
```

---

## Ограничения и важные замечания

1) **Парсинг “вне строк” — эвристика.**
   Утилита пытается не принимать `//` или `#` внутри строк (`"..."`, `'...'`, `` `...` ``), но это не полноценный парсер языка.

2) **Python и тройные кавычки.**
   В вашей экосистеме тройные кавычки могут считаться блочными “комментариями” для совместимости. На практике это может быть docstring/строка.
   Рекомендация: для `.py` всегда сначала `--preview`, потом проверка `git diff`.

3) **Незакрытые блочные комментарии.**
   Если блок начался и не закрылся до EOF:
   - в `remove`‑режиме утилита считает, что блок продолжается до конца файла, вырезает его и сохраняет количество строк;
   - в `extract`‑режиме ничего не меняет, но пишет warning.

4) **Один `--pattern` и один `--exclude-comment-pattern` за запуск.**
   Для сложной логики используйте несколько запусков либо постобработку экспортов.

---

## Рецепты (готовые сценарии)

### 1) “Сканировать проект как git”
```bash
comment-extractor . -r -ig
```

### 2) Реально удалить комментарии только в `src/`, не трогая зависимости/сборки
```bash
comment-extractor src -r -ig \
  -ed venv -ed node_modules -ed dist -ed build \
  -p "*.py" \
  --remove-comments --preview
# посмотреть вывод, затем:
comment-extractor src -r -ig \
  -ed venv -ed node_modules -ed dist -ed build \
  -p "*.py" \
  --remove-comments --backup-dir .backups
```

### 3) Аудит на секреты
```bash
comment-extractor . -r -ig --export-comments comments.txt
grep -iE "password|secret|token|api[_-]?key" comments.txt
```

### 4) Удалить только английские комментарии (если установлен langdetect)
```bash
comment-extractor . -r -p "*.js" --remove-comments --language en --backup-dir .backups
```

---

## Частые проблемы

### “Почему нет `.bak`?”
Проверьте:
- вы не используете `--preview`
- реально что‑то было удалено (иначе файл не переписывается)
- вы включили сохранение бэкапов: `--keep-backups` или `--backup-dir`

По умолчанию (без этих флагов) **постоянные** `.bak` не создаются.

### “Я указал `--language`, но ничего не изменилось”
- убедитесь, что установлен `langdetect`
- помните: фильтрация влияет на удаление; если язык не совпал, комментарии остаются

### “Хочу несколько паттернов файлов”
Сделайте несколько запусков или используйте `--exclude-*` для отсечения лишнего.
