#!/usr/bin/env python3
"""Generate the final SAFE-FIELD TP4 academic PDF from frozen evidence."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs_tp4" / "output" / "pdf" / "RELATORIO_TECNICO_SAFE_FIELD_TP4.pdf"


NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#247BA0")
CYAN = colors.HexColor("#D9F0F7")
GREEN = colors.HexColor("#20834A")
LIGHT_GREEN = colors.HexColor("#E7F6EC")
AMBER = colors.HexColor("#A66200")
LIGHT_AMBER = colors.HexColor("#FFF3D6")
GRID = colors.HexColor("#B9C7D4")
TEXT = colors.HexColor("#23303D")
MUTED = colors.HexColor("#566573")


class ArchitectureDiagram(Flowable):
    """Compact vector diagram of the evaluated data path."""

    def __init__(self, width: float, height: float = 5.2 * cm):
        super().__init__()
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        boxes = [
            ("INMP441", "ADC + I2S"),
            ("Tang Nano 4K", "I2S RX"),
            ("DSP + BSRAM", "power + window"),
            ("SAFE-FIELD", "FSM"),
            ("UART + CRC", "telemetry"),
            ("Raspberry Pi 4", "ARM64 + JSONL"),
        ]
        gap = 7
        box_w = (self.width - gap * (len(boxes) - 1)) / len(boxes)
        y = 3.4 * cm
        box_h = 1.45 * cm
        for i, (title, sub) in enumerate(boxes):
            x = i * (box_w + gap)
            fill = CYAN if i not in (2, 3) else LIGHT_GREEN
            c.setFillColor(fill)
            c.setStrokeColor(BLUE if i not in (2, 3) else GREEN)
            c.roundRect(x, y, box_w, box_h, 5, fill=1, stroke=1)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawCentredString(x + box_w / 2, y + 0.88 * cm, title)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 6.8)
            c.drawCentredString(x + box_w / 2, y + 0.46 * cm, sub)
            if i < len(boxes) - 1:
                ax = x + box_w + 1
                ay = y + box_h / 2
                c.setStrokeColor(NAVY)
                c.line(ax, ay, ax + gap - 2, ay)
                c.line(ax + gap - 5, ay + 3, ax + gap - 2, ay)
                c.line(ax + gap - 5, ay - 3, ax + gap - 2, ay)

        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(0, 2.7 * cm, "Deterministic hardware path")
        c.setFont("Helvetica", 7)
        c.setFillColor(MUTED)
        c.drawString(0, 2.28 * cm, "sound -> signed samples -> energy -> decision -> verified event")

        x1 = self.width * 0.18
        x2 = self.width * 0.82
        y2 = 1.25 * cm
        for x, title, sub in [
            (x1, "Pi -> FPGA", "command + seq + payload + CRC-8"),
            (x2, "FPGA -> Pi", "state + energy + frames + flags + CRC-8"),
        ]:
            c.setFillColor(LIGHT_AMBER if "Pi ->" in title else LIGHT_GREEN)
            c.setStrokeColor(AMBER if "Pi ->" in title else GREEN)
            c.roundRect(x - 3.0 * cm, y2, 6.0 * cm, 1.0 * cm, 5, fill=1, stroke=1)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(x, y2 + 0.60 * cm, title)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 7)
            c.drawCentredString(x, y2 + 0.27 * cm, sub)


def make_styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(
        name="TitleSF", parent=ss["Title"], fontName="Helvetica-Bold",
        fontSize=24, leading=28, textColor=NAVY, alignment=TA_CENTER, spaceAfter=12,
    ))
    ss.add(ParagraphStyle(
        name="SubtitleSF", parent=ss["Normal"], fontName="Helvetica",
        fontSize=11, leading=15, textColor=MUTED, alignment=TA_CENTER, spaceAfter=9,
    ))
    ss.add(ParagraphStyle(
        name="H1SF", parent=ss["Heading1"], fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=NAVY, spaceBefore=8, spaceAfter=8,
    ))
    ss.add(ParagraphStyle(
        name="H2SF", parent=ss["Heading2"], fontName="Helvetica-Bold",
        fontSize=12, leading=15, textColor=BLUE, spaceBefore=7, spaceAfter=5,
    ))
    ss.add(ParagraphStyle(
        name="BodySF", parent=ss["BodyText"], fontName="Helvetica",
        fontSize=9.2, leading=13.2, textColor=TEXT, alignment=TA_JUSTIFY, spaceAfter=6,
    ))
    ss.add(ParagraphStyle(
        name="SmallSF", parent=ss["BodyText"], fontName="Helvetica",
        fontSize=7.6, leading=10, textColor=MUTED, alignment=TA_LEFT,
    ))
    ss.add(ParagraphStyle(
        name="CalloutSF", parent=ss["BodyText"], fontName="Helvetica-Bold",
        fontSize=10, leading=14, textColor=GREEN, borderColor=GREEN,
        borderWidth=0.8, borderPadding=8, backColor=LIGHT_GREEN, spaceBefore=6, spaceAfter=8,
    ))
    return ss


def P(styles, text, name="BodySF"):
    return Paragraph(text, styles[name])


def table(data, widths, header=True, font_size=7.5):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(commands))
    return t


def scaled_image(path: Path, max_w: float, max_h: float):
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    return Image(str(path), width=w * scale, height=h * scale)


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(GRID)
    canvas.line(1.8 * cm, height - 1.28 * cm, width - 1.8 * cm, height - 1.28 * cm)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(NAVY)
    canvas.drawString(1.8 * cm, height - 1.05 * cm, "SAFE-FIELD | TP4 Sistemas Digitais Embarcados")
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - 1.8 * cm, 0.9 * cm, f"Igor de Freitas Monteiro | pagina {doc.page}")
    canvas.restoreState()


def build_pdf():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4,
        rightMargin=1.8 * cm, leftMargin=1.8 * cm,
        topMargin=1.65 * cm, bottomMargin=1.45 * cm,
        title="SAFE-FIELD - Relatorio Tecnico TP4",
        author="Igor de Freitas Monteiro",
        subject="FPGA, I2S, DSP, BSRAM, UART, ARM64 e NEON",
    )
    W = A4[0] - doc.leftMargin - doc.rightMargin
    story = []

    # Cover
    story += [Spacer(1, 2.0 * cm), P(styles, "SAFE-FIELD", "TitleSF")]
    story += [P(styles, "Relatorio Tecnico - TP4 de Sistemas Digitais Embarcados", "SubtitleSF")]
    story += [Spacer(1, 0.6 * cm), ArchitectureDiagram(W), Spacer(1, 0.55 * cm)]
    summary = [
        ["Resultado da rubrica", "22/22 PASS | 0 PARTIAL | 0 MISSING"],
        ["FPGA", "Tang Nano 4K - GW1NSR-4C - clock 27 MHz"],
        ["Processador", "Raspberry Pi 4 Model B - AArch64 real"],
        ["Build academico", "P&R PASS | STA PASS | 1 DSP | 1 BSRAM"],
        ["Data", "04/09/2026"],
    ]
    story += [table(summary, [5.0 * cm, W - 5.0 * cm], header=False, font_size=8.5)]
    story += [Spacer(1, 0.55 * cm), P(styles,
        "Baseline fisica preservada. O build academico corrigido foi programado somente em SRAM. "
        "FPGA -> Raspberry e Raspberry -> FPGA foram aprovados fisicamente, com tres de tres "
        "respostas numericas corretas, zero erro de checksum e zero perda de sequence.", "CalloutSF")]
    story += [Spacer(1, 0.3 * cm), P(styles, "Aluno: Igor de Freitas Monteiro", "SubtitleSF")]
    story += [PageBreak()]

    # 1 - Scope and evolution
    story += [P(styles, "1. Introducao e escopo", "H1SF")]
    story += [P(styles,
        "O SAFE-FIELD demonstra aquisicao e processamento deterministico de audio em FPGA, "
        "integracao com processador ARM64 e comunicacao serial verificavel. O trabalho parte "
        "da baseline fisica Raspberry GPIO17 -> Tang -> LED e evolui ate som -> INMP441 -> I2S "
        "-> FPGA -> energia/FSM -> UART -> Raspberry.")]
    story += [P(styles,
        "O fechamento academico acrescenta uma unidade aritmetica mapeada em DSP, um buffer "
        "funcional em BSRAM, recepcao de comandos Pi -> Tang com CRC, Assembly AArch64 e rotinas "
        "NEON inteiras e floating point. Nenhuma dessas mudancas sobrescreve o bitstream de audio validado.")]
    story += [P(styles, "1.1 Evolucao TP3 -> TP4", "H2SF")]
    evolution = [
        ["Camada", "Baseline preservada", "Acrescimo TP4"],
        ["Controle", "GPIO17 -> Tang -> LED", "FSM QUIET/ACTIVE com override"],
        ["Aquisicao", "Integracao digital", "INMP441, I2S 24-bit signed, 42.1875 ksample/s"],
        ["Processamento", "Logica simples", "magnitude, janela, histerese, DSP e BSRAM"],
        ["Comunicacao", "GPIO", "UART bidirecional versionada com CRC-8/ATM"],
        ["Software", "Raspberry", "bridge JSONL, AArch64 e NEON medidos"],
    ]
    story += [table(evolution, [3.1 * cm, 5.2 * cm, W - 8.3 * cm], font_size=7.6)]
    story += [P(styles, "1.2 Delimitacao", "H2SF")]
    story += [P(styles,
        "O nucleo avaliado termina em evento digital verificavel no Raspberry. Camera UVC, wearable, "
        "transcricao, IA e transporte integral de PCM permanecem declarados como evolucoes futuras, "
        "sem resultados ficticios.")]

    # 2 - Architecture/pinout
    story += [P(styles, "2. Arquitetura e pinout", "H1SF"), ArchitectureDiagram(W, 5.2 * cm)]
    pinout = [
        ["Sinal", "Tang pin", "Direcao", "Padrao"],
        ["clock 27 MHz", "45", "entrada", "LVCMOS33"],
        ["GPIO17", "40", "Pi -> Tang", "LVCMOS33"],
        ["I2S SCK", "41", "Tang -> INMP441", "LVCMOS33"],
        ["I2S WS", "42", "Tang -> INMP441", "LVCMOS33"],
        ["I2S SD", "43", "INMP441 -> Tang", "LVCMOS33"],
        ["LED", "10", "saida", "LVCMOS18"],
        ["UART TX", "39", "Tang -> Pi GPIO15", "LVCMOS33"],
        ["UART RX academico", "46", "Pi GPIO14 -> Tang", "LVCMOS33 input"],
    ]
    story += [Spacer(1, 0.2 * cm), table(pinout, [4.0 * cm, 2.0 * cm, 5.0 * cm, W - 11.0 * cm])]
    story += [P(styles,
        "O package pin 46 foi selecionado no esquematico oficial Sipeed 3603: IOT13B, Bank 1 em "
        "3,3 V e net CAMERA_SDA. A camera permaneceu desconectada. A ligacao fisica foi executada "
        "com as placas desenergizadas e o build foi programado exclusivamente em SRAM.", "SmallSF")]

    # 3 - Physical audio
    story += [PageBreak(), P(styles, "3. Captacao de audio fisica", "H1SF")]
    story += [P(styles,
        "Apos reparo dos contatos dos pins 41 e 43, SD voltou a transmitir dados e o diagnostico "
        "anterior de falha do INMP441 foi invalidado. A captura real apresentou samples signed e "
        "nao-zero, resposta clara a voz e tres picos de palmas, sem erros de frame.")]
    physical = [
        ["Metrica fisica", "Resultado"],
        ["Samples LEFT no gate pos-reparo", "1024/1024 nao-zero"],
        ["RMS voz / silencio", "4,992566x"],
        ["Mean absolute voz / silencio", "4,372595x"],
        ["Palmas", "3 eventos distinguiveis"],
        ["Frame errors", "0"],
        ["Aquisicao continua", "99,42 s PASS"],
    ]
    story += [table(physical, [8.0 * cm, W - 8.0 * cm], font_size=8.2)]
    silence = ROOT / "evidence/physical/retest_after_contact_fix/normal_silence_reference_01_waveform_distribution.png"
    voice = ROOT / "evidence/physical/retest_after_contact_fix/normal_voice_real_01_waveform_distribution.png"
    story += [Spacer(1, 0.25 * cm), P(styles, "Figura 1 - Referencia fisica de silencio", "SmallSF")]
    story += [scaled_image(silence, W, 8.3 * cm), PageBreak()]
    story += [P(styles, "Figura 2 - Voz real capturada pelo INMP441 e reconstruida na FPGA", "SmallSF")]
    story += [scaled_image(voice, W, 10.0 * cm)]
    claps = ROOT / "evidence/physical/retest_after_contact_fix/normal_claps_real_01_clap_amplitude_time.png"
    story += [Spacer(1, 0.2 * cm), P(styles, "Figura 3 - Tres palmas: amplitude por tempo", "SmallSF")]
    story += [scaled_image(claps, W, 7.2 * cm)]

    # 4 - DSP/BRAM
    story += [PageBreak(), P(styles, "4. Unidade aritmetica, DSP e BSRAM", "H1SF")]
    story += [P(styles, "4.1 DSP dedicado", "H2SF")]
    story += [P(styles,
        "safe_field_audio_energy_dsp seleciona sample[23:8] como inteiro signed de 16 bits e "
        "calcula seu quadrado em pipeline. Zero, valores positivos e negativos, maximo positivo "
        "e minimo negativo foram verificados. O limite -32768^2 = 1073741824 cabe em 32 bits.")]
    dsp = [
        ["Evidencia", "Valor"],
        ["Primitive no P&R", "MULT18X18 = 1"],
        ["Hierarchy report", "DSP NUMBER = 1 em power_dsp"],
        ["Latencia", "1 ciclo = 37,037 ns a 27 MHz"],
        ["Teste", "10/10 checks PASS"],
        ["Replay fisico", "8192 silencio + 8192 voz; overflow = 0"],
        ["Potencia media", "245,4473 silencio; 6117,9492 voz; razao 24,9257x"],
    ]
    story += [table(dsp, [6.2 * cm, W - 6.2 * cm], font_size=8)]
    story += [P(styles, "4.2 BSRAM funcional", "H2SF")]
    story += [P(styles,
        "safe_field_energy_bram implementa 256 x 32 bits, escrita de uma potencia por sample LEFT, "
        "leitura sincrona e acumulador de 40 bits. A cada 256 amostras, produz uma media verificavel. "
        "Os enderecos 0, 123 e 255, wrap e media de 0..255 igual a 127 foram testados.")]
    bram = [
        ["Primitive", "Quantidade", "Funcao"],
        ["SDPB", "1", "buffer 256 x 32 com read/write real"],
        ["BSRAM total", "1/10", "10% dos blocos disponiveis"],
        ["Testbench", "5/5 PASS", "enderecos, wrap e media"],
    ]
    story += [table(bram, [4.0 * cm, 3.0 * cm, W - 7.0 * cm], font_size=8)]
    dsp_wave = ROOT / "evidence/official_tp4/waveforms/dsp_expected_actual_waveform.png"
    story += [Spacer(1, 0.25 * cm), P(styles, "Figura 4 - Waveform DSP expected x actual", "SmallSF")]
    story += [scaled_image(dsp_wave, W, 8.0 * cm)]

    # 5 - Protocol
    story += [PageBreak(), P(styles, "5. UART bidirecional e CRC", "H1SF")]
    story += [P(styles,
        "A direcao Tang -> Pi v1 foi aprovada fisicamente: 3.264 mensagens validas, zero perdas de "
        "sequence, zero erros de avanco de frame e uma transicao QUIET -> ACTIVE -> QUIET. O frame "
        "Pi -> Tang adiciona comandos numericos sem substituir a telemetria aprovada.")]
    protocol = [
        ["Offset", "Campo", "Bytes", "Observacao"],
        ["0", "sync", "2", "A6 6A"],
        ["2", "version", "1", "01"],
        ["3", "command", "1", "square/read/average"],
        ["4", "sequence", "2", "little-endian"],
        ["6", "payload", "4", "signed/unsigned conforme comando"],
        ["10", "CRC", "1", "CRC-8/ATM sobre bytes 0..9"],
    ]
    story += [table(protocol, [1.8 * cm, 4.0 * cm, 2.0 * cm, W - 7.8 * cm], font_size=8)]
    story += [P(styles,
        "Os comandos implementados sao: 0x01 square16 via DSP, 0x02 leitura da BSRAM e 0x03 "
        "media mais recente. A resposta usa o TX aprovado, preserva sequence, marca response e "
        "propaga erro em flags. Tres vetores passaram e um CRC corrompido foi rejeitado.")]
    physical_vectors = [
        ["Input", "Expected", "Actual", "Resultado"],
        ["123", "15129", "15129", "PASS"],
        ["-123", "15129", "15129", "PASS"],
        ["32767", "1073676289", "1073676289", "PASS"],
    ]
    story += [P(styles, "5.1 Validacao bidirecional ARM <-> FPGA", "H2SF")]
    story += [table(physical_vectors, [3.0 * cm, 4.0 * cm, 4.0 * cm, W - 11.0 * cm], font_size=8)]
    story += [P(styles,
        "Resultado fisico: 3/3 PASS, checksum errors = 0, sequence losses = 0 e response errors = 0. "
        "A arbitragem foi corrigida para manter event_valid ate event_ready; a regressao permaneceu "
        "40/40 PASS sem alterar audio, DSP ou BSRAM.", "CalloutSF")]
    uart_wave = ROOT / "evidence/official_tp4/waveforms/uart_command_crc_waveform.png"
    story += [P(styles, "Figura 5 - Comandos UART e rejeicao de checksum", "SmallSF")]
    story += [scaled_image(uart_wave, W, 10.0 * cm)]

    # 6 - ARM64/NEON
    story += [PageBreak(), P(styles, "6. Assembly AArch64 e NEON no Raspberry Pi 4", "H1SF")]
    story += [P(styles,
        "O codigo foi compilado e executado no Raspberry Pi 4 real, em AArch64, com GCC 14.2.0. "
        "O log integral, binario e objdump -d -S estao preservados. Todos os testes expected x actual passaram.")]
    arm = [
        ["Competencia", "Instrucao/estrategia", "Resultado real"],
        ["Multi-palavra 128-bit", "ADDS + ADC", "expected = actual"],
        ["Inteiro -> double", "SCVTF", "-123456789,0 exato"],
        ["Lookup table", "LDR indexado + limite", "validos e out-of-range PASS"],
        ["Mascara/shift/rotate", "AND, LSR, EOR, ROR", "expected = actual"],
        ["NEON inteiro, 8 lanes", "SMULL/SMULL2/UADALP", "energia = 21865754704 exata"],
        ["NEON float, 4 lanes", "FMUL", "erro maximo = 0; tolerancia 1e-7"],
    ]
    story += [table(arm, [4.6 * cm, 5.0 * cm, W - 9.6 * cm], font_size=7.7)]
    story += [P(styles, "6.1 Benchmark real", "H2SF")]
    bench = [
        ["Repeticoes", "NEON inteiro speedup", "NEON float speedup"],
        ["50", "3,243166x", "2,052943x"],
        ["200", "9,566309x", "1,161292x"],
        ["800", "3,273697x", "1,126641x"],
    ]
    story += [table(bench, [4.0 * cm, 6.0 * cm, W - 10.0 * cm], font_size=8.4)]
    story += [P(styles,
        "Os runs 50/200/800 foram preservados sem selecao do melhor caso. A variacao e compativel "
        "com DVFS, caches e sistema operacional. No run de 800 repeticoes: escalar inteiro "
        "58.673.389 ns, NEON inteiro 17.922.667 ns; escalar float 59.432.019 ns, NEON float 52.751.518 ns.")]

    # 7 - verification and build
    story += [P(styles, "7. Simulacao, sintese, P&R e STA", "H1SF")]
    sim = [
        ["Testbench", "Checks", "Status"],
        ["DSP signed square", "10", "PASS"],
        ["BSRAM read/window", "5", "PASS"],
        ["UART command/CRC", "8", "PASS"],
        ["Integracao I2S/DSP/BRAM/UART/GPIO17", "17", "PASS"],
        ["Total", "40/40", "PASS"],
    ]
    story += [table(sim, [9.0 * cm, 3.0 * cm, W - 12.0 * cm], font_size=8)]
    pnr = [
        ["Recurso/STA", "Uso/resultado"],
        ["Logic", "1065/4608 (24%)"],
        ["Registers", "833/3573 (24%)"],
        ["CLS", "827/2304 (36%)"],
        ["BSRAM", "1/10; SDPB = 1"],
        ["DSP", "MULT18X18 = 1"],
        ["Setup/Hold violations", "0/0; TNS = 0/0"],
        ["Fmax", "38,297 MHz para requisito 27 MHz"],
    ]
    story += [Spacer(1, 0.25 * cm), table(pnr, [7.0 * cm, W - 7.0 * cm], font_size=8)]
    story += [P(styles,
        "Bitstream academico: safe_field_tp4_official_bidirectional.fs. SHA-256 "
        "6E4C460162816C54EE38B11CDA246004C05FE07CEC4C1FA963FDBB36092E172F. "
        "O arquivo e separado e foi programado somente em SRAM.", "CalloutSF")]

    # 8 - warnings/performance
    story += [PageBreak(), P(styles, "8. Warnings e desempenho", "H1SF")]
    warnings = [
        ["Codigo", "Qtd.", "Analise"],
        ["NL0002", "1", "hierarquia flattened; nao altera funcao"],
        ["PA1001", "54", "saidas carry/cascade/auxiliares nao usadas"],
        ["PR1014", "1", "rota generica de sys_clk; STA sem violacoes"],
        ["Total", "56", "todos preservados; nenhum mascarado"],
    ]
    story += [table(warnings, [2.8 * cm, 1.5 * cm, W - 4.3 * cm], font_size=8)]
    perf = [
        ["Modulo", "Latencia", "Throughput/observacao"],
        ["I2S LEFT", "23,704 us/frame", "42.187,5 samples/s; frame_errors=0"],
        ["DSP", "37,037 ns", "ate 27 Mresultados/s"],
        ["BSRAM", "37,037 ns read", "1 read + 1 write/ciclo"],
        ["Janela 256", "6,068 ms", "164,795 janelas/s"],
        ["UART FPGA -> Pi", "1,387 ms/frame", "720,9 frames/s max; 164,8 usados"],
        ["UART Pi -> FPGA", "0,953 ms/cmd", "1.048 comandos/s max"],
    ]
    story += [Spacer(1, 0.3 * cm), table(perf, [5.0 * cm, 3.7 * cm, W - 8.7 * cm], font_size=7.8)]

    # 9 - rubric
    story += [P(styles, "9. Matriz da rubrica", "H1SF")]
    rubric_items = [
        ("Unidade aritmetica Verilog", "PASS"), ("BRAM funcional", "PASS"),
        ("DSP dedicado", "PASS"), ("Waveforms", "PASS"),
        ("Teste fisico Tang", "PASS"), ("ARM64 multi-palavra", "PASS"),
        ("Conversao inteiro/float", "PASS"), ("Lookup table", "PASS"),
        ("Masks/shifts/rotates", "PASS"), ("NEON inteiro", "PASS"),
        ("NEON float", "PASS"), ("Benchmark", "PASS"),
        ("Arquitetura", "PASS"), ("ARM -> FPGA", "PASS"),
        ("FPGA -> ARM", "PASS"), ("Checksum", "PASS"),
        ("Telemetria", "PASS"), ("Desempenho/latencia", "PASS"),
        ("Documentacao", "PASS"), ("PDF", "PASS"),
        ("ZIP", "PASS"), ("Video", "PASS"),
    ]
    rubric = [["#", "Requisito", "Status"]] + [[str(i), n, s] for i, (n, s) in enumerate(rubric_items, 1)]
    rt = table(rubric, [1.0 * cm, W - 4.2 * cm, 3.2 * cm], font_size=6.6)
    rt.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TEXTCOLOR", (2, 1), (2, 22), GREEN),
        ("FONTNAME", (2, 1), (2, 22), "Helvetica-Bold"),
    ]))
    story += [rt, Spacer(1, 0.2 * cm), P(styles,
        "Resultado: 22/22 PASS, 0 PARTIAL, 0 MISSING. O video foi gravado e publicado no YouTube.",
        "CalloutSF")]

    # 10 - limitations and closeout
    story += [PageBreak(), P(styles, "10. Limitacoes, entrega e conclusao", "H1SF")]
    story += [P(styles, "10.1 Limitacoes honestas", "H2SF")]
    limitations = [
        ["Item", "Estado"],
        ["Pi -> Tang fisico", "PASS; 3/3 respostas corretas; checksum=0; perdas=0"],
        ["Video", "gravado; https://youtu.be/1Ancm5QdG2E"],
        ["FSM refinada", "replay sobre dados fisicos; nao nova captura GAO"],
        ["GitHub Classroom", "Prof-Dacio-INFNET/live-profdaciosouza-IgorFMCVO"],
        ["TP3/enunciado PDF", "nao localizados no workspace; criterios nao inventados"],
    ]
    story += [table(limitations, [5.0 * cm, W - 5.0 * cm], font_size=8)]
    story += [P(styles, "10.2 Validacao bidirecional ARM <-> FPGA", "H2SF")]
    story += [P(styles,
        "A ligacao Raspberry physical pin 8 (GPIO14/TXD) -> Tang package pin 46 foi feita com as "
        "placas desenergizadas, camera desconectada e GND compartilhado. O ensaio em SRAM retornou "
        "123 -> 15129, -123 -> 15129 e 32767 -> 1073676289, todos expected = actual, com zero erro "
        "de checksum e zero perda de sequence. Nenhuma Flash foi gravada.", "CalloutSF")]
    story += [P(styles, "10.3 Integridade", "H2SF")]
    integrity = [
        ["Artefato", "SHA-256 / estado"],
        ["safe_field_tp4_validated.fs", "5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181"],
        ["safe_field_tp4_official.fs", "0460826C112FFF69A83E6420BDD28657AE5265EFD5E7D96BE457B9CBA1581A73"],
        ["safe_field_tp4_official_bidirectional.fs", "6E4C460162816C54EE38B11CDA246004C05FE07CEC4C1FA963FDBB36092E172F"],
        ["ZIP academico", "hash publicado em HASHES_SHA256.txt e ZIP_SHA256.txt"],
    ]
    story += [table(integrity, [5.0 * cm, W - 5.0 * cm], font_size=7.2)]
    story += [P(styles, "10.4 Conclusao", "H2SF")]
    story += [P(styles,
        "O TP4 fecha com cadeia fisica de audio e telemetria aprovadas, recursos academicos reais "
        "de DSP e BSRAM comprovados pela ferramenta, 40/40 checks de simulacao, P&R e STA aprovados, "
        "e rotinas AArch64/NEON executadas no Raspberry Pi 4. As duas direcoes UART passaram em "
        "hardware, com CRC e sequence verificados. A rubrica fecha em 22/22 PASS e o video esta "
        "publicado em https://youtu.be/1Ancm5QdG2E. Nao permanece requisito pendente.")]
    story += [P(styles, "Referencias", "H2SF")]
    refs = [
        "1. Sipeed, Tang Nano 4K schematic 3603.",
        "2. GOWIN Semiconductor, GowinSynthesis User Guide SUG550.",
        "3. TDK InvenSense, INMP441 datasheet.",
        "4. Arm, A64 instruction set architecture documentation.",
    ]
    for ref in refs:
        story += [P(styles, ref, "SmallSF")]

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(OUTPUT)


if __name__ == "__main__":
    build_pdf()
