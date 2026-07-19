from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from reporter.activation import (
    activate_subscription,
    evaluate_activation_readiness,
    load_activation_state,
)
from reporter.audit import coverage_audit
from reporter.cli import PipelineBusyError, build_parser, project_lock
from reporter.db import Database
from reporter.ingest import IngestResult, start_werss_wechat_auth
from reporter.proposals import _one_calendar_month_ago
from reporter.settings import Settings


ROOT = Path(__file__).resolve().parents[1]


class ActivationTests(unittest.TestCase):
    def test_wechat_collection_modes_are_mutually_exclusive(self) -> None:
        with redirect_stderr(StringIO()), redirect_stdout(StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(
                    ["activate", "--skip-wechat", "--enable-wechat"]
                )

    def test_history_boundary_uses_one_calendar_month(self) -> None:
        timezone = ZoneInfo("Asia/Shanghai")
        self.assertEqual(
            "2026-02-28",
            _one_calendar_month_ago(
                datetime(2026, 3, 31, 12, 0, tzinfo=timezone)
            ).date().isoformat(),
        )
        self.assertEqual(
            "2025-12-31",
            _one_calendar_month_ago(
                datetime(2026, 1, 31, 12, 0, tzinfo=timezone)
            ).date().isoformat(),
        )

    def test_qr_start_saves_only_image_and_public_status(self) -> None:
        settings = Settings.load(ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "qr.png"
            with patch(
                "reporter.ingest.werss_wechat_auth_status",
                return_value={
                    "status": "needs_auth",
                    "authorized": False,
                    "qr_pending": False,
                },
            ), patch(
                "reporter.ingest.werss_admin_token", return_value="private-token"
            ), patch(
                "reporter.ingest._json_api",
                return_value={"data": {"code": "/static/wx_qrcode.png?t=1"}},
            ), patch(
                "reporter.ingest._http", return_value=b"\x89PNG\r\n\x1a\nimage"
            ):
                result = start_werss_wechat_auth(settings, output)
            self.assertEqual("awaiting_scan", result["status"])
            self.assertEqual(output.resolve(), Path(result["qr_image"]))
            self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))
            self.assertNotIn("token", json.dumps(result))

    def test_skip_wechat_persists_degraded_rss_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            shutil.copytree(ROOT / "config", config)
            (config / "runtime.json").write_text(
                json.dumps(
                    {
                        "data_dir": str(temp / "data"),
                        "logs_dir": str(temp / "logs"),
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings.load(ROOT, config)
            db = Database(settings.db_path)
            readiness = {
                "ready": True,
                "wechat_enabled": False,
                "required_wechat_ready": 0,
                "required_wechat_total": 0,
                "active_rss": 1,
                "configured_rss": 1,
                "article_count": 1,
                "audit_status": "warning",
                "critical": [],
                "warnings": [],
            }
            with patch(
                "reporter.activation.ingest",
                return_value=IngestResult(mode="external_rss", imported=1),
            ), patch(
                "reporter.activation.evaluate_activation_readiness",
                return_value=readiness,
            ):
                result = activate_subscription(
                    settings,
                    db,
                    skip_wechat=True,
                )
            self.assertEqual("degraded", result["status"])
            self.assertTrue(result["wechat_skipped"])
            reporting = json.loads(
                (config / "reporting.json").read_text(encoding="utf-8")
            )
            self.assertFalse(reporting["collection"]["wechat_enabled"])
            self.assertEqual("degraded", load_activation_state(settings)["status"])

    def test_persisted_rss_mode_stays_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            shutil.copytree(ROOT / "config", config)
            reporting_path = config / "reporting.json"
            reporting = json.loads(reporting_path.read_text(encoding="utf-8"))
            reporting.setdefault("collection", {})["wechat_enabled"] = False
            reporting_path.write_text(json.dumps(reporting), encoding="utf-8")
            (config / "runtime.json").write_text(
                json.dumps(
                    {
                        "data_dir": str(temp / "data"),
                        "logs_dir": str(temp / "logs"),
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings.load(ROOT, config)
            readiness = {
                "ready": True,
                "wechat_enabled": False,
                "required_wechat_ready": 0,
                "required_wechat_total": 0,
                "active_rss": 1,
                "configured_rss": 1,
                "article_count": 1,
                "audit_status": "warning",
                "critical": [],
                "warnings": [],
            }
            with patch(
                "reporter.activation.ingest",
                return_value=IngestResult(mode="external_rss", imported=1),
            ), patch(
                "reporter.activation.evaluate_activation_readiness",
                return_value=readiness,
            ):
                result = activate_subscription(
                    settings,
                    Database(settings.db_path),
                )
            self.assertEqual("degraded", result["status"])
            self.assertTrue(result["wechat_skipped"])

    def test_required_web_candidate_marks_activation_with_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            shutil.copytree(ROOT / "config", config)
            (config / "accounts.json").write_text(
                json.dumps({"priorities": {}, "accounts": []}),
                encoding="utf-8",
            )
            (config / "external_sources.json").write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "active-rss",
                                "name": "Active RSS",
                                "priority": "required",
                                "capture_method": "rss",
                                "feed_url": "https://example.com/feed.xml",
                            },
                            {
                                "id": "official-web",
                                "name": "Official Web",
                                "priority": "required",
                                "capture_method": "web_pending",
                                "homepage_url": "https://example.com/official",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (config / "runtime.json").write_text(
                json.dumps(
                    {
                        "data_dir": str(temp / "data"),
                        "logs_dir": str(temp / "logs"),
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings.load(ROOT, config)
            db = Database(settings.db_path)
            readiness = {
                "ready": True,
                "wechat_enabled": False,
                "required_wechat_ready": 0,
                "required_wechat_total": 0,
                "active_rss": 1,
                "configured_rss": 1,
                "pending_external": 1,
                "required_pending_external": 1,
                "required_pending_external_ids": ["external:official-web"],
                "article_count": 1,
                "audit_status": "warning",
                "critical": [],
                "warnings": ["必抓外部源尚未激活"],
            }
            with patch(
                "reporter.activation.ingest",
                return_value=IngestResult(mode="external_rss", imported=1),
            ), patch(
                "reporter.activation.evaluate_activation_readiness",
                return_value=readiness,
            ):
                result = activate_subscription(settings, db)
            self.assertEqual("active_with_gaps", result["status"])

    def test_audit_warns_for_required_web_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            shutil.copytree(ROOT / "config", config)
            (config / "accounts.json").write_text(
                json.dumps({"priorities": {}, "accounts": []}),
                encoding="utf-8",
            )
            (config / "external_sources.json").write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "official-web",
                                "name": "Official Web",
                                "priority": "required",
                                "capture_method": "web_pending",
                                "homepage_url": "https://example.com/official",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (config / "runtime.json").write_text(
                json.dumps(
                    {
                        "data_dir": str(temp / "data"),
                        "logs_dir": str(temp / "logs"),
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings.load(ROOT, config)
            db = Database(settings.db_path)
            db.initialize(settings.all_sources)
            audit = coverage_audit(settings, db)
            self.assertEqual("warning", audit["status"])
            self.assertTrue(
                any("必抓外部源尚未激活" in item for item in audit["warnings"])
            )
            readiness = evaluate_activation_readiness(settings, db)
            self.assertEqual(1, readiness["required_pending_external"])
            self.assertEqual(
                ["external:official-web"],
                readiness["required_pending_external_ids"],
            )

    def test_pipeline_lock_timeout_has_a_specific_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config = temp / "config"
            shutil.copytree(ROOT / "config", config)
            (config / "runtime.json").write_text(
                json.dumps(
                    {
                        "data_dir": str(temp / "data"),
                        "logs_dir": str(temp / "logs"),
                    }
                ),
                encoding="utf-8",
            )
            settings = Settings.load(ROOT, config)
            with patch(
                "reporter.cli.fcntl.flock",
                side_effect=BlockingIOError,
            ), patch("reporter.cli.time.monotonic", side_effect=[0, 301]):
                with self.assertRaises(PipelineBusyError):
                    with project_lock(settings):
                        pass


if __name__ == "__main__":
    unittest.main()
