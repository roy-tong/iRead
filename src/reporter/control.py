from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .settings import Settings
from .subscriptions import PRODUCT_NAME
from .workspace import active_config_dir, summarize_subscription


CONTROL_PROTOCOL_VERSION = 1


def capability_contract(root: Path) -> Dict[str, Any]:
    schema_dir = root.resolve() / "schemas"
    return {
        "product": PRODUCT_NAME,
        "version": __version__,
        "protocol_version": CONTROL_PROTOCOL_VERSION,
        "interface": "structured_cli",
        "permission_levels": {
            "local_read": "Reads local configuration, state, indexes, or reports.",
            "local_write": "Writes local configuration, state, analysis, or reports.",
            "network_read": "Fetches remote source material without changing user accounts.",
            "sensitive_auth": "Starts or consumes local account authorization state.",
            "scheduler": "Installs or changes recurring background execution.",
            "external_write": "Publishes data to an external service.",
        },
        "schemas": {
            "capabilities": str(schema_dir / "agent_capabilities.schema.json"),
            "acceptance": str(schema_dir / "acceptance.schema.json"),
            "error": str(schema_dir / "error_response.schema.json"),
            "operations": str(schema_dir / "operation_events.schema.json"),
            "feedback_list": str(schema_dir / "feedback_list.schema.json"),
        },
        "execution_contract": {
            "result_format": "json",
            "error_format": "json",
            "request_id_option": "--request-id",
            "request_id_scope": "one unchanged mutation intent",
            "mutations_audited": True,
            "audit_command": "operations",
            "acceptance_command": "acceptance",
        },
        "capabilities": [
            {
                "id": "inspect_workspace",
                "cli": "workspace",
                "description": "Discover subscriptions and recommended next actions.",
                "permissions": ["local_read"],
                "side_effects": [],
                "approval": "none",
                "idempotency": "safe_read",
            },
            {
                "id": "list_reports",
                "cli": "reports [--kind KIND] [--limit N]",
                "description": "Locate existing local daily, weekly, or monthly reports.",
                "permissions": ["local_read"],
                "side_effects": [],
                "approval": "none",
                "idempotency": "safe_read",
            },
            {
                "id": "validate_outcome",
                "cli": "acceptance",
                "description": "Evaluate whether a subscription is operational and report-ready.",
                "permissions": ["local_read"],
                "side_effects": [],
                "approval": "none",
                "idempotency": "safe_read",
            },
            {
                "id": "propose_domains",
                "cli": "batch-propose MANIFEST --output-dir DIR",
                "description": "Create resumable source proposals for one or more domains.",
                "permissions": ["local_write", "network_read"],
                "side_effects": ["writes_proposals", "model_usage"],
                "approval": "user_goal_is_sufficient",
                "idempotency": "resume_by_output_path",
            },
            {
                "id": "apply_subscription",
                "cli": "apply-subscription MANIFEST --approved DOMAIN --output-dir DIR",
                "description": "Create one subscription from explicitly approved domains.",
                "permissions": ["local_write"],
                "side_effects": ["writes_configuration", "registers_subscription"],
                "approval": "explicit_domain_and_source_approval_required",
                "idempotency": "refuses_existing_output_without_force",
            },
            {
                "id": "activate_collection",
                "cli": "activate --approved [--wait-for-auth] [--install-schedule]",
                "description": "Authorize connectors, match sources, backfill, and optionally schedule reports.",
                "permissions": ["local_write", "network_read", "sensitive_auth"],
                "side_effects": ["starts_collection", "may_show_local_qr"],
                "approval": "explicit_collection_approval_required",
                "idempotency": "resumable_state_machine",
            },
            {
                "id": "install_schedule",
                "cli": "activate --approved --install-schedule",
                "description": "Install recurring collection, analysis, reporting, and archive jobs.",
                "permissions": ["local_write", "scheduler"],
                "side_effects": ["changes_background_jobs"],
                "approval": "explicit_schedule_approval_required",
                "idempotency": "same_config_is_repeatable",
            },
            {
                "id": "remove_schedule",
                "cli": "schedule uninstall --approved",
                "description": "Stop recurring background execution without deleting local data.",
                "permissions": ["local_write", "scheduler"],
                "side_effects": ["removes_background_jobs", "revokes_schedule_approval"],
                "approval": "explicit_schedule_removal_approval_required",
                "idempotency": "safe_when_already_removed",
            },
            {
                "id": "continue_collection",
                "cli": "collect",
                "description": "Run one resumable collection and historical backfill step.",
                "permissions": ["local_write", "network_read"],
                "side_effects": ["updates_local_database", "requests_source_pages"],
                "approval": "prior_collection_approval_or_explicit_request",
                "idempotency": "request_id_supported",
            },
            {
                "id": "generate_report",
                "cli": "report KIND --no-publish",
                "description": "Generate or reuse a local report for a report window.",
                "permissions": ["local_write"],
                "side_effects": ["model_usage", "writes_local_report"],
                "approval": "explicit_generation_request_or_approved_schedule",
                "idempotency": "report_window_unique_unless_force",
            },
            {
                "id": "publish_report",
                "cli": "publish REPORT_ID",
                "description": "Publish an existing report to configured Notion.",
                "permissions": ["external_write"],
                "side_effects": ["creates_or_updates_notion_page"],
                "approval": "explicit_publication_approval_required",
                "idempotency": "report_id_reused_unless_force",
            },
            {
                "id": "export_archive",
                "cli": "export --output-dir DIR",
                "description": "Write a metadata and structured-analysis archive locally.",
                "permissions": ["local_write"],
                "side_effects": ["writes_local_archive"],
                "approval": "explicit_export_request",
                "idempotency": "replaces_generated_index_files",
            },
            {
                "id": "record_feedback",
                "cli": "feedback add --target TARGET --rating RATING [--note NOTE]",
                "description": "Persist user feedback for future reports and source review.",
                "permissions": ["local_write"],
                "side_effects": ["writes_local_feedback"],
                "approval": "explicit_user_feedback",
                "idempotency": "request_id_supported",
            },
        ],
    }


