# Recuperação pt-BR — checkpoint experimental não liberado

Data: 2026-09-06. Branch `mvp-occurrence-recovery-ptbr-physical`, origem `74d4d28427215092d30cb217b7fa01c1b269e802`.

MVP STATUS = PARTIAL. Gate B = FAIL. C = NOT_RUN_GATE_B_FAILED.
Não instalar este reasoner como padrão na Raspberry. Nenhuma alteração do TP4,
FPGA, UART física, firmware do relógio ou câmera foi realizada. Não houve teste
acústico nesta recuperação, nem participação do operador.

## Resultado verificável

- ASR CUDA: large-v3 e large-v3-turbo realmente executados; selecionado turbo,
  FP16, português, beam=5, word timestamps e hotwords genéricos permitidos.
- Digital: 1087 palavras, 7 erros normalizados (0,64%); RAW WER 4,23%.
- Registry integrado: 5 IDs, 19/19 retornos, 0 merge pairs, 0 split pairs.
- Papéis: 5/5 INFERRED; nenhuma identidade/papel civil confirmado automaticamente.
- CORAA/MG test: 12 clips, 244 palavras; WER normalizado 15,98%, raw 29,92%.
  Outros 8 clips dev foram usados para seleção; readiness PRELIMINARY.
- Extração: somente 11 fatos operacionais; muitos candidatos recusados. O
  avaliador local estimou precisão 81,82%, recall 37,93% e 2 flags. Essas medidas
  semânticas NÃO estão homologadas: a revisão identificou erros no avaliador.
  Um campo `8 AM` extrapola o horário sem período expresso; não declarar zero
  alucinações. Os artefatos originais de avaliação foram preservados.
- Hipótese: `Observação de conflito verbal`; não corresponde à natureza esperada.
  A primeira hipótese ficou fixada apesar da chegada de novas falas. Não houve
  fallback que injetasse a resposta esperada.
- 24 segmentos completados; 1 job de confirmação falhou com
  `GUIDANCE_NOT_AVAILABLE`. STOP recusado: `PROCESSING_FAILED_REQUIRES_REPLAY`.
  API transporta os estados, mas orientação/finalização/histórico falharam.
- Índice DIAO intacto: 19.129 chunks, 2.161 páginas, hashes de todos os cinco
  artefatos conferidos. Regressão ISOLADA da consulta previamente aprovada em A
  retorna fonte real; não substitui o FAIL do retrieval integrado B.
- 93 testes unitários/integração PASS; `pip check` PASS; 300/300 arquivos da A
  conferidos por hash. 48 requests LLM auditados contra entradas reais.

## Limitações que impedem liberação

Esta branch contém trabalho experimental, não uma correção operacional concluída.
Os três ciclos substanciais foram encerrados. Não foi feita uma quarta rodada
de tuning nem uma execução física C com o gate digital reprovado.

1. `LocalDiscourseReasoner` precisa reavaliar hipóteses quando surge evidência
   material; atualmente conserva a primeira proposta genérica.
2. Campos de confiança/citações do LLM nem sempre atendem ao contrato, derrubando
   recall. O verificador do mesmo modelo também deixa passar extrapolações.
3. Usar outro avaliador ou uma revisão estruturada independente antes de aceitar
   precisão/recall/hallucinations. Citação literal, por si só, não garante campos
   semânticos corretos; actor/time/location ainda podem ser combinados indevidamente.
4. `RecoveryDiarizer` não é separador de overlap. O quality gate mede consistência
   de embeddings, ocupação, duração e clipping, não uma probabilidade calibrada.
5. pyannote community-1 normal/exclusive não executado: acesso gated 401, sem
   token/aceite. Não é motivo para atribuir falha ao hardware.

## Arquivos privados e integridade

Raiz: `C:\SAFE-FIELD\fpga\tp4-audio-inmp441`.

