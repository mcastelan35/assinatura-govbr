"""Validação de documentos, entrega na pasta de saída, registro e planilha.

Pasta de saída:
    Painel de Assinaturas.html     painel (gerado a cada validação)
    Validações.csv                 histórico, abre no Excel
    Documentos/                    o que o usuário usa no dia a dia
        <nome>.pdf                                  cópia íntegra (modo separado)
        <nome> - Relatório de Conformidade ITI.pdf  relatório oficial (modo separado)
        <nome> - Dossiê de Conformidade.pdf         capa + [documento] + relatório
    Dossiês por pessoa/            gerados sob demanda, pelo painel ou pela linha de comando
    _auditoria/<doc>_<data-hora>/  respostas do ITI, original enviado e resumo.json
"""

import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from . import iti

PASTA_DOCUMENTOS = "Documentos"
PASTA_PESSOAS = "Dossiês por pessoa"
PASTA_AUDITORIA = "_auditoria"
NOME_RELATORIO = "Relatório de Conformidade ITI"
NOME_DOSSIE = "Dossiê de Conformidade"
NOME_PLANILHA = "Validações.csv"
PAUSA_LOTE = 2  # segundos entre documentos, para não sobrecarregar o serviço público

EXTENSOES_ASSINATURA = {".pdf", ".xml", ".p7s", ".json"}
EXTENSOES_DESTACADA = {".p7s", ".jws", ".xml", ".p7m", ".json"}

ROTULOS = {
    "APROVADO": "",
    "COM_RESSALVAS": "COM RESSALVAS",
    "SEM_ASSINATURA_RECONHECIDA": "SEM ASSINATURA RECONHECIDA",
    "SEM_ASSINATURA_OU_CORROMPIDA": "SEM ASSINATURA OU CORROMPIDA",
}


def sha256(dados):
    return hashlib.sha256(dados).hexdigest()


def _nome_seguro(texto):
    return re.sub(r"[^\w.-]+", "_", texto).strip("_")[:80] or "documento"


