from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import URLError
from urllib.request import urlopen

from . import __version__
from .ingest import werss_wechat_auth_status
from .settings import Settings
from .subscriptions import PRODUCT_NAME


def _codex_path(settings: Settings) -> str:
    configured = settings.env("CODEX_BIN")
    if configured and Path(configured).is_file():
        return configured
    bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if bundled.is_file():
        return str(bundled)
    return shutil.which("codex") or ""


def _entry(
    name: str,
    status: str,
    detail: str,
    *,
    required: bool,
) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "required": required,
        "detail": detail,
    }


def _werss_status(settings: Settings) -> Dict[str, str]:
    try:
        with urlopen(settings.werss_base_url, timeout=2) as response:
            return {
                "status": "pass" if response.status < 500 else "warn",
                "detail": f"{settings.werss_base_url} returned HTTP {response.status}",
            }
    except (OSError, URLError) as exc:
        return {
            "status": "warn",
            "detail": f"not reachable yet: {type(exc).__name__}",
        }


def run_doctor(settings: Settings, surface: str = "codex") -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    python_ok = sys.version_info >= (3, 9)
    checks.append(
        _entry(
            "python",
            "pass" if python_ok else "fail",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            required=True,
        )
    )

    required_paths = [
        settings.root / "bin/iread",
        settings.schema_dir / "research_proposal.schema.json",
        settings.schema_dir / "subscription_manifest.schema.json",
        settings.prompt_dir / "propose.md",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    checks.append(
        _entry(
            "project_layout",
            "fail" if missing else "pass",
            "missing: " + ", ".join(missing) if missing else str(settings.root),
            required=True,
        )
    )

    writable = os.access(settings.data_dir, os.W_OK) and os.access(
        settings.logs_dir, os.W_OK
    )
    checks.append(
        _entry(
            "local_storage",
            "pass" if writable else "fail",
            f"data={settings.data_dir}; logs={settings.logs_dir}",
            required=True,
        )
    )

    domains = settings.profile.domains or list(settings.topics.get("topics", []))
    checks.append(
        _entry(
            "active_configuration",
            "pass",
            f"{settings.profile.name}; {len(domains)} domain(s); {len(settings.all_sources)} source(s)",
            required=True,
        )
    )

    if surface == "codex":
        codex = _codex_path(settings)
        checks.append(
            _entry(
                "codex_cli",
                "pass" if codex else "fail",
                codex or "Codex CLI not found",
                required=True,
            )
        )
    elif surface == "workbuddy":
        adapter = settings.root / "integrations/work-buddy/install.sh"
        checks.append(
            _entry(
                "workbuddy_adapter",
                "pass" if adapter.is_file() else "fail",
                str(adapter),
                required=True,
            )
        )

    werss = _werss_status(settings)
    checks.append(
        _entry(
            "wechat_collection",
            werss["status"],
            werss["detail"],
            required=False,
        )
    )
    wechat_sources = list(settings.accounts)
    wechat_authorized = False
    if wechat_sources and werss["status"] == "pass":
        try:
            authorization = werss_wechat_auth_status(settings)
            wechat_authorized = bool(authorization["authorized"])
            checks.append(
                _entry(
                    "wechat_authorization",
                    "pass" if wechat_authorized else "warn",
                    "authorized locally"
                    if wechat_authorized
                    else "scan is required after source approval",
                    required=False,
                )
            )
        except Exception as exc:
            checks.append(
                _entry(
                    "wechat_authorization",
                    "warn",
                    f"could not verify: {type(exc).__name__}",
                    required=False,
                )
            )
    notion_ready = bool(
        settings.env("NOTION_TOKEN") and settings.env("NOTION_PARENT_PAGE_ID")
    )
    checks.append(
        _entry(
            "notion_output",
            "pass" if notion_ready else "warn",
            "configured" if notion_ready else "not configured; local Markdown remains available",
            required=False,
        )
    )

    required_failures = [
        check for check in checks if check["required"] and check["status"] == "fail"
    ]
    warnings = [check for check in checks if check["status"] == "warn"]
    return {
        "product": PRODUCT_NAME,
        "version": __version__,
        "surface": surface,
        "status": "blocked" if required_failures else "ready",
        "ready_for_domain_setup": not required_failures,
        "ready_for_collection": not required_failures
        and (
            any(source.capture_method == "rss" for source in settings.external_sources)
            or bool(wechat_sources and wechat_authorized)
        ),
        "checks": checks,
        "summary": {
            "passed": sum(check["status"] == "pass" for check in checks),
            "warnings": len(warnings),
            "failed": sum(check["status"] == "fail" for check in checks),
        },
    }
