# Manifesto acadêmico SAFE-FIELD TP4

Aluno: Igor de Freitas Monteiro.  
Hardware real: Raspberry Pi 4 Model B e Tang Nano 4K GW1NSR-4C.  
Data: 04/09/2026.

## Conteúdo

- `/verilog_tp4`: RTL congelado e acadêmico, TBs, constraints, scripts,
  waveforms, `.fs`, síntese, P&R e STA;
- `/assembly_tp4`: AArch64, NEON, harness, Makefile, protocolo, binário ARM64,
  `objdump` e logs reais;
- `/docs_tp4`: relatório, arquitetura, tabelas, gráficos e evidências físicas;
- arquivos de raiz: matriz, checklist, roteiro, links e hashes.

## Integridade e separação

O bitstream oficial de áudio previamente validado mantém SHA-256
`5D8F2D31EF5D0349AC0E52F13AC8A7472FCB1A23103131D13163BB8946F39181`.
O build acadêmico bidirecional é independente e foi programado somente em SRAM,
após a ligação física autorizada, com 3/3 respostas numéricas corretas, zero erro
de checksum e zero perda de sequência. O ZIP acadêmico foi regenerado depois da
validação bidirecional e da gravação do vídeo. O ZIP de engenharia
`SAFE_FIELD_TP4_Igor_de_Freitas_Monteiro.zip` permanece preservado.

Não são incluídos caches, `.git`, credenciais, senha, temporários ou builds
diagnósticos redundantes. Resultados físicos, intermediários relevantes e
warnings permanecem rastreáveis.
