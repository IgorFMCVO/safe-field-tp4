# Confirmação do operador — captura 10 ciclos

Data: 04/09/2026, após `stable_cued_fsm_10cycles_04_valid`.

O operador confirmou que falou durante os intervalos de LED aceso, com a
ressalva de que pode ter pulado um ciclo. A relação física foi confirmada por
teste estático imediatamente anterior: GPIO17 LOW = LED apagado; GPIO17 HIGH =
LED aceso.

O GAO exportou nove intervalos HIGH completos; em todos os nove a FSM observou
ACTIVE e, depois, QUIET. Assim, a captura sustenta **9/9 intervalos observáveis
PASS para detecção**, mas não autoriza alegar 10/10 por causa do possível ciclo
pulado e da borda truncada do buffer. A mesma captura registrou 100 transições
de `sound_active` em 99,42 s; portanto a estabilidade da FSM é FAIL, enquanto
a aquisição I2S/áudio permanece PASS com zero frame errors.
