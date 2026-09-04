# SAFE-FIELD MVP FPGA -> Raspberry bridge

Data: 04/09/2026, fuso `America/Sao_Paulo`.

## Resultado

**FPGA_TO_RASPBERRY_PHYSICAL_BRIDGE = PASS**

O caminho validado fisicamente foi:

`INMP441 -> I2S -> Tang Nano 4K -> UART 115200 8N1 -> Raspberry Pi -> JSONL`

A baseline de áudio `safe_field_tp4_validated.fs` não foi alterada nem
sobrescrita. O bridge usa um build independente e foi carregado somente em
SRAM.

## Evidência física final

Bitstream efetivamente programado:

- arquivo: `build/safe_field_mvp_hw_bridge/impl/pnr/safe_field_mvp_hw_bridge.fs`;
- SHA-256: `2FEE0AE7BFA036DBB1F97EB6CC06A3D2A8FBC8CDD7BAE8E139F450D6E298A963`;
- dispositivo detectado por JTAG: `GW1NSR-4C`, ID `0x0100981B`;
- operação: SRAM Program, índice 2, 2,5 MHz;
- resultado Programmer: 100%, status `0x0003F020`, user code `0x00004B9F`;
- Flash: não utilizada.

Na captura final solicitada ao operador, o Raspberry recebeu 3.264 mensagens
entre 15:24:03 e 15:24:22 -03:

| Medida | Valor |
|---|---:|
| sequência | 62034..65297 |
| perdas/descontinuidades de sequência | 0 |
| avanço inválido de `frame_counter` | 0 |
| incremento por mensagem | 256 frames |
| energia mínima/máxima/média | 775 / 25.829 / 6.020,73 |
| flags observadas | `0x04` somente |
| transição física | `QUIET -> ACTIVE -> QUIET` |

Segmentos observados:

| Estado | Mensagens | Energia média | Pico |
|---|---:|---:|---:|
| QUIET inicial | 902 | 5.028,64 | 24.651 |
| ACTIVE | 414 | 6.413,49 | 23.302 |
| QUIET final | 1.948 | 6.396,64 | 25.829 |

O critério do bridge é a entrega íntegra do evento digital da FSM, não uma nova
calibração acústica. A calibração e a aquisição I2S permanecem congeladas como
resultado do TP4.

Arquivos brutos:

- `evidence/mvp_hw_bridge/physical/raspberry_evidence/physical_voice_final_20260904T152402.jsonl`;
- `evidence/mvp_hw_bridge/physical/raspberry_evidence/physical_voice_final_20260904T152402.log`;
- `evidence/mvp_hw_bridge/physical/sram_program.log`;
- `evidence/mvp_hw_bridge/physical/jtag_scan_ft2ch.log`.

## Raspberry

- host: Raspberry Pi 4 Model B Rev 1.5, Debian 13, AArch64;
- `serial0 -> ttyS0`;
- GPIO14/GPIO15 em ALT5 (`TXD1`/`RXD1`);
- console serial removido; console `tty1` preservado;
- `enable_uart=1`;
- usuário integrante de `dialout`;
- `python3-serial` instalado;
- configuração anterior preservada em backups timestamped em `/boot/firmware/`;
- senha não foi gravada em arquivo ou evidência.

## Protocolo e parser

O protocolo v1 contém sync, versão, sequence number, FSM, energia,
`frame_counter`, flags e CRC-8. A validação no Raspberry confirmou:

- frames válidos QUIET/ACTIVE;
- CRC inválido rejeitado;
- perda de sequência detectada;
- fragmento truncado retido até completar;
- console e JSONL.

## SAFE-FIELD core

O serviço mínimo em `raspberry/safe_field_core/` passou 6/6 testes locais e
6/6 no Raspberry. Em execução física ele:

- criou a sessão `20260904T182058Z_f31005b8`;
- ingeriu 624 eventos FPGA reais;
- registrou timeline e estado `AUDIO_QUIET`;
- retornou `CAMERA_NOT_CONNECTED` com HTTP 409 e não criou JPEG falso;
- encerrou a ocorrência com `ended_at` e `OCCURRENCE_FINISHED`.

Evidência: `evidence/mvp_hw_bridge/physical/raspberry_evidence/core_physical_bundle_20260904T152056/`.

## Pinout físico do bridge

| Origem | Destino | Função |
|---|---|---|
| Tang package pin 39, P7 posição 6 | Raspberry physical pin 10, GPIO15/RXD0 | UART TX -> RX |
| Tang GND | Raspberry GND | referência elétrica comum |

Os pins 40/41/42/43/45/10 e a câmera desconectada foram preservados.
