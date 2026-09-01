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


if __name__ == "__main__":
    unittest.main()
