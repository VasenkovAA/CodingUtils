# Полное руководство по использованию утилиты `tree-generator`

## Содержание
1. [Введение](#введение)
2. [Основные возможности](#основные-возможности)
3. [Установка и запуск](#установка-и-запуск)
4. [Базовое использование](#базовое-использование)
5. [Параметры отображения](#параметры-отображения)
6. [Фильтрация и исключения](#фильтрация-и-исключения)
7. [Использование .gitignore](#использование-gitignore)
8. [Расширенные сценарии](#расширенные-сценарии)
9. [Формат вывода](#формат-вывода)
10. [Примеры использования](#примеры-использования)
11. [Советы и рекомендации](#советы-и-рекомендации)

---

## Введение

`tree-generator` - это мощный кроссплатформенный инструмент для визуализации структуры директорий с поддержкой фильтрации через `.gitignore`. Это расширенная альтернатива команде `tree` с дополнительными возможностями для разработчиков.

**Основное назначение:**
- Визуализация структуры проектов
- Анализ размеров и состава директорий
- Сравнение нескольких проектов
- Создание документации структуры проекта
- Отладка фильтров .gitignore

## Основные возможности

**Визуализация структуры:**
- Древовидное отображение с символами Unicode
- Поддержка множественных корневых директорий
- Контроль глубины рекурсии
- Цветовое кодирование (через терминал)

**Фильтрация и исключения:**
- Полная поддержка `.gitignore` синтаксиса
- Исключение директорий по имени
- Исключение файлов по шаблону
- Исключение по полному пути
- Соответствие фильтрам merger.py

**Статистика и анализ:**
- Подсчет файлов и директорий
- Расчет общего размера
- Статистика исключенных элементов
- Информация о примененных фильтрах

**Гибкий вывод:**
- Вывод в консоль или файл
- Форматирование размеров (B/KB/MB/GB)
- Детальная информация о фильтрации
- Унифицированный синтаксис команд

## Установка и запуск

### Требования
- Python 3.6+
- Стандартные библиотеки Python
- Терминал с поддержкой Unicode (для корректного отображения символов)

### Запуск
```bash
# Базовая форма
tree-generator [опции]

# Проверка установки
tree-generator --help

# Быстрая проверка
tree-generator -d .
```

## Базовое использование

### Простейшие примеры
```bash
# Показать структуру текущей директории
tree-generator

# Показать структуру конкретной директории
tree-generator -d /path/to/project

# Сохранить структуру в файл
tree-generator -d . -o project_structure.txt

# Использовать шаблон фильтрации
tree-generator -p "*.py"
```

### Отображение структуры проекта
```bash
# Полная структура проекта
tree-generator -d ~/projects/myapp

# Только первые два уровня
tree-generator --max-depth 2

# Сравнить две версии проекта
tree-generator -d ~/projects/v1.0 -d ~/projects/v2.0
```

## Параметры отображения

### Основные параметры

| Параметр | Короткая форма | Описание | По умолчанию |
|----------|----------------|----------|--------------|
| `--directory` | `-d` | Директория для отображения | текущая |
| `--pattern` | `-p` | Паттерн включения файлов | `*` |
| `--output` | `-o` | Выходной файл | консоль |
| `--max-depth` | - | Максимальная глубина рекурсии | нет |

### Примеры отображения

```bash
# Ограничить глубину просмотра
tree-generator --max-depth 3

# Показать только Python файлы
tree-generator -p "*.py"

# Показать несколько директорий
tree-generator -d src -d tests -d docs

# Детальный просмотр с сохранением
tree-generator -d . -o tree.txt --max-depth 4
```

### Символы дерева
```
directory/
├── subdirectory/
│   ├── file1.txt
│   └── file2.py
└── another_file.md
```

- `├──` - элемент продолжается
- `└──` - последний элемент
- `│   ` - вертикальная линия продолжения
- `    ` - отступ для последнего элемента

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
tree-generator -ed venv -ed .git -ed __pycache__

# Исключить временные файлы
tree-generator -en "*.tmp" -en "*.bak" -en "*.swp"

# Исключить тестовые файлы
tree-generator -ep "*test*" -ep "*spec.*"

# Комбинированная фильтрация
tree-generator \
  -ed node_modules \
  -ed dist \
  -en "*.log" \
  -ep "*_old*" \
  -ep "*debug*"
```

### Паттерны фильтрации

#### Для `--exclude-name` (`-en`):
```bash
# Точное имя файла
-en "package-lock.json"

# Шаблоны с *
-en "*.pyc"          # Все .pyc файлы
-en "temp_*"         # Файлы, начинающиеся с temp_
-en "*_backup"       # Файлы, заканчивающиеся на _backup
-en "file?.txt"      # file1.txt, file2.txt и т.д.
```

#### Для `--exclude-pattern` (`-ep`):
```bash
# Путь целиком
-ep "docs/old/*"     # Все в docs/old/
-ep "*/.idea/*"      # Директории .idea в любом месте
-ep "src/*test*"     # Все test файлы в src/
```

## Использование .gitignore

### Флаги .gitignore

| Флаг | Короткая форма | Описание |
|------|----------------|----------|
| `--gitignore` | `-i` | Использовать указанный .gitignore файл |
| `--use-gitignore` | `-ig` | Автоматически найти .gitignore |
| `--no-gitignore` | - | Игнорировать .gitignore файлы |

### Поддерживаемые синтаксисы .gitignore
```
# Комментарии
*.pyc                    # Все .pyc файлы
__pycache__/             # Директория и всё внутри
**/temp/                 # Любые temp директории
!important.py            # Исключение из исключения
build/                   # Директория build
*.log                    # Все логи
.DS_Store                # Конкретный файл
```

### Примеры использования .gitignore

```bash
# Использовать стандартный .gitignore
tree-generator -ig

# Указать конкретный .gitignore файл
tree-generator -i /path/to/.gitignore

# Игнорировать .gitignore полностью
tree-generator --no-gitignore

# Комбинировать с другими фильтрами
tree-generator -ig -ed build -en "*.log"
```

### Приоритет фильтрации
1. `.gitignore` фильтры (если включены)
2. `--exclude-dir` (исключение директорий)
3. `--exclude-name` (исключение по имени файла)
4. `--exclude-pattern` (исключение по полному пути)
5. `--pattern` (паттерн включения)

## Расширенные сценарии

### Сравнение проектов
```bash
# Сравнить две версии проекта
tree-generator -d old_version -d new_version -o comparison.txt

# Сравнить с фильтрами
tree-generator \
  -d project_a \
  -d project_b \
  -ig \
  -ed node_modules \
  -en "*.log" \
  --max-depth 4
```

### Документирование структуры
```bash
# Создать документацию структуры проекта
tree-generator -d . -ig -o PROJECT_STRUCTURE.md

# Создать легковесный обзор
tree-generator \
  --max-depth 2 \
  -ed ".*" \
  -en "*" \
  -o overview.txt
```

### Отладка .gitignore
```bash
# Проверить, какие файлы игнорируются
tree-generator -ig --no-gitignore | head -20
tree-generator -ig | head -20

# Сравнить с и без .gitignore
tree-generator -d . --no-gitignore -o full_tree.txt
tree-generator -d . -ig -o filtered_tree.txt
diff full_tree.txt filtered_tree.txt
```

### Анализ размеров проекта
```bash
# Анализ распределения файлов
tree-generator -d . -p "*.py"
tree-generator -d . -p "*.js"
tree-generator -d . -p "*.html"

# Найти крупные директории
tree-generator -d . --max-depth 1
```

## Формат вывода

### Структура вывода
```
Project Tree: /absolute/path/to/project
Pattern: *.py
.gitignore: Auto-discovered and applied
Exclusions applied:
  Directories: venv, node_modules
  Names: *.log, *.tmp
============================================================
project/
├── src/
│   ├── main.py
│   └── utils.py
├── tests/
│   └── test_main.py
└── README.md
============================================================
Statistics:
  Directories: 3
  Files: 4
  Excluded items: 15
  Total Size: 45.67 KB
  Max Depth: 3
```

### Статистика в выводе
- **Directories**: Количество отображенных директорий
- **Files**: Количество отображенных файлов
- **Excluded items**: Сколько элементов было исключено фильтрами
- **Total Size**: Общий размер всех файлов в удобном формате
- **Max Depth**: Максимальная глубина рекурсии (если указана)

### Множественные директории
При указании нескольких директорий с помощью `-d`:
```
COMBINED VIEW/
├── project_a/
│   ├── src/
│   └── tests/
└── project_b/
    ├── lib/
    └── docs/
```

## Примеры использования

### Пример 1: Быстрый обзор проекта
```bash
# Получить общее представление о проекте
tree-generator --max-depth 2 -ig
```

**Вывод:**
```
Project Tree: /home/user/projects/myapp
Pattern: *
.gitignore: Auto-discovered and applied
============================================================
myapp/
├── src/
│   ├── components/
│   ├── utils/
│   └── main.py
├── tests/
├── docs/
├── requirements.txt
└── README.md
============================================================
Statistics:
  Directories: 5
  Files: 3
  Excluded items: 42
  Total Size: 1.24 MB
```

### Пример 2: Анализ исходного кода
```bash
tree-generator -d . \
  -p "*.py" \
  -ed "__pycache__" \
  -ed "venv" \
  -en "*.pyc" \
  --max-depth 4 \
  -o python_structure.txt
```

### Пример 3: Сравнение конфигураций
```bash
# Сравнить конфиги разных сред
tree-generator \
  -d config/development \
  -d config/production \
  -d config/staging \
  -p "*.json" \
  -p "*.yaml" \
  -p "*.env*" \
  -o config_comparison.txt
```

### Пример 4: Мониторинг логов
```bash
# Структура логов приложения
tree-generator -d /var/log/myapp \
  -p "*.log" \
  --max-depth 1 \
  -o logs_structure_$(date +%Y%m%d).txt
```

### Пример 5: Документирование проекта для README
```bash
# Создать секцию структуры проекта для README
echo "# Project Structure" > README.md
echo "\`\`\`" >> README.md
tree-generator -d . --max-depth 3 -ig >> README.md
echo "\`\`\`" >> README.md
```

### Совместное использование:
```bash
# Сначала просмотреть структуру
tree-generator -d . -ig --max-depth 2

# Затем объединить выбранные файлы
file-merger -d src -r -p "*.py" -ig -o source_code.txt
```

## Советы и рекомендации

### Производительность
1. **Используйте `--max-depth`** для больших проектов:
   ```bash
   # Быстрый просмотр
   tree-generator --max-depth 2

   # Полный анализ
   tree-generator --max-depth 5
   ```

2. **Исключайте тяжелые директории**:
   ```bash
   tree-generator -ed node_modules -ed .git -ed venv
   ```

3. **Используйте конкретные паттерны**:
   ```bash
   # Вместо
   tree-generator

   # Используйте
   tree-generator -p "*.py" -p "*.js" -p "*.html"
   ```

### Интеграция с другими инструментами

#### Скрипты оболочки:
```bash
#!/bin/bash
# generate_project_report.sh
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
tree-generator -d . -ig -o "structure_${TIMESTAMP}.txt"
file-merger d . -r -ig -o "code_${TIMESTAMP}.txt"
```

#### Makefile:
```makefile
.PHONY: docs
docs:
	tree-generator -d . -ig -o STRUCTURE.md
	file-merger -d src -r -p "*.py" -o SOURCE.md

.PHONY: clean-view
clean-view:
	tree-generator -d . \
		-ed "venv" \
		-ed "__pycache__" \
		-en "*.pyc" \
		--max-depth 3
```

#### Git hooks:
```bash
# .git/hooks/post-commit
tree-generator -d . -ig -o ".git/project_structure_$(git rev-parse --short HEAD).txt"
```

### Отладка и решение проблем

#### Проблема: "Permission Denied"
```bash
# Игнорировать ошибки доступа
tree-generator 2>/dev/null | grep -v "Permission Denied"

# Или исключить системные директории
tree-generator -ed ".*" -ed "system_*"
```

#### Проблема: Слишком большой вывод
```bash
# Ограничить вывод
tree-generator --max-depth 2 | head -50

# Сохранить в файл и просмотреть позже
tree-generator -o output.txt
less output.txt
```

#### Проблема: Некорректные символы
```bash
# Использовать ASCII символы
tree-generator 2>&1 | sed 's/├──/|--/g; s/└──/`--/g; s/│/|/g'
```

### Лучшие практики

1. **Всегда используйте `.gitignore`** для стандартных исключений:
   ```bash
   tree-generator -ig
   ```

2. **Сохраняйте команды** как скрипты для повторного использования:
   ```bash
   # save_structure.sh
   tree-generator -d . -ig -o "structure_$(date +%Y%m%d).txt"
   ```

3. **Используйте относительные пути** для переносимости:
   ```bash
   tree-generator -d ./src
   ```

4. **Комбинируйте с другими инструментами**:
   ```bash
   # Подсчет строк кода после просмотра структуры
   tree-generator -d src -p "*.py"
   find src -name "*.py" | xargs wc -l
   ```

5. **Версионируйте вывод** с датами:
   ```bash
   tree-generator -d . -ig -o "snapshot_$(date +%Y%m%d_%H%M%S).txt"
   ```

### Расширенные комбинации фильтров

```bash
# Просмотр только исходного кода
tree-generator \
  -d . \
  -p "*.py" \
  -p "*.js" \
  -p "*.ts" \
  -p "*.java" \
  -p "*.cpp" \
  -p "*.c" \
  -ed "venv" \
  -ed "node_modules" \
  -ed "__pycache__" \
  -ed "target" \
  -en "*.min.js" \
  -en "*.min.css" \
  --max-depth 4
```
