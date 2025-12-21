# Полное руководство по использованию утилиты `comment_extractor`

## Содержание
1. [Введение](#введение)
2. [Основные возможности](#основные-возможности)
3. [Установка и зависимости](#установка-и-зависимости)
4. [Базовое использование](#базовое-использование)
5. [Параметры поиска файлов](#параметры-поиска-файлов)
6. [Фильтрация и исключения](#фильтрация-и-исключения)
7. [Обработка комментариев](#обработка-комментариев)
8. [Языковая фильтрация](#языковая-фильтрация)
9. [Расширенные сценарии](#расширенные-сценарии)
10. [Форматы вывода](#форматы-вывода)
11. [Примеры использования](#примеры-использования)
12. [Сравнение с другими утилитами](#сравнение-с-другими-утилитами)
13. [Советы и рекомендации](#советы-и-рекомендации)

---

## Введение

`comment_extractor` - это продвинутый инструмент для обнаружения, анализа и удаления комментариев в исходном коде. Поддерживает множество языков программирования, интеллектуальную фильтрацию по языку и совместим с `.gitignore`.

**Основное назначение:**
- Очистка кода от ненужных комментариев
- Анализ комментариев на разных языках
- Экспорт документации из комментариев
- Подготовка кода для продакшена
- Аудит качества комментариев

## Основные возможности

**Поддержка языков программирования:**
- Python, JavaScript/TypeScript, Java
- C/C++, C#, PHP, Ruby
- Go, Rust, Lua, SQL
- HTML, CSS/SCSS/SASS
- Shell скрипты, Perl, R

**Типы комментариев:**
- Строчные комментарии (`#`, `//`, `--`)
- Блочные комментарии (`/* */`, `<!-- -->`)
- Встроенные комментарии (после кода)
- Многострочные блоки

**Фильтрация и анализ:**
- Определение языка комментариев
- Исключение по шаблонам
- Поддержка `.gitignore`
- Фильтрация по директориям и именам

**Режимы работы:**
- Детекция (только поиск)
- Предварительный просмотр
- Удаление комментариев
- Экспорт в файл

## Установка и зависимости

### Базовые требования
- Python 3.6+
- Стандартные библиотеки Python

### Опциональные зависимости
```bash
# Для языковой фильтрации комментариев
pip install langdetect

# Для расширенной обработки
pip install chardet  # автоматическое определение кодировки
```

### Проверка установки
```bash
# Базовая проверка
comment-extractor--help

# Проверка с langdetect
python -c "import langdetect; print('langdetect доступен')"
```

## Базовое использование

### Простейшие примеры
```bash
# Поиск комментариев в текущей директории
comment-extractor

# Поиск в конкретной директории
comment-extractor /path/to/project

# Поиск с рекурсией
comment-extractor . -r

# Только Python файлы
comment-extractor . -r -p "*.py"
```

### Режимы работы
```bash
# 1. Детекция (по умолчанию) - только поиск
comment-extractor -d src

# 2. Предварительный просмотр
comment-extractor -d src --preview

# 3. Удаление комментариев
comment-extractor -d src --remove-comments

# 4. Экспорт комментариев
comment-extractor -d src --export-comments comments.txt
```

## Параметры поиска файлов

### Основные параметры

| Параметр | Короткая форма | Описание | По умолчанию |
|----------|----------------|----------|--------------|
| `files` | - | Явный список файлов | - |
| `--directory` | `-d` | Директория для поиска | текущая |
| `--recursive` | `-r` | Рекурсивный поиск | False |
| `--pattern` | `-p` | Паттерн поиска файлов | `*` |

### Примеры поиска файлов

```bash
# Явное указание файлов
comment-extractor file1.py file2.js config.py

# Несколько директорий
comment-extractor -d src -d tests -d utils

# Рекурсивный поиск с паттерном
comment-extractor -d . -r -p "*.js"

# Комбинация директорий и файлов
comment-extractor main.py -d src -d lib
```

### Поддерживаемые паттерны
```bash
# Расширения языков
-p "*.py"              # Python
-p "*.js" -p "*.ts"    # JavaScript/TypeScript
-p "*.java"            # Java
-p "*.cpp" -p "*.h"    # C/C++
-p "*.go"              # Go
-p "*.rs"              # Rust
-p "*.php"             # PHP
-p "*.rb"              # Ruby
-p "*.sh"              # Shell
-p "*.sql"             # SQL

# Шаблоны имен
-p "test_*.py"         # Тестовые файлы
-p "*_spec.js"         # Spec файлы
-p "config*.*"         # Конфигурационные файлы
-p "*.min.*"           # Минифицированные файлы
```

## Фильтрация и исключения

### Флаги исключения

| Флаг | Короткая форма | Описание | Примеры |
|------|----------------|----------|---------|
| `--exclude-dir` | `-ed` | Исключить директории по имени | `-ed venv -ed __pycache__` |
| `--exclude-name` | `-en` | Исключить файлы по имени/шаблону | `-en "*.tmp" -en "temp_*"` |
| `--exclude-pattern` | `-ep` | Исключить по полному пути/шаблону | `-ep "*test*" -ep "*backup*"` |

### Примеры фильтрации

```bash
# Исключить системные директории
comment-extractor -d . -r -ed venv -ed .git -ed __pycache__

# Исключить сгенерированные файлы
comment-extractor -d . -en "*.pyc" -en "__pycache__/*"

# Исключить тестовые файлы
comment-extractor -d src -ep "*test*" -ep "*spec.*"

# Комплексная фильтрация
comment-extractor -d . \
  -ed node_modules \
  -ed dist \
  -ed build \
  -en "*.log" \
  -en "*.min.js" \
  -ep "*_old*" \
  -ep "*debug*"
```

### Использование .gitignore

| Флаг | Короткая форма | Описание |
|------|----------------|----------|
| `--gitignore` | `-gi` | Использовать указанный .gitignore |
| `--use-gitignore` | `-ig` | Автоматически найти .gitignore |

```bash
# Использовать стандартный .gitignore
comment-extractor -d . -r -ig

# Указать конкретный файл
comment-extractor -d . -gi /path/to/.gitignore

# Комбинировать с другими фильтрами
comment-extractor -d . -ig -ed build -en "*.log"
```

## Обработка комментариев

### Автоматическое определение символов комментариев
Утилита автоматически определяет символы комментариев по расширению файла:

| Расширение | Строчный | Блочный |
|------------|----------|---------|
| `.py` | `#` | - |
| `.js`, `.ts` | `//` | `/* */` |
| `.java` | `//` | `/* */` |
| `.cpp`, `.c`, `.h` | `//` | `/* */` |
| `.go` | `//` | `/* */` |
| `.php` | `//` | `/* */` |
| `.rb` | `#` | - |
| `.sh` | `#` | - |
| `.sql` | `--` | `/* */` |
| `.lua` | `--` | - |
| `.html` | - | `<!-- -->` |
| `.css`, `.scss` | - | `/* */` |

### Ручное указание символов
```bash
# Для нестандартных файлов
comment-extractor -d . -c "//"

# Для файлов без расширения
comment-extractor script -c "#"
```

### Исключение определенных комментариев
```bash
# Исключить комментарии, начинающиеся с ##
comment-extractor -d . -e "##"

# Исключить TODOs и FIXMEs
comment-extractor -d . -e "TODO" -e "FIXME"

# Исключить заголовочные комментарии
comment-extractor -d . -e "===" -e "---"
```

## Языковая фильтрация

### Определение языка комментариев
Для использования языковой фильтрации требуется установить `langdetect`:
```bash
pip install langdetect
```

### Примеры языковой фильтрации
```bash
# Только русские комментарии
comment-extractor -d . -l "ru"

# Только английские комментарии
comment-extractor -d . -l "en"

# Удалить неанглийские комментарии
comment-extractor -d . -l "en" --remove-comments

# Найти все иностранные комментарии
comment-extractor -d . --preview --export-comments foreign.txt
```

### Поддерживаемые языки
```bash
# Основные языки
-l "en"    # Английский
-l "ru"    # Русский
-l "es"    # Испанский
-l "fr"    # Французский
-l "de"    # Немецкий
-l "zh"    # Китайский
-l "ja"    # Японский
-l "ko"    # Корейский

# Полный список доступен в langdetect
python -c "from langdetect import DetectorFactory; df = DetectorFactory(); print(df.get_langs())"
```

### Особенности языковой фильтрации
1. **Короткие комментарии** (< 3 символов) игнорируются
2. **Технические термины** (def, class, import и т.д.) фильтруются
3. **Знаки препинания** удаляются перед анализом
4. **Смешанные языки** определяются по преобладающему

## Расширенные сценарии

### Очистка проекта для продакшена
```bash
# Удалить все комментарии из продакшен кода
comment-extractor -d src \
  -r \
  -ig \
  --remove-comments \
  -o cleanup.log

# Сохранить только английские комментарии
comment-extractor -d src \
  -r \
  -l "en" \
  --remove-comments \
  --export-comments kept_comments.txt
```

### Анализ комментариев в проекте
```bash
# Собрать статистику комментариев
comment-extractor -d . \
  -r \
  --export-comments all_comments.txt

# Анализ распределения языков
comment-extractor -d . \
  -r \
  --export-comments by_language/ \
  --preview
```

### Подготовка кода для локализации
```bash
# Извлечь все русские комментарии для перевода
comment-extractor -d src \
  -r \
  -l "ru" \
  --export-comments ru_comments.txt

# Удалить переведенные комментарии
comment-extractor -d src \
  -r \
  -l "ru" \
  --remove-comments \
  --export-comments removed_ru_comments.txt
```

### Аудит качества комментариев
```bash
# Найти пустые или бесполезные комментарии
comment-extractor -d . \
  -r \
  --preview \
  | grep -E "^\s*$|TODO|FIXME|HACK|XXX"

# Проверить соответствие стандартам
comment-extractor -d . \
  -r \
  -p "*.py" \
  --export-comments python_comments_audit.txt
```

## Форматы вывода

### Консольный вывод
```
Comment Extractor Configuration:
  Directory: /path/to/project
  Pattern: *.py
  Recursive: True
  Exclusions applied:
    Directories: venv, __pycache__
    Names: *.pyc
============================================================
Found 42 files to process
============================================================
src/main.py:10: This is a comment
src/utils.py:5: Another comment here
...
============================================================
Found 156 comments out of 200 total
Processed 42 files
```

### Файловый вывод
```bash
# Логирование в файл
comment-extractor -d . -o extraction.log

# Экспорт комментариев
comment-extractor -d . --export-comments comments.txt
```

### Формат экспортированных комментариев
```
EXTRACTED COMMENTS: 156 comments from 42 files
============================================================

FILE: src/main.py:10
COMMENT: This is a comment
----------------------------------------

FILE: src/utils.py:5
COMMENT: Another comment here
----------------------------------------
```

### Настройка логирования
```bash
# Минимальный вывод
comment-extractor -d . --quiet 2>/dev/null

# Детальный лог
comment-extractor -d . -o detailed.log

# Раздельные логи
comment-extractor -d . \
  --export-comments comments.txt \
  -o process.log
```

## Примеры использования

### Пример 1: Базовая очистка Python проекта
```bash
comment-extractor -d . \
  -r \
  -p "*.py" \
  -ed venv \
  -ed __pycache__ \
  -en "*.pyc" \
  --remove-comments \
  -o cleanup_python.log
```

### Пример 2: Анализ многоязычного проекта
```bash
# Собрать все комментарии
comment-extractor -d . \
  -r \
  --export-comments all_comments.txt

# Разделить по языкам
comment-extractor -d . -r -l "en" --export-comments english.txt
comment-extractor -d . -r -l "ru" --export-comments russian.txt
comment-extractor -d . -r -l "es" --export-comments spanish.txt

# Проанализировать распределение
wc -l *comments.txt
```

### Пример 3: Подготовка кода к ревью
```bash
# Удалить временные комментарии
comment-extractor -d src \
  -r \
  -e "TODO" \
  -e "FIXME" \
  -e "HACK" \
  -e "XXX" \
  --remove-comments \
  --export-comments removed_todos.txt
```

### Пример 4: Миграция комментариев
```bash
# Экспорт всех комментариев из старой кодовой базы
comment-extractor -d legacy_code \
  -r \
  --export-comments legacy_comments.txt

# Импорт в новую систему (пример обработки)
cat legacy_comments.txt | grep -v "FILE:" > clean_comments.txt
```

### Пример 5: Аудит безопасности
```bash
# Поиск потенциально опасных комментариев
comment-extractor -d . \
  -r \
  --export-comments security_audit.txt

# Проверка на наличие секретов
grep -i "password\|secret\|key\|token\|credential" security_audit.txt
```

### Пример 6: Генерация документации
```bash
# Извлечь docstring и важные комментарии
comment-extractor -d src \
  -r \
  -p "*.py" \
  -e "#" \
  --export-comments documentation.txt

# Отфильтровать только полезные комментарии
grep -v "^#" documentation.txt | grep -v "^$" > clean_docs.txt
```

## Советы и рекомендации

### Безопасность работы

1. **Всегда используйте `--preview` перед удалением:**
```bash
# Сначала проверьте
comment-extractor -d . --preview

# Затем удаляйте
comment-extractor -d . --remove-comments
```

2. **Создавайте резервные копии:**
```bash
# Перед массовым удалением
cp -r project/ project_backup/
comment-extractor -d project --remove-comments
```

3. **Используйте систему контроля версий:**
```bash
# Сделайте коммит перед изменениями
git add .
git commit -m "Before comment removal"

# Выполните удаление
comment-extractor -d . --remove-comments

# Проверьте изменения
git diff
```

### Производительность

1. **Исключайте ненужные директории:**
```bash
# Оптимизированный запуск
comment-extractor -d . \
  -ed node_modules \
  -ed venv \
  -ed .git \
  -ed __pycache__ \
  -ed dist \
  -ed build
```

2. **Используйте конкретные паттерны:**
```bash
# Вместо
comment-extractor -d . -r

# Используйте
comment-extractor -d src -r -p "*.py"
```

3. **Ограничивайте глубину рекурсии через фильтры:**
```bash
# Исключить глубокие директории
comment-extractor -d . -ed "**/node_modules/**" -ed "**/vendor/**"
```

### Интеграция в рабочий процесс

#### CI/CD пайплайн
```yaml
# .gitlab-ci.yml
audit_comments:
  stage: test
  script:
    - comment-extractor -d src -r --export-comments comments_audit.txt
    - comment-extractor -d src -r -l "en" --preview
  artifacts:
    paths:
      - comments_audit.txt
```

#### Makefile
```makefile
.PHONY: clean-comments
clean-comments:
	comment-extractor -d src -r --remove-comments

.PHONY: audit-comments
audit-comments:
	comment-extractor -d . -r --export-comments comments_audit_$(shell date +%Y%m%d).txt

.PHONY: preview-comments
preview-comments:
	comment-extractor -d . -r --preview
```

#### Скрипты оболочки
```bash
#!/bin/bash
# cleanup_project.sh

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backup_${TIMESTAMP}"

echo "Создание резервной копии..."
cp -r project/ "${BACKUP_DIR}/"

echo "Анализ комментариев..."
comment-extractor -d project -r --preview > "preview_${TIMESTAMP}.log"

read -p "Продолжить с удалением комментариев? (y/n): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Удаление комментариев..."
    comment-extractor -d project -r --remove-comments > "removal_${TIMESTAMP}.log"
    echo "Готово! Резервная копия в ${BACKUP_DIR}"
else
    echo "Операция отменена."
fi
```

### Расширенные настройки

#### Кастомные символы комментариев
```bash
# Для нестандартных форматов
comment-extractor -d . -c "%%"  # MATLAB-style
comment-extractor -d . -c "(*"  # Pascal-style (начало)
```

#### Обработка специфичных файлов
```bash
# Dockerfile
comment-extractor -d . -p "Dockerfile" -c "#"

# Makefile
comment-extractor -d . -p "Makefile" -c "#"

# Конфиги YAML
comment-extractor -d . -p "*.yaml" -p "*.yml" -c "#"
```

#### Пакетная обработка
```bash
# Обработка проектов по списку
for project in project1 project2 project3; do
    echo "Обработка $project..."
    comment-extractor -d "$project" \
        -r \
        --export-comments "${project}_comments.txt" \
        -o "${project}_process.log"
done
```

### Решение проблем

#### Проблема: Не определяется язык комментариев
```bash
# Проверьте установку langdetect
python -c "import langdetect; print('OK')"

# Используйте без языковой фильтрации
comment-extractor -d . --preview
```

#### Проблема: Кодировка файлов
```bash
# Принудительно укажите кодировку (в коде можно добавить параметр)
# Или конвертируйте файлы заранее
find . -name "*.py" -exec iconv -f WINDOWS-1251 -t UTF-8 {} -o {}.utf8 \;
```

#### Проблема: Слишком много false positives
```bash
# Настройте исключения
comment-extractor -d . \
  -e "TODO" \
  -e "FIXME" \
  -e "NOTE" \
  --preview

# Или используйте языковую фильтрацию
comment-extractor -d . -l "en" --preview
```

