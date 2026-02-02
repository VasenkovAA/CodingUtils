from __future__ import annotations

from typing import Dict, List

from ...infrastructure.token_counter import TokenCounter
from ..base import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):
    name = "mock"

    @classmethod
    def get_supported_config_keys(cls):
        return []

    async def complete(self, messages: List[Dict[str, str]]) -> str:
        user = next((m["content"] for m in messages if m["role"] == "user"), "")
        return f"MOCK_REVIEW(len={len(user)})"

    def estimate_tokens(self, text: str) -> int:
        return TokenCounter(method="approximate").estimate(text)
