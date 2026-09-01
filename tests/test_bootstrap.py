from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import bootstrap


class BootstrapTest(unittest.TestCase):
    def test_clean_install_check_and_smoke(self) -> None:
        # A disposable home proves the complete public journey without
        # reading or mutating the signed-in machine's normal agent profiles.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual(bootstrap.install(home), 0)
            self.assertEqual(bootstrap.check(home), 0)
            self.assertEqual(bootstrap.smoke(home), 0)
            self.assertIn(bootstrap.managed_block(), (home / ".claude/CLAUDE.md").read_text(encoding="utf-8"))
            self.assertIn(bootstrap.managed_block(), (home / ".codex/AGENTS.md").read_text(encoding="utf-8"))
            self.assertTrue((home / ".claude/skills/test/SKILL.md").is_file())
            self.assertTrue((home / ".agents/skills/make-portable/SKILL.md").is_file())

    def test_reinstall_is_idempotent_and_preserves_unmanaged_skills(self) -> None:
        # Unmanaged siblings model skills installed from another source;
        # their exact bytes and the backup count must remain unchanged on rerun.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            unmanaged = home / ".agents/skills/external/SKILL.md"
            unmanaged.parent.mkdir(parents=True)
            unmanaged.write_bytes(b"external\x00asset")
            bootstrap.install(home)
            before = sorted((home / ".agent-lab-public/backups").rglob("*")) if (home / ".agent-lab-public/backups").exists() else []
            bootstrap.install(home)
            after = sorted((home / ".agent-lab-public/backups").rglob("*")) if (home / ".agent-lab-public/backups").exists() else []
            self.assertEqual(unmanaged.read_bytes(), b"external\x00asset")
            self.assertEqual(before, after)

    def test_existing_indexes_and_colliding_skill_are_backed_up(self) -> None:
        # Both text around the managed block and a pre-existing skill are
        # checked after replacement so recovery is observable rather than promised.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            index = home / ".codex/AGENTS.md"
            index.parent.mkdir(parents=True)
            index.write_text("# my rules\n", encoding="utf-8")
            skill = home / ".agents/skills/test/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("old skill", encoding="utf-8")
            bootstrap.install(home)
            self.assertTrue((home / ".codex/AGENTS.md").read_text(encoding="utf-8").startswith("# my rules"))
            backups = home / ".agent-lab-public/backups"
            self.assertEqual(len(list(backups.rglob("AGENTS.md"))), 1)
            old_skills = list(backups.rglob("test/SKILL.md"))
            self.assertEqual(len(old_skills), 1)
            self.assertEqual(old_skills[0].read_text(encoding="utf-8"), "old skill")

    def test_check_and_smoke_fail_with_recovery_command(self) -> None:
        # Missing installation must stay a visible nonzero result and
        # direct a first-time user to the exact normal recovery entry point.
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                check_result = bootstrap.check(Path(directory))
                smoke_result = bootstrap.smoke(Path(directory))
            self.assertEqual(check_result, 1)
            self.assertEqual(smoke_result, 1)
            self.assertIn("python bootstrap.py install", output.getvalue())


if __name__ == "__main__":
    unittest.main()
