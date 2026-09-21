# Links de entrega — SAFE-FIELD TP5

**Aluno:** Igor de Freitas Monteiro · **Professor:** Dácio Souza · **Data:** 13/09/2026.

## Vídeo informado pelo autor

[Assistir ao vídeo TP5 no Loom](https://www.loom.com/share/dd65ae3944f94fa897e1196fe789a90b)

O link substitui a pendência de link do fechamento técnico. O vídeo e seu áudio original não foram editados nesta consolidação. Acesso sem login, duração e presença da webcam não foram aferidos por esta etapa de empacotamento. O enunciado solicita hospedagem no Google Drive acadêmico; o link informado pelo autor é do Loom. Conferir a adequação da hospedagem antes de enviar.

## Código e validação

- [Código exato validado](https://github.com/IgorFMCVO/safe-field-tp4/tree/72759423a1e06e3b2eef5721e75679a56ea3a2ee)
- Commit técnico: `72759423a1e06e3b2eef5721e75679a56ea3a2ee`.
- [Branch de documentação TP5](https://github.com/IgorFMCVO/safe-field-tp4/tree/tp5/final-integration-v1)
- [PR #1](https://github.com/IgorFMCVO/safe-field-tp4/pull/1)
- [CI do fechamento técnico — SUCCESS](https://github.com/IgorFMCVO/safe-field-tp4/actions/runs/34782568776)

## Pacote final entregue ao autor nesta consolidação

- `Igor_Monteiro_PB_TP5.ZIP`: 186 arquivos; integridade CRC/SHA-256 e extração em pasta vazia conferidas.
- SHA-256 do ZIP: `A0530172D97610AC2F55DBC3F4368A9373DA9DFA395960B51C2EB14DE11D6899`.
- `RELATORIO_TECNICO_SAFE_FIELD_TP5.pdf`: versão editorial final com nove páginas e link do vídeo.
- SHA-256 do PDF: `561C404E3737D52EC188717F2D7BC523EEC166BDD421DC353B094B3AED4C1F2B`.
- No pacote final, o PDF está em `docs_tp5/output/pdf/RELATORIO_TECNICO_SAFE_FIELD_TP5.pdf`.
- Manifestações internas: `MANIFESTO_ARQUIVOS_SHA256.json` e `SHA256SUMS.txt`.
- O hash do ZIP fica no arquivo externo `ENTREGA_TP5_SHA256.txt`, sem autorreferência.

Os arquivos finais acima foram entregues separadamente ao autor. O PDF de seis páginas ainda versionado no checkpoint técnico deste repositório é o original do Codex; não foi sobrescrito por esta atualização de links. Usar o PDF de nove páginas e o ZIP com os hashes acima para a submissão consolidada.

## Evidências técnicas

- `docs_tp5/evidence/simulation/tp5_wasm_self_checking.log`: cinco testes auto-verificáveis.
- `verilog_tp5/build/safe_field_tp5_final/impl/pnr/`: síntese/P&R/STA e pinout.
- `assembly_tp5/evidence/raspberry_native/`: execução AArch64 nativa, comandos, desempenho e estabilidade.
- `docs_tp5/evidence/audio/INMP441_ACOUSTIC_REVALIDATION_20260913.md`: voz/tom e hashes de origem.
- `docs_tp5/evidence/photos/`: fotografias fornecidas pelo operador.
- `docs_tp5/video_demo/03_WAVEFORM_RAW24_COMMAND.png`: visualização da simulação de coexistência.

Bitstream entregue, sem nova síntese: SHA-256 `2672D28A5C72F980C53447EC7B3DCF7A953828F6336A9B91ADE2DAAC478D2F18`. As terminações CRLF foram recuperadas no export do Git somente após coincidência exata com esse hash previamente validado, conforme registrado no pacote final. Nenhuma nova programação física foi realizada.
