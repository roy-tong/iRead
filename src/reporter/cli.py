from __future__ import annotations

import argparse
import fcntl
import json
import logging
import shlex
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from .analysis import enrich_pending
from .activation import (
    REPORT_READY_STATES,
    activation_approval,
    activate_subscription,
    load_activation_state,
    record_activation_approval,
    record_activation_schedule,
    refresh_activation_state,
    revoke_schedule_approval,
)
from .audit import audit_markdown, coverage_audit
from .control import capability_contract, evaluate_acceptance
from .db import Database
from .doctor import run_doctor
from .export import export_public_archive
from .feedback import list_feedback, record_feedback
from .ingest import (
    ingest,
    request_backfill,
    request_recent_refresh,
    start_werss_wechat_auth,
    subscribe_accounts,
    sync_werss_worker_feeds,
    wait_for_werss_wechat_auth,
    werss_wechat_auth_status,
)
from .notion import publish_report, verify_notion
from .operations import (
    acquire_request_lock,
    completed_request,
    error_code,
    fail_operation,
    finish_operation,
    intent_hash,
    operation_events,
    release_request_lock,
    start_operation,
    validate_request_id,
)
from .proposals import (
    apply_research_batch,
    apply_research_proposal,
    propose_research_batch,
    propose_research_setup,
    proposal_review_markdown,
    validate_research_proposal,
)
from .reports import due_report_kinds, generate_report, report_window
from .settings import Settings
from .source_quality import review_sources
from .subscriptions import PRODUCT_NAME, apply_research_subscription
from .workspace import inspect_workspace, list_reports, register_subscription


LOGGER = logging.getLogger(__name__)


class PipelineBusyError(RuntimeError):
    pass


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        _json(
            {
                "status": "error",
                "command": self.prog,
                "request_id": None,
                "error": {
                    "code": "invalid_request",
                    "type": "ArgumentError",
                    "message": message,
                },
            }
        )
        raise SystemExit(2)


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@contextmanager
def project_lock(settings: Settings) -> Iterator[None]:
    path = settings.data_dir / "pipeline.lock"
    with path.open("a+") as handle:
        deadline = time.monotonic() + 300
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise PipelineBusyError(
                        "Another pipeline process is still running after 300 seconds"
                    ) from exc
                time.sleep(1)
        yield


def _setup_logging(settings: Settings, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(settings.logs_dir / "pipeline.log", encoding="utf-8"),
        ],
    )


