# Validação do pacote TP5

Arquivo: `Igor_Monteiro_PB_TP5.ZIP`.

- Construído por `docs_tp5/scripts/build_tp5_zip.ps1` a partir de uma lista explícita de diretórios TP5.
- Todos os membros foram lidos integralmente com `zipfile.ZipFile.testzip()` sem erro.
- Confirmada a presença de `README_TP5.md`, RTL/constraints/bitstream, Assembly/biblioteca/ELF, relatório PDF, manifesto e hashes.
- Confirmada a ausência de `.git`, caches, `node_modules`, `.env`, temporários e vídeo.
- O SHA-256 final é calculado após o último empacotamento e registrado no retorno de fechamento; ele não é embutido no próprio ZIP para evitar autorreferência inválida.
