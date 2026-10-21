#!/usr/bin/env python3
"""
Validador automático de assinaturas GOV.BR / ICP-Brasil pelo VALIDAR do ITI.

Envia os documentos assinados ao validar.iti.gov.br, guarda as respostas do ITI
para auditoria e entrega o Relatório de Conformidade oficial em PDF — separado
do documento ou mesclado com ele, conforme a configuração.

ATENÇÃO: usa a API interna do portal VALIDAR (não documentada pelo ITI). Pode
mudar sem aviso. Ao usar, você aceita os termos do VALIDAR (Portaria ITI nº 22/2023).

Comandos:
    configurar --entrada PASTA --saida PASTA --modo separado|mesclado
    mostrar-config
    sugerir-pastas
    escolher-pasta [--titulo TEXTO]
    diagnostico
    validar                      valida os documentos novos da pasta de entrada
    validar ARQUIVO              valida um arquivo avulso
    validar --entrada P --saida P --modo M   (sobrepõe a configuração)

Códigos de saída do comando validar:
    0  todos os documentos enviados foram aprovados (ou não havia nada novo)
    1  algum documento com ressalvas ou sem assinatura reconhecida
    2  erro (rede, VALIDAR fora do ar, configuração ou arquivo inválido)

Dependências: biblioteca padrão do Python 3.9+; o modo "mesclado" usa pypdf.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "https://validar.iti.gov.br"
TIMEOUT = 300  # documentos com muitas assinaturas demoram
PAUSA_LOTE = 2  # segundos entre documentos, para não sobrecarregar o serviço público
TENTATIVAS = 3  # para instabilidades temporárias (408/502/503 e falhas de rede)
STATUS_TEMPORARIO = {408, 502, 503, 504}

# O backend recusa (401) requisições sem Origin/Referer do próprio portal.
HEADERS = {
    "Origin": BASE,
    "Referer": BASE + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) assinatura-govbr/1.0",
}

EXTENSOES_ASSINATURA = {".pdf", ".xml", ".p7s", ".json"}
EXTENSOES_DESTACADA = {".p7s", ".jws", ".xml", ".p7m", ".json"}
MODOS = ("separado", "mesclado")
IDIOMAS = ("portuga", "ingles", "espanhol")  # valores aceitos pelo /downloadPdf

MENSAGENS_HTTP = {
    400: "Documento sem assinatura reconhecível ou com assinatura corrompida.",
    401: "Não autorizado (o portal pode ter mudado a checagem de origem).",
    403: "Não autorizado.",
    404: "Recurso não encontrado (a API pode ter mudado).",
    408: "Tempo esgotado no servidor do ITI. Tente novamente mais tarde.",
    415: "Tipo de arquivo não suportado.",
    422: "Documento inválido.",
    500: "Erro interno do VALIDAR ao processar o arquivo.",
    502: "Instabilidade no VALIDAR. Tente novamente mais tarde.",
    503: "VALIDAR indisponível. Tente novamente mais tarde.",
}

ROTULOS = {
    "APROVADO": "",
    "COM_RESSALVAS": "COM RESSALVAS",
    "SEM_ASSINATURA_RECONHECIDA": "SEM ASSINATURA RECONHECIDA",
    "SEM_ASSINATURA_OU_CORROMPIDA": "SEM ASSINATURA OU CORROMPIDA",
}

NOME_RELATORIO = "Relatório de Conformidade ITI"
NOME_PLANILHA = "Validações.csv"
PASTA_AUDITORIA = "_auditoria"


class ErroValidar(Exception):
    pass


def _abortar(mensagem):
    print(f"ERRO: {mensagem}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------- configuração


def pasta_config():
    """Fora da pasta do plugin, para sobreviver a atualizações e reinstalações."""
    if os.environ.get("ASSINATURA_GOVBR_CONFIG_DIR"):
        return Path(os.environ["ASSINATURA_GOVBR_CONFIG_DIR"])
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "AssinaturaGovBr"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AssinaturaGovBr"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "assinatura-govbr"


def arquivo_config():
    return pasta_config() / "config.json"


def ler_config():
    caminho = arquivo_config()
    if not caminho.is_file():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def salvar_config(cfg):
    caminho = arquivo_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


def pasta_documentos():
    """Pasta Documentos do usuário (no Windows, a real, mesmo redirecionada ao OneDrive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_PERSONAL = 5 (Documentos)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
                return Path(buf.value)
        except Exception:
            pass
    docs = Path.home() / "Documents"
    return docs if docs.is_dir() else Path.home()


def em_nuvem(caminho):
    """Heurística: pastas sincronizadas expõem dados de clientes a outro serviço."""
    texto = str(caminho).lower()
    return any(
        marca in texto
        for marca in ("onedrive", "google drive", "googledrive", "dropbox", "icloud", "my drive", "meu drive")
    )


# ---------------------------------------------------------------- HTTP / VALIDAR


def _request_uma_vez(url, data, content_type):
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in HEADERS.items():
        req.add_header(k, v)
    req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise ErroValidar(f"Falha de conexão com o VALIDAR: {getattr(e, 'reason', e)}") from e


def _request(url, data, content_type):
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            status, corpo = _request_uma_vez(url, data, content_type)
        except ErroValidar:
            if tentativa == TENTATIVAS:
                raise
        else:
            if status not in STATUS_TEMPORARIO or tentativa == TENTATIVAS:
                return status, corpo
        time.sleep(5 * tentativa)


def _multipart(campos):
    """campos: lista de (nome_do_campo, Path)."""
    boundary = "----validar" + uuid.uuid4().hex
    partes = []
    for nome, caminho in campos:
        mime = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
        partes.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{nome}"; filename="{caminho.name}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode("utf-8")
            + caminho.read_bytes()
            + b"\r\n"
        )
    corpo = b"".join(partes) + f"--{boundary}--\r\n".encode()
    return corpo, f"multipart/form-data; boundary={boundary}"


