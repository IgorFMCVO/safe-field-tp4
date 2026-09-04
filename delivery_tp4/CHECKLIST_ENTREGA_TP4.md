# Checklist final — SAFE-FIELD TP4

## Concluído

- [x] baseline física Raspberry GPIO17 -> Tang -> LED preservada;
- [x] pinout 40/41/42/43/45/10 documentado;
- [x] clock I2S 2,700 MHz / WS 42,1875 kHz / 64 clocks por frame;
- [x] receptor I2S LEFT 24-bit signed e `sample_valid`;
- [x] magnitude/energia, janela e FSM com histerese;
- [x] voz e palmas capturadas fisicamente;
- [x] samples reais não-zero e `frame_errors=0`;
- [x] aquisição contínua de 99,42 s;
- [x] testbenches auto-verificáveis PASS;
- [x] síntese PASS;
- [x] Place & Route PASS;
- [x] STA PASS, zero endpoints violados;
- [x] warnings finais identificados e explicados;
- [x] `.fs` final independente e SHA-256 confirmado;
- [x] logs, GAO, CSVs, gráficos e relatórios preservados;
- [x] causa raiz dos contatos 41/43 registrada;
- [x] bridge FPGA->Raspberry validado fisicamente e separado do TP4;
- [x] manifesto e hashes do pacote gerados.

## Pendente ou residual — sem ocultação

- [ ] rubricagem formal item a item: o enunciado/rubrica oficial não foi
  encontrado em `C:\SAFE-FIELD`; não foi inventado;
- [ ] estabilidade FSM final em nova captura GAO: regressões PASS, mas a última
  iteração `M=82` não teve recaptura física, portanto permanece residual;
- [ ] validação de câmera UVC física: câmera desconectada e fora do escopo do
  TP4 de áudio; scaffold retorna corretamente `CAMERA_NOT_CONNECTED`;
- [ ] itens futuros PCM, gravação, transcrição, fatos/atores/divergências,
  interface e wearable físico não pertencem a este TP4.

## Verificação de integridade

Execute no PowerShell, a partir da raiz extraída:

```powershell
Get-Content .\HASHES_SHA256.txt
Get-FileHash -Algorithm SHA256 .\bitstream\safe_field_tp4_validated.fs
```

O segundo comando deve retornar
`5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`.
