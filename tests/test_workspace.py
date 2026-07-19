from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reporter.workspace import (
    inspect_workspace,
    list_reports,
    register_subscription,
)


class WorkspaceTests(unittest.TestCase):
    def _subscription(self, root: Path, subscription_id: str = "example") -> Path:
        config = root / "subscriptions" / subscription_id
        config.mkdir(parents=True)
        (config / "profile.json").write_text(
            json.dumps(
                {
                    "id": subscription_id,
                    "name": "Example Research",
                    "domains": [
                        {"id": "policy", "name": "Policy"},
                        {"id": "markets", "name": "Markets"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (config / "subscription.json").write_text(
            json.dumps(
                {
                    "id": subscription_id,
                    "name": "Example Research",
                    "status": "configured",
                    "created_at": "2026-07-18T08:00:00+08:00",
                    "domains": [
                        {"id": "policy", "name": "Policy"},
                        {"id": "markets", "name": "Markets"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (config / "runtime.json").write_text(
            json.dumps({"data_dir": f"data/profiles/{subscription_id}"}),
            encoding="utf-8",
        )
        (config / "reporting.json").write_text(
            json.dumps(
                {
                    "strategy_preset": "standard",
                    "history_start": "2026-06-18T00:00:00+08:00",
                }
            ),
            encoding="utf-8",
        )
        (config / "accounts.json").write_text(
            json.dumps({"accounts": [{"name": "One"}]}),
            encoding="utf-8",
        )
        (config / "external_sources.json").write_text(
            json.dumps({"sources": [{"name": "Two"}, {"name": "Three"}]}),
            encoding="utf-8",
        )
        return config

    def _database(self, root: Path, subscription_id: str = "example") -> Path:
        data = root / "data" / "profiles" / subscription_id
        reports = data / "reports"
        reports.mkdir(parents=True)
        report_path = reports / "daily.md"
        report_path.write_text("# Daily\n", encoding="utf-8")
        db_path = data / "research.db"
        with sqlite3.connect(db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE articles (
                    id TEXT PRIMARY KEY,
                    analysis_status TEXT NOT NULL
                );
                CREATE TABLE reports (
                    id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    markdown_path TEXT NOT NULL,
                    period_start INTEGER NOT NULL,
                    period_end INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    notion_status TEXT,
                    notion_url TEXT
                );
                """
            )
            connection.executemany(
                "INSERT INTO articles (id, analysis_status) VALUES (?, ?)",
                [("a", "done"), ("b", "pending"), ("c", "failed")],
            )
            connection.execute(
                """
                INSERT INTO reports (
                    id, kind, title, markdown_path, period_start, period_end,
                    created_at, notion_status, notion_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "daily",
                    "Daily Example",
                    str(report_path),
                    100,
                    200,
                    300,
                    "pending",
                    None,
                ),
            )
        return db_path

    def test_register_and_discover_subscription(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._subscription(root)
            home = root / "iread-home"
            service = root / "service"
            with mock.patch.dict(
                os.environ,
                {"IREAD_HOME": str(home), "IREAD_SERVICE_ROOT": str(service)},
                clear=False,
            ):
                registered = register_subscription(config)
                workspace = inspect_workspace(root)
            self.assertEqual("example", registered["id"])
            self.assertEqual(1, workspace["subscription_count"])
            summary = workspace["subscriptions"][0]
            self.assertEqual("configured", summary["status"])
            self.assertEqual(2, len(summary["domains"]))
            self.assertEqual("approve_activation", summary["next_actions"][0]["id"])
            registry = json.loads((home / "subscriptions.json").read_text())
            self.assertEqual(str(config.resolve()), registry["subscriptions"][0]["config_dir"])

    def test_active_legacy_subscription_is_not_told_to_activate_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._subscription(root)
            self._database(root)
            service = root / "service"
            service.mkdir()
            (service / "active-config-dir").write_text(str(config), encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "IREAD_HOME": str(root / "iread-home"),
                    "IREAD_SERVICE_ROOT": str(service),
                },
                clear=False,
            ):
                workspace = inspect_workspace(root)
            summary = workspace["subscriptions"][0]
            self.assertEqual("active_unverified", summary["status"])
            self.assertEqual("installed", summary["schedule"]["status"])
            self.assertEqual(3, summary["articles"])
            self.assertEqual(1, summary["pending_analysis"])
            self.assertEqual(1, summary["failed_analysis"])
            action_ids = [item["id"] for item in summary["next_actions"]]
            self.assertEqual(
                ["audit_legacy_activation", "view_latest_report"], action_ids
            )

    def test_registry_preserves_subscription_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            owner_root = temp / "owner"
            current_root = temp / "current"
            current_root.mkdir()
            config = self._subscription(owner_root)
            self._database(owner_root)
            with mock.patch.dict(
                os.environ,
                {
                    "IREAD_HOME": str(temp / "iread-home"),
                    "IREAD_SERVICE_ROOT": str(temp / "service"),
                },
                clear=False,
            ):
                register_subscription(config, owner_root)
                workspace = inspect_workspace(current_root)
            summary = workspace["subscriptions"][0]
            self.assertEqual(str(owner_root.resolve()), summary["repository_root"])
            self.assertEqual(3, summary["articles"])
            self.assertEqual(
                str((owner_root / "data/profiles/example/research.db").resolve()),
                summary["database"],
            )

    def test_active_with_gaps_keeps_required_source_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._subscription(root)
            self._database(root)
            state = root / "data/profiles/example/state"
            state.mkdir(parents=True)
            (state / "activation.json").write_text(
                json.dumps(
                    {
                        "status": "active_with_gaps",
                        "updated_at": "2026-07-18T09:00:00+08:00",
                        "schedule": {"status": "installed"},
                        "readiness": {
                            "ready": True,
                            "article_count": 3,
                            "pending_external": 2,
                            "required_pending_external": 1,
                            "required_pending_external_ids": ["external:regulator"],
                            "warnings": ["one", "two"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "IREAD_HOME": str(root / "iread-home"),
                    "IREAD_SERVICE_ROOT": str(root / "service"),
                },
                clear=False,
            ):
                workspace = inspect_workspace(root, selected_config_dir=config)
            summary = workspace["subscriptions"][0]
            self.assertEqual("active_with_gaps", summary["status"])
            self.assertEqual("not_active", summary["schedule"]["status"])
            self.assertEqual(
                ["external:regulator"],
                summary["activation"]["readiness"][
                    "required_pending_external_ids"
                ],
            )
            self.assertEqual(
                "review_coverage_gaps", summary["next_actions"][0]["id"]
            )

    def test_report_index_supports_kind_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = self._database(root)
            reports = list_reports(db_path, kind="daily", limit=5)
            self.assertEqual(1, reports["count"])
            self.assertEqual("Daily Example", reports["reports"][0]["title"])
            self.assertTrue(reports["reports"][0]["exists"])
            self.assertIn("created_at_iso", reports["reports"][0])


if __name__ == "__main__":
    unittest.main()
