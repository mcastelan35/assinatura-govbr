---
name: configurar
description: Configuração inicial do validador de assinaturas GOV.BR/ICP-Brasil — verifica a instalação, pergunta em qual pasta os documentos assinados serão colocados, qual a pasta de saída e se o Relatório de Conformidade do ITI sai mesclado ao documento ou em arquivo separado. Use logo depois de instalar o plugin, quando o contexto disser que o plugin assinatura-govbr ainda não foi configurado, ou quando o usuário disser "configura o validador", "muda a pasta", "quero o relatório mesclado/separado", "não está funcionando".
allowed-tools:
  - Bash(uv run --no-project --python 3.12 --with pypdf "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - PowerShell(uv run --no-project --python 3.12 --with pypdf "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - Bash(~/.local/bin/uv run --no-project --python 3.12 --with pypdf "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - PowerShell(& "$env:USERPROFILE\.local\bin\uv.exe" run --no-project --python 3.12 --with pypdf "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
---

# Configuração do validador de assinaturas

Objetivo: numa conversa só, o usuário sai com a ferramenta funcionando e três escolhas feitas — pasta de entrada, pasta de saída e formato do relatório. Fale em linguagem simples, uma etapa por vez, e faça as perguntas com a ferramenta `AskUserQuestion` (botões), quando ela existir na sessão.

**Comando base** (`<cmd>` neste texto): `uv run --no-project --python 3.12 --with pypdf "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py"`.
Ele exige o **uv** (astral.sh), que traz o Python certo e a biblioteca de PDF sem pedir administrador. Logo depois de instalar o uv, ele ainda não está no PATH desta sessão: use o caminho completo — Windows (PowerShell): `& "$env:USERPROFILE\.local\bin\uv.exe" run --no-project --python 3.12 --with pypdf "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" …`; Mac/Linux: `~/.local/bin/uv run …` — ou peça ao usuário para reiniciar o Claude Code. Se o Claude Code pedir permissão para esses comandos, explique que são a mesma ferramenta e sugira "Sim, e não perguntar de novo".

## 1. Diagnóstico

Rode `<cmd> diagnostico`. Resuma em uma ou duas linhas o que está pronto e o que falta.
- Se a resposta for "uv não é reconhecido" (ou "command not found"), faça o passo 2.
- Se já existir configuração, mostre-a e pergunte se o usuário quer mudar algo. Se não quiser, encerre (passo 6).

## 2. Instalar o uv (só se faltar)

Explique que é o instalador oficial do uv (astral.sh), que não precisa de administrador, e só rode depois da confirmação:
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

Depois, repita o diagnóstico com o caminho completo do uv. Na primeira execução o uv baixa o Python 3.12 e a biblioteca pypdf (alguns segundos; uma vez só).

## 3. As três perguntas

Rode `<cmd> sugerir-pastas` para obter as pastas sugeridas (dentro de Documentos) e, num único `AskUserQuestion`, faça as três perguntas:

1. **"Em qual pasta você vai colocar os documentos assinados para validar?"**
   - "Sugerida: `<entrada sugerida>`" (recomendada)
   - "Escolher numa janela"
   - (o usuário pode digitar outro caminho em "Outro")
2. **"Em qual pasta os relatórios devem ser entregues?"**
   - "Sugerida: `<saída sugerida>`" (recomendada)
   - "Escolher numa janela"
3. **"Como você quer o Relatório de Conformidade do ITI?"**
   - "Separado" — na pasta de saída ficam uma cópia intacta do documento assinado e, ao lado, `<nome> - Relatório de Conformidade ITI.pdf`. Recomendado: a cópia mantém a assinatura digital válida.
   - "Mesclado" — um PDF só, `<nome> - com Relatório de Conformidade ITI.pdf`, com as páginas do documento seguidas das do relatório e marcadores para navegar. Prático para protocolar, mas esse arquivo novo **não carrega a assinatura digital** (qualquer alteração a invalida); a prova está no relatório e no documento original, que continua intacto na pasta de entrada.

Para "Escolher numa janela", rode `<cmd> escolher-pasta --titulo "Pasta dos documentos assinados"` (ou "Pasta de saída dos relatórios") com tempo limite longo. A janela do sistema pode abrir atrás de outras; no Windows, procure na barra de tarefas. A saída é o caminho escolhido, ou `CANCELADO`.

Se o usuário digitou um caminho, use-o como veio. As pastas não precisam existir: a ferramenta as cria.

## 4. Salvar

Rode `<cmd> configurar --entrada "ENTRADA" --saida "SAIDA" --modo separado|mesclado`.
- Se a saída avisar que uma pasta "parece sincronizada com a nuvem" (OneDrive, Google Drive, Dropbox…), diga em uma frase que os relatórios trazem nome e parte do CPF dos signatários e pergunte se ele quer manter assim mesmo.
- Subpastas: por padrão só a própria pasta de entrada é lida. Se o usuário organiza por cliente em subpastas, rode também `<cmd> configurar --recursivo`.

## 5. Avisos importantes (diga em poucas linhas)

- Os documentos são **enviados ao VALIDAR do ITI** (serviço público do governo federal) para validação. Segundo os termos do serviço (Portaria ITI nº 22/2023), o ITI descarta o arquivo ao final e mostra o CPF mascarado. PDFs sem assinatura digital **não** são enviados.
- A ferramenta usa a interface interna do portal VALIDAR, que não tem documentação oficial: se o ITI mudar o site, ela pode parar até ser atualizada.
- O documento original na pasta de entrada **nunca é alterado nem movido**.

## 6. Fechar

Se a pasta de saída estiver fora da pasta em que o Claude Code está aberto, diga que o usuário pode digitar `/add-dir "<pasta de saída>"` uma vez, para o Claude ler os resultados sem pedir permissão a cada vez.

Explique o dia a dia em três linhas:
- coloque os PDFs assinados na pasta de entrada e diga **"valide os documentos assinados"** (ou `/assinatura-govbr:validar`);
- só os documentos novos são enviados ao ITI; os já validados são reconhecidos pelo conteúdo, mesmo renomeados;
- cada validação entra na planilha `Validações.csv` da pasta de saída, e as respostas completas do ITI ficam em `_auditoria`.

Pergunte se ele quer testar agora com um documento assinado. Se sim, siga a skill `validar`.
