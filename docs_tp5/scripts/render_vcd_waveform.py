#!/usr/bin/env python3
"""Render a compact PNG from the coexistence VCD for the TP5 video."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
VCD = ROOT / "docs_tp5/evidence/simulation/waveforms/tb_tp5_raw24_coexist.vcd"
OUT = ROOT / "docs_tp5/video_demo/03_WAVEFORM_RAW24_COMMAND.png"
W, H = 1800, 900


def font(size, bold=False):
    path = "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"
    return ImageFont.truetype(path, size)


def parse():
    wanted = {"raw_tx_active", "command_valid", "response_pending", "response_launch", "telemetry_busy"}
    scopes, codes, changes = [], {}, {}
    now = 0; definitions = True
    with VCD.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith("$scope"):
                scopes.append(line.split()[2])
            elif line.startswith("$upscope"):
                if scopes: scopes.pop()
            elif line.startswith("$var"):
                parts = line.split(); code, name = parts[3], parts[4]
                if name in wanted and scopes[-1:] == ["dut"]:
                    codes[code] = name; changes[name] = []
            elif line.startswith("$enddefinitions"):
                definitions = False
            elif not definitions and line.startswith("#"):
                now = int(line[1:])
            elif not definitions and line and line[0] in "01xz" and line[1:] in codes:
                changes[codes[line[1:]]].append((now, 1 if line[0] == "1" else 0))
    return changes


def main():
    changes = parse()
    starts = [t for t, v in changes.get("raw_tx_active", []) if v]
    ends = [t for points in changes.values() for t, _ in points]
    t0 = min(starts) if starts else 0; t1 = max(ends) if ends else t0 + 1
    pad = max(1, (t1 - t0) // 50); t0 -= pad; t1 += pad
    img = Image.new("RGB", (W, H), "#071321"); d = ImageDraw.Draw(img)
    d.text((70, 35), "SAFE-FIELD TP5 · COEXISTÊNCIA RAW24 + COMANDO", font=font(36, True), fill="#F4F8FC")
    d.text((70, 86), "Waveform simulada auto-verificável · sem colisão no UART TX", font=font(22), fill="#8EABC7")
    left, right, top = 390, W - 70, 180
    tracks = ["raw_tx_active", "command_valid", "response_pending", "response_launch", "telemetry_busy"]
    colors = ["#2DD4BF", "#F7C948", "#60A5FA", "#F472B6", "#A78BFA"]
    def sx(t): return left + int((t - t0) * (right - left) / max(1, t1 - t0))
    for idx, (name, color) in enumerate(zip(tracks, colors)):
        cy = top + idx * 120
        d.text((70, cy + 20), name, font=font(23, True), fill=color)
        d.line((left, cy + 70, right, cy + 70), fill="#294057", width=2)
        points = changes.get(name, []); state = 0; last_t = t0
        for t, value in points:
            if t < t0: state = value; continue
            if t > t1: break
            y = cy + (18 if state else 70)
            d.line((sx(last_t), y, sx(t), y), fill=color, width=5)
            d.line((sx(t), cy + (18 if state else 70), sx(t), cy + (18 if value else 70)), fill=color, width=5)
            last_t, state = t, value
        d.line((sx(last_t), cy + (18 if state else 70), right, cy + (18 if state else 70)), fill=color, width=5)
    d.line((left, top - 25, left, top + 5 * 120 - 20), fill="#60778F", width=2)
    d.line((right, top - 25, right, top + 5 * 120 - 20), fill="#60778F", width=2)
    d.text((left, H - 78), f"janela {t0/1e6:.3f}–{t1/1e6:.3f} µs (VCD timescale 1 ps)", font=font(18), fill="#8EABC7")
    d.text((W - 590, H - 78), "Fonte: tb_tp5_raw24_coexist.vcd · TEST_RESULT: PASS", font=font(18), fill="#8EABC7")
    OUT.parent.mkdir(parents=True, exist_ok=True); img.save(OUT, quality=95)
    print(OUT)


if __name__ == "__main__": main()
