# English

# CodingUtils

A comprehensive set of Python utilities for code analysis, file management, and project documentation. These scripts help developers maintain clean codebases, merge files efficiently, and visualize project structures.

## Scripts Overview

### 1. comment_extractor.py

**Purpose**: Automatically detect and remove code comments with language-specific filtering.

**Features**:
- Multi-language comment detection (Python, C/C++, Java, JavaScript, etc.)
- Language-based comment filtering (English, Russian, etc.)
- Safe comment removal with preview mode
- Support for inline and full-line comments
- Custom comment symbol configuration

**Usage**:
```bash
# Basic comment detection in Python files
python comment_extractor.py ./src -p "*.py" -l en

# Remove Russian comments from C++ files recursively
python comment_extractor.py ./project -r -p "*.cpp" -l ru --remove-comments

# Process single file with custom comment symbols
python comment_extractor.py config.txt -c "#" --remove-comments -o comments.log

# Preview comments without removal
python comment_extractor.py ./src -p "*.js" -l en
```

**Parameters**:
- `directory`: Directory to search or single file to process
- `-r, --recursive`: Search subdirectories recursively
- `-p, --pattern`: File pattern (e.g., "*.py", "model_*.cpp")
- `-c, --comment-symbols`: Custom comment symbols
- `-e, --exclude-pattern`: Pattern to exclude from comments
- `-l, --language`: Language code for comment filtering
- `--remove-comments`: Actually remove comments (default: detection only)
- `-o, --log-file`: Output log file (default: console)

**Dependencies**: `pip install langdetect`

---

### 2. merger.py

**Purpose**: Merge multiple files into a single file with clear file headers and boundaries.

**Features**:
- Merge explicit file lists or directory patterns
- Recursive directory searching
- File headers with relative paths
- Preview mode before merging
- Cross-platform path handling

**Usage**:
```bash
# Merge specific files
python merger.py file1.py file2.js file3.txt -o combined.txt

# Merge all Python files recursively
python merger.py -d ./src -r -p "*.py" -o all_code.txt

# Preview what would be merged
python merger.py -d ./docs -p "*.md" --preview

# Merge with custom pattern
python merger.py -d ./project -p "test_*.py" -o tests_combined.txt
```

**Parameters**:
- `files`: Explicit list of files to merge
- `-d, --directory`: Directory to search files
- `-r, --recursive`: Search subdirectories
- `-p, --pattern`: File pattern to match
- `-o, --output`: Output file (default: merged_files.txt)
- `--preview`: Preview without merging

---

### 3. tree_generater.py

**Purpose**: Generate project structure trees with .gitignore support (cross-platform alternative to `tree` command).

**Features**:
- .gitignore pattern support
- Cross-platform compatibility
- File filtering with patterns
- Statistics (file count, directory count, total size)
- Multiple output formats

**Usage**:
```bash
# Basic project tree
python tree_generater.py

# Tree with specific directory and .gitignore
python tree_generater.py -d ./my_project -i .gitignore -o project_tree.txt

# Only show Python files
python tree_generater.py -p "*.py"

# Ignore .gitignore rules
python tree_generater.py --no-gitignore

# Complex example
python tree_generater.py -d ./src -p "*.py" -i ../.gitignore -o python_structure.txt
```

**Parameters**:
- `-d, --directory`: Directory to map (default: current)
- `-i, --gitignore`: Path to .gitignore file
- `-p, --pattern`: File pattern to include
- `-o, --output`: Output file for tree
- `--no-gitignore`: Ignore .gitignore files

---

## Installation

1. Clone or download the scripts
2. Ensure Python 3.6+ is installed
3. Install optional dependencies:
   ```bash
   pip install langdetect
   ```

## Common Use Cases

### Code Cleanup
```bash
python comment_extractor.py ./src -r -p "*.py" -l en --remove-comments
```

### Documentation Generation
```bash
python merger.py -d ./src -p "*.py" -o documentation.txt
python tree_generater.py -o project_structure.txt
```

### Project Analysis
```bash
python tree_generater.py --no-gitignore -o full_structure.txt
python comment_extractor.py ./src -l ru -o russian_comments.log
```

## Notes

- All scripts are cross-platform (Windows, Linux, macOS)
- File encoding is automatically handled (UTF-8, Latin-1)
- Permission errors are gracefully handled
- Relative paths are calculated from the execution directory

---

# Русский

# CodingUtils

Комплексный набор Python-утилит для анализа кода, управления файлами и документации проектов. Эти скрипты помогают разработчикам поддерживать чистые кодовые базы, эффективно объединять файлы и визуализировать структуры проектов.

## Обзор скриптов

### 1. comment_extractor.py

**Назначение**: Автоматическое обнаружение и удаление комментариев в коде с языковой фильтрацией.

**Возможности**:
- Обнаружение комментариев в разных языках (Python, C/C++, Java, JavaScript и др.)
- Фильтрация комментариев по языку (английский, русский и др.)
- Безопасное удаление комментариев с режимом предпросмотра
- Поддержка inline и полнострочных комментариев
- Настройка пользовательских символов комментариев

