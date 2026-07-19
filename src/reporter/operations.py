from __future__ import annotations

import fcntl
import hashlib
import json
import re
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, IO, Mapping, Optional

from .settings import Settings


OPERATION_PROTOCOL_VERSION = 1
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def error_code(error: Exception) -> str:
    if isinstance(error, PermissionError):
        return "approval_required"
    if isinstance(error, FileNotFoundError):
        return "not_found"
    if isinstance(error, ValueError):
        return "invalid_request"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, RuntimeError):
        return "execution_failed"
    return "internal_error"


def operations_path(settings: Settings) -> Path:
    return settings.data_dir / "state" / "operations.jsonl"


def validate_request_id(request_id: Optional[str]) -> Optional[str]:
    if request_id is None:
        return None
    value = request_id.strip()
    if not REQUEST_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "request_id must be 1-128 characters using letters, numbers, '.', '_', ':', or '-'"
        )
    return value


def intent_hash(values: Mapping[str, Any]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _append(settings: Settings, event: Dict[str, Any]) -> None:
    path = operations_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _event(
    settings: Settings,
    operation_id: str,
    command: str,
    phase: str,
    request_id: Optional[str],
    **values: Any,
) -> Dict[str, Any]:
    return {
        "protocol_version": OPERATION_PROTOCOL_VERSION,
        "operation_id": operation_id,
        "request_id": request_id,
        "command": command,
        "config_dir": str(settings.config_dir),
        "phase": phase,
        "at": datetime.now(timezone.utc).isoformat(),
        **values,
    }


def start_operation(
    settings: Settings,
    command: str,
    request_id: Optional[str],
    operation_intent_hash: str,
) -> str:
    request_id = validate_request_id(request_id)
    operation_id = str(uuid.uuid4())
    _append(
        settings,
        _event(
            settings,
            operation_id,
            command,
            "started",
            request_id,
            intent_hash=operation_intent_hash,
        ),
    )
    return operation_id


def finish_operation(
    settings: Settings,
    operation_id: str,
    command: str,
    request_id: Optional[str],
    operation_intent_hash: str,
    *,
    outcome: str = "completed",
) -> None:
    _append(
        settings,
        _event(
            settings,
            operation_id,
            command,
            "finished",
            request_id,
            intent_hash=operation_intent_hash,
            outcome=outcome,
        ),
    )


def fail_operation(
    settings: Settings,
    operation_id: str,
    command: str,
    request_id: Optional[str],
    operation_intent_hash: str,
    error: Exception,
) -> None:
    _append(
        settings,
        _event(
            settings,
            operation_id,
            command,
            "failed",
            request_id,
            intent_hash=operation_intent_hash,
            error_code=error_code(error),
            error_type=type(error).__name__,
            error_message=" ".join(str(error).split())[:1000],
        ),
    )


def operation_events(settings: Settings, limit: int = 50) -> Dict[str, Any]:
    path = operations_path(settings)
    if not path.is_file():
        return {
            "path": str(path),
            "count": 0,
            "returned": 0,
            "invalid_lines": 0,
            "events": [],
        }
    events: Deque[Dict[str, Any]] = deque(maxlen=max(1, min(limit, 500)))
    invalid_lines = 0
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except ValueError:
                invalid_lines += 1
                continue
            if isinstance(value, dict):
                total += 1
                events.append(value)
    return {
        "path": str(path),
        "count": total,
        "returned": len(events),
        "invalid_lines": invalid_lines,
        "events": list(events),
    }


def completed_request(
    settings: Settings,
    command: str,
    request_id: Optional[str],
    operation_intent_hash: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    request_id = validate_request_id(request_id)
    if not request_id:
        return None
    path = operations_path(settings)
    if not path.is_file():
        return None
    completed = None
    conflicting = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not (
                isinstance(event, dict)
                and event.get("request_id") == request_id
                and event.get("command") == command
                and event.get("phase") == "finished"
                and event.get("outcome") == "completed"
            ):
                continue
            previous_hash = event.get("intent_hash")
            if (
                operation_intent_hash
                and previous_hash
                and previous_hash != operation_intent_hash
            ):
                conflicting = event
            else:
                completed = event
    if conflicting and completed is None:
        raise ValueError(
            "request_id was already completed with different arguments; use a new request id"
        )
    return completed


def acquire_request_lock(
    settings: Settings,
    command: str,
    request_id: str,
) -> IO[str]:
    request_id = validate_request_id(request_id) or ""
    digest = hashlib.sha256(f"{command}\0{request_id}".encode("utf-8")).hexdigest()
    path = settings.data_dir / "state/request-locks" / f"{digest}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def release_request_lock(handle: Optional[IO[str]]) -> None:
    if handle is None or handle.closed:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()
