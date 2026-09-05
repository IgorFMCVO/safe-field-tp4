# Especificação do Speaker Registry

## Unidade de isolamento

Existe um `SpeakerRegistry` novo para cada `occurrence_id`. Não há busca de
civis entre ocorrências. Um policial conhecido só pode ser marcado por enrollment
ou confirmação explícita; o timbre não determina função, identidade ou conduta.

Cada registro mantém:

```text
speaker_id
prototypes[]
segments[]
confidence
provisional_role
confirmed_role
confirmed_identity
known_officer
match_status
possible_matches[]
```

## Reidentificação

O registry recebe embeddings de um `SpeakerEmbeddingProvider` validado. Não usa
frequência fundamental nem algoritmo biométrico proprietário. A implementação
compara cada observação aos protótipos existentes por similaridade cosseno:

- score `>= 0,82`: reutiliza o speaker e conserva a nova observação como
  protótipo, até o limite configurado;
- score `< 0,65`: cria novo speaker;
- score entre os limites: cria novo registro com
  `SPEAKER_MATCH_UNCERTAIN` e lista candidatos. Nunca funde silenciosamente.

Os limites são parâmetros iniciais, não uma calibração final.

## Caso obrigatório

Para a sequência `S1 → S2 → S3 → S1`, embeddings separáveis devem produzir
três registros. A última observação deve ser associada ao primeiro registro,
sem false split. O teste unitário também comprova que uma observação ambígua não
é mesclada automaticamente.

## Papéis e confirmação

`provisional_role` vem exclusivamente do conteúdo e contexto via
`ReasoningProvider`. `confirmed_role` e `confirmed_identity` só mudam por ação
explícita do policial. A confirmação é registrada na timeline. Os estados
`CAPTURED`, `INFERRED` e `OFFICER_CONFIRMED` permanecem distintos nos modelos.
