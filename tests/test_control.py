from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from reporter.cli import _publish_requested, build_parser, main
from reporter.control import capability_contract, evaluate_acceptance
from reporter.db import Database
from reporter.feedback import list_feedback, record_feedback
from reporter.operations import completed_request, operation_events
from reporter.proposals import _reporting_config
from reporter.settings import Settings
from reporter.source_quality import review_sources


ROOT = Path(__file__).resolve().parents[1]


class ControlPlaneTests(unittest.TestCase):
    def _settings(self, temp: Path) -> Settings:
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
        return Settings.load(ROOT, config)

    def test_capability_contract_has_unique_governed_capabilities(self) -> None:
        contract = capability_contract(ROOT)
        capability_ids = [item["id"] for item in contract["capabilities"]]
        self.assertEqual(len(capability_ids), len(set(capability_ids)))
        by_id = {item["id"]: item for item in contract["capabilities"]}
        self.assertEqual("safe_read", by_id["inspect_workspace"]["idempotency"])
        self.assertIn("external_write", by_id["publish_report"]["permissions"])
        self.assertIn("explicit", by_id["publish_report"]["approval"])
        for name in (
            "agent_capabilities.schema.json",
            "acceptance.schema.json",
            "error_response.schema.json",
            "operation_events.schema.json",
            "feedback_list.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            self.assertEqual("object", schema["type"])

    def test_acceptance_blocks_unstarted_subscription(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            with mock.patch.dict(
                os.environ,
                {
                    "IREAD_HOME": str(temp / "iread-home"),
                    "IREAD_SERVICE_ROOT": str(temp / "service"),
                },
                clear=False,
            ):
                settings = self._settings(temp)
                result = evaluate_acceptance(settings)
            self.assertFalse(result["accepted"])
            self.assertEqual("blocked", result["quality"])
            failed = {
                item["id"]
                for item in result["checks"]
                if item["status"] == "fail"
            }
            self.assertIn("activation", failed)
            self.assertIn("collection", failed)
            self.assertIn("report_delivery", failed)

    def test_activate_requires_machine_enforced_approval(self) -> None:
        parser = build_parser()
        self.assertTrue(parser.parse_args(["activate", "--approved"]).approved)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            with mock.patch.dict(
                os.environ,
                {
                    "IREAD_HOME": str(temp / "iread-home"),
                    "IREAD_SERVICE_ROOT": str(temp / "service"),
                },
                clear=False,
            ):
                settings = self._settings(temp)
                stdout = StringIO()
                with redirect_stdout(stdout), redirect_stderr(StringIO()):
                    exit_code = main(
                        [
                            "--project-root",
                            str(ROOT),
                            "--config-dir",
                            str(settings.config_dir),
                            "activate",
                        ]
                    )
            self.assertEqual(1, exit_code)
            result = json.loads(stdout.getvalue())
            self.assertEqual("PermissionError", result["error"]["type"])
            self.assertIn("--approved", result["error"]["message"])

    def test_argument_errors_are_structured_json(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["feedback", "add", "--target", "report"])
        self.assertEqual(2, raised.exception.code)
        result = json.loads(stdout.getvalue())
        self.assertEqual("invalid_request", result["error"]["code"])
        self.assertEqual("ArgumentError", result["error"]["type"])

    def test_request_id_makes_feedback_idempotent_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            with mock.patch.dict(
                os.environ,
                {
                    "IREAD_HOME": str(temp / "iread-home"),
                    "IREAD_SERVICE_ROOT": str(temp / "service"),
                },
                clear=False,
            ):
                settings = self._settings(temp)
                argv = [
                    "--project-root",
                    str(ROOT),
                    "--config-dir",
                    str(settings.config_dir),
                    "--request-id",
                    "feedback:daily:1",
                    "feedback",
                    "add",
                    "--target",
                    "report",
                    "--target-id",
                    "1",
                    "--rating",
                    "down",
                    "--note",
                    "Too repetitive",
                ]
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    self.assertEqual(0, main(argv))
                second_stdout = StringIO()
                with redirect_stdout(second_stdout), redirect_stderr(StringIO()):
                    self.assertEqual(0, main(argv))
                conflicting_stdout = StringIO()
                conflicting_argv = [*argv[:-1], "Different intent"]
                with redirect_stdout(conflicting_stdout), redirect_stderr(StringIO()):
                    self.assertEqual(1, main(conflicting_argv))
                feedback = list_feedback(settings)
                events = operation_events(settings, 20)
                completed = completed_request(
                    settings, "feedback", "feedback:daily:1"
                )
                limited = operation_events(settings, 1)
            self.assertEqual(1, feedback["count"])
            self.assertEqual("request_already_completed", json.loads(second_stdout.getvalue())["reason"])
            self.assertEqual(
                "invalid_request",
                json.loads(conflicting_stdout.getvalue())["error"]["code"],
            )
            self.assertIsNotNone(completed)
            self.assertEqual(
                ["started", "finished"],
                [item["phase"] for item in events["events"]],
            )
            self.assertEqual(2, limited["count"])
            self.assertEqual(1, limited["returned"])

    def test_schedule_removal_requires_machine_enforced_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            with mock.patch.dict(
                os.environ,
                {
                    "IREAD_HOME": str(temp / "iread-home"),
                    "IREAD_SERVICE_ROOT": str(temp / "service"),
                },
                clear=False,
            ):
                settings = self._settings(temp)
                stdout = StringIO()
                with redirect_stdout(stdout), redirect_stderr(StringIO()):
                    exit_code = main(
                        [
                            "--project-root",
                            str(ROOT),
                            "--config-dir",
                            str(settings.config_dir),
                            "schedule",
                            "uninstall",
                        ]
                    )
            self.assertEqual(1, exit_code)
            result = json.loads(stdout.getvalue())
            self.assertEqual("approval_required", result["error"]["code"])
            self.assertIn("--approved", result["error"]["message"])

    def test_generated_subscriptions_default_to_local_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(Path(temp_dir))
            settings.reporting.setdefault("notion", {})["auto_publish"] = False
            self.assertFalse(
                _publish_requested(
                    settings,
                    SimpleNamespace(publish=False, no_publish=False),
                )
            )
            self.assertTrue(
                _publish_requested(
                    settings,
                    SimpleNamespace(publish=True, no_publish=False),
                )
            )

    def test_source_feedback_is_disclosed_without_rewriting_score(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(Path(temp_dir))
            db = Database(settings.db_path)
            db.initialize(settings.all_sources)
            source_id = settings.all_sources[0].wechat_id
            record_feedback(
                settings,
                target="source",
                target_id=source_id,
                rating="down",
                note="Too much repeated commentary",
            )
            review = review_sources(settings, db, representative_works=0)
            source = next(item for item in review["sources"] if item["id"] == source_id)
            self.assertEqual(1, len(source["user_feedback"]))
            self.assertTrue(
                any("负向反馈" in warning for warning in source["warnings"])
            )
            self.assertEqual(1, review["summary"]["sources_with_user_feedback"])

    def test_generated_subscription_disables_implicit_notion_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(Path(temp_dir))
            policy = {
                "enabled": True,
                "reading_minutes": 10,
                "focus": ["changes"],
                "max_items": 10,
            }
            proposal = {
                "report_presets": [
                    {
                        "id": "standard",
                        "daily": policy,
                        "weekly": policy,
                        "monthly": policy,
                    }
                ]
            }
            reporting = _reporting_config(
                settings,
                proposal,
                "standard",
                "2026-06-18T00:00:00+08:00",
            )
            self.assertFalse(reporting["notion"]["auto_publish"])


if __name__ == "__main__":
    unittest.main()
