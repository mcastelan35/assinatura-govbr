import csv
import json
import os
import time

import pytest
from pypdf import PdfReader

from conftest import ASSINANTES, pdf_assinado, pdf_simples
from govbr import iti, processo


def _lote(saida):
    return processo.Lote(saida)


# ---------------------------------------------------------------- nomes e caminhos


def test_nome_arquivo_remove_caracteres_proibidos_e_limita():
    assert processo.nome_arquivo('Contrato: "A/B" <final>?') == "Contrato_ _A_B_ _final__"
    assert len(processo.nome_arquivo("x" * 500)) == processo.LIMITE_NOME
    assert processo.nome_arquivo("   ") == "documento"


def test_pior_caminho_cabe_no_limite_do_windows():
    base = r"G:\Drives compartilhados\Escritorio Vilas Boas\Assinaturas GOV.BR\Validados\Documentos" + "\\"
    pior = (base + processo.nome_arquivo("x" * 500)
            + f" - {processo.NOME_RELATORIO} (SEM ASSINATURA OU CORROMPIDA) (2).pdf")
    assert len(pior) < 260


def test_prefiltro_reconhece_pdf_assinado(tmp_path):
    assinado = pdf_assinado(tmp_path / "a.pdf")
    simples = tmp_path / "b.pdf"
    simples.write_bytes(pdf_simples())
    assert processo.pdf_tem_assinatura(assinado)
    assert not processo.pdf_tem_assinatura(simples)


# ---------------------------------------------------------------- validação em lote


def test_lote_separado(pastas, iti_simulado):
    entrada, saida = pastas
    doc = pdf_assinado(entrada / "Procuração Teste_assinado.pdf")
    (entrada / "minuta.pdf").write_bytes(pdf_simples("minuta"))

    linhas = processo.validar_pasta(entrada, _lote(saida), "separado", "portuga", log=lambda *_: None)

    resultados = {l["arquivo"]: l["resultado"] for l in linhas}
    assert resultados == {"Procuração Teste_assinado.pdf": "APROVADO", "minuta.pdf": "IGNORADO"}
    assert iti_simulado.envios == ["Procuração Teste_assinado.pdf"]  # a minuta não vai ao ITI
    docs = saida / processo.PASTA_DOCUMENTOS
    copia = docs / "Procuração Teste_assinado.pdf"
    assert copia.read_bytes() == doc.read_bytes()  # cópia íntegra: assinatura preservada
    assert (docs / "Procuração Teste_assinado - Relatório de Conformidade ITI.pdf").is_file()
    dossie = docs / "Procuração Teste_assinado - Dossiê de Conformidade.pdf"
    assert len(PdfReader(dossie).pages) == 1 + 4  # capa + relatório (o documento fica ao lado)

    resumo = json.loads(next((saida / processo.PASTA_AUDITORIA).glob("*/resumo.json")).read_text("utf-8"))
    assert resumo["hash_confere"] is True
    assert resumo["arquivos"]["dossie"] == f"{processo.PASTA_DOCUMENTOS}/{dossie.name}"
    assert resumo["assinaturas"][0]["emissor"] == "AC Final do Governo Federal do Brasil v1"

    with open(saida / processo.NOME_PLANILHA, encoding="utf-8-sig") as f:
        assert len(list(csv.DictReader(f, delimiter=";"))) == 2

    # Segunda rodada: nada novo, nada enviado.
    assert processo.validar_pasta(entrada, _lote(saida), "separado", "portuga", log=lambda *_: None) == []
    assert len(iti_simulado.envios) == 1


def test_lote_mesclado_remove_campo_de_assinatura(pastas, iti_simulado):
    entrada, saida = pastas
    pdf_assinado(entrada / "contrato.pdf")
    processo.validar_pasta(entrada, _lote(saida), "mesclado", "portuga", log=lambda *_: None)

    docs = list((saida / processo.PASTA_DOCUMENTOS).iterdir())
    assert [d.name for d in docs] == ["contrato - Dossiê de Conformidade.pdf"]
    leitor = PdfReader(docs[0])
    assert len(leitor.pages) == 1 + 1 + 4
    assert [o.title for o in leitor.outline] == ["Capa", "Cópia do documento", "Relatório de Conformidade ITI"]
    assert b"/ByteRange" not in docs[0].read_bytes()
    # O original exato fica na auditoria, para o painel e para a cadeia de custódia.
    original = next((saida / processo.PASTA_AUDITORIA).glob("*/original.pdf"))
    assert original.read_bytes() == (entrada / "contrato.pdf").read_bytes()


def test_com_ressalvas_ganha_sufixo(pastas, iti_simulado):
    entrada, saida = pastas
    iti_simulado.resultado = "COM_RESSALVAS"
    iti_simulado.assinantes = ASSINANTES[:2]
    pdf_assinado(entrada / "acordo.pdf")
    [linha] = processo.validar_pasta(entrada, _lote(saida), "separado", "portuga", log=lambda *_: None)
    assert linha["resultado"] == "COM_RESSALVAS"
    nomes = sorted(p.name for p in (saida / processo.PASTA_DOCUMENTOS).iterdir())
    assert "acordo - Dossiê de Conformidade (COM RESSALVAS).pdf" in nomes


