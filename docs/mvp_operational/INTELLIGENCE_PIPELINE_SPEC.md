# Especificação do pipeline de inteligência

## Contratos substituíveis

O pacote define cinco abstrações assíncronas:

- `ASRProvider.transcribe(audio_path)`;
- `DiarizationProvider.diarize(audio_path, transcript)`;
- `SpeakerEmbeddingProvider.embed(audio_path, start, end)`;
- `ReasoningProvider.analyze(transcript)`;
- `KnowledgeProvider.retrieve_guidance(hypothesis, facts)`.

Fixtures são permitidas apenas em testes. Uma execução sem provider configurado
falha explicitamente com `PROCESSING_PENDING`, mantendo áudio e job para replay.
Ocorrências reais não são enviadas a serviços externos por padrão.

## Sequência por segmento

1. O segmentador persiste `segment_NNNN.wav` e seu JSON.
2. O job entra na fila sem bloquear a captura.
3. Assim que o ASR retorna, o pipeline grava atomicamente o
   `TranscriptSegment` com `raw_transcript`, confiança, tempos e caminho de
   áudio. Nesse instante `speaker_ids` pode estar vazio.
4. Somente depois dessa persistência a diarização fornece turnos locais; ao
   concluir o vínculo de speakers, o mesmo artefato é atualizado atomicamente.
5. Embeddings são associados ao registry da ocorrência.
6. Reasoning pode produzir papéis provisórios, fatos, divergências, lacunas e
   hipóteses.
7. Fatos entram também no `facts/fact_graph.json`; um mesmo ID com conteúdo
   diferente é rejeitado em vez de sobrescrito.
8. Cada fato e hipótese é validado contra `source_segments`; item sem origem é
   rejeitado.
9. Artefatos e transições são persistidos antes de marcar o job `COMPLETE`.

Os fatos suportam `CAPTURED`, `INFERRED` e `OFFICER_CONFIRMED`. Hipóteses usam
`PROPOSED`, `OFFICER_CONFIRMED`, `OFFICER_REJECTED` e `SUPERSEDED`. Nenhuma
estrutura determina culpa ou classifica alguém como mentiroso.

## Confirmação e orientação

Decisões `CONFIRM`, `REJECT` e `MORE_DATA` também entram na fila. Retrieval de
orientação só ocorre depois de `CONFIRM`. Cada `GuidanceItem` precisa ter pelo
menos uma `KnowledgeSource`; uma orientação sem fonte é rejeitada e permanece
pendente. Esta camada não contém conteúdo operacional embutido.

## Recuperação

Cada erro registra tipo, mensagem, instante e dados do job em `jobs/pending_*`.
Os resultados possíveis são:

- ASR indisponível: `PROCESSING_PENDING`;
- diarização/embedding/IA indisponível após ASR: áudio, `raw_transcript` e job
  são preservados;
- knowledge indisponível: `GUIDANCE_NOT_AVAILABLE`;
- qualquer erro de rastreabilidade: job pendente, sem inserir o fato.

O STOP fecha o último trecho e espera a fila pelo timeout informado. Se houver
timeout, o Core permanece em `STOPPING/FINALIZATION_PENDING`, mantém suas
referências e não cria relatório final; repetir STOP continua a mesma
finalização sem fechar o gravador outra vez. Se houver job falho, o Core informa
`PROCESSING_FAILED_REQUIRES_REPLAY` e também não publica histórico incompleto.
