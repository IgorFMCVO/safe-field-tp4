#!/usr/bin/env python3
"""Generate concise, evidence-backed SAFE-FIELD TP4 video demo screens."""

from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs_tp4" / "video_demo"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#102A43"
BLUE = "#247BA0"
GREEN = "#20834A"
TEAL = "#2A9D8F"
AMBER = "#C27600"
LIGHT = "#F4F8FB"
TEXT = "#23303D"
MUTED = "#5C6B78"


def new_slide(title: str):
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor="white")
    fig.text(0.055, 0.93, title, fontsize=27, fontweight="bold", color=NAVY)
    fig.text(0.055, 0.895, "SAFE-FIELD TP4 | Igor de Freitas Monteiro", fontsize=11, color=MUTED)
    return fig


def save(fig, name: str):
    fig.savefig(OUT / name, dpi=120, facecolor="white", bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)


def architecture():
    fig = new_slide("Arquitetura validada ponta a ponta")
    ax = fig.add_axes([0.055, 0.13, 0.89, 0.70])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    nodes = [
        ("INMP441", "ADC + I2S"),
        ("Tang Nano 4K", "I2S RX"),
        ("DSP", "sample²"),
        ("BSRAM", "256 x 32"),
        ("FSM", "QUIET/ACTIVE"),
        ("UART + CRC", "eventos"),
        ("Raspberry Pi 4", "ARM64 + CORE"),
    ]
    box_w, gap, y, h = 0.118, 0.021, 0.58, 0.20
    x0 = 0.012
    for i, (title, subtitle) in enumerate(nodes):
        x = x0 + i * (box_w + gap)
        color = GREEN if title in {"DSP", "BSRAM", "FSM"} else BLUE
        patch = FancyBboxPatch(
            (x, y), box_w, h,
            boxstyle="round,pad=0.012,rounding_size=0.016",
            linewidth=2, edgecolor=color, facecolor=LIGHT,
        )
        ax.add_patch(patch)
        ax.text(x + box_w / 2, y + 0.125, title, ha="center", va="center", fontsize=12, weight="bold", color=NAVY)
        ax.text(x + box_w / 2, y + 0.065, subtitle, ha="center", va="center", fontsize=10, color=MUTED)
        if i < len(nodes) - 1:
            ax.add_patch(FancyArrowPatch(
                (x + box_w + 0.002, y + h / 2),
                (x + box_w + gap - 0.003, y + h / 2),
                arrowstyle="->", mutation_scale=16, linewidth=1.8, color=NAVY,
            ))

    ax.text(0.50, 0.46, "UART bidirecional fisicamente validada", ha="center", fontsize=17, weight="bold", color=NAVY)
    left = FancyBboxPatch((0.12, 0.22), 0.31, 0.14, boxstyle="round,pad=0.012", linewidth=2, edgecolor=AMBER, facecolor="#FFF6DE")
    right = FancyBboxPatch((0.57, 0.22), 0.31, 0.14, boxstyle="round,pad=0.012", linewidth=2, edgecolor=GREEN, facecolor="#EAF7EF")
    ax.add_patch(left)
    ax.add_patch(right)
    ax.text(0.275, 0.305, "Pi GPIO14/TXD -> Tang pin 46", ha="center", fontsize=14, weight="bold", color=NAVY)
    ax.text(0.275, 0.255, "3/3 comandos | CRC=0 | perdas=0", ha="center", fontsize=11, color=TEXT)
    ax.text(0.725, 0.305, "Tang pin 39 -> Pi GPIO15/RXD", ha="center", fontsize=14, weight="bold", color=NAVY)
    ax.text(0.725, 0.255, "3.264 mensagens | perdas=0", ha="center", fontsize=11, color=TEXT)
    ax.add_patch(FancyArrowPatch((0.43, 0.29), (0.57, 0.29), arrowstyle="<->", mutation_scale=18, linewidth=2.2, color=TEAL))
    ax.text(0.5, 0.08, "INMP441 -> FPGA -> processamento determinístico -> Raspberry", ha="center", fontsize=16, color=GREEN, weight="bold")
    save(fig, "01_ARQUITETURA.png")


def verilog_resources():
    fig = new_slide("Verilog: unidade DSP e BSRAM funcional")
    ax = fig.add_axes([0.055, 0.10, 0.89, 0.75])
    ax.axis("off")
    dsp = '''safe_field_audio_energy_dsp
/* synthesis syn_dspstyle = "dsp" */
reg signed [15:0] sample_q;

sample_q <= sample_signed[23:8];
sample_power <= $signed(sample_q)
              * $signed(sample_q);'''
    bram = '''safe_field_energy_bram
/* synthesis syn_ramstyle = "block_ram" */
reg [31:0] memory [0:255];
reg [39:0] window_sum;

memory[write_address] <= power_value;
window_average <= (window_sum + power_value) >> 8;'''
    for x, title, code, color in [
        (0.01, "DSP signed square", dsp, GREEN),
        (0.51, "Buffer e média", bram, BLUE),
    ]:
        ax.add_patch(FancyBboxPatch((x, 0.28), 0.47, 0.62, boxstyle="round,pad=0.014", linewidth=2, edgecolor=color, facecolor=LIGHT))
        ax.text(x + 0.02, 0.84, title, fontsize=18, weight="bold", color=color, va="top")
        ax.text(x + 0.025, 0.76, code, fontsize=13.5, family="DejaVu Sans Mono", color=TEXT, va="top", linespacing=1.5)
    ax.add_patch(FancyBboxPatch((0.12, 0.04), 0.76, 0.15, boxstyle="round,pad=0.012", linewidth=2.5, edgecolor=GREEN, facecolor="#EAF7EF"))
    ax.text(0.50, 0.135, "Relatório Gowin P&R", ha="center", fontsize=14, color=MUTED)
    ax.text(0.50, 0.075, "MULT18X18 = 1    |    SDPB = 1    |    40/40 checks PASS", ha="center", fontsize=20, weight="bold", color=GREEN)
    save(fig, "02_VERILOG_BRAM_DSP.png")


