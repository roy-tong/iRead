from __future__ import annotations

import fcntl
import json
import os
import shlex
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .subscriptions import PRODUCT_NAME


REGISTRY_VERSION = 1
READY_STATES = {"active", "active_with_gaps", "degraded"}


def iread_home() -> Path:
    return Path(os.environ.get("IREAD_HOME", "~/.config/iread")).expanduser()


def registry_path() -> Path:
    return iread_home() / "subscriptions.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _read_object(path: Path) -> Dict[str, Any]:
    value = _read_json(path, {})
    return value if isinstance(value, dict) else {}


def _subscription_identity(config_dir: Path) -> Dict[str, str]:
    subscription = _read_object(config_dir / "subscription.json")
    profile = _read_object(config_dir / "profile.json")
    return {
        "id": str(
            subscription.get("id")
            or profile.get("id")
            or config_dir.name
        ),
        "name": str(
            subscription.get("name")
            or profile.get("name")
            or config_dir.name
        ),
    }


def register_subscription(
    config_dir: Path,
    repository_root: Optional[Path] = None,
) -> Dict[str, Any]:
    config_dir = config_dir.expanduser().resolve()
    inferred_root = (
        config_dir.parent.parent
        if config_dir.parent.name in {"subscriptions", "profiles"}
        else config_dir.parent
    )
    repository_root = (repository_root or inferred_root).expanduser().resolve()
    if not (config_dir / "profile.json").is_file():
        raise FileNotFoundError(f"Not an iRead configuration directory: {config_dir}")
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    identity = _subscription_identity(config_dir)
    entry = {
        **identity,
        "config_dir": str(config_dir),
        "repository_root": str(repository_root),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current = _read_object(path)
        subscriptions = current.get("subscriptions", [])
        if not isinstance(subscriptions, list):
            subscriptions = []
        updated = [
            item
            for item in subscriptions
            if isinstance(item, dict)
            and str(item.get("config_dir") or "") != str(config_dir)
        ]
        updated.append(entry)
        payload = {"version": REGISTRY_VERSION, "subscriptions": updated}
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return {**entry, "registry": str(path)}


def is_registered(config_dir: Path) -> bool:
    target = str(config_dir.expanduser().resolve())
    registry = _read_object(registry_path())
    return any(
        str(Path(str(item["config_dir"])).expanduser().resolve()) == target
        for item in registry.get("subscriptions", [])
        if isinstance(item, dict) and item.get("config_dir")
    )


def _service_root(root: Path) -> Path:
    configured = os.environ.get("IREAD_SERVICE_ROOT") or os.environ.get(
        "REPORTER_SERVICE_ROOT"
    )
    if configured:
        return Path(configured).expanduser().resolve()
    data_dir = root / "data"
    if data_dir.is_symlink():
        return data_dir.resolve().parent
    return Path.home() / "Library/Application Support/ResearchReporter"


def active_config_dir(root: Path) -> Optional[Path]:
    pointer = _service_root(root) / "active-config-dir"
    if not pointer.is_file():
        return None
    try:
        value = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(value).expanduser().resolve() if value else None


def _runtime_data_dir(root: Path, config_dir: Path) -> Path:
    runtime = _read_object(config_dir / "runtime.json")
    value = str(runtime.get("data_dir") or "data")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def list_reports(
    db_path: Path,
    *,
    kind: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "database": str(db_path),
        "count": 0,
        "reports": [],
    }
    if not db_path.is_file():
        return result
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        if "reports" not in _table_names(connection):
            return result
        where = "WHERE kind=?" if kind else ""
        params: List[Any] = [kind] if kind else []
        count_row = connection.execute(
            f"SELECT COUNT(*) FROM reports {where}", params
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT id, kind, title, markdown_path, period_start, period_end,
                   created_at, notion_status, notion_url
            FROM reports {where}
            ORDER BY period_end DESC, id DESC
            LIMIT ?
            """,
            [*params, max(1, min(limit, 100))],
        ).fetchall()
        reports = []
        for row in rows:
            markdown_path = Path(str(row["markdown_path"])).expanduser()
            quality_path = markdown_path.with_suffix(".quality.json")
            quality = _read_object(quality_path) if quality_path.is_file() else {}
            reports.append(
                {
                    "id": int(row["id"]),
                    "kind": str(row["kind"]),
                    "title": str(row["title"]),
                    "path": str(markdown_path),
                    "exists": markdown_path.is_file(),
                    "quality": {
                        "status": quality.get("status"),
                        "score": quality.get("score"),
                        "path": str(quality_path) if quality else None,
                    },
                    "period_start": int(row["period_start"]),
                    "period_end": int(row["period_end"]),
                    "created_at": int(row["created_at"]),
                    "created_at_iso": datetime.fromtimestamp(
                        int(row["created_at"]), timezone.utc
                    ).isoformat(),
                    "notion_status": row["notion_status"],
                    "notion_url": row["notion_url"],
                }
            )
        result["count"] = int(count_row[0] if count_row else 0)
        result["reports"] = reports
        return result
    except sqlite3.Error as exc:
        return {**result, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if connection is not None:
            connection.close()


def _database_counts(db_path: Path) -> Dict[str, int]:
    counts = {
        "articles": 0,
        "pending_analysis": 0,
        "failed_analysis": 0,
    }
    if not db_path.is_file():
        return counts
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
        tables = _table_names(connection)
        if "articles" not in tables:
            return counts
        counts["articles"] = int(
            connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        )
        counts["pending_analysis"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM articles WHERE analysis_status IN ('pending', 'retry')"
            ).fetchone()[0]
        )
        counts["failed_analysis"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM articles WHERE analysis_status='failed'"
            ).fetchone()[0]
        )
    except sqlite3.Error:
        pass
    finally:
        if connection is not None:
            connection.close()
    return counts


def _feedback_summary(data_dir: Path) -> Dict[str, Any]:
    path = data_dir / "state/feedback.jsonl"
    if not path.is_file():
        return {"count": 0, "latest": None}
    count = 0
    latest = None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    count += 1
                    latest = {
                        key: value.get(key)
                        for key in (
                            "id",
                            "target",
                            "target_id",
                            "rating",
                            "note",
                            "tags",
                            "created_at",
                        )
                    }
    except OSError:
        return {"count": 0, "latest": None}
    return {"count": count, "latest": latest}


def _compact_activation(activation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not activation:
        return None
    readiness = activation.get("readiness") or {}
    matching = activation.get("matching") or {}
    return {
        "status": activation.get("status"),
        "updated_at": activation.get("updated_at"),
        "wechat_skipped": bool(activation.get("wechat_skipped")),
        "approval": activation.get("approval"),
        "auth": activation.get("auth"),
        "schedule": activation.get("schedule"),
        "error": activation.get("error"),
        "next_command": activation.get("next_command"),
        "matching": {
            "unresolved": matching.get("unresolved", []),
            "errors": matching.get("errors", []),
        }
        if matching
        else None,
        "readiness": {
            "ready": readiness.get("ready"),
            "article_count": readiness.get("article_count"),
            "audit_status": readiness.get("audit_status"),
            "active_rss": readiness.get("active_rss"),
            "configured_rss": readiness.get("configured_rss"),
            "pending_external": readiness.get("pending_external"),
            "required_pending_external": readiness.get(
                "required_pending_external"
            ),
            "required_pending_external_ids": readiness.get(
                "required_pending_external_ids", []
            ),
            "critical": readiness.get("critical", 0),
            "warning_count": len(readiness.get("warnings", [])),
        }
        if readiness
        else None,
    }


def _next_actions(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    config = shlex.quote(str(summary["config_dir"]))
    command = f"bin/iread --config-dir {config}"
    status = str(summary.get("status") or "configured")
    activation = summary.get("activation") or {}
    actions: List[Dict[str, Any]] = []

    if status in {"configured", "not_started"}:
        actions.append(
            {
                "id": "approve_activation",
                "reason": "Sources are configured but collection has not started.",
                "command": f"{command} activate --approved --install-schedule",
                "requires_confirmation": True,
            }
        )
    elif status == "needs_collector":
        actions.append(
            {
                "id": "setup_collector",
                "reason": "The local collection service is not ready.",
                "command": "scripts/setup_collection.sh",
                "requires_confirmation": False,
            }
        )
    elif status in {"needs_auth", "auth_timeout"}:
        actions.append(
            {
                "id": "complete_wechat_auth",
                "reason": "Local WeChat authorization is waiting for a QR scan.",
                "command": f"{command} activate --wait-for-auth --install-schedule",
                "qr_image": (activation.get("auth") or {}).get("qr_image"),
                "requires_confirmation": False,
            }
        )
    elif status == "needs_source_review":
        actions.append(
            {
                "id": "review_source_matches",
                "reason": "One or more source matches are unresolved or ambiguous.",
                "command": f"{command} subscribe --dry-run",
                "requires_confirmation": False,
            }
        )
    elif status in {"backfilling", "readiness_review"}:
        actions.append(
            {
                "id": "continue_backfill",
                "reason": "The initial one-month collection is incomplete.",
                "command": f"{command} collect",
                "requires_confirmation": False,
            }
        )

    if status == "active_unverified":
        actions.append(
            {
                "id": "audit_legacy_activation",
                "reason": "This scheduled subscription predates activation state tracking.",
                "command": f"{command} audit",
                "requires_confirmation": False,
            }
        )

    if status == "active_with_gaps":
        actions.append(
            {
                "id": "review_coverage_gaps",
                "reason": "Required web sources are still pending.",
                "command": f"{command} audit",
                "source_ids": (activation.get("readiness") or {}).get(
                    "required_pending_external_ids", []
                ),
                "requires_confirmation": False,
            }
        )

    schedule = summary.get("schedule") or {}
    if status in READY_STATES and schedule.get("status") != "installed":
        actions.append(
            {
                "id": "approve_schedule",
                "reason": "Recurring collection and reports are not confirmed as installed.",
                "command": f"{command} activate --approved --install-schedule",
                "requires_confirmation": True,
            }
        )
    if status in READY_STATES and summary.get("report_count", 0) == 0:
        actions.append(
            {
                "id": "generate_first_report",
                "reason": "Collection is report-ready but no local report exists yet.",
                "command": f"{command} run --no-publish",
                "requires_confirmation": True,
            }
        )
    if summary.get("report_count", 0) > 0:
        actions.append(
            {
                "id": "view_latest_report",
                "reason": "Local reports are available.",
                "command": f"{command} reports --limit 5",
                "path": next(
                    (
                        report.get("path")
                        for report in summary.get("latest_reports", {}).values()
                        if report.get("path")
                    ),
                    None,
                ),
                "requires_confirmation": False,
            }
        )
    return actions


def summarize_subscription(
    root: Path,
    config_dir: Path,
    *,
    active: bool = False,
) -> Optional[Dict[str, Any]]:
    config_dir = config_dir.expanduser().resolve()
    profile = _read_object(config_dir / "profile.json")
    if not isinstance(profile, dict) or not profile:
        return None
    subscription = _read_object(config_dir / "subscription.json")
    reporting = _read_object(config_dir / "reporting.json")
    accounts = _read_object(config_dir / "accounts.json")
    external = _read_object(config_dir / "external_sources.json")
    data_dir = _runtime_data_dir(root, config_dir)
    raw_activation = _read_object(data_dir / "state/activation.json")
    db_path = data_dir / "research.db"
    counts = _database_counts(db_path)
    report_index = list_reports(db_path, limit=100)
    latest: Dict[str, Any] = {}
    for report in report_index["reports"]:
        latest.setdefault(str(report["kind"]), report)
    domains = subscription.get("domains") or profile.get("domains") or []
    inferred_status = str(
        raw_activation.get("status")
        or subscription.get("status")
        or "configured"
    )
    if not raw_activation and active and (counts["articles"] or report_index["count"]):
        inferred_status = "active_unverified"
    recorded_schedule = raw_activation.get("schedule")
    if active:
        schedule = recorded_schedule or {
            "status": "installed",
            "source": "active-config-pointer",
        }
    elif (
        isinstance(recorded_schedule, dict)
        and recorded_schedule.get("status") == "installed"
    ):
        schedule = {
            **recorded_schedule,
            "status": "not_active",
            "recorded_status": "installed",
            "reason": "another subscription is the active scheduled configuration",
        }
    else:
        schedule = recorded_schedule
    activation = _compact_activation(raw_activation)
    summary: Dict[str, Any] = {
        "id": str(subscription.get("id") or profile.get("id") or config_dir.name),
        "name": str(
            subscription.get("name") or profile.get("name") or config_dir.name
        ),
        "config_dir": str(config_dir),
        "repository_root": str(root.resolve()),
        "registered": is_registered(config_dir),
        "active_schedule": active,
        "status": inferred_status,
        "updated_at": raw_activation.get("updated_at")
        or subscription.get("created_at"),
        "domains": [
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or item.get("field") or ""),
            }
            for item in domains
            if isinstance(item, dict)
        ],
        "report_preset": reporting.get("strategy_preset")
        or subscription.get("report_preset"),
        "history_start": reporting.get("history_start")
        or subscription.get("history_start"),
        "sources": {
            "wechat": len(accounts.get("accounts", [])),
            "external": len(external.get("sources", [])),
        },
        "data_dir": str(data_dir),
        "database": str(db_path),
        **counts,
        "report_count": int(report_index["count"]),
        "latest_reports": latest,
        "feedback": _feedback_summary(data_dir),
        "schedule": schedule,
        "activation": activation,
    }
    summary["next_actions"] = _next_actions(summary)
    return summary


def _candidate_config_dirs(
    root: Path,
    selected_config_dir: Optional[Path],
) -> List[Tuple[Path, Path]]:
    candidates: List[Tuple[Path, Path]] = []
    registry = _read_object(registry_path())
    for item in registry.get("subscriptions", []):
        if isinstance(item, dict) and item.get("config_dir"):
            owner_root = Path(str(item.get("repository_root") or root))
            candidates.append((Path(str(item["config_dir"])), owner_root))
    subscriptions_dir = root / "subscriptions"
    if subscriptions_dir.is_dir():
        candidates.extend(
            (path.parent, root)
            for path in subscriptions_dir.glob("*/subscription.json")
        )
    active = active_config_dir(root)
    if active:
        candidates.append((active, root))
    if selected_config_dir:
        candidates.append((selected_config_dir, root))

    result: List[Tuple[Path, Path]] = []
    seen = set()
    for candidate, owner_root in candidates:
        resolved = candidate.expanduser().resolve()
        value = str(resolved)
        if value not in seen and (resolved / "profile.json").is_file():
            seen.add(value)
            result.append((resolved, owner_root.expanduser().resolve()))
    return result


def inspect_workspace(
    root: Path,
    *,
    selected_config_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    root = root.resolve()
    active = active_config_dir(root)
    summaries = [
        summary
        for config_dir, owner_root in _candidate_config_dirs(
            root, selected_config_dir
        )
        if (
            summary := summarize_subscription(
                owner_root,
                config_dir,
                active=bool(active and config_dir.resolve() == active.resolve()),
            )
        )
    ]
    summaries.sort(
        key=lambda item: (
            bool(item.get("active_schedule")),
            str(item.get("updated_at") or ""),
        ),
        reverse=True,
    )
    recommended = summaries[0]["config_dir"] if summaries else None
    return {
        "product": PRODUCT_NAME,
        "version": __version__,
        "repository_root": str(root),
        "registry": str(registry_path()),
        "active_config_dir": str(active) if active else None,
        "recommended_config_dir": recommended,
        "subscription_count": len(summaries),
        "subscriptions": summaries,
        "next_action": (
            summaries[0]["next_actions"][0]
            if summaries and summaries[0]["next_actions"]
            else {
                "id": "start_onboarding",
                "reason": "No registered iRead subscription was found.",
                "command": "Use the onboard-research-domains Codex skill.",
                "requires_confirmation": False,
            }
            if not summaries
            else None
        ),
    }
