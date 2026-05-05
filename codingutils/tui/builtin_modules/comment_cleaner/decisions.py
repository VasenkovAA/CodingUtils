from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional


@dataclass(slots=True)
class DecisionsDB:
    """
    decisions[rel_path][key] = true, где key = f"cell:{cell}|sig:{signature}"
    Храним только "удалить".
    """
    version: int
    decisions: Dict[str, Dict[str, bool]]

    @classmethod
    def empty(cls) -> "DecisionsDB":
        return cls(version=1, decisions={})


def decision_key(signature: str, cell_index: Optional[int]) -> str:
    cell = "None" if cell_index is None else str(int(cell_index))
    return f"cell:{cell}|sig:{signature}"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_decisions(path: Path) -> DecisionsDB:
    path = Path(path)
    if not path.exists():
        return DecisionsDB.empty()

    data = json.loads(path.read_text(encoding="utf-8"))
    ver = int(data.get("version", 1))
    decisions_raw = data.get("decisions", {}) or {}

    decisions: Dict[str, Dict[str, bool]] = {}
    if isinstance(decisions_raw, dict):
        for rel, m in decisions_raw.items():
            if not isinstance(rel, str) or not isinstance(m, dict):
                continue
            decisions[rel] = {str(k): bool(v) for k, v in m.items()}

    return DecisionsDB(version=ver, decisions=decisions)


def save_decisions(path: Path, decisions: Mapping[str, Mapping[str, bool]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "updated_at": _now_iso(),
        "decisions": {str(rel): {str(k): bool(v) for k, v in m.items()} for rel, m in decisions.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")