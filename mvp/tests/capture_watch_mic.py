from __future__ import annotations

import argparse
import json
import math
import time
import wave
from pathlib import Path

import numpy as np
import serial


def read_exact(port: serial.Serial, size: int) -> bytes:
    result = bytearray()
    deadline = time.monotonic() + 30
    while len(result) < size:
        block = port.read(size - len(result))
        if block:
            result.extend(block)
        elif time.monotonic() > deadline:
            raise TimeoutError(f"PCM timeout: {len(result)}/{size} bytes")
    return bytes(result)


def stats(values: np.ndarray) -> dict[str, float | int]:
    data = values.astype(np.float64)
    dc = float(np.mean(data))
    ac = data - dc
    return {
        "minimum": int(np.min(values)),
        "maximum": int(np.max(values)),
        "dc": dc,
        "ac_rms": float(math.sqrt(np.mean(ac * ac))),
        "peak": int(np.max(np.abs(data))),
        "clipping": int(np.count_nonzero(np.abs(data) >= 32767)),
        "unique": int(np.unique(values).size),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    with serial.Serial(args.port, 921600, timeout=1, write_timeout=2) as port:
        time.sleep(0.8)
        port.reset_input_buffer()
        port.write(b"STATUS\n")
        status = port.readline().decode("ascii", "replace").strip()
        if "audio=READY" not in status:
            raise RuntimeError(f"watch microphone unavailable: {status!r}")
        port.write(b"CAPTURE\n")
        header = ""
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            line = port.readline().decode("ascii", "replace").strip()
            if line.startswith("PCM_BEGIN "):
                header = line
                break
            if line.startswith("ERR "):
                raise RuntimeError(line)
        if not header:
            raise TimeoutError("PCM_BEGIN not received")
        fields = header.split()
        rate, channels, byte_count, elapsed_ms = map(int, fields[1:5])
        firmware_rms = [float(fields[5]), float(fields[6])]
        raw = read_exact(port, byte_count)
        trailer = port.readline()  # leading newline after binary payload
        if not trailer.strip():
            trailer = port.readline()
        trailer_text = trailer.decode("ascii", "replace").strip()
        if trailer_text != f"PCM_END {byte_count}":
            raise RuntimeError(f"bad trailer: {trailer_text!r}")

    interleaved = np.frombuffer(raw, dtype="<i2")
    frames = interleaved.reshape(-1, channels)
    channel_stats = [stats(frames[:, index]) for index in range(channels)]
    selected = int(np.argmax([item["ac_rms"] for item in channel_stats]))
    mono = frames[:, selected].copy()

    with wave.open(str(output / "watch_mic_stereo.wav"), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(raw)
    with wave.open(str(output / "watch_mic_mono.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(mono.astype("<i2").tobytes())

    report = {
        "status": status,
        "header": header,
        "trailer": trailer_text,
        "sample_rate_hz": rate,
        "channels": channels,
        "frames": int(frames.shape[0]),
        "duration_s": frames.shape[0] / rate,
        "capture_elapsed_ms": elapsed_ms,
        "firmware_ac_rms": firmware_rms,
        "channel_stats": channel_stats,
        "selected_channel": selected,
    }
    (output / "watch_mic_capture.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

