from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from ...core.models.domain import CodeElement
from ..base import BaseParser


class PythonParser(BaseParser):
    name = "python"

    def __init__(self, **_):
        pass

    @classmethod
    def get_supported_config_keys(cls):
        return []

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return [".py", ".pyw", ".pyi"]

    def parse_functions(self, file_path: Path) -> List[CodeElement]:
        src = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
        out: List[CodeElement] = []

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.class_stack: List[str] = []

            def visit_ClassDef(self, node: ast.ClassDef):
                self.class_stack.append(node.name)
                self.generic_visit(node)
                self.class_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef):
                self._handle_func(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self._handle_func(node)

            def _handle_func(self, node):
                seg = ast.get_source_segment(src, node) or ""
                if not seg.strip():
                    return
                if self.class_stack:
                    name = ".".join(self.class_stack) + "." + node.name
                    tp = CodeElement.Type.METHOD
                else:
                    name = node.name
                    tp = CodeElement.Type.FUNCTION

                out.append(
                    CodeElement(
                        type=tp,
                        name=name,
                        content=seg,
                        file_path=file_path,
                        line_start=getattr(node, "lineno", None),
                        line_end=getattr(node, "end_lineno", None),
                        language="python",
                    )
                )

        Visitor().visit(tree)
        return out

    def parse_classes(self, file_path: Path) -> List[CodeElement]:
        src = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
        out: List[CodeElement] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                seg = ast.get_source_segment(src, node) or ""
                if not seg.strip():
                    continue
                out.append(
                    CodeElement(
                        type=CodeElement.Type.CLASS,
                        name=node.name,
                        content=seg,
                        file_path=file_path,
                        line_start=getattr(node, "lineno", None),
                        line_end=getattr(node, "end_lineno", None),
                        language="python",
                    )
                )
        return out
