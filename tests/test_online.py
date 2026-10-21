"""Teste contra o VALIDAR de verdade. Desligado por padrão.

Ligue com ASSINATURA_GOVBR_TESTE_ONLINE=1. Envia só govbr/canario.p7s (texto
fixo, certificado de teste, sem dados pessoais) e confere que a API interna
do portal continua respondendo do jeito que o plugin espera. O GitHub Actions
roda este teste toda semana: se o ITI mudar o portal, o aviso chega antes de
um lote real falhar.
"""

import os

import pytest

from govbr import iti

pytestmark = pytest.mark.skipif(
    os.environ.get("ASSINATURA_GOVBR_TESTE_ONLINE") != "1",
    reason="teste online desligado (ASSINATURA_GOVBR_TESTE_ONLINE=1 para ligar)",
)


def test_api_do_validar_continua_compativel():
    ok, mensagem = iti.testar_api()
    assert ok, mensagem
