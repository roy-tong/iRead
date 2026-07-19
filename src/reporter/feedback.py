from __future__ import annotations

import fcntl
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence

from .settings import Settings


FEEDBACK_VERSION = 1
TARGETS = {"report", "source", "subscription"}
RATINGS = {"up", "down", "neutral"}


def feedback_path(settings: Settings) -> Path:
    return settings.data_dir / "state" / "feedback.jsonl"


def _clean_text(value: Optional[str], limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def record_feedback(
    settings: Settings,
    *,
    target: str,
    rating: str,
    target_id: Optional[str] = None,
    note: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if target not in TARGETS:
        raise ValueError(f"Unknown feedback target: {target}")
    if rating not in RATINGS:
        raise ValueError(f"Unknown feedback rating: {rating}")
    clean_note = _clean_text(note, 2000)
    clean_tags = []
    for tag in tags or []:
        value = _clean_text(tag, 64)
        if value and value not in clean_tags:
            clean_tags.append(value)
    if not clean_note and rating == "neutral" and not clean_tags:
        raise ValueError("Neutral feedback requires a note or tag")
    item = {
        "version": FEEDBACK_VERSION,
        "id": str(uuid.uuid4()),
        "subscription_id": settings.profile.id,
        "target": target,
        "target_id": _clean_text(target_id, 200) or None,
        "rating": rating,
        "note": clean_note,
        "tags": clean_tags,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = feedback_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return {**item, "path": str(path)}


def list_feedback(
    settings: Settings,
    *,
    target: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    if target is not None and target not in TARGETS:
        raise ValueError(f"Unknown feedback target: {target}")
    path = feedback_path(settings)
    if not path.is_file():
        return {
            "path": str(path),
            "count": 0,
            "returned": 0,
            "invalid_lines": 0,
            "items": [],
        }
    items: Deque[Dict[str, Any]] = deque(maxlen=max(1, min(limit, 100)))
    invalid_lines = 0
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except ValueError:
                invalid_lines += 1
                continue
            if not isinstance(value, dict) or (target and value.get("target") != target):
                continue
            total += 1
            items.append(value)
    return {
        "path": str(path),
        "count": total,
        "returned": len(items),
        "invalid_lines": invalid_lines,
        "items": list(reversed(items)),
    }


def feedback_for_report(settings: Settings, limit: int = 20) -> List[Dict[str, Any]]:
    return list_feedback(settings, limit=limit)["items"]
