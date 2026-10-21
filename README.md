# Validador de assinaturas GOV.BR para o Claude Code

> Desenvolvido por **Claude para Advogados** · fale com o desenvolvedor: [@advvilasboas](https://www.instagram.com/advvilasboas/)

Plugin do Claude Code que valida documentos assinados via **GOV.BR** ou **ICP-Brasil** no [VALIDAR do ITI](https://validar.iti.gov.br) e entrega, de forma automática:

- o **Relatório de Conformidade oficial** do ITI, igual ao que o site gera;
- o **Dossiê de Conformidade**: uma capa-resumo (situação, signatários, SHA-256, software do ITI) seguida do relatório oficial;
- o **Painel de Assinaturas**: métricas, busca de pessoas analisadas, downloads em lote dos originais e dos dossiês, e dossiê por pessoa;
- a planilha `Validações.csv` e uma trilha de auditoria com as respostas completas do ITI.

Você coloca os PDFs assinados numa pasta, de preferência no **Google Drive**, e diz **"valide os documentos assinados"**. Só os documentos novos vão ao ITI.

## Instalação

No Claude Code:

```
/plugin marketplace add mcastelan35/assinatura-govbr
/plugin install assinatura-govbr@assinatura-govbr
```

Na próxima conversa, o Claude avisa que falta configurar e faz três perguntas (ou rode `/assinatura-govbr:configurar`):

1. em qual pasta você vai colocar os documentos assinados — o plugin sugere pastas do **Google Drive** (Drive compartilhado do escritório, de preferência) quando o *Google Drive para computador* está instalado;
2. em qual pasta os relatórios e o painel devem ficar;
3. se o relatório sai **separado** ou **mesclado** ao documento.

A ferramenta usa o [uv](https://docs.astral.sh/uv/), que traz o Python e as bibliotecas de PDF sem pedir administrador. Se ele não estiver instalado, o Claude oferece instalar.

Quer ver antes de usar com documentos reais? Diga **"mostre o painel com dados fictícios"**.

## Uso

| Você diz | O que acontece |
|---|---|
| "valide os documentos assinados" | valida os PDFs novos da pasta de entrada |
| "valide este arquivo: C:\…\contrato.pdf" | valida um arquivo avulso |
| "abra o painel de assinaturas" | abre o painel no navegador, com downloads em lote |
| "gere o dossiê de Fulano" | junta num PDF os dossiês de tudo o que a pessoa assinou |
| "agende a validação de hora em hora" | cria uma tarefa agendada no app Claude que valida sozinha o que chegar |
| "valide de novo todos" | revalida, inclusive os já validados |
| "quero o relatório mesclado" | muda o formato (skill `configurar`) |

## O que aparece na pasta de saída

```
Painel de Assinaturas.html    abre direto, em qualquer computador que veja a pasta (somente leitura)
Validações.csv                histórico, abre no Excel
Documentos/
  <nome>.pdf                                   cópia íntegra, com a assinatura válida   (modo separado)
  <nome> - Relatório de Conformidade ITI.pdf   relatório oficial do ITI                 (modo separado)
  <nome> - Dossiê de Conformidade.pdf          capa + [documento] + relatório
Dossiês por pessoa/           gerados pelo painel ou pela conversa
_auditoria/                   respostas do ITI, original enviado e resumo de cada validação
```

### Separado ou mesclado?

- **Separado** (recomendado): a cópia do documento é idêntica ao original e mantém a assinatura digital válida. O relatório e o dossiê ficam ao lado, com o mesmo nome.
- **Mesclado**: um PDF só por documento — capa, cópia do documento e relatório, com marcadores para navegar. Prático para protocolar, mas esse arquivo **não carrega a assinatura digital**, porque qualquer alteração num PDF assinado a invalida. A prova continua no relatório (que traz o SHA-256 do original) e no próprio original, que nunca é alterado.

## Painel de Assinaturas

- **Indicadores** de documentos recebidos, aprovados, com ressalvas e sem assinatura; pessoas analisadas; arquivos gerados; filtro de período.
- **Validações por mês** e composição por situação e por tipo de certificado (GOV.BR ou ICP-Brasil).
- **Busca** por documento, nome ou dígitos visíveis do CPF.
- **Documentos**: detalhes de cada assinatura, integridade (SHA-256), botões de download e seleção múltipla para baixar um `.zip`.
- **Pessoas**: tudo o que cada pessoa assinou e o dossiê da pessoa em um clique.
- **Validar novos**: envia ao ITI os documentos que chegaram na pasta de entrada.

Aberto pelo Claude, o painel roda só neste computador (`127.0.0.1`, protegido por uma chave de acesso). O arquivo `Painel de Assinaturas.html` da pasta de saída mostra as mesmas informações em modo leitura, em qualquer máquina da equipe que veja a pasta pelo Google Drive.

## Validação automática

A skill `agendar` cria uma **tarefa agendada do app Claude para desktop** (por exemplo, de hora em hora em dias úteis) que valida os documentos novos sem ninguém pedir e avisa quando algo sai com ressalvas. A tarefa roda enquanto o app está aberto; se ele estiver fechado no horário, roda quando for aberto.

Com a pasta num Drive compartilhado, vários computadores podem validar: uma trava na pasta de saída impede duas validações ao mesmo tempo, e o registro do que já foi validado é mesclado mesmo quando o Google Drive cria cópias de conflito.

## Pela linha de comando, sem o Claude

```bash
uv run --no-project --python 3.12 --with pypdf --with reportlab validar_govbr.py configurar --entrada "G:\Meu Drive\Assinaturas GOV.BR\A validar" --saida "G:\Meu Drive\Assinaturas GOV.BR\Validados" --modo separado
uv run --no-project --python 3.12 --with pypdf --with reportlab validar_govbr.py validar
uv run --no-project --python 3.12 --with pypdf --with reportlab validar_govbr.py painel
uv run --no-project --python 3.12 --with pypdf --with reportlab validar_govbr.py dossie-pessoa "Fulano de Tal"
uv run --no-project --python 3.12 --with pypdf --with reportlab validar_govbr.py demo
uv run --no-project --python 3.12 --with pypdf --with reportlab validar_govbr.py diagnostico
```

Códigos de saída de `validar`: `0` tudo aprovado, `1` alguma ressalva, `2` erro.

## Testes

```bash
uv run --no-project --python 3.12 --with pytest --with pypdf --with reportlab pytest
```

Os testes usam um ITI simulado, com respostas no formato real e dados fictícios. O GitHub Actions roda tudo a cada envio, no Windows e no Linux, e toda segunda-feira confere a API de verdade com `govbr/canario.p7s` — um texto fixo assinado com certificado de teste, sem dados pessoais. Se o ITI mudar o portal, o teste semanal falha e o GitHub avisa por e-mail, antes de um lote real dar erro. O comando `diagnostico` faz a mesma conferência na hora.

## Privacidade e limites

- Os documentos são **enviados ao VALIDAR do ITI**. Pelos [termos do serviço](https://validar.iti.gov.br) (Portaria ITI nº 22/2023), o ITI descarta o arquivo ao final da validação e mostra o CPF dos signatários mascarado. PDFs sem assinatura digital **não** são enviados.
- Painel, dossiês e planilha ficam na sua pasta de saída: nada é enviado a outro serviço. No Google Drive, as permissões da pasta definem quem vê os dados dos clientes — prefira um Drive compartilhado do escritório.
- A ferramenta usa a interface interna do portal VALIDAR (a mesma que o site usa). Ela não tem documentação oficial nem garantia de estabilidade: se o ITI mudar o site, a validação pode falhar até o plugin ser atualizado. Nesse caso, valide manualmente em https://validar.iti.gov.br. O `diagnostico` e o teste semanal detectam essa mudança enviando apenas um arquivo de teste sem dados pessoais.
- O ITI valida integridade e autoria da assinatura, não o conteúdo do documento. A capa do dossiê é um resumo; o documento oficial é o relatório do ITI que vem logo depois dela.
- A assinatura GOV.BR é **avançada** (Lei 14.063/2020), não qualificada ICP-Brasil; alguns órgãos exigem a qualificada.
- No Windows, o aviso de "configuração pendente" no início da conversa usa o Git Bash, que vem com o Claude Code. Sem ele, rode `/assinatura-govbr:configurar` diretamente.

## Onde fica a configuração

Windows: `%LOCALAPPDATA%\AssinaturaGovBr\config.json` · Mac: `~/Library/Application Support/AssinaturaGovBr/` · Linux: `~/.config/assinatura-govbr/`. Fica fora do plugin, então sobrevive a atualizações e reinstalações.

---

Desenvolvido por **Claude para Advogados**. Dúvidas, sugestões e contato com o desenvolvedor: [instagram.com/advvilasboas](https://www.instagram.com/advvilasboas/).
