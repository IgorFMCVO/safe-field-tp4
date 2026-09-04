#!/usr/bin/env python3
"""Summarize SAFE-FIELD UART bridge JSONL without modifying source evidence."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def summarize(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("capture contains no records")

    sequence_errors = 0
    frame_step_errors = 0
    for previous, current in zip(rows, rows[1:]):
        if (current["seq"] - previous["seq"]) & 0xFFFF != 1:
            sequence_errors += 1
        if (current["frame_counter"] - previous["frame_counter"]) & 0xFFFFFFFF != 256:
            frame_step_errors += 1

    segments = []
    start = 0
    for index in range(1, len(rows) + 1):
        if index == len(rows) or rows[index]["state"] != rows[start]["state"]:
            subset = rows[start:index]
            energies = [row["energy"] for row in subset]
            segments.append(
                {
                    "state": rows[start]["state"],
                    "records": len(subset),
                    "start": subset[0]["timestamp"],
                    "end": subset[-1]["timestamp"],
                    "energy_min": min(energies),
                    "energy_max": max(energies),
                    "energy_mean": round(statistics.fmean(energies), 2),
                }
            )
            start = index

    energies = [row["energy"] for row in rows]
    return {
        "source": str(path),
        "records": len(rows),
        "start": rows[0]["timestamp"],
        "end": rows[-1]["timestamp"],
        "sequence": {"first": rows[0]["seq"], "last": rows[-1]["seq"], "discontinuities": sequence_errors},
        "frame_counter": {
            "first": rows[0]["frame_counter"],
            "last": rows[-1]["frame_counter"],
            "expected_step": 256,
            "step_errors": frame_step_errors,
        },
        "energy": {
            "min": min(energies),
            "max": max(energies),
            "mean": round(statistics.fmean(energies), 2),
        },
        "flags": sorted(set(row["flags"] for row in rows)),
        "segments": segments,
        "quiet_active_quiet": any(
            [segment["state"] for segment in segments[i : i + 3]] == ["QUIET", "ACTIVE", "QUIET"]
            for i in range(max(0, len(segments) - 2))
        ),
        "result": "PASS" if sequence_errors == 0 and frame_step_errors == 0 else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = summarize(args.input)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
