import io
import json
import re
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import pytest

from conftest import ASSINANTES, pdf_assinado
from govbr import painel, processo


@pytest.fixture
def saida_validada(pastas, iti_simulado):
    entrada, saida = pastas
    iti_simulado.assinantes = ASSINANTES[:2]
    pdf_assinado(entrada / "Contrato A.pdf", "A")
    pdf_assinado(entrada / "Contrato B.pdf", "B")
    processo.validar_pasta(entrada, processo.Lote(saida), "separado", "portuga", log=lambda *_: None)
    pdf_assinado(entrada / "Chegou depois.pdf", "C")  # fica na fila
    return entrada, saida


def _dados_do_html(texto):
    m = re.search(r'<script id="dados" type="application/json">(.*?)</script>', texto, re.S)
    return json.loads(m.group(1))


def test_coletar(saida_validada):
    entrada, saida = saida_validada
    dados = painel.coletar(saida, entrada)
    assert len(dados["documentos"]) == 2
    assert dados["fila"] == ["Chegou depois.pdf"]
    assert dados["arquivos_gerados"] == 4  # 2 × (cópia + relatório)
    for d in dados["documentos"]:
        assert set(d["arquivos"]) == {"original", "relatorio"}
        assert len(d["assinaturas"]) == 2


def test_html_estatico_embute_dados_validos(saida_validada):
    entrada, saida = saida_validada
    destino = painel.escrever_estatico(saida, entrada)
    texto = destino.read_text(encoding="utf-8")
    assert "__DADOS__" not in texto
    dados = _dados_do_html(texto)
    assert dados["servidor"] is None  # estático: sem chave, somente leitura
    assert dados["credito"].startswith("Desenvolvido por Claude para Advogados")


def test_html_resiste_a_nome_de_arquivo_malicioso():
    dados = {"documentos": [{"arquivo": "</script><script>alert(1)</script>.pdf"}]}
    texto = painel.html(dados)
    assert "</script><script>alert(1)" not in texto
    assert _dados_do_html(texto) == dados


def test_modelo_sozinho_mostra_explicacao():
    modelo = painel.MODELO.read_text(encoding="utf-8")
    assert "__DADOS__" in modelo
    assert "Este arquivo é o modelo, ainda sem dados" in modelo


@pytest.fixture
def servidor(saida_validada):
    entrada, saida = saida_validada
    p = painel.Painel({"saida": str(saida), "entrada": str(entrada), "modo": "separado"})
    ref = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), painel._criar_handler(p, ref))
    ref.append(srv)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, p.token, saida
    srv.shutdown()
    srv.server_close()


def _get(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def _post(url, corpo, cabecalho=True):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          **({"X-Painel": "1"} if cabecalho else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def test_servidor_exige_chave(servidor):
    base, token, _ = servidor
    assert _get(f"{base}/")[0] == 403
    assert _get(f"{base}/?t=errada")[0] == 403
    status, corpo, _ = _get(f"{base}/?t={token}")
    assert status == 200 and _dados_do_html(corpo.decode())["servidor"]["token"] == token


def test_servidor_nao_sai_da_pasta_de_saida(servidor):
    base, token, _ = servidor
    assert _get(f"{base}/f/..%2F..%2Fsegredo.txt?t={token}")[0] == 404
    assert _post(f"{base}/api/zip?t={token}", {"ids": []}, cabecalho=False)[0] == 403


def test_zip_e_download(servidor):
    base, token, _ = servidor
    dados = json.loads(_get(f"{base}/api/dados?t={token}")[1])
    ids = [d["id"] for d in dados["documentos"]]
    status, corpo, cab = _post(f"{base}/api/zip?t={token}", {"ids": ids, "tipos": ["original", "relatorio"]})
    assert status == 200 and "attachment" in cab["Content-Disposition"]
    nomes = zipfile.ZipFile(io.BytesIO(corpo)).namelist()
    assert sorted(nomes) == ["Contrato A - Relatório de Conformidade ITI.pdf", "Contrato A.pdf",
                             "Contrato B - Relatório de Conformidade ITI.pdf", "Contrato B.pdf"]

    rel = dados["documentos"][0]["arquivos"]["relatorio"]
    status, corpo, cab = _get(f"{base}/f/{urllib.request.quote(rel)}?t={token}&baixar=1")
    assert status == 200 and corpo.startswith(b"%PDF") and cab["Content-Type"] == "application/pdf"


def test_zip_de_uma_pessoa_leva_o_nome_dela(servidor):
    base, token, _ = servidor
    dados = json.loads(_get(f"{base}/api/dados?t={token}")[1])
    ids = [d["id"] for d in dados["documentos"]]
    status, _, cab = _post(f"{base}/api/zip?t={token}",
                           {"ids": ids, "tipos": ["original", "relatorio"], "titulo": "José Fictício da Silva"})
    assert status == 200
    assert "Jos%C3%A9%20Fict%C3%ADcio%20da%20Silva%20-%202%20documentos" in cab["Content-Disposition"]


def test_api_de_dossie_por_pessoa_foi_removida(servidor):
    base, token, _ = servidor
    assert _post(f"{base}/api/pessoa?t={token}", {"nome": ASSINANTES[0][0]})[0] == 404
