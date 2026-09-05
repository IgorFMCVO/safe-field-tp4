#!/usr/bin/env python3
"""Convert the offline 16 kHz mono SAPI WAV into ESP32 dual-mono PCM."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import wave


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("header", type=Path)
    args = parser.parse_args()

    with wave.open(str(args.wav), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise SystemExit("WAV must be mono, signed PCM16, 16000 Hz")
        mono = source.readframes(source.getnframes())

    samples = struct.unpack(f"<{len(mono) // 2}h", mono)
    # ESP_I2S is configured as stereo like the first-party example. Duplicating
    # a mono source keeps both slots coherent without changing pitch or rate.
    stereo = bytearray()
    for sample in samples:
        stereo.extend(struct.pack("<hh", sample, sample))

    args.header.parent.mkdir(parents=True, exist_ok=True)
    with args.header.open("w", encoding="ascii", newline="\n") as target:
        target.write("#pragma once\n#include <stdint.h>\n\n")
        target.write("static const uint8_t kSafeFieldSpeechPcm[] PROGMEM = {\n")
        for offset in range(0, len(stereo), 16):
            row = ", ".join(f"0x{value:02X}" for value in stereo[offset:offset + 16])
            target.write(f"  {row},\n")
        target.write("};\n")
        target.write(f"static const uint32_t kSafeFieldSpeechPcmLength = {len(stereo)}u;\n")
        target.write(f"static const uint32_t kSafeFieldSpeechFrames = {len(samples)}u;\n")
    print(f"MONO_SAMPLES={len(samples)}")
    print(f"DURATION_SECONDS={len(samples) / 16000:.3f}")
    print(f"HEADER_BYTES={len(stereo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
