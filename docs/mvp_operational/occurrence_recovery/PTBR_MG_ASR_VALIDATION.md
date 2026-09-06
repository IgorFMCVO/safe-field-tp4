# Validação independente CORAA / Minas Gerais

MG READINESS = PRELIMINARY

CORAA-v1.1, origem nilc-nlp; distribuição HF referida pelo projeto. Metadata pt_br, Minas Gerais, spontaneous speech. 20 clips: 8 dev usados para seleção; 12 test mantidos fora da escolha de modelo/tratamento. Seleção determinística por hash de nome de arquivo, ≥6 palavras; amostra pequena, não estratificada por falante/demografia. Não significa validação de todo sotaque mineiro. Nenhum treinamento realizado.

Licença CC BY-NC-ND 4.0: corpus e áudio tratado somente privados para este estudo; sem redistribuição. Referências/metadados em corpus/selection.json; artefatos tratados separados dos originais.

Configuração congelada: `{"model": "faster-whisper-large-v3-turbo", "variant": "speech_asr", "beam": 5}`. Test final não reabre seleção.

| Split | Clips | RAW WER | NORMALIZED WER | Média ms/clip |
|---|---:|---:|---:|---:|
| mg_dev | 8 | 35.43% | 20.47% | 239.2 |
| mg_test | 12 | 29.92% | 15.98% | 249.0 |

Principais erros: segmentação lexical de fala espontânea, interjeições/hesitações, contrações e palavras pouco claras; pontuação/caixa explicam parte do RAW WER. Nenhum erro é consertado semanticamente na avaliação.

[CORAA oficial e licença](https://github.com/nilc-nlp/CORAA). Resultados por clip: benchmark/final_selected_evaluation.json.
