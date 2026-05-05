from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional

from .models import ScanResult, FileRecord, CommentItem


def export_report(path: Path, scan: ScanResult) -> None:
    """
    Export current scan state (including delete flags) to:
      - .txt
      - .json
      - .jsonl
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suf = path.suffix.lower()

    if suf == ".json":
        payload = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_files": scan.total_files,
            "total_comments": scan.total_comments,
            "files": [],
        }
        for rel, fr in sorted(scan.files.items(), key=lambda kv: kv[0]):
            payload["files"].append(_file_to_dict(fr))
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    if suf == ".jsonl":
        with path.open("w", encoding="utf-8") as f:
            for rel, fr in sorted(scan.files.items(), key=lambda kv: kv[0]):
                for c in fr.comments:
                    f.write(json.dumps(_comment_to_dict(fr, c), ensure_ascii=False) + "\n")
        return

    # default: txt
    lines = []
    lines.append("COMMENT CLEANER REPORT")
    lines.append("=" * 60)
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Files: {scan.total_files}")
    lines.append(f"Comments: {scan.total_comments}")
    lines.append("")

    for rel, fr in sorted(scan.files.items(), key=lambda kv: kv[0]):
        lines.append(f"FILE: {rel}")
        lines.append(f"  total={fr.total} delete={fr.to_delete} new={fr.new} excluded={fr.excluded}")
        for c in fr.comments:
            flag = "DEL" if c.delete else "KEEP"
            if c.excluded:
                flag = "EXCL"
            cell = f" [cell {c.cell_index}]" if c.cell_index is not None else ""
            loc = f"{c.start_line}:{c.start_col}-{c.end_line}:{c.end_col}"
            text = c.text.replace("\n", " ⏎ ")
            lines.append(f"    {flag} {c.kind}{cell} {loc}: {text}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _file_to_dict(fr: FileRecord) -> dict:
    return {
        "rel_path": fr.rel_path,
        "total": fr.total,
        "to_delete": fr.to_delete,
        "new": fr.new,
        "excluded": fr.excluded,
        "comments": [_comment_to_dict(fr, c) for c in fr.comments],
    }


def _comment_to_dict(fr: FileRecord, c: CommentItem) -> dict:
    return {
        "rel_path": fr.rel_path,
        "cell_index": c.cell_index,
        "kind": c.kind,
        "start_line": c.start_line,
        "start_col": c.start_col,
        "end_line": c.end_line,
        "end_col": c.end_col,
        "text": c.text,
        "raw": c.raw,
        "signature": c.signature,
        "decision_key": c.decision_key,
        "excluded": c.excluded,
        "lang": c.lang,
        "is_new": c.is_new,
        "delete": c.delete,
    }