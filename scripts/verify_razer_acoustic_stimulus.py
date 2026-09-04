#!/usr/bin/env python3
"""Use the Razer microphone array as an independent witness of speaker output."""

from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tmp" / "sounddevice"))
import sounddevice as sd  # noqa: E402


EVIDENCE = PROJECT / "evidence" / "physical" / "retest_after_contact_fix"
SAMPLE_RATE = 48_000
FREQUENCY = 1_000.0
AMPLITUDE = 0.40


def rms(values: np.ndarray) -> float:
    return float(math.sqrt(np.mean(np.square(values.astype(np.float64)))))


def main() -> int:
    duration = 4.0
    frame_count = int(SAMPLE_RATE * duration)
    timeline = np.arange(frame_count) / SAMPLE_RATE
    enabled = (timeline >= 0.5) & (timeline < 3.5)
    output = np.zeros((frame_count, 2), dtype=np.float32)
    tone = (AMPLITUDE * np.sin(2 * np.pi * FREQUENCY * timeline)).astype(np.float32)
    output[:, 0] = np.where(enabled, tone, 0.0)
    output[:, 1] = output[:, 0]

    input_device, output_device = sd.default.device
    recording = sd.playrec(
        output,
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=(input_device, output_device),
        blocking=True,
    )[:, 0]

    silence = np.concatenate((recording[: int(0.4 * SAMPLE_RATE)], recording[int(3.6 * SAMPLE_RATE) :]))
    received = recording[int(0.8 * SAMPLE_RATE) : int(3.2 * SAMPLE_RATE)]
    centered = received - received.mean()
    spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(centered))))
    frequencies = np.fft.rfftfreq(len(centered), 1 / SAMPLE_RATE)
    spectrum[frequencies < 100] = 0
    peak_hz = float(frequencies[int(np.argmax(spectrum))])
    silence_rms = rms(silence)
    tone_rms = rms(received)
    result = {
        "kind": "independent Razer microphone-array witness",
        "input_device": int(input_device),
        "input_device_name": sd.query_devices(input_device)["name"],
        "output_device": int(output_device),
        "output_device_name": sd.query_devices(output_device)["name"],
        "sample_rate_hz": SAMPLE_RATE,
        "generated_frequency_hz": FREQUENCY,
        "generated_amplitude_fraction_full_scale": AMPLITUDE,
        "captured_peak_frequency_hz": peak_hz,
        "frequency_error_hz": peak_hz - FREQUENCY,
        "silence_rms": silence_rms,
        "tone_rms": tone_rms,
        "rms_ratio_tone_to_silence": tone_rms / silence_rms if silence_rms else None,
        "pass": abs(peak_hz - FREQUENCY) <= 10 and tone_rms >= silence_rms * 2,
    }

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    wav_path = EVIDENCE / "razer_mic_witness_1000hz.wav"
    pcm = np.clip(recording * 32767, -32768, 32767).astype("<i2")
    with wave.open(str(wav_path), "wb") as output_wav:
        output_wav.setnchannels(1)
        output_wav.setsampwidth(2)
        output_wav.setframerate(SAMPLE_RATE)
        output_wav.writeframes(pcm.tobytes())

    json_path = EVIDENCE / "razer_mic_witness_1000hz_analysis.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    figure, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    axes[0].plot(timeline, recording, linewidth=0.6)
    axes[0].set(title="Razer microphone-array witness — waveform", xlabel="tempo (s)", ylabel="amplitude")
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(frequencies, spectrum, linewidth=0.7)
    axes[1].set_xlim(0, 3000)
    axes[1].set(title=f"Razer witness spectrum — pico {peak_hz:.2f} Hz", xlabel="frequência (Hz)", ylabel="amplitude FFT")
    axes[1].grid(True, alpha=0.3)
    plot_path = EVIDENCE / "razer_mic_witness_1000hz.png"
    figure.savefig(plot_path, dpi=160)
    plt.close(figure)

    print(json.dumps(result, indent=2))
    print(f"WAV={wav_path}")
    print(f"ANALYSIS_JSON={json_path}")
    print(f"PLOT={plot_path}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
