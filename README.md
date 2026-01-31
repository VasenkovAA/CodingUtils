<p align="center">
  <img src="docs/assets/logo.png"
       alt="CodingUtils logo"
       style="width: 100%; max-width: 900px; height: auto;">
</p>

# CodingUtils

[![CI](https://github.com/VasenkovAA/CodingUtils/actions/workflows/run_tests.yml/badge.svg)](https://github.com/VasenkovAA/CodingUtils/actions/workflows/run_tests.yml)

Набор небольших CLI‑утилит на Python для анализа и документирования кодовой базы: просмотр структуры проекта, извлечение/удаление комментариев и объединение файлов в один “снимок”.

Проект рассчитан на использование:
- локально (для ревью/аудита/подготовки документации),
- в CI (генерация артефактов: структура, комментарии, snapshot исходников),
- как “инструменты‑помощники” в репозитории.

---

## Что внутри

- **`tree-generator`** — ASCII‑визуализатор структуры проекта (альтернатива `tree`) с фильтрами и `.gitignore`, поддерживает вывод в `text/json/xml/markdown`.
- **`comment-extractor`** — извлечение и (опционально) удаление комментариев, preview‑режим, экспорт в `txt/json/jsonl`, фильтр по языку (опционально `langdetect`).
- **`file-merger`** — объединение выбранных файлов в один output с заголовками/метаданными, preview‑режим, лимиты размеров, обработка бинарных файлов, бэкапы output.

> Все утилиты используют единый стиль флагов и одинаковую модель фильтрации (pattern, exclude-*, gitignore).

---

## Требования

- Python **3.10+**
- Linux/macOS/Windows

Опционально:
- `langdetect` — для фильтрации удаления комментариев по языку в `comment-extractor`:
  ```bash
  pip install langdetect
  ```

---

## Установка

### Вариант 1: установить из GitHub через pip
```bash
pip install git+https://github.com/VasenkovAA/CodingUtils.git
```

### Вариант 2: разработка локально
```bash
git clone https://github.com/VasenkovAA/CodingUtils.git
cd CodingUtils
python -m venv venv
source venv/bin/activate
pip install -e .
```

---

## Быстрый старт

### 1) Структура проекта (рекурсивно, с учетом .gitignore)
```bash
tree-generator . -r -ig
```

### 2) Извлечение комментариев с экспортом
```bash
comment-extractor . -r -p "*.py" --export-comments comments.json
```

### 3) Снимок исходников в одном файле
```bash
file-merger src -r -p "*.py" -o merged.txt
```

---

## Общие принципы CLI (единый стиль)

Все утилиты поддерживают общий набор флагов:

- `DIRECTORY ...` — директории (позиционные)
- `-p/--pattern` — включающий паттерн файлов (glob)
- `-r/--recursive` — рекурсивный обход
- `--max-depth` — ограничение глубины (где применимо)
- `-ed/--exclude-dir`, `-en/--exclude-name`, `-ep/--exclude-pattern`
- `-ig/--use-gitignore`, `-gi/--gitignore`, `--no-gitignore`
- `-o/--output` — файл результата (для инструментов, у которых есть output)
- `--log-file`, `-v/--verbose` — логирование (логи идут в stderr/файл, результат — отдельно)

---

## `tree-generator` — структура проекта

Примеры:

```bash
# Текстовое дерево
tree-generator . -r -ig

# Ограничение глубины
tree-generator . -r --max-depth 2

# JSON (чистый, без логов)
tree-generator . -r -ig --format json -o structure.json
```

Подробная документация: **`docs/Tree_generator_RU.md`**

---

## `comment-extractor` — комментарии (extract / preview / remove)

Примеры:

```bash
# Извлечь комментарии и сохранить в JSONL
comment-extractor . -r --export-comments comments.jsonl

# Preview удаления (файлы не меняются)
comment-extractor . -r -p "*.py" --remove-comments --preview

# Реальное удаление + бэкапы в отдельную папку
comment-extractor . -r -p "*.py" --remove-comments --backup-dir .backups --overwrite-backups
```

Подробная документация: **`docs/Comment-extractor_RU.md`**

---

## `file-merger` — объединение файлов

Примеры:

```bash
# Preview: что будет объединено
file-merger src tests -r -p "*.py" --preview

# Реальный merge с заголовками
file-merger src -r -p "*.py" -o merged.txt

# Компактные заголовки (без relpath и даты)
file-merger src -r -p "*.py" -o merged.txt --compact-file-headers

# Бэкапы output-файла
file-merger src -r -p "*.py" -o merged.txt --backup-dir .backups
```

Подробная документация: **`docs/Merger_RU.md`**

---

## Документация

Подробные руководства лежат в `docs/`:

- `docs/Tree_generator_RU.md`
- `docs/Comment-extractor_RU.md`
- `docs/Merger_RU.md`

---

## Интеграция в CI / автоматизация

### GitHub Actions / GitLab CI (идея)
Генерировать артефакты на каждый запуск:

```yaml
# пример (псевдо)
steps:
  - run: tree-generator . -r -ig --format json -o structure.json
  - run: comment-extractor . -r --export-comments comments.jsonl
  - run: file-merger src -r -p "*.py" -o merged.txt
```

Потом сохранять `structure.json`, `comments.jsonl`, `merged.txt` как artifacts.

---