def _post_json(caminho, payload):
    status, corpo = _request(
        BASE + caminho, json.dumps(payload).encode("utf-8"), "application/json"
    )
    if status != 200:
        raise ErroValidar(
            f"{caminho} respondeu HTTP {status}: {MENSAGENS_HTTP.get(status, corpo[:200])}"
        )
    return corpo


def validar_arquivo(assinatura, destacado=None):
    """POST /arquivo. Retorna (status_http, json_bruto)."""
    if destacado:
        campos = [("signature_files[]", assinatura), ("detached_files[]", destacado)]
    else:
        campos = [("signature_files[]", assinatura)]
    corpo, ctype = _multipart(campos)
    status, resposta = _request(BASE + "/arquivo", corpo, ctype)

    if status in (200, 206, 406):
        try:
            dados = json.loads(resposta)
        except ValueError as e:
            raise ErroValidar(f"Resposta inesperada do VALIDAR (HTTP {status}).") from e
        # 206 = validação parcial (muitas assinaturas); o relatório vem em "json".
        if status == 206:
            dados = dados.get("json", dados)
        return status, dados
    if status == 400:
        # Não é falha do serviço: o arquivo não tem assinatura legível.
        return status, {"errorCode": 400}

    raise ErroValidar(f"HTTP {status}: {MENSAGENS_HTTP.get(status, 'erro desconhecido')}")


def relatorio_simples(bruto):
    return json.loads(_post_json("/simples", bruto))


def relatorio_conformidade(bruto):
    return json.loads(_post_json("/conformidade", bruto))


def baixar_pdf(conformidade, idioma="portuga"):
    pdf = _post_json(
        "/downloadPdf", {"data": json.dumps(conformidade), "language": idioma}
    )
    if not pdf.startswith(b"%PDF"):
        raise ErroValidar("O VALIDAR não devolveu um PDF válido.")
    return pdf


