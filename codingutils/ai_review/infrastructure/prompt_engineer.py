from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..core.models.config import PromptConfig
from ..core.models.domain import CodeElement

logger = logging.getLogger(__name__)


class PromptEngineer:
    def __init__(self, config: PromptConfig):
        self.config = config
        self._cache: Dict[str, str] = {}

    def _load(self, ref: Optional[str]) -> Optional[str]:
        if not ref:
            return None
        if "\n" in ref:
            return ref
        p = Path(ref)
        if p.exists() and p.is_file():
            key = str(p.resolve())
            if key in self._cache:
                return self._cache[key]
            txt = p.read_text(encoding="utf-8")
            self._cache[key] = txt
            return txt
        return None

    def build_messages(self, element: CodeElement) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []

        system_txt = self._load(self.config.system_prompt)
        if system_txt:
            messages.append({"role": "system", "content": system_txt})

        user_tpl = self._load(self.config.user_prompt)
        if not user_tpl:
            raise ValueError(f"User prompt not found: {self.config.user_prompt}")

        variables = self._variables(element)

        if self.config.include_context and "{{context}}" in user_tpl:
            try:
                variables["context"] = element.file_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning("Failed to read context: %s", e)
                variables["context"] = ""

        if self.config.context_files and "{{context_files}}" in user_tpl:
            blocks: List[str] = []
            for pat in self.config.context_files:
                for fp in Path.cwd().glob(pat):
                    try:
                        blocks.append(f"--- {fp} ---\n{fp.read_text(encoding='utf-8', errors='replace')}")
                    except Exception as e:
                        logger.warning("Failed to read context file %s: %s", fp, e)
            variables["context_files"] = "\n\n".join(blocks)

        txt = self._render(user_tpl, variables)
        messages.append({"role": "user", "content": txt})
        return messages

    def _variables(self, element: CodeElement) -> Dict[str, str]:
        try:
            rel = str(element.file_path.resolve().relative_to(Path.cwd().resolve()))
        except Exception:
            rel = str(element.file_path)

        vars_: Dict[str, str] = {
            "code": element.content,
            "filename": element.file_path.name,
            "filepath": rel,
            "language": element.language or element.file_path.suffix.lstrip("."),
            "element_name": element.name,
            "element_type": element.type.value,
            "timestamp": datetime.now().isoformat(),
        }
        vars_.update(self.config.placeholders or {})
        return vars_

    @staticmethod
    def _render(template: str, variables: Dict[str, str]) -> str:
        out = template
        for k, v in variables.items():
            out = out.replace(f"{{{{{k}}}}}", v)
        return out
