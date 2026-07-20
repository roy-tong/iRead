from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_portable_agent_skill_is_progressive_and_repository_agnostic(self) -> None:
        skill_root = ROOT / "skills/iread"
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(skill.split()), 220)
        self.assertIn("references/onboarding.md", skill)
        self.assertIn("references/management.md", skill)
        self.assertIn("Do not browse or analyze", skill)
        self.assertNotIn("doctor --surface", skill)
        self.assertTrue((skill_root / "scripts/iread").stat().st_mode & 0o111)
        self.assertTrue(
            (skill_root / "scripts/install-runtime").stat().st_mode & 0o111
        )

    def test_claude_and_doubao_installers_are_concise_and_rerunnable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            env = {
                **os.environ,
                "HOME": str(temp),
                "IREAD_HOME": str(temp / ".config/iread"),
            }
            for surface in ("claude-code", "doubao"):
                target = temp / surface / "iread"
                for _ in range(2):
                    completed = subprocess.run(
                        [
                            str(ROOT / "scripts/install.sh"),
                            surface,
                            str(target),
                        ],
                        cwd=ROOT,
                        env=env,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    self.assertLess(len(completed.stdout), 600)
                    self.assertIn("iRead check passed:", completed.stdout)
                    self.assertNotIn('"checks"', completed.stdout)
                    self.assertNotIn("knowledge-index rebuild", completed.stdout)
                self.assertTrue((target / "SKILL.md").is_file())
                self.assertTrue((target / "scripts/iread").stat().st_mode & 0o111)
                self.assertTrue(
                    (target / "scripts/install-runtime").stat().st_mode & 0o111
                )

    def test_portable_skill_bundle_is_small_and_contains_no_runtime_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [str(ROOT / "scripts/build_agent_skill_bundle.sh"), temp_dir],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            bundle = Path(completed.stdout.strip())
            self.assertLess(bundle.stat().st_size, 50_000)
            with zipfile.ZipFile(bundle) as archive:
                names = set(archive.namelist())
            self.assertIn("iread/SKILL.md", names)
            self.assertIn("iread/scripts/install-runtime", names)
            self.assertFalse(
                any(
                    part in name
                    for name in names
                    for part in (".env", "data/", "logs/", "subscriptions/")
                )
            )
            self.assertTrue((Path(temp_dir) / "SHA256SUMS").is_file())

    def test_one_line_workbuddy_installer_detects_project_and_is_rerunnable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_iread = temp / "fake-iread"
            fake_install = fake_iread / "scripts/install.sh"
            fake_install.parent.mkdir(parents=True)
            fake_install.write_text(
                "#!/bin/bash\nprintf '%s\\n' \"$*\" >> \"$INSTALL_CALLS\"\n",
                encoding="utf-8",
            )
            fake_install.chmod(0o755)
            workbuddy = temp / "Documents/work-buddy"
            (workbuddy / "knowledge/store").mkdir(parents=True)
            (workbuddy / ".claude/commands").mkdir(parents=True)
            calls = temp / "calls.txt"
            env = {
                **os.environ,
                "HOME": str(temp),
                "IREAD_SOURCE_ROOT": str(fake_iread),
                "INSTALL_CALLS": str(calls),
            }
            installer = ROOT / "install-workbuddy.sh"
            for _ in range(2):
                completed = subprocess.run(
                    [str(installer)],
                    cwd=workbuddy,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn("No repository analysis", completed.stdout)
                self.assertNotIn("agent_docs_rebuild", completed.stdout)
            expected = f"workbuddy {os.path.realpath(workbuddy)} --force"
            self.assertEqual([expected, expected], calls.read_text().splitlines())

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
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)
        self.assertTrue((ROOT / "scripts/uninstall_schedule.sh").stat().st_mode & 0o111)

    def test_remote_bootstrap_is_short_and_supports_every_agent_surface(self) -> None:
        installer = ROOT / "install"
        text = installer.read_text(encoding="utf-8")
        self.assertTrue(installer.stat().st_mode & 0o111)
        for surface in ("codex", "claude-code", "doubao", "workbuddy"):
            self.assertIn(surface, text)
        command = (
            "set -o pipefail; curl -fsSL "
            "https://cdn.jsdelivr.net/gh/roy-tong/iRead@main/install "
            "| bash -s -- codex"
        )
        self.assertLess(len(command), 120)
        self.assertIn("pipefail", command)
        self.assertNotIn("git clone", command)

    def test_remote_bootstrap_uses_archive_and_preserves_runtime_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            archive = temp / "iread.tar.gz"
            with archive.open("wb") as output:
                subprocess.run(
                    [
                        "git",
                        "archive",
                        "--format=tar.gz",
                        "--prefix=iRead-main/",
                        "HEAD",
                    ],
                    cwd=ROOT,
                    stdout=output,
                    check=True,
                )
            home = temp / "home"
            install_root = home / ".local/share/iread"
            env = {
                **os.environ,
                "HOME": str(home),
                "IREAD_INSTALL_ROOT": str(install_root),
                "IREAD_ARCHIVE_URL": archive.as_uri(),
                "WERSS_BASE_URL": "http://127.0.0.1:9",
            }
            for _ in range(2):
                completed = subprocess.run(
                    [str(ROOT / "install"), "claude-code"],
                    cwd=ROOT,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn("iRead check passed:", completed.stdout)
            self.assertTrue((install_root / ".iread-archive-install").is_file())
            self.assertTrue((install_root / ".env").is_file())
            self.assertTrue((home / ".claude/skills/iread/SKILL.md").is_file())

    def test_codex_management_skill_covers_status_reports_and_approval(self) -> None:
        skill_dir = ROOT / "integrations/codex/plugins/iread/skills/manage-iread"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        references = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((skill_dir / "references").glob("*.md"))
        )
        combined = skill + references
        metadata = (skill_dir / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertLess(len(skill.split()), 260)
        self.assertIn("Run only `workspace` first", skill)
        self.assertIn("reports --kind <kind> --limit 5", combined)
        self.assertIn("active_with_gaps", combined)
        self.assertIn("active_unverified", combined)
        self.assertIn("Require explicit approval", combined)
        self.assertIn("--request-id <stable-id>", combined)
        self.assertIn("operations --limit 20", skill)
        self.assertIn("workspace` and `acceptance", skill)
        self.assertIn("feedback add", combined)
        self.assertIn("schedule uninstall --approved", combined)
        self.assertIn("$manage-iread", metadata)

    def test_codex_onboarding_uses_current_task_research(self) -> None:
        skill_dir = ROOT / "integrations/codex/plugins/iread/skills/onboard-research-domains"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        reference = (skill_dir / "references/proposal-authoring.md").read_text(
            encoding="utf-8"
        )
        activation = (skill_dir / "references/apply-and-activate.md").read_text(
            encoding="utf-8"
        )
        self.assertLess(len(skill.split()), 260)
        self.assertIn("current Codex task", skill)
        self.assertIn("Do not run Doctor", skill)
        self.assertIn("iread validate-proposal", skill)
        self.assertIn("批准全部领域", skill)
        self.assertIn("Do not invoke a nested Codex process", reference)
        self.assertIn("activate --approved --install-schedule", activation)

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

    def test_workbuddy_install_prints_concise_doctor_summary(self) -> None:
        script = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/doctor_summary.py", script)
        self.assertNotIn(
            'exec "$ROOT/bin/iread" doctor --surface workbuddy', script
        )

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
            command_text = command.read_text()
            self.assertIn("multi-domain-onboard-directions.md", command_text)
            self.assertIn("Do not browse or analyze", command_text)
            self.assertNotIn("mcp__work-buddy__wb_run", command_text)
            self.assertIn("bin/iread apply-subscription", directions.read_text())
            self.assertIn("bin/iread validate-proposal", directions.read_text())
            self.assertIn(
                "activate --approved --install-schedule", directions.read_text()
            )
            self.assertIn("acceptance", directions.read_text())
            self.assertIn("longer than 30 seconds", directions.read_text())

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
