"""Pasta de saída fictícia, para conhecer o painel sem dados de clientes.

Nada aqui fala com o ITI: os "relatórios" são PDFs de demonstração, marcados
como tal em todas as páginas.
"""

import datetime as dt
import hashlib
import io
import json
import random
from pathlib import Path

from . import processo

PESSOAS = [
    ("HELENA MARQUES DE OLIVEIRA", "***.412.538-**"),
    ("RAFAEL AUGUSTO PIMENTEL", "***.903.117-**"),
    ("BEATRIZ CAMARGO NUNES", "***.250.641-**"),
    ("JOÃO PEDRO SALVADOR", "***.778.002-**"),
    ("MARINA DUARTE FONSECA", "***.135.890-**"),
    ("OTÁVIO RIBEIRO LACERDA", "***.664.271-**"),
    ("LUÍSA TEIXEIRA BRANDÃO", "***.389.455-**"),
    ("CARLOS EDUARDO MENEZES", "***.021.736-**"),
    ("SOFIA ALMEIDA PRADO", "***.847.390-**"),
]
TIPOS = [
    "Procuração", "Contrato de Honorários", "Declaração de Hipossuficiência",
    "Substabelecimento", "Acordo Extrajudicial", "Termo de Confidencialidade",
    "Notificação Extrajudicial", "Recibo de Repasse", "Ata de Reunião",
]


def _pdf_simples(titulo, linhas, marca="DEMONSTRAÇÃO"):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    largura, altura = A4
    c.setFont("Times-Roman", 20)
    c.drawString(70, altura - 100, titulo)
    c.setFont("Helvetica", 10)
    y = altura - 140
    for linha in linhas:
        c.drawString(70, y, linha)
        y -= 16
    c.setFont("Helvetica-Bold", 44)
    c.setFillGray(0.92)
    c.saveState()
    c.translate(largura / 2, altura / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, marca)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def criar(saida, quantidade=26, semente=7, modo="separado"):
    from .mesclagem import mesclar

    rnd = random.Random(semente)
    saida = Path(saida)
    docs = saida / processo.PASTA_DOCUMENTOS
    aud = saida / processo.PASTA_AUDITORIA
    docs.mkdir(parents=True, exist_ok=True)
    aud.mkdir(parents=True, exist_ok=True)
    registro = {}
    hoje = dt.datetime.now().replace(second=0, microsecond=0)

    for i in range(quantidade):
        tipo = rnd.choice(TIPOS)
        signatarios = rnd.sample(PESSOAS, rnd.choice([1, 1, 1, 2, 2, 3]))
        cliente = signatarios[0][0].split()[0].title()
        nome = f"{tipo} {cliente} {1000 + i}_assinado"
        quando = hoje - dt.timedelta(days=rnd.randint(0, 330), hours=rnd.randint(0, 9))
        sorteio = rnd.random()
        resultado = ("APROVADO" if sorteio < 0.78 else "COM_RESSALVAS" if sorteio < 0.88
                     else "SEM_ASSINATURA_RECONHECIDA" if sorteio < 0.93 else "IGNORADO")
        original = _pdf_simples(tipo, [f"Documento fictício nº {1000 + i}", "Gerado para demonstração do painel."])
        h = hashlib.sha256(original).hexdigest()

        if resultado == "IGNORADO":
            registro[h] = {"arquivo": f"{nome}.pdf", "resultado": "IGNORADO",
                           "data_validacao": quando.strftime("%d/%m/%Y %H:%M"), "arquivos_gerados": ""}
            continue

        pasta = aud / f"demo_{i:03d}"
        pasta.mkdir(exist_ok=True)
        (pasta / "original.pdf").write_bytes(original)
        assinaturas = []
        for j, (pessoa, cpf) in enumerate(signatarios):
            status = "Aprovado" if resultado == "APROVADO" or j else rnd.choice(["Indeterminada", "Reprovado"])
            assinada = quando - dt.timedelta(hours=rnd.randint(1, 72))
            assinaturas.append({
                "signatario": pessoa, "status": status, "cpf": cpf,
                "certificadora": "Gov-Br" if rnd.random() < 0.8 else "ICP-Brasil",
                "data_assinatura": assinada.strftime("%d/%m/%Y %H:%M:%S BRT"),
                "carimbo_de_tempo": False, "tipo_assinatura": "Destacada",
                "caminho_certificacao": "Aprovado", "estrutura": "Em conformidade com o padrão",
                "cifra": "Aprovada", "emissor": "AC Final do Governo Federal do Brasil v1",
            })
        resumo = {
            "arquivo": f"{nome}.pdf", "sha256_arquivo": h, "validado_em": quando.isoformat(timespec="seconds"),
            "data_validacao_iti": quando.strftime("%d/%m/%Y %H:%M:%S BRT"), "servico": "demonstração",
            "resultado": resultado, "hash_confere": resultado != "SEM_ASSINATURA_RECONHECIDA",
            "assinaturas": assinaturas if resultado != "SEM_ASSINATURA_RECONHECIDA" else [],
            "iti": {"verificador": "Verificador de Conformidade 2.32.1",
                    "validador": "Validador de Documentos 3.5.2", "tipo_arquivo": "PDF"},
            "modo": modo, "demonstracao": True,
        }
        arquivos = {"original": f"{processo.PASTA_AUDITORIA}/{pasta.name}/original.pdf"}
        if resultado == "SEM_ASSINATURA_RECONHECIDA":
            resumo["detalhe"] = "O VALIDAR não reconheceu assinatura ICP-Brasil ou GOV.BR no arquivo."
        else:
            rel = pasta / f"{processo.NOME_RELATORIO}.pdf"
            rel.write_bytes(_pdf_simples("Relatório de conformidade (demonstração)", [
                "Este não é um relatório do ITI.", f"Arquivo: {nome}.pdf", f"SHA-256: {h[:32]}…"]))
            sufixo = "" if resultado == "APROVADO" else " (COM RESSALVAS)"
            arquivos["relatorio"] = f"{processo.PASTA_AUDITORIA}/{pasta.name}/{rel.name}"
            if modo == "mesclado":
                mesclado = docs / f"{nome} - com {processo.NOME_RELATORIO}{sufixo}.pdf"
                mesclar(pasta / "original.pdf", rel, mesclado, f"{nome}.pdf")
                arquivos["mesclado"] = f"{processo.PASTA_DOCUMENTOS}/{mesclado.name}"
            else:
                copia = docs / f"{nome}.pdf"
                copia.write_bytes(original)
                rel_vis = docs / f"{nome} - {processo.NOME_RELATORIO}{sufixo}.pdf"
                rel_vis.write_bytes(rel.read_bytes())
                arquivos.update(original=f"{processo.PASTA_DOCUMENTOS}/{copia.name}",
                                relatorio=f"{processo.PASTA_DOCUMENTOS}/{rel_vis.name}")
        resumo["arquivos"] = arquivos
        (pasta / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
        registro[h] = {"arquivo": resumo["arquivo"], "resultado": resultado,
                       "data_validacao": quando.strftime("%d/%m/%Y %H:%M"), "arquivos_gerados": ""}

    (aud / "registro.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    entrada = saida.parent / "A validar (demonstração)"
    entrada.mkdir(exist_ok=True)
    for k in range(3):
        (entrada / f"Documento aguardando {k + 1}.pdf").write_bytes(
            _pdf_simples("Aguardando validação", [f"Arquivo fictício {k + 1}"]))
    return saida, entrada
