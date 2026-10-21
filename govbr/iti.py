"""Cliente da API interna do VALIDAR (validar.iti.gov.br).

A API não é documentada pelo ITI: os endpoints e campos abaixo são os que o
próprio portal usa (js/services/requestHandler.js). Pode mudar sem aviso.
"""

import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid

from . import VERSAO

BASE = "https://validar.iti.gov.br"
TIMEOUT = 300  # documentos com muitas assinaturas demoram
TENTATIVAS = 3  # para instabilidades temporárias (408/502/503 e falhas de rede)
STATUS_TEMPORARIO = {408, 502, 503, 504}

# O backend recusa (401) requisições sem Origin/Referer do próprio portal.
HEADERS = {
    "Origin": BASE,
    "Referer": BASE + "/",
    "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) assinatura-govbr/{VERSAO}",
}

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


class ErroValidar(Exception):
    pass


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


def acessivel():
    req = urllib.request.Request(BASE + "/", headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status
