"""Record Codex subscription usage without starting an AI turn."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import plistlib
import queue
import shutil
import subprocess
import sys
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

STATE_DIR = Path.home() / ".agent-lab" / "usage-monitor"
LABEL = "com.agent-lab.codex-usage"
FIELDS = (
    "observed_at", "account", "declared_plan", "bucket", "window",
    "window_minutes", "resets_at", "used_percent", "delta_10m_points",
    "measured_seconds", "status",
)
JST = timezone(timedelta(hours=9))


def codex_command(binary: str) -> list[str]:
    # AI_NOTE: npm's Windows .cmd shim is resolved to its native binary, avoiding a shell.
    executable = Path(binary)
    if sys.platform == "win32" and executable.suffix.lower() in (".cmd", ".bat", ".ps1"):
        machine = platform.machine().lower()
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        target = "aarch64" if arch == "arm64" else "x86_64"
        relative = Path("vendor") / f"{target}-pc-windows-msvc" / "bin" / "codex.exe"
        packages = executable.parent / "node_modules" / "@openai"
        candidates = [packages / f"codex-win32-{arch}" / relative,
                      packages / "codex" / "node_modules" / "@openai" / f"codex-win32-{arch}" / relative,
                      packages / "codex" / relative]
        executable = next((path for path in candidates if path.is_file()), Path())
        if not executable.is_file():
            raise FileNotFoundError("Use --codex with the native codex.exe path")
    return [str(executable.absolute()), "app-server"]


def lock_file(lock: TextIO) -> None:
    # AI_NOTE: Both OS implementations protect the same CSV against concurrent collectors.
    if sys.platform == "win32":
        import msvcrt
        if not lock.tell():
            lock.write("0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX)


class AppServer:
    def __init__(self, binary: str) -> None:
        # AI_NOTE: Only account methods are used; no thread or model execution is started.
        self.process = subprocess.Popen(
            codex_command(binary), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, encoding="utf-8",
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        self.messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.sequence = 0
        threading.Thread(target=self.read_messages, daemon=True).start()

    def read_messages(self) -> None:
        # AI_NOTE: A reader thread gives requests a timeout even for a silent server.
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        finally:
            self.messages.put(None)

    def send(self, message: dict[str, Any]) -> None:
        # AI_NOTE: Account credentials remain inside Codex's own authentication layer.
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # AI_NOTE: Match response IDs and ignore unsolicited notifications.
        self.sequence += 1
        self.send({"id": self.sequence, "method": method, "params": params or {}})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            if message is None:
                raise RuntimeError("app-server exited")
            if message.get("id") != self.sequence:
                continue
            if "error" in message:
                raise RuntimeError("app-server rejected usage request")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ValueError("invalid app-server response")
            return result
        raise TimeoutError("app-server response timeout")

    def snapshot(self) -> tuple[str, dict[str, Any]]:
        # AI_NOTE: Check the active account on each observation, avoiding mixed-account deltas.
        self.request("initialize", {"clientInfo": {"name": "agent_lab_usage_monitor", "version": "0.1.0"}})
        self.send({"method": "initialized", "params": {}})
        account = self.request("account/read").get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            raise ValueError("ChatGPT login required")
        identity = account.get("id") or account.get("email")
        if not isinstance(identity, str) or not identity:
            raise ValueError("account identity unavailable")
        fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:16]
        return fingerprint, self.request("account/rateLimits/read")

    def close(self) -> None:
        # AI_NOTE: Shut down this observer only, never the desktop app or its tasks.
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def read_recent(path: Path) -> list[dict[str, str]]:
    # AI_NOTE: Read a bounded tail, so minute-by-minute polling stays cheap as the file grows.
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open("rb") as source:
        header = source.readline().decode().strip().split(",")
        if tuple(header) != FIELDS:
            raise ValueError("usage CSV header differs")
        header_end = source.tell()
        offset = max(header_end, path.stat().st_size - 1024 * 1024)
        source.seek(offset)
        # A tail starting inside a record must discard its partial first line.
        if offset > header_end:
            source.readline()
        rows = list(csv.DictReader(source.read().decode("utf-8").splitlines(), fieldnames=FIELDS))
    last_error = max((i for i, row in enumerate(rows) if row["status"] == "fetch_error"), default=-1)
    return rows[last_error + 1:]


def usage_rows(
    snapshot: dict[str, Any], account: str, declared_plan: str,
    now: datetime, history: list[dict[str, str]],
) -> list[dict[str, str]]:
    # AI_NOTE: Deltas are percentage points of a quota window, never token counts or USD.
    buckets = snapshot.get("rateLimitsByLimitId") or {}
    if not buckets and isinstance(snapshot.get("rateLimits"), dict):
        bucket = snapshot["rateLimits"]
        buckets = {bucket.get("limitId") or "codex": bucket}
    if not isinstance(buckets, dict):
        raise ValueError("invalid rate-limit buckets")
    rows = []
    for bucket_id, bucket in buckets.items():
        if not isinstance(bucket, dict):
            raise ValueError("invalid rate-limit bucket")
        for kind in ("primary", "secondary"):
            window = bucket.get(kind)
            if window is None:
                continue
            if not isinstance(window, dict):
                raise ValueError("invalid rate-limit window")
            used = window.get("usedPercent")
            minutes = window.get("windowDurationMins")
            reset = window.get("resetsAt")
            if (
                isinstance(used, bool) or not isinstance(used, (int, float))
                or not math.isfinite(used) or not 0 <= used <= 100
                or isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0
                or isinstance(reset, bool) or not isinstance(reset, int)
            ):
                raise ValueError("invalid rate-limit window")
            row = dict.fromkeys(FIELDS, "")
            row.update(observed_at=now.isoformat(timespec="seconds"), account=account,
                       declared_plan=declared_plan, bucket=str(bucket_id), window=kind,
                       window_minutes=str(minutes), resets_at=str(reset), used_percent=str(used),
                       status="warming_up")
            previous = [item for item in history if all(item[key] == row[key] for key in
                        ("account", "bucket", "window", "window_minutes"))]
            # Stop at the most recent reset/decrease, even when the counter has since recovered.
            start = 0
            for i, item in enumerate(previous):
                if item["resets_at"] != str(reset):
                    start = i + 1
                elif i and float(item["used_percent"]) < float(previous[i - 1]["used_percent"]):
                    start = i
            previous = previous[start:]
            if previous and used < float(previous[-1]["used_percent"]):
                row["status"] = "counter_decreased"
                previous = []
            target = now.timestamp() - 600
            baselines = [item for item in previous if datetime.fromisoformat(item["observed_at"]).timestamp() <= target]
            if baselines:
                baseline = baselines[-1]
                times = [datetime.fromisoformat(item["observed_at"]).timestamp()
                         for item in previous[previous.index(baseline):]] + [now.timestamp()]
                span = times[-1] - times[0]
                if span > 690 or any(b - a > 90 or b < a for a, b in zip(times, times[1:])):
                    row["status"] = "gap"
                else:
                    row.update(delta_10m_points=str(round(used - float(baseline["used_percent"]), 6)),
                               measured_seconds=str(round(span)), status="ok")
            rows.append(row)
    if not rows:
        raise ValueError("no subscription windows returned")
    return rows


def record_once(binary: str, path: Path, plan: str) -> bool:
    # AI_NOTE: Serialize manual and scheduled observations; failures are explicit rows, not zeros.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.with_suffix(".lock").open("a") as lock:
        lock_file(lock)
        history = read_recent(path)
        server = None
        try:
            server = AppServer(binary)
            account, snapshot = server.snapshot()
            rows = usage_rows(snapshot, account, plan, datetime.now(JST), history)
        except (OSError, RuntimeError, ValueError, TimeoutError, queue.Empty) as error:
            rows = [dict.fromkeys(FIELDS, "")]
            rows[0].update(observed_at=datetime.now(JST).isoformat(timespec="seconds"),
                           declared_plan=plan, status="fetch_error")
            print(f"Usage acquisition failed: {type(error).__name__}", file=sys.stderr)
        finally:
            if server is not None:
                server.close()
        new_file = not path.exists() or not path.stat().st_size
        with path.open("a", newline="", encoding="utf-8") as output:
            os.chmod(path, 0o600)
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerows(rows)
        print(json.dumps({"file": str(path), "observations": [
            {key: row[key] for key in ("observed_at", "used_percent", "delta_10m_points", "status")}
            for row in rows]}, ensure_ascii=False))
        return all(row["status"] != "fetch_error" for row in rows)


def main() -> None:
    # AI_NOTE: Only explicit installation enables recording at login; bridge install stays unchanged.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("once", "install", "status", "check", "stop"))
    parser.add_argument("--codex", default=shutil.which("codex"))
    parser.add_argument("--csv", type=Path, default=STATE_DIR / "codex-usage.csv")
    parser.add_argument("--plan", default="ChatGPT")
    parser.add_argument("--log", type=Path, help="Redirect scheduled observations to this log")
    args = parser.parse_args()
    if args.action in ("once", "check"):
        if not args.codex:
            parser.error("codex executable not found")
        if args.action == "check":
            if sys.platform == "win32":
                subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                                str(Path(__file__).with_name("windows-task.ps1")), "-Action", "status"], check=True)
            elif sys.platform == "darwin":
                subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
                               check=True, stdout=subprocess.DEVNULL)
            else:
                parser.error("UNKNOWN: automatic scheduling on this OS must be verified separately")
        if args.log:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            with args.log.open("a", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
                successful = record_once(args.codex, args.csv.resolve(), args.plan)
        else:
            successful = record_once(args.codex, args.csv.resolve(), args.plan)
        raise SystemExit(0 if successful else 1)
    if sys.platform == "win32":
        if args.action == "install" and not args.codex:
            parser.error("Codex CLI missing: install it and run 'codex login', then retry")
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                   str(Path(__file__).with_name("windows-task.ps1")), "-Action", args.action]
        if args.action == "install":
            native = codex_command(args.codex)[0]
            if not Path(native).is_file():
                parser.error("Codex CLI missing: supply --codex with the codex.exe path")
            if not record_once(native, args.csv.resolve(), args.plan):
                parser.error("MANUAL: run 'codex login' or resolve acquisition failure before installation")
            runtime = Path(sys.executable)
            hidden = runtime.with_name("pythonw.exe")
            if not hidden.exists():
                parser.error("pythonw.exe missing: install standard Python for background recording")
            arguments = subprocess.list2cmdline([
                str(Path(__file__).resolve()), "once", "--codex", native,
                "--csv", str(args.csv.resolve()), "--plan", args.plan,
                "--log", str(args.csv.resolve().parent / "collector.log"),
            ])
            config = args.csv.resolve().parent / "windows-task.json"
            if config.exists():
                shutil.copy2(config, config.with_suffix(".previous.json"))
            config.write_text(json.dumps({"Python": str(hidden), "Arguments": arguments,
                                          "WorkingDirectory": str(args.csv.resolve().parent)}), encoding="utf-8")
            command += ["-ConfigPath", str(config)]
        subprocess.run(command, check=True)
        return
    if sys.platform != "darwin":
        parser.error("service management requires macOS; schedule 'once' on Linux")
    service = f"gui/{os.getuid()}/{LABEL}"
    plist = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if args.action in ("status", "stop"):
        result = subprocess.run(["launchctl", "print" if args.action == "status" else "bootout", service])
        raise SystemExit(result.returncode)
    if not args.codex:
        parser.error("codex executable not found")
    args.csv = args.csv.resolve()
    args.csv.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    plist.parent.mkdir(parents=True, exist_ok=True)
    definition = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "once",
                             "--codex", str(Path(args.codex).absolute()), "--csv", str(args.csv), "--plan", args.plan],
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        "WorkingDirectory": str(STATE_DIR), "RunAtLoad": True, "StartInterval": 60,
        "StandardOutPath": str(args.csv.parent / "collector.log"),
        "StandardErrorPath": str(args.csv.parent / "collector.log"),
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if subprocess.run(["launchctl", "print", service], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.run(["launchctl", "bootout", service], check=True)
    with plist.open("wb") as output:
        os.chmod(plist, 0o600)
        plistlib.dump(definition, output)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], check=True)
    print(f"Recording every 60 seconds: {args.csv}")


if __name__ == "__main__":
    main()
