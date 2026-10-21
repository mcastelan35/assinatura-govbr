---
name: painel
description: Abre o Painel de Assinaturas — métricas de documentos recebidos, validados e gerados, busca de pessoas analisadas, download em lote dos documentos originais e dos relatórios de conformidade (inclusive tudo de uma pessoa) e validação com um clique. Use quando o usuário pedir "abra o painel", "painel de assinaturas", "quantos documentos validamos", "métricas", "buscar quem assinou", "documentos assinados por Fulano", "baixar os relatórios", "baixar tudo de Fulano", "ver as validações", ou quiser conhecer o painel com dados fictícios.
allowed-tools:
  - Bash(uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - PowerShell(uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - Bash(~/.local/bin/uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - PowerShell(& "$env:USERPROFILE\.local\bin\uv.exe" run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
---

# Painel de Assinaturas

**Comando base** (`<cmd>`): `uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py"`. Se o uv não for reconhecido, siga a skill `configurar` (passo 2). Sem configuração (`<cmd> mostrar-config` responde código 3), siga `configurar` antes — ou ofereça o painel de demonstração.

## Abrir

Rode `<cmd> painel` **em segundo plano**. Ele imprime `Painel aberto em: http://127.0.0.1:…/?t=…` e abre o navegador. Passe esse endereço ao usuário como link clicável, caso o navegador não tenha aberto. O painel fica no ar enquanto a página estiver aberta e se encerra sozinho 30 minutos depois de fechada. O endereço tem uma chave (`t=`) que só vale nesta execução: não o compartilhe.

Explique o que dá para fazer, em poucas linhas:
- **Indicadores**: recebidos, aprovados, com ressalvas, sem assinatura, pessoas e arquivos gerados, com filtro de período.
- **Busca**: por nome do documento, nome da pessoa ou dígitos visíveis do CPF (tecla `/`).
- **Documentos**: clique numa linha para ver signatários, integridade (SHA-256) e arquivos; os botões Original e Relatório (ou Mesclado, no modo mesclado) baixam na hora; marque várias linhas para baixar um `.zip`.
- **Pessoas**: todos os documentos assinados por alguém e o botão **Baixar tudo (.zip)**, com os originais e os relatórios do ITI dessa pessoa.
- **Validar novos**: envia ao ITI os documentos que chegaram na pasta de entrada e atualiza o painel.

O arquivo `Painel de Assinaturas.html` na pasta de saída abre direto (inclusive pelo Google Drive para computador, em qualquer máquina da equipe), em modo somente leitura: sem `.zip` e sem validar.

## Demonstração

Sem documentos validados ainda, ou se o usuário quiser conhecer: `<cmd> demo` (em segundo plano). Cria dados fictícios numa pasta temporária, no formato configurado (separado ou mesclado) — nada vai ao ITI — e abre o painel.

## Pela conversa, sem abrir o painel

- **Documentos de uma pessoa**: leia `Validações.csv` da pasta de saída (coluna `signatarios`) e liste os arquivos de `Documentos/` correspondentes.
- **Só atualizar o HTML** da pasta de saída: `<cmd> painel --estatico`.
- **Números rápidos** ("quantos aprovados este mês?"): leia `Validações.csv` da pasta de saída e responda direto.

## Cuidados

- O painel mostra nomes e CPFs mascarados de clientes: não copie esses dados para fora da conversa sem o usuário pedir.
- O painel roda só neste computador (127.0.0.1); para a equipe ver de outra máquina, use o arquivo HTML na pasta compartilhada.
