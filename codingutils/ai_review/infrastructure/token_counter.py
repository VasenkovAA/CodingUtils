from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TokenCounter:
    def __init__(self, method: str = "approximate"):
        self.method = method
        self._encoders: Dict[str, object] = {}

        if method == "tiktoken":
            try:
                import tiktoken # noqa F401
            except ImportError:
                logger.warning("tiktoken not installed, falling back to approximate")
                self.method = "approximate"

    def estimate(self, text: str, model: Optional[str] = None) -> int:
        if self.method == "tiktoken" and model:
            return self._count_with_tiktoken(text, model)
        return len(text) // 4 + 1

    def _count_with_tiktoken(self, text: str, model: str) -> int:
        try:
            import tiktoken

            enc = self._encoders.get(model)
            if enc is None:
                try:
                    enc = tiktoken.encoding_for_model(model)
                except KeyError:
                    enc = tiktoken.get_encoding("cl100k_base")
                self._encoders[model] = enc

            return len(enc.encode(text))
        except Exception as e:
            logger.warning("Failed to use tiktoken (%s), falling back to approximate", e)
            self.method = "approximate"
            return len(text) // 4 + 1
