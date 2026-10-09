"""Generate an offline usage graph from the local Codex recording (no AI calls)."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import TypedDict

STATE_DIR = Path.home() / ".agent-lab" / "usage-monitor"


class Sample(TypedDict):
    t: float
    used: float | None
    delta: float | None
    seconds: float | None
    reset: str
    status: str


class Series(TypedDict):
    label: str
    plan: str
    samples: list[Sample]


def number(value: str) -> float | None:
    # AI_NOTE: Missing measurements stay unknown, while a recorded zero stays zero.
    if not value:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite measurement")
    return result


def read_series(path: Path) -> list[Series]:
    # AI_NOTE: Separate account/window series and apply unknown acquisition failures to all.
    groups: dict[tuple[str, str, str, str], Series] = {}
    accounts: dict[str, int] = {}
    failures: list[Sample] = []
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        required = {"observed_at", "account", "bucket", "window", "window_minutes",
                    "used_percent", "delta_10m_points", "measured_seconds", "resets_at",
                    "status", "declared_plan"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Codex記録CSVの列が揃っていません")
        for row in reader:
            try:
                time = datetime.fromisoformat(row["observed_at"])
                if time.tzinfo is None:
                    raise ValueError("time zone missing")
                status = row["status"]
                sample: Sample = {
                    "t": time.timestamp() * 1000,
                    "used": None if status == "fetch_error" else number(row["used_percent"]),
                    "delta": number(row["delta_10m_points"]) if status == "ok" else None,
                    "seconds": number(row["measured_seconds"]) if status == "ok" else None,
                    "reset": row["resets_at"], "status": status,
                }
                if status == "fetch_error":
                    failures.append(sample)
                    continue
                used = sample["used"]
                if used is None or not 0 <= used <= 100:
                    raise ValueError("usage outside 0–100")
                if sample["delta"] is not None and not 0 <= sample["delta"] <= 100:
                    raise ValueError("invalid increase")
                if status == "ok" and (sample["delta"] is None or sample["seconds"] is None
                                      or not 600 <= sample["seconds"] <= 690):
                    raise ValueError("invalid comparison interval")
                account = row["account"]
                minutes = int(row["window_minutes"])
                if not account or not row["bucket"] or not row["window"] or minutes <= 0:
                    raise ValueError("window identity missing")
                accounts.setdefault(account, len(accounts) + 1)
                key = (account, row["bucket"], row["window"], row["window_minutes"])
                period = "週間枠" if minutes == 10080 else f"{minutes / 60:g}時間枠"
                if key not in groups:
                    groups[key] = {"label": f"アカウント{accounts[account]} · {row['bucket']} · "
                                           f"{period} ({row['window']})",
                                   "plan": row["declared_plan"], "samples": []}
                groups[key]["samples"].append(sample)
            except (ValueError, TypeError) as error:
                raise ValueError(f"CSV {reader.line_num}行目を読めません: {error}") from error
    if not groups:
        raise ValueError("使用率の有効な記録がまだありません")
    for series in groups.values():
        series["samples"] = sorted(series["samples"] + failures, key=lambda item: item["t"])
    return list(groups.values())


def write_graph(source: Path, output: Path) -> None:
    # AI_NOTE: Embedded data permits offline viewing; escape '<' to prevent script termination.
    if source.resolve() == output.resolve():
        raise ValueError("出力先は入力CSVと別のファイルにしてください")
    payload = json.dumps(read_series(source), ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("graph.html").read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("@@DATA@@", payload), encoding="utf-8")
    output.chmod(0o600)


def main() -> None:
    # AI_NOTE: Use each PC's existing CSV by default; recording and graph generation are independent.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=STATE_DIR / "codex-usage.csv")
    parser.add_argument("--output", type=Path, default=STATE_DIR / "usage-graph.html")
    args = parser.parse_args()
    try:
        write_graph(args.csv, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"グラフを生成できません: {error}\n")
    print(args.output.absolute())


if __name__ == "__main__":
    main()
