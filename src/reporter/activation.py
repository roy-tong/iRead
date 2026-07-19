from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from .audit import coverage_audit
from .db import Database
from .ingest import (
    ingest,
    request_backfill,
    start_werss_wechat_auth,
    subscribe_accounts,
    wait_for_werss_wechat_auth,
    werss_wechat_auth_status,
)
from .settings import Settings


ACTIVATION_VERSION = 1
WAITING_STATES = {"needs_collector", "needs_auth", "auth_timeout", "needs_source_review"}
REPORT_READY_STATES = {"active", "active_with_gaps", "degraded"}


def activation_path(settings: Settings) -> Path:
    return settings.data_dir / "state" / "activation.json"


def load_activation_state(settings: Settings) -> Optional[Dict[str, Any]]:
    path = activation_path(settings)
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _write_state(settings: Settings, status: str, **values: Any) -> Dict[str, Any]:
    timezone = ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
    previous = load_activation_state(settings) or {}
    state = {
        **previous,
        "version": ACTIVATION_VERSION,
        "subscription_id": settings.profile.id,
        "subscription_name": settings.profile.name,
        "config_dir": str(settings.config_dir),
        "status": status,
        "updated_at": datetime.now(timezone).isoformat(),
        **values,
    }
    path = activation_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def set_wechat_collection_enabled(settings: Settings, enabled: bool) -> None:
    settings.reporting.setdefault("collection", {})["wechat_enabled"] = enabled
    path = settings.config_dir / "reporting.json"
    if not path.exists():
        raise FileNotFoundError(f"Cannot persist collection mode: {path}")
    path.write_text(
        json.dumps(settings.reporting, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def evaluate_activation_readiness(settings: Settings, db: Database) -> Dict[str, Any]:
    audit = coverage_audit(settings, db)
    wechat_enabled = bool(
        settings.reporting.get("collection", {}).get("wechat_enabled", True)
    )
    required_wechat = [
        source
        for source in audit["sources"]
        if source["priority"] == "required"
    ] if wechat_enabled else []
    required_ready = all(
        source["resolved"]
        and source["article_count"] > 0
        and source["history_boundary_reached"]
        and source["missing_body_count"] == 0
        for source in required_wechat
    )
    rss_sources = [
        source for source in settings.external_sources if source.capture_method == "rss"
    ]
    pending_external = [
        source
        for source in settings.external_sources
        if source.capture_method != "rss"
    ]
    required_pending_external = [
        source for source in pending_external if source.priority == "required"
    ]
    active_rss = int(audit["external_sources"]["active"])
    has_collectable_source = bool(
        (wechat_enabled and settings.accounts) or rss_sources
    )
    ready = bool(
        has_collectable_source
        and audit["article_count"] > 0
        and required_ready
        and (not rss_sources or active_rss > 0 or bool(settings.accounts))
    )
    return {
        "ready": ready,
        "wechat_enabled": wechat_enabled,
        "required_wechat_ready": sum(
            source["resolved"]
            and source["article_count"] > 0
            and source["history_boundary_reached"]
            and source["missing_body_count"] == 0
            for source in required_wechat
        ),
        "required_wechat_total": len(required_wechat),
        "active_rss": active_rss,
        "configured_rss": len(rss_sources),
        "pending_external": len(pending_external),
        "required_pending_external": len(required_pending_external),
        "required_pending_external_ids": [
            source.wechat_id for source in required_pending_external
        ],
        "article_count": audit["article_count"],
        "audit_status": audit["status"],
        "critical": audit["critical"],
        "warnings": audit["warnings"],
    }


def refresh_activation_state(
    settings: Settings,
    db: Database,
) -> Optional[Dict[str, Any]]:
    current = load_activation_state(settings)
    if not current or current.get("status") in WAITING_STATES:
        return current
    readiness = evaluate_activation_readiness(settings, db)
    if readiness["ready"]:
        if current.get("wechat_skipped"):
            status = "degraded"
        elif readiness.get("required_pending_external"):
            status = "active_with_gaps"
        else:
            status = "active"
    else:
        status = "readiness_review" if current.get("backfill_started") else "backfilling"
    return _write_state(settings, status, readiness=readiness)


def record_activation_schedule(
    settings: Settings,
    schedule: Dict[str, Any],
) -> Dict[str, Any]:
    current = load_activation_state(settings) or {}
    return _write_state(
        settings,
        str(current.get("status") or "configured"),
        schedule=schedule,
    )


def activation_approval(settings: Settings) -> Dict[str, Any]:
    state = load_activation_state(settings) or {}
    value = state.get("approval") or {}
    return value if isinstance(value, dict) else {}


def record_activation_approval(
    settings: Settings,
    *,
    collection: bool = False,
    schedule: bool = False,
    wechat_enable: bool = False,
) -> Dict[str, Any]:
    current = load_activation_state(settings) or {}
    previous = activation_approval(settings)
    approval = {
        **previous,
        "collection": bool(previous.get("collection") or collection),
        "schedule": bool(previous.get("schedule") or schedule),
        "wechat_enable": bool(previous.get("wechat_enable") or wechat_enable),
        "approved_at": datetime.now(
            ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
        ).isoformat(),
    }
    return _write_state(
        settings,
        str(current.get("status") or "configured"),
        approval=approval,
    )


def revoke_schedule_approval(settings: Settings) -> Dict[str, Any]:
    current = load_activation_state(settings) or {}
    previous = activation_approval(settings)
    approval = {
        **previous,
        "schedule": False,
        "schedule_revoked_at": datetime.now(
            ZoneInfo(settings.reporting.get("timezone", "Asia/Shanghai"))
        ).isoformat(),
    }
    return _write_state(
        settings,
        str(current.get("status") or "configured"),
        approval=approval,
        schedule={"status": "not_installed", "reason": "user_revoked"},
    )


def activate_subscription(
    settings: Settings,
    db: Database,
    *,
    wait_for_auth: bool = False,
    auth_timeout_seconds: int = 300,
    skip_wechat: bool = False,
    enable_wechat: bool = False,
) -> Dict[str, Any]:
    db.initialize(settings.all_sources)
    has_wechat = bool(settings.accounts)
    if enable_wechat and has_wechat:
        set_wechat_collection_enabled(settings, True)
    if skip_wechat and has_wechat:
        set_wechat_collection_enabled(settings, False)
    wechat_enabled = has_wechat and bool(
        settings.reporting.get("collection", {}).get("wechat_enabled", True)
    )

    auth: Dict[str, Any] = {"status": "not_required", "authorized": False}
    matching: Dict[str, Any] = {
        "added": [],
        "existing": [],
        "unresolved": [],
        "errors": [],
    }
    if wechat_enabled:
        try:
            auth = werss_wechat_auth_status(settings)
        except Exception as exc:
            return _write_state(
                settings,
                "needs_collector",
                error=f"{type(exc).__name__}: {exc}",
                next_command="scripts/setup_collection.sh",
            )
        if not auth["authorized"]:
            if wait_for_auth:
                auth = wait_for_werss_wechat_auth(settings, auth_timeout_seconds)
                if not auth["authorized"]:
                    return _write_state(settings, auth["status"], auth=auth)
            else:
                auth = start_werss_wechat_auth(settings)
                return _write_state(settings, "needs_auth", auth=auth)
        matching = subscribe_accounts(settings, dry_run=False)

    collection = ingest(settings, db, "auto")
    backfill: Dict[str, Any] = {"status": "not_required", "requested": []}
    if wechat_enabled:
        backfill = request_backfill(
            settings,
            db,
            int(
                settings.reporting.get("collection", {}).get(
                    "historical_backfill_batch_accounts", 1
                )
            ),
        )

    readiness = evaluate_activation_readiness(settings, db)
    has_collectable_source = bool(
        (wechat_enabled and settings.accounts)
        or any(
            source.capture_method == "rss" for source in settings.external_sources
        )
    )
    wechat_skipped = bool(has_wechat and not wechat_enabled)
    if readiness["ready"]:
        if wechat_skipped:
            status = "degraded"
        elif readiness.get("required_pending_external"):
            status = "active_with_gaps"
        else:
            status = "active"
    elif not has_collectable_source:
        status = "needs_source_review"
    elif matching["unresolved"] or matching["errors"]:
        status = "needs_source_review"
    else:
        status = "backfilling"
    return _write_state(
        settings,
        status,
        auth={"status": auth["status"], "authorized": bool(auth.get("authorized"))},
        wechat_skipped=wechat_skipped,
        matching=matching,
        collection=collection.as_dict(),
        backfill=backfill,
        backfill_started=bool(wechat_enabled),
        readiness=readiness,
    )
