# SAFE-FIELD — checkpoint do piloto `/demo`

Este checkpoint preserva a delimitação do piloto sem adicionar ao índice as
alterações locais anteriores dos arquivos de produção.

## Hunks do piloto a preservar

- `mvp/operational_intelligence/http_api.py`
  - expõe `information_gaps` no snapshot somente-leitura;
  - projeta transcrição por `speaker_id`, atores, fatos, lacunas,
    divergências, hipóteses a avaliar, histórico e proveniência no `/demo`;
  - apresenta data/hora local e atualiza a lista de ocorrências a cada 3 s.
- `mvp/tests/test_operational_http_api.py`
  - atualiza o contrato de snapshot para incluir `information_gaps`.

## Limites

- Nenhum hunk de wearable, captura, FPGA, UART, autenticação, worker ou
  reasoner faz parte deste checkpoint.
- Nenhum hunk pré-existente de controle do wearable, guidance ou otimização de
  payload deve ser incluído em um commit do piloto sem revisão separada.

## Evidência de validação

- Teste: `python -m unittest mvp.tests.test_operational_http_api` — 15 PASS.
- Sintaxe do JavaScript embutido: `node --check -` — PASS.
- Ocorrência salva validada: `20260922T044435Z_08b5885c`.
  Áudio disponível, uma transcrição, um fato, hipóteses e histórico
  preliminar persistidos.
