
"""
anonymizer — поиск и обезличивание конфиденциальной информации в текстовых файлах и Jupyter Notebooks.

Особенности:
- Встроенные правила для разных типов секретов (ключи API, пароли, PII, системные данные)
- Загрузка пользовательских правил из YAML/JSON
- Поиск строк из .env файлов
- Динамическая подстановка системных данных (имя пользователя, домашняя папка, имя хоста)
- Поддержка Jupyter Notebook (включая выводы ячеек)
- Режимы замены: замена на плейсхолдер, удаление строки, хеширование
- Preview режим (--preview) показывает, что будет изменено, без изменения файлов
- Экспорт отчёта о найденных совпадениях
- Интеграция с common_utils: фильтрация файлов, .gitignore, прогресс, резервное копирование, split-streams
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shlex
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from codingutils.common_utils import (
    FilterConfig,
    FileContentDetector,
    FileSystemWalker,
    FileType,
    GitIgnoreParser,
    ProgressReporter,
    get_relative_path,
    safe_write,
)

logger = logging.getLogger(__name__)
OUTPUT_LOGGER_NAME = "codingutils.anonymizer.output"






@dataclass
class AnonymizerMatch:
    """Одно найденное совпадение в файле."""
    file: Path
    relative_path: str
    rule_name: str
    matched_text: str
    replacement_text: Optional[str]
    line: int
    column: int
    confidence: str = "medium"
    cell_index: Optional[int] = None
    field: Optional[str] = None


@dataclass
class AnonymizerRule:
    """
    Правило поиска и замены.

    :param name: уникальное имя правила
    :param pattern: регулярное выражение (строка)
    :param replacement: строка замены (может содержать обратные ссылки \1, \2). Если None,
                        используется глобальный replacement из конфига.
    :param mode: режим обработки (replace, remove-line, hash). Если None, берётся глобальный.
    :param case_sensitive: учитывать регистр
    :param whole_word: искать как целое слово (добавляет границы \b)
    :param scope: список расширений файлов, к которым применяется правило (например, [".py", ".ipynb"]).
                  Пустой список означает все файлы.
    :param confidence: уровень доверия ("high", "medium", "low")
    :param enabled: активно ли правило
    """
    name: str
    pattern: str
    replacement: Optional[str] = None
    mode: Optional[str] = None
    case_sensitive: bool = True
    whole_word: bool = False
    scope: List[str] = field(default_factory=list)
    confidence: str = "medium"
    enabled: bool = True

    def __post_init__(self):
        if self.whole_word and not self.pattern.startswith(r"\b") and not self.pattern.endswith(r"\b"):
            self.pattern = r"\b" + self.pattern + r"\b"
        flags = 0 if self.case_sensitive else re.IGNORECASE
        try:
            self._compiled = re.compile(self.pattern, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex in rule '{self.name}': {e}") from e

    def compile(self) -> re.Pattern:
        return self._compiled


@dataclass
class AnonymizerConfig(FilterConfig):
    """Конфигурация анонимайзера."""


    builtin_rules: Set[str] = field(default_factory=set)
    rules_file: Optional[Path] = None
    env_files: List[Path] = field(default_factory=list)


    mode: str = "replace"
    replacement: str = "[REDACTED]"
    apply: bool = False
    preview_mode: bool = False


    scan_notebooks: bool = True
    scan_outputs: bool = True
    scan_metadata: bool = False


    detect_system_info: bool = True
    username_placeholder: str = "[USER]"
    home_placeholder: str = "[HOME]"
    hostname_placeholder: str = "[HOST]"
    project_root_placeholder: str = "[PROJECT_ROOT]"


    export_matches: Optional[Path] = None
    log_file: Optional[Path] = None
    use_cache: bool = True
    keep_backups: bool = False
    backup_dir: Optional[Path] = None
    overwrite_backups: bool = False
    split_streams: bool = False


    directory_recursion: Dict[Path, bool] = field(default_factory=dict)

    def __post_init__(self):
        FilterConfig.__post_init__(self)
        if self.backup_dir is not None:
            self.keep_backups = True
            self.backup_dir = Path(self.backup_dir).resolve()
        if self.directory_recursion:
            normalized = {}
            for k, v in self.directory_recursion.items():
                try:
                    normalized[Path(k).resolve()] = bool(v)
                except Exception:
                    normalized[Path(k)] = bool(v)
            self.directory_recursion = normalized






def load_builtin_rules(groups: Set[str]) -> List[AnonymizerRule]:
    """
    Возвращает список встроенных правил для указанных групп.
    Группы: credentials, pii, system, all (все группы).
    """

    all_rules = []


    cred_rules = [
        AnonymizerRule(
            name="AWS Access Key",
            pattern=r"AKIA[0-9A-Z]{16}",
            replacement="[AWS_KEY]",
            confidence="high",
        ),
        AnonymizerRule(
            name="OpenAI API Key",
            pattern=r"sk-[a-zA-Z0-9]{48}",
            replacement="[OPENAI_KEY]",
            confidence="high",
        ),
        AnonymizerRule(
            name="GitHub Token",
            pattern=r"ghp_[a-zA-Z0-9]{36}",
            replacement="[GITHUB_TOKEN]",
            confidence="high",
        ),
        AnonymizerRule(
            name="Slack Token",
            pattern=r"xox[baprs]-[0-9]{12,13}-[a-zA-Z0-9]{24}",
            replacement="[SLACK_TOKEN]",
            confidence="high",
        ),
        AnonymizerRule(
            name="JWT Token",
            pattern=r"[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+",
            replacement="[JWT]",
            confidence="high",
        ),
        AnonymizerRule(
            name="Password in code",
            pattern=r"(password|passwd|pwd)\s*[:=]\s*['\"]?(\w+)['\"]?",
            replacement=r"\1=[REDACTED]",
            case_sensitive=False,
            confidence="high",
        ),
        AnonymizerRule(
            name="Connection string",
            pattern=r"(postgresql|mysql|mongodb|redis)://[^@]+@",
            replacement=r"\1://[USER:REDACTED]@",
            case_sensitive=False,
            confidence="high",
        ),
        AnonymizerRule(
            name="Private key block",
            pattern=r"-----BEGIN (RSA|OPENSSH|DSA|EC) PRIVATE KEY-----",
            replacement="[PRIVATE_KEY_BLOCK]",
            confidence="high",
        ),
    ]
    all_rules.extend(cred_rules)


    pii_rules = [
        AnonymizerRule(
            name="Email address",
            pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            replacement="[EMAIL]",
            confidence="medium",
        ),
        AnonymizerRule(
            name="Phone number",
            pattern=r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}",
            replacement="[PHONE]",
            confidence="medium",
        ),
        AnonymizerRule(
            name="IPv4 address",
            pattern=r"\b(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
            replacement="[IP_ADDRESS]",
            confidence="medium",
        ),
        AnonymizerRule(
            name="Local IP (RFC 1918)",
            pattern=r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b",
            replacement="[LOCAL_IP]",
            confidence="high",
        ),
    ]
    all_rules.extend(pii_rules)



    system_rules = [
        AnonymizerRule(
            name="Windows user profile path",
            pattern=r"C:\\Users\\[^\\]+",
            replacement="C:\\Users\\[USER]",
            case_sensitive=False,
            confidence="high",
        ),
    ]
    all_rules.extend(system_rules)


    if "all" in groups:
        return all_rules

    selected = []
    if "credentials" in groups:
        selected.extend(cred_rules)
    if "pii" in groups:
        selected.extend(pii_rules)
    if "system" in groups:
        selected.extend(system_rules)
    return selected


def load_rules_from_file(path: Path) -> List[AnonymizerRule]:
    """Загружает правила из YAML или JSON файла."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif suffix in (".yaml", ".yml"):
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML is required to load YAML rules. Install with: pip install pyyaml")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    else:
        raise ValueError(f"Unsupported rules file format: {suffix}. Use .json or .yaml/.yml")

    rules = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue

            if "pattern" not in item or "name" not in item:
                logger.warning("Skipping rule item missing 'name' or 'pattern': %s", item)
                continue
            rule = AnonymizerRule(
                name=item["name"],
                pattern=item["pattern"],
                replacement=item.get("replacement"),
                mode=item.get("mode"),
                case_sensitive=item.get("case_sensitive", True),
                whole_word=item.get("whole_word", False),
                scope=item.get("scope", []),
                confidence=item.get("confidence", "medium"),
                enabled=item.get("enabled", True),
            )
            rules.append(rule)
    return rules


