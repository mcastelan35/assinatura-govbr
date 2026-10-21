from pypdf import PdfReader

from conftest import pdf_assinado, pdf_simples
from govbr import mesclagem, processo


def test_mescla_documento_e_relatorio_sem_capa(tmp_path):
    doc = pdf_assinado(tmp_path / "procuracao.pdf")
    rel = tmp_path / "rel.pdf"
    rel.write_bytes(pdf_simples("relatorio", paginas=4))
    destino = tmp_path / "saida.pdf"

    mesclagem.mesclar(doc, rel, destino)

    leitor = PdfReader(destino)
    assert len(leitor.pages) == 1 + 4  # documento + relatório, nada além disso
    assert [o.title for o in leitor.outline] == ["Documento assinado", processo.NOME_RELATORIO]
    assert "Documento assinado de teste" in leitor.pages[0].extract_text()
    assert leitor.metadata["/Title"] == f"procuracao - com {processo.NOME_RELATORIO}"


def test_mesclagem_remove_campo_de_assinatura(tmp_path):
    doc = pdf_assinado(tmp_path / "a.pdf")
    rel = tmp_path / "rel.pdf"
    rel.write_bytes(pdf_simples())
    destino = tmp_path / "m.pdf"
    mesclagem.mesclar(doc, rel, destino)
    # Numa cópia a assinatura é inválida; sem o campo, o leitor de PDF não acusa erro.
    assert b"/ByteRange" not in destino.read_bytes()
    assert "/Annots" not in PdfReader(destino).pages[0]
