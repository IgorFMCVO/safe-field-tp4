# Validação de diarização local

## Resultado

`DIARIZATION = FAIL / BLOCKED_FOR_MULTI_SPEAKER_RUNTIME`

O gate não foi promovido a PASS. O pipeline experimental opera integralmente
local e detectou fala, mas não separou/reidentificou os locutores com estabilidade
nos três cenários controlados. Ele **não está ligado** ao bundle de produção.

## Escopo realmente executado

- áudio: WAV PCM16 mono, TTS fictício, concatenado como um arquivo anônimo por cenário;
- detecção de fala: `speechbrain/vad-crdnn-libriparty`, CRDNN local;
- embeddings: `speechbrain/spkrec-ecapa-voxceleb`, ECAPA local;
- clustering: aglomerativo, métrica cosseno, limiar fixo `0.25`;
- variante adicional: clustering espectral de
  `speechbrain.processing.diarization.Spec_Clust_unorm`;
- speaker count: inferido exclusivamente dos embeddings; nenhum número oracle;
- transcript enviado ao provider: vazio;
- ground truth: usado somente depois da inferência, para calcular métricas;
- sobreposição simultânea de vozes: fora deste teste.

O modelo VAD público e não gated foi baixado uma vez para o diretório ignorado
`mvp/evidence/models/vad-crdnn-libriparty`. A inferência posterior foi executada
com o guard offline fail-closed. Nenhuma credencial foi usada.

## Artefatos auditados

| Bundle | Revisão de origem | SHA-256 do arquivo principal | Auditoria complementar |
|---|---|---|---|
| `speechbrain/vad-crdnn-libriparty` | `c5d5ae4fce161d94c3ab0286e32fb4a041a21a04` | `F378F95E8ABAE056ED46DAEE57884F96AC8F7057D42F92A74A491EBDEB3D7594` | SHA da lista de arquivos: `065F3E0FA6E1617170A5288819D4CA79E068FA8D0A505717D9502905008C78BF` |
| `speechbrain/spkrec-ecapa-voxceleb` | `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` | `0575CB64845E6B9A10DB9BCB74D5AC32B326B8DC90352671D345E2EE3D0126A2` | ver manifesto canônico em `LOCAL_SPEAKER_REID_VALIDATION.md` |

Runtime: SpeechBrain 1.0.3, PyTorch/Torchaudio 2.8.0 CPU e scikit-learn
1.7.2, todos dentro da venv ignorada. O probe de rede verificou
`HF_HUB_OFFLINE`, adaptadores HTTP/HTTPS offline e restauração posterior: PASS.

## Configuração de avaliação registrada

- silêncio entre falas: 0,75 s;
- VAD neural + refinamento de energia: habilitado;
- janela máxima ECAPA: 30 s, cauda mínima 0,5 s;
- distância aglomerativa: 0,25;
- critério DER: no máximo 0,20;
- requisitos adicionais: número correto, todas as falas cobertas, S1 reaparece
  no mesmo cluster, zero false merge e zero false split.

## Resultados multi-speaker

| Cenário | Speakers esperado/detectado | DER | False merge | False split | S1 re-ID | Gate |
|---|---:|---:|---:|---:|---|---|
| A | 4 / 6 | 0,4264 | 1 | 3 | FAIL | FAIL |
| B | 3 / 4 | 0,1722 | 0 | 0 | PASS | FAIL (speaker count) |
| C | 3 / 3 | 0,1166 | 0 | 0 | PASS | PASS |

Cobertura de turnos de referência: A `7/7`, B `5/5`, C `4/4`. Apenas `1/3`
cenários completos passou. O resultado agregado é FAIL.

## Probes single-speaker

Três WAVs independentes, cada um com apenas um locutor sintético, foram enviados
sem labels ao mesmo provider:

| Probe | Speakers esperado/detectado | Cobertura de fala | Resultado |
|---|---:|---:|---|
| A/segment_001 | 1 / 1 | 0,789 | PASS |
| B/segment_001 | 1 / 1 | 0,803 | PASS |
| C/segment_001 | 1 / 1 | 0,890 | PASS |

Isso demonstra suporte ao caso de um locutor, mas não corrige o gate
multi-speaker.

## Tentativas não promovidas

Também foram executadas janelas de 1,5 s e clustering espectral com eigengap ou
K estimado do áudio. O eigengap superestimou os três cenários (`5/4`, `4/3`,
`4/3`) e a configuração espectral mais favorável ainda falhou A e B por merges,
splits e DER. Ajustes exploratórios de pruning (`0,1`, `0,5`, `0,7`) não foram
aceitos como calibração: escolher um limiar depois de observar os mesmos fixtures
seria overfit e não provaria generalização.

## Causa do bloqueio

ECAPA resolve embedding/re-ID quando os limites dos turnos já são conhecidos,
mas CRDNN VAD detecta apenas fala/não-fala. A composição não possui um modelo de
segmentação de mudança de locutor/overlap treinado conjuntamente; por isso
pausas internas e mudanças entre falantes geram fragmentação e associações
instáveis. O provider Pyannote já previsto no projeto exigiria um pipeline local
completo previamente provisionado. Esse bundle não existe no ambiente, e sua
obtenção pode exigir aceite/licença/token externo — não foi contornada nem
simulada.

## Reprodutibilidade

```powershell
& 'mvp/evidence/local_ai_venv/Scripts/python.exe' `
  'mvp/tests/run_local_diarization_validation.py' `
  --vad-model 'mvp/evidence/models/vad-crdnn-libriparty' `
  --embedding-model 'mvp/evidence/models/spkrec-ecapa-voxceleb'
```

O JSON detalhado fica, deliberadamente fora do Git, em
`mvp/evidence/local_diarization/report.json`. Os warnings de depreciação do
Torchaudio/SpeechBrain foram preservados no console e não mudam o FAIL funcional.
