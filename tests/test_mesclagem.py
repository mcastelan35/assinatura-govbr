from pypdf import PdfReader

from conftest import SELO, pdf_assinado, pdf_simples
from govbr import mesclagem, processo


def _mesclar(tmp_path, **kw):
    doc = pdf_assinado(tmp_path / "procuracao.pdf", **kw)
    rel = tmp_path / "rel.pdf"
    rel.write_bytes(pdf_simples("relatorio", paginas=4))
    destino = tmp_path / "saida.pdf"
    mesclagem.mesclar(doc, rel, destino)
    return destino


def test_mescla_documento_e_relatorio_sem_capa(tmp_path):
    leitor = PdfReader(_mesclar(tmp_path))
    assert len(leitor.pages) == 1 + 4  # documento + relatório, nada além disso
    assert [o.title for o in leitor.outline] == ["Documento assinado", processo.NOME_RELATORIO]
    assert "Documento assinado de teste" in leitor.pages[0].extract_text()
    assert leitor.metadata["/Title"] == f"procuracao - com {processo.NOME_RELATORIO}"


def test_selo_visivel_da_assinatura_continua_na_pagina(tmp_path):
    """O selo GOV.BR é desenhado no conteúdo; sem isso a cópia parece o documento não assinado."""
    pagina = PdfReader(_mesclar(tmp_path)).pages[0]
    assert SELO in pagina.extract_text()
    assert "/Annots" not in pagina  # o campo interativo saiu; ficou só o desenho


def test_dados_da_assinatura_nao_vao_para_a_copia(tmp_path):
    destino = _mesclar(tmp_path)
    # Numa cópia a assinatura é inválida; sem o campo e sem /ByteRange, o leitor não acusa erro.
    assert b"/ByteRange" not in destino.read_bytes()
    assert "/AcroForm" not in PdfReader(destino).trailer["/Root"]


def test_assinatura_invisivel_nao_desenha_nada(tmp_path):
    pagina = PdfReader(_mesclar(tmp_path, visivel=False)).pages[0]
    assert SELO not in pagina.extract_text()
    assert "/Annots" not in pagina
