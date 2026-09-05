# Especificação dos providers locais de IA

Implementação: `mvp/operational_intelligence/local_ai.py`.

## Garantias

1. O provider aceita somente caminho local absoluto e existente.
2. Identificadores remotos como `org/model` são rejeitados.
3. `HF_HUB_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY`, `TRANSFORMERS_OFFLINE` e
   `HF_DATASETS_OFFLINE` ficam habilitados durante carga e inferência. Se
   `huggingface_hub` já estiver importado, o guard também atualiza seus flags
   vivos, substitui as sessões HTTP/HTTPS por `OfflineAdapter` e restaura o
   estado anterior ao sair.
4. Pacote, modelo, arquivo ou inferência ausente gera `ProviderUnavailable`
   com causa explícita.
5. Não há fallback para texto de fixture, speaker conhecido ou confiança
   inventada.
6. O áudio é processado por worker via `asyncio.to_thread`, evitando bloquear
   o loop assíncrono de captura.

## Adapters implementados

### `FasterWhisperLocalASRProvider`

- entrada: arquivo de áudio local;
- idioma solicitado ao modelo: `pt`;
- saída do contrato: `ASRResult`, rotulada `pt-BR` quando o modelo detecta
  português;
- confiança: exponencial da média ponderada de `avg_logprob`, limitada a
  `[0, 1]`; não é tratada como probabilidade calibrada;
- download automático: desabilitado por `local_files_only=True` e modo
  offline.

### `PyannoteLocalDiarizationProvider`

- entrada: arquivo de áudio local e transcript apenas por compatibilidade de
  contrato;
- saída: intervalos e speaker labels locais;
- como a anotação pyannote não expõe posterior calibrado por turno, a
  confiança é `0.0`, nunca um valor inventado;
- pipeline deve existir integralmente no disco e resolver suas dependências em
  modo offline.

### `SpeechBrainLocalEmbeddingProvider`

- entrada: intervalo `[start, end]` de arquivo local;
- áudio convertido para mono e 16 kHz antes do encoder;
- saída L2-normalizada;
- modelo SpeechBrain deve estar integralmente disponível no caminho local;
- a referência `pretrained_path` publicada no YAML é sobrescrita pelo caminho
  local auditado;
- `LocalStrategy.NO_LINK` evita cópia/link, enquanto o bloqueio de rede é feito
  separadamente pelo guard offline fail-closed;
- a validação registra hashes de todos os arquivos do bundle, revisão de origem,
  licença e dimensão realmente observada, sem confiar em dimensão hardcoded.

## Configuração local, sem credenciais no Git

```powershell
$env:SAFE_FIELD_ASR_MODEL = 'C:\modelos\faster-whisper-small-pt'
$env:SAFE_FIELD_DIARIZATION_MODEL = 'C:\modelos\pyannote-speaker-diarization'
$env:SAFE_FIELD_EMBEDDING_MODEL = 'C:\modelos\speechbrain-ecapa'
python -m mvp.operational_intelligence.local_ai_probe
```

O código consumidor pode obter providers ou blockers tipados com:

```python
from mvp.operational_intelligence.local_ai import build_local_ai_provider_bundle

local = build_local_ai_provider_bundle(device="cpu", asr_compute_type="int8")
print(local.readiness)
```

O bundle só informa `READY_LOCAL_MODEL` depois de validar a presença dos
pacotes e do caminho. A carga real ainda pode falhar explicitamente se o cache
estiver incompleto, a GPU/runtime for incompatível ou o pipeline tentar
resolver dependência não local.

Nesta estação, Faster-Whisper small e o encoder ECAPA-TDNN foram validados em
CPU. O encoder produziu embeddings L2-normalizados de 192 dimensões e passou
3/3 cenários sintéticos com re-ID 1,000, zero pares false-merge e zero pares
false-split. O bundle local retornou `READY_LOCAL_MODEL`, e o teste de guard
offline passou com Hugging Face previamente importado e sessão previamente
criada. A GPU foi
detectada, mas a carga CUDA falhou por ausência de `cublas64_12.dll`; por isso
CPU/int8, e não CUDA, é o default operacional comprovado. Consulte
`LOCAL_ASR_VALIDATION.md` para WER e
`LOCAL_SPEAKER_REID_VALIDATION.md` para proveniência, métricas e latência reais.

## Critérios antes de habilitar em ocorrência real

- ASR: medir WER/CER em fala pt-BR não usada para configuração;
- diarização: medir DER e erros de merge/split com três ou mais pessoas;
- embedding: medir reidentificação intraocorrência e rejeição de desconhecido;
- executar em áudio real do transporte PCM aprovado, não em telemetria;
- provar que nenhuma chamada de rede ocorre durante inferência;
- conservar `raw.wav`, offsets, hashes e vínculo entre transcript e segmento;
- manter revisão humana para identidades, papéis, hipótese e orientação DIAO.

ASR autônomo já atende o primeiro critério no subconjunto TTS pt-BR; transporte
PCM físico e embedding/re-ID também possuem gates separados PASS. Diarização
multi-speaker e ASR de fala física continuam pendentes; quando uma
dessas etapas não estiver disponível, o estado correto é `PROCESSING_PENDING`,
não um resultado fabricado.