def _as_of(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _publish_requested(settings: Settings, args: argparse.Namespace) -> bool:
    return bool(
        args.publish
        or (
            not args.no_publish
            and settings.reporting.get("notion", {}).get("auto_publish", False)
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = StructuredArgumentParser(
        prog="iread",
        description="iRead: local professional information subscriptions and reports"
    )
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument(
        "--config-dir",
        help="Optional configuration directory. Missing files fall back to the repository config/ directory.",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--request-id",
        type=validate_request_id,
        help="Optional stable Agent request id used to skip a repeated successful mutation",
    )
    sub = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=StructuredArgumentParser,
    )

    sub.add_parser("init", help="Initialize the local research database")
    sub.add_parser(
        "capabilities",
        help="Show the machine-readable Agent capability and permission contract",
    )
    doctor = sub.add_parser("doctor", help="Check whether iRead is ready to use")
    doctor.add_argument(
        "--surface",
        choices=["codex", "claude-code", "doubao", "workbuddy", "cli"],
        default="codex",
    )
    sub.add_parser("profile", help="Show the active research profile and report policies")
    sub.add_parser("subscription", help="Show the active iRead subscription and domains")
    sub.add_parser("activation", help="Show the persisted onboarding and collection state")
    workspace = sub.add_parser(
        "workspace",
        help="List local subscriptions, reports, state, and recommended next actions",
    )
    workspace.add_argument(
        "--register",
        action="store_true",
        help="Register the selected --config-dir for discovery in future Codex tasks",
    )
    reports = sub.add_parser("reports", help="List generated local reports")
    reports.add_argument("--kind", choices=["daily", "weekly", "monthly"])
    reports.add_argument("--limit", type=int, default=20)
    sub.add_parser(
        "acceptance",
        help="Evaluate whether the selected subscription is operational and report-ready",
    )
    operations = sub.add_parser(
        "operations",
        help="Show recent local operation audit events",
    )
    operations.add_argument("--limit", type=int, default=50)
    schedule = sub.add_parser(
        "schedule",
        help="Inspect or remove recurring background execution",
    )
    schedule.add_argument("action", choices=["status", "uninstall"])
    schedule.add_argument(
        "--approved",
        action="store_true",
        help="Confirm removal of the selected subscription's recurring tasks",
    )
    feedback = sub.add_parser(
        "feedback",
        help="Record or list local user feedback for future reports",
    )
    feedback_actions = feedback.add_subparsers(
        dest="feedback_action",
        required=True,
        parser_class=StructuredArgumentParser,
    )
    feedback_add = feedback_actions.add_parser("add")
    feedback_add.add_argument(
        "--target", choices=["report", "source", "subscription"], required=True
    )
    feedback_add.add_argument("--target-id")
    feedback_add.add_argument(
        "--rating", choices=["up", "down", "neutral"], required=True
    )
    feedback_add.add_argument("--note")
    feedback_add.add_argument("--tag", action="append")
    feedback_list = feedback_actions.add_parser("list")
    feedback_list.add_argument(
        "--target", choices=["report", "source", "subscription"]
    )
    feedback_list.add_argument("--limit", type=int, default=20)

    wechat_auth = sub.add_parser(
        "wechat-auth",
        help="Start, wait for, or inspect local WeChat public-platform authorization",
    )
    wechat_auth.add_argument("action", choices=["status", "start", "wait"])
    wechat_auth.add_argument("--timeout", type=int, default=300)
    wechat_auth.add_argument("--qr-output")
    wechat_auth.add_argument(
        "--approved",
        action="store_true",
        help="Confirm starting local WeChat authorization",
    )

    activate = sub.add_parser(
        "activate",
        help="Authorize connectors, match sources, start one-month backfill, and schedule reports",
    )
    activate.add_argument("--wait-for-auth", action="store_true")
    activate.add_argument("--auth-timeout", type=int, default=300)
    activate.add_argument(
        "--approved",
        action="store_true",
        help="Confirm collection and any schedule or connector change requested by this command",
    )
    collection_mode = activate.add_mutually_exclusive_group()
    collection_mode.add_argument(
        "--skip-wechat",
        action="store_true",
        help="Explicitly continue with RSS and web sources without WeChat collection",
    )
    collection_mode.add_argument(
        "--enable-wechat",
        action="store_true",
        help="Re-enable WeChat collection after using RSS and web-only mode",
    )
    activate.add_argument("--install-schedule", action="store_true")

    sync = sub.add_parser("sync", help="Import articles from We-MP-RSS")
    sync.add_argument("--mode", choices=["auto", "werss_db", "rss"], default="auto")
    sync.add_argument("--skip-external", action="store_true")

    enrich = sub.add_parser("enrich", help="Classify and summarize pending articles with Codex")
    enrich.add_argument("--max-batches", type=int)
    enrich.add_argument("--start", help="Only analyze articles after this ISO datetime")
    enrich.add_argument("--end", help="Only analyze articles up to this ISO datetime")
    enrich.add_argument(
        "--report-ready",
        action="store_true",
        help="Skip articles without enough body, transcript, or description material",
    )

    sub.add_parser("audit", help="Audit source and article completeness")

    subscribe = sub.add_parser("subscribe", help="Search and subscribe configured accounts in We-MP-RSS")
    subscribe.add_argument("--dry-run", action="store_true")

    sub.add_parser(
        "sync-workers",
        help="Copy primary We-MP-RSS subscriptions to the configured worker nodes",
    )

    backfill = sub.add_parser("backfill", help="Request the next historical page batch from We-MP-RSS")
    backfill.add_argument("--max-accounts", type=int, default=1)

    recent = sub.add_parser("refresh-recent", help="Refresh page zero for the stalest WeChat feeds")
    recent.add_argument("--max-accounts", type=int, default=9)

    collect = sub.add_parser(
        "collect",
        help="Merge WeRSS nodes, refresh recent posts, and continue historical backfill",
    )
    collect.add_argument("--recent-accounts", type=int, default=9)
    collect.add_argument("--backfill-accounts", type=int, default=12)

    report = sub.add_parser("report", help="Generate one report")
    report.add_argument("kind", choices=["daily", "weekly", "monthly"])
    report.add_argument("--as-of")
    report.add_argument("--force", action="store_true")
    report_publish = report.add_mutually_exclusive_group()
    report_publish.add_argument("--publish", action="store_true")
    report_publish.add_argument("--no-publish", action="store_true")
    report.add_argument("--skip-enrich", action="store_true")

    publish = sub.add_parser("publish", help="Publish an existing report to Notion")
    publish.add_argument("report_id", type=int)
    publish.add_argument("--force", action="store_true")

    export = sub.add_parser("export", help="Export a public archive for GitHub or static hosting")
    export.add_argument("--output-dir", default="public/archive")
    export.add_argument("--include-content", action="store_true")
    export.add_argument(
        "--rights-confirmed",
        action="store_true",
        help="Required with --include-content after confirming publication rights for every exported source.",
    )
    export.add_argument("--max-content-chars", type=int)
    export.add_argument(
        "--articles-per-source",
        type=int,
        help="Export only the newest N articles for each source.",
    )
    export.add_argument(
        "--omit-descriptions",
        action="store_true",
        help="Exclude publisher-provided descriptions from the public archive.",
    )

    source_review = sub.add_parser(
        "sources-review",
        help="Rate configured sources and select representative works",
    )
    source_review.add_argument("--output", help="Optional JSON output path")
    source_review.add_argument("--representative-works", type=int)

    propose = sub.add_parser(
        "propose",
        help="Propose a research profile, source list, and report presets from a field",
    )
    propose.add_argument("--field", required=True)
    propose.add_argument("--audience", action="append")
    propose.add_argument("--goal", action="append")
    propose.add_argument("--language", action="append")
    propose.add_argument("--region", action="append")
    propose.add_argument("--max-sources", type=int, default=20)
    propose.add_argument("--output")

    apply_proposal = sub.add_parser(
        "apply-proposal",
        help="Create a configuration directory from a reviewed proposal",
    )
    apply_proposal.add_argument("proposal")
    apply_proposal.add_argument("--output-dir", required=True)
    apply_proposal.add_argument("--preset", choices=["light", "standard", "deep"], default="standard")
    apply_proposal.add_argument("--history-start")
    apply_proposal.add_argument("--force", action="store_true")

    validate_proposal = sub.add_parser(
        "validate-proposal",
        help="Validate an agent-authored research proposal before review or apply",
    )
    validate_proposal.add_argument("proposal")
    validate_proposal.add_argument(
        "--lenient",
        action="store_true",
        help="Allow small fixtures while still checking proposal structure",
    )

    review_proposal = sub.add_parser(
        "review-proposal",
        help="Create a complete human-readable source review from a validated proposal",
    )
    review_proposal.add_argument("proposal")
    review_proposal.add_argument("--output")

    batch_propose = sub.add_parser(
        "batch-propose",
        help="Generate resumable research proposals from a batch manifest",
    )
    batch_propose.add_argument("manifest")
    batch_propose.add_argument("--output-dir", required=True)
    batch_propose.add_argument("--no-resume", action="store_true")
    batch_propose.add_argument("--force", action="store_true")
    batch_propose.add_argument("--fail-fast", action="store_true")

    batch_apply = sub.add_parser(
        "batch-apply",
        help="Create configuration directories for approved batch proposals",
    )
    batch_apply.add_argument("manifest")
    batch_apply.add_argument("--proposals-dir", required=True)
    batch_apply.add_argument("--profiles-dir", required=True)
    approval = batch_apply.add_mutually_exclusive_group(required=True)
    approval.add_argument("--approved", action="append")
    approval.add_argument("--approve-all", action="store_true")
    batch_apply.add_argument("--force", action="store_true")

    apply_subscription = sub.add_parser(
        "apply-subscription",
        help="Merge approved domain proposals into one iRead subscription",
    )
    apply_subscription.add_argument("manifest")
    apply_subscription.add_argument("--proposals-dir", required=True)
    apply_subscription.add_argument("--output-dir", required=True)
    subscription_approval = apply_subscription.add_mutually_exclusive_group(required=True)
    subscription_approval.add_argument("--approved", action="append")
    subscription_approval.add_argument("--approve-all", action="store_true")
    apply_subscription.add_argument("--id")
    apply_subscription.add_argument("--name")
    apply_subscription.add_argument(
        "--preset", choices=["light", "standard", "deep"]
    )
    apply_subscription.add_argument("--history-start")
    apply_subscription.add_argument("--force", action="store_true")

    sub.add_parser("notion-test", help="Verify Notion credentials and parent page access")

    run = sub.add_parser("run", help="Run sync, enrichment, and due local reports")
    run.add_argument("--as-of")
    run.add_argument("--skip-sync", action="store_true")
    run_publish = run.add_mutually_exclusive_group()
    run_publish.add_argument("--publish", action="store_true")
    run_publish.add_argument("--no-publish", action="store_true")
    run.add_argument("--max-batches", type=int)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root)
    selected_config_dir = Path(args.config_dir) if args.config_dir else None
    if args.command == "subscription" and selected_config_dir is None:
        workspace = inspect_workspace(project_root)
        recommended = workspace.get("recommended_config_dir")
        if recommended:
            selected_config_dir = Path(str(recommended))
        else:
            _json(
                {
                    "product": PRODUCT_NAME,
                    "status": "not_configured",
                    "subscription": None,
                    "next_action": workspace["next_action"],
                }
            )
            return 0
    settings = Settings.load(
        project_root,
        selected_config_dir,
    )
    _setup_logging(settings, args.verbose)
    db = Database(settings.db_path)
    request_id = args.request_id
    operation_intent = intent_hash(
        {
            key: value
            for key, value in vars(args).items()
            if key not in {"request_id", "verbose", "project_root"}
        }
    )
    lock_free_commands = {
        "doctor",
        "capabilities",
        "profile",
        "subscription",
        "activation",
        "workspace",
        "reports",
        "acceptance",
        "operations",
        "schedule",
        "feedback",
        "wechat-auth",
        "propose",
        "apply-proposal",
        "validate-proposal",
        "review-proposal",
        "batch-propose",
        "batch-apply",
        "apply-subscription",
        "notion-test",
    }
    mutating_commands = {
        "init",
        "activate",
        "sync",
        "enrich",
        "subscribe",
        "sync-workers",
        "backfill",
        "refresh-recent",
        "collect",
        "report",
        "publish",
        "export",
        "propose",
        "apply-proposal",
        "batch-propose",
        "batch-apply",
        "apply-subscription",
        "review-proposal",
        "run",
    }
    is_mutating = args.command in mutating_commands or (
        args.command == "wechat-auth" and args.action != "status"
    ) or (args.command == "workspace" and args.register) or (
        args.command == "sources-review" and bool(args.output)
    ) or (
        args.command == "feedback" and args.feedback_action == "add"
    ) or (
        args.command == "schedule" and args.action == "uninstall"
    )
    operation_id: Optional[str] = None
    request_lock_handle = None
    try:
        if is_mutating and request_id:
            request_lock_handle = acquire_request_lock(
                settings, args.command, request_id
            )
        if is_mutating and (
            previous := completed_request(
                settings,
                args.command,
                request_id,
                operation_intent,
            )
        ):
            _json(
                {
                    "status": "skipped",
                    "reason": "request_already_completed",
                    "request_id": request_id,
                    "previous_operation_id": previous["operation_id"],
                    "previous_completed_at": previous["at"],
                }
            )
            release_request_lock(request_lock_handle)
            return 0
        if is_mutating:
            operation_id = start_operation(
                settings,
                args.command,
                request_id,
                operation_intent,
            )
        if args.command not in lock_free_commands:
            db.initialize(settings.all_sources)
        needs_project_lock = args.command not in lock_free_commands or (
            args.command == "schedule" and args.action == "uninstall"
        )
        lock = project_lock(settings) if needs_project_lock else nullcontext()
        with lock:
            if args.command == "init":
                _json(
                    {
                        "database": str(settings.db_path),
                        "config_dir": str(settings.config_dir),
                        "profile": settings.profile.as_dict(),
                        "wechat_accounts": len(settings.accounts),
                        "external_sources": len(settings.external_sources),
                    }
                )
            elif args.command == "capabilities":
                _json(capability_contract(settings.root))
            elif args.command == "doctor":
                _json(run_doctor(settings, args.surface))
            elif args.command == "profile":
                _json(
                    {
                        "profile": settings.profile.as_dict(),
                        "topics": settings.topics,
                        "source_policy": settings.source_policy,
                        "reporting": {
                            kind: settings.reporting[kind]
                            for kind in ("daily", "weekly", "monthly")
                        },
                    }
                )
            elif args.command == "subscription":
                domains = settings.profile.domains or [
                    {
                        "id": str(topic.get("id") or ""),
                        "name": str(topic.get("name") or ""),
                        "topic_ids": [
                            str(item.get("id") or "")
                            for item in topic.get("secondaries", [])
                            if isinstance(item, dict)
                        ],
                    }
                    for topic in settings.topics.get("topics", [])
                    if isinstance(topic, dict)
                ]
                _json(
                    {
                        "product": PRODUCT_NAME,
                        "subscription": {
                            "id": settings.profile.id,
                            "name": settings.profile.name,
                            "domains": domains,
                        },
                        "sources": {
                            "wechat": len(settings.accounts),
                            "external": len(settings.external_sources),
                            "total": len(settings.all_sources),
                        },
                        "history_start": settings.history_start.isoformat(),
                        "report_preset": settings.reporting.get("strategy_preset"),
                    }
                )
            elif args.command == "activation":
                _json(
                    load_activation_state(settings)
                    or {
                        "status": "not_started",
                        "config_dir": str(settings.config_dir),
                    }
                )
            elif args.command == "workspace":
                result = inspect_workspace(
                    settings.root,
                    selected_config_dir=settings.config_dir
                    if args.config_dir
                    else None,
                )
                if args.register:
                    result["registered"] = register_subscription(
                        settings.config_dir,
                        settings.root,
                    )
                    result = {
                        **inspect_workspace(
                            settings.root,
                            selected_config_dir=settings.config_dir,
                        ),
                        "registered": result["registered"],
                    }
                _json(result)
            elif args.command == "reports":
                _json(
                    {
                        "config_dir": str(settings.config_dir),
                        **list_reports(
                            settings.db_path,
                            kind=args.kind,
                            limit=args.limit,
                        ),
                    }
                )
            elif args.command == "acceptance":
                _json(evaluate_acceptance(settings))
            elif args.command == "operations":
                _json(operation_events(settings, args.limit))
            elif args.command == "schedule":
                workspace = inspect_workspace(
                    settings.root,
                    selected_config_dir=settings.config_dir,
                )
                selected = next(
                    (
                        item
                        for item in workspace["subscriptions"]
                        if Path(item["config_dir"]).resolve()
                        == settings.config_dir.resolve()
                    ),
                    None,
                )
                if args.action == "status":
                    _json(
                        {
                            "config_dir": str(settings.config_dir),
                            "schedule": (selected or {}).get("schedule")
                            or {"status": "not_installed"},
                        }
                    )
                else:
                    if not args.approved:
                        raise PermissionError(
                            "Removing recurring tasks requires explicit approval; rerun with --approved"
                        )
                    completed = subprocess.run(
                        [
                            str(settings.root / "scripts/uninstall_schedule.sh"),
                            "--config-dir",
                            str(settings.config_dir),
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                    if completed.returncode != 0:
                        raise RuntimeError(
                            (completed.stderr or completed.stdout).strip()
                            or "Schedule removal failed"
                        )
                    state = revoke_schedule_approval(settings)
                    _json(
                        {
                            "status": "not_installed",
                            "config_dir": str(settings.config_dir),
                            "detail": completed.stdout.strip(),
                            "activation": state,
                        }
                    )
            elif args.command == "feedback":
                if args.feedback_action == "add":
                    _json(
                        record_feedback(
                            settings,
                            target=args.target,
                            target_id=args.target_id,
                            rating=args.rating,
                            note=args.note,
                            tags=args.tag,
                        )
                    )
                else:
                    _json(
                        list_feedback(
                            settings,
                            target=args.target,
                            limit=args.limit,
                        )
                    )
            elif args.command == "wechat-auth":
                if args.action == "status":
                    _json(werss_wechat_auth_status(settings))
                elif args.action == "start":
                    if not (
                        args.approved
                        or activation_approval(settings).get("collection")
                    ):
                        raise PermissionError(
                            "Starting WeChat authorization requires explicit approval; rerun with --approved"
                        )
                    _json(
                        start_werss_wechat_auth(
                            settings,
                            settings.resolve_path(args.qr_output)
                            if args.qr_output
                            else None,
                            min(max(args.timeout, 1), 120),
                        )
                    )
                else:
                    _json(wait_for_werss_wechat_auth(settings, args.timeout))
            elif args.command == "activate":
                approval = activation_approval(settings)
                if not approval.get("collection") and not args.approved:
                    raise PermissionError(
                        "Starting collection requires explicit approval; rerun with --approved"
                    )
                if args.enable_wechat and not args.approved:
                    raise PermissionError(
                        "Enabling WeChat collection requires explicit approval; rerun with --approved"
                    )
                if (
                    args.install_schedule
                    and not approval.get("schedule")
                    and not args.approved
                ):
                    raise PermissionError(
                        "Installing a schedule requires explicit approval; rerun with --approved"
                    )
                if args.approved:
                    record_activation_approval(
                        settings,
                        collection=True,
                        schedule=args.install_schedule,
                        wechat_enable=args.enable_wechat,
                    )
                activation = activate_subscription(
                    settings,
                    db,
                    wait_for_auth=args.wait_for_auth,
                    auth_timeout_seconds=args.auth_timeout,
                    skip_wechat=args.skip_wechat,
                    enable_wechat=args.enable_wechat,
                )
                if args.install_schedule and activation["status"] not in {
                    "needs_collector",
                    "needs_auth",
                    "auth_timeout",
                    "needs_source_review",
                }:
                    installer = settings.root / "scripts" / "install_schedule.sh"
                    completed = subprocess.run(
                        [str(installer), "--config-dir", str(settings.config_dir)],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                    schedule = {
                        "status": "installed" if completed.returncode == 0 else "failed",
                        "detail": (completed.stdout or completed.stderr).strip()[-2000:],
                    }
                    activation = record_activation_schedule(settings, schedule)
                _json(activation)
            elif args.command == "sync":
                _json(
                    ingest(
                        settings,
                        db,
                        args.mode,
                        include_external=not args.skip_external,
                    ).as_dict()
                )
            elif args.command == "enrich":
                start = _as_of(args.start)
                end = _as_of(args.end)
                _json(
                    enrich_pending(
                        settings,
                        db,
                        args.max_batches,
                        int(start.timestamp()) if start else None,
                        int(end.timestamp()) if end else None,
                        args.report_ready,
                    )
                )
            elif args.command == "audit":
                audit = coverage_audit(settings, db)
                print(audit_markdown(audit))
                _json(audit)
            elif args.command == "subscribe":
                _json(subscribe_accounts(settings, args.dry_run))
            elif args.command == "sync-workers":
                _json(sync_werss_worker_feeds(settings))
            elif args.command == "backfill":
                _json(request_backfill(settings, db, args.max_accounts))
            elif args.command == "refresh-recent":
                _json(request_recent_refresh(settings, db, args.max_accounts))
            elif args.command == "collect":
                wechat_enabled = bool(
                    settings.reporting.get("collection", {}).get(
                        "wechat_enabled", True
                    )
                )
                result = {
                    "sync": ingest(
                        settings,
                        db,
                        "werss_db",
                        include_external=not wechat_enabled,
                    ).as_dict(),
                    "recent": request_recent_refresh(
                        settings,
                        db,
                        args.recent_accounts,
                    )
                    if wechat_enabled
                    else {"status": "disabled", "requested": []},
                    "backfill": request_backfill(
                        settings,
                        db,
                        args.backfill_accounts,
                    )
                    if wechat_enabled
                    else {"status": "disabled", "requested": []},
                }
                result["activation"] = refresh_activation_state(settings, db)
                _json(result)
            elif args.command == "report":
                as_of = _as_of(args.as_of)
                start, end = report_window(settings, args.kind, as_of)
                finalization = None
                if not args.skip_enrich:
                    finalization = enrich_pending(
                        settings,
                        db,
                        start_ts=int(start.timestamp()),
                        end_ts=int(end.timestamp()),
                        require_report_content=True,
                    )
                    if finalization["remaining"]:
                        raise RuntimeError(
                            f"Report window still has {finalization['remaining']} eligible articles awaiting analysis"
                        )
                result = generate_report(settings, db, args.kind, as_of, args.force)
                if finalization is not None:
                    result["finalization"] = finalization
                publish_requested = _publish_requested(settings, args)
                if publish_requested:
                    result["notion"] = publish_report(settings, db, int(result["report_id"]), args.force)
                _json(result)
            elif args.command == "publish":
                _json(publish_report(settings, db, args.report_id, args.force))
            elif args.command == "export":
                _json(
                    export_public_archive(
                        settings,
                        db,
                        Path(args.output_dir),
                        include_content=args.include_content,
                        rights_confirmed=args.rights_confirmed,
                        max_content_chars=args.max_content_chars,
                        articles_per_source=args.articles_per_source,
                        include_descriptions=not args.omit_descriptions,
                    )
                )
            elif args.command == "sources-review":
                review = review_sources(
                    settings,
                    db,
                    representative_works=args.representative_works,
                )
                if args.output:
                    output_path = settings.resolve_path(args.output)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(
                        json.dumps(review, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    _json({**review["summary"], "output": str(output_path)})
                else:
                    _json(review)
            elif args.command == "propose":
                proposal = propose_research_setup(
                    settings,
                    args.field,
                    audiences=args.audience,
                    goals=args.goal,
                    languages=args.language,
                    regions=args.region,
                    max_sources=args.max_sources,
                )
                if args.output:
                    output_path = settings.resolve_path(args.output)
                else:
                    profile_id = proposal["research_profile"]["id"]
                    output_path = settings.data_dir / "proposals" / f"{profile_id}.json"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(proposal, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                _json(
                    {
                        "profile": proposal["research_profile"],
                        "source_candidates": len(proposal["sources"]),
                        "report_presets": [item["id"] for item in proposal["report_presets"]],
                        "output": str(output_path),
                    }
                )
            elif args.command == "apply-proposal":
                proposal_path = settings.resolve_path(args.proposal)
                proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                validate_research_proposal(proposal, strict=True)
                _json(
                    apply_research_proposal(
                        settings,
                        proposal,
                        settings.resolve_path(args.output_dir),
                        preset_id=args.preset,
                        history_start=args.history_start,
                        force=args.force,
                    )
                )
            elif args.command == "validate-proposal":
                proposal_path = settings.resolve_path(args.proposal)
                proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                _json(
                    {
                        **validate_research_proposal(
                            proposal,
                            strict=not args.lenient,
                        ),
                        "proposal": str(proposal_path),
                    }
                )
            elif args.command == "review-proposal":
                proposal_path = settings.resolve_path(args.proposal)
                proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                markdown = proposal_review_markdown(proposal)
                output_path = (
                    settings.resolve_path(args.output)
                    if args.output
                    else proposal_path.with_suffix(".review.md")
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(markdown + "\n", encoding="utf-8")
                validation = validate_research_proposal(proposal, strict=True)
                _json({**validation, "output": str(output_path)})
            elif args.command == "batch-propose":
                manifest_path = settings.resolve_path(args.manifest)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                _json(
                    propose_research_batch(
                        settings,
                        manifest,
                        settings.resolve_path(args.output_dir),
                        resume=not args.no_resume,
                        force=args.force,
                        continue_on_error=not args.fail_fast,
                    )
                )
            elif args.command == "batch-apply":
                manifest_path = settings.resolve_path(args.manifest)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                _json(
                    apply_research_batch(
                        settings,
                        manifest,
                        settings.resolve_path(args.proposals_dir),
                        settings.resolve_path(args.profiles_dir),
                        approved=args.approved,
                        approve_all=args.approve_all,
                        force=args.force,
                        strict=True,
                    )
                )
            elif args.command == "apply-subscription":
                manifest_path = settings.resolve_path(args.manifest)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                result = apply_research_subscription(
                    settings,
                    manifest,
                    settings.resolve_path(args.proposals_dir),
                    settings.resolve_path(args.output_dir),
                    approved=args.approved,
                    approve_all=args.approve_all,
                    subscription_id=args.id,
                    subscription_name=args.name,
                    preset_id=args.preset,
                    history_start=args.history_start,
                    force=args.force,
                )
                try:
                    result["registration"] = {
                        "status": "registered",
                        **register_subscription(
                            Path(result["output_dir"]),
                            settings.root,
                        ),
                    }
                except OSError as exc:
                    result["registration"] = {
                        "status": "warning",
                        "error": f"{type(exc).__name__}: {exc}",
                        "recovery_command": (
                            "bin/iread --config-dir "
                            f"{shlex.quote(str(result['output_dir']))} "
                            "workspace --register"
                        ),
                    }
                _json(result)
            elif args.command == "notion-test":
                _json(verify_notion(settings))
            elif args.command == "run":
                result: Dict[str, Any] = {}
                if not args.skip_sync:
                    result["sync"] = ingest(settings, db, "auto").as_dict()
                result["reports"] = []
                as_of = _as_of(args.as_of)
                due_kinds = due_report_kinds(settings, as_of)
                windows = [report_window(settings, kind, as_of) for kind in due_kinds]
                if windows:
                    analysis_start = min(start for start, _ in windows)
                    analysis_end = max(end for _, end in windows)
                    result["enrich"] = enrich_pending(
                        settings,
                        db,
                        args.max_batches,
                        int(analysis_start.timestamp()),
                        int(analysis_end.timestamp()),
                        True,
                    )
                else:
                    result["enrich"] = enrich_pending(settings, db, args.max_batches)
                result["audit"] = coverage_audit(settings, db)
                result["activation"] = refresh_activation_state(settings, db)
                skip_reason = None
                if result["audit"]["article_count"] == 0:
                    skip_reason = "No articles have been collected yet"
                elif result["activation"] and result["activation"].get(
                    "status"
                ) not in REPORT_READY_STATES:
                    skip_reason = "Initial collection has not passed readiness review"
                elif result["enrich"]["remaining"]:
                    skip_reason = (
                        f"Report window still has {result['enrich']['remaining']} eligible articles awaiting analysis"
                    )
                if skip_reason:
                    result["reports"].append({"status": "skipped", "reason": skip_reason})
                else:
                    notion_ready = bool(
                        settings.env("NOTION_TOKEN")
                        and settings.env("NOTION_PARENT_PAGE_ID")
                    )
                    for kind in due_kinds:
                        report = generate_report(settings, db, kind, as_of)
                        publish_requested = _publish_requested(settings, args)
                        if publish_requested and notion_ready:
                            report["notion"] = publish_report(
                                settings,
                                db,
                                int(report["report_id"]),
                            )
                        elif publish_requested:
                            report["notion"] = {
                                "status": "skipped",
                                "reason": "Notion is not configured; local report was generated",
                            }
                        result["reports"].append(report)
                _json(result)
        if operation_id:
            finish_operation(
                settings,
                operation_id,
                args.command,
                request_id,
                operation_intent,
            )
        release_request_lock(request_lock_handle)
        return 0
    except PipelineBusyError as exc:
        if operation_id:
            finish_operation(
                settings,
                operation_id,
                args.command,
                request_id,
                operation_intent,
                outcome="pipeline_busy",
            )
        release_request_lock(request_lock_handle)
        _json(
            {
                "status": "skipped",
                "reason": "pipeline_busy",
                "detail": str(exc),
            }
        )
        return 0
    except Exception as exc:
        if operation_id:
            fail_operation(
                settings,
                operation_id,
                args.command,
                request_id,
                operation_intent,
                exc,
            )
        release_request_lock(request_lock_handle)
        if args.verbose:
            LOGGER.exception("Pipeline command failed")
        else:
            LOGGER.debug("Pipeline command failed", exc_info=True)
        _json(
            {
                "status": "error",
                "command": args.command,
                "request_id": request_id,
                "error": {
                    "code": error_code(exc),
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