def nome_arquivo(texto):
    """Mantém acentos e espaços; só remove o que o Windows não aceita."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto).strip(" .")[:150] or "documento"


def _salvar_json(pasta, nome, dados):
    (pasta / nome).write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _pasta_livre(base):
    pasta, n = base, 1
    while pasta.exists():
        n += 1
        pasta = base.with_name(f"{base.name}_{n}")
    return pasta


def destino_livre(pasta, nome):
    destino = pasta / nome
    n = 1
    while destino.exists():
        n += 1
        destino = pasta / f"{Path(nome).stem} ({n}){Path(nome).suffix}"
    return destino


def _cn(dn):
    """'CN=AC Final do Governo..., OU=...' -> 'AC Final do Governo...'."""
    m = re.search(r"CN=([^,]+)", dn or "")
    return m.group(1).strip() if m else (dn or "")


# ---------------------------------------------------------------- validação de um documento


def processar(assinatura, destacado=None, auditoria=Path("."), idioma="portuga"):
    """Valida no ITI e grava as evidências em auditoria/<doc>_<data-hora>/.

    Retorna (pasta, resumo, caminho_do_relatorio_ou_None).
    """
    agora = dt.datetime.now()
    pasta = _pasta_livre(auditoria / f"{_nome_seguro(assinatura.stem)}_{agora:%Y%m%d-%H%M%S}")
    pasta.mkdir(parents=True)
    # Cópia exata do que foi enviado ao ITI: cadeia de custódia, mesmo que a entrada mude.
    shutil.copy2(assinatura, pasta / f"original{assinatura.suffix.lower()}")
    if destacado:
        shutil.copy2(destacado, pasta / f"documento_destacado{destacado.suffix.lower()}")

    resumo = {
        "arquivo": assinatura.name,
        "caminho_original": str(assinatura),
        "sha256_arquivo": sha256(assinatura.read_bytes()),
        "arquivo_destacado": destacado.name if destacado else None,
        "sha256_destacado": sha256(destacado.read_bytes()) if destacado else None,
        "validado_em": agora.isoformat(timespec="seconds"),
        "servico": iti.BASE,
    }

    status, bruto = iti.validar_arquivo(assinatura, destacado)
    _salvar_json(pasta, "01_validacao_bruta.json", bruto)
    resumo["http_validacao"] = status

    if status in (400, 406):
        resultado = "SEM_ASSINATURA_OU_CORROMPIDA" if status == 400 else "SEM_ASSINATURA_RECONHECIDA"
        detalhe = (
            iti.MENSAGENS_HTTP[400] if status == 400
            else "O VALIDAR não reconheceu assinatura ICP-Brasil ou GOV.BR no arquivo."
        )
        resumo.update(resultado=resultado, detalhe=detalhe, assinaturas=[])
        if status == 406:
            resumo["protocolo_iti"] = {k: bruto.get(k) for k in ("hash", "date")}
        _salvar_json(pasta, "resumo.json", resumo)
        return pasta, resumo, None

    simples = iti.relatorio_simples(bruto)
    _salvar_json(pasta, "02_relatorio_simples.json", simples)

    conformidade = iti.relatorio_conformidade(bruto)
    _salvar_json(pasta, "03_relatorio_conformidade.json", conformidade)

    pdf = iti.baixar_pdf(conformidade, idioma)
    relatorio = pasta / f"{NOME_RELATORIO}.pdf"
    relatorio.write_bytes(pdf)

    info = conformidade.get("infoAss") or []
    assinaturas = []
    for i, a in enumerate(simples.get("assinaturas", [])):
        c = info[i] if i < len(info) else {}
        certs = c.get("certUtilizados") or [{}]
        assinaturas.append({
            "signatario": a.get("nome"),
            "status": a.get("status"),
            "certificadora": a.get("certificadora"),
            "cpf": a.get("cpf"),  # já vem mascarado pelo ITI
            "data_assinatura": a.get("data"),
            "carimbo_de_tempo": a.get("possuiCarimboTempo"),
            "tipo_assinatura": c.get("tipoAssinatura"),
            "caminho_certificacao": c.get("caminhoCert"),
            "estrutura": c.get("estrutura"),
            "cifra": c.get("cifra"),
            "alerta": c.get("msgAlerta"),
            "emissor": _cn(certs[0].get("emissor")),
            "certificado_valido_ate": certs[0].get("dataMaxVal"),
        })
    aprovadas = assinaturas and all(a["status"] == "Aprovado" for a in assinaturas)
    resumo.update(
        resultado="APROVADO" if aprovadas else "COM_RESSALVAS",
        status_documento_iti=simples.get("statusDocumento"),
        data_validacao_iti=simples.get("dataValidacao"),
        validacao_parcial=status == 206,
        hash_iti=simples.get("hash"),
        hash_confere=simples.get("hash") == resumo["sha256_arquivo"],
        assinaturas=assinaturas,
        assinaturas_desconhecidas=simples.get("assinaturasNaoAncoradas", 0),
        sha256_relatorio_pdf=sha256(pdf),
        iti={
            "software": conformidade.get("nomeSoftware"),
            "verificador": f"{conformidade.get('nomeVerificador', '')} {conformidade.get('versaoVerificador', '')}".strip(),
            "validador": f"{conformidade.get('nomeValidador', '')} {conformidade.get('versaoValidador', '')}".strip(),
            "tipo_arquivo": conformidade.get("tipoArquivo"),
            "qtd_assinaturas": conformidade.get("qtdAssinaturas"),
            "qtd_ancoradas": conformidade.get("qtdAncoradas"),
        },
    )
    _salvar_json(pasta, "resumo.json", resumo)
    return pasta, resumo, relatorio


# ---------------------------------------------------------------- entrega (separado / mesclado)


def entregar(original, resumo, relatorio, pasta_aud, saida, modo, destacado=None):
    """Gera os arquivos finais em saida/Documentos. Retorna (arquivos, gerados).

    arquivos: caminhos relativos à saída para original, relatório e dossiê
    (o painel usa estes caminhos); gerados: nomes dos arquivos novos visíveis.
    """
    from .dossie import montar_dossie

    def rel(p):
        return p.relative_to(saida).as_posix()

    arquivos = {"original": rel(pasta_aud / f"original{original.suffix.lower()}")}
    if relatorio is None:
        return arquivos, []
    arquivos["relatorio"] = rel(relatorio)

    docs = saida / PASTA_DOCUMENTOS
    docs.mkdir(parents=True, exist_ok=True)
    rotulo = ROTULOS.get(resumo["resultado"], resumo["resultado"])
    sufixo = f" ({rotulo})" if rotulo else ""
    gerados = []

    if modo == "separado":
        copia = destino_livre(docs, nome_arquivo(original.stem) + original.suffix)
        shutil.copy2(original, copia)
        # O relatório e o dossiê acompanham o nome da cópia (inclusive o "(2)" de homônimos).
        rel_vis = destino_livre(docs, f"{copia.stem} - {NOME_RELATORIO}{sufixo}.pdf")
        shutil.copy2(relatorio, rel_vis)
        arquivos.update(original=rel(copia), relatorio=rel(rel_vis))
        gerados += [copia.name, rel_vis.name]
        raiz, incluir_documento = copia.stem, False
    else:
        raiz = nome_arquivo(original.stem)
        incluir_documento = original.suffix.lower() == ".pdf" and not destacado

    dossie = destino_livre(docs, f"{raiz} - {NOME_DOSSIE}{sufixo}.pdf")
    montar_dossie(resumo, original if incluir_documento else None, relatorio, dossie)
    arquivos["dossie"] = rel(dossie)
    gerados.append(dossie.name)
    return arquivos, gerados


# ---------------------------------------------------------------- lote, registro e planilha


def pdf_tem_assinatura(caminho):
    """Pré-filtro local: só PDFs com dicionário de assinatura vão ao ITI."""
    dados = caminho.read_bytes()
    # /ByteRange é obrigatório em toda assinatura PDF; /ObjStm pode escondê-lo
    # dentro de stream comprimido, então nesse caso o arquivo é enviado mesmo assim.
    return b"/ByteRange" in dados or b"/ObjStm" in dados


COLUNAS_CSV = [
    "data_validacao", "arquivo", "resultado", "qtd_assinaturas", "signatarios",
    "status_assinaturas", "certificadoras", "datas_assinatura", "carimbo_de_tempo",
    "assinaturas_desconhecidas", "hash_confere", "sha256_arquivo", "arquivos_gerados",
    "auditoria", "caminho_original", "detalhe",
]


def linha_csv(caminho, resumo=None, gerados=(), auditoria="", resultado=None, detalhe=""):
    linha = dict.fromkeys(COLUNAS_CSV, "")
    linha.update(
        data_validacao=dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        arquivo=caminho.name,
        caminho_original=str(caminho),
        detalhe=detalhe,
    )
    if resumo is None:
        linha["resultado"] = resultado
        return linha

    def juntar(campo):
        return " | ".join(str(a.get(campo) or "") for a in resumo["assinaturas"])

    linha.update(
        resultado=resumo["resultado"],
        qtd_assinaturas=len(resumo["assinaturas"]),
        signatarios=juntar("signatario"),
        status_assinaturas=juntar("status"),
        certificadoras=juntar("certificadora"),
        datas_assinatura=juntar("data_assinatura"),
        carimbo_de_tempo=" | ".join(
            "sim" if a.get("carimbo_de_tempo") else "não" for a in resumo["assinaturas"]
        ),
        assinaturas_desconhecidas=resumo.get("assinaturas_desconhecidas", ""),
        hash_confere={True: "sim", False: "NÃO"}.get(resumo.get("hash_confere"), ""),
        sha256_arquivo=resumo["sha256_arquivo"],
        arquivos_gerados=" | ".join(gerados),
        auditoria=str(auditoria),
        detalhe=detalhe or resumo.get("detalhe", ""),
    )
    if resumo.get("validacao_parcial"):
        linha["detalhe"] = "Validação parcial (documento com muitas assinaturas)."
    return linha


def _anexar_csv(caminho, linhas):
    """Planilha acumulada: ";" e UTF-8 com BOM abrem direto no Excel em português."""
    if not linhas:
        return
    novo = not caminho.exists()
    with open(caminho, "a", newline="", encoding="utf-8-sig" if novo else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_CSV, delimiter=";")
        if novo:
            w.writeheader()
        w.writerows(linhas)


class Lote:
    """Registro do que já foi validado (pelo SHA-256) e planilha acumulada."""

    def __init__(self, saida):
        self.saida = Path(saida)
        self.auditoria = self.saida / PASTA_AUDITORIA
        self.auditoria.mkdir(parents=True, exist_ok=True)
        self.caminho_registro = self.auditoria / "registro.json"
        self.registro = ler_registro(self.saida)

    def ja_validado(self, hash_):
        return hash_ in self.registro

    def registrar(self, hash_, linha):
        if linha["resultado"] != "ERRO":  # erros são tentados de novo na próxima vez
            self.registro[hash_] = {
                k: linha[k] for k in ("arquivo", "resultado", "data_validacao", "arquivos_gerados")
            }
            self.caminho_registro.write_text(
                json.dumps(self.registro, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        # Grava a cada documento para não perder o progresso se o lote cair.
        _anexar_csv(self.saida / NOME_PLANILHA, [linha])


def ler_registro(saida):
    caminho = Path(saida) / PASTA_AUDITORIA / "registro.json"
    if caminho.is_file():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {}


def validar_um(caminho, lote, modo, idioma, destacado=None):
    pasta_aud, resumo, relatorio = processar(caminho, destacado, lote.auditoria, idioma)
    arquivos, gerados = entregar(caminho, resumo, relatorio, pasta_aud, lote.saida, modo, destacado)
    resumo.update(arquivos=arquivos, modo=modo)
    _salvar_json(pasta_aud, "resumo.json", resumo)
    return linha_csv(caminho, resumo, gerados, pasta_aud.relative_to(lote.saida).as_posix())


def listar_pdfs(entrada, recursivo):
    candidatos = Path(entrada).rglob("*") if recursivo else Path(entrada).glob("*")
    return sorted(
        p for p in candidatos
        if p.is_file() and p.suffix.lower() == ".pdf" and not p.name.startswith("~$")
    )


def pendentes(entrada, saida, recursivo=False):
    """PDFs da entrada ainda não validados: [(caminho, sha256)]."""
    saida_res = Path(saida).resolve()
    registro = ler_registro(saida)
    fila = []
    for p in listar_pdfs(entrada, recursivo):
        # Saída dentro da entrada faria o lote validar os próprios relatórios.
        if saida_res in p.resolve().parents:
            continue
        h = sha256(p.read_bytes())
        if h not in registro:
            fila.append((p, h))
    return fila


def validar_pasta(entrada, lote, modo, idioma, recursivo=False, refazer=False, log=print):
    if refazer:
        saida_res = lote.saida.resolve()
        novos = [
            (p, sha256(p.read_bytes())) for p in listar_pdfs(entrada, recursivo)
            if saida_res not in p.resolve().parents
        ]
    else:
        novos = pendentes(entrada, lote.saida, recursivo)
    log(f"{len(novos)} documento(s) novo(s) na pasta de entrada.")

    linhas = []
    enviados = 0
    for caminho, h in novos:
        if not pdf_tem_assinatura(caminho):
            linha = linha_csv(
                caminho, resultado="IGNORADO",
                detalhe="PDF sem assinatura digital embutida; não enviado ao ITI.",
            )
            log(f"  {caminho.name}: IGNORADO (sem assinatura digital)")
        else:
            if enviados:
                time.sleep(PAUSA_LOTE)
            enviados += 1
            try:
                linha = validar_um(caminho, lote, modo, idioma)
            except iti.ErroValidar as e:
                linha = linha_csv(caminho, resultado="ERRO", detalhe=str(e))
            log(f"  {caminho.name}: {linha['resultado']}")
        lote.registrar(h, linha)
        linhas.append(linha)
    return linhas


def codigo_saida(linhas):
    enviados = [l for l in linhas if l["resultado"] != "IGNORADO"]
    if any(l["resultado"] == "ERRO" for l in enviados):
        return 2
    return 0 if all(l["resultado"] == "APROVADO" for l in enviados) else 1
