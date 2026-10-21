"""Dossiê de Conformidade: capa + [cópia do documento] + Relatório oficial do ITI.

A capa é um resumo feito a partir das respostas do ITI; o documento oficial é o
relatório do VALIDAR, reproduzido sem alteração logo depois dela.
"""

import datetime as dt
import io
from pathlib import Path
from xml.sax.saxutils import escape

from . import CONTATO_ROTULO, CONTATO_URL, CREDITO, VERSAO

TINTA = "#1b2230"
TINTA_2 = "#4a5160"
APAGADO = "#7c818b"
LINHA = "#ddd8cc"
FUNDO_NOTA = "#f5f2ea"
LATAO = "#9a7b4f"
COR_STATUS = {
    "APROVADO": "#1f7a3a",
    "COM_RESSALVAS": "#a86a00",
    "SEM_ASSINATURA_RECONHECIDA": "#b4532a",
    "SEM_ASSINATURA_OU_CORROMPIDA": "#b4532a",
    "ERRO": "#b42318",
}
TEXTO_STATUS = {
    "APROVADO": "Aprovado",
    "COM_RESSALVAS": "Com ressalvas",
    "SEM_ASSINATURA_RECONHECIDA": "Sem assinatura reconhecida",
    "SEM_ASSINATURA_OU_CORROMPIDA": "Sem assinatura ou corrompida",
    "ERRO": "Erro na validação",
}
PARTICULAS = {"da", "das", "de", "do", "dos", "e"}


def nome_proprio(nome):
    """'FRANCISCO DAS CHAGAS DE ARAUJO' -> 'Francisco das Chagas de Araujo'."""
    palavras = (nome or "").strip().lower().split()
    return " ".join(
        p if (i and p in PARTICULAS) else p[:1].upper() + p[1:] for i, p in enumerate(palavras)
    )


def data_br(iso):
    try:
        return dt.datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def _e(texto):
    return escape(str(texto if texto is not None else ""))


# ---------------------------------------------------------------- capa (reportlab)


def _estilos():
    from reportlab.lib.styles import ParagraphStyle

    base = dict(fontName="Helvetica", fontSize=9.2, leading=13, textColor=TINTA)
    return {
        "rotulo": ParagraphStyle("rotulo", **{**base, "fontSize": 6.8, "leading": 9,
                                              "textColor": APAGADO, "fontName": "Helvetica-Bold"}),
        "valor": ParagraphStyle("valor", **base),
        "mono": ParagraphStyle("mono", **{**base, "fontName": "Courier", "fontSize": 8.2, "leading": 11}),
        "titulo": ParagraphStyle("titulo", **{**base, "fontName": "Times-Roman", "fontSize": 22,
                                              "leading": 26}),
        "sub": ParagraphStyle("sub", **{**base, "textColor": TINTA_2, "fontSize": 9.5, "leading": 13.5}),
        "secao": ParagraphStyle("secao", **{**base, "fontName": "Times-Roman", "fontSize": 13.5,
                                            "leading": 17, "spaceBefore": 12, "spaceAfter": 4}),
        "status": ParagraphStyle("status", **{**base, "fontName": "Helvetica-Bold", "fontSize": 13,
                                              "leading": 16}),
        "nota": ParagraphStyle("nota", **{**base, "fontSize": 7.8, "leading": 11, "textColor": TINTA_2}),
        "nome": ParagraphStyle("nome", **{**base, "fontName": "Helvetica-Bold", "fontSize": 10}),
    }


def _rotulo_espacado(texto):
    return _e(texto.upper())


def _moldura(titulo_cabecalho):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm

    def desenhar(canvas, doc):
        largura, altura = doc.pagesize
        canvas.saveState()
        canvas.setFillColor(HexColor(LATAO))
        canvas.rect(doc.leftMargin, altura - 14 * mm, 18 * mm, 0.9 * mm, stroke=0, fill=1)
        canvas.setFont("Helvetica-Bold", 6.6)
        canvas.setFillColor(HexColor(APAGADO))
        canvas.drawString(doc.leftMargin, altura - 19 * mm, titulo_cabecalho.upper(), charSpace=1.4)
        canvas.setStrokeColor(HexColor(LINHA))
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 15 * mm, largura - doc.rightMargin, 15 * mm)
        canvas.setFont("Helvetica", 6.8)
        canvas.drawString(doc.leftMargin, 10.5 * mm,
                          f"assinatura-govbr {VERSAO}  ·  {CREDITO}  ·  {CONTATO_ROTULO}")
        canvas.linkURL(CONTATO_URL, (doc.leftMargin, 9 * mm, doc.leftMargin + 120 * mm, 13 * mm))
        canvas.drawRightString(largura - doc.rightMargin, 10.5 * mm, f"Capa · {doc.page}")
        canvas.restoreState()

    return desenhar