def load_env_rules(env_files: List[Path], mode: str = "exact") -> List[AnonymizerRule]:
    """
    Создаёт правила для поиска значений переменных из .env файлов.
    Если mode = "exact", ищет точное совпадение значения (с учётом кавычек).
    Если mode = "substring", ищет вхождение значения как подстроки (может давать много ложных срабатываний).
    """
    rules = []
    values: Set[str] = set()

    for env_file in env_files:
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    val = val.strip()

                    if val and val[0] in ('"', "'") and val[-1] == val[0]:
                        val = val[1:-1]
                    if val:
                        values.add(val)
        except Exception as e:
            logger.error("Failed to read env file %s: %s", env_file, e)

    for idx, val in enumerate(values):

        escaped = re.escape(val)
        if mode == "exact":

            pattern = r"(?<![a-zA-Z0-9_])" + escaped + r"(?![a-zA-Z0-9_])"
        else:
            pattern = escaped
        rules.append(AnonymizerRule(
            name=f".env_value_{idx}",
            pattern=pattern,
            replacement="[ENV_SECRET]",
            confidence="high",
        ))
    return rules


def create_dynamic_system_rules(config: AnonymizerConfig) -> List[AnonymizerRule]:
    """
    Создаёт правила на основе текущей системы: имя пользователя, домашняя папка, имя хоста.
    """
    rules = []
    try:
        username = os.getlogin()
    except Exception:
        username = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if username and config.username_placeholder:


        rules.append(AnonymizerRule(
            name="system_username",
            pattern=r"\b" + re.escape(username) + r"\b",
            replacement=config.username_placeholder,
            confidence="high",
        ))

    home = str(Path.home())
    if home and config.home_placeholder:




        if os.name == "nt":
            home_escaped = re.escape(home).replace("\\\\", "\\\\")
            pattern = home_escaped + r"(?:\\|$)"
        else:
            home_escaped = re.escape(home)
            pattern = home_escaped + r"(?:/|$)"
        rules.append(AnonymizerRule(
            name="system_home",
            pattern=pattern,
            replacement=config.home_placeholder,
            confidence="high",
        ))

    hostname = socket.gethostname()
    if hostname and config.hostname_placeholder:
        rules.append(AnonymizerRule(
            name="system_hostname",
            pattern=r"\b" + re.escape(hostname) + r"\b",
            replacement=config.hostname_placeholder,
            confidence="high",
        ))


    if config.directories and config.project_root_placeholder:
        root = Path(config.directories[0]).resolve()
        root_str = str(root)

        if os.name == "nt":
            root_escaped = re.escape(root_str).replace("\\\\", "\\\\")
            pattern = root_escaped + r"(?:\\|$)"
        else:
            root_escaped = re.escape(root_str)
            pattern = root_escaped + r"(?:/|$)"
        rules.append(AnonymizerRule(
            name="system_project_root",
            pattern=pattern,
            replacement=config.project_root_placeholder,
            confidence="high",
        ))

    return rules






