# Code Analysis and Documentation Tools

Набор Python-утилит для анализа кодовой базы, извлечения комментариев и визуализации структуры проектов.

## 📦 Установка

Установите пакеты напрямую с GitHub через pip:

```bash
pip install git+https://github.com/VasenkovAA/CodingUtils.git
```

**Требования:**
- Python 3.6+
- Терминал с поддержкой Unicode (для tree-generator)

## 🛠️ Доступные инструменты

### 1. **file-merger** - Объединение файлов
Мощная утилита для объединения содержимого нескольких файлов в один с сохранением структуры.

```bash
# Базовое использование
file-merger -o merged.txt

# Объединение всех Python файлов
file-merger -p "*.py" -r -o python_code.txt

# Создание архива проекта с фильтрацией
file-merger -r -ig -ed venv -ed node_modules -o project_archive.txt
```

**Основные возможности:**
- Рекурсивный поиск файлов по шаблонам
- Поддержка .gitignore файлов
- Фильтрация и исключение директорий/файлов
- Предварительный просмотр
- Обработка ошибок кодировки

### 2. **comment-extractor** - Извлечение комментариев
Инструмент для извлечения, фильтрации и анализа комментариев в исходном коде.

```bash
# Извлечение всех комментариев
comment-extractor -d src -r --export-comments comments.txt

# Фильтрация по языку
comment-extractor -d . -r -l "en" --export-comments english_comments.txt

# Очистка кода от комментариев
comment-extractor -d . -r --remove-comments
```

**Основные возможности:**
- Поддержка 15+ языков программирования
- Определение языка комментариев (через langdetect)
- Фильтрация по языку, шаблонам, ключевым словам
- Удаление комментариев с сохранением кода
- Интеграция с .gitignore

### 3. **tree-generator** - Визуализация структуры
Расширенная альтернатива команде `tree` с поддержкой фильтрации через .gitignore.

```bash
# Визуализация структуры проекта
tree-generator -d . -ig

# Сохранение в файл с ограничением глубины
tree-generator -d . --max-depth 3 -o structure.txt

# Сравнение двух проектов
tree-generator -d old_version -d new_version -o comparison.txt
```

**Основные возможности:**
- Древовидное отображение с Unicode символами
- Полная поддержка .gitignore синтаксиса
- Статистика по размерам и количеству файлов
- Цветовое кодирование в терминале
- Сравнение нескольких директорий


## 🔧 Интеграция и автоматизация

### Makefile
```makefile
.PHONY: docs
docs:
    tree-generator -d . -ig -o STRUCTURE.md
    file-merger -d src -r -p "*.py" -o SOURCE.md
    comment-extractor -d src -r --export-comments COMMENTS.md

.PHONY: audit
audit:
    comment-extractor -d . -r --export-comments audit_$(shell date +%Y%m%d).txt
    tree-generator -d . -ig -o structure_$(shell date +%Y%m%d).txt
```

### CI/CD пайплайны
```yaml
# .gitlab-ci.yml или .github/workflows/ci.yml
analyze:
  stage: test
  script:
    - comment-extractor -d src -r --export-comments comments_report.txt
    - tree-generator -d . -ig -o project_structure.txt
    - file-merger -d src -r -p "*.py" -p "*.js" -o code_snapshot.txt
  artifacts:
    paths:
      - comments_report.txt
      - project_structure.txt
      - code_snapshot.txt
```

### Скрипт для автоматического анализа
```bash
#!/bin/bash
# analyze_project.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PROJECT_NAME=$(basename "$PWD")

echo "Анализ проекта: $PROJECT_NAME"

# 1. Структура проекта
echo "Генерация структуры проекта..."
tree-generator -d . -ig -o "${PROJECT_NAME}_structure_${TIMESTAMP}.txt"

# 2. Снимок исходного кода
echo "Создание снимка кода..."
file-merger -d src -r -ig -o "${PROJECT_NAME}_code_${TIMESTAMP}.txt"

# 3. Анализ комментариев
echo "Анализ комментариев..."
comment-extractor -d src -r --export-comments "${PROJECT_NAME}_comments_${TIMESTAMP}.txt"

echo "Анализ завершен. Файлы сохранены с меткой $TIMESTAMP"
```

## 🚀 Примеры использования

### Сценарий 1: Документирование проекта
```bash
# Создать полную документацию проекта
tree-generator -d . -ig -o PROJECT_STRUCTURE.md
file-merger -d src -r -p "*.py" -p "*.js" -o SOURCE_CODE.md
comment-extractor -d src -r -l "en" --export-comments DOCUMENTATION_COMMENTS.md
```

### Сценарий 2: Очистка кода перед релизом
```bash
# Удалить все комментарии из исходного кода
comment-extractor -d src -r --remove-comments

# Создать архив чистого кода
file-merger -d src -r -o clean_code_$(date +%Y%m%d).txt

# Проверить структуру после очистки
tree-generator -d src -ig
```

### Сценарий 3: Сравнение версий проекта
```bash
# Сравнить структуру стабильной и dev версий
tree-generator -d stable -d dev -o version_comparison.txt

# Сравнить комментарии в двух ветках
comment-extractor -d stable -r --export-comments stable_comments.txt
comment-extractor -d dev -r --export-comments dev_comments.txt
diff stable_comments.txt dev_comments.txt
```

## 🔍 Советы и рекомендации

### Производительность
```bash
# Для больших проектов используйте ограничения
tree-generator --max-depth 3
file-merger -p "*.py" -p "*.js"  # конкретные расширения
comment-extractor -l "en"        # только один язык
```

### Безопасность
```bash
# Исключайте конфиденциальные файлы
file-merger -en "*.env" -en "*secret*" -en "*password*"
comment-extractor -e "password" -e "secret" -e "token"
```

### Совместное использование
```bash
# 1. Сначала посмотреть структуру
tree-generator -d . -ig --max-depth 2

# 2. Затем извлечь комментарии для анализа
comment-extractor -d src -r --export-comments comments_to_review.txt

# 3. Объединить важные файлы
file-merger -d src -r -p "*.py" -p "*.js" -o core_code.txt
```