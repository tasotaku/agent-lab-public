from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools import session_memory


class SessionMemoryTest(unittest.TestCase):
    def fixture(self, root: Path, canary: str = "CANARY-LOCAL-1") -> tuple[Path, Path, dict[str, str]]:
        project = root / "project"
        project.mkdir()
        transcript = root / "transcript.jsonl"
        lines = [
            {"role": "user", "content": f"fixture task complete {canary}."},
            {"role": "assistant", "content": f"use local journal because fixture must not send externally {canary}."},
            {"role": "assistant", "content": f"Next: verify start injection {canary}."},
            {"role": "assistant", "content": "Raw filler that must not be injected."},
        ]
        transcript.write_text("\n".join(json.dumps(item) for item in lines), encoding="utf-8")
        event = {"cwd": str(project), "transcript_path": str(transcript), "session_id": "fixture-session"}
        return project, transcript, event

    def test_record_context_is_project_scoped_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            project, _, event = self.fixture(root)
            first = session_memory.record(home, "codex", event)
            second = session_memory.record(home, "codex", event)
            self.assertEqual(first["entry"], second["entry"])
            self.assertEqual(len(list(first["journal"].glob("*.md"))), 1)
            journal = first["entry"].read_text(encoding="utf-8")
            current = first["current"].read_text(encoding="utf-8")
            for marker in ("Work completed", "Decisions and reasons", "Next work", "CANARY-LOCAL-1"):
                self.assertIn(marker, journal)
                self.assertIn(marker, current)
            injected = session_memory.context(home, event)
            self.assertEqual(injected.count("CANARY-LOCAL-1"), 3)
            self.assertNotIn("Raw filler", injected)
            other = root / "other"
            other.mkdir()
            self.assertEqual(session_memory.context(home, {"cwd": str(other)}), "")

    def test_install_merge_remove_preserves_unmanaged_hooks_and_data(self) -> None:
        for agent in ("claude", "codex"):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                home = root / "home"
                path = session_memory.settings_path(home, agent)
                path.parent.mkdir(parents=True)
                original = {"theme": "user", "hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": "user-tool"}]}]}}
                path.write_text(json.dumps(original), encoding="utf-8")
                session_memory.install_hooks(home, agent)
                session_memory.install_hooks(home, agent)
                self.assertEqual(session_memory.hook_counts(home, agent), {"SessionEnd": 1, "SessionStart": 1})
                installed = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(installed["theme"], "user")
                self.assertIn("user-tool", json.dumps(installed))
                project, _, event = self.fixture(root)
                paths = session_memory.record(home, agent, event)
                session_memory.remove_hooks(home, agent)
                removed = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn(session_memory.MANAGED_ID, json.dumps(removed))
                self.assertIn("user-tool", json.dumps(removed))
                self.assertTrue(paths["current"].is_file())

    def test_hook_commands_are_cross_platform_and_local(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for agent in ("claude", "codex"):
                session_memory.install_hooks(home, agent)
            codex = session_memory._read_json(session_memory.settings_path(home, "codex"))
            encoded = json.dumps(codex)
            self.assertIn("commandWindows", encoded)
            self.assertIn("python3", encoded)
            self.assertNotIn("http", encoded)
            self.assertNotIn("push", encoded)


if __name__ == "__main__":
    unittest.main()