class AnonymizerScanner:
    """
    Применяет список правил к строкам текста.
    Возвращает изменённые строки и список совпадений.
    """

    def __init__(
        self,
        rules: List[AnonymizerRule],
        global_mode: str,
        global_replacement: str,
    ):
        self.rules = [r for r in rules if r.enabled]
        self.global_mode = global_mode
        self.global_replacement = global_replacement

    def scan_lines(
        self,
        lines: Iterable[str],
        *,
        file_path: Path,
        cell_index: Optional[int] = None,
        field: Optional[str] = None,
    ) -> Tuple[List[str], List[AnonymizerMatch]]:
        """
        Обрабатывает итератор строк, возвращает новые строки и список совпадений.
        """
        new_lines: List[str] = []
        matches: List[AnonymizerMatch] = []
        relative = get_relative_path(file_path)

        for line_no, raw_line in enumerate(lines, 1):

            nl = "\n" if raw_line.endswith("\n") else ""
            line = raw_line[:-1] if nl else raw_line


            current_line = line
            applied_in_line = False

            for rule in self.rules:

                if rule.scope and file_path.suffix.lower() not in rule.scope:
                    continue

                compiled = rule.compile()

                for m in compiled.finditer(current_line):
                    matched_text = m.group(0)

                    mode = rule.mode or self.global_mode
                    replacement = rule.replacement if rule.replacement is not None else self.global_replacement

                    if mode == "replace":

                        new_part = m.expand(replacement)

                        start, end = m.span()
                        current_line = current_line[:start] + new_part + current_line[end:]
                        replacement_text = new_part
                    elif mode == "remove-line":

                        matches.append(AnonymizerMatch(
                            file=file_path,
                            relative_path=relative,
                            rule_name=rule.name,
                            matched_text=matched_text,
                            replacement_text=None,
                            line=line_no,
                            column=m.start(),
                            confidence=rule.confidence,
                            cell_index=cell_index,
                            field=field,
                        ))
                        applied_in_line = True
                        replacement_text = None
                        break
                    elif mode == "hash":

                        h = hashlib.sha256(matched_text.encode("utf-8")).hexdigest()[:8]
                        replacement_text = f"[HASH:{h}]"
                        start, end = m.span()
                        current_line = current_line[:start] + replacement_text + current_line[end:]
                    else:

                        continue


                    if mode != "remove-line":
                        matches.append(AnonymizerMatch(
                            file=file_path,
                            relative_path=relative,
                            rule_name=rule.name,
                            matched_text=matched_text,
                            replacement_text=replacement_text,
                            line=line_no,
                            column=m.start(),
                            confidence=rule.confidence,
                            cell_index=cell_index,
                            field=field,
                        ))

                if applied_in_line:
                    break

            if applied_in_line:

                continue
            else:
                new_lines.append(current_line + nl)

        return new_lines, matches






