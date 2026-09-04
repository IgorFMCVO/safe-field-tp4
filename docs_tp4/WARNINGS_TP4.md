# Análise de warnings do build acadêmico

Total no console Gowin: 56 warnings.

| Código | Quantidade | Análise |
|---|---:|---|
| `NL0002` | 1 | hierarquia trivial `rasp_to_tang` achatada; lógica equivalente preservada e testada |
| `PA1001` | 54 | saídas de carry/cascade não utilizadas em somadores e no `MULT18X18`; não são entradas flutuantes nem caminhos funcionais perdidos |
| `PR1014` | 1 | `sys_clk_d` usa rota genérica já conhecida; STA final continua positivo com Fmax 37,778 MHz e zero violações |

Nenhum warning foi suprimido. Os 40 checks de simulação, o pin report, o
resource report e o STA são as evidências de que não houve perda funcional.
