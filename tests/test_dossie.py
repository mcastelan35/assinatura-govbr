import io

from pypdf import PdfReader

from conftest import ASSINANTES, pdf_simples
from govbr import CREDITO, dossie


def _resumo(n_assinaturas=1, resultado="APROVADO"):
    return {
        "arquivo": "Contrato de Teste_assinado.pdf",
        "sha256_arquivo": "a" * 64,
        "validado_em": "2026-10-21T15:06:08",
        "data_validacao_iti": "21/10/2026 15:06:10 BRT",
        "resultado": resultado,
        "hash_confere": True,
        "iti": {"verificador": "Verificador de Conformidade 2.32.1",
                "validador": "Validador de Documentos 3.5.2", "tipo_arquivo": "PDF"},
        "assinaturas": [
            {"signatario": nome, "cpf": cpf, "status": "Aprovado", "certificadora": "Gov-Br",
             "emissor": "AC Final do Governo Federal do Brasil v1",
             "data_assinatura": "21/10/2026 10:50:47 BRT", "carimbo_de_tempo": False,
             "caminho_certificacao": "Aprovado", "cifra": "Aprovada",
             "alerta": "Nenhuma mensagem de alerta"}
            for nome, cpf in ASSINANTES[:n_assinaturas]
        ],
    }


def _texto(pdf_bytes):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_nome_proprio():
    assert dossie.nome_proprio("FRANCISCO DAS CHAGAS DE ARAUJO") == "Francisco das Chagas de Araujo"
    assert dossie.nome_proprio("DE SOUZA") == "De Souza"


def test_capa_cabe_em_uma_pagina_com_tres_assinaturas(tmp_path):
    rel = tmp_path / "rel.pdf"
    rel.write_bytes(pdf_simples("relatorio", paginas=4))
    capa = dossie.gerar_capa(_resumo(3), None, rel)
    assert len(PdfReader(io.BytesIO(capa)).pages) == 1
    texto = _texto(capa)
    assert "As 3 assinaturas foram aprovadas" in texto
    assert "Relatório de Conformidade emitido pelo ITI — p. 2–5" in texto
    assert CREDITO in texto


def test_capa_com_documento_explica_que_a_copia_nao_tem_assinatura(tmp_path):
    rel = tmp_path / "rel.pdf"
    rel.write_bytes(pdf_simples(paginas=4))
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(pdf_simples(paginas=2))
    texto = _texto(dossie.gerar_capa(_resumo(), doc, rel))
    assert "Cópia do documento — p. 2–3" in texto
    assert "não contém a assinatura digital" in texto


def test_dossie_por_pessoa(tmp_path):
    itens = []
    for i in range(3):
        caminho = tmp_path / f"d{i}.pdf"
        caminho.write_bytes(pdf_simples(paginas=2))
        itens.append((_resumo(), caminho))
    destino = tmp_path / "pessoa.pdf"
    dossie.montar_dossie_pessoa(ASSINANTES[0][0], ASSINANTES[0][1], itens, destino)
    leitor = PdfReader(destino)
    assert len(leitor.pages) == 1 + 3 * 2
    assert leitor.outline[0].title == "Resumo"
    assert "Maria de Teste Oliveira" in leitor.pages[0].extract_text()