Sessão B final: `sessions/OCC-OPT-DIGITAL-20260906T145405Z`.
Rodada B anterior com falhas de formato:
`sessions/OCC-OPT-DIGITAL-20260906T144707Z`.
Baseline A preservada: `sessions/OCC-SIM-20260906T135545Z`.

Evidência principal: `mvp/evidence/occurrence_recovery/`.
Master mono PCM16/16k de 717,632 segundos: `occurrence_ptbr_master.wav`.
SHA-256: `f1edc5a8b3aa1c6ae02f439482715e851aff741811ea9dfad6c29834dbcfe6f1`.
Semântica: `d80a0048b349182b81661bc12dc3ebe5dc6d76f4589ffdabc9a570156a168b17`.
Mesmas 24 falas, 5 personagens, 29 proposições de referência; nenhum roteiro
reescrito. Vozes Daniel/Maria/pm_alex/pm_santa/pf_dora, todas pt-BR e sem identidade
por simples alteração de pitch. Amplitudes normalizadas sem alterar os brutos.

O diretório `reports` de B contém o manifesto SHA-256, atribuições, fatos,
sequência de comandos, histórico marcado não gerado e minuta marcada NÃO PRONTA.
Não existe WAV, histórico, BO ou evidência de display físico C: não foram fabricados.

## Comandos de execução e reprodução

Executados a partir da raiz acima. Todos os comandos de replay abaixo são
DIGITAIS. Não usar o master como input de qualquer validação física.

```powershell
$env:PYTHONUTF8='1'
$py='.\mvp\evidence\recovery_venv\Scripts\python.exe'
& $py -m mvp.tests.recovery_prepare
& $py -m mvp.tests.recovery_assets_ranged
& $py -m mvp.tests.recovery_ptbr_audio
& $py -m mvp.tests.recovery_asr_benchmark --audio mvp/evidence/occurrence_recovery/occurrence_ptbr_master.wav --output mvp/evidence/occurrence_recovery/benchmark --models mvp/evidence/models --corpus mvp/evidence/occurrence_recovery/corpus
& $py -m mvp.tests.recovery_asr_evaluate
# selected_asr.json congelado aqui; NÃO repetir o selector após ampliar o test.
& $py -m mvp.tests.recovery_asr_benchmark --audio mvp/evidence/occurrence_recovery/occurrence_ptbr_master.wav --output mvp/evidence/occurrence_recovery/benchmark --models mvp/evidence/models --corpus mvp/evidence/occurrence_recovery/corpus --selected-only
& $py -m mvp.tests.recovery_diar_benchmark --audio mvp/evidence/occurrence_recovery/occurrence_ptbr_master.wav --models mvp/evidence/models --output mvp/evidence/occurrence_recovery/diar_benchmark
& $py -m mvp.tests.recovery_infer --benchmark mvp/evidence/occurrence_recovery/benchmark --output mvp/evidence/occurrence_recovery/iteration_2 --models mvp/evidence/models --iteration 2
& $py -m mvp.tests.recovery_llm_launch
$env:SAFE_FIELD_LOCAL_LLM_TOKEN_FILE='C:\SAFE-FIELD\fpga\tp4-audio-inmp441\mvp\evidence\occurrence_recovery\llm_api_key.private'
& $py -m mvp.tests.recovery_replay --audio mvp/evidence/occurrence_recovery/occurrence_ptbr_master.wav --cache mvp/evidence/occurrence_recovery/iteration_2/cache --speed 3
& $py -m mvp.tests.recovery_semantic_evaluate --session sessions/OCC-OPT-DIGITAL-20260906T145405Z
& $py -m mvp.tests.recovery_report --session sessions/OCC-OPT-DIGITAL-20260906T145405Z
& $py -m mvp.tests.recovery_audit --session sessions/OCC-OPT-DIGITAL-20260906T145405Z
& $py -m mvp.tests.recovery_diao_regression
& $py -m unittest discover -s mvp/tests -p 'test_*.py' -v
& $py -m pip check
git diff --check
```

