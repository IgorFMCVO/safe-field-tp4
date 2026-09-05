# Especificação do histórico preliminar final

## Saídas

Ao finalizar uma ocorrência, o núcleo gera simultaneamente:

- `reports/HISTORICO_PRELIMINAR.md`, para revisão humana;
- `reports/HISTORICO_PRELIMINAR.json`, para integração e auditoria.

Ambos são marcados como preliminares e sujeitos à revisão policial.

## Conteúdo consolidado

1. identificação, início, fim e estado da ocorrência;
2. timeline append-only;
3. interlocutores, papéis provisórios e confirmações;
4. transcrições brutas e referências aos segmentos WAV;
5. fatos e seus `source_segments`/`source_speakers`;
6. divergências e lacunas informacionais;
7. hipóteses, suporte, contradições e decisões do policial;
8. orientações consultadas e referências documentais;
9. jobs pendentes;
10. narrativa preliminar.

## Regra de não invenção

A narrativa é construída somente a partir do texto dos objetos `Fact` já
persistidos. O gerador não chama LLM, não completa lacunas e não transforma
hipótese em fato. Todo fato exige ao menos um segmento de origem desde a criação.

O Markdown mostra IDs e fontes. O JSON mantém os objetos completos para auditoria.
Orientações extensas não são copiadas: registram-se síntese e metadados de fonte.

## Gate de completude

STOP sempre preserva a gravação, mas **não** publica o histórico final enquanto
existir processamento em andamento ou falho. Um timeout mantém a ocorrência em
`FINALIZATION_PENDING`, sem criar `HISTORICO_PRELIMINAR.md/json`; um novo STOP
continua a espera com as mesmas referências e sem duplicar o fechamento do
áudio. Somente fila drenada e zero falhas autorizam a consolidação.

Falha de provider retorna `PROCESSING_FAILED_REQUIRES_REPLAY`. O WAV, o job
pendente e qualquer `raw_transcript` produzido antes da falha continuam
preservados, mas ausência de processamento nunca é apresentada como histórico
completo. Após replay bem-sucedido, a finalização pode ser retomada.
