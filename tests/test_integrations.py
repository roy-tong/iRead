from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_codex_marketplace_points_to_iread_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / "integrations/codex/.agents/plugins/marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        entry = marketplace["plugins"][0]
        plugin_dir = (
            ROOT / "integrations/codex" / entry["source"]["path"]
        ).resolve()
        manifest = json.loads(
            (plugin_dir / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual("iread", marketplace["name"])
        self.assertEqual("iread", entry["name"])
        self.assertEqual("iread", plugin_dir.name)
        self.assertEqual("iread", manifest["name"])
        self.assertTrue((plugin_dir / "scripts/iread").stat().st_mode & 0o111)
        self.assertTrue(
            (plugin_dir / "skills/onboard-research-domains/SKILL.md").is_file()
        )
        self.assertTrue((plugin_dir / "skills/manage-iread/SKILL.md").is_file())
        self.assertIn("Workflow Recovery", manifest["interface"]["capabilities"])
        self.assertIn("Agent Control Contract", manifest["interface"]["capabilities"])
        self.assertTrue((ROOT / "scripts/uninstall_schedule.sh").stat().st_mode & 0o111)

    def test_codex_management_skill_covers_status_reports_and_approval(self) -> None:
        skill_dir = ROOT / "integrations/codex/plugins/iread/skills/manage-iread"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill_dir / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("../../scripts/iread workspace", skill)
        self.assertIn("reports --kind <kind> --limit 5", skill)
        self.assertIn("active_with_gaps", skill)
        self.assertIn("active_unverified", skill)
        self.assertIn("Require explicit approval", skill)
        self.assertIn("--request-id <stable-request-id>", skill)
        self.assertIn("operations --limit 20", skill)
        self.assertIn("workspace` and `acceptance", skill)
        self.assertIn("feedback add", skill)
        self.assertIn("schedule uninstall --approved", skill)
        self.assertIn("$manage-iread", metadata)

    def test_codex_onboarding_uses_current_task_research(self) -> None:
        skill_dir = ROOT / "integrations/codex/plugins/iread/skills/onboard-research-domains"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        reference = (skill_dir / "references/proposal-authoring.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("current Codex task", skill)
        self.assertIn("instead of invoking another Codex process", skill)
        self.assertIn("iread validate-proposal", skill)
        self.assertIn("批准全部领域", skill)
        self.assertIn("Do not invoke a nested Codex process", reference)

    def test_codex_installer_creates_codex_home_and_prints_concise_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_codex = temp / "codex"
            fake_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_codex.chmod(0o755)
            env = {
                **os.environ,
                "HOME": str(temp / "home"),
                "CODEX_HOME": str(temp / "home/.codex"),
                "CODEX_BIN": str(fake_codex),
                "IREAD_HOME": str(temp / "home/.config/iread"),
                "IREAD_SERVICE_ROOT": str(temp / "service"),
                "IREAD_DATA_DIR": str(temp / "data"),
                "IREAD_LOGS_DIR": str(temp / "logs"),
                "WERSS_BASE_URL": "http://127.0.0.1:9",
            }
            completed = subprocess.run(
                [str(ROOT / "scripts/install_codex_plugin.sh")],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue((temp / "home/.codex").is_dir())
            self.assertIn("iRead is ready", completed.stdout)
            self.assertIn("did not add any example domain", completed.stdout)
            self.assertNotIn('"checks"', completed.stdout)

    def test_top_level_installer_preflights_codex_before_runtime_setup(self) -> None:
        script = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
        preflight = script.index("Codex CLI was not found")
        prepare = script.index('"$ROOT/scripts/prepare_runtime.sh"')
        self.assertLess(preflight, prepare)

    def test_workbuddy_installer_creates_iread_command_and_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbuddy = Path(temp_dir)
            (workbuddy / "knowledge/store").mkdir(parents=True)
            (workbuddy / ".claude/commands").mkdir(parents=True)
            subprocess.run(
                [str(ROOT / "integrations/work-buddy/install.sh"), str(workbuddy)],
                check=True,
                capture_output=True,
                text=True,
            )
            command = workbuddy / ".claude/commands/iread.md"
            workflow = workbuddy / "knowledge/store/iread/multi-domain-onboard.md"
            directions = (
                workbuddy
                / "knowledge/store/iread/multi-domain-onboard-directions.md"
            )
            self.assertTrue(command.exists())
            self.assertTrue(workflow.exists())
            self.assertTrue(directions.exists())
            root_pointer = workbuddy / "knowledge/store/iread/repository-root.txt"
            self.assertEqual(str(ROOT), root_pointer.read_text().strip())
            self.assertIn("workflow: iread-multi-domain-onboard", command.read_text())
            self.assertIn("bin/iread apply-subscription", directions.read_text())
            self.assertIn("bin/iread validate-proposal", directions.read_text())

    def test_cached_codex_wrapper_resolves_installed_repository_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            cached_scripts = temp / "cache/iread/scripts"
            cached_scripts.mkdir(parents=True)
            wrapper = cached_scripts / "iread"
            wrapper.write_bytes(
                (ROOT / "integrations/codex/plugins/iread/scripts/iread").read_bytes()
            )
            wrapper.chmod(0o755)
            iread_home = temp / "iread-home"
            iread_home.mkdir()
            (iread_home / "repository-root").write_text(str(ROOT) + "\n")
            completed = subprocess.run(
                [str(wrapper), "--help"],
                env={"PATH": "/usr/bin:/bin", "HOME": str(temp), "IREAD_HOME": str(iread_home)},
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("usage: iread", completed.stdout)

            workspace = subprocess.run(
                [str(wrapper), "workspace"],
                env={"PATH": "/usr/bin:/bin", "HOME": str(temp), "IREAD_HOME": str(iread_home)},
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(workspace.stdout)
            self.assertEqual("iRead", result["product"])
            self.assertIn("subscriptions", result)


if __name__ == "__main__":
    unittest.main()
