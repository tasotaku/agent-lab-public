"""Verify the published usage entry points with synthetic local data only."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "usage_monitor"
FIELDS = ("observed_at", "account", "declared_plan", "bucket", "window", "window_minutes",
          "resets_at", "used_percent", "delta_10m_points", "measured_seconds", "status")


class UsageDistributionTest(unittest.TestCase):
    def test_cli_and_synthetic_graph(self) -> None:
        # AI_NOTE: Exercise the public commands without needing Codex or account credentials.
        help_result = subprocess.run([sys.executable, str(TOOL / "codex_usage.py"), "--help"],
                                     capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        with tempfile.TemporaryDirectory(prefix="usage fixture ") as directory:
            source = Path(directory) / "fixture.csv"
            output = Path(directory) / "usage graph.html"
            rows = [
                ["2026-01-01T12:00:00+09:00", "fixture-account", "Fixture plan", "codex",
                 "primary", "10080", "2000000000", "24", "", "", "warming_up"],
                ["2026-01-01T12:10:00+09:00", "fixture-account", "Fixture plan", "codex",
                 "primary", "10080", "2000000000", "24", "0", "600", "ok"],
                ["2026-01-01T12:11:00+09:00", "", "Fixture plan", "", "", "", "",
                 "", "", "", "fetch_error"],
                ["2026-01-01T12:12:00+09:00", "fixture-account", "Fixture plan", "codex",
                 "primary", "10080", "2000001000", "1", "", "", "warming_up"],
            ]
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(FIELDS)
                writer.writerows(rows)
            result = subprocess.run([sys.executable, str(TOOL / "graph.py"), "--csv", str(source),
                                     "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            html = output.read_text(encoding="utf-8")
            self.assertNotIn("@@DATA@@", html)
            payload = html.split('type="application/json">', 1)[1].split("</script>", 1)[0]
            samples = json.loads(payload)[0]["samples"]
            self.assertIsNone(samples[0]["delta"])
            self.assertEqual(samples[1]["delta"], 0)
            self.assertIsNone(samples[2]["used"])
            self.assertIsNone(samples[2]["delta"])
            self.assertNotEqual(samples[1]["reset"], samples[3]["reset"])
            self.assertIn('id="usage"', html)
            self.assertIn('id="delta"', html)
            original = source.read_bytes()
            result = subprocess.run([sys.executable, str(TOOL / "graph.py"), "--csv", str(source),
                                     "--output", str(source)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), original)

    def test_bad_csv_is_rejected(self) -> None:
        # AI_NOTE: A malformed recording must not produce a plausible-looking usage report.
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.csv"
            output = Path(directory) / "report.html"
            source.write_text("invalid,header\n1,2\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(TOOL / "graph.py"), "--csv", str(source),
                                     "--output", str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
