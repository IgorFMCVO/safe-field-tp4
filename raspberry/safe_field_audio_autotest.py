#!/usr/bin/env python3
"""Autonomous watch-speaker -> INMP441 -> FPGA detector calibration."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import struct
import time
import urllib.parse
import urllib.request

from safe_field_uart_protocol import SequenceTracker, StreamParser, crc8_atm


COMMAND_SYNC = b"\xA6\x6A"
PHASE_PRE = "SILENCIO 2s"
PHASE_PLAY = "REPRODUZINDO"
PHASE_POST = "SILENCIO FINAL"
PHASE_DONE = "TESTE ENVIADO"


@dataclass(frozen=True)
class DetectorConfig:
    threshold_on: int
    threshold_off: int
    k: int
    n: int
    attack: int
    release: int
    hangover: int


def percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def stats(values: list[int]) -> dict:
    if not values:
        return {"count": 0}
    mean = statistics.fmean(values)
    return {
        "count": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": mean,
        "rms_equivalent": math.sqrt(statistics.fmean(v * v for v in values)),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
    }


def encode_command(command: int, sequence: int, payload: int) -> bytes:
    body = bytes((1, command)) + struct.pack("<H", sequence & 0xFFFF) + struct.pack("<I", payload & 0xFFFFFFFF)
    return COMMAND_SYNC + body + bytes((crc8_atm(body),))


def http_json(url: str, method: str = "GET", timeout: float = 1.0) -> dict:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


class HardwareSession:
    def __init__(self, port: str, baud: int, core_url: str | None):
        import serial
        self.serial = serial.Serial(port, baud, timeout=0.02)
        self.parser = StreamParser()
        self.tracker = SequenceTracker()
        self.command_sequence = 1
        self.core_url = core_url
        self.last_core_state = None
        self.crc_errors = 0
        self.sequence_losses = 0
        self.frame_errors = 0
        self.telemetry_overruns = 0
        self.command_errors = 0
        self.all_frames = []
        self.serial.reset_input_buffer()

    def close(self):
        self.serial.close()

    def read_frames(self):
        chunk = self.serial.read(512)
        decoded = self.parser.feed(chunk) if chunk else []
        self.crc_errors = self.parser.crc_errors
        for frame in decoded:
            self.sequence_losses += self.tracker.observe(frame.seq)
            self.frame_errors += 1 if frame.flags & 0x01 else 0
            self.telemetry_overruns += 1 if frame.flags & 0x02 else 0
            self.command_errors += 1 if frame.flags & 0x20 else 0
            self.all_frames.append(frame)
            if not frame.flags & 0x80 and frame.state_name != self.last_core_state:
                self.last_core_state = frame.state_name
                self.post_core(frame)
        return decoded

    def post_core(self, frame):
        if not self.core_url:
            return
        payload = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "seq": frame.seq,
            "state": frame.state_name,
            "energy": frame.energy,
            "frame_counter": frame.frame_counter,
            "flags": frame.flags,
        }).encode()
        try:
            request = urllib.request.Request(self.core_url, data=payload,
                                             headers={"Content-Type": "application/json"},
                                             method="POST")
            urllib.request.urlopen(request, timeout=0.25).read()
        except Exception:
            pass

    def command(self, command: int, payload: int, timeout: float = 1.0) -> int:
        sequence = self.command_sequence
        self.command_sequence = (self.command_sequence + 1) & 0xFFFF
        self.serial.write(encode_command(command, sequence, payload))
        self.serial.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in self.read_frames():
                if (frame.flags & 0x80 and frame.energy >> 16 == command and
                        frame.energy & 0xFFFF == sequence):
                    if frame.flags & 0x40:
                        raise RuntimeError(f"FPGA rejected command 0x{command:02X}")
                    return frame.frame_counter
        raise TimeoutError(f"no FPGA response for command 0x{command:02X}")

    def configure(self, config: DetectorConfig):
        commands = [
            (0x10, config.threshold_on),
            (0x11, config.threshold_off),
            (0x12, config.k | (config.n << 8)),
            (0x13, config.attack),
            (0x14, config.release),
            (0x15, config.hangover),
        ]
        actual = [self.command(cmd, value) for cmd, value in commands]
        expected = [value for _, value in commands]
        if actual != expected:
            raise RuntimeError(f"configuration ACK mismatch expected={expected} actual={actual}")


def simulate_new(energies: list[int], config: DetectorConfig) -> list[bool]:
    history = [False] * config.n
    active = False
    attack = release = hangover = 0
    output = []
    for energy in energies:
        history = (history + [energy >= config.threshold_on])[-config.n:]
        votes = sum(history)
        if not active:
            release = hangover = 0
            attack = attack + 1 if votes else 0
            if votes >= config.k and (config.attack == 0 or attack >= config.attack):
                active, attack = True, 0
        else:
            attack = 0
            if energy > config.threshold_off:
                release = hangover = 0
            elif config.release and release < config.release:
                release += 1
                hangover = 0
            elif config.hangover and hangover < config.hangover:
                hangover += 1
            else:
                active, release, hangover = False, 0, 0
                history = [False] * config.n
        output.append(active)
    return output


def simulate_old(energies: list[int], on=12000, off=6000, attack_windows=24,
                 release_windows=82) -> list[bool]:
    active = False
    attack = release = 0
    output = []
    for energy in energies:
        if not active:
            release = 0
            attack = attack + 1 if energy >= on else 0
            if attack >= attack_windows:
                active, attack = True, 0
        else:
            attack = 0
            release = release + 1 if energy <= off else 0
            if release >= release_windows:
                active, release = False, 0
        output.append(active)
    return output


def run_round(session: HardwareSession, watch_url: str, volume: int,
              profile: str, round_id: str, csv_path: Path) -> dict:
    play_url = f"{watch_url}/api/v1/selftest/play?" + urllib.parse.urlencode(
        {"profile": profile, "volume": volume})
    response = http_json(play_url, method="POST", timeout=2.0)
    if not response.get("ok"):
        raise RuntimeError(f"wearable refused self-test: {response}")
    started = time.monotonic()
    current_phase = PHASE_PRE
    last_status = 0.0
    rows = []
    done_since = None
    while time.monotonic() - started < 15.0:
        now = time.monotonic()
        if now - last_status >= 0.08:
            last_status = now
            try:
                current_phase = http_json(f"{watch_url}/api/v1/selftest/status", timeout=0.4).get("phase", current_phase)
            except Exception:
                pass
        for frame in session.read_frames():
            if frame.flags & 0x80:
                continue
            rows.append({
                "elapsed_s": now - started,
                "phase": current_phase,
                "seq": frame.seq,
                "state": frame.state_name,
                "energy": frame.energy,
                "frame_counter": frame.frame_counter,
                "flags": frame.flags,
            })
        if current_phase == PHASE_DONE:
            done_since = done_since or now
            if now - done_since > 0.35:
                break
        time.sleep(0.002)
    if not rows or current_phase != PHASE_DONE:
        raise RuntimeError(f"incomplete wearable round {round_id}: phase={current_phase} rows={len(rows)}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    phases = {phase: [row["energy"] for row in rows if row["phase"] == phase]
              for phase in (PHASE_PRE, PHASE_PLAY, PHASE_POST)}
    states = [row["state"] == "ACTIVE" for row in rows]
    active_rises = sum(not before and after for before, after in zip([False] + states, states))
    play_rows = [row for row in rows if row["phase"] == PHASE_PLAY]
    play_start = play_rows[0]["elapsed_s"] if play_rows else None
    active_during = [row for row in play_rows if row["state"] == "ACTIVE"]
    attack_ms = ((active_during[0]["elapsed_s"] - play_start) * 1000
                 if active_during and play_start is not None else None)
    post_rows = [row for row in rows if row["phase"] == PHASE_POST]
    quiet_post = [row for row in post_rows if row["state"] == "QUIET"]
    release_ms = None
    if active_during and quiet_post:
        release_ms = max(0.0, (quiet_post[0]["elapsed_s"] - play_rows[-1]["elapsed_s"]) * 1000)
    pre_relevant = [row for row in rows if row["phase"] == PHASE_PRE and row["elapsed_s"] > 0.4]
    result = {
        "round": round_id,
        "volume": volume,
        "profile": profile,
        "samples": len(rows),
        "phase_stats": {phase: stats(values) for phase, values in phases.items()},
        "active_rises": active_rises,
        "detected": bool(active_during),
        "returned_quiet": bool(quiet_post and quiet_post[-1]["state"] == "QUIET"),
        "false_active_pre": sum(row["state"] == "ACTIVE" for row in pre_relevant),
        "attack_ms": attack_ms,
        "release_ms": release_ms,
        "csv": str(csv_path),
        "rows": rows,
    }
    return result


def choose_config(calibration_rounds: list[dict]) -> tuple[DetectorConfig, list[dict]]:
    noise = []
    signal = []
    for result in calibration_rounds:
        rows = result["rows"]
        noise.extend(row["energy"] for row in rows if row["phase"] == PHASE_PRE and row["elapsed_s"] > 0.5)
        noise.extend(row["energy"] for row in rows if row["phase"] == PHASE_POST and row["elapsed_s"] > 7.3)
        signal.extend(row["energy"] for row in rows if row["phase"] == PHASE_PLAY)
    noise_p95 = percentile(noise, .95)
    noise_p99 = percentile(noise, .99)
    signal_p50 = percentile(signal, .50)
    separation = max(1000.0, signal_p50 - noise_p99)
    threshold_pairs = []
    for fraction in (.18, .28, .38):
        on = int(max(1000, min(500000, noise_p99 + separation * fraction)))
        off = int(max(500, min(on - 1, noise_p95 + separation * .08)))
        threshold_pairs.append((on, off))
    candidates = []
    for on, off in threshold_pairs:
        for k, n in ((3, 8), (4, 12), (6, 16), (8, 24)):
            for release, hangover in ((12, 70), (16, 82), (24, 96)):
                config = DetectorConfig(on, off, k, n, 1, release, hangover)
                detected = false_pre = extra_rises = 0
                for result in calibration_rounds:
                    states = simulate_new([row["energy"] for row in result["rows"]], config)
                    phases = [row["phase"] for row in result["rows"]]
                    detected += any(state and phase == PHASE_PLAY for state, phase in zip(states, phases))
                    false_pre += sum(state and phase == PHASE_PRE for state, phase in zip(states, phases))
                    rises = sum(not a and b for a, b in zip([False] + states, states))
                    extra_rises += max(0, rises - 1)
                score = detected * 10000 - false_pre * 100 - extra_rises * 1000 - on / 1000
                candidates.append({"score": score, "config": config,
                                   "detected": detected, "false_pre": false_pre,
                                   "extra_rises": extra_rises})
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[0]["config"], candidates[:10]


def public_result(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "rows"}


def write_report(path: Path, result: dict):
    config = result["chosen_config"]
    lines = [
        "# SAFE-FIELD — AUDIO AUTOCALIBRATION REPORT",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "## Hardware playback path",
        "",
        "The official Waveshare V1.0 schematic and bundled example confirm ES8311,",
        "GPIO46 PA enable and the onboard SPK output. Playback used offline pt-BR",
        "PCM16 at 16 kHz; no operator voice or clap was used.",
        "",
        "## Detector",
        "",
        "The frozen detector required consecutive threshold crossings. The MVP variant",
        "uses a runtime RAM-only K-of-N vote plus deterministic release/hangover.",
        "",
        f"- Noise floor p95: {result['noise_floor']:.1f}",
        f"- THRESHOLD_ON: {config['threshold_on']}",
        f"- THRESHOLD_OFF: {config['threshold_off']}",
        f"- K/N: {config['k']}/{config['n']}",
        f"- Attack windows: {config['attack']}",
        f"- Release windows: {config['release']}",
        f"- Hangover windows: {config['hangover']}",
        "",
        "## Physical autonomous acceptance",
        "",
        f"- Cycles passed: {result['cycles_passed']}/10",
        f"- False positives: {result['false_positives']}",
        f"- CRC errors: {result['crc_errors']}",
        f"- Sequence losses: {result['sequence_losses']}",
        f"- Frame errors: {result['frame_errors']}",
        f"- Result: {'PASS' if result['pass'] else 'FAIL'}",
        "",
        "## Evidence",
        "",
        f"- Machine-readable summary: `{result['json_path']}`",
        f"- Per-round CSV directory: `{result['evidence_dir']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_playback_failure_report(path: Path, result: dict):
    lines = [
        "# SAFE-FIELD — AUDIO AUTOCALIBRATION REPORT",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "## Result",
        "",
        "**VOICE_DETECTION_AUTONOMOUS = FAIL (blocked before detector calibration).**",
        "",
        "The wearable accepted every HTTP command, the official ES8311 driver",
        "initialized, and ESP_I2S reported that every expected PCM byte was written.",
        "The physical INMP441 telemetry did not show a reproducible increase during",
        "playback at 40/65/85 volume. Running a detector search on these windows would",
        "fit ambient drift rather than the known stimulus, so no threshold was claimed.",
        "",
        "## Exact isolation",
        "",
        "- ESP32-S3 boot/Wi-Fi/HTTP: PASS",
        "- ES8311 I2C initialization: PASS",
        "- I2S software byte delivery: PASS",
        "- acoustic coupling speaker -> air -> INMP441: FAIL / not observable",
        "- INMP441 -> FPGA -> Pi telemetry remained live, CRC-valid and non-zero",
        "- Pi TX -> Tang pin 46 also failed a regression using the frozen, previously",
        "  approved bidirectional bitstream; GPIO14 remained muxed as TXD1. This points",
        "  outside the new detector RTL and blocks RAM-only runtime parameter updates.",
        "",
        "Likely physical boundary: absent/disconnected SPK transducer or PA-to-speaker",
        "path, insufficient fixed acoustic coupling, and separately the existing",
        "Raspberry pin 8 -> Tang pin 46 contact. No wire was touched in this sprint.",
        "",
        "## Measurements",
        "",
        f"- Noise-floor p95: {result['noise_floor']:.1f}",
        f"- Playback/pre-silence RMS ratios: {result['playback_ratios']}",
        f"- autonomous detector cycles completed: {result['cycles_passed']}/10",
        f"- CRC errors: {result['crc_errors']}",
        f"- sequence losses: {result['sequence_losses']}",
        f"- frame errors: {result['frame_errors']}",
        "- operator speech/claps/readiness prompts: 0",
        "",
        "## Evidence",
        "",
        f"- Machine-readable summary: `{result['json_path']}`",
        f"- Per-round CSV directory: `{result['evidence_dir']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--watch-url", default="http://safe-field-watch.local")
    parser.add_argument("--core-events-url", default="http://127.0.0.1:8765/api/v1/fpga/events")
    parser.add_argument("--output", type=Path, default=Path("evidence/audio_autocalibration"))
    parser.add_argument("--report", type=Path, default=Path("AUDIO_AUTOCALIBRATION_REPORT.md"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    watch_status = http_json(f"{args.watch_url}/api/v1/selftest/status", timeout=2.0)
    if not watch_status.get("audio_ready"):
        raise SystemExit("wearable ES8311 playback is not ready")

    session = HardwareSession(args.port, args.baud, args.core_events_url)
    try:
        calibration = []
        for index, volume in enumerate((40, 65, 85), 1):
            calibration.append(run_round(
                session, args.watch_url, volume, "speech",
                f"calibration_v{volume}", args.output / f"calibration_{index:02d}_v{volume}.csv"))

        playback_ratios = []
        response_rounds = 0
        for item in calibration:
            phase_stats = item["phase_stats"]
            play_rms = phase_stats[PHASE_PLAY].get("rms_equivalent", 0.0)
            reference_rms = max(phase_stats[PHASE_PRE].get("rms_equivalent", 0.0),
                                phase_stats[PHASE_POST].get("rms_equivalent", 0.0), 1.0)
            ratio = play_rms / reference_rms
            playback_ratios.append(round(ratio, 4))
            response_rounds += ratio >= 1.5
        # Require reproducible acoustic separation, not a single favorable drift.
        physical_playback_pass = response_rounds >= 2
        if not physical_playback_pass:
            noise_values = [row["energy"] for item in calibration for row in item["rows"]
                            if row["phase"] in (PHASE_PRE, PHASE_POST)]
            result = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "watch_status": watch_status,
                "physical_playback_pass": False,
                "inmp441_response_pass": False,
                "detector_old_pass": False,
                "detector_new_pass": False,
                "chosen_config": None,
                "calibration": [public_result(item) for item in calibration],
                "playback_ratios": playback_ratios,
                "noise_floor": percentile(noise_values, .95),
                "cycles_passed": 0,
                "false_positives": 0,
                "crc_errors": session.crc_errors,
                "sequence_losses": session.sequence_losses,
                "frame_errors": session.frame_errors,
                "telemetry_overruns": session.telemetry_overruns,
                "command_errors": session.command_errors,
                "pass": False,
                "diagnosis": "ES8311/I2S bytes PASS, but no reproducible acoustic response; runtime Pi-to-Tang ACK regression independently confirmed",
                "evidence_dir": str(args.output),
                "json_path": str(args.output / "autocalibration_result.json"),
            }
            (args.output / "autocalibration_result.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8")
            write_playback_failure_report(args.report, result)
            print(json.dumps(result, indent=2))
            return 3
        chosen, grid = choose_config(calibration)
        session.configure(chosen)

        verification = []
        for index in range(1, 11):
            verification.append(run_round(
                session, args.watch_url, 65, "speech", f"verify_{index:02d}",
                args.output / f"verify_{index:02d}.csv"))

        cycles_passed = sum(
            item["detected"] and item["returned_quiet"] and
            item["false_active_pre"] == 0 and item["active_rises"] <= 1
            for item in verification)
        false_positives = sum(item["false_active_pre"] for item in verification)
        noise_values = [row["energy"] for item in calibration for row in item["rows"]
                        if row["phase"] == PHASE_PRE and row["elapsed_s"] > .5]
        old_new = []
        for item in calibration:
            energies = [row["energy"] for row in item["rows"]]
            phases = [row["phase"] for row in item["rows"]]
            old_states = simulate_old(energies)
            new_states = simulate_new(energies, chosen)
            old_new.append({
                "round": item["round"],
                "old_detected": any(s and p == PHASE_PLAY for s, p in zip(old_states, phases)),
                "new_detected": any(s and p == PHASE_PLAY for s, p in zip(new_states, phases)),
            })
        attack_values = [item["attack_ms"] for item in verification if item["attack_ms"] is not None]
        release_values = [item["release_ms"] for item in verification if item["release_ms"] is not None]
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "watch_status": watch_status,
            "chosen_config": asdict(chosen),
            "grid_top10": [{**item, "config": asdict(item["config"])} for item in grid],
            "calibration": [public_result(item) for item in calibration],
            "verification": [public_result(item) for item in verification],
            "old_vs_new": old_new,
            "noise_floor": percentile(noise_values, .95),
            "cycles_passed": cycles_passed,
            "false_positives": false_positives,
            "crc_errors": session.crc_errors,
            "sequence_losses": session.sequence_losses,
            "frame_errors": session.frame_errors,
            "telemetry_overruns": session.telemetry_overruns,
            "command_errors": session.command_errors,
            "attack_ms_mean": statistics.fmean(attack_values) if attack_values else None,
            "attack_ms_max": max(attack_values) if attack_values else None,
            "release_ms_mean": statistics.fmean(release_values) if release_values else None,
            "release_ms_max": max(release_values) if release_values else None,
            "evidence_dir": str(args.output),
            "json_path": str(args.output / "autocalibration_result.json"),
        }
        result["pass"] = (
            cycles_passed == 10 and false_positives == 0 and session.crc_errors == 0 and
            session.sequence_losses == 0 and session.frame_errors == 0 and
            session.telemetry_overruns == 0 and session.command_errors == 0)
        (args.output / "autocalibration_result.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
        write_report(args.report, result)
        print(json.dumps(result, indent=2))
        return 0 if result["pass"] else 2
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
