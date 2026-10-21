import json

import pytest

from govbr import iti


def _responder(monkeypatch, *respostas):
    fila = list(respostas)
    chamadas = []

    def falso(url, data, content_type):
        chamadas.append(url)
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(iti, "_request_uma_vez", falso)
    monkeypatch.setattr(iti.time, "sleep", lambda s: None)
    return chamadas


def test_aprovado_devolve_json(monkeypatch, tmp_path):
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF-1.4")
    _responder(monkeypatch, (200, json.dumps({"verifierReport": 1}).encode()))
    assert iti.validar_arquivo(arq) == (200, {"verifierReport": 1})


def test_validacao_parcial_206_usa_campo_json(monkeypatch, tmp_path):
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF-1.4")
    corpo = {"qtds": [10, 40], "json": {"verifierReport": "parcial"}}
    _responder(monkeypatch, (206, json.dumps(corpo).encode()))
    assert iti.validar_arquivo(arq) == (206, {"verifierReport": "parcial"})


def test_406_e_400_nao_sao_erro(monkeypatch, tmp_path):
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF-1.4")
    _responder(monkeypatch, (406, b'{"errorCode": 406, "hash": "x"}'), (400, b"Bad Request"))
    assert iti.validar_arquivo(arq)[0] == 406
    assert iti.validar_arquivo(arq) == (400, {"errorCode": 400})


def test_erro_do_servidor_vira_ErroValidar(monkeypatch, tmp_path):
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF-1.4")
    _responder(monkeypatch, (500, b"<html>"))
    with pytest.raises(iti.ErroValidar, match="HTTP 500"):
        iti.validar_arquivo(arq)


def test_instabilidade_temporaria_e_repetida(monkeypatch, tmp_path):
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"%PDF-1.4")
    chamadas = _responder(
        monkeypatch,
        (503, b""),
        iti.ErroValidar("rede"),
        (200, b'{"ok": true}'),
    )
    assert iti.validar_arquivo(arq) == (200, {"ok": True})
    assert len(chamadas) == 3


def test_envio_inclui_origem_do_portal(monkeypatch):
    """Sem Origin/Referer do portal, o VALIDAR responde 401."""
    assert iti.HEADERS["Origin"] == iti.BASE
    assert iti.HEADERS["Referer"].startswith(iti.BASE)


def test_canario_existe_e_teste_de_api(monkeypatch):
    assert iti.CANARIO.is_file() and iti.CANARIO.stat().st_size > 500
    monkeypatch.setattr(iti, "validar_arquivo", lambda a, d=None: (406, {"errorCode": 406, "hash": "abc"}))
    assert iti.testar_api()[0] is True
    monkeypatch.setattr(iti, "validar_arquivo", lambda a, d=None: (200, {"outra": "coisa"}))
    assert iti.testar_api()[0] is False