# ---------------------------------------------------------------- validação de um documento


def sha256(dados):
    return hashlib.sha256(dados).hexdigest()


def _nome_seguro(texto):
    return re.sub(r"[^\w.-]+", "_", texto).strip("_")[:80] or "documento"


def _nome_arquivo(texto):
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


def processar(assinatura, destacado=None, auditoria=Path("."), idioma="portuga"):
    """Valida no ITI e grava as evidências em auditoria/<doc>_<data-hora>/."""
    agora = dt.datetime.now()
    pasta = _pasta_livre(auditoria / f"{_nome_seguro(assinatura.stem)}_{agora:%Y%m%d-%H%M%S}")
    pasta.mkdir(parents=True)

    resumo = {
        "arquivo": assinatura.name,
        "caminho_original": str(assinatura),
        "sha256_arquivo": sha256(assinatura.read_bytes()),
        "arquivo_destacado": destacado.name if destacado else None,
        "sha256_destacado": sha256(destacado.read_bytes()) if destacado else None,
        "validado_em": agora.isoformat(timespec="seconds"),
        "servico": BASE,
    }

    status, bruto = validar_arquivo(assinatura, destacado)
    _salvar_json(pasta, "01_validacao_bruta.json", bruto)
    resumo["http_validacao"] = status

    if status in (400, 406):
        resultado = "SEM_ASSINATURA_OU_CORROMPIDA" if status == 400 else "SEM_ASSINATURA_RECONHECIDA"
        detalhe = (
            MENSAGENS_HTTP[400] if status == 400
            else "O VALIDAR não reconheceu assinatura ICP-Brasil ou GOV.BR no arquivo."
        )
        resumo.update(resultado=resultado, detalhe=detalhe, assinaturas=[])
        if status == 406:
            resumo["protocolo_iti"] = {k: bruto.get(k) for k in ("hash", "date")}
        _salvar_json(pasta, "resumo.json", resumo)
        return pasta, resumo, None

    simples = relatorio_simples(bruto)
    _salvar_json(pasta, "02_relatorio_simples.json", simples)

    conformidade = relatorio_conformidade(bruto)
    _salvar_json(pasta, "03_relatorio_conformidade.json", conformidade)

    pdf = baixar_pdf(conformidade, idioma)
    relatorio = pasta / f"{NOME_RELATORIO}.pdf"
    relatorio.write_bytes(pdf)

    assinaturas = [
        {
            "signatario": a.get("nome"),
            "status": a.get("status"),
            "certificadora": a.get("certificadora"),
            "cpf": a.get("cpf"),  # já vem mascarado pelo ITI
            "data_assinatura": a.get("data"),
            "carimbo_de_tempo": a.get("possuiCarimboTempo"),
        }
        for a in simples.get("assinaturas", [])
    ]
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
    )
    _salvar_json(pasta, "resumo.json", resumo)
    return pasta, resumo, relatorio


# ---------------------------------------------------------------- entrega (separado / mesclado)


def _destino_livre(pasta, nome):
    destino = pasta / nome
    n = 1
    while destino.exists():
        n += 1
        destino = pasta / f"{Path(nome).stem} ({n}){Path(nome).suffix}"
    return destino


