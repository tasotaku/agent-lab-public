#!/usr/bin/env python3
"""Deterministically validate and lock normal-mode user-test artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{path}: invalid UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{path}: root must be an object")
    return value, raw


def exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing or extra:
        fail(f"{where}: missing={sorted(missing)} extra={sorted(extra)}")


def text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{where}: must be a non-empty string")
    return value


def text_list(value: Any, where: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        fail(f"{where}: must be {'an' if allow_empty else 'a non-'}empty string array")
    for index, item in enumerate(value):
        text(item, f"{where}[{index}]")
    return value


SPEC_KEYS = {
    "schema_version", "spec_id", "version", "goal", "persona", "public_entry",
    "test_data", "minimal_test_count_rationale", "execution_policy",
    "tests", "reporting", "coverage", "revision",
}
TEST_KEYS = {
    "id", "title", "user_task", "setup", "actions", "functional_expectations",
    "ux_checks", "impossible_if", "isolation_requirements", "budget",
}


def validate_spec(spec: dict[str, Any], *, previous: dict[str, Any] | None = None) -> None:
    exact_keys(spec, SPEC_KEYS, "spec")
    if spec["schema_version"] != "user-test-spec/v1":
        fail("spec.schema_version: expected user-test-spec/v1")
    spec_id = text(spec["spec_id"], "spec.spec_id")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", spec_id):
        fail("spec.spec_id: use lowercase kebab-case")
    if not isinstance(spec["version"], int) or isinstance(spec["version"], bool) or spec["version"] < 1:
        fail("spec.version: must be a positive integer")
    for key in ("goal", "persona", "public_entry", "minimal_test_count_rationale"):
        text(spec[key], f"spec.{key}")
    text_list(spec["test_data"], "spec.test_data", allow_empty=True)

    exact_keys(spec["execution_policy"], {"runs_per_test", "continue_after_failure", "parallelize_independent_tests"}, "spec.execution_policy")
    if spec["execution_policy"] != {"runs_per_test": 1, "continue_after_failure": True, "parallelize_independent_tests": True}:
        fail("spec.execution_policy: run once, continue after failure, and parallelize independent journeys")

    tests = spec["tests"]
    if not isinstance(tests, list) or not tests:
        fail("spec.tests: at least one test is required")
    seen: set[str] = set()
    for index, case in enumerate(tests):
        where = f"spec.tests[{index}]"
        if not isinstance(case, dict):
            fail(f"{where}: must be an object")
        exact_keys(case, TEST_KEYS, where)
        case_id = text(case["id"], f"{where}.id")
        if case_id in seen:
            fail(f"{where}.id: duplicate {case_id}")
        seen.add(case_id)
        for key in ("title", "user_task"):
            text(case[key], f"{where}.{key}")
        text_list(case["setup"], f"{where}.setup", allow_empty=True)
        for key in ("actions", "functional_expectations", "ux_checks", "impossible_if"):
            text_list(case[key], f"{where}.{key}")
        text(case["isolation_requirements"], f"{where}.isolation_requirements")
        budget = case["budget"]
        if not isinstance(budget, dict):
            fail(f"{where}.budget: must be an object")
        exact_keys(budget, {"public_steps_minutes", "expected_external_wait_minutes", "total_minutes", "basis"}, f"{where}.budget")
        for key in ("public_steps_minutes", "expected_external_wait_minutes", "total_minutes"):
            value = budget[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                fail(f"{where}.budget.{key}: must be a non-negative number")
        if budget["total_minutes"] <= 0 or budget["total_minutes"] != budget["public_steps_minutes"] + budget["expected_external_wait_minutes"]:
            fail(f"{where}.budget: total must be positive and equal public steps + expected wait")
        text(budget["basis"], f"{where}.budget.basis")

    exact_keys(spec["reporting"], {"separate_functional_and_ux", "include_unexpected_findings", "evidence_level"}, "spec.reporting")
    if spec["reporting"] != {
        "separate_functional_and_ux": True,
        "include_unexpected_findings": True,
        "evidence_level": "concise",
    }:
        fail("spec.reporting: normal-mode reporting contract changed")
    exact_keys(spec["coverage"], {"covered_risks", "blind_spots"}, "spec.coverage")
    text_list(spec["coverage"]["covered_risks"], "spec.coverage.covered_risks")
    text_list(spec["coverage"]["blind_spots"], "spec.coverage.blind_spots", allow_empty=True)

    revision = spec["revision"]
    if spec["version"] == 1:
        if revision is not None:
            fail("spec.revision: version 1 must be null")
    else:
        if not isinstance(revision, dict):
            fail("spec.revision: required for a revised version")
        exact_keys(revision, {"kind", "previous_version", "issue", "raw_observation"}, "spec.revision")
        if revision["kind"] != "TEST_SPEC_ISSUE" or revision["previous_version"] != spec["version"] - 1:
            fail("spec.revision: only TEST_SPEC_ISSUE may create the next version")
        text(revision["issue"], "spec.revision.issue")
        text(revision["raw_observation"], "spec.revision.raw_observation")
    if previous is not None:
        validate_spec(previous)
        if spec_id != previous["spec_id"] or spec["version"] != previous["version"] + 1:
            fail("spec revision: keep spec_id and increment version by exactly one")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def lock_value(spec: dict[str, Any], raw: bytes) -> dict[str, Any]:
    return {"spec_id": spec["spec_id"], "version": spec["version"], "sha256": digest(raw)}


def verify_lock(spec: dict[str, Any], raw: bytes, path: Path) -> dict[str, Any]:
    lock, _ = load_json(path)
    exact_keys(lock, {"spec_id", "version", "sha256"}, "lock")
    if lock != lock_value(spec, raw):
        fail(f"{path}: lock does not match the exact spec bytes")
    return lock


REPORT_KEYS = {
    "schema_version", "spec_id", "spec_version", "spec_sha256", "executor_id",
    "started_at", "finished_at", "scheduling", "execution_artifacts", "tests", "product_findings_count", "blind_spots",
}
REPORT_TEST_KEYS = {
    "id", "execution_count", "status", "functional_findings", "ux_findings",
    "unexpected_findings", "test_spec_issues", "evidence", "batch",
    "journey_started_at", "journey_stopped_at", "stop_reason", "cleanup",
}


def parse_time(value: Any, where: str) -> datetime:
    raw = text(value, where)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"{where}: invalid ISO-8601 timestamp: {exc}")


def optional_time(value: Any, where: str) -> datetime | None:
    return None if value is None else parse_time(value, where)


def validate_report(report: dict[str, Any], spec: dict[str, Any], lock: dict[str, Any]) -> None:
    exact_keys(report, REPORT_KEYS, "report")
    if report["schema_version"] != "user-test-report/v1":
        fail("report.schema_version: expected user-test-report/v1")
    if (report["spec_id"], report["spec_version"], report["spec_sha256"]) != (
        lock["spec_id"], lock["version"], lock["sha256"]
    ):
        fail("report: spec binding does not match the verified lock")
    text(report["executor_id"], "report.executor_id")
    start = parse_time(report["started_at"], "report.started_at")
    finish = parse_time(report["finished_at"], "report.finished_at")
    if finish < start:
        fail("report: finished_at precedes started_at")
    scheduling = report["scheduling"]
    if not isinstance(scheduling, dict):
        fail("report.scheduling: must be an object")
    exact_keys(scheduling, {"available_executor_slots", "batch_count"}, "report.scheduling")
    slots = scheduling["available_executor_slots"]
    batches = scheduling["batch_count"]
    if not isinstance(slots, int) or isinstance(slots, bool) or slots < 1:
        fail("report.scheduling.available_executor_slots: must be a positive integer")
    expected_batches = (len(spec["tests"]) + min(slots, len(spec["tests"])) - 1) // min(slots, len(spec["tests"]))
    if batches != expected_batches:
        fail("report.scheduling.batch_count: must use the minimum number of batches")
    artifacts = report["execution_artifacts"]
    if not isinstance(artifacts, dict):
        fail("report.execution_artifacts: must be an object")
    exact_keys(artifacts, {"preserved_workspace", "completed_record"}, "report.execution_artifacts")
    for key in ("preserved_workspace", "completed_record"):
        if artifacts[key] is not None:
            text(artifacts[key], f"report.execution_artifacts.{key}")

    cases = report["tests"]
    if not isinstance(cases, list) or len(cases) != len(spec["tests"]):
        fail("report.tests: include every fixed test exactly once")
    expected_ids = [case["id"] for case in spec["tests"]]
    finding_count = 0
    intervals: dict[int, list[tuple[datetime, datetime]]] = {}
    for index, case in enumerate(cases):
        where = f"report.tests[{index}]"
        if not isinstance(case, dict):
            fail(f"{where}: must be an object")
        exact_keys(case, REPORT_TEST_KEYS, where)
        if case["id"] != expected_ids[index]:
            fail(f"{where}.id: preserve fixed test order")
        if case["status"] not in {"PASS", "FINDINGS", "INCOMPLETE", "NOT_RUN"}:
            fail(f"{where}.status: invalid value")
        for key in ("functional_findings", "ux_findings", "unexpected_findings", "test_spec_issues", "evidence"):
            text_list(case[key], f"{where}.{key}", allow_empty=True)
        product_count = sum(len(case[key]) for key in ("functional_findings", "ux_findings", "unexpected_findings"))
        finding_count += product_count
        batch = case["batch"]
        if not isinstance(batch, int) or isinstance(batch, bool) or not 1 <= batch <= batches:
            fail(f"{where}.batch: outside declared batch range")
        journey_start = optional_time(case["journey_started_at"], f"{where}.journey_started_at")
        journey_stop = optional_time(case["journey_stopped_at"], f"{where}.journey_stopped_at")
        if case["stop_reason"] not in {"completed", "budget", "impossible", "unsafe"}:
            fail(f"{where}.stop_reason: invalid value")
        exact_keys(case["cleanup"], {"status", "finished_at", "evidence"}, f"{where}.cleanup")
        if case["cleanup"]["status"] not in {"completed", "failed"}:
            fail(f"{where}.cleanup.status: expected completed or failed")
        cleanup_finish = parse_time(case["cleanup"]["finished_at"], f"{where}.cleanup.finished_at")
        if journey_stop is not None and cleanup_finish < journey_stop:
            fail(f"{where}.cleanup.finished_at: precedes journey stop")
        text(case["cleanup"]["evidence"], f"{where}.cleanup.evidence")
        if case["status"] == "NOT_RUN":
            if case["execution_count"] != 0 or journey_start is not None or journey_stop is not None:
                fail(f"{where}: NOT_RUN requires execution_count=0 and null journey timestamps")
        else:
            if journey_start is None or journey_stop is None:
                fail(f"{where}: executed journey requires start and stop timestamps")
            journey_elapsed = (journey_stop - journey_start).total_seconds()
            budget_seconds = spec["tests"][index]["budget"]["total_minutes"] * 60
            if journey_elapsed < 0 or journey_elapsed > budget_seconds:
                fail(f"{where}: journey exceeded its predeclared budget")
            intervals.setdefault(batch, []).append((journey_start, journey_stop))
            if case["execution_count"] != 1:
                fail(f"{where}: an executed test must run exactly once")
            if case["stop_reason"] == "completed":
                expected_status = "FINDINGS" if product_count else "PASS"
                if case["status"] != expected_status:
                    fail(f"{where}.status: inconsistent with product findings")
            elif case["status"] != "INCOMPLETE":
                fail(f"{where}.status: non-completed journey must be INCOMPLETE")

    if not isinstance(report["product_findings_count"], int) or report["product_findings_count"] != finding_count:
        fail("report.product_findings_count: must equal functional + UX + unexpected findings")
    for batch, spans in intervals.items():
        if len(spans) > slots:
            fail(f"report batch {batch}: exceeds available executor slots")
        if len(spans) > 1 and max(span[0] for span in spans) > min(span[1] for span in spans):
            fail(f"report batch {batch}: independent journeys did not overlap")
    text_list(report["blind_spots"], "report.blind_spots", allow_empty=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="artifact", required=True)
    spec_parser = sub.add_parser("spec")
    spec_parser.add_argument("path", type=Path)
    spec_parser.add_argument("--previous", type=Path)
    spec_parser.add_argument("--create-lock", type=Path)
    spec_parser.add_argument("--verify-lock", type=Path)
    report_parser = sub.add_parser("report")
    report_parser.add_argument("path", type=Path)
    report_parser.add_argument("--spec", required=True, type=Path)
    report_parser.add_argument("--verify-lock", required=True, type=Path)
    report_parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    try:
        if args.artifact == "spec":
            spec, raw = load_json(args.path)
            previous = load_json(args.previous)[0] if args.previous else None
            validate_spec(spec, previous=previous)
            if args.create_lock and args.verify_lock:
                fail("choose only one of --create-lock and --verify-lock")
            if args.create_lock:
                if args.create_lock.exists():
                    fail(f"{args.create_lock}: refusing to overwrite an existing lock")
                args.create_lock.write_text(json.dumps(lock_value(spec, raw), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if args.verify_lock:
                verify_lock(spec, raw, args.verify_lock)
            print(f"PASS spec {spec['spec_id']} v{spec['version']} sha256={digest(raw)}")
        else:
            spec, raw = load_json(args.spec)
            validate_spec(spec)
            lock = verify_lock(spec, raw, args.verify_lock)
            report, _ = load_json(args.path)
            validate_report(report, spec, lock)
            incomplete = sum(case["status"] in {"INCOMPLETE", "NOT_RUN"} for case in report["tests"])
            cleanup_failed = sum(case["cleanup"]["status"] != "completed" for case in report["tests"])
            if args.require_complete and (report["product_findings_count"] or incomplete or cleanup_failed):
                fail(
                    "improvement gate remains open: "
                    f"findings={report['product_findings_count']} incomplete={incomplete} cleanup_failed={cleanup_failed}"
                )
            print(f"PASS report findings={report['product_findings_count']} incomplete={incomplete}")
    except (OSError, ValidationError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

