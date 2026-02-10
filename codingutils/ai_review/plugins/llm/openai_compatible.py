from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from typing import Dict, List, Optional

from ...core.models.config import LLMConfig
from ...infrastructure.token_counter import TokenCounter
from ..base import BaseLLMProvider


class OpenAICompatibleClient(BaseLLMProvider):
    """
    OpenAI-compatible /v1/chat/completions endpoint.
    Используем urllib + asyncio.to_thread, без внешних зависимостей.
    """

    name = "openai_compatible"

    def __init__(self, config: LLMConfig, default_api_base: Optional[str] = None, require_api_key: bool = False):
        super().__init__(config=config)
        self.default_api_base = default_api_base
        self.require_api_key = require_api_key
        self._counter = TokenCounter(method="approximate")

    @classmethod
    def get_supported_config_keys(cls):
        return ["default_api_base", "require_api_key"]

    def _api_base(self) -> str:
        return (self.config.api_base or self.default_api_base or "").rstrip("/")

    def _api_key(self) -> Optional[str]:
        if self.config.api_key:
            return self.config.api_key
        return os.environ.get("OPENAI_API_KEY")

    async def complete(self, messages: List[Dict[str, str]]) -> str:
        api_base = self._api_base()
        if not api_base:
            raise ValueError("api_base is not set for provider")
        if self.require_api_key and not self._api_key():
            raise ValueError("api_key is required for this provider")

        url = f"{api_base}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "messages": messages,
        }
        data = json.dumps(payload).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"

        def _do_request() -> str:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            return obj["choices"][0]["message"]["content"]

        return await asyncio.to_thread(_do_request)

    def estimate_tokens(self, text: str) -> int:
        return self._counter.estimate(text, model=self.config.model)


class OpenAIClient(OpenAICompatibleClient):
    name = "openai"

    def __init__(self, config: LLMConfig, **kwargs):
        super().__init__(
            config=config,
            default_api_base="https://api.openai.com/v1",
            require_api_key=True,
            **kwargs,
        )


class LMStudioClient(OpenAICompatibleClient):
    name = "lmstudio"

    def __init__(self, config: LLMConfig, **kwargs):
        super().__init__(
            config=config,
            default_api_base="http://localhost:1234/v1",
            require_api_key=False,
            **kwargs,
        )