def mesclar(documento, relatorio, destino):
    """Cria um PDF novo: páginas do documento + páginas do relatório do ITI.

    O PDF mesclado é uma CÓPIA para leitura/protocolo: a assinatura digital
    original não sobrevive à mesclagem (qualquer alteração invalida o hash).
    Por isso os campos de assinatura são removidos — evita que leitores
    exibam "assinatura inválida" — e o original permanece intacto na entrada.
    """
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import ArrayObject, NameObject
    except ImportError as e:
        raise ErroValidar(
            "O modo mesclado precisa do pacote pypdf (rode pelo plugin, com uv, ou: pip install pypdf)."
        ) from e

    def eh_assinatura(anot):
        obj = anot.get_object()
        if obj.get("/FT") == "/Sig":
            return True
        pai = obj.get("/Parent")
        return pai is not None and pai.get_object().get("/FT") == "/Sig"

    w = PdfWriter()
    marcadores = []
    for titulo, origem in (("Documento assinado", documento), (NOME_RELATORIO, relatorio)):
        marcadores.append((titulo, len(w.pages)))
        for pagina in PdfReader(str(origem)).pages:
            # Filtra antes de copiar: assim o dicionário da assinatura nem entra no arquivo novo.
            if "/Annots" in pagina:
                restantes = [a for a in pagina["/Annots"] if not eh_assinatura(a)]
                if restantes:
                    pagina[NameObject("/Annots")] = ArrayObject(restantes)
                else:
                    del pagina["/Annots"]
            w.add_page(pagina)
    for titulo, indice in marcadores:
        w.add_outline_item(titulo, indice)
    w.add_metadata({
        "/Title": f"{documento.stem} - com {NOME_RELATORIO}",
        "/Subject": (
            "Cópia do documento seguida do Relatório de Conformidade do VALIDAR/ITI. "
            "A assinatura digital vale no arquivo original."
        ),
        "/Producer": "assinatura-govbr",
    })
    with open(destino, "wb") as f:
        w.write(f)


def entregar(original, resumo, relatorio, saida, modo):
    """Gera os arquivos finais na pasta de saída. Retorna a lista de nomes."""
    if relatorio is None:
        return []
    rotulo = ROTULOS.get(resumo["resultado"], resumo["resultado"])
    sufixo = f" ({rotulo})" if rotulo else ""
    base = _nome_arquivo(original.stem)

    if modo == "mesclado":
        destino = _destino_livre(saida, f"{base} - com {NOME_RELATORIO}{sufixo}.pdf")
        mesclar(original, relatorio, destino)
        return [destino.name]

    copia = _destino_livre(saida, f"{base}{original.suffix}")
    shutil.copy2(original, copia)
    # O relatório acompanha o nome da cópia (inclusive o "(2)" de homônimos).
    rel = _destino_livre(saida, f"{copia.stem} - {NOME_RELATORIO}{sufixo}.pdf")
    shutil.copy2(relatorio, rel)
    return [copia.name, rel.name]


# ---------------------------------------------------------------- lote, registro e planilha


def pdf_tem_assinatura(caminho):
    """Pré-filtro local: só PDFs com dicionário de assinatura vão ao ITI."""
    dados = caminho.read_bytes()
    # /ByteRange é obrigatório em toda assinatura PDF; /ObjStm pode escondê-lo
    # dentro de stream comprimido, então nesse caso o arquivo é enviado mesmo assim.
    return b"/ByteRange" in dados or b"/ObjStm" in dados


def _ler_registro(caminho):
    if caminho.is_file():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {}


COLUNAS_CSV = [
    "data_validacao", "arquivo", "resultado", "qtd_assinaturas", "signatarios",
    "status_assinaturas", "certificadoras", "datas_assinatura", "carimbo_de_tempo",
    "assinaturas_desconhecidas", "hash_confere", "sha256_arquivo", "arquivos_gerados",
    "auditoria", "caminho_original", "detalhe",
]


def _linha_csv(caminho, resumo=None, gerados=(), auditoria="", resultado=None, detalhe=""):
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
        self.saida = saida
        self.auditoria = saida / PASTA_AUDITORIA
        self.auditoria.mkdir(parents=True, exist_ok=True)
        self.caminho_registro = self.auditoria / "registro.json"
        self.registro = _ler_registro(self.caminho_registro)

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


def validar_um(caminho, lote, modo, idioma, destacado=None):
    pasta_aud, resumo, relatorio = processar(caminho, destacado, lote.auditoria, idioma)
    gerados = entregar(caminho, resumo, relatorio, lote.saida, modo)
    return _linha_csv(caminho, resumo, gerados, pasta_aud.relative_to(lote.saida))