def arm64_neon():
    fig = new_slide("ARM64 Assembly e NEON executados no Raspberry Pi 4")
    ax = fig.add_axes([0.055, 0.10, 0.89, 0.75])
    ax.axis("off")
    code = '''sf_add128:          adds x5, x0, x2
                    adc  x6, x1, x3
sf_i64_to_double:   scvtf d0, x0
sf_protocol_mix:    and / lsr / eor / ror

sf_energy_neon:     smull  v1.4s, v0.4h, v0.4h
                    smull2 v2.4s, v0.8h, v0.8h
                    uadalp v4.2d, v1.4s

sf_scale_neon:      fmul v1.4s, v1.4s, v3.4s'''
    ax.add_patch(FancyBboxPatch((0.01, 0.08), 0.60, 0.82, boxstyle="round,pad=0.015", linewidth=2, edgecolor=BLUE, facecolor=LIGHT))
    ax.text(0.035, 0.84, code, fontsize=15, family="DejaVu Sans Mono", color=TEXT, va="top", linespacing=1.55)
    checks = [
        "ADDS/ADC 128-bit: PASS",
        "SCVTF integer->double: PASS",
        "LUT + masks/shifts/ROR: PASS",
        "NEON INT: resultado exato",
        "NEON FLOAT: erro máximo 0",
        "objdump e logs preservados",
    ]
    ax.add_patch(FancyBboxPatch((0.65, 0.08), 0.34, 0.82, boxstyle="round,pad=0.015", linewidth=2, edgecolor=GREEN, facecolor="#EAF7EF"))
    ax.text(0.82, 0.83, "Execução real", ha="center", fontsize=20, weight="bold", color=GREEN)
    for i, check in enumerate(checks):
        ax.text(0.69, 0.72 - i * 0.105, "✓  " + check, fontsize=14, color=TEXT, va="center")
    save(fig, "04_ARM64_NEON.png")


def benchmark():
    fig = new_slide("Benchmark NEON medido no Raspberry Pi 4")
    ax = fig.add_axes([0.10, 0.15, 0.82, 0.68])
    repeats = ["50", "200", "800"]
    neon_int = [3.243166, 9.566309, 3.273697]
    neon_float = [2.052943, 1.161292, 1.126641]
    x = range(len(repeats))
    width = 0.34
    b1 = ax.bar([v - width / 2 for v in x], neon_int, width, label="NEON inteiro (8 lanes)", color=GREEN)
    b2 = ax.bar([v + width / 2 for v in x], neon_float, width, label="NEON float (4 lanes)", color=BLUE)
    ax.axhline(1.0, color=MUTED, linewidth=1.3, linestyle="--")
    ax.set_xticks(list(x), repeats)
    ax.set_xlabel("Repetições do benchmark", fontsize=13)
    ax.set_ylabel("Speedup vs. escalar (x)", fontsize=13)
    ax.set_ylim(0, 10.6)
    ax.grid(axis="y", alpha=0.22)
    ax.legend(frameon=False, fontsize=12, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    for bars in (b1, b2):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.14, f"{bar.get_height():.3f}x", ha="center", va="bottom", fontsize=11, weight="bold", color=TEXT)
    fig.text(0.5, 0.08, "Valores reais preservados; variação de DVFS/cache não foi ocultada.", ha="center", fontsize=13, color=MUTED)
    save(fig, "05_BENCHMARK_NEON.png")


def audio_pass():
    fig = new_slide("Captação acústica física: PASS")
    ax1 = fig.add_axes([0.055, 0.47, 0.89, 0.38])
    ax2 = fig.add_axes([0.055, 0.08, 0.89, 0.31])
    voice = plt.imread(ROOT / "evidence/physical/retest_after_contact_fix/normal_voice_real_01_waveform_distribution.png")
    claps = plt.imread(ROOT / "evidence/physical/retest_after_contact_fix/normal_claps_real_01_clap_amplitude_time.png")
    ax1.imshow(voice)
    ax2.imshow(claps)
    for ax in (ax1, ax2):
        ax.axis("off")
    fig.text(0.72, 0.89, "voz RMS = 4,99x silêncio | 3 palmas | frame_errors = 0", ha="center", fontsize=15, weight="bold", color=GREEN)
    save(fig, "07_AUDIO_PHYSICAL_PASS.png")


def copies():
    shutil.copyfile(
        ROOT / "evidence/official_tp4/waveforms/dsp_expected_actual_waveform.png",
        OUT / "03_WAVEFORM.png",
    )
    shutil.copyfile(
        ROOT / "evidence/official_tp4/arm_to_fpga_physical/06_FPGA_PI_BIDIRECTIONAL.log",
        OUT / "06_FPGA_PI_BIDIRECTIONAL.log",
    )


if __name__ == "__main__":
    architecture()
    verilog_resources()
    arm64_neon()
    benchmark()
    audio_pass()
    copies()
    print(OUT)
