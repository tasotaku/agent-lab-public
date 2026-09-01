from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/audit_public.py"
SPEC = importlib.util.spec_from_file_location("audit_public", MODULE_PATH)
assert SPEC and SPEC.loader
audit_public = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_public
SPEC.loader.exec_module(audit_public)
COMPATIBILITY_PATH = Path(__file__).resolve().parents[1] / "tools/compatibility.py"
COMPATIBILITY_SPEC = importlib.util.spec_from_file_location("compatibility", COMPATIBILITY_PATH)
assert COMPATIBILITY_SPEC and COMPATIBILITY_SPEC.loader
compatibility = importlib.util.module_from_spec(COMPATIBILITY_SPEC)
sys.modules[COMPATIBILITY_SPEC.name] = compatibility
COMPATIBILITY_SPEC.loader.exec_module(compatibility)


class PublicAuditTest(unittest.TestCase):
    def test_detects_credential_without_storing_fixture_in_source(self) -> None:
        # Runtime assembly exercises the detector without committing a
        # token-shaped fixture that would correctly fail the repository audit.
        value = "gh" + "p_" + ("A" * 24)
        findings = audit_public.scan_path("fixture", "safe.txt", value.encode())
        self.assertEqual([finding.category for finding in findings], ["credentials"])

    def test_detects_machine_home_path_without_storing_one(self) -> None:
        # The path is assembled only in memory so the public test remains
        # privacy-clean while proving Windows home leakage is rejected.
        value = "C:" + "\\" + "Users" + "\\" + "person" + "\\settings"
        findings = audit_public.scan_path("fixture", "safe.txt", value.encode())
        self.assertEqual([finding.category for finding in findings], ["personal_config"])

    def test_detects_private_category_paths(self) -> None:
        findings = audit_public.scan_path("fixture", "knowledge/projects/example/journal/entry.md", b"generic")
        categories = {finding.category for finding in findings}
        self.assertEqual(categories, {"personal_config", "private_knowledge", "conversations"})

    def test_public_repository_payload_passes(self) -> None:
        # The product audits its actual working payload and current Git
        # history, preventing unit-only fixtures from masking publication leaks.
        report = audit_public.audit()
        self.assertEqual(report["verdict"], "PASS", report["findings"])
        self.assertGreaterEqual(report["scanned"]["files"], 20)
        self.assertEqual(report["scanner"]["version"], "1.1.0")
        self.assertGreaterEqual(len(report["linked_artifacts"]), 4)
        self.assertEqual(report["dependencies"]["working_submodules"], [])
        self.assertGreaterEqual(len(report["inventory"]["shared_skills"]), 6)
        self.assertTrue(all({"path", "reason", "risk"} <= set(item) for item in report["scanned"]["exclusions"]))

    def test_unsigned_compatibility_evidence_requires_every_component(self) -> None:
        commit = "a" * 40
        runs = {
            "workflow_runs": [
                {"head_sha": commit, "name": "Cross-platform install", "conclusion": "success"}
            ]
        }
        jobs = {
            "jobs": [
                {
                    "name": f"install-check ({os_name}, 3.13)",
                    "conclusion": "success",
                    "html_url": "https://github.com/example/job",
                    "steps": [
                        {"name": step, "conclusion": "success"}
                        for step in compatibility.REQUIRED_STEPS
                    ],
                }
                for os_name in compatibility.REQUIRED_OS
            ]
        }
        evidence, failures = compatibility.evaluate(commit, runs, jobs)
        self.assertEqual(failures, [])
        self.assertEqual({item["os"] for item in evidence}, compatibility.REQUIRED_OS)


if __name__ == "__main__":
    unittest.main()
