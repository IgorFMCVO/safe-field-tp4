#!/usr/bin/env python3
"""Render the verified TP5 architecture for the short video."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs_tp5/video_demo/01_ARQUITETURA_FINAL.png"
W, H = 1800, 1000


def ft(size, bold=False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)


def box(draw, xy, title, lines, accent, primary=False):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=24, fill="#112B45" if primary else "#102337", outline=accent, width=4)
    draw.text(((x0 + x1) / 2, y0 + 32), title, anchor="ma", font=ft(27, True), fill="#FFFFFF")
    for i, line in enumerate(lines):
        draw.text(((x0 + x1) / 2, y0 + 86 + i * 38), line, anchor="ma", font=ft(21), fill="#BFD2E5")


def arrow(draw, start, end, color, label, above=True):
    x0, y0 = start; x1, y1 = end
    draw.line((x0, y0, x1, y1), fill=color, width=7)
    direction = 1 if x1 > x0 else -1
    base = x1 - 22 * direction
    draw.polygon([(x1, y1), (base, y1 - 13), (base, y1 + 13)], fill=color)
    draw.text(((x0 + x1) / 2, y0 - 32 if above else y0 + 37), label, anchor="ms" if above else "ma", font=ft(16, True), fill=color)


def main():
    img = Image.new("RGB", (W, H), "#071321"); d = ImageDraw.Draw(img)
    d.text((85, 55), "SAFE-FIELD TP5", font=ft(46, True), fill="#F5F9FD")
    d.text((85, 120), "Uma imagem FPGA: áudio RAW24 contínuo + comandos ARM↔FPGA", font=ft(27), fill="#8EABC7")
    box(d, (70, 300, 370, 560), "INMP441", ["ADC interno", "I²S signed 24-bit", "LEFT · 42,1875 kHz"], "#2DD4BF")
    box(d, (500, 245, 1030, 620), "TANG NANO 4K · GW1NSR-4C", ["receptor I²S + sample_valid", "RAW24 + PCM16 · bancos duplos", "energia / FSM observadora", "Q1.15 + binary16 · CRC / sequence", "arbitragem UART sem colisão"], "#60A5FA", True)
    box(d, (1160, 300, 1580, 560), "RASPBERRY PI 4", ["AArch64 nativo", "libsafe_field_tp5.a", "cliente + métricas", "SAFE-FIELD Core"], "#A78BFA")
    arrow(d, (370, 410), (500, 410), "#2DD4BF", "SD / amostras")
    arrow(d, (1030, 380), (1160, 380), "#60A5FA", "RAW24 / resposta")
    arrow(d, (1160, 495), (1030, 495), "#F7C948", "comando v05 + CRC", above=False)
    d.rounded_rectangle((185, 735, 1615, 895), radius=22, fill="#0B1930", outline="#274864", width=3)
    d.text((225, 772), "BASELINE FINAL", font=ft(24, True), fill="#2DD4BF")
    d.text((225, 817), "27 MHz · UART 1.500.000 baud · SRAM only · TP4 congelado", font=ft(24), fill="#E7F0F8")
    d.text((225, 855), "Simulação 5/5 · P&R/STA PASS · Assembly Pi 4 nativo · áudio físico preservado", font=ft(21), fill="#AFC5D8")
    OUT.parent.mkdir(parents=True, exist_ok=True); img.save(OUT, quality=95); print(OUT)


if __name__ == "__main__": main()
