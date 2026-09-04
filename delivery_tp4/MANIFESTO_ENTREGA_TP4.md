# Manifesto da entrega SAFE-FIELD TP4

## Escopo

Este pacote é uma fotografia imutável dos artefatos acadêmicos relevantes do
TP4 de Sistemas Digitais Embarcados. O áudio validado permanece congelado; o
bridge UART/Raspberry é incluído em `supplemental_mvp/` como evolução posterior
e não substitui o bitstream oficial do TP4.

## Estrutura

| Diretório/arquivo | Conteúdo |
|---|---|
| `bitstream/` | `.fs` final validado do TP4 |
| `rtl/` | RTL do clock I2S, receptor, energia, FSM, integração e constraints |
| `testbenches/` | testes auto-verificáveis e regressões de capturas físicas |
| `scripts/` | scripts de build, simulação e análise |
| `gowin_reports/` | síntese, P&R, pinout, recursos e STA do build final |
| `evidence/` | logs, GAO, CSVs, JSONs, gráficos e confirmações físicas preservadas |
| `media/` | registro audiovisual existente da baseline GPIO17 |
| `docs/` | aceitação, status, pinout, arquitetura e reprodução |
| `supplemental_mvp/` | FPGA->Raspberry, core, câmera e contrato wearable posteriores ao TP4 |
| `HASHES_SHA256.txt` | SHA-256 de todos os demais arquivos do conteúdo |

## Evidência principal

- alimentação INMP441 3,3 V: PASS informado pelo operador;
- SCK 2,700 MHz e WS 42,1875 kHz: PASS;
- SD e samples LEFT signed/non-zero: PASS após correção dos contatos 41/43;
- voz: RMS 4,99 vezes o silêncio;
- palmas: três eventos temporais detectados;
- `frame_errors`: zero;
- aquisição contínua: 99,42 s;
- GPIO17 LOW/HIGH/LOW: PASS e restaurado a LOW;
- síntese, P&R e STA: PASS;
- bitstream final: hash fixado no README.

## Rastreabilidade de resultados invalidados ou residuais

Os arquivos de estímulos de tom e microfone-testemunha foram preservados por
rastreabilidade, mas não são usados como prova acústica porque não houve
confirmação de emissão física. O diagnóstico anterior de microfone defeituoso
foi invalidado depois da correção dos contatos dos pins 41 e 43.

A iteração final da FSM reduziu 100 transições para 7 em replay e removeu
reversões menores que 500 ms. Como não houve uma nova captura GAO após o último
ajuste, a estabilidade final é marcada `RESIDUAL`, não PASS físico.

## Exclusões deliberadas

Não foram incluídos `.git`, caches, `node_modules`, `__pycache__`, credenciais,
senhas, temporários de ferramentas nem a coleção completa de builds
diagnósticos redundantes. Os logs e dados físicos relevantes foram mantidos.