def _tabela_campos(pares, est, largura_rotulo=38):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    linhas = [[Paragraph(_rotulo_espacado(r), est["rotulo"]), v if not isinstance(v, str)
               else Paragraph(v, est["valor"])] for r, v in pares]
    t = Table(linhas, colWidths=[largura_rotulo * mm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, HexColor(LINHA)),
    ]))
    return t


def _tabela_assinaturas(assinaturas, est):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    pequeno = ParagraphStyle("pequeno", parent=est["nota"], textColor=APAGADO)
    linhas = [[Paragraph(_rotulo_espacado(t), est["rotulo"])
               for t in ("Signatário", "Assinado em", "Certificado", "Situação")]]
    for a in assinaturas:
        data, _, hora = (a.get("data_assinatura") or "—").replace(" BRT", "").partition(" ")
        cor = COR_STATUS["APROVADO"] if a.get("status") == "Aprovado" else COR_STATUS["COM_RESSALVAS"]
        linhas.append([
            [Paragraph(_e(nome_proprio(a.get("signatario"))), est["nome"]),
             Paragraph(f"CPF {_e(a.get('cpf') or '—')}", pequeno)],
            [Paragraph(_e(data), est["valor"]), Paragraph(_e(hora), pequeno)],
            [Paragraph(_e(a.get("certificadora") or "—"), est["valor"]),
             Paragraph(_e(a.get("emissor") or ""), pequeno)],
            Paragraph(f'<font color="{cor}"><b>{_e(a.get("status"))}</b></font>', est["valor"]),
        ])
    t = Table(linhas, colWidths=[None, 24 * mm, 62 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor(LINHA)),
    ]))
    return t


def _faixa_status(resultado, conclusao, est):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    cor = COR_STATUS.get(resultado, TINTA)
    t = Table(
        [["", [Paragraph(f'<font color="{cor}">{_e(TEXTO_STATUS.get(resultado, resultado))}</font>',
                         est["status"]),
               Paragraph(conclusao, est["sub"])]]],
        colWidths=[1.6 * mm, None],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), HexColor(cor)),
        ("BACKGROUND", (1, 0), (1, 0), HexColor(FUNDO_NOTA)),
        ("LEFTPADDING", (1, 0), (1, 0), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
    ]))
    return t


def _conclusao(resumo):
    ass = resumo.get("assinaturas") or []
    n = len(ass)
    aprov = sum(1 for a in ass if a.get("status") == "Aprovado")
    if resumo["resultado"] == "APROVADO":
        texto = (f"{'A assinatura foi aprovada' if n == 1 else f'As {n} assinaturas foram aprovadas'} "
                 "pelo VALIDAR do ITI.")
    elif resumo["resultado"] == "COM_RESSALVAS":
        texto = (f"{aprov} de {n} assinatura(s) aprovada(s); as demais foram consideradas "
                 "indeterminadas ou reprovadas. Consulte os detalhes no relatório do ITI.")
    else:
        texto = _e(resumo.get("detalhe") or "")
    if resumo.get("hash_confere") is True:
        texto += " O resumo SHA-256 calculado localmente coincide com o informado pelo ITI."
    elif resumo.get("hash_confere") is False:
        texto += " <b>Atenção:</b> o resumo SHA-256 calculado localmente difere do informado pelo ITI."
    if resumo.get("validacao_parcial"):
        texto += " Validação parcial: o documento tem mais assinaturas do que o ITI processou."
    return texto


def _paginas(caminho):
    from pypdf import PdfReader

    return len(PdfReader(str(caminho)).pages) if caminho else 0