**Использование**:
```bash
# Базовое обнаружение комментариев в Python файлах
python comment_extractor.py ./src -p "*.py" -l en

# Удаление русских комментариев из C++ файлов рекурсивно
python comment_extractor.py ./project -r -p "*.cpp" -l ru --remove-comments

# Обработка одного файла с кастомными символами комментариев
python comment_extractor.py config.txt -c "#" --remove-comments -o comments.log

# Предпросмотр комментариев без удаления
python comment_extractor.py ./src -p "*.js" -l en
```

**Параметры**:
- `directory`: Директория для поиска или отдельный файл
- `-r, --recursive`: Рекурсивный поиск в поддиректориях
- `-p, --pattern`: Паттерн файлов (например, "*.py", "model_*.cpp")
- `-c, --comment-symbols`: Пользовательские символы комментариев
- `-e, --exclude-pattern`: Паттерн для исключения из комментариев
- `-l, --language`: Код языка для фильтрации комментариев
- `--remove-comments`: Фактически удалять комментарии (по умолчанию: только обнаружение)
- `-o, --log-file`: Файл для логов (по умолчанию: консоль)

**Зависимости**: `pip install langdetect`

---

### 2. merger.py

**Назначение**: Объединение нескольких файлов в один с четкими заголовками и границами файлов.

**Возможности**:
- Объединение явных списков файлов или по паттернам директорий
- Рекурсивный поиск в директориях
- Заголовки файлов с относительными путями
- Режим предпросмотра перед объединением
- Кроссплатформенная обработка путей

**Использование**:
```bash
# Объединение конкретных файлов
python merger.py file1.py file2.js file3.txt -o combined.txt

# Объединение всех Python файлов рекурсивно
python merger.py -d ./src -r -p "*.py" -o all_code.txt

# Предпросмотр того, что будет объединено
python merger.py -d ./docs -p "*.md" --preview

# Объединение с кастомным паттерном
python merger.py -d ./project -p "test_*.py" -o tests_combined.txt
```

**Параметры**:
- `files`: Явный список файлов для объединения
- `-d, --directory`: Директория для поиска файлов
- `-r, --recursive`: Поиск в поддиректориях
- `-p, --pattern`: Паттерн для сопоставления файлов
- `-o, --output`: Выходной файл (по умолчанию: merged_files.txt)
- `--preview`: Предпросмотр без объединения

---

### 3. tree_generater.py

**Назначение**: Генерация деревьев структуры проектов с поддержкой .gitignore (кроссплатформенная альтернатива команде `tree`).

**Возможности**:
- Поддержка паттернов .gitignore
- Кроссплатформенная совместимость
- Фильтрация файлов по паттернам
- Статистика (количество файлов, директорий, общий размер)
- Несколько форматов вывода

**Использование**:
```bash
# Базовое дерево проекта
python tree_generater.py

# Дерево с указанием директории и .gitignore
python tree_generater.py -d ./my_project -i .gitignore -o project_tree.txt

# Только Python файлы
python tree_generater.py -p "*.py"

# Игнорировать правила .gitignore
python tree_generater.py --no-gitignore

# Сложный пример
python tree_generater.py -d ./src -p "*.py" -i ../.gitignore -o python_structure.txt
```

**Параметры**:
- `-d, --directory`: Директория для отображения (по умолчанию: текущая)
- `-i, --gitignore`: Путь к файлу .gitignore
- `-p, --pattern`: Паттерн файлов для включения
- `-o, --output`: Выходной файл для дерева
- `--no-gitignore`: Игнорировать файлы .gitignore

---

## Установка

1. Склонируйте или скачайте скрипты
2. Убедитесь, что установлен Python 3.6+
3. Установите опциональные зависимости:
   ```bash
   pip install langdetect
   ```

## Типичные сценарии использования

### Очистка кода
```bash
python comment_extractor.py ./src -r -p "*.py" -l en --remove-comments
```

### Генерация документации
```bash
python merger.py -d ./src -p "*.py" -o documentation.txt
python tree_generater.py -o project_structure.txt
```

### Анализ проекта
```bash
python tree_generater.py --no-gitignore -o full_structure.txt
python comment_extractor.py ./src -l ru -o russian_comments.log
```

## Примечания

- Все скрипты кроссплатформенные (Windows, Linux, macOS)
- Кодировка файлов обрабатывается автоматически (UTF-8, Latin-1)
- Ошибки прав доступа обрабатываются корректно
- Относительные пути рассчитываются от директории выполнения

---

## Вклад в разработку

Если вы хотите внести свой вклад в развитие утилит, пожалуйста:
1. Сделайте форк репозитория
2. Создайте feature branch
3. Внесите изменения
4. Создайте Pull Request

## Поддержка

Если у вас возникли проблемы или вопросы:
1. Проверьте документацию выше
2. Создайте issue в репозитории проекта
3. Опишите проблему подробно, указав версию Python и ОС
