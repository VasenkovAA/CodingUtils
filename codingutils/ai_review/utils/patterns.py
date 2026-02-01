from __future__ import annotations

from typing import List


def expand_braces(pattern: str) -> List[str]:
    """
    Expand brace patterns:
      "*.{js,ts,tsx}" -> ["*.js","*.ts","*.tsx"]
    """
    if "{" not in pattern or "}" not in pattern:
        return [pattern]

    start = pattern.find("{")
    end = pattern.find("}", start + 1)
    if start == -1 or end == -1 or end < start:
        return [pattern]

    prefix = pattern[:start]
    suffix = pattern[end + 1 :]
    body = pattern[start + 1 : end].strip()
    if not body:
        return [pattern]

    parts = [p.strip() for p in body.split(",") if p.strip()]
    if not parts:
        return [pattern]

    return [f"{prefix}{p}{suffix}" for p in parts]
