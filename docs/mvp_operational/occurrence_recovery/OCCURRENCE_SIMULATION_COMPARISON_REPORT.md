# Recuperação da ocorrência — A × B × C

Branch: mvp-occurrence-recovery-ptbr-physical. B: `OCC-OPT-DIGITAL-20260906T145405Z`. Gate B: **FAIL**.
C: **NOT_RUN_GATE_B_FAILED**. Nenhum som reproduzido, PCM físico recebido ou relógio físico validado nesta rodada.

| METRIC | BASELINE A ORIGINAL | BASELINE B OPTIMIZED DIGITAL | BASELINE C PHYSICAL ACOUSTIC | DELTA A→B | DELTA B→C |
|---|---|---|---|---|---|
| WER raw | não recalculado | 4.23% | NOT_RUN | não comparável | N/A |
| WER normalized | 41.12% (método original) | 0.64% | NOT_RUN | normalização mudou; não atribuir delta só ao modelo | N/A |
| Speaker count | 8 | 5 | NOT_RUN | -3 | N/A |
| re-ID integrado | 57.89% | 100.00% | NOT_RUN | +42.11 pp | N/A |
| False merge pairs | 0 | 0 | NOT_RUN | 0 | N/A |
| False split pairs | 8 | 0 | NOT_RUN | -8 | N/A |
| Roles | 0/5 | 5/5 | NOT_RUN | +5 | N/A |
| Fact precision | 74.4% lexical | 81.82% semântica estimada | NOT_RUN | métodos diferentes | N/A |
| Fact recall | 48.28% lexical | 37.93% semântica estimada | NOT_RUN | métodos diferentes | N/A |
| Unsupported facts | 32 candidates (não mesma métrica) | 2 | NOT_RUN | não comparável | N/A |
| Hypothesis | POSSÍVEL AMEAÇA | ['Observação de conflito verbal'] | NOT_RUN | FAIL | N/A |
| DIAO | B01.147 / p103 PASS | FAIL — ausência da fonte esperada | NOT_RUN | regressão | N/A |
| Watch | API PASS | transport True / fluxo False | NOT_RUN | sem display físico | N/A |
| History | PASS/PARTIAL | gerado False / aceito False | NOT_RUN | não aprovado | N/A |
| BO | minuta parcial | minuta incompleta / não liberada | NOT_RUN | não aprovado | N/A |
| Reasoning latency | não recalculado | {'n': 24, 'mean_ms': 13533.384012490083, 'p50_ms': 13008.370199997444, 'p95_ms': 20521.577499923296, 'max_ms': 23984.205199987628} | NOT_RUN | não comparável | N/A |

## Por interlocutor

| SPEAKER | TTS VOICE | WORDS | WER DIGITAL | WER PHYSICAL | RE-ID DIGITAL | RE-ID PHYSICAL | ROLE EXPECTED | ROLE PREDICTED |
|---|---|---:|---:|---|---:|---|---|---|
| OFFICER_01 | Microsoft Daniel | 260 | 1.15% | NOT_RUN | 100.00% | NOT_RUN | POLICE_OFFICER | POLICE_OFFICER |
| OFFICER_02 | pm_alex | 306 | 0.98% | NOT_RUN | 100.00% | NOT_RUN | POLICE_OFFICER | POLICE_OFFICER |
| CIVIL_01 | Microsoft Maria | 194 | 0.00% | NOT_RUN | 100.00% | NOT_RUN | POSSIBLE_VICTIM | POSSIBLE_VICTIM |
| CIVIL_02 | pm_santa | 184 | 0.54% | NOT_RUN | 100.00% | NOT_RUN | POSSIBLE_INVOLVED | POSSIBLE_INVOLVED |
| CIVIL_03 | pf_dora | 143 | 0.00% | NOT_RUN | 100.00% | NOT_RUN | WITNESS | WITNESS |

## Gates e limites

```json
{
  "five_speakers": true,
  "reid": true,
  "merges": true,
  "splits": true,
  "asr": true,
  "roles": true,
  "fact_precision": false,
  "fact_recall": false,
  "hallucinations": false,
  "hypothesis": false,
  "diao": false,
  "watch_flow": false,
  "history": false,
  "all_jobs_processed": false
}
```

Três iterações substanciais encerradas. Não executar uma quarta nem iniciar C sem B PASS.
1. CRDNN/ECAPA, vozes pt-BR e quality gate: cauda de 2,37 s sem evidência de consistência recusada; áudio e logs preservados.
2. Janela de 20 s e cauda mínima de 4 s (duas metades de 2 s): registry correto; resposta LLM com Markdown/JSON inválido interrompeu segmentos.
3. Contrato JSON-schema e hipótese restrita a fatos SUPPORTED: execução completada conforme fila abaixo, mas sem aceitação semântica automática.
A hipótese inicial genérica fica fixada e não é revisitada quando chega evidência adicional. Candidatos com confidence=0 ou citação de outro turno são recusados: protege contra promoção indevida, mas derruba recall. Essa combinação é limitação do reasoner, não evidência de defeito no INMP441.

Precisão/recall semânticos são estimativas do mesmo modelo local, NÃO HOMOLOGADAS: a revisão encontrou penalização indevida de campos null e inconsistências na associação de recall. Dois flags automáticos não significam duas alucinações confirmadas; há pelo menos um campo inventado (AM em horário sem período explícito). Ver FACT_EXTRACTION_REPORT.md e as avaliações preservadas. Não foi reavaliado seletivamente até melhorar o resultado.

Fila final: `{"pending": 0, "completed": 24, "failed": 1}`.
Os 24 jobs de segmentos concluíram; o job de confirmação falhou com GUIDANCE_NOT_AVAILABLE e STOP retornou PROCESSING_FAILED_REQUIRES_REPLAY. Por isso não houve histórico do Core nem fluxo completo do relógio.
Não foi alterado o threshold de clustering para forçar cinco pessoas. A comparação K=5 foi exclusivamente diagnóstica; pyannote normal/exclusive indisponível por modelo gated (401, sem token/aceite).
Quality confidence do embedding = consistência de cosseno entre metades, não probabilidade calibrada. Os áudios sintéticos sequenciais não validam overlap/conversação humana em campo.

## Reprodução e preservação

Master: `C:\SAFE-FIELD\fpga\tp4-audio-inmp441\mvp\evidence\occurrence_recovery\occurrence_ptbr_master.wav`; SHA-256 `f1edc5a8b3aa1c6ae02f439482715e851aff741811ea9dfad6c29834dbcfe6f1`.
Semântica congelada SHA-256 `d80a0048b349182b81661bc12dc3ebe5dc6d76f4589ffdabc9a570156a168b17`; duração 717,632 s; mesmas 24 falas e 29 fatos esperados.
Cinco vozes pt-BR, sem pitch-shift como identidade; RMS comparável. Baseline A não reexecutada nem sobrescrita.
TP4, FPGA, pinout, UART, Raspberry, câmera e firmware do wearable não alterados nesta recuperação. C só aceitaria PCM do SerialPCMSource, com injeção direta rejeitada pelo guard testado; isso é teste unitário, não prova física.
Artefatos privados por sessão: `C:\SAFE-FIELD\fpga\tp4-audio-inmp441\sessions\OCC-OPT-DIGITAL-20260906T145405Z\reports`. Evidências/modelos/corpus/senhas não entram no Git.

## Fontes dos componentes

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Kokoro vozes pt-BR](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
- [CORAA oficial](https://github.com/nilc-nlp/CORAA)
- [Qwen local](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF)
- [pyannote gated](https://huggingface.co/pyannote/speaker-diarization-community-1)
