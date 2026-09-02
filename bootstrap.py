#!/usr/bin/env python3
"""Install and verify the public agent-lab rules and skills."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

from tools import session_memory


ROOT = Path(__file__).resolve().parent
SHARED_SKILLS = ROOT / "skills/shared"
CODEX_SKILLS = ROOT / "skills/codex"
RULE = ROOT / "rules/core.md"
TOOL_SOURCES = {
    "bootstrap.py": ROOT / "bootstrap.py",
    "audit_public.py": ROOT / "tools/audit_public.py",
    "compatibility.py": ROOT / "tools/compatibility.py",
    "session_memory.py": ROOT / "tools/session_memory.py",
}
START = "<!-- agent-lab-public:start -->"
END = "<!-- agent-lab-public:end -->"


def tree_hash(path: Path) -> str:
    # Content hashes make install idempotent across copied directories
    # without depending on timestamps that differ after clone or extraction.
    digest = hashlib.sha256()
    if not path.exists():
        return "missing"
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def installed_rule(home: Path) -> Path:
    return home / ".agent-lab-public/rules/core.md"


def managed_block(home: Path) -> str:
    # Both agents receive the same portable rule through an absolute
    # import resolved from the user's public clone, not a baked-in machine path.
    return f"{START}\n@{installed_rule(home).as_posix()}\n{END}"


def merged_index(existing: str, home: Path) -> str:
    # Only the marked block is managed; unknown user instructions stay
    # byte-for-byte outside it and remain recoverable through the backup too.
    block = managed_block(home)
    if START not in existing and END not in existing:
        prefix = existing.rstrip()
        return f"{prefix}\n\n{block}\n" if prefix else f"{block}\n"
    if existing.count(START) != 1 or existing.count(END) != 1:
        raise ValueError("managed rule markers are incomplete or duplicated")
    before, tail = existing.split(START, 1)
    _, after = tail.split(END, 1)
    return f"{before}{block}{after}"


def backup(path: Path, home: Path, backup_root: Path) -> None:
    # Every replacement is copied to a timestamped relative path before
    # mutation, preserving both files and complete pre-existing skill folders.
    if not path.exists():
        return
    relative = path.relative_to(home)
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, destination)
    else:
        shutil.copy2(path, destination)


def install_index(path: Path, home: Path, backup_root: Path) -> str:
    # Index updates converge on one managed import while preserving all
    # user-owned text around it, so repeated installs do not create churn.
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    desired = merged_index(existing, home)
    if existing == desired:
        return "REUSED"
    backup(path, home, backup_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desired, encoding="utf-8")
    return "INSTALLED"


def install_skill(source: Path, destination: Path, home: Path, backup_root: Path) -> str:
    # Managed skill names are refreshed as complete units; unrelated
    # skill directories in the same parent are never enumerated or removed.
    if tree_hash(source) == tree_hash(destination):
        return "REUSED"
    backup(destination, home, backup_root)
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return "INSTALLED"


def install_file(source: Path, destination: Path, home: Path, backup_root: Path) -> str:
    if tree_hash(source) == tree_hash(destination):
        return "REUSED"
    backup(destination, home, backup_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return "INSTALLED"


def source_skills() -> tuple[dict[str, Path], dict[str, Path]]:
    # Codex starts with shared skills then applies explicit overrides;
    # Claude receives only provider-neutral shared procedures.
    shared = {path.name: path for path in SHARED_SKILLS.iterdir() if path.is_dir()}
    codex = dict(shared)
    codex.update({path.name: path for path in CODEX_SKILLS.iterdir() if path.is_dir()})
    return shared, codex


def target_inventory() -> dict[str, object]:
    shared, codex = source_skills()
    targets = [
        {"category": "rules", "owner": "shared", "root": "home", "path": ".agent-lab-public/rules/core.md"},
        {"category": "tooling", "owner": "shared", "root": "home", "path": ".agent-lab-public/tools/bootstrap.py"},
        {"category": "tooling", "owner": "shared", "root": "home", "path": ".agent-lab-public/tools/audit_public.py"},
        {"category": "tooling", "owner": "shared", "root": "home", "path": ".agent-lab-public/tools/compatibility.py"},
        {"category": "tooling", "owner": "shared", "root": "home", "path": ".agent-lab-public/tools/session_memory.py"},
        {"category": "rules", "owner": "claude-code", "root": "home", "path": ".claude/CLAUDE.md"},
        {"category": "rules", "owner": "codex", "root": "home", "path": ".codex/AGENTS.md"},
    ]
    targets.extend(
        {"category": "skills", "owner": "claude-code", "root": "home", "path": f".claude/skills/{name}"}
        for name in sorted(shared)
    )
    targets.extend(
        {"category": "skills", "owner": "codex", "root": "home", "path": f".agents/skills/{name}"}
        for name in sorted(codex)
    )
    return {"schema": "agent-lab-public-targets-v1", "configuration_root": "home", "targets": targets}


def install(home: Path) -> int:
    # One timestamp groups all backups from a single transaction and is
    # created lazily only if a pre-existing asset is actually replaced.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = home / ".agent-lab-public/backups" / stamp
    shared, codex = source_skills()
    results = [
        ("generic rule", install_file(RULE, installed_rule(home), home, backup_root)),
        *(
            (f"tooling {name}", install_file(source, home / ".agent-lab-public/tools" / name, home, backup_root))
            for name, source in TOOL_SOURCES.items()
        ),
        ("Claude Code rules", install_index(home / ".claude/CLAUDE.md", home, backup_root)),
        ("Codex rules", install_index(home / ".codex/AGENTS.md", home, backup_root)),
    ]
    for name, source in shared.items():
        results.append((f"Claude skill {name}", install_skill(source, home / ".claude/skills" / name, home, backup_root)))
    for name, source in codex.items():
        results.append((f"Codex skill {name}", install_skill(source, home / ".agents/skills" / name, home, backup_root)))
    for label, status in results:
        print(f"{status}: {label}")
    print("MANUAL: sign in to Claude Code and Codex in each application when you use them")
    print("NEXT: python bootstrap.py check")
    return 0


def check_index(path: Path, home: Path) -> bool:
    # Verification requires the exact current managed block, not merely
    # the existence of an agent index that could still reference an old clone.
    return path.is_file() and managed_block(home) in path.read_text(encoding="utf-8")


def check(home: Path) -> int:
    # Component-level output is intentionally stable and front-loaded so
    # partial installation cannot be mistaken for a generic success message.
    shared, codex = source_skills()
    checks = [
        ("generic rules", tree_hash(RULE) == tree_hash(installed_rule(home))),
        (
            "reusable tooling (bootstrap, public audit, compatibility)",
            all(tree_hash(source) == tree_hash(home / ".agent-lab-public/tools" / name) for name, source in TOOL_SOURCES.items()),
        ),
        ("Claude Code rules", check_index(home / ".claude/CLAUDE.md", home)),
        ("Codex rules", check_index(home / ".codex/AGENTS.md", home)),
        (
            f"Claude skills ({len(shared)})",
            all(tree_hash(source) == tree_hash(home / ".claude/skills" / name) for name, source in shared.items()),
        ),
        (
            f"Codex skills ({len(codex)})",
            all(tree_hash(source) == tree_hash(home / ".agents/skills" / name) for name, source in codex.items()),
        ),
    ]
    for label, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    if all(passed for _, passed in checks):
        print("PASS: agent-lab-public installation is complete")
        return 0
    print("NEXT: python bootstrap.py install, then python bootstrap.py check")
    return 1


def skill_name(path: Path) -> str | None:
    # Smoke reads the installed public asset itself, proving consumption
    # from the configured location rather than trusting source-tree inventory.
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def smoke(home: Path) -> int:
    # The credential-free test skill is common to both agents and makes
    # a deterministic end-to-end probe without launching or authenticating them.
    locations = {
        "Claude Code": home / ".claude/skills/test/SKILL.md",
        "Codex": home / ".agents/skills/test/SKILL.md",
    }
    failed = False
    for agent, path in locations.items():
        name = skill_name(path)
        if name == "test":
            print(f"PASS: {agent} capability=test path={path}")
        else:
            failed = True
            print(f"FAIL: {agent} installed test capability is unavailable at {path}")
    if failed:
        print("NEXT: python bootstrap.py install, then python bootstrap.py smoke")
        return 1
    print("PASS: installed reusable capability loaded")
    return 0


def require_agent(agent: str | None) -> str:
    if agent is None:
        raise ValueError("--agent claude or --agent codex is required")
    return agent


def install_memory(home: Path, agent: str) -> int:
    result = install(home)
    if result:
        return result
    path = session_memory.install_hooks(home, agent)
    print(f"PASS: local session memory installed for {agent}")
    print(f"hooks: {path}")
    print(f"NEXT: python bootstrap.py --home \"{home}\" check-memory --agent {agent} --project .")
    return 0


def remove_memory(home: Path, agent: str) -> int:
    path = session_memory.remove_hooks(home, agent)
    print(f"PASS: managed session memory hooks removed for {agent}")
    print(f"settings: {path}")
    print("KEPT: local journal and current files")
    return 0


def parse_args() -> argparse.Namespace:
    # An explicit home override enables safe trials and CI isolation;
    # normal users need only the three short README commands.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument(
        "command",
        choices=[
            "install", "check", "smoke", "targets", "install-memory", "check-memory",
            "memory-record", "memory-context", "remove-memory",
        ],
    )
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--agent", choices=["claude", "codex"])
    parser.add_argument("--project", type=Path)
    parser.add_argument("--event", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    home = args.home.expanduser().resolve()
    if args.command == "targets":
        print(json.dumps(target_inventory(), indent=2, sort_keys=True))
        return 0
    if args.command == "install":
        return install(home)
    if args.command == "check":
        return check(home)
    if args.command == "smoke":
        return smoke(home)
    agent = require_agent(args.agent)
    if args.command == "install-memory":
        return install_memory(home, agent)
    if args.command == "remove-memory":
        return remove_memory(home, agent)
    if args.command == "check-memory":
        return session_memory.check(home, agent, (args.project or Path.cwd()).expanduser().resolve())
    event = session_memory.load_event(args.event)
    project = args.project.expanduser().resolve() if args.project else None
    if args.command == "memory-record":
        paths = session_memory.record(home, agent, event, project)
        print(f"PASS: local session memory recorded\njournal: {paths['entry']}\ncurrent: {paths['current']}")
        return 0
    output = session_memory.context(home, event, project)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": output}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
