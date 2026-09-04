# SAFE-FIELD TP4 — auditoria pré-submissão

Data: 04/09/2026. Escopo: matriz acadêmica de 22 requisitos e fechamento
solicitado pelo operador.

| Verificação | Status | Evidência objetiva |
|---|---|---|
| PDF presente e abre | PASS | 9 páginas A4 renderizadas e inspecionadas; `docs_tp4/output/pdf/RELATORIO_TECNICO_SAFE_FIELD_TP4.pdf` |
| `/verilog_tp4` presente | PASS | RTL, TBs, constraints, relatórios, bitstreams e evidências |
| `/assembly_tp4` presente | PASS | AArch64, NEON, harness, binário, objdump e logs reais |
| `/docs_tp4` presente | PASS | relatório, arquitetura, gráficos, waveforms e evidências físicas |
| BRAM comprovada | PASS | primitive `SDPB=1`; testbench 5/5 PASS |
| DSP comprovado | PASS | primitive `MULT18X18=1`; testbench 10/10 PASS |
| ARM64 comprovado | PASS | execução real no Raspberry Pi 4; expected = actual |
| NEON inteiro comprovado | PASS | resultado exato igual ao escalar e benchmark real |
| NEON float comprovado | PASS | erro máximo zero e benchmark real |
| FPGA -> ARM comprovado | PASS | 3.264 frames físicos, zero perda e zero erro |
| ARM -> FPGA comprovado | PASS | 3/3 comandos físicos com expected = actual |
| checksum comprovado | PASS | CRC-8/ATM; `checksum_errors=0`; corrupção rejeitada em TB |
| telemetria comprovada | PASS | state, energy, frame counter, flags e sequence recebidos no Pi |
| vídeo registrado | PASS | https://youtu.be/1Ancm5QdG2E |
| GitHub acessível | PASS | https://github.com/IgorFMCVO/safe-field-tp4, repositório público |
| ZIP íntegro | PASS | estrutura aberta e conferida após compressão; manifesto interno SHA-256 |

## Validação bidirecional ARM <-> FPGA

| Input | Expected | Actual |
|---:|---:|---:|
| 123 | 15129 | 15129 |
| -123 | 15129 | 15129 |
| 32767 | 1073676289 | 1073676289 |

- checksum errors: 0;
- sequence losses: 0;
- response errors: 0.

## Integridade

- PDF SHA-256: `957E5DEFF83C7D0AD2DE240A64D09ACE7B096B762745391A643F502EA5DB4409`;
- baseline de áudio SHA-256 preservada:
  `5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`;
- build acadêmico bidirecional SHA-256:
  `6E4C460162816C54EE38B11CDA246004C05FE07CEC4C1FA963FDBB36092E172F`;
- vídeo não está embutido no ZIP;
- nenhum cache, `.git`, `.env`, credencial ou senha foi incluído;
- scan básico por nomes e padrões de secrets: PASS; `gitleaks` não estava
  instalado, fato registrado sem mascaramento.

## Resultado

**AUDITORIA: PASS. RUBRICA: 22/22 PASS.**

Única providência do operador: substituir `PENDENTE_LINK_FINAL` pelo link do
Google Drive antes da submissão na plataforma oficial.
