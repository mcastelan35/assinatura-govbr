# Validador de assinaturas GOV.BR para o Claude Code

Plugin do Claude Code que valida documentos assinados via **GOV.BR** ou **ICP-Brasil** no [VALIDAR do ITI](https://validar.iti.gov.br) e entrega o **Relatório de Conformidade oficial em PDF**, do mesmo jeito que o site entrega, mas de forma automática:

- você coloca os PDFs assinados numa pasta e diz **"valide os documentos assinados"**;
- só os documentos novos vão ao ITI (os já validados são reconhecidos pelo conteúdo, mesmo renomeados);
- o relatório sai **separado** (cópia do documento + `<nome> - Relatório de Conformidade ITI.pdf`) ou **mesclado** ao documento (`<nome> - com Relatório de Conformidade ITI.pdf`), à sua escolha;
- cada validação entra na planilha `Validações.csv` e as respostas completas do ITI ficam em `_auditoria/`.

## Instalação

No Claude Code:

```
/plugin marketplace add mcastelan35/assinatura-govbr
/plugin install assinatura-govbr@assinatura-govbr
```

Na próxima conversa, o Claude avisa que falta configurar e faz três perguntas (ou rode `/assinatura-govbr:configurar`):

1. em qual pasta você vai colocar os documentos assinados;
2. em qual pasta os relatórios devem ser entregues;
3. se o relatório sai separado ou mesclado ao documento.

A ferramenta usa o [uv](https://docs.astral.sh/uv/), que traz o Python e a biblioteca de PDF sem pedir administrador. Se ele não estiver instalado, o Claude oferece instalar.

## Uso

| Você diz | O que acontece |
|---|---|
| "valide os documentos assinados" | valida os PDFs novos da pasta de entrada |
| "valide este arquivo: C:\…\contrato.pdf" | valida um arquivo avulso |
| "valide de novo todos" | revalida, inclusive os já validados |
| "quero o relatório mesclado" | muda o formato (skill `configurar`) |

Resultados possíveis: `APROVADO`, `COM_RESSALVAS` (alguma assinatura indeterminada ou reprovada), `SEM_ASSINATURA_RECONHECIDA`, `SEM_ASSINATURA_OU_CORROMPIDA`, `IGNORADO` (PDF sem assinatura digital, não enviado) e `ERRO` (tentado de novo na próxima vez).

### Pela linha de comando, sem o Claude

```bash
uv run --no-project --python 3.12 --with pypdf validar_govbr.py configurar --entrada "C:\Assinados" --saida "C:\Validados" --modo separado
uv run --no-project --python 3.12 --with pypdf validar_govbr.py validar
uv run --no-project --python 3.12 --with pypdf validar_govbr.py validar "contrato.pdf"
uv run --no-project --python 3.12 --with pypdf validar_govbr.py diagnostico
```

Códigos de saída de `validar`: `0` tudo aprovado, `1` alguma ressalva, `2` erro.

## Separado ou mesclado?

- **Separado** (recomendado): a cópia do documento na pasta de saída é idêntica ao original e mantém a assinatura digital válida; o relatório fica ao lado, com o mesmo nome.
- **Mesclado**: um PDF só, com as páginas do documento seguidas das do relatório e marcadores para navegar. Prático para protocolar, mas esse arquivo novo **não carrega a assinatura digital**, porque qualquer alteração num PDF assinado a invalida. A prova continua no relatório, que traz o SHA-256 do original, e no próprio original, que nunca é alterado.

## Privacidade e limites

- Os documentos são **enviados ao VALIDAR do ITI**. Pelos [termos do serviço](https://validar.iti.gov.br) (Portaria ITI nº 22/2023), o ITI descarta o arquivo ao final da validação e mostra o CPF dos signatários mascarado. PDFs sem assinatura digital **não** são enviados.
- A ferramenta usa a interface interna do portal VALIDAR (a mesma que o site usa). Ela não tem documentação oficial nem garantia de estabilidade: se o ITI mudar o site, a validação pode falhar até o plugin ser atualizado. Nesse caso, valide manualmente em https://validar.iti.gov.br.
- O ITI valida integridade e autoria da assinatura, não o conteúdo do documento.
- A assinatura GOV.BR é **avançada** (Lei 14.063/2020), não qualificada ICP-Brasil; alguns órgãos exigem a qualificada.
- No Windows, o aviso de "configuração pendente" no início da conversa usa o Git Bash, que vem com o Claude Code. Sem ele, rode `/assinatura-govbr:configurar` diretamente.

## Onde ficam as coisas

| O quê | Onde |
|---|---|
| Configuração | Windows: `%LOCALAPPDATA%\AssinaturaGovBr\config.json` · Mac: `~/Library/Application Support/AssinaturaGovBr/` · Linux: `~/.config/assinatura-govbr/` |
| Relatórios e planilha | pasta de saída escolhida |
| Respostas completas do ITI e registro do que já foi validado | `<saída>/_auditoria/` |

A configuração fica fora do plugin, então sobrevive a atualizações e reinstalações.
