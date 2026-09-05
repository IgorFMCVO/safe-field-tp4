# SAFE-FIELD — Grounded Reasoning Provider

## Escopo

`LocalGroundedReasoningProvider` é um `ReasoningProvider` local, determinístico e de mundo fechado. Ele transforma transcrições já atribuídas a locutores em fatos capturados, papéis provisórios, divergências temporais e hipóteses operacionais provisórias. Não realiza chamadas de rede, não contém texto de orientação operacional e não consulta serviços em nuvem.

O provedor não é um decisor jurídico. Ele não determina culpa, veracidade, autoria ou procedimento. A única saída de natureza é uma hipótese com estado `PROPOSED`, ainda sujeita à decisão do policial e ao fluxo separado de consulta à DIAO.

## Invariantes de grounding

1. Cada `Fact.statement` é uma frase literal de `TranscriptSegment.raw_transcript`, sem paráfrase.
2. Cada fato contém `source_segments` e `source_speakers` não vazios.
3. `fact_provenance(fact_id)` devolve a transcrição bruta, a citação literal e os offsets `[start, end)` dessa citação.
4. Campos estruturados (`action`, `object`, `location`, `time`) são substrings literais da mesma frase ou `null`.
5. Fatos de transcrição usam `CAPTURED`: isso significa “declaração capturada”, não “conteúdo externamente comprovado”.
6. IDs são estáveis e únicos no escopo da ocorrência, derivados por SHA-256 de ocorrência, segmento, posição e evidência.
7. Reprocessar o mesmo `segment_id` com a mesma evidência é idempotente; tentar vinculá-lo a outro texto é rejeitado.

## Estado por ocorrência

O estado é particionado por `occurrence_id`. No layout padrão, o identificador é extraído de:

```text
.../<occurrence_id>/segments/<segment>.wav
```

Para outro layout, o chamador deve construir o provedor com `occurrence_id="..."`. `clear_occurrence()` remove somente o estado em memória após o arquivamento. Relatos temporais de ocorrências diferentes nunca são comparados.

## Classificação contextual de papel

Os papéis suportados são:

- `KNOWN_OFFICER`;
- `POSSIBLE_VICTIM`;
- `POSSIBLE_INVOLVED`;
- `POSSIBLE_WITNESS`;
- `REQUESTER`;
- `UNKNOWN`.

A classificação usa apenas palavras da declaração e o histórico contextual do mesmo `speaker_id` na ocorrência. Voz, pitch, frequência fundamental, nome de arquivo e embedding não são usados para inferir função. Quando um segmento contém mais de um locutor, o provedor retorna `UNKNOWN` para todos, pois não há alinhamento palavra–locutor suficiente para uma atribuição segura.

## Divergência temporal

Expressões simples como “às oito horas”, “depois das dez” e “antes das nove” são convertidas em intervalos. Dois intervalos sem interseção, em segmentos diferentes da mesma ocorrência, geram:

```yaml
type: TEMPORAL_DIVERGENCE
status: INFERRED
reassessment_required: true
evidence:
  - fact_id
  - source_segment
  - source_speakers
  - quote
  - time_literal
```

O registro descreve relatos incompatíveis; não classifica qualquer interlocutor como mentiroso.

## Hipóteses permitidas

O provedor opera com whitelist explícita, limitada às naturezas com cobertura real nos cenários e no índice DIAO desta versão:

- `C 01.155 - FURTO`;
- `G 01.330 - DESOBEDIÊNCIA`;
- `B 01.147 - AMEAÇA`.

Uma hipótese só é emitida quando existe evidência textual mínima. Ela referencia apenas `fact_id` já emitidos e todos os segmentos-fonte. Informação posterior temporalmente divergente ou que altere o contexto de ameaça produz nova hipótese/revisão e `REASSESSMENT_REQUIRED`; a hipótese anterior não é substituída silenciosamente.

Texto fora da whitelist continua preservado como declaração capturada, mas produz zero hipótese. Nenhum procedimento é gerado neste componente.

## Integração

```python
from mvp.operational_intelligence.grounded_reasoning import LocalGroundedReasoningProvider

reasoning = LocalGroundedReasoningProvider()
```

O objeto pode ocupar o campo `reasoning` de `PipelineProviders`. Para preservar a separação de estado, a implantação deve manter o layout padrão de sessão ou informar o `occurrence_id` explicitamente.

## Limites honestos

- As regras cobrem português brasileiro e um vocabulário deliberadamente estreito; não substituem um modelo consolidado de extração de informação.
- Não há resolução ampla de correferência, negação complexa, ironia ou eventos que atravessem meia-noite.
- Horários são tratados como intervalos no mesmo dia quando o contexto não fornece data.
- `raw_transcript` herda eventuais erros do ASR; o provedor não corrige silenciosamente o texto.
- Uma frase completa é a unidade persistida. Os campos estruturados são esparsos por segurança.
- O histórico contextual pressupõe que `speaker_id` já tenha sido produzido pelo registro/diarização da ocorrência.
- A confiança é uma estimativa conservadora de suporte textual, não probabilidade jurídica.
- Citações com alegações de culpa ou mentira podem aparecer literalmente como conteúdo capturado do interlocutor; o sistema nunca as promove a conclusão própria.
- O provedor não contém orientação DIAO, não autoriza ação e não elimina a confirmação humana exigida antes do retrieval operacional.
