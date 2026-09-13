# Scan básico de segredos — TP5

Data: 13/09/2026  
Escopo: `verilog_tp5`, `assembly_tp5`, `docs_tp5`, `scripts`, `README_TP5.md`.

Padrões pesquisados, com exclusão de binários/imagens/VCD/PDF/ZIP:
senha/password atribuídos, API key, secret, access token e cabeçalhos de chaves
privadas RSA/OpenSSH/EC.

Resultado: `PASS_NO_MATCHES`.

Varredura final adicional em 13/09/2026 pesquisou também o valor numérico da
senha temporária informada durante a bancada. As duas ocorrências encontradas
eram apenas substrings coincidentes dentro de hashes SHA-256 no manifesto de
rollback; nenhum valor de senha, credencial ou segredo está presente.

Arquivos pessoais de áudio, transcrições integrais, modelos, DIAO, `.env`, caches
e credenciais não fazem parte do pacote TP5.