class AnonymizerProcessor:
    def __init__(self, config: AnonymizerConfig) -> None:
        self.config = config
        self.file_walker = self._create_walker()
        self._cache: Optional[Dict[str, Tuple[float, Tuple[List[AnonymizerMatch], bool]]]] = (
            {} if config.use_cache else None
        )
        self.out_logger = logging.getLogger(OUTPUT_LOGGER_NAME)


        self.rules = self._collect_rules()

    def _create_walker(self) -> FileSystemWalker:
        parser: Optional[GitIgnoreParser] = None
        if self.config.use_gitignore or self.config.custom_gitignore:
            root_dir = Path(self.config.directories[0]).resolve() if self.config.directories else Path.cwd().resolve()
            parser = GitIgnoreParser(root_dir=root_dir)
            if self.config.custom_gitignore:
                parser.load_from_file(self.config.custom_gitignore)
            else:
                parser.load_from_file()
        return FileSystemWalker(self.config, parser)

    def _collect_rules(self) -> List[AnonymizerRule]:
        rules = []

        if self.config.builtin_rules:
            rules.extend(load_builtin_rules(self.config.builtin_rules))

        if self.config.rules_file:
            try:
                rules.extend(load_rules_from_file(self.config.rules_file))
            except Exception as e:
                logger.error("Failed to load rules from %s: %s", self.config.rules_file, e)

        if self.config.env_files:
            rules.extend(load_env_rules(self.config.env_files))

        if self.config.detect_system_info:
            rules.extend(create_dynamic_system_rules(self.config))
        return rules

    def find_files(self) -> List[Path]:
        roots = [Path(d).resolve() for d in (self.config.directories or ["."])]

        if self.config.directory_recursion:
            rec_map = {k.resolve(): v for k, v in self.config.directory_recursion.items()}
            files = self.file_walker.find_files(roots, recursive=rec_map)
        else:
            files = self.file_walker.find_files(roots, recursive=self.config.recursive)


        if not self.config.scan_notebooks:
            files = [f for f in files if f.suffix.lower() != ".ipynb"]

        logger.info("Found %d files to process", len(files))
        return files

    def process_files(self) -> Dict[str, Any]:
        files = self.find_files()
        if not files:
            logger.warning("No files found matching criteria")
            return {"total_files": 0, "total_matches": 0, "modified_files": 0, "matches": []}

        self._log_configuration()

        all_matches: List[AnonymizerMatch] = []
        modified_files = 0

        progress_stream = sys.stderr if self.config.split_streams else sys.stdout

        with ProgressReporter(total=len(files), description="Scanning files", stream=progress_stream) as progress:
            for p in files:
                try:
                    file_matches, modified = self.process_file(p)
                    all_matches.extend(file_matches)
                    if modified:
                        modified_files += 1
                except Exception as e:
                    logger.error("Failed to process %s: %s", p, e)
                progress.update(1)


        if self.config.preview_mode and all_matches:
            self._print_preview(all_matches)

        self._log_summary(len(all_matches), modified_files, len(files))

        if self.config.export_matches and all_matches:
            self._export_matches(all_matches, self.config.export_matches)

        return {
            "total_files": len(files),
            "total_matches": len(all_matches),
            "modified_files": modified_files,
            "matches": [self._match_to_dict(m) for m in all_matches],
        }

    def _print_preview(self, matches: List[AnonymizerMatch]) -> None:
        """Выводит предпросмотр изменений в читаемом формате."""
        out_stream = sys.stdout if self.config.split_streams else sys.stderr
        out_stream.write("\n" + "=" * 60 + "\n")
        out_stream.write("PREVIEW OF CHANGES (no files will be modified)\n")
        out_stream.write("=" * 60 + "\n")

        for m in sorted(matches, key=lambda x: (x.relative_path, x.line, x.column)):

            location = m.relative_path
            if m.cell_index is not None:
                location += f" [cell {m.cell_index}]"
            if m.field and m.field != "source":
                location += f" ({m.field})"

            line_info = f"{location}:{m.line}:{m.column}"


            if m.replacement_text is None:

                change = f"'{m.matched_text}' → [LINE REMOVED]"
            else:
                change = f"'{m.matched_text}' → '{m.replacement_text}'"

            out_stream.write(f"  {line_info}  {change}\n")

        out_stream.write("=" * 60 + "\n")
        out_stream.flush()

    def process_file(self, file_path: Path) -> Tuple[List[AnonymizerMatch], bool]:
        """Возвращает (список совпадений, был ли файл изменён)."""

        cache_key = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
        except Exception:
            mtime = -1.0

        if self._cache is not None and cache_key in self._cache:
            cached_mtime, cached_result = self._cache[cache_key]
            if cached_mtime == mtime:
                return cached_result


        if file_path.suffix.lower() == ".ipynb":
            matches, modified = self._process_ipynb_file(file_path)
        else:
            if FileContentDetector.detect_file_type(file_path) != FileType.TEXT:
                logger.debug("Skipping non-text file: %s", file_path)
                return [], False
            matches, modified = self._process_text_file(file_path)

        result = (matches, modified)
        if self._cache is not None:
            self._cache[cache_key] = (mtime, result)
        return result

    def _process_text_file(self, file_path: Path) -> Tuple[List[AnonymizerMatch], bool]:
        """Обработка обычного текстового файла."""
        encoding = FileContentDetector.detect_encoding(file_path)
        try:
            with open(file_path, "r", encoding=encoding, errors="strict") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            logger.warning("Decoding failed with %s for %s, falling back to latin-1", encoding, file_path)
            encoding = "latin-1"
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()

        scanner = AnonymizerScanner(self.rules, self.config.mode, self.config.replacement)
        new_lines, matches = scanner.scan_lines(lines, file_path=file_path)

        modified = False

        if matches and self.config.apply and not self.config.preview_mode:
            backup_path = None
            try:
                if self.config.keep_backups:
                    backup_path = self._create_persistent_backup(file_path)

                ok = safe_write(
                    file_path,
                    "".join(new_lines),
                    encoding=encoding,
                    backup=False,
                )
                if not ok:
                    raise RuntimeError(f"Failed to write updated file: {file_path}")
                modified = True
                logger.info("Modified %s", file_path)
            except Exception as e:
                logger.error("Error writing file %s: %s", file_path, e)

                if backup_path and backup_path.exists():
                    try:
                        import shutil
                        shutil.copy2(backup_path, file_path)
                    except Exception:
                        pass
                raise
        elif matches and self.config.preview_mode:

            logger.debug("Preview mode – would modify %s", file_path)
            modified = False
        else:

            modified = False

        return matches, modified

    def _process_ipynb_file(self, file_path: Path) -> Tuple[List[AnonymizerMatch], bool]:
        """Обработка Jupyter Notebook."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                nb = json.load(f)
        except Exception as e:
            logger.error("Failed to read notebook %s: %s", file_path, e)
            return [], False

        scanner = AnonymizerScanner(self.rules, self.config.mode, self.config.replacement)
        all_matches: List[AnonymizerMatch] = []
        modified = False

        cells = nb.get("cells", [])
        for cell_idx, cell in enumerate(cells):

            source = cell.get("source", [])
            if isinstance(source, str):
                source_lines = source.splitlines(keepends=True)
            elif isinstance(source, list):
                source_lines = [s if s.endswith("\n") else s + "\n" for s in source if isinstance(s, str)]
            else:
                source_lines = []

            if source_lines:
                new_source_lines, source_matches = scanner.scan_lines(
                    source_lines,
                    file_path=file_path,
                    cell_index=cell_idx,
                    field="source",
                )
                all_matches.extend(source_matches)
                if source_matches and self.config.apply and not self.config.preview_mode:
                    if isinstance(source, str):
                        cell["source"] = "".join(new_source_lines)
                    else:
                        cell["source"] = new_source_lines
                    modified = True


            if self.config.scan_outputs:
                outputs = cell.get("outputs", [])
                for out_idx, out in enumerate(outputs):

                    for field_name in ("text", "html", "markdown", "latex", "traceback"):
                        if field_name in out:
                            val = out[field_name]
                            if isinstance(val, list):
                                lines = [s if s.endswith("\n") else s + "\n" for s in val if isinstance(s, str)]
                            elif isinstance(val, str):
                                lines = val.splitlines(keepends=True)
                            else:
                                continue

                            new_lines, out_matches = scanner.scan_lines(
                                lines,
                                file_path=file_path,
                                cell_index=cell_idx,
                                field=field_name,
                            )
                            all_matches.extend(out_matches)
                            if out_matches and self.config.apply and not self.config.preview_mode:
                                if isinstance(val, list):
                                    out[field_name] = new_lines
                                else:
                                    out[field_name] = "".join(new_lines)
                                modified = True


                    if "data" in out and isinstance(out["data"], dict):
                        for mime, content in out["data"].items():
                            if not isinstance(content, (str, list)):
                                continue
                            lines = content.splitlines(keepends=True) if isinstance(content, str) else [s + "\n" for s in content if isinstance(s, str)]
                            new_lines, data_matches = scanner.scan_lines(
                                lines,
                                file_path=file_path,
                                cell_index=cell_idx,
                                field=mime,
                            )
                            all_matches.extend(data_matches)
                            if data_matches and self.config.apply and not self.config.preview_mode:
                                if isinstance(content, str):
                                    out["data"][mime] = "".join(new_lines)
                                else:
                                    out["data"][mime] = new_lines
                                modified = True


            if self.config.scan_metadata and "metadata" in cell:


                pass

        if modified and self.config.apply and not self.config.preview_mode:

            backup_path = None
            try:
                if self.config.keep_backups:
                    backup_path = self._create_persistent_backup(file_path)

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(nb, f, ensure_ascii=False, indent=1)

                logger.info("Modified notebook saved: %s", file_path)
            except Exception as e:
                logger.error("Failed to write notebook %s: %s", file_path, e)
                if backup_path and backup_path.exists():
                    try:
                        import shutil
                        shutil.copy2(backup_path, file_path)
                    except Exception:
                        pass
                raise
        elif all_matches and self.config.preview_mode:
            logger.debug("Preview mode – would modify notebook %s", file_path)
            modified = False

        return all_matches, modified

    def _backup_base_dir(self) -> Path:
        if self.config.directories:
            return Path(self.config.directories[0]).resolve()
        return Path.cwd().resolve()

    def _target_backup_path(self, file_path: Path) -> Path:
        if self.config.backup_dir is None:
            return file_path.with_name(file_path.name + ".bak")
        base = self._backup_base_dir()
        src = file_path.resolve()
        try:
            rel = src.relative_to(base)
        except Exception:
            rel = Path(src.name)
        target = (self.config.backup_dir / rel).with_name(rel.name + ".bak")
        return target

    @staticmethod
    def _next_versioned_backup_path(p: Path) -> Path:
        i = 1
        while True:
            cand = Path(str(p) + f".{i}")
            if not cand.exists():
                return cand
            i += 1

    def _create_persistent_backup(self, file_path: Path) -> Optional[Path]:
        if not file_path.exists():
            return None
        target = self._target_backup_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if self.config.overwrite_backups:
                try:
                    target.unlink()
                except Exception:
                    target = self._next_versioned_backup_path(target)
            else:
                target = self._next_versioned_backup_path(target)
        import shutil
        shutil.copy2(file_path, target)
        logger.debug("Backup created: %s", target)
        return target

    def _export_matches(self, matches: List[AnonymizerMatch], export_path: Path) -> None:
        export_path = Path(export_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)

        data = [self._match_to_dict(m) for m in matches]
        try:
            suf = export_path.suffix.lower()
            if suf == ".json":
                payload = {
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_matches": len(data),
                    "matches": data,
                }
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            elif suf == ".jsonl":
                with open(export_path, "w", encoding="utf-8") as f:
                    for item in data:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
            else:

                with open(export_path, "w", encoding="utf-8") as f:
                    f.write("ANONYMIZER MATCHES REPORT\n")
                    f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Total matches: {len(matches)}\n")
                    f.write("=" * 60 + "\n\n")
                    for m in matches:
                        cell = f" [cell {m.cell_index}]" if m.cell_index is not None else ""
                        f.write(f"{m.relative_path}:{m.line}{cell} [{m.rule_name}] {m.matched_text!r} -> {m.replacement_text!r}\n")
            logger.info("Matches exported to: %s", export_path)
        except Exception as e:
            logger.error("Failed to export matches: %s", e)

    @staticmethod
    def _match_to_dict(m: AnonymizerMatch) -> Dict[str, Any]:
        return {
            "file": str(m.file),
            "relative_path": m.relative_path,
            "rule_name": m.rule_name,
            "matched_text": m.matched_text,
            "replacement_text": m.replacement_text,
            "line": m.line,
            "column": m.column,
            "confidence": m.confidence,
            "cell_index": m.cell_index,
            "field": m.field,
        }

    def _log_configuration(self) -> None:
        logger.info("=" * 60)
        logger.info("ANONYMIZER CONFIGURATION")
        logger.info("=" * 60)
        logger.info("Directories: %s", ", ".join(self.config.directories or ["."]))
        logger.info("Pattern(s): %s", self.config.include_pattern)
        logger.info("Recursive (default): %s", self.config.recursive)
        logger.info("Built-in rule groups: %s", ", ".join(self.config.builtin_rules) or "none")
        logger.info("Rules file: %s", self.config.rules_file or "none")
        logger.info("Env files: %s", ", ".join(str(p) for p in self.config.env_files) or "none")
        logger.info("Mode: %s", self.config.mode)
        logger.info("Global replacement: %s", self.config.replacement)
        logger.info("Apply changes: %s", self.config.apply)
        logger.info("Preview mode: %s", self.config.preview_mode)
        logger.info("Scan notebooks: %s", self.config.scan_notebooks)
        logger.info("Scan outputs: %s", self.config.scan_outputs)
        logger.info("=" * 60)

    def _log_summary(self, matches: int, modified: int, files: int) -> None:
        logger.info("=" * 60)
        logger.info("PROCESSING SUMMARY")
        logger.info("=" * 60)
        logger.info("Found %d matches in %d files", matches, files)
        if self.config.preview_mode:
            logger.info("Preview mode – no files were modified (use --apply to actually redact).")
        elif not self.config.apply:
            logger.info("Search mode – no files were modified (use --apply to redact).")
        else:
            logger.info("Modified %d files", modified)
        logger.info("=" * 60)






def _flatten_patterns(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        try:
            parts = shlex.split(v)
        except ValueError:
            parts = v.split()
        for p in parts:
            p = p.strip()
            if p:
                out.append(p)
    return out or ["*"]


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Anonymizer – search and redact sensitive information in code and notebooks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("directories", nargs="*", default=[], help="Directories to process (default: .)")
    parser.add_argument("-d", "--dir", action="append", dest="dirs_nonrecursive", default=[], help="Add directory (non-recursive)")
    parser.add_argument("-dr", "--dir-recursive", action="append", dest="dirs_recursive", default=[], help="Add directory (recursive)")

    parser.add_argument("-p", "--pattern", nargs="+", default=["*"], help='File pattern(s) (e.g. "*.py" "*.txt" "*.ipynb")')
    parser.add_argument("-r", "--recursive", action="store_true", help="Search recursively (default recursion)")
    parser.add_argument("--max-depth", type=int, help="Maximum recursion depth")

    parser.add_argument("-ed", "--exclude-dir", action="append", dest="exclude_dirs", help="Exclude directory name")
    parser.add_argument("-en", "--exclude-name", action="append", dest="exclude_names", help="Exclude file wildcard")
    parser.add_argument("-ep", "--exclude-pattern", action="append", dest="exclude_patterns", help="Exclude path wildcard")

    parser.add_argument("-ig", "--use-gitignore", action="store_true", help="Auto-discover and use .gitignore")
    parser.add_argument("-gi", "--gitignore", type=Path, help="Use a specific .gitignore")
    parser.add_argument("--no-gitignore", action="store_true", help="Ignore .gitignore")


    parser.add_argument("--builtin-rules", help="Comma-separated list of built-in rule groups: credentials,pii,system,all")
    parser.add_argument("--rules-file", type=Path, help="Load additional rules from YAML/JSON file")
    parser.add_argument("--env-file", action="append", dest="env_files", type=Path, help="Path to .env file (can be repeated)")


    parser.add_argument("--mode", choices=["replace", "remove-line", "hash"], default="replace", help="Default redaction mode")
    parser.add_argument("--replacement", default="[REDACTED]", help="Global placeholder for replaced text")
    parser.add_argument("--apply", action="store_true", help="Actually apply redactions to files (default: search only)")
    parser.add_argument("--preview", action="store_true", help="Preview what would be redacted (without modifying files)")


    parser.add_argument("--no-scan-notebooks", action="store_false", dest="scan_notebooks", help="Skip Jupyter notebooks")
    parser.add_argument("--no-scan-outputs", action="store_false", dest="scan_outputs", help="Do not scan notebook outputs")
    parser.add_argument("--scan-metadata", action="store_true", dest="scan_metadata", help="Scan notebook metadata (may contain sensitive info)")


    parser.add_argument("--no-detect-system", action="store_false", dest="detect_system_info", help="Disable detection of system info (username, home, hostname)")
    parser.add_argument("--username-placeholder", default="[USER]", help="Placeholder for username")
    parser.add_argument("--home-placeholder", default="[HOME]", help="Placeholder for home directory")
    parser.add_argument("--hostname-placeholder", default="[HOST]", help="Placeholder for hostname")
    parser.add_argument("--project-root-placeholder", default="[PROJECT_ROOT]", help="Placeholder for project root")


    parser.add_argument("--export-matches", type=Path, help="Export matches to file (.txt/.json/.jsonl)")
    parser.add_argument("-o", "--output", type=Path, help="Log file for diagnostic messages")
    parser.add_argument("--log-file", type=Path, help="Legacy alias for --output")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--split-streams", action="store_true", help="stdout: changed files summary; stderr: logs")


    parser.add_argument("--no-cache", action="store_true", help="Disable file modification cache")
    parser.add_argument("--keep-backups", action="store_true", help="Keep backups after successful write")
    parser.add_argument("--backup-dir", type=Path, help="Directory to store backups (preserves relative structure)")
    parser.add_argument("--overwrite-backups", action="store_true", help="Overwrite existing backups (else .bak.1, .bak.2...)")

    args = parser.parse_args(argv)


    if args.log_file and not args.output:
        args.output = args.log_file


    if isinstance(args.pattern, list):
        if len(args.pattern) == 1:
            args.pattern = args.pattern[0]
        else:
            args.pattern = " ".join(args.pattern)

    return args


def create_config_from_args(args: argparse.Namespace) -> AnonymizerConfig:
    use_gitignore = bool(args.use_gitignore) and not bool(args.no_gitignore)
    custom_gitignore = None if args.no_gitignore else args.gitignore

    pattern_values = [args.pattern] if isinstance(args.pattern, str) else list(args.pattern)
    patterns = _flatten_patterns(pattern_values)
    include_pattern = " ".join(patterns)

    directories: List[str] = []
    directories.extend(args.directories or [])
    directories.extend(args.dirs_nonrecursive or [])
    directories.extend(args.dirs_recursive or [])
    if not directories:
        directories = ["."]

    dir_recursion: Dict[Path, bool] = {}
    for d in args.dirs_nonrecursive or []:
        try:
            dir_recursion[Path(d).resolve()] = False
        except Exception:
            dir_recursion[Path(d)] = False
    for d in args.dirs_recursive or []:
        try:
            dir_recursion[Path(d).resolve()] = True
        except Exception:
            dir_recursion[Path(d)] = True

    builtin_groups = set()
    if args.builtin_rules:
        for g in args.builtin_rules.split(","):
            g = g.strip().lower()
            if g:
                builtin_groups.add(g)


    if args.preview and not args.apply:
        logger.info("--preview used without --apply. Showing preview of potential changes (no files will be modified).")

    return AnonymizerConfig(
        directories=directories,
        include_pattern=include_pattern,
        recursive=bool(args.recursive),
        exclude_dirs=set(args.exclude_dirs or []),
        exclude_names=set(args.exclude_names or []),
        exclude_patterns=set(args.exclude_patterns or []),
        max_depth=args.max_depth,
        use_gitignore=use_gitignore,
        custom_gitignore=custom_gitignore,
        builtin_rules=builtin_groups,
        rules_file=args.rules_file,
        env_files=args.env_files or [],
        mode=args.mode,
        replacement=args.replacement,
        apply=bool(args.apply),
        preview_mode=bool(args.preview),
        scan_notebooks=bool(args.scan_notebooks),
        scan_outputs=bool(args.scan_outputs),
        scan_metadata=bool(args.scan_metadata),
        detect_system_info=bool(args.detect_system_info),
        username_placeholder=args.username_placeholder,
        home_placeholder=args.home_placeholder,
        hostname_placeholder=args.hostname_placeholder,
        project_root_placeholder=args.project_root_placeholder,
        export_matches=args.export_matches,
        log_file=args.output,
        use_cache=not bool(args.no_cache),
        keep_backups=bool(args.keep_backups) or bool(args.backup_dir),
        backup_dir=args.backup_dir,
        overwrite_backups=bool(args.overwrite_backups),
        directory_recursion=dir_recursion,
        split_streams=bool(args.split_streams),
    )


def _configure_logging(log_file: Optional[Path], *, verbose: bool, split_streams: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    diag_stream = sys.stderr if split_streams else sys.stdout
    diag = logging.StreamHandler(diag_stream)
    diag.setLevel(level)
    diag.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(diag)

    if log_file:
        fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(fh)

    out_logger = logging.getLogger(OUTPUT_LOGGER_NAME)
    out_logger.setLevel(logging.INFO)
    out_logger.handlers.clear()
    if split_streams:
        out_h = logging.StreamHandler(sys.stdout)
        out_h.setLevel(logging.INFO)
        out_h.setFormatter(logging.Formatter("%(message)s"))
        out_logger.addHandler(out_h)
        out_logger.propagate = False
    else:
        out_logger.propagate = True


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)
    _configure_logging(args.output, verbose=bool(args.verbose), split_streams=bool(args.split_streams))

    try:
        config = create_config_from_args(args)
        processor = AnonymizerProcessor(config)
        result = processor.process_files()

        if config.split_streams and not config.preview_mode:

            print(f"OK: matches={result['total_matches']} modified={result['modified_files']} files={result['total_files']}")

        return 0
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        logger.error("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
