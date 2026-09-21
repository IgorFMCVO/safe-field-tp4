# Manifesto de entrega TP5

## Conteúdo principal

- `verilog_tp5/`: RTL, constraints, testbenches, scripts, relatórios Gowin e bitstream final.
- `assembly_tp5/`: Assembly AArch64 modular, biblioteca estática, ELF, testes e evidências nativas/físicas.
- `docs_tp5/`: arquitetura, protocolo, relatório, rubrica, evidências, fotos, roteiro e PDF.
- `README_TP5.md`: ponto inicial da entrega.

## Baseline e rollback

O TP4 congelado não foi alterado. O checkpoint, hashes e manifesto pré-handoff estão em `docs_tp5/evidence/handoff/ROLLBACK_CHECKPOINT.md` e `PRE_TP5_UNTRACKED_SHA256.csv`.

## Exclusões conscientes

O pacote não contém `.git`, caches, `.env`, credenciais, dados policiais, DIAO integral, gravações pessoais nem vídeo. O vídeo é entregue por link após gravação/publicação do operador.

## Proveniência dos resultados

QEMU, PTY e WASM são rotulados como evidência offline. P&R/STA, SRAM/JTAG, Assembly nativo, UART bidirecional, áudio, desempenho e estabilidade estão acompanhados por logs da bancada física real.
