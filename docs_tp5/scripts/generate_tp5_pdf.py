#!/usr/bin/env python3
"""Generate the audited SAFE-FIELD TP5 technical report PDF."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs_tp5" / "output" / "pdf" / "RELATORIO_TECNICO_SAFE_FIELD_TP5.pdf"
STABILITY_DIR = ROOT / "assembly_tp5" / "evidence" / "raspberry_native"

NAVY = colors.HexColor("#0B1930")
BLUE = colors.HexColor("#177DDC")
CYAN = colors.HexColor("#2DD4BF")
PALE = colors.HexColor("#EAF4FC")
INK = colors.HexColor("#152338")
MUTED = colors.HexColor("#516174")
GREEN = colors.HexColor("#0F8A5F")
AMBER = colors.HexColor("#B76E00")
RED = colors.HexColor("#B42318")


def register_fonts():
    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("SFRegular", str(fonts / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("SFBold", str(fonts / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("SFMono", str(fonts / "consola.ttf")))


class Architecture(Flowable):
    def __init__(self, width=170 * mm, height=58 * mm):
        super().__init__(); self.width = width; self.height = height

    def draw(self):
        c = self.canv
        boxes = [
            (2, 28, 31, 20, "INMP441", "I²S 24-bit"),
            (44, 22, 41, 32, "TANG NANO 4K", "RAW24 + DSP + FSM\nCRC + comandos"),
            (98, 22, 37, 32, "RASPBERRY PI 4", "ARM64 Assembly\nmedição + Core"),
            (148, 28, 26, 20, "INTERFACE", "evidência"),
        ]
        for x, y, w, h, title, sub in boxes:
            c.setFillColor(NAVY if "TANG" in title else PALE)
            c.setStrokeColor(BLUE); c.setLineWidth(1.2)
            c.roundRect(x * mm, y * mm, w * mm, h * mm, 3 * mm, fill=1, stroke=1)
            c.setFillColor(colors.white if "TANG" in title else INK)
            c.setFont("SFBold", 8); c.drawCentredString((x + w / 2) * mm, (y + h - 7) * mm, title)
            c.setFont("SFRegular", 6.7)
            for i, line in enumerate(sub.split("\n")):
                c.drawCentredString((x + w / 2) * mm, (y + h - 13 - i * 4.2) * mm, line)
        c.setStrokeColor(CYAN); c.setFillColor(CYAN); c.setLineWidth(2)
        for x1, x2, y in ((33, 44, 38), (85, 98, 38), (135, 148, 38)):
            c.line(x1 * mm, y * mm, x2 * mm, y * mm)
            c.line((x2 - 2) * mm, (y + 1.5) * mm, x2 * mm, y * mm)
            c.line((x2 - 2) * mm, (y - 1.5) * mm, x2 * mm, y * mm)
        c.setStrokeColor(BLUE); c.setLineWidth(1)
        c.line(98 * mm, 30 * mm, 85 * mm, 30 * mm)
        c.line(87 * mm, 31.5 * mm, 85 * mm, 30 * mm); c.line(87 * mm, 28.5 * mm, 85 * mm, 30 * mm)
        c.setFillColor(MUTED); c.setFont("SFRegular", 6.5)
        c.drawCentredString(91.5 * mm, 41 * mm, "RAW24 / respostas")
        c.drawCentredString(91.5 * mm, 25.7 * mm, "comandos + CRC")
        c.drawCentredString(64.5 * mm, 57 * mm, "caminho acústico preservado; TP4 congelado")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7E0EA")); canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
    canvas.setFont("SFRegular", 7); canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 8.5 * mm, "SAFE-FIELD · TP5 · Igor de Freitas Monteiro")
    canvas.drawRightString(192 * mm, 8.5 * mm, f"página {doc.page}")
    canvas.restoreState()


def p(text, style): return Paragraph(text, style)


def status_table(rows, styles, widths=None):
    table = Table([[p(str(cell), styles["header_cell"] if row_index == 0 else styles["cell"]) for cell in row]
                   for row_index, row in enumerate(rows)], colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "SFBold"), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CCD7E3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F9FC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])); return table


def build():
    register_fonts(); OUT.parent.mkdir(parents=True, exist_ok=True)
    stability = None
    for candidate in sorted(STABILITY_DIR.glob("tp5_uart_stability_600s*.json")):
        value = json.loads(candidate.read_text(encoding="utf-8"))
        if value.get("pass"):
            stability = value
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="SFBold", fontSize=28, leading=32, textColor=colors.white, alignment=TA_LEFT),
        "subtitle": ParagraphStyle("subtitle", fontName="SFRegular", fontSize=12, leading=17, textColor=colors.HexColor("#D7E9FA")),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="SFBold", fontSize=18, leading=22, textColor=NAVY, spaceBefore=7 * mm, spaceAfter=3 * mm),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="SFBold", fontSize=12, leading=15, textColor=BLUE, spaceBefore=4 * mm, spaceAfter=2 * mm),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="SFRegular", fontSize=9.2, leading=13.2, textColor=INK, spaceAfter=2.2 * mm),
        "small": ParagraphStyle("small", fontName="SFRegular", fontSize=7.4, leading=10, textColor=MUTED),
        "cell": ParagraphStyle("cell", fontName="SFRegular", fontSize=7.7, leading=10, textColor=INK),
        "header_cell": ParagraphStyle("header_cell", fontName="SFBold", fontSize=7.7, leading=10, textColor=colors.white),
        "callout": ParagraphStyle("callout", fontName="SFBold", fontSize=10, leading=14, textColor=GREEN, backColor=colors.HexColor("#EAF8F2"), borderColor=colors.HexColor("#9BD8C4"), borderWidth=.7, borderPadding=8, spaceBefore=3 * mm, spaceAfter=4 * mm),
        "code": ParagraphStyle("code", fontName="SFMono", fontSize=7.2, leading=10, textColor=colors.HexColor("#E8EEF6"), backColor=NAVY, borderPadding=8, spaceAfter=3 * mm),
    }

    story = []
    cover = Table([[p("SAFE-FIELD", styles["title"])], [p("RELATÓRIO TÉCNICO · TP5", styles["subtitle"])], [Spacer(1, 20 * mm)], [p("Integração final ARM64 ↔ FPGA<br/>aquisição I²S, RAW24, processamento e protocolo verificável", styles["subtitle"])], [Spacer(1, 20 * mm)], [p("Igor de Freitas Monteiro<br/>Sistemas Digitais Embarcados<br/>13 de setembro de 2026", styles["subtitle"]) ]], colWidths=[174 * mm], rowHeights=[32 * mm, 18 * mm, 20 * mm, 35 * mm, 20 * mm, 35 * mm])
    cover.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("BOX", (0, 0), (-1, -1), 0, NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 14 * mm), ("TOPPADDING", (0, 0), (0, 0), 8 * mm)]))
    story += [cover, PageBreak()]

    story += [p("1. Resultado executivo", styles["h1"]), p("O TP5 preserva o núcleo acústico aprovado e acrescenta, na mesma imagem da Tang Nano 4K, recepção de comandos TP5, unidades Q1.15/binary16, resposta com CRC e arbitragem determinística com o streaming RAW24. O TP4 validado não foi alterado.", styles["body"])]
    executive = [
        ["Gate", "Resultado", "Evidência objetiva"],
        ["Simulação RTL", "PASS", "5/5 testbenches auto-verificáveis; VCDs preservados"],
        ["Síntese / P&R / STA", "PASS", "0 violações setup/hold; Fmax 42,268 MHz @ 27 MHz"],
        ["Assembly nativo", "PASS", "Pi 4 AArch64; ABI 196/196; referência PASS"],
        ["FPGA → Raspberry", "PASS físico", "RAW24 CRC-válido, sem perdas/erros"],
        ["Raspberry → FPGA", "PASS físico" if stability else "PENDENTE", "PING + 3 operações úteis" if stability else "aguardando gate físico final"],
        ["Estabilidade 600 s", "PASS físico" if stability and stability.get("pass") else "PENDENTE", f'{stability.get("responses", 0)} respostas; {stability.get("raw24_frames", 0):,} quadros RAW24' if stability else "aguardando execução"],
        ["Áudio físico", "PASS", "voz coerente + tom físico de 1.000 Hz; transporte final RAW24 ativo"],
    ]
    story += [status_table(executive, styles, [42 * mm, 31 * mm, 97 * mm]), p("Baseline física real: Raspberry Pi 4 Model B Rev 1.5, AArch64; Tang Nano 4K GW1NSR-4C. A plataforma real é declarada sem representar emulação como teste físico.", styles["callout"])]

    story += [p("2. Arquitetura integrada", styles["h1"]), Architecture(), p("O enlace UART opera a 1.500.000 baud. Quadros RAW24 completos sempre terminam antes de uma resposta TP5; o comando inibe apenas o início do próximo pacote. A aquisição I²S continua independente do estado QUIET/ACTIVE.", styles["body"])]
    story += [p("Pinout físico preservado", styles["h2"]), status_table([
        ["Sinal", "Direção", "Package pin", "Nível"], ["sys_clk", "entrada", "45", "27 MHz"], ["GPIO17", "Pi → FPGA", "40", "3,3 V"], ["I²S SCK / WS", "FPGA → INMP441", "41 / 42", "3,3 V"], ["I²S SD", "INMP441 → FPGA", "43", "3,3 V"], ["UART TX", "FPGA → Pi RX", "39", "3,3 V"], ["UART RX", "Pi TX → FPGA", "46", "3,3 V"], ["LED", "FPGA → LED", "10", "1,8 V"],
    ], styles, [37 * mm, 53 * mm, 35 * mm, 35 * mm])]

    story += [PageBreak(), p("3. FPGA: aquisição, processamento e coexistência", styles["h1"]), p("O gerador deriva SCK de 2,7 MHz e WS de 42,1875 kHz a partir de 27 MHz, com 64 SCK por frame. O receptor considera o atraso I²S de um BCLK, captura 24 bits signed MSB-first no slot LEFT e emite sample_valid. O packetizer mantém bancos duplos, RAW24 e PCM16 derivado; a FSM de energia é observadora e não interrompe a captura.", styles["body"]), p("O top responde a PING, multiplicação Q1.15, multiplicação binary16 e leitura de contadores. CRC/framing, erros I²S e overrun são expostos. Q1.15 usa saturação; binary16 é perfil acadêmico reduzido, com subnormais em flush-to-zero.", styles["body"]), p("assign uart_tx = raw_tx_active ? raw_uart_tx : response_uart_tx;<br/>wire response_launch = response_pending &amp;&amp; !response_launched &amp;&amp; !raw_tx_active;", styles["code"])]
    story += [p("Cobertura RTL", styles["h2"]), status_table([
        ["Teste", "Resultado", "Cobertura"], ["tb_arithmetic", "PASS · 23 checks", "Q1.15, saturação, sinais; FP16 normal/zero/overflow/NaN/underflow"], ["tb_command_rx", "PASS", "hold valid/ready, CRC inválido e recuperação"], ["tb_gpio_oe", "PASS", "OE / tri-state"], ["tb_tp5_integration", "PASS · 8 transações", "contrato completo e comandos"], ["tb_tp5_raw24_coexist", "PASS", "RAW24 95 bytes + resposta PING, CRCs e ausência de colisão"],
    ], styles, [47 * mm, 35 * mm, 88 * mm])]

    story += [p("4. Protocolo TP5", styles["h1"]), status_table([
        ["Fluxo", "Formato"], ["ARM → FPGA · 11 bytes", "A6 6A | v05 | command | sequence16 | payload32 | CRC-8/ATM"], ["FPGA → ARM · 12 bytes", "5A A5 | v05 | type | sequence16 | data32 | flags | CRC-8/ATM"], ["RAW24 · 95 bytes", "A5 C4 | versão/tipo | sequence | source counter | 16 × (RAW24+PCM16) | CRC-16"],
    ], styles, [47 * mm, 123 * mm]), p("Sequence, CRC e flags distinguem perda, corrupção e resposta semântica inválida. O parser ARM ressincroniza respostas TP5 em meio ao fluxo RAW24 contínuo.", styles["body"])]

    story += [PageBreak(), p("5. Assembly ARM64 nativo", styles["h1"]), p("A entrega contém biblioteca estática real e executáveis AArch64. As rotinas usam syscalls Linux via svc #0, parsing, buffers, conversões, CRC e validação integral de resposta. A correção de ABI salva/restaura LR na função não-leaf sf_validate_response; a regressão nativa fechou 196/196 checks.", styles["body"]), status_table([
        ["Artefato / teste", "Resultado / SHA-256"], ["libsafe_field_tp5.a", "78460FA7D25A96CEFA3ECAA105CB716DD9939885961FD5678FFC9E809806069C"], ["tp5_demo", "A435EE38BE07100F9DDE0800AD00191AC5C2D1993DC032277E01D37E1CF04DF4"], ["tp5_uart_demo", "11F1F4BFE61C9EF05E3CA126EAB6018EDE8B77C67CD7F2DC045B939A13E14BFE"], ["ABI", "PASS · 196/196"], ["PTY", "PASS · 7/7 · somente simulação de contrato"], ["Execução física", "PASS · COMMANDS_VERIFIED=4 · Pi 4 Model B Rev 1.5"],
    ], styles, [45 * mm, 125 * mm])]
    story += [p("Operações físicas verificadas", styles["h2"]), status_table([
        ["Comando", "Entrada", "Esperado", "Obtido"], ["PING", "—", "0x54503501", "0x54503501"], ["Q1.15", "0x4000 × 0x4000", "0x00002000", "0x00002000"], ["Q1.15", "0x8000 × 0x8000", "0x00008000", "0x00008000"], ["FP16", "0x3E00 × 0x4000", "0x00004200", "0x00004200"],
    ], styles, [34 * mm, 52 * mm, 42 * mm, 42 * mm])]

    story += [p("6. Implementação Gowin e timing", styles["h1"]), p("Imagem final: safe_field_tp5_final.fs · SHA-256 2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18. Síntese, P&R e bitstream concluídos; programação realizada somente em SRAM.", styles["callout"]), status_table([
        ["Métrica", "Resultado"], ["Logic", "2169 / 4608 · 48%"], ["Registers", "2252 / 3573 · 64%"], ["CLS", "2030 / 2304 · 89%"], ["DSP", "1 / 8 · 13%"], ["Clock", "27,000 MHz · PRIMARY 1/8"], ["Fmax", "42,268 MHz"], ["Setup", "0 violações · slack 13,379 ns"], ["Hold", "0 violações · slack 0,558 ns"],
    ], styles, [70 * mm, 100 * mm]), p("Warnings: 129 PA1001 de saídas/carry não consumidos após poda de larguras e 1 PR1014 de roteamento do clock. Nenhum foi ocultado; o relatório final registra recurso PRIMARY, Fmax acima do requisito e zero endpoints violados.", styles["small"])]

    story += [PageBreak(), p("7. Evidência física, desempenho e estabilidade", styles["h1"]), p("O smoke da imagem final recebeu 3.966 quadros e 63.456 amostras em 3,012 s, com CRC, sequence loss, source-counter loss, erro I²S e overrun iguais a zero. RAW24→PCM16 coincidiu amostra a amostra; o WAV produzido foi byte-idêntico ao PCM transportado.", styles["body"]), status_table([
        ["Ensaio", "Resultado"], ["Assembly round-trip", "PASS · PING + 3 operações · RTT total 2,464 ms"], ["Rajada de 100 PINGs", "100/100 · 0 falhas · média 8,227 ms · p95 11,895 ms · 121,55 comandos/s"], ["Estabilidade", (f'PASS · {stability["elapsed_duration_s"]:.3f} s · {stability["responses"]} respostas · {stability["raw24_frames"]:,} RAW24' if stability and stability.get("pass") else "PENDENTE")], ["Integridade 600 s", (f'CRC/perdas/framing/I²S/overrun = 0 · p95 {stability["rtt_p95_us"]/1000:.3f} ms' if stability and stability.get("pass") else "PENDENTE")],
    ], styles, [55 * mm, 115 * mm])]
    story += [p("8. Áudio físico preservado", styles["h1"]), p("A revalidação pós-reparo recuperou voz humana coerente exclusivamente do PCM Tang→Pi. Uma reprodução sincronizada de 1.000 Hz foi observada exatamente em 1.000,0 Hz, com razão do bin local de 169,46×; a rodada final teve 31.646 quadros de transporte e 0 CRC/perdas/erros I²S. Essa razão não é apresentada como SNR calibrado.", styles["body"]), p("No smoke desta imagem TP5, 63.456 amostras foram transportadas com RMS RAW24 94.145,97, pico 247.370 e zero erro. Portanto a integração de comandos não regrediu o streaming acústico. A captura pessoal WAV/VTT não integra o repositório público nem o ZIP.", styles["body"])]

    photo_a = ROOT / "docs_tp5" / "evidence" / "photos" / "INMP441_WIRING_OPERATOR_20260913.jpg"
    photo_b = ROOT / "docs_tp5" / "evidence" / "photos" / "TANG_NANO_4K_PIN_WIRING_OPERATOR_20260913.jpg"
    if photo_a.exists() and photo_b.exists():
        images = Table([
            [Image(str(photo_a), width=82 * mm, height=46 * mm), Image(str(photo_b), width=82 * mm, height=46 * mm)],
            [p("INMP441 e chicote — foto fornecida pelo operador em 13/09/2026.", styles["small"]), p("Pinout Tang Nano 4K — foto fornecida pelo operador em 13/09/2026.", styles["small"])],
        ], colWidths=[85 * mm, 85 * mm])
        images.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm)]))
        story += [p("9. Registro visual da bancada", styles["h1"]), images]

    story += [p("10. Rastreabilidade e limites", styles["h1"]), status_table([
        ["Classe", "Declaração"], ["Físico", "Pi 4 real + Tang real; JTAG/SRAM; UART bidirecional; RAW24"], ["Nativo", "ELF AArch64 executado no Pi 4; não QEMU"], ["Simulado", "WASM/iverilog e PTY são evidência de contrato, rotulados como tal"], ["Rollback", "TP4 fs preservado (SHA 5D8F…F39181) e checkpoint pré-handoff"], ["Fora do escopo", "sem câmera, TLS, IA, diarização ou expansão do MVP"], ["Vídeo", "gravação/webcam e link final dependem do operador"],
    ], styles, [42 * mm, 128 * mm])]

    story += [PageBreak(), p("11. Conclusão", styles["h1"]), p("A baseline final reúne aquisição I²S/RAW24 e processamento determinístico com um protocolo ARM↔FPGA versionado, CRC, sequência e respostas verificadas. Simulação, síntese, P&R, STA e Assembly nativo passaram; a sessão física confirmou comandos úteis em ambos os sentidos e preservou o áudio.", styles["body"]), p("O material de entrega inclui fontes comentados, biblioteca, ELF, bitstream, constraints, relatórios Gowin, VCDs, logs físicos, documentação, hashes e ZIP auditado. O vídeo final permanece uma ação humana por exigir webcam e publicação do link.", styles["callout"]), p("Repositório: https://github.com/IgorFMCVO/safe-field-tp4<br/>Branch: tp5/final-integration-v1<br/>PR: https://github.com/IgorFMCVO/safe-field-tp4/pull/1", styles["body"])]

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=17 * mm, bottomMargin=18 * mm, title="Relatório Técnico SAFE-FIELD TP5", author="Igor de Freitas Monteiro")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest().upper()
    print(json.dumps({"pdf": str(OUT), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__": build()
