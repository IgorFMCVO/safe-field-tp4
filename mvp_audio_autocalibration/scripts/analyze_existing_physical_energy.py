#!/usr/bin/env python3
"""Audit historical physical energy evidence without relabelling it.

This script deliberately reports state-transition behaviour separately from
classification accuracy. Most historical captures have no trustworthy acoustic
labels, so a quieter state trace is not treated as a successful voice detector.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path


def old_detector(values, on=12000, off=6000, attack=24, release=82):
    active = False
    attack_count = release_count = 0
    states = []
    for value in values:
        if not active:
            release_count = 0
            attack_count = attack_count + 1 if value >= on else 0
            if attack_count >= attack:
                active, attack_count = True, 0
        else:
            attack_count = 0
            release_count = release_count + 1 if value <= off else 0
            if release_count >= release:
                active, release_count = False, 0
        states.append(active)
    return states


def k_of_n_detector(values, on=12000, off=6000, k=8, n=24,
                    attack=1, release=16, hangover=82):
    active = False
    history = deque([False] * n, maxlen=n)
    attack_count = release_count = hangover_count = 0
    states = []
    for value in values:
        history.append(value >= on)
        votes = sum(history)
        if not active:
            release_count = hangover_count = 0
            attack_count = attack_count + 1 if votes else 0
            if votes >= k and attack_count >= max(1, attack):
                active, attack_count = True, 0
        else:
            attack_count = 0
            if value > off:
                release_count = hangover_count = 0
            elif release_count < release:
                release_count += 1
                hangover_count = 0
            elif hangover_count < hangover:
                hangover_count += 1
            else:
                active = False
                release_count = hangover_count = 0
                history = deque([False] * n, maxlen=n)
        states.append(active)
    return states


def state_summary(states):
    transitions = sum(left != right for left, right in zip([False] + states, states))
    return {
        "samples": len(states),
        "transitions": transitions,
        "active_samples": sum(states),
        "active_fraction": (sum(states) / len(states)) if states else 0.0,
    }


def load_memh(path):
    values = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        word = raw.split("//", 1)[0].split("#", 1)[0].strip()
        if word:
            values.append(int(word, 16))
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("evidence/physical/retest_after_contact_fix"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "evidence/wearable_audio_autocalibration/"
            "existing_physical_dataset_audit.json"
        ),
    )
    args = parser.parse_args()

    json_files = sorted(args.root.rglob("*.json"))
    evidence = {
        "json_files_scanned": len(json_files),
        "explicit_acoustic_pass": 0,
        "explicit_acoustic_fail": 0,
        "energy_cycles_pass": 0,
        "energy_cycles_fail": 0,
        "fsm_transition_pairs_pass": 0,
        "fsm_transition_pairs_fail": 0,
        "reported_old_transition_counts": [],
        "reported_results": {},
    }
    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        acoustic = data.get("acoustic_capture_pass")
        if acoustic is True:
            evidence["explicit_acoustic_pass"] += 1
        elif acoustic is False:
            evidence["explicit_acoustic_fail"] += 1
        for cycle in data.get("cycles", []):
            if cycle.get("energy_separation_pass") is True:
                evidence["energy_cycles_pass"] += 1
            elif cycle.get("energy_separation_pass") is False:
                evidence["energy_cycles_fail"] += 1
            if cycle.get("fsm_transition_pair_pass") is True:
                evidence["fsm_transition_pairs_pass"] += 1
            elif cycle.get("fsm_transition_pair_pass") is False:
                evidence["fsm_transition_pairs_fail"] += 1
        for key in ("repeatability_result", "fsm_transition_repeatability_result",
                    "fsm_stability_result"):
            if key in data:
                evidence["reported_results"].setdefault(key, []).append({
                    "file": str(path), "value": data[key]
                })
        for key in ("sound_active_transition_count", "transitions_before"):
            if isinstance(data.get(key), int):
                evidence["reported_old_transition_counts"].append({
                    "file": str(path), "field": key, "value": data[key]
                })

    traces = []
    for path in sorted(args.root.rglob("*.memh")):
        values = load_memh(path)
        traces.append({
            "file": str(path),
            "old_consecutive_24_release_82": state_summary(old_detector(values)),
            "candidate_k8_of_n24_release16_hangover82": state_summary(
                k_of_n_detector(values)
            ),
            "accuracy_claim": "INCONCLUSIVE_NO_TRUSTWORTHY_LABELS",
        })

    result = {
        "purpose": "read-only audit of historical physical energy evidence",
        "parameters": {
            "old": {"on": 12000, "off": 6000, "attack": 24, "release": 82},
            "candidate": {
                "on": 12000, "off": 6000, "k": 8, "n": 24,
                "attack": 1, "release": 16, "hangover": 82,
            },
        },
        "evidence_summary": evidence,
        "memory_trace_replays": traces,
        "conclusion": (
            "Historical evidence proves real acoustic response and documents "
            "old-FSM chatter/misses, but does not provide sufficiently reliable "
            "labels to physically accept the candidate. The autonomous wearable "
            "playback gate must pass before thresholds are fitted."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
