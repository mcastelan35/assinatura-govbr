"""Mesclagem: documento assinado + Relatório de Conformidade do ITI num PDF só.

O PDF mesclado é uma CÓPIA para leitura e protocolo: a assinatura digital
original não sobrevive à mesclagem (qualquer alteração num PDF assinado invalida
o hash). Por isso os campos de assinatura são removidos — evita que leitores
exibam "assinatura inválida" — e o original permanece intacto na entrada e em
_auditoria.
"""

from pathlib import Path

from . import CREDITO, VERSAO, processo


def _sem_campos_de_assinatura(pagina):
    from pypdf.generic import ArrayObject, NameObject

    def eh_assinatura(anot):
        obj = anot.get_object()
        if obj.get("/FT") == "/Sig":
            return True
        pai = obj.get("/Parent")
        return pai is not None and pai.get_object().get("/FT") == "/Sig"

    if "/Annots" in pagina:
        restantes = [a for a in pagina["/Annots"] if not eh_assinatura(a)]
        if restantes:
            pagina[NameObject("/Annots")] = ArrayObject(restantes)
        else:
            del pagina["/Annots"]
    return pagina


def _anexar(writer, origem, titulo, limpar=False):
    from pypdf import PdfReader

    inicio = len(writer.pages)
    for pagina in PdfReader(str(origem)).pages:
        # Filtra antes de copiar: assim o dicionário da assinatura nem entra no arquivo novo.
        writer.add_page(_sem_campos_de_assinatura(pagina) if limpar else pagina)
    writer.add_outline_item(titulo, inicio)


def mesclar(documento, relatorio, destino, nome_documento=None):
    """Páginas do documento assinado seguidas das do relatório oficial do ITI."""
    from pypdf import PdfWriter

    w = PdfWriter()
    _anexar(w, documento, "Documento assinado", limpar=True)
    _anexar(w, relatorio, processo.NOME_RELATORIO)
    stem = Path(nome_documento or documento).stem
    w.add_metadata({
        "/Title": f"{stem} - com {processo.NOME_RELATORIO}",
        "/Subject": "Cópia do documento seguida do Relatório de Conformidade do VALIDAR/ITI. "
                    "A assinatura digital vale no arquivo original.",
        "/Author": CREDITO,
        "/Producer": f"assinatura-govbr {VERSAO}",
    })
    w.page_mode = "/UseOutlines"
    with open(destino, "wb") as f:
        w.write(f)
