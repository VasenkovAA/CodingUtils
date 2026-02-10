from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from ...core.models.domain import CodeElement
from ..base import BaseParser


_FUNC_DECL = re.compile(
    r"""^\s*(export\s+)?(default\s+)?(async\s+)?function(\s*\*)?\s+(?P<name>[A-Za-z_$][\w$]*)\s*\(""",
    re.MULTILINE,
)

_ARROW_DECL = re.compile(
    r"""^\s*(export\s+)?(const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(async\s+)?(?P<args>\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>""",
    re.MULTILINE,
)

_CLASS_DECL = re.compile(
    r"""^\s*(export\s+)?(default\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)\b""",
    re.MULTILINE,
)

_METHOD_DECL = re.compile(
    r"""^\s*(async\s+)?(?P<name>[A-Za-z_$][\w$]*)\s*\(""",
    re.MULTILINE,
)


@dataclass
class _Span:
    start: int
    end: int
    line_start: int
    line_end: int


def _line_no(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _skip_ws(text: str, i: int) -> int:
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    return i


def _find_block_span(text: str, start_idx: int) -> Optional[_Span]:
    """
    Find span for a JS/TS block starting at first '{' after start_idx.
    Counts braces, skipping strings/comments in a simple state machine.
    """
    n = len(text)
    i = start_idx
    i = _skip_ws(text, i)

    brace = text.find("{", i)
    if brace == -1:
        return None

    depth = 0
    i = brace
    in_squote = False
    in_dquote = False
    in_tmpl = False
    in_line_comment = False
    in_block_comment = False
    esc = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if not (in_squote or in_dquote or in_tmpl):
            if ch == "/" and nxt == "/":
                in_line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue

        if in_squote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "'":
                in_squote = False
            i += 1
            continue

        if in_dquote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_dquote = False
            i += 1
            continue

        if in_tmpl:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "`":
                in_tmpl = False
            i += 1
            continue

        if ch == "'":
            in_squote = True
            i += 1
            continue
        if ch == '"':
            in_dquote = True
            i += 1
            continue
        if ch == "`":
            in_tmpl = True
            i += 1
            continue

        # braces
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                return _Span(
                    start=brace,
                    end=end,
                    line_start=_line_no(text, brace),
                    line_end=_line_no(text, end),
                )

        i += 1

    return None


def _find_statement_end(text: str, start_idx: int) -> int:
    """
    For arrow functions without block: try to end at ';' or newline.
    """
    n = len(text)
    semi = text.find(";", start_idx)
    if semi != -1:
        return semi + 1
    nl = text.find("\n", start_idx)
    if nl != -1:
        return nl
    return n


class JavaScriptParser(BaseParser):
    """
    JS/TS/TSX parser with naive block extraction.
    Intended for MVP: typical function/class patterns.
    """
    name = "javascript"

    def __init__(self, parse_arrow_functions: bool = True, **_):
        self.parse_arrow_functions = parse_arrow_functions

    @classmethod
    def get_supported_config_keys(cls) -> List[str]:
        return ["parse_arrow_functions"]

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]

    def parse_functions(self, file_path: Path) -> List[CodeElement]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        out: List[CodeElement] = []

        for m in _FUNC_DECL.finditer(text):
            name = m.group("name")
            block = _find_block_span(text, m.start())
            if block:
                start = m.start()
                end = block.end
            else:
                start = m.start()
                end = _find_statement_end(text, start)

            content = text[start:end].strip()
            if content:
                out.append(
                    CodeElement(
                        type=CodeElement.Type.FUNCTION,
                        name=name,
                        content=content,
                        file_path=file_path,
                        line_start=_line_no(text, start),
                        line_end=_line_no(text, end),
                        language="javascript",
                    )
                )
        if self.parse_arrow_functions:
            for m in _ARROW_DECL.finditer(text):
                name = m.group("name")
                start = m.start()

                after = m.end()
                after = _skip_ws(text, after)

                if after < len(text) and text[after] == "{":
                    block = _find_block_span(text, after)
                    end = block.end if block else _find_statement_end(text, after)
                else:
                    end = _find_statement_end(text, after)

                content = text[start:end].strip()
                if content:
                    out.append(
                        CodeElement(
                            type=CodeElement.Type.FUNCTION,
                            name=name,
                            content=content,
                            file_path=file_path,
                            line_start=_line_no(text, start),
                            line_end=_line_no(text, end),
                            language="javascript",
                        )
                    )

        for cls_name, cls_span in self._iter_classes(text):
            methods = self._parse_methods_inside_class(text, cls_span)
            for meth_name, meth_span in methods:
                full = f"{cls_name}.{meth_name}"
                out.append(
                    CodeElement(
                        type=CodeElement.Type.METHOD,
                        name=full,
                        content=text[meth_span.start:meth_span.end].strip(),
                        file_path=file_path,
                        line_start=meth_span.line_start,
                        line_end=meth_span.line_end,
                        language="javascript",
                    )
                )

        return out

    def parse_classes(self, file_path: Path) -> List[CodeElement]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        out: List[CodeElement] = []
        for cls_name, cls_span in self._iter_classes(text):
            start = text.rfind("\n", 0, cls_span.start)
            start = 0 if start == -1 else start + 1
            end = cls_span.end
            out.append(
                CodeElement(
                    type=CodeElement.Type.CLASS,
                    name=cls_name,
                    content=text[start:end].strip(),
                    file_path=file_path,
                    line_start=_line_no(text, start),
                    line_end=_line_no(text, end),
                    language="javascript",
                )
            )
        return out

    def _iter_classes(self, text: str) -> List[Tuple[str, _Span]]:
        res: List[Tuple[str, _Span]] = []
        for m in _CLASS_DECL.finditer(text):
            cls_name = m.group("name")
            span = _find_block_span(text, m.end())
            if span:
                res.append((cls_name, span))
        return res

    def _parse_methods_inside_class(self, text: str, cls_body: _Span) -> List[Tuple[str, _Span]]:
        """
        Parse methods inside class body span [start..end], where start is '{'.
        We do a very simplified scan: look for method-ish lines and capture their blocks.
        """
        body_text = text[cls_body.start:cls_body.end]
        base_offset = cls_body.start

        methods: List[Tuple[str, _Span]] = []
        for m in _METHOD_DECL.finditer(body_text):
            name = m.group("name")
            if name in {"if", "for", "while", "switch", "catch", "return", "function"}:
                continue

            start_idx = m.start()
            brace_span = _find_block_span(body_text, m.end())
            if not brace_span:
                continue

            start_line = body_text.rfind("\n", 0, start_idx)
            start_line = 0 if start_line == -1 else start_line + 1
            abs_start = base_offset + start_line
            abs_end = base_offset + brace_span.end

            methods.append(
                (
                    name,
                    _Span(
                        start=abs_start,
                        end=abs_end,
                        line_start=_line_no(text, abs_start),
                        line_end=_line_no(text, abs_end),
                    ),
                )
            )

        uniq = {}
        for name, sp in methods:
            uniq[(sp.start, sp.end)] = (name, sp)
        return list(uniq.values())
