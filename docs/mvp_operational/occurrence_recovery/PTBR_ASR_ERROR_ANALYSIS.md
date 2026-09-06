# ASR pt-BR — erros sem correção semântica

B runtime RAW WER: 4.23%; NORMALIZED WER: 0.64%.
RAW: tokens por whitespace, preservando caixa/pontuação. Normalized: NFC/minúsculas, pontuação removida, números por extenso pt-BR, pra/pro/pros/tá/tô/cê equivalentes. Não se corrigem nomes nem palavras por sentido.
Contagens B: `{"words": 1087, "errors": 7, "substitution": 4, "deletion": 1, "insertion": 2, "wer": 0.006439742410303588}`.

## Erros de alinhamento digital (referência → reconhecido)

- utterance_006 / CIVIL_02 / replace: `versão` → `aversão`
- utterance_012 / OFFICER_02 / replace: `por que` → `porque`
- utterance_018 / OFFICER_01 / replace: `presenciaram` → `presenciarão`
- utterance_018 / OFFICER_01 / insert: `` → `e aí`
- utterance_020 / OFFICER_02 / replace: `há` → `a`

O alinhamento ilustrativo SequenceMatcher acima não substitui o Levenshtein usado nas contagens. Há nomes próprios e vocabulário operacional; nenhuma substituição é corrigida pelo ground truth.
C: substitution/deletion/insertion/proper name/police vocabulary/colloquialism/acoustic loss = NOT_RUN. Não atribuir erros digitais à acústica nem inventar medidas de C.

ASR roda CUDA FP16. Comparação raw large-v3/beam5 vs turbo/beam5 e A/B de tratamento/beam em benchmark/asr_evaluation.json. Modelo/configuração selecionados em synthetic+MG dev; conjunto sintético não é holdout. Tratamento DC/gain/resample sem denoise; ganho de seleção pequeno, não extrapolar eficácia geral.

## Benchmark de seleção original

| Modelo | Config | Amostra | Clips | RAW WER | NORM WER | ms/clip |
|---|---|---|---:|---:|---:|---:|
| faster-whisper-large-v3 | raw beam1 | mg_dev | 8 | 43.31% | 22.83% | 454.9 |
| faster-whisper-large-v3 | raw beam5 | mg_dev | 8 | 40.94% | 22.83% | 590.7 |
| faster-whisper-large-v3 | speech_asr beam5 | mg_dev | 8 | 40.94% | 22.83% | 588.3 |
| faster-whisper-large-v3 | raw beam1 | synthetic | 5 | 3.88% | 0.00% | 1277.1 |
| faster-whisper-large-v3 | raw beam5 | synthetic | 24 | 3.50% | 0.46% | 1426.4 |
| faster-whisper-large-v3 | speech_asr beam5 | synthetic | 5 | 3.88% | 0.00% | 1660.2 |
| faster-whisper-large-v3 | raw beam5 | mg_test | 12 | 36.07% | 18.44% | 597.5 |
| faster-whisper-large-v3-turbo | raw beam1 | mg_dev | 8 | 37.01% | 22.05% | 192.8 |
| faster-whisper-large-v3-turbo | raw beam5 | mg_dev | 8 | 37.80% | 21.26% | 226.1 |
| faster-whisper-large-v3-turbo | speech_asr beam5 | mg_dev | 8 | 35.43% | 20.47% | 239.2 |
| faster-whisper-large-v3-turbo | raw beam1 | synthetic | 5 | 3.88% | 0.00% | 312.8 |
| faster-whisper-large-v3-turbo | raw beam5 | synthetic | 24 | 4.14% | 0.64% | 413.9 |
| faster-whisper-large-v3-turbo | speech_asr beam5 | synthetic | 5 | 4.31% | 0.00% | 442.5 |
| faster-whisper-large-v3-turbo | raw beam5 | mg_test | 12 | 29.51% | 16.39% | 240.4 |
