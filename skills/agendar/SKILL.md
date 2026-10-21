---
name: agendar
description: Agenda a validação automática dos documentos assinados como tarefa do Claude Code — de hora em hora, em horário comercial ou na frequência que o usuário escolher —, para que tudo o que cair na pasta de entrada (inclusive no Google Drive) seja validado sem precisar pedir. Use quando o usuário disser "agende a validação", "valide sozinho", "validação automática", "rode a cada hora", "mude a frequência da validação", "pare a validação automática".
allowed-tools:
  - Bash(uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
  - PowerShell(uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py" *)
---

# Validação automática agendada

A validação automática é uma **tarefa agendada do Claude Code** (app para desktop): no horário marcado, o app abre uma sessão que roda a skill `validar` sozinha e avisa o resultado.

**Comando base** (`<cmd>`): `uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py"`.

## 1. Pré-requisitos

- Rode `<cmd> mostrar-config`. Sem configuração (código 3), siga a skill `configurar` antes: a tarefa usa as pastas e o formato já escolhidos.
- Procure a ferramenta de tarefas agendadas desta sessão (`create_scheduled_task`, do servidor `scheduled-tasks`; se estiver só listada, carregue-a). Ela existe no app Claude para desktop. Se não existir — Claude Code só no terminal, por exemplo —, explique que o agendamento precisa do app para desktop e que, até lá, basta dizer "valide os documentos assinados".

## 2. Frequência

Pergunte com `AskUserQuestion`: **"Com que frequência validar os documentos novos?"**
- "De hora em hora, em dias úteis (8h às 18h)" (recomendado) → cron `0 8-18 * * 1-5`
- "A cada 30 minutos, em dias úteis (8h às 18h)" → `*/30 8-18 * * 1-5`
- "Duas vezes por dia (9h e 14h), em dias úteis" → `0 9,14 * * 1-5`
- O usuário pode descrever outra em "Outro": converta para cron no horário local.

Validação mais frequente que a cada 30 minutos não faz sentido: cada execução abre uma sessão do Claude e, sem documento novo, só confirma que não há nada.

## 3. Criar a tarefa

Antes, liste as tarefas existentes (`list_scheduled_tasks`): se já houver uma com id `validar-assinaturas-govbr`, altere-a com `update_scheduled_task` em vez de criar outra.

Chame `create_scheduled_task` com:
- `taskId`: `validar-assinaturas-govbr`
- `title`: `Validar assinaturas GOV.BR`
- `description`: `Valida no ITI os documentos assinados novos da pasta de entrada`
- `cronExpression`: o da escolha acima
- `prompt` (copie como está):

  > Rotina agendada do plugin assinatura-govbr. Use a skill /assinatura-govbr:validar para validar os documentos novos da pasta de entrada configurada (comando validar, sem arquivo avulso). É uma execução automática: não faça perguntas, não altere a configuração e não leia o conteúdo dos PDFs. Se não houver documento novo, responda apenas: "Nenhum documento novo." Se houver, comece destacando qualquer documento COM_RESSALVAS, SEM_ASSINATURA_RECONHECIDA, SEM_ASSINATURA_OU_CORROMPIDA ou ERRO e depois mostre uma tabela curta (documento, resultado, signatários). Se a validação não rodar porque outra já está em andamento, diga isso em uma linha.

## 4. Explicar ao usuário (poucas linhas)

- A tarefa roda **enquanto o app Claude estiver aberto**; se ele estiver fechado no horário, roda quando for aberto.
- Só documentos novos vão ao ITI. Se uma validação manual ou de outro computador estiver em andamento, a tarefa espera a próxima rodada: a pasta de saída tem uma trava que impede duas validações ao mesmo tempo.
- Na primeira execução o Claude Code pode pedir permissão para rodar a ferramenta; escolher "sempre permitir" evita que as próximas fiquem paradas esperando.
- O resultado aparece na lista de tarefas agendadas do app, e o painel e a planilha `Validações.csv` são atualizados a cada rodada.

## Mudar ou parar

- **Mudar a frequência**: `list_scheduled_tasks` para achar `validar-assinaturas-govbr` e `update_scheduled_task` com o novo cron.
- **Pausar ou excluir**: pela lista de tarefas agendadas do app, ou com `update_scheduled_task` (desativar) / `delete_scheduled_task` — confirme com o usuário antes de excluir.
