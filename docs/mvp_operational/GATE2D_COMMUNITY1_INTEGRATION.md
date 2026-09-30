# SAFE-FIELD — Incremento 2 / Gate 2D

## Resultado

`GATE_2D = PASS`

Community-1 foi integrado ao worker por um adaptador isolado, explícito e
reversível. O `RecoveryDiarizer` permanece disponível sem reversão de commit.
Nenhuma captura física foi iniciada neste gate.

## Interface e fluxo

- Interface canônica: `DiarizationEngine.diarize(audio, metadata) -> DiarizationResult` em
  `mvp/operational_intelligence/diarization_engines.py`.
- Implementações: `Community1DiarizerAdapter` e `RecoveryDiarizerAdapter`.
- Compatibilidade com o pipeline existente: `DiarizationProviderBridge` converte somente
  os turns locais ao contrato legado. `local_SPEAKER_*` não é identidade nem papel.
- Reidentificação: ECAPA existente permanece separado; score, threshold, margem e decisão
  continuam pertencendo ao `SpeakerRegistry`. Observação insuficiente permanece
  `UNVERIFIED` e não bloqueia o reasoner.
- Qualidade: Community-1 não publica posterior calibrado. O resultado canônico mantém
  `confidence=null`; o `0.0` no turn legado é apenas sentinel de transporte e nunca é
  usado como qualidade global. A qualidade de reidentificação vem da consistência ECAPA.
- Seleção: `DIARIZATION_ENGINE=community1`; rollback: `DIARIZATION_ENGINE=recovery`.

## Runtime offline e fixação

- Modelo: `pyannote/speaker-diarization-community-1`.
- Revisão: `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`.
- `pyannote.audio`: 4.0.7; `torch`: 2.14.0+cpu; device: CPU.
- Cache: `C:\SAFE-FIELD\_checkpoints\gate2c_ab_20260930T002124Z_3a68721c\community1_cache`.
- `config.yaml`: `5CE2BFA9A938DC132CEC1172592D65173CBB8F444EA1E4133F10F9391DE155BE`.
- embedding: `6F10FF60898A1D185FA22E1D11E0BFA8A92EFEC811F11BCA48CB8CAFEBEFD929`.
- segmentation: `7AD24338D844FB95985486EB1A464E32D229F6D7A03C9ABE60F978BACF3F816E`.
- Runtime remove variáveis de token herdadas, fixa `HF_HUB_OFFLINE=1` e
  `TRANSFORMERS_OFFLINE=1`, valida revisão/hash antes do load e usa `token=False`.
- Cache ausente ou divergente falha explicitamente antes de iniciar inferência; não há
  download nem fallback silencioso durante ocorrência.

O modelo fica em um subprocesso JSONL persistente. O processo é carregado uma vez por
worker e reutilizado por capturas subsequentes. O WAV `CAPTURED` é somente leitura; uma
conversão para 16 kHz ocorre em memória dentro do runtime.

## Benchmark real offline

Fonte: os dois WAVs persistidos do caso histórico
`20260930T002124Z_3a68721c`. O snapshot observado não é tratado como ground truth humana.

| Métrica | Valor |
|---|---:|
| cold load desta execução (cache quente do SO) | 5.809 s |
| warm 1 | 4.154 s |
| warm 2 | 2.570 s |
| model_load_count após duas capturas | 1 |
| cap1 speakers / turns | 2 / 4 |
| cap2 speakers / turns | 2 / 2 |
| source sample rate | 21.094 Hz (valor inteiro no WAV persistido) |
| diarization sample rate | 16.000 Hz |
| GPU memory | 0 MiB (runtime CPU) |
| WAVs originais preservados | SIM; SHA-256 antes/depois idênticos |

O cold load inicial observado no Gate 2C foi 43.855 s; a medição acima é a nova
inicialização com arquivos já em cache do sistema operacional. O runtime não foi
recarregado entre warm 1 e warm 2.

Evidência de benchmark:
`C:\SAFE-FIELD\_checkpoints\gate2d_community1_integration\gate2d_runtime_benchmark.json`.

## Cross-capture

O Gate 2C já mediu, sem escrever no registry:

- melhor associação presumida PM: 0.7833; margem 0.7246;
- melhor associação presumida Fernanda: 0.4986; margem 0.5199.

Esses valores não promovem identidade. A segunda observação fica `UNVERIFIED` por não
atingir o threshold vigente; nenhum threshold foi reduzido neste gate.

## Testes e reversibilidade

- Contrato A–H: 8/8 PASS.
- Composição/feature flag: 3/3 PASS.
- Regressão dirigida (adaptadores, worker, transporte, sample-rate): 52/52 PASS.
- Compatibilidade reasoner/unverified: 15/15 PASS.
- Regressão do registry/reasoner: 11/11 PASS.
- Processo implantado: bearer válido 200 e ausência de bearer 401.
- Sequência real de reinício:
  `community1 (PASS) -> recovery (PASS) -> community1 (PASS)`.
- O processo final usa Community-1, revisão fixada, offline, `model_load_count=1`.

Evidência da sequência:
`C:\SAFE-FIELD\_checkpoints\gate2d_community1_integration\deploy\restart_sequence.json`.

## Estado final

- Worker: READY, `DIARIZATION_ENGINE=community1`, autenticação preservada.
- Core Raspberry: `STANDBY`, sem `occurrence_id`, sem captura ativa.
- Recovery: disponível via `-DiarizationEngine recovery` no mesmo launcher.
- Reasoner: contrato existente preservado; identidade persistente ausente/insuficiente
  não impede análise e permanece explicitamente não verificada.

## Arquivos do Gate 2D

- `mvp/operational_intelligence/diarization_engines.py`
- `mvp/operational_intelligence/community1_runtime.py`
- `mvp/razer_worker_service.py`
- `scripts/start_razer_worker_hidden.ps1`
- `mvp/tests/test_diarization_engines.py`
- `mvp/tests/test_gate2d_worker_composition.py`
- `docs/mvp_operational/GATE2D_COMMUNITY1_INTEGRATION.md`
- `docs/mvp_operational/GATE2D_COMMUNITY1_INTEGRATION_TESTS.json`
