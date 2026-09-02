#!/usr/bin/env python3
"""Local, project-scoped session notes for Claude Code and Codex hooks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
from typing import Any, Iterable


MANAGED_ID = "agent-lab-public-session-memory"
EVENTS = ("SessionEnd", "SessionStart")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def settings_path(home: Path, agent: str) -> Path:
    return home / (".claude/settings.json" if agent == "claude" else ".codex/hooks.json")


def _command(home: Path, agent: str, action: str) -> dict[str, Any]:
    tool = home / ".agent-lab-public/tools/session_memory.py"
    posix = " ".join(
        shlex.quote(part)
        for part in (
            "python3", str(tool), action, "--home", str(home), "--agent", agent,
            "--managed-id", MANAGED_ID,
        )
    )
    windows_parts = (
        "python", str(tool), action, "--home", str(home), "--agent", agent,
        "--managed-id", MANAGED_ID,
    )
    windows = "& " + " ".join("'" + part.replace("'", "''") + "'" for part in windows_parts)
    result: dict[str, Any] = {"type": "command", "command": posix, "timeout": 10}
    if agent == "claude":
        result = {"type": "command", "command": windows if sys.platform == "win32" else posix, "timeout": 10}
        if sys.platform == "win32":
            result["shell"] = "powershell"
    else:
        result["commandWindows"] = windows
        result["statusMessage"] = "Saving or loading local project session context"
    return result


def _managed_hook(hook: Any) -> bool:
    return isinstance(hook, dict) and MANAGED_ID in str(hook.get("command", "")) + str(hook.get("commandWindows", ""))


def _remove_managed(groups: Any) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    if not isinstance(groups, list):
        return clean
    for group in groups:
        if not isinstance(group, dict):
            continue
        copied = dict(group)
        existing = copied.get("hooks")
        if isinstance(existing, list):
            copied["hooks"] = [hook for hook in existing if not _managed_hook(hook)]
            if copied["hooks"]:
                clean.append(copied)
        elif not _managed_hook(copied):
            clean.append(copied)
    return clean


def hook_counts(home: Path, agent: str) -> dict[str, int]:
    data = _read_json(settings_path(home, agent))
    hooks = data.get("hooks", {})
    counts: dict[str, int] = {}
    for event in EVENTS:
        count = 0
        for group in hooks.get(event, []) if isinstance(hooks, dict) else []:
            entries = group.get("hooks", []) if isinstance(group, dict) else []
            count += sum(1 for item in entries if _managed_hook(item))
        counts[event] = count
    return counts


def install_hooks(home: Path, agent: str) -> Path:
    path = settings_path(home, agent)
    data = _read_json(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"hooks must be a JSON object: {path}")
    for event, action in (("SessionEnd", "record"), ("SessionStart", "context")):
        groups = _remove_managed(hooks.get(event, []))
        group: dict[str, Any] = {"hooks": [_command(home, agent, action)]}
        if agent == "codex" and event == "SessionStart":
            group["matcher"] = "startup|resume|clear|compact"
        groups.append(group)
        hooks[event] = groups
    _write_json(path, data)
    return path


def remove_hooks(home: Path, agent: str) -> Path:
    path = settings_path(home, agent)
    data = _read_json(path)
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for event in EVENTS:
            if event in hooks:
                cleaned = _remove_managed(hooks[event])
                if cleaned:
                    hooks[event] = cleaned
                else:
                    hooks.pop(event, None)
    _write_json(path, data)
    return path


def project_path(event: dict[str, Any], explicit: Path | None = None) -> Path:
    raw = explicit or event.get("cwd") or event.get("project_path") or Path.cwd()
    return Path(raw).expanduser().resolve()


def memory_paths(home: Path, project: Path) -> dict[str, Path]:
    identity = str(project.resolve())
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project.name).strip("-") or "project"
    key = f"{slug}-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"
    root = home / ".agent-lab-public/runtime-memory/projects" / key
    return {"root": root, "journal": root / "journal", "current": root / "current.md"}


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key.lower() not in {"usage", "metadata", "id", "timestamp"}:
                yield from _strings(item)


def transcript_text(path: Path) -> str:
    parts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            value = line
        parts.extend(text.strip() for text in _strings(value) if text.strip())
    return "\n".join(dict.fromkeys(parts))


def _sentences(text: str) -> list[str]:
    values: list[str] = []
    for raw in re.split(r"[\r\n]+|(?<=[.!?。！？])\s+", text):
        cleaned = re.sub(r"\s+", " ", raw).strip(" -*\t")
        if cleaned and len(cleaned) <= 600:
            values.append(cleaned)
    return list(dict.fromkeys(values))


def _select(sentences: list[str], patterns: tuple[str, ...]) -> list[str]:
    return [sentence for sentence in sentences if any(pattern in sentence.lower() for pattern in patterns)]


def summarize(text: str) -> dict[str, list[str]]:
    sentences = _sentences(text)
    decisions = _select(sentences, (" because ", "because ", "reason:", "理由", "なので", "ため", "decision:"))
    next_work = _select(sentences, ("next", "todo", "verify start injection", "次", "残り", "未完了"))
    completed = _select(sentences, ("complete", "completed", "done", "finished", "完了", "実装した", "対応した"))
    used = set(decisions + next_work)
    completed = [item for item in completed if item not in used]
    if not completed:
        completed = [item for item in sentences if item not in used][:1]
    return {
        "Work completed": completed or ["No completed work was explicitly stated."],
        "Decisions and reasons": decisions or ["No decision and reason were explicitly stated."],
        "Next work": next_work or ["No next work was explicitly stated."],
    }


def _section(title: str, values: list[str]) -> str:
    return f"## {title}\n" + "\n".join(f"- {value}" for value in values)


def render_summary(summary: dict[str, list[str]]) -> str:
    return "\n\n".join(_section(title, summary[title]) for title in summary) + "\n"


def load_event(event_path: Path | None) -> dict[str, Any]:
    if event_path:
        return _read_json(event_path)
    if sys.stdin.isatty():
        return {}
    payload = sys.stdin.read().strip()
    return json.loads(payload) if payload else {}


def record(home: Path, agent: str, event: dict[str, Any], explicit_project: Path | None = None) -> dict[str, Path]:
    project = project_path(event, explicit_project)
    transcript = event.get("transcript_path") or event.get("transcriptPath")
    if not transcript:
        raise ValueError("event must include transcript_path")
    source = Path(transcript).expanduser().resolve()
    text = transcript_text(source)
    summary = summarize(text)
    paths = memory_paths(home, project)
    session_id = str(event.get("session_id") or event.get("sessionId") or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16])
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", session_id)[:80] or "session"
    journal = paths["journal"] / f"{safe_id}.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    if not journal.exists():
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        journal.write_text(f"# Session {safe_id}\n\nRecorded: {created}\nAgent: {agent}\n\n{render_summary(summary)}", encoding="utf-8")
    paths["current"].parent.mkdir(parents=True, exist_ok=True)
    paths["current"].write_text(
        f"# Current project context\n\nProject: {project.name}\nSource journal: {journal.name}\n\n{render_summary(summary)}",
        encoding="utf-8",
    )
    return {**paths, "entry": journal}


def context(home: Path, event: dict[str, Any], explicit_project: Path | None = None) -> str:
    project = project_path(event, explicit_project)
    paths = memory_paths(home, project)
    if not paths["current"].is_file():
        return ""
    current = paths["current"].read_text(encoding="utf-8").strip()
    recent = sorted(paths["journal"].glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)[:5]
    index = "\n".join(f"- {item.name}" for item in recent) or "- none"
    return f"Local project session context:\n\n{current}\n\n## Recent journal entries\n{index}"


def check(home: Path, agent: str, project: Path) -> int:
    counts = hook_counts(home, agent)
    paths = memory_paths(home, project.resolve())
    installed = all(counts[event] == 1 for event in EVENTS)
    print(f"{'PASS' if installed else 'NOT INSTALLED'}: agent={agent} project={project.resolve()}")
    print(f"SessionEnd hook: {counts['SessionEnd']} managed")
    print(f"SessionStart hook: {counts['SessionStart']} managed")
    print(f"journal: {paths['journal']}")
    print(f"current: {paths['current']}")
    return 0 if installed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["record", "context"])
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--agent", choices=["claude", "codex"], required=True)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--managed-id", default=MANAGED_ID)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    event = load_event(args.event)
    if args.action == "record":
        paths = record(args.home.expanduser().resolve(), args.agent, event, args.project)
        print(f"PASS: local session memory recorded\njournal: {paths['entry']}\ncurrent: {paths['current']}")
        return 0
    output = context(args.home.expanduser().resolve(), event, args.project)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": output}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
