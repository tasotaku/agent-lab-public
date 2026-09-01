#!/usr/bin/env python3
"""Refresh the curated public skills from a local private agent-lab checkout."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


MAPPINGS = {
    "skills/design-user-tests": "skills/shared/design-user-tests",
    "skills/improve-with-user-tests": "skills/shared/improve-with-user-tests",
    "skills/loop-engineering": "skills/shared/loop-engineering",
    "skills/run-user-tests": "skills/shared/run-user-tests",
    "skills/test": "skills/shared/test",
    "skills/write-for-readers": "skills/shared/write-for-readers",
    "codex-skills/make-portable": "skills/codex/make-portable",
    "codex-skills/plan": "skills/codex/plan",
    "codex-skills/rethink": "skills/codex/rethink",
    "codex-skills/self-review": "skills/codex/self-review",
    "codex-skills/visual-verify": "skills/codex/visual-verify",
}
FORBIDDEN_PARTS = {"knowledge", "user-config", ".git", ".agent-lab", ".claude", ".codex"}


def sync(source: Path, destination: Path) -> list[str]:
    # A fixed allowlist makes future refreshes additive only through an
    # explicit review of this manifest, never through a broad private-tree copy.
    copied: list[str] = []
    for source_text, destination_text in MAPPINGS.items():
        source_path = source / source_text
        destination_path = destination / destination_text
        if not source_path.is_dir():
            raise FileNotFoundError(f"missing curated source: {source_path}")
        if FORBIDDEN_PARTS.intersection(source_path.parts):
            raise ValueError(f"forbidden source path: {source_path}")
        if destination_path.exists():
            shutil.rmtree(destination_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_path, destination_path)
        copied.append(destination_text)
    return copied


def main() -> int:
    # The private source is always caller-supplied so the public tree
    # contains no machine-specific path or private remote dependency.
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1]
    for path in sync(args.source.resolve(), destination):
        print(f"COPIED: {path}")
    print("NEXT: python tools/audit_public.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
