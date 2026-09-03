# Auditoria read-only da baseline SAFE-FIELD

Data local: 03/09/2026 (America/Sao_Paulo)

## Projeto localizado

- Baseline imutável: `C:\SAFE-FIELD\fpga\safe_field_tang_blink\safe_field_tang_blink`
- Projeto Gowin: `safe_field_tang_blink.gprj`
- Dispositivo: `GW1NSR-LV4CQN48PC6/I5` / `GW1NSR-4C`
- Top efetivo no último build: `rasp_to_tang`
- Build P&R registrado: 02/09/2026 16:02:39, Gowin V1.9.11.03 Education
- Artefato: `impl\pnr\safe_field_tang_blink.fs`
- Evidência local preexistente: `20260831_151428.mp4`

## Pinagem comprovada na baseline

- `pi_signal`: package pin 40, bank 1, LVCMOS33, VCCIO 3,3 V.
- `led`: package pin 10, bank 0, LVCMOS18, VCCIO 1,8 V.
- O projeto oficial Sipeed Tang Nano 4K confirma `sys_clk` de 27 MHz no package pin 45.
- A baseline não contém nets, LOCs, esquema as-built ou tabela de ligação do INMP441.

## Hashes SHA-256 essenciais antes da cópia

- `rasp_to_tang.v`: `1955AAE8CD8E7BC802A30CB56DD3B98BE140BA741DA014CF2D95DB11543D1E5B`
- `safe_field_tang_blink.cst`: `523A6996C4396D43469C0F1B3158E4A667B5B421F109EA1E74AE1AFB7A49EB4F`
- `safe_field_tang_blink.gprj`: `E308F345DCA01D385EE120C9826665E22E557211F516966E6C4F5341A076F5E2`
- `safe_field_tang_blink.fs`: `37E29CB8FADDA7F84046C2960450287E7307F68175280465D593CB869EFEB9B7`

## Ferramentas localizadas

- Gowin Designer Education: `C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_ide.exe`
- `gw_sh.exe` Education: `C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe`
- Gowin Programmer Education: `C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer.exe`
- Programmer CLI Education: `C:\Gowin\Gowin_V1.9.11.03_Education_x64\Programmer\bin\programmer_cli.exe`
- Também presente: Gowin V1.9.12.03 x64 nos subdiretórios equivalentes de `C:\Gowin`.

## Checkpoint

- Cópia byte a byte verificada: `C:\SAFE-FIELD\fpga\tp4-audio-inmp441`
- Arquivos comparados por SHA-256: 30/30 idênticos antes do desenvolvimento.
- Repositório Git local inicializado na branch `tp4-audio-inmp441`.
- Commit da baseline: `e5f232a` (`checkpoint: preserve physically validated GPIO17 to LED baseline`).

## Revalidação após o build de áudio

Em 03/09/2026, depois da geração do bitstream TP4, os quatro arquivos críticos
da baseline foram novamente lidos e produziram exatamente os mesmos SHA-256
listados acima. O `src/rasp_to_tang.v` no checkpoint também conserva o hash
`1955AAE8CD8E7BC802A30CB56DD3B98BE140BA741DA014CF2D95DB11543D1E5B`.
Nenhum arquivo da baseline física foi alterado ou sobrescrito.