def gerar_capa(resumo, documento, relatorio):
    """PDF da capa (bytes). Feito em duas passagens para saber as páginas do sumário."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    est = _estilos()
    pag_doc, pag_rel = _paginas(documento), _paginas(relatorio)

    def construir(paginas_capa):
        h = []
        h.append(Spacer(1, 4 * mm))
        h.append(Paragraph(_e(Path(resumo["arquivo"]).stem), est["titulo"]))
        h.append(Spacer(1, 2.5 * mm))
        quando = resumo.get("data_validacao_iti") or data_br(resumo.get("validado_em"))
        h.append(Paragraph(
            f"Validação no VALIDAR — Instituto Nacional de Tecnologia da Informação (ITI), em {_e(quando)}.",
            est["sub"]))
        h.append(Spacer(1, 7 * mm))
        h.append(_faixa_status(resumo["resultado"], _conclusao(resumo), est))

        h.append(Paragraph("Documento", est["secao"]))
        iti_info = resumo.get("iti") or {}
        h.append(_tabela_campos([
            ("Arquivo", _e(resumo["arquivo"])),
            ("SHA-256", Paragraph(_e(resumo["sha256_arquivo"]), est["mono"])),
            ("Tipo", _e(iti_info.get("tipo_arquivo") or Path(resumo["arquivo"]).suffix.upper().lstrip("."))),
            ("Assinaturas", _e(f"{len(resumo.get('assinaturas') or [])} encontrada(s)"
                               + (f", {resumo['assinaturas_desconhecidas']} desconhecida(s)"
                                  if resumo.get("assinaturas_desconhecidas") else ""))),
        ], est))

        assinaturas = resumo.get("assinaturas") or []
        if assinaturas:
            h.append(Paragraph(f"Assinaturas ({len(assinaturas)})", est["secao"]))
            h.append(_tabela_assinaturas(assinaturas, est))
            observacoes = []
            for a in assinaturas:
                problemas = [
                    f"caminho de certificação {a['caminho_certificacao'].lower()}"
                    for _ in [0] if a.get("caminho_certificacao") not in (None, "", "Aprovado")
                ] + [
                    f"cifra {a['cifra'].lower()}" for _ in [0] if a.get("cifra") not in (None, "", "Aprovada")
                ] + [
                    a["alerta"] for _ in [0]
                    if a.get("alerta") and a["alerta"] != "Nenhuma mensagem de alerta"
                ]
                if problemas:
                    observacoes.append(f"<b>{_e(nome_proprio(a.get('signatario')))}:</b> {_e('; '.join(problemas))}.")
            if not any(a.get("carimbo_de_tempo") for a in assinaturas):
                observacoes.append("Nenhuma assinatura tem carimbo de tempo: as datas são as declaradas por "
                                   "quem assinou, como é usual nas assinaturas GOV.BR.")
            for obs in observacoes:
                h.append(Spacer(1, 1.5 * mm))
                h.append(Paragraph(obs, est["nota"]))

        h.append(Paragraph("Validação", est["secao"]))
        h.append(_tabela_campos([
            ("Serviço", "VALIDAR — ITI (validar.iti.gov.br)"),
            ("Software do ITI", _e(" · ".join(filter(None, [iti_info.get("verificador"),
                                                            iti_info.get("validador")])) or "—")),
            ("Norma", "ETSI EN 319 102-1 e regulamentação ICP-Brasil / GOV.BR"),
        ], est))

        h.append(Paragraph("Este dossiê contém", est["secao"]))
        itens = [("Capa", 1, paginas_capa)]
        inicio = paginas_capa + 1
        if documento:
            itens.append(("Cópia do documento", inicio, inicio + pag_doc - 1))
            inicio += pag_doc
        itens.append(("Relatório de Conformidade emitido pelo ITI", inicio, inicio + pag_rel - 1))
        h.append(_tabela_campos([
            (f"{i}.", f"{_e(t)} — {'p. ' + str(a) if a == b else f'p. {a}–{b}'}")
            for i, (t, a, b) in enumerate(itens, 1)
        ], est, largura_rotulo=10))

        h.append(Spacer(1, 6 * mm))
        nota = ("Esta capa é um resumo elaborado pelo plugin assinatura-govbr a partir das respostas do "
                "ITI. O documento oficial é o Relatório de Conformidade emitido pelo VALIDAR, reproduzido "
                "integralmente a seguir.")
        if documento:
            nota += (" A cópia do documento incluída neste dossiê não contém a assinatura digital: a "
                     "assinatura é verificável no arquivo original, identificado pelo resumo SHA-256 acima.")
        h.append(_tabela_campos([("Nota", Paragraph(nota, est["nota"]))], est, largura_rotulo=14))
        return h

    def renderizar(paginas_capa):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=26 * mm,
            bottomMargin=22 * mm, title=f"{Path(resumo['arquivo']).stem} - Dossiê de Conformidade",
            author=CREDITO, creator=f"assinatura-govbr {VERSAO}",
        )
        moldura = _moldura("Dossiê de conformidade de assinatura")
        doc.build(construir(paginas_capa), onFirstPage=moldura, onLaterPages=moldura)
        return buf.getvalue(), doc.page

    pdf, paginas = renderizar(1)
    if paginas != 1:
        pdf, _ = renderizar(paginas)
    return pdf


# ---------------------------------------------------------------- montagem (pypdf)


def _sem_campos_de_assinatura(pagina):
    """Remove os widgets de assinatura: numa cópia, o leitor mostraria 'assinatura inválida'."""
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


def _anexar(writer, origem, titulo, pai=None, limpar=False):
    from pypdf import PdfReader

    inicio = len(writer.pages)
    leitor = PdfReader(origem if isinstance(origem, io.BytesIO) else str(origem))
    for pagina in leitor.pages:
        # Filtra antes de copiar: assim o dicionário da assinatura nem entra no arquivo novo.
        writer.add_page(_sem_campos_de_assinatura(pagina) if limpar else pagina)
    return writer.add_outline_item(titulo, inicio, parent=pai)


def montar_dossie(resumo, documento, relatorio, destino):
    """capa + [cópia do documento, sem os campos de assinatura] + relatório oficial."""
    from pypdf import PdfWriter

    w = PdfWriter()
    _anexar(w, io.BytesIO(gerar_capa(resumo, documento, relatorio)), "Capa")
    if documento:
        _anexar(w, documento, "Cópia do documento", limpar=True)
    _anexar(w, relatorio, "Relatório de Conformidade ITI")
    w.add_metadata({
        "/Title": f"{Path(resumo['arquivo']).stem} - Dossiê de Conformidade",
        "/Subject": "Capa-resumo, cópia do documento e Relatório de Conformidade do VALIDAR/ITI. "
                    "A assinatura digital vale no arquivo original.",
        "/Author": CREDITO,
        "/Producer": f"assinatura-govbr {VERSAO}",
    })
    w.page_mode = "/UseOutlines"
    with open(destino, "wb") as f:
        w.write(f)


# ---------------------------------------------------------------- dossiê por pessoa


def capa_pessoa(nome, cpf, documentos):
    """documentos: [(resumo, paginas_do_dossie)] na ordem em que entram no PDF."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    est = _estilos()

    def construir(paginas_capa):
        h = [Spacer(1, 4 * mm), Paragraph(_e(nome_proprio(nome)), est["titulo"]), Spacer(1, 2.5 * mm)]
        h.append(Paragraph(
            f"CPF {_e(cpf or '—')}  ·  {len(documentos)} documento(s) assinado(s) validado(s) no VALIDAR do ITI.",
            est["sub"]))
        h.append(Paragraph("Documentos", est["secao"]))
        cab = [Paragraph(_rotulo_espacado(t), est["rotulo"]) for t in ("Documento", "Assinado em", "Situação", "Páginas")]
        linhas = [cab]
        inicio = paginas_capa + 1
        for resumo, pags in documentos:
            data = next((a.get("data_assinatura") for a in resumo.get("assinaturas", [])
                         if (a.get("signatario") or "").upper() == nome.upper()), "")
            cor = COR_STATUS.get(resumo["resultado"], TINTA)
            linhas.append([
                Paragraph(_e(Path(resumo["arquivo"]).stem), est["valor"]),
                Paragraph(_e((data or "").replace(" BRT", "")), est["valor"]),
                Paragraph(f'<font color="{cor}">{_e(TEXTO_STATUS.get(resumo["resultado"], resumo["resultado"]))}</font>',
                          est["valor"]),
                Paragraph(f"{inicio}–{inicio + pags - 1}", est["valor"]),
            ])
            inicio += pags
        t = Table(linhas, colWidths=[None, 34 * mm, 30 * mm, 16 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, HexColor(LINHA)),
        ]))
        h.append(t)
        h.append(Spacer(1, 6 * mm))
        h.append(Paragraph(
            "Cada documento a seguir traz a própria capa-resumo e o Relatório de Conformidade oficial "
            "emitido pelo ITI. O CPF aparece mascarado, como informado pelo ITI.", est["nota"]))
        return h

    def renderizar(paginas_capa):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                                topMargin=26 * mm, bottomMargin=22 * mm,
                                title=f"{nome_proprio(nome)} - Dossiê de assinaturas",
                                author=CREDITO, creator=f"assinatura-govbr {VERSAO}")
        moldura = _moldura("Dossiê de assinaturas por pessoa")
        doc.build(construir(paginas_capa), onFirstPage=moldura, onLaterPages=moldura)
        return buf.getvalue(), doc.page

    pdf, paginas = renderizar(1)
    if paginas != 1:
        pdf, _ = renderizar(paginas)
    return pdf


def montar_dossie_pessoa(nome, cpf, itens, destino):
    """itens: [(resumo, caminho_do_dossie)]; junta os dossiês com uma capa da pessoa."""
    from pypdf import PdfWriter

    com_paginas = [(r, _paginas(c), c) for r, c in itens]
    w = PdfWriter()
    _anexar(w, io.BytesIO(capa_pessoa(nome, cpf, [(r, p) for r, p, _ in com_paginas])), "Resumo")
    for resumo, _, caminho in com_paginas:
        _anexar(w, caminho, Path(resumo["arquivo"]).stem)
    w.add_metadata({"/Title": f"{nome_proprio(nome)} - Dossiê de assinaturas", "/Author": CREDITO,
                    "/Producer": f"assinatura-govbr {VERSAO}"})
    w.page_mode = "/UseOutlines"
    with open(destino, "wb") as f:
        w.write(f)
