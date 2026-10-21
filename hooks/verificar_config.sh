#!/usr/bin/env bash
# SessionStart: se ainda não há configuração neste computador, informa o Claude,
# que então oferece a configuração inicial (/assinatura-govbr:configurar).
# Não depende de Python: precisa rodar mesmo antes de o uv estar instalado.
# Os caminhos espelham pasta_config() em govbr/config.py.

for dir in \
  "${ASSINATURA_GOVBR_CONFIG_DIR:-}" \
  "${LOCALAPPDATA:+$LOCALAPPDATA/AssinaturaGovBr}" \
  "$HOME/Library/Application Support/AssinaturaGovBr" \
  "${XDG_CONFIG_HOME:-$HOME/.config}/assinatura-govbr"; do
  if [ -n "$dir" ] && [ -f "$dir/config.json" ]; then
    exit 0
  fi
done

cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"O plugin assinatura-govbr (validação de assinaturas GOV.BR/ICP-Brasil no VALIDAR do ITI) está instalado, mas ainda não foi configurado neste computador: a pasta onde os documentos assinados serão colocados, a pasta de saída dos relatórios e o formato do relatório (separado ou mesclado ao documento) ainda não foram escolhidos. A configuração inicial é feita pela skill /assinatura-govbr:configurar, que faz essas perguntas ao usuário."}}
JSON