def _check(
    check_id: str,
    status: str,
    detail: str,
    *,
    required: bool,
    remediation: Optional[str] = None,
) -> Dict[str, Any]:
    result = {
        "id": check_id,
        "status": status,
        "required": required,
        "detail": detail,
    }
    if remediation and status != "pass":
        result["remediation"] = remediation
    return result


def evaluate_acceptance(settings: Settings) -> Dict[str, Any]:
    active = active_config_dir(settings.root)
    summary = summarize_subscription(
        settings.root,
        settings.config_dir,
        active=bool(active and active.resolve() == settings.config_dir.resolve()),
    )
    checks: List[Dict[str, Any]] = []
    if summary is None:
        checks.append(
            _check(
                "configuration",
                "fail",
                f"No iRead profile found in {settings.config_dir}",
                required=True,
                remediation="Create or select a reviewed subscription.",
            )
        )
    else:
        domain_count = len(summary["domains"])
        source_count = int(summary["sources"]["wechat"]) + int(
            summary["sources"]["external"]
        )
        checks.append(
            _check(
                "configuration",
                "pass" if domain_count and source_count else "fail",
                f"{domain_count} domain(s); {source_count} source(s)",
                required=True,
                remediation="Review and apply at least one domain with sources.",
            )
        )
        context_ready = bool(summary["registered"] or summary["active_schedule"])
        checks.append(
            _check(
                "context_continuity",
                "pass" if context_ready else "fail",
                "discoverable in future Codex tasks"
                if context_ready
                else "configuration is neither registered nor scheduled",
                required=True,
                remediation=(
                    f"Run bin/iread --config-dir '{settings.config_dir}' "
                    "workspace --register"
                ),
            )
        )
        status = str(summary["status"])
        if status == "active":
            activation_status = "pass"
        elif status in {"active_with_gaps", "degraded", "active_unverified"}:
            activation_status = "warn"
        else:
            activation_status = "fail"
        checks.append(
            _check(
                "activation",
                activation_status,
                status,
                required=True,
                remediation="Follow the first workspace next_action and rerun acceptance.",
            )
        )
        articles = int(summary["articles"])
        checks.append(
            _check(
                "collection",
                "pass" if articles else "fail",
                f"{articles} article(s) collected",
                required=True,
                remediation="Continue collection and the one-month backfill.",
            )
        )
        failed_analysis = int(summary["failed_analysis"])
        pending_analysis = int(summary["pending_analysis"])
        analysis_status = "warn" if failed_analysis or pending_analysis else "pass"
        checks.append(
            _check(
                "analysis_health",
                analysis_status,
                (
                    f"{pending_analysis} pending; "
                    f"{failed_analysis} failed"
                ),
                required=False,
                remediation="Continue pending analysis and inspect failed items before the next report window.",
            )
        )
        schedule_status = str((summary.get("schedule") or {}).get("status") or "missing")
        checks.append(
            _check(
                "schedule",
                "pass" if schedule_status == "installed" else "fail",
                schedule_status,
                required=True,
                remediation="Install the schedule after explicit user approval.",
            )
        )
        existing_reports = [
            item
            for item in summary["latest_reports"].values()
            if item.get("exists")
        ]
        checks.append(
            _check(
                "report_delivery",
                "pass" if existing_reports else "fail",
                f"{summary['report_count']} indexed report(s); {len(existing_reports)} latest file(s) available",
                required=True,
                remediation="Generate the first local report after collection is ready.",
            )
        )
        readiness = ((summary.get("activation") or {}).get("readiness") or {})
        critical = int(readiness.get("critical") or 0)
        required_pending = int(readiness.get("required_pending_external") or 0)
        coverage_status = "fail" if critical else "warn" if required_pending else "pass"
        checks.append(
            _check(
                "coverage_quality",
                coverage_status,
                f"{critical} critical; {required_pending} required external source(s) pending",
                required=False,
                remediation="Run audit and connect or explicitly waive required source gaps.",
            )
        )

    failures = [item for item in checks if item["required"] and item["status"] == "fail"]
    warnings = [item for item in checks if item["status"] == "warn"]
    accepted = not failures
    quality = "blocked" if failures else "accepted_with_warnings" if warnings else "accepted"
    return {
        "product": PRODUCT_NAME,
        "version": __version__,
        "protocol_version": CONTROL_PROTOCOL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_dir": str(settings.config_dir),
        "accepted": accepted,
        "quality": quality,
        "checks": checks,
        "summary": {
            "passed": sum(item["status"] == "pass" for item in checks),
            "warnings": len(warnings),
            "failed": len(failures),
        },
    }
