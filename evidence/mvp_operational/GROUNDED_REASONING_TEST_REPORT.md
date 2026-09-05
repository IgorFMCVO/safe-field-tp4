# SAFE-FIELD — Grounded Reasoning Test Report

Data: 2026-09-05T11:10:22-03:00
Componente: `mvp/operational_intelligence/grounded_reasoning.py`
Fonte de ground truth: `mvp/tests/scenario_ground_truth.json`

## Resultado específico

Comando executado:

```powershell
python -m unittest mvp.tests.test_grounded_reasoning -v
```

Resultado: **PASS — 8/8 testes** em aproximadamente 0,060 s.

| Cenário/caso | Resultado | Evidência verificada |
|---|---:|---|
| A — conflito, quatro locutores | PASS | Papel contextual por turno; hipótese `C 01.155 - FURTO`; citações exatas; divergências `08:00` × `depois de 10:00` e `depois de 10:00` × `antes de 09:00`; `REASSESSMENT_REQUIRED` |
| B — ordem/reidentificação | PASS | Papéis esperados; hipótese `G 01.330 - DESOBEDIÊNCIA`; nenhum conflito temporal inventado |
| C — ameaça ambígua | PASS | Papéis esperados; hipótese `B 01.147 - AMEAÇA`; informação posterior gera revisão explícita; nenhuma divergência temporal inventada |
| Texto sem suporte | PASS | Declaração literal preservada; zero hipótese; zero divergência; papel `UNKNOWN` |
| Alegação sensível na fonte | PASS | Permanece somente citação `CAPTURED`; não vira conclusão de culpa, mentira ou procedimento |
| Isolamento por ocorrência | PASS | Horários de ocorrências distintas não são comparados |
| Replay/idempotência | PASS | Mesmo segmento/evidência retorna mesmos artefatos; rebinding de evidência é rejeitado |
| Segmento multilocutor sem alinhamento | PASS | Nenhum papel único é atribuído indevidamente; todos permanecem `UNKNOWN` |

Todos os fatos emitidos nos três cenários foram verificados como substrings exatas das respectivas transcrições. Os testes também verificaram que cada citação possui offsets válidos, que todo campo estruturado não nulo aparece literalmente na frase, que IDs não colidem e que hipóteses referenciam apenas fatos emitidos.

## Regressão compartilhada

Comando executado:

```powershell
python -m unittest discover -s mvp\tests -p 'test_*.py' -v
```

Resultado: **PASS — 77/77 testes** em 15,168 s.

## Interpretação

O gate desta implementação é PASS para os três cenários sintéticos controlados e para as propriedades fail-safe testadas. Isso não valida compreensão livre de linguagem natural, não valida ASR físico e não transforma hipótese em conclusão jurídica. Naturezas fora da whitelist retornam sem hipótese, deliberadamente.