@pytest.mark.parametrize("resposta,esperado", [
    ("406", "SEM_ASSINATURA_RECONHECIDA"),
    ("400", "SEM_ASSINATURA_OU_CORROMPIDA"),
    ("ERRO", "ERRO"),
])
def test_resultados_sem_relatorio(pastas, iti_simulado, resposta, esperado):
    entrada, saida = pastas
    iti_simulado.resultado = resposta
    pdf_assinado(entrada / "x.pdf")
    [linha] = processo.validar_pasta(entrada, _lote(saida), "separado", "portuga", log=lambda *_: None)
    assert linha["resultado"] == esperado
    assert not (saida / processo.PASTA_DOCUMENTOS).exists()
    registro = processo.ler_registro(saida)
    # Erro de rede não entra no registro: é tentado de novo na próxima validação.
    assert (esperado == "ERRO") == (len(registro) == 0)


def test_homonimos_nao_se_sobrescrevem(tmp_path, iti_simulado):
    entrada = tmp_path / "e"
    (entrada / "cliente A").mkdir(parents=True)
    (entrada / "cliente B").mkdir(parents=True)
    pdf_assinado(entrada / "cliente A" / "procuracao.pdf", "A")
    pdf_assinado(entrada / "cliente B" / "procuracao.pdf", "B")
    saida = tmp_path / "s"
    processo.validar_pasta(entrada, _lote(saida), "separado", "portuga", recursivo=True, log=lambda *_: None)
    nomes = sorted(p.name for p in (saida / processo.PASTA_DOCUMENTOS).iterdir())
    assert "procuracao.pdf" in nomes and "procuracao (2).pdf" in nomes
    assert "procuracao (2) - Dossiê de Conformidade.pdf" in nomes


# ---------------------------------------------------------------- uso simultâneo


def test_trava_impede_validacao_simultanea(pastas, iti_simulado):
    entrada, saida = pastas
    pdf_assinado(entrada / "a.pdf")
    with processo.Trava(saida):
        with pytest.raises(iti.ErroValidar, match="Outra validação"):
            processo.validar_pasta(entrada, _lote(saida), "separado", "portuga", log=lambda *_: None)
    assert iti_simulado.envios == []
    # Liberada a trava, a validação segue normalmente.
    processo.validar_pasta(entrada, _lote(saida), "separado", "portuga", log=lambda *_: None)
    assert iti_simulado.envios == ["a.pdf"]
    assert not (saida / processo.PASTA_AUDITORIA / ".trava").exists()


def test_trava_abandonada_vence(pastas):
    _, saida = pastas
    trava = saida / processo.PASTA_AUDITORIA / ".trava"
    trava.parent.mkdir(parents=True)
    trava.write_text('{"computador": "outro"}', encoding="utf-8")
    antigo = time.time() - processo.Trava.VALIDADE - 60
    os.utime(trava, (antigo, antigo))
    with processo.Trava(saida):
        assert "outro" not in trava.read_text(encoding="utf-8")


def test_registro_mescla_copias_de_conflito_do_drive(pastas):
    _, saida = pastas
    aud = saida / processo.PASTA_AUDITORIA
    aud.mkdir()
    (aud / "registro.json").write_text(json.dumps({"h1": {"resultado": "APROVADO"}}), encoding="utf-8")
    (aud / "registro (1).json").write_text(json.dumps({"h2": {"resultado": "IGNORADO"},
                                                       "h1": {"resultado": "ANTIGO"}}), encoding="utf-8")
    registro = processo.ler_registro(saida)
    assert set(registro) == {"h1", "h2"}
    assert registro["h1"]["resultado"] == "APROVADO"  # o arquivo principal prevalece


def test_registrar_nao_apaga_o_que_outro_computador_gravou(pastas):
    _, saida = pastas
    lote = _lote(saida)
    linha = {**dict.fromkeys(processo.COLUNAS_CSV, ""), "arquivo": "a.pdf", "resultado": "APROVADO"}
    lote.registrar("h1", linha)
    # Outro computador grava h2 diretamente no arquivo...
    caminho = saida / processo.PASTA_AUDITORIA / "registro.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["h2"] = {"resultado": "APROVADO"}
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    # ...e este lote, ao registrar h3, mantém h2.
    lote.registrar("h3", linha)
    assert set(processo.ler_registro(saida)) == {"h1", "h2", "h3"}
    assert lote.ja_validado("h2")


# ---------------------------------------------------------------- cache de SHA-256


def test_cache_evita_reler_arquivo_inalterado(tmp_path):
    arq = tmp_path / "a.pdf"
    arq.write_bytes(b"conteudo original")
    cache = processo.CacheHash()
    h1 = cache.sha256(arq)
    cache.salvar()

    st = arq.stat()
    arq.write_bytes(b"conteudo trocado!")  # mesmo tamanho
    os.utime(arq, ns=(st.st_atime_ns, st.st_mtime_ns))  # mesma data
    assert processo.CacheHash().sha256(arq) == h1  # veio do cache, sem ler o arquivo

    os.utime(arq, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert processo.CacheHash().sha256(arq) == processo.sha256(b"conteudo trocado!")
