"""Fixtures comuns: configuração isolada, PDFs de teste e um ITI simulado.

As respostas simuladas seguem o formato real do VALIDAR (campos de
/simples e /conformidade), com dados fictícios: o repositório é público.
"""

import hashlib
import io
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from govbr import iti  # noqa: E402

ASSINANTES = [
    ("MARIA DE TESTE OLIVEIRA", "***.111.222-**"),
    ("JOSÉ FICTÍCIO DA SILVA", "***.333.444-**"),
    ("ANA EXEMPLO SOUZA", "***.555.666-**"),
]


@pytest.fixture(autouse=True)
def config_isolada(tmp_path, monkeypatch):
    """Nenhum teste toca a configuração real do usuário."""
    pasta = tmp_path / "config"
    monkeypatch.setenv("ASSINATURA_GOVBR_CONFIG_DIR", str(pasta))
    return pasta


def pdf_simples(texto="Documento de teste", paginas=1):
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(paginas):
        c.drawString(72, 720, f"{texto} — página {n + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


SELO = "SELO GOVBR DE TESTE"


def pdf_assinado(caminho, texto="Documento assinado de teste", visivel=True):
    """PDF com campo de assinatura (/FT /Sig, /ByteRange e selo visível), como os do GOV.BR.

    A assinatura não é criptograficamente válida: serve para o pré-filtro
    local e para conferir que a mesclagem estampa o selo e remove o campo.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject,
                               NameObject, NumberObject, TextStringObject)

    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_simples(texto))))
    valor = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Sig"),
        NameObject("/ByteRange"): ArrayObject([NumberObject(0)] * 4),
    }))
    fonte = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    aparencia = DecodedStreamObject()
    aparencia.set_data(f"BT /F1 10 Tf 5 8 Td ({SELO}) Tj ET".encode())
    aparencia.update({
        NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): ArrayObject([FloatObject(0), FloatObject(0), FloatObject(160), FloatObject(30)]),
        NameObject("/Resources"): DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): fonte})}),
    })
    retangulo = [300, 150, 460, 180] if visivel else [0, 0, 0, 0]
    widget = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Sig"),
        NameObject("/T"): TextStringObject("Assinatura1"),
        NameObject("/Rect"): ArrayObject([NumberObject(v) for v in retangulo]),
        NameObject("/V"): valor,
        NameObject("/AP"): DictionaryObject({NameObject("/N"): w._add_object(aparencia)}),
    }))
    w.pages[0][NameObject("/Annots")] = ArrayObject([widget])
    w._root_object[NameObject("/AcroForm")] = DictionaryObject({NameObject("/Fields"): ArrayObject([widget])})
    with open(caminho, "wb") as f:
        w.write(f)
    return Path(caminho)


class ITISimulado:
    """Substitui as chamadas de rede de govbr.iti. `resultado` controla a resposta."""

    def __init__(self):
        self.resultado = "APROVADO"  # APROVADO | COM_RESSALVAS | 406 | 400 | ERRO
        self.assinantes = ASSINANTES[:1]
        self.envios = []

    def validar_arquivo(self, assinatura, destacado=None):
        self.envios.append(Path(assinatura).name)
        if self.resultado == "ERRO":
            raise iti.ErroValidar("HTTP 503: VALIDAR indisponível. Tente novamente mais tarde.")
        h = hashlib.sha256(Path(assinatura).read_bytes()).hexdigest()
        if self.resultado == "406":
            return 406, {"errorCode": 406, "nome": "Verificador de Conformidade", "hash": h,
                         "date": "21/10/2026 14:34:00 BRT"}
        if self.resultado == "400":
            return 400, {"errorCode": 400}
        return 200, {"verifierReport": "simulado", "hash": h, "nome": Path(assinatura).name}

    def relatorio_simples(self, bruto):
        status = ["Aprovado"] * len(self.assinantes)
        if self.resultado == "COM_RESSALVAS":
            status[0] = "Indeterminada"
        return {
            "statusDocumento": "Aprovado" if self.resultado == "APROVADO" else "Indeterminado",
            "nomeArquivo": bruto["nome"],
            "hash": bruto["hash"],
            "dataValidacao": "21/10/2026 15:06:10 BRT",
            "assinaturas": [
                {"nome": nome, "certificadora": "Gov-Br", "cpf": cpf, "possuiDadosMedicos": False,
                 "data": f"2{i}/10/2026 10:50:47 BRT", "status": s, "mdp": False, "possuiCarimboTempo": False}
                for i, ((nome, cpf), s) in enumerate(zip(self.assinantes, status))
            ],
        }

    def relatorio_conformidade(self, bruto):
        return {
            "nomeSoftware": "Validador de assinaturas eletrônicas",
            "nomeVerificador": "Verificador de Conformidade", "versaoVerificador": "2.32.1",
            "nomeValidador": "Validador de Documentos", "versaoValidador": "3.5.2",
            "nomeArquivo": bruto["nome"], "sha256": bruto["hash"], "tipoArquivo": "PDF",
            "qtdAssinaturas": len(self.assinantes), "qtdAncoradas": len(self.assinantes),
            "infoAss": [
                {"assinante": f"CN={nome}", "tipoAssinatura": "Destacada", "statusAss": "Aprovado",
                 "caminhoCert": "Aprovado", "estrutura": "Em conformidade com o padrão", "cifra": "Aprovada",
                 "msgAlerta": "Nenhuma mensagem de alerta", "CPF": cpf,
                 "certUtilizados": [{
                     "emissor": "CN=AC Final do Governo Federal do Brasil v1, OU=AC Intermediaria do "
                                "Governo Federal do Brasil v1, O=Gov-Br, C=BR",
                     "dataMaxVal": "02/07/2027 12:02:56 BRT",
                 }]}
                for nome, cpf in self.assinantes
            ],
        }

    def baixar_pdf(self, conformidade, idioma="portuga"):
        return pdf_simples("Relatório de conformidade (simulado)", paginas=4)


@pytest.fixture
def iti_simulado(monkeypatch):
    sim = ITISimulado()
    for nome in ("validar_arquivo", "relatorio_simples", "relatorio_conformidade", "baixar_pdf"):
        monkeypatch.setattr(iti, nome, getattr(sim, nome))
    monkeypatch.setattr("govbr.processo.PAUSA_LOTE", 0)
    return sim


@pytest.fixture
def pastas(tmp_path):
    entrada = tmp_path / "A validar"
    saida = tmp_path / "Validados"
    entrada.mkdir()
    saida.mkdir()
    return entrada, saida
