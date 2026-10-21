---
name: configurar
description: Configuração inicial do validador de assinaturas GOV.BR/ICP-Brasil — verifica a instalação, pergunta em qual pasta os documentos assinados serão colocados (de preferência no Google Drive), qual a pasta de saída e se o Relatório de Conformidade do ITI sai mesclado ao documento ou em arquivo separado. Use logo depois de instalar o plugin, quando o contexto disser que o plugin assinatura-govbr ainda não foi configurado, ou quando o usuário disser "configura o validador", "muda a pasta", "quero usar o Google Drive", "quero o relatório mesclado/separado", "não está funcionando".
allowed-tools:
  - Bash(uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - PowerShell(uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - Bash(~/.local/bin/uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - PowerShell(& "$env:USERPROFILE\.local\bin\uv.exe" run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
---

# Configuração do validador de assinaturas

Objetivo: numa conversa só, o usuário sai com a ferramenta funcionando e três escolhas feitas — pasta de entrada, pasta de saída e formato do relatório. Fale em linguagem simples, uma etapa por vez, e faça as perguntas com a ferramenta `AskUserQuestion` (botões), quando ela existir na sessão.

**Comando base** (`<cmd>` neste texto): `uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py"`.
Ele exige o **uv** (astral.sh), que traz o Python certo e as bibliotecas de PDF sem pedir administrador. Logo depois de instalar o uv, ele ainda não está no PATH desta sessão: use o caminho completo — Windows (PowerShell): `& "$env:USERPROFILE\.local\bin\uv.exe" run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" …`; Mac/Linux: `~/.local/bin/uv run …` — ou peça ao usuário para reiniciar o Claude Code. Se o Claude Code pedir permissão para esses comandos, explique que são a mesma ferramenta e sugira "Sim, e não perguntar de novo".

## 1. Diagnóstico

Rode `<cmd> diagnostico`. Resuma em uma ou duas linhas o que está pronto e o que falta. O diagnóstico confere a API do VALIDAR enviando um arquivo de teste fixo, sem dados pessoais; se ele disser que "o portal pode ter mudado", avise que a validação automática pode falhar até o plugin ser atualizado.
- Se a resposta for "uv não é reconhecido" (ou "command not found"), faça o passo 2.
- Se já existir configuração, mostre-a e pergunte se o usuário quer mudar algo. Se não quiser, encerre (passo 6).

## 2. Instalar o uv (só se faltar)

Explique que é o instalador oficial do uv (astral.sh), que não precisa de administrador, e só rode depois da confirmação:
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

Depois, repita o diagnóstico com o caminho completo do uv. Na primeira execução o uv baixa o Python 3.12 e as bibliotecas pypdf e reportlab (alguns segundos; uma vez só).

## 3. As três perguntas

Rode `<cmd> sugerir-pastas`. A resposta lista, em ordem de preferência, os Drives compartilhados do Google Drive, o Meu Drive e a pasta Documentos, cada um com `entrada` e `saida` sugeridas.

**Recomende o Google Drive** quando ele estiver instalado: os documentos chegam de qualquer computador ou do celular, ficam com backup e o painel abre em qualquer máquina da equipe. Entre os Drives, prefira um **Drive compartilhado** do escritório — os arquivos pertencem ao escritório, não a uma pessoa, e as permissões do Drive controlam quem vê dados de clientes. Se o Drive não estiver instalado, mencione em uma frase que dá para instalar o "Google Drive para computador" depois e usar a pasta Documentos por enquanto.

Num único `AskUserQuestion`, faça as três perguntas:

1. **"Onde você vai colocar os documentos assinados para validar?"** — uma opção por sugestão (rótulo curto como "Drive compartilhado: Escritório", "Meu Drive", "Somente este computador"), a recomendada primeiro, mais "Escolher numa janela". O usuário pode digitar outro caminho em "Outro".
2. **"Onde os relatórios e o painel devem ficar?"** — as mesmas origens, apontando para a `saida` sugerida. Recomende o mesmo lugar escolhido na pergunta 1.
3. **"Como você quer o Relatório de Conformidade do ITI?"**
   - "Separado" (recomendado) — em `Documentos/` ficam a cópia intacta do documento assinado (a assinatura digital continua válida) e, ao lado, o relatório oficial do ITI com o mesmo nome.
   - "Mesclado" — um PDF só por documento: o documento assinado seguido do relatório oficial do ITI, com marcadores para navegar. Prático para protocolar, mas esse arquivo **não carrega a assinatura digital** (qualquer alteração num PDF assinado a invalida); a prova está no relatório, e o original fica intacto na pasta de entrada e em `_auditoria`.

Para "Escolher numa janela", rode `<cmd> escolher-pasta --titulo "Pasta dos documentos assinados"` (ou "Pasta de saída") com tempo limite longo. A janela pode abrir atrás de outras; no Windows, procure na barra de tarefas. A saída é o caminho escolhido, ou `CANCELADO`.

Se o usuário digitou um caminho, use-o como veio. As pastas não precisam existir: a ferramenta as cria.

## 4. Salvar

Rode `<cmd> configurar --entrada "ENTRADA" --saida "SAIDA" --modo separado|mesclado`.
- Se a pasta estiver no Google Drive, lembre em uma frase que os relatórios trazem nome e parte do CPF dos signatários: vale conferir quem tem acesso à pasta. Para outro serviço de nuvem (OneDrive, Dropbox), diga o mesmo.
- Subpastas: por padrão só a própria pasta de entrada é lida. Se o usuário organiza por cliente em subpastas, rode também `<cmd> configurar --recursivo`.

## 5. Avisos importantes (diga em poucas linhas)

- Os documentos são **enviados ao VALIDAR do ITI** (serviço público do governo federal) para validação. Segundo os termos do serviço (Portaria ITI nº 22/2023), o ITI descarta o arquivo ao final e mostra o CPF mascarado. PDFs sem assinatura digital **não** são enviados.
- A ferramenta usa a interface interna do portal VALIDAR, que não tem documentação oficial: se o ITI mudar o site, ela pode parar até ser atualizada.
- O documento original na pasta de entrada **nunca é alterado nem movido**.

## 6. Fechar

Se a pasta de saída estiver fora da pasta em que o Claude Code está aberto, diga que o usuário pode digitar `/add-dir "<pasta de saída>"` uma vez, para o Claude ler os resultados sem pedir permissão a cada vez.

Explique o dia a dia em quatro linhas:
- coloque os PDFs assinados na pasta de entrada e diga **"valide os documentos assinados"**;
- só os documentos novos vão ao ITI; os já validados são reconhecidos pelo conteúdo, mesmo renomeados;
- **"abra o painel de assinaturas"** mostra métricas, busca por pessoa e downloads em lote; o arquivo `Painel de Assinaturas.html` na pasta de saída também abre direto, em modo leitura;
- cada validação entra na planilha `Validações.csv`, e as respostas completas do ITI ficam em `_auditoria`.

Mencione que dá para deixar a validação automática, de hora em hora por exemplo (skill `agendar`).

Ofereça: "Quer ver o painel com dados fictícios antes de usar com documentos reais?" — se sim, rode `<cmd> demo` **em segundo plano** e passe ao usuário o endereço que ele imprimir (`Painel aberto em: …`). Ou, se ele tiver um documento assinado à mão, siga a skill `validar`.

Termine com uma linha de crédito: o plugin foi desenvolvido por **Claude para Advogados**; dúvidas e sugestões: https://www.instagram.com/advvilasboas/
