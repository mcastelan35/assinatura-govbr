"""Mesclagem: documento assinado + Relatório de Conformidade do ITI num PDF só.

O PDF mesclado é uma CÓPIA para leitura e protocolo: a assinatura digital
original não sobrevive à mesclagem (qualquer alteração num PDF assinado invalida
o hash). O campo de assinatura vira só desenho: o selo visível (ex.: o carimbo
GOV.BR) é estampado no conteúdo da página, na mesma posição, e o campo
interativo sai — assim a cópia fica igual ao original na tela e na impressão,
sem o leitor acusar "assinatura inválida". O original permanece intacto na
entrada e em _auditoria.
"""

from pathlib import Path

from . import CREDITO, VERSAO, processo


def _eh_assinatura(obj):
    if obj.get("/FT") == "/Sig":
        return True
    pai = obj.get("/Parent")
    return pai is not None and pai.get_object().get("/FT") == "/Sig"


def _matriz_do_selo(aparencia, retangulo):
    """Matriz que leva a aparência (BBox × Matrix) ao retângulo do campo, como o leitor faz (PDF 32000, 12.5.5)."""
    bbox = [float(v) for v in aparencia.get("/BBox", [0, 0, 1, 1])]
    m = [float(v) for v in aparencia.get("/Matrix", [1, 0, 0, 1, 0, 0])]
    cantos = [(x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5])
              for x in (bbox[0], bbox[2]) for y in (bbox[1], bbox[3])]
    bx1, bx2 = min(c[0] for c in cantos), max(c[0] for c in cantos)
    by1, by2 = min(c[1] for c in cantos), max(c[1] for c in cantos)
    rx1, ry1, rx2, ry2 = (float(v) for v in retangulo)
    rx1, rx2, ry1, ry2 = min(rx1, rx2), max(rx1, rx2), min(ry1, ry2), max(ry1, ry2)
    if bx2 == bx1 or by2 == by1 or rx2 == rx1 or ry2 == ry1:
        return None  # assinatura invisível (retângulo vazio): nada a desenhar
    sx, sy = (rx2 - rx1) / (bx2 - bx1), (ry2 - ry1) / (by2 - by1)
    return sx, sy, rx1 - bx1 * sx, ry1 - by1 * sy


def _estampar_assinaturas(pagina):
    """Desenha o selo de cada campo de assinatura no conteúdo e remove os campos."""
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, StreamObject

    if "/Annots" not in pagina:
        return
    restantes, comandos, xobjetos = [], [], {}
    for i, ref in enumerate(pagina["/Annots"]):
        anot = ref.get_object()
        if not _eh_assinatura(anot):
            restantes.append(ref)
            continue
        # Esvazia o valor da assinatura (/ByteRange, /Contents com o PKCS#7) na cópia:
        # sem isso ele seria gravado como objeto solto, mesmo sem referência.
        for campo in (anot, anot.get("/Parent")):
            valor = campo.get_object().get("/V") if campo is not None else None
            if valor is not None and isinstance(valor.get_object(), DictionaryObject):
                valor.get_object().clear()
        oculta = int(anot.get("/F", 0)) & (2 | 32)  # Hidden | NoView
        ap = anot.get("/AP")
        normal = ap.get_object().get("/N") if ap is not None else None
        if oculta or normal is None or not isinstance(normal.get_object(), StreamObject):
            continue
        matriz = _matriz_do_selo(normal.get_object(), anot.get("/Rect", [0, 0, 0, 0]))
        if matriz is None:
            continue
        nome = f"/SeloAssinatura{i}"
        xobjetos[NameObject(nome)] = normal  # referência à aparência original, sem recriá-la
        comandos.append("q {:.6f} 0 0 {:.6f} {:.4f} {:.4f} cm {} Do Q".format(*matriz, nome))

    if comandos:
        recursos = pagina.get("/Resources")
        recursos = recursos.get_object() if recursos is not None else DictionaryObject()
        xo = recursos.get("/XObject")
        xo = xo.get_object() if xo is not None else DictionaryObject()
        xo.update(xobjetos)
        recursos[NameObject("/XObject")] = xo
        pagina[NameObject("/Resources")] = recursos
        conteudo = pagina.get_contents()
        anterior = conteudo.get_data() if conteudo is not None else b""
        # O conteúdo original vai entre q/Q para que o estado gráfico dele não desloque o selo.
        novo = b"q\n" + anterior + b"\nQ\n" + "\n".join(comandos).encode("ascii") + b"\n"
        if conteudo is None:
            from pypdf.generic import ContentStream, DecodedStreamObject

            conteudo = ContentStream(DecodedStreamObject(), pagina.pdf)
        conteudo.set_data(novo)
        pagina.replace_contents(conteudo)

    if restantes:
        pagina[NameObject("/Annots")] = ArrayObject(restantes)
    else:
        del pagina["/Annots"]


def _anexar(writer, origem, titulo, estampar=False):
    from pypdf import PdfReader

    inicio = len(writer.pages)
    for pagina in PdfReader(str(origem)).pages:
        nova = writer.add_page(pagina)
        if estampar:
            _estampar_assinaturas(nova)
    writer.add_outline_item(titulo, inicio)


def mesclar(documento, relatorio, destino, nome_documento=None):
    """Páginas do documento assinado (com o selo visível) seguidas das do relatório do ITI."""
    from pypdf import PdfWriter

    w = PdfWriter()
    _anexar(w, documento, "Documento assinado", estampar=True)
    _anexar(w, relatorio, processo.NOME_RELATORIO)
    if "/AcroForm" in w._root_object:  # campos de formulário que apontariam para a assinatura removida
        del w._root_object["/AcroForm"]
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