Não reexecutar os comandos sobre evidências congeladas: alguns harnesses geram
artefatos determinísticos no mesmo diretório. Copiar o checkpoint/evidências para
uma área nova antes de reproduzir. `recovery_asr_evaluate` é seleção inicial, não
o relatório final; o relatório final usa a seleção salva sem olhar o test para escolher.

Logs: `asr_benchmark.log`, `asr_selected_validation.log`,
`inference_iteration_1.log`, `inference_iteration_2.log`,
`digital_replay_iteration_2.log`, `digital_replay_iteration_3_run.log`,
`semantic_evaluation*.log`, `regression_final.log`, `diao_regression.log`,
`provenance_audit.log`, `pip_check_final.log`.
Tentativas abortadas/erros também permanecem; ausência de PASS não é ocultada.
Auditoria final inicialmente sinalizou os próprios documentos novos por um
prefixo incorreto no allowlist (`docs/mvp/` em vez do diretório real). O helper
foi corrigido para permitir somente `docs/mvp_operational/occurrence_recovery/`,
com teste que mantém TP4/wearable protegidos e exit code não-zero em FAIL.
Logs anteriores mantidos; ver `provenance_audit_scope_fixed.log` e
`regression_final_scope.log`. Isso não alterou nem repetiu o pipeline B.

## Dependências e privacidade

Ambiente separado `recovery_venv` com torch/torchaudio 2.5.1 CUDA12.4,
transformers 4.48.3, Kokoro 0.9.4; pacotes auxiliares do ambiente anterior são
referenciados por `.pth` privado, sem sobrescrever os originais. Isso não é um
ambiente redistribuível autossuficiente; manifeste as dependências antes de migrar.
Qwen2.5-7B Q4_K_M, llama.cpp b10825 CUDA12.4, API somente loopback com chave local
aleatória em arquivo ignorado. Chave não publicada; teste sem autorização 401.
O primeiro processo de teste local era sem autenticação; foi encerrado e
substituído antes da última execução. Nenhuma porta externa foi exposta.

Modelos, corpus, áudio, dados de ocorrência, índice DIAO, dumps e credenciais
ficam fora do Git. Downloads tiveram travamentos de GET integral; retomada por
HTTP Range com tamanho/hash foi usada, preservando os parciais. Não houve envio
de dados de ocorrência a TTS/ASR/LLM externos.

Fontes e termos: ver os três relatórios anexos. CORAA CC BY-NC-ND4.0 mantido
privado; não foi treinado modelo nem redistribuído o corpus tratado.

## Checkpoint operacional — recuperação de lançamento (2026-09-22)

- Última captura acústica física comprovada: `post_ground_audio_20260913`,
  RAW24 (`safe_field_mvp_raw24_capture.fs`, SHA-256
  `B0B665EBB20DAEAB3C3ABCCDCE96858FA8084DCDB1F9B7587EC5EBC72ECF21F1`),
  programada somente em SRAM; fala humana e tom de 1 kHz foram observados.
- O ensaio posterior `physical_watch_occurrence_20260913` comprova que o Core
  recebeu PCM16 (`UART_PCM16_V1`) em uma ocorrência ativa, mas não preserva o
  comando de programação nem a identidade/hash da imagem SRAM correspondente.
  Seu primeiro erro registrado foi espera pelo START físico do relógio; não há
  evidência de que o playback tenha começado nessa tentativa.
- O estado atual do Core anuncia `UART_PCM16_V1`; a sonda exclusiva de
  2026-09-22 leu zero bytes. Não é seguro substituir a SRAM por uma imagem
  escolhida pelo nome: faltam a imagem/hash, a pinagem e o comando de lançamento
  que associem o ensaio PCM16 ao hardware. Nenhuma reprogramação ou alteração de
  certificado, autenticação, RTL, Flash ou fiação foi feita nesta recuperação.
