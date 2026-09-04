#!/usr/bin/env python3
"""Play one moderate acoustic stimulus and collect four physical DEBUG6 GAO captures."""

from __future__ import annotations

import argparse
import datetime as dt
import math
import struct
import subprocess
import time
import wave
import winsound
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE = PROJECT / "evidence" / "physical" / "retest_after_contact_fix"
STIMULI = EVIDENCE / "stimuli"
GAO = Path(r"C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gao_sh.exe")
RAO = PROJECT / "build" / "debug6_retest_after_contact_fix" / "debug6_retest_after_contact_fix.rao"
DEFAULT_AMPLITUDE = 0.12
OUTPUT_SAMPLE_RATE = 48_000
CAPTURE_COUNT = 4


def timestamp() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def create_wav(path: Path, frequency: float, pulsed: bool, amplitude: float) -> None:
    duration_seconds = 8
    frame_count = OUTPUT_SAMPLE_RATE * duration_seconds
    samples = bytearray()
    for index in range(frame_count):
        enabled = not pulsed or ((index // (OUTPUT_SAMPLE_RATE // 4)) % 2 == 0)
        sample = 0 if not enabled else round(
            32767 * amplitude * math.sin(2 * math.pi * frequency * index / OUTPUT_SAMPLE_RATE)
        )
        samples.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(OUTPUT_SAMPLE_RATE)
        output.writeframes(samples)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stimulus",
        choices=("silence", "tone_500hz", "tone_1000hz", "tone_2000hz", "pulses_1000hz"),
    )
    parser.add_argument("--label", help="distinct evidence prefix; defaults to the stimulus name")
    parser.add_argument("--amplitude", type=float, default=DEFAULT_AMPLITUDE)
    args = parser.parse_args()
    if not 0.01 <= args.amplitude <= 0.5:
        parser.error("--amplitude must remain in the moderate 0.01..0.5 range")
    label = args.label or args.stimulus
    frequency = {
        "silence": 0.0,
        "tone_500hz": 500.0,
        "tone_1000hz": 1000.0,
        "tone_2000hz": 2000.0,
        "pulses_1000hz": 1000.0,
    }[args.stimulus]
    pulsed = args.stimulus == "pulses_1000hz"

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    STIMULI.mkdir(parents=True, exist_ok=True)
    log_path = EVIDENCE / f"debug6_{label}_capture.log"
    lines = [
        f"started_local={timestamp()}",
        "capture_kind=physical GAO/JTAG after contact repair",
        f"stimulus={args.stimulus}",
        f"evidence_label={label}",
        f"stimulus_frequency_hz={frequency}",
        f"wav_amplitude_fraction_full_scale={args.amplitude}",
        f"capture_count={CAPTURE_COUNT}",
        "samples_per_capture=1024 LEFT frames",
        f"rao={RAO}",
    ]

    wav_path: Path | None = None
    if frequency:
        wav_path = STIMULI / f"{label}.wav"
        create_wav(wav_path, frequency, pulsed, args.amplitude)
        lines.append(f"wav={wav_path}")
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
        time.sleep(0.5)
    else:
        winsound.PlaySound(None, 0)
        time.sleep(0.5)

    try:
        for capture_index in range(1, CAPTURE_COUNT + 1):
            prefix = EVIDENCE / f"debug6_{label}_capture{capture_index:02d}"
            command = [
                str(GAO), "-gao", str(RAO), "-out", str(prefix),
                "-device", "GW1NSR-4C", "-cable", "FT2CH", "-location", "0",
            ]
            lines.append(f"capture_{capture_index:02d}_start={timestamp()}")
            lines.append(f"capture_{capture_index:02d}_command=" + subprocess.list2cmdline(command))
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
            lines.append(result.stdout.rstrip())
            if result.stderr:
                lines.append("stderr=" + result.stderr.rstrip())
            lines.append(f"capture_{capture_index:02d}_exit_code={result.returncode}")
            core0 = Path(f"{prefix}_core0_window0.csv")
            core1 = Path(f"{prefix}_core1_window0.csv")
            if result.returncode or not core0.is_file() or not core1.is_file():
                raise RuntimeError(f"GAO capture {capture_index} did not produce both CSVs")
            lines.append(f"capture_{capture_index:02d}_finish={timestamp()}")
            time.sleep(0.25)
    finally:
        winsound.PlaySound(None, 0)
        lines.append(f"finished_local={timestamp()}")
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"EVIDENCE_LOG={log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
