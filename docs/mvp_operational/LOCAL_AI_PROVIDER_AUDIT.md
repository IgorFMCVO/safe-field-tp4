# Auditoria dos providers locais de IA

Data: 2026-09-05 (America/Sao_Paulo)

## Resultado

| Componente | Estado nesta sessão | Evidência objetiva |
|---|---|---|
| GPU local | DETECTADA, INFERÊNCIA BLOQUEADA | NVIDIA GeForce RTX 4090 Laptop GPU; o carregamento CUDA falhou explicitamente por ausência de `cublas64_12.dll` |
| ASR pt-BR local | **PASS em CPU** | Faster-Whisper small, CPU/int8, 16/16 WAVs com saída; WER médio da voz nativa pt-BR = 0,0922 |
| Stress ASR com vozes en-US falando português | **FAIL preservado** | WER médio = 0,4241, acima da meta 0,35; não foi mascarado |
| Diarização neural | **BLOCKED** | CRDNN-VAD + ECAPA passou 3/3 single-speaker, mas só 1/3 multi-speaker; provider experimental não integrado |
| Speaker embedding / re-ID neural | **PASS controlado** | ECAPA-TDNN oficial local; 3/3 cenários, re-ID 1,000, 0 merges, 0 splits |
| Falha explícita e segura | PASS | nenhum transcript, speaker ou confiança é fabricado na ausência do provider |
| Envio de dados externo | NÃO | nenhum WAV, ocorrência ou documento foi enviado |

O PASS de ASR é autônomo e baseado em inferência real sobre fixtures TTS offline.
O transporte físico INMP441→FPGA→Raspberry e o lifecycle START/STOP acionado
por utilitário foram validados separadamente; não houve toque físico no wearable
operacional. O ASR físico com fala e a diarização multi-speaker
continuam gates distintos; nenhum resultado sintético é apresentado como fala
capturada no hardware.

## Runtime e modelo auditados

- venv isolada e ignorada pelo Git: `mvp/evidence/local_ai_venv`;
- Faster-Whisper `1.2.1`;
- CTranslate2 `4.8.2`;
- PyTorch/torchaudio CPU `2.8.0` e SpeechBrain `1.0.3`;
- modelo local ignorado: `mvp/evidence/models/faster-whisper-small`;
- 15 arquivos, 486.217.555 bytes;
- SHA-256 de `model.bin`:
  `3E305921506D8872816023E4C273E75D2419FB89B24DA97B4FE7BCE14170D671`;
- modelo ECAPA local ignorado: `mvp/evidence/models/spkrec-ecapa-voxceleb`;
- SHA-256 de `embedding_model.ckpt`:
  `0575CB64845E6B9A10DB9BCB74D5AC32B326B8DC90352671D345E2EE3D0126A2`;
- revisão ECAPA: `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`;
- manifesto canônico do bundle ECAPA:
  `9DC5A428DB0C2A4D5B0DB792FB7C2F99D5FF3B99732E091C286CA2068B879CEF`;
- device/compute validados: `cpu`/`int8`;
- tentativa `cuda`/`float16`: bloqueada por `cublas64_12.dll` ausente;
- nenhum caminho de modelo nem segredo é gravado em código versionado.

O probe padrão, executado no interpretador que hospedará o serviço, é:

```powershell
python -m mvp.operational_intelligence.local_ai_probe
```

O inventário mostra somente se um caminho foi configurado e existe; ele não
imprime o valor da variável. O servidor aceita `--ai-device` e
`--asr-compute-type`; o default validado é CPU/int8.

## Validação ASR real

Comando executado na venv isolada, apontando para o diretório local do modelo:

```powershell
.\mvp\evidence\local_ai_venv\Scripts\python.exe `
  .\mvp\tests\run_local_asr_validation.py `
  --model .\mvp\evidence\models\faster-whisper-small `
  --device cpu --compute-type int8
```

Resultado:

- 16/16 arquivos transcritos, 0 saídas vazias;
- subconjunto da voz nativa pt-BR: WER médio 0,0922 (PASS, meta ≤ 0,25);
- conjunto completo com vozes en-US forçadas a português: WER médio 0,4241
  (FAIL, meta ≤ 0,35);
- tempo médio cold-inclusive: 1.547,8 ms/arquivo; p95 nearest-rank: 2.227,3 ms;
- primeira inferência: 2.227,3 ms; warm mean/p95: 1.502,5/1.780,0 ms;
- fixture esperada usada somente como ground truth, nunca como saída;
- relatório detalhado: `LOCAL_ASR_VALIDATION.md`.

O teste de controles do adapter também permanece reprodutível:

```powershell
python -m mvp.operational_intelligence.local_ai_selftest
```

Resultado: **5/5 PASS** para caminho estritamente local, bloqueio de IDs
remotos/rede, guard offline mesmo após import/sessão Hub e falha explícita.

## Bloqueadores remanescentes

1. Diarização multi-speaker ainda precisa de um modelo validado de mudança de
   locutor/overlap. A composição local tentada foi mantida como evidência FAIL
   (A: 4/6, DER 0,4264; B: 3/4, DER 0,1722; C: 3/3, DER 0,1166), sem integração
   ao runtime. Embedding/re-ID já passou de modo neural controlado.
2. A janela física START→PCM→STOP passou sem erro, mas ASR sobre fala física e o
   wearable operacional novo ainda exigem uma única validação final integrada.
3. A GPU detectada não é utilizável pelo CTranslate2 nesta instalação por falta
   da DLL CUDA citada; CPU/int8 é a configuração realmente validada.

Enquanto esses itens não forem fechados, áudio bruto é preservado e jobs
incompletos permanecem `PROCESSING_PENDING`, sem dados fictícios.
