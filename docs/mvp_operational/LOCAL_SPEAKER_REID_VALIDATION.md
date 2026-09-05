# Validação local de speaker embedding / reidentificação

Data: 2026-09-05 (America/Sao_Paulo)

## Resultado do gate

`SPEAKER_EMBEDDING_NEURAL_LOCAL = PASS` em cenários sintéticos controlados.

O runtime é local e isolado: PyTorch/torchaudio CPU 2.8.0, SpeechBrain 1.0.3 e
o checkpoint oficial `speechbrain/spkrec-ecapa-voxceleb` (Apache-2.0). A carga
substitui a referência remota do `hyperparams.yaml` pelo diretório auditado e
usa um guard fail-closed que atualiza tanto `HF_HUB_OFFLINE=1` quanto as
constantes e sessões HTTP já carregadas do Hugging Face. Os adapters HTTP e
HTTPS foram comprovados como `OfflineAdapter`; nenhum áudio ou ocorrência foi
enviado externamente. `LocalStrategy.NO_LINK` é usado apenas para não criar
cópias/links e não é tratado como controle de rede.

Arquivo principal do modelo: `embedding_model.ckpt`, 83.316.686 bytes.
SHA-256: `0575CB64845E6B9A10DB9BCB74D5AC32B326B8DC90352671D345E2EE3D0126A2`.

- revisão Hugging Face resolvida:
  `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`;
- bundle auditado: 10 arquivos, 89.133.738 bytes;
- SHA-256 do manifesto canônico do bundle:
  `9DC5A428DB0C2A4D5B0DB792FB7C2F99D5FF3B99732E091C286CA2068B879CEF`;
- manifesto completo: `mvp/evidence/neural_speaker_reid/model_manifest.json`
  (local e ignorado pelo Git).

## Resultado neural

| Cenário | esperado | detectado | re-ID | pureza | false merges | false splits |
|---|---:|---:|---:|---:|---:|---:|
| A: `OFFICER→S1→S2→S3→OFFICER→S1→S2` | 4 | 4 | 1,000 | 1,000 | 0 | 0 |
| B: `S1→S2→S1→S3→S2` | 3 | 3 | 1,000 | 1,000 | 0 | 0 |
| C: `OFFICER→S1→S2→S1` | 3 | 3 | 1,000 | 1,000 | 0 | 0 |

Os embeddings observados têm 192 dimensões e normalização L2. Na reexecução
final com 16 segmentos, o tempo médio incluindo a carga fria foi 370,405 ms; o
p95 cold-inclusive pelo método nearest-rank foi 2.472,599 ms. A primeira chamada
custou 2.472,599 ms. Removida somente essa carga inicial, a média warm foi
230,259 ms e o p95 warm foi 358,547 ms. O relatório machine-readable completo está em
`mvp/evidence/neural_speaker_reid/report.json`, diretório ignorado pelo Git.

O cenário A é deliberadamente adverso: são quatro personas rotuladas, mas
OFFICER e S3 usam a mesma voz-base SAPI com pitch diferente. A similaridade
0,745 caiu na faixa ambígua de 0,65–0,82;
o sistema criou `SPEAKER_04` com `SPEAKER_MATCH_UNCERTAIN` em vez de fundi-lo
silenciosamente. Reaparecimentos verdadeiros tiveram similaridade mínima 0,861
e foram reidentificados corretamente.

## Limites preservados

- os rótulos são de vozes TTS fictícias e valem apenas dentro da ocorrência;
- o cenário A comprova a política conservadora de incerteza; não equivale a um
  ensaio com quatro vozes-base ou quatro pessoas físicas independentes;
- o sistema não atribui identidade civil e não usa timbre para inferir papel;
- esta validação fecha embedding/re-ID, não diarização multi-speaker;
- `PyannoteLocalDiarizationProvider` continua bloqueado sem pipeline local
  provisionado e deve retornar `PROCESSING_PENDING`.

## Comando reproduzível

```powershell
.\mvp\evidence\local_ai_venv\Scripts\python.exe `
  .\mvp\tests\run_neural_speaker_reid_validation.py `
  --model .\mvp\evidence\models\spkrec-ecapa-voxceleb
```

Resultado: **PASS — 3/3 cenários**, zero pares false-merge, zero pares
false-split, re-ID 1,000. A execução preservou warnings de depreciação do
TorchAudio 2.8/SpeechBrain; eles não afetaram esta inferência, mas exigirão
revisão antes de uma migração para TorchAudio 2.9/TorchCodec.