def listar_pdfs(entrada, recursivo):
    candidatos = entrada.rglob("*") if recursivo else entrada.glob("*")
    return sorted(
        p for p in candidatos
        if p.is_file() and p.suffix.lower() == ".pdf" and not p.name.startswith("~$")
    )


def validar_pasta(entrada, lote, modo, idioma, recursivo=False, refazer=False):
    saida_res = lote.saida.resolve()
    # Saída dentro da entrada faria o lote validar os próprios relatórios.
    arquivos = [p for p in listar_pdfs(entrada, recursivo) if saida_res not in p.resolve().parents]

    novos = []
    for p in arquivos:
        h = sha256(p.read_bytes())
        if refazer or not lote.ja_validado(h):
            novos.append((p, h))
    print(f"{len(arquivos)} PDF(s) na pasta de entrada, {len(novos)} novo(s).")

    linhas = []
    enviados = 0
    for caminho, h in novos:
        if not pdf_tem_assinatura(caminho):
            linha = _linha_csv(
                caminho, resultado="IGNORADO",
                detalhe="PDF sem assinatura digital embutida; não enviado ao ITI.",
            )
            print(f"  {caminho.name}: IGNORADO (sem assinatura digital)")
        else:
            if enviados:
                time.sleep(PAUSA_LOTE)
            enviados += 1
            print(f"  {caminho.name} ... ", end="", flush=True)
            try:
                linha = validar_um(caminho, lote, modo, idioma)
                print(linha["resultado"])
            except ErroValidar as e:
                linha = _linha_csv(caminho, resultado="ERRO", detalhe=str(e))
                print(f"ERRO: {e}")
        lote.registrar(h, linha)
        linhas.append(linha)
    return linhas


def _imprimir_linha(linha):
    print(f"Resultado: {linha['resultado']}")
    if linha["signatarios"]:
        for nome, status, cert, data in zip(
            linha["signatarios"].split(" | "),
            linha["status_assinaturas"].split(" | "),
            linha["certificadoras"].split(" | "),
            linha["datas_assinatura"].split(" | "),
        ):
            print(f"  - {nome} ({cert}, {data}): {status}")
    if linha["detalhe"]:
        print(f"  {linha['detalhe']}")
    for g in filter(None, linha["arquivos_gerados"].split(" | ")):
        print(f"  arquivo gerado: {g}")


def _codigo_saida(linhas):
    enviados = [l for l in linhas if l["resultado"] != "IGNORADO"]
    if any(l["resultado"] == "ERRO" for l in enviados):
        return 2
    return 0 if all(l["resultado"] == "APROVADO" for l in enviados) else 1


# ---------------------------------------------------------------- comandos


def cmd_configurar(args):
    atual = ler_config() or {}
    cfg = {
        "entrada": str(Path(args.entrada).expanduser().resolve()) if args.entrada else atual.get("entrada"),
        "saida": str(Path(args.saida).expanduser().resolve()) if args.saida else atual.get("saida"),
        "modo": args.modo or atual.get("modo"),
        "recursivo": args.recursivo if args.recursivo is not None else atual.get("recursivo", False),
        "idioma": args.idioma or atual.get("idioma", "portuga"),
    }
    faltando = [k for k in ("entrada", "saida", "modo") if not cfg[k]]
    if faltando:
        _abortar(f"faltam: {', '.join('--' + k for k in faltando)}")
    entrada, saida = Path(cfg["entrada"]), Path(cfg["saida"])
    if entrada == saida:
        _abortar("a pasta de saída deve ser diferente da pasta de entrada.")
    if entrada in saida.parents and cfg["recursivo"]:
        _abortar("com subpastas ativadas, a saída não pode ficar dentro da entrada.")
    entrada.mkdir(parents=True, exist_ok=True)
    saida.mkdir(parents=True, exist_ok=True)
    caminho = salvar_config(cfg)
    print("Configuração salva.")
    _mostrar(cfg, caminho)
    return 0


def _mostrar(cfg, caminho):
    print(f"  Pasta de entrada (documentos assinados): {cfg['entrada']}")
    print(f"  Pasta de saída (relatórios):             {cfg['saida']}")
    print(f"  Modo: {cfg['modo']}" + (
        " (documento + relatório num PDF só)" if cfg["modo"] == "mesclado"
        else " (cópia do documento + relatório em arquivos separados)"
    ))
    print(f"  Subpastas da entrada: {'sim' if cfg.get('recursivo') else 'não'}")
    print(f"  Arquivo de configuração: {caminho}")
    for rotulo, pasta in (("entrada", cfg["entrada"]), ("saída", cfg["saida"])):
        if em_nuvem(pasta):
            print(f"  AVISO: a pasta de {rotulo} parece sincronizada com a nuvem.")


def cmd_mostrar_config(args):
    cfg = ler_config()
    if not cfg:
        print(f"Não configurado (esperado em {arquivo_config()}).")
        return 3
    if args.json:
        print(json.dumps({**cfg, "arquivo": str(arquivo_config())}, ensure_ascii=False, indent=2))
    else:
        _mostrar(cfg, arquivo_config())
    return 0


def cmd_sugerir_pastas(args):
    base = pasta_documentos() / "Assinaturas GOV.BR"
    print(json.dumps({
        "entrada": str(base / "A validar"),
        "saida": str(base / "Validados"),
        "documentos_na_nuvem": em_nuvem(base),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_escolher_pasta(args):
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        _abortar("janela de seleção indisponível neste Python; informe o caminho digitado.")
    raiz = tkinter.Tk()
    raiz.withdraw()
    raiz.attributes("-topmost", True)
    escolhida = filedialog.askdirectory(title=args.titulo, mustexist=False)
    raiz.destroy()
    if not escolhida:
        print("CANCELADO")
        return 1
    print(str(Path(escolhida).resolve()))
    return 0


def cmd_diagnostico(args):
    ok = True
    print(f"Python {sys.version.split()[0]}")
    try:
        import pypdf

        print(f"pypdf {pypdf.__version__}: ok (modo mesclado disponível)")
    except ImportError:
        print("pypdf: ausente (necessário só para o modo mesclado)")
    cfg = ler_config()
    if cfg:
        print("Configuração: ok")
        _mostrar(cfg, arquivo_config())
        for k in ("entrada", "saida"):
            if not Path(cfg[k]).is_dir():
                ok = False
                print(f"  PROBLEMA: pasta de {k} não existe: {cfg[k]}")
    else:
        ok = False
        print(f"Configuração: ausente ({arquivo_config()})")
    try:
        req = urllib.request.Request(BASE + "/", headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"VALIDAR ({BASE}): acessível (HTTP {r.status})")
    except Exception as e:
        ok = False
        print(f"VALIDAR ({BASE}): inacessível ({e})")
    return 0 if ok else 1


def cmd_validar(args):
    cfg = ler_config() or {}
    saida = Path(args.saida or cfg.get("saida") or "")
    modo = args.modo or cfg.get("modo") or "separado"
    idioma = args.idioma or cfg.get("idioma", "portuga")
    if not str(saida) or str(saida) == ".":
        _abortar("pasta de saída não configurada. Rode 'configurar' ou informe --saida.")
    lote = Lote(saida)

    if args.arquivo:
        arquivo = Path(args.arquivo)
        if not arquivo.is_file():
            _abortar(f"arquivo não encontrado: {arquivo}")
        exts = EXTENSOES_DESTACADA if args.destacado else EXTENSOES_ASSINATURA
        if arquivo.suffix.lower() not in exts:
            _abortar(f"extensão não aceita: {arquivo.suffix} (aceitas: {', '.join(sorted(exts))})")
        destacado = Path(args.destacado) if args.destacado else None
        if destacado and not destacado.is_file():
            _abortar(f"arquivo não encontrado: {destacado}")
        if modo == "mesclado" and (destacado or arquivo.suffix.lower() != ".pdf"):
            modo = "separado"  # só dá para mesclar quando o próprio arquivo é o PDF
        try:
            linha = validar_um(arquivo, lote, modo, idioma, destacado)
        except ErroValidar as e:
            linha = _linha_csv(arquivo, resultado="ERRO", detalhe=str(e))
        lote.registrar(sha256(arquivo.read_bytes()), linha)
        _imprimir_linha(linha)
        print(f"Pasta de saída: {saida}")
        return _codigo_saida([linha])

    entrada = Path(args.entrada or cfg.get("entrada") or "")
    if not str(entrada) or str(entrada) == "." or not entrada.is_dir():
        _abortar(f"pasta de entrada não encontrada: {entrada}. Rode 'configurar' ou informe --entrada.")
    recursivo = args.recursivo if args.recursivo is not None else cfg.get("recursivo", False)
    linhas = validar_pasta(entrada, lote, modo, idioma, recursivo, args.refazer)

    contagem = {}
    for l in linhas:
        contagem[l["resultado"]] = contagem.get(l["resultado"], 0) + 1
    if linhas:
        print("\nResumo: " + ", ".join(f"{k}: {v}" for k, v in sorted(contagem.items())))
        print(f"Planilha: {saida / NOME_PLANILHA}")
    else:
        print("Nada novo para validar.")
    print(f"Pasta de saída: {saida}")
    return _codigo_saida(linhas)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        # Acentos legíveis no terminal do Windows e na saída capturada pelo Claude Code.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Valida assinaturas GOV.BR/ICP-Brasil no VALIDAR do ITI e entrega o relatório oficial."
    )
    sub = ap.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("configurar", help="define pastas e modo de saída")
    p.add_argument("--entrada", help="pasta onde os documentos assinados serão colocados")
    p.add_argument("--saida", help="pasta onde os relatórios serão entregues")
    p.add_argument("--modo", choices=MODOS, help="separado ou mesclado")
    p.add_argument("--recursivo", action=argparse.BooleanOptionalAction, default=None,
                   help="incluir subpastas da entrada")
    p.add_argument("--idioma", choices=IDIOMAS)
    p.set_defaults(func=cmd_configurar)

    p = sub.add_parser("mostrar-config", help="mostra a configuração atual")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_mostrar_config)

    p = sub.add_parser("sugerir-pastas", help="sugere pastas padrão em Documentos")
    p.set_defaults(func=cmd_sugerir_pastas)

    p = sub.add_parser("escolher-pasta", help="abre a janela do sistema para escolher uma pasta")
    p.add_argument("--titulo", default="Escolha a pasta")
    p.set_defaults(func=cmd_escolher_pasta)

    p = sub.add_parser("diagnostico", help="verifica configuração, pastas e acesso ao VALIDAR")
    p.set_defaults(func=cmd_diagnostico)

    p = sub.add_parser("validar", help="valida os documentos novos (ou um arquivo avulso)")
    p.add_argument("arquivo", nargs="?", help="arquivo avulso (.pdf, .xml, .p7s, .json)")
    p.add_argument("--destacado", help="documento original, quando 'arquivo' for assinatura destacada")
    p.add_argument("--entrada", help="sobrepõe a pasta de entrada configurada")
    p.add_argument("--saida", help="sobrepõe a pasta de saída configurada")
    p.add_argument("--modo", choices=MODOS, help="sobrepõe o modo configurado")
    p.add_argument("--recursivo", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--refazer", action="store_true", help="valida de novo o que já foi validado")
    p.add_argument("--idioma", choices=IDIOMAS)
    p.set_defaults(func=cmd_validar)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
