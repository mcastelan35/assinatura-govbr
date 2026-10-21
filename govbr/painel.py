"""Painel de Assinaturas: métricas, busca de pessoas e acesso aos documentos.

Funciona de dois jeitos, com o mesmo HTML:
- estático: "Painel de Assinaturas.html" na pasta de saída, regravado a cada
  validação. Abre em qualquer computador que veja a pasta (ex.: Google Drive),
  com os links relativos aos arquivos. Somente leitura.
- servidor local (comando `painel`): 127.0.0.1, protegido por token. Acrescenta
  download em lote (.zip), dossiê por pessoa, abrir pastas e validar novos.
"""

import datetime as dt
import io
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import CONTATO_ROTULO, CONTATO_URL, CREDITO, VERSAO, processo

NOME_PAINEL = "Painel de Assinaturas.html"
MODELO = Path(__file__).with_name("painel.html")
OCIOSO = 30 * 60  # o servidor se encerra após 30 min sem a página aberta


# ---------------------------------------------------------------- dados


def _iso_de_registro(texto):
    try:
        return dt.datetime.strptime(texto, "%d/%m/%Y %H:%M").isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def coletar(saida, entrada=None, recursivo=False):
    saida = Path(saida)
    por_hash = {}
    for f in (saida / processo.PASTA_AUDITORIA).glob("*/resumo.json"):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        h = r.get("sha256_arquivo")
        if not h:
            continue
        atual = por_hash.get(h)
        if atual and (atual["validado_em"] or "") >= (r.get("validado_em") or ""):
            continue  # fica a validação mais recente do mesmo conteúdo
        pasta = f.parent.relative_to(saida).as_posix()
        arquivos = dict(r.get("arquivos") or {})
        if not arquivos:  # validações da versão 1.0, antes do campo "arquivos"
            for chave, nome in (("relatorio", f"{processo.NOME_RELATORIO}.pdf"), ("original", "original.pdf")):
                if (f.parent / nome).exists():
                    arquivos[chave] = f"{pasta}/{nome}"
        arquivos = {k: v for k, v in arquivos.items() if (saida / v).is_file()}
        por_hash[h] = {
            "id": h[:16],
            "sha256": h,
            "arquivo": r.get("arquivo"),
            "resultado": r.get("resultado"),
            "validado_em": r.get("validado_em"),
            "data_iti": r.get("data_validacao_iti"),
            "hash_confere": r.get("hash_confere"),
            "parcial": bool(r.get("validacao_parcial")),
            "detalhe": r.get("detalhe"),
            "modo": r.get("modo"),
            "iti": r.get("iti") or {},
            "assinaturas": [
                {
                    "nome": a.get("signatario"),
                    "cpf": a.get("cpf"),
                    "certificadora": a.get("certificadora"),
                    "emissor": a.get("emissor"),
                    "status": a.get("status"),
                    "data": a.get("data_assinatura"),
                    "carimbo": bool(a.get("carimbo_de_tempo")),
                }
                for a in r.get("assinaturas") or []
            ],
            "arquivos": arquivos,
            "auditoria": pasta,
            "demo": bool(r.get("demonstracao")),
        }
    for h, item in processo.ler_registro(saida).items():
        if h in por_hash:
            continue
        por_hash[h] = {
            "id": h[:16], "sha256": h, "arquivo": item.get("arquivo"), "resultado": item.get("resultado"),
            "validado_em": _iso_de_registro(item.get("data_validacao")), "assinaturas": [], "arquivos": {},
            "detalhe": ("PDF sem assinatura digital embutida; não foi enviado ao ITI."
                        if item.get("resultado") == "IGNORADO" else None),
        }

    fila = None
    if entrada and Path(entrada).is_dir():
        fila = [p.name for p, _ in processo.pendentes(entrada, saida, recursivo)]
    gerados = sum(
        1 for pasta in (processo.PASTA_DOCUMENTOS, processo.PASTA_PESSOAS)
        if (saida / pasta).is_dir() for p in (saida / pasta).iterdir() if p.is_file()
    )
    return {
        "versao": VERSAO,
        "gerado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "saida": str(saida),
        "saida_nome": saida.name,
        "entrada": str(entrada) if entrada else None,
        "fila": fila,
        "arquivos_gerados": gerados,
        "documentos": sorted(por_hash.values(), key=lambda d: d.get("validado_em") or "", reverse=True),
        "credito": CREDITO,
        "contato_url": CONTATO_URL,
        "contato_rotulo": CONTATO_ROTULO,
    }


def html(dados):
    corpo = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    return MODELO.read_text(encoding="utf-8").replace("__DADOS__", corpo)


def escrever_estatico(saida, entrada=None, recursivo=False):
    """Regrava o painel na pasta de saída (sem token: modo somente leitura)."""
    destino = Path(saida) / NOME_PAINEL
    temp = destino.with_suffix(".tmp")
    temp.write_text(html({**coletar(saida, entrada, recursivo), "servidor": None}), encoding="utf-8")
    os.replace(temp, destino)  # troca atômica: o Drive nunca sincroniza um arquivo pela metade
    return destino


# ---------------------------------------------------------------- ações


def _pessoa_docs(dados, nome, cpf):
    return [
        d for d in dados["documentos"]
        if any((a.get("nome") or "").upper() == nome.upper() and (a.get("cpf") or "") == (cpf or "")
               for a in d["assinaturas"])
    ]


def gerar_dossie_pessoa(saida, nome, cpf):
    from .dossie import montar_dossie_pessoa, nome_proprio

    saida = Path(saida)
    dados = coletar(saida)
    itens = []
    for d in sorted(_pessoa_docs(dados, nome, cpf), key=lambda d: d.get("validado_em") or ""):
        if d["arquivos"].get("dossie"):
            resumo = json.loads((saida / d["auditoria"] / "resumo.json").read_text(encoding="utf-8"))
            itens.append((resumo, saida / d["arquivos"]["dossie"]))
    if not itens:
        raise ValueError("Nenhum dossiê disponível para esta pessoa.")
    pasta = saida / processo.PASTA_PESSOAS
    pasta.mkdir(parents=True, exist_ok=True)
    digitos = "".join(c for c in (cpf or "") if c.isdigit())
    destino = pasta / processo.nome_arquivo(f"{nome_proprio(nome)}{' - ' + digitos if digitos else ''} - Dossiê.pdf")
    montar_dossie_pessoa(nome, cpf, itens, destino)
    return destino


def abrir_no_sistema(caminho, selecionar=False):
    caminho = Path(caminho)
    if os.name == "nt":
        if selecionar:
            subprocess.Popen(["explorer", "/select,", str(caminho)])
        else:
            os.startfile(str(caminho))  # noqa: S606 - pasta escolhida pelo usuário
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(caminho)] if selecionar else ["open", str(caminho)])
    else:
        subprocess.Popen(["xdg-open", str(caminho.parent if selecionar else caminho)])


# ---------------------------------------------------------------- servidor local


class Painel:
    def __init__(self, cfg):
        self.saida = Path(cfg["saida"])
        self.entrada = cfg.get("entrada")
        self.modo = cfg.get("modo", "separado")
        self.idioma = cfg.get("idioma", "portuga")
        self.recursivo = cfg.get("recursivo", False)
        self.token = secrets.token_urlsafe(18)
        self.ultimo_acesso = time.time()
        self.trabalho = {"rodando": False, "linhas": [], "fim": None}
        self.trava = threading.Lock()

    def dados(self):
        d = coletar(self.saida, self.entrada, self.recursivo)
        d["servidor"] = {"token": self.token, "pode_validar": bool(self.entrada)}
        return d

    def arquivo_seguro(self, relativo):
        alvo = (self.saida / relativo).resolve()
        if self.saida.resolve() not in alvo.parents or not alvo.is_file():
            return None
        return alvo

    def validar(self):
        with self.trava:
            if self.trabalho["rodando"]:
                return False
            self.trabalho = {"rodando": True, "linhas": [], "fim": None}

        def registrar(texto):
            self.trabalho["linhas"].append(texto)

        def executar():
            from . import iti

            try:
                lote = processo.Lote(self.saida)
                linhas = processo.validar_pasta(self.entrada, lote, self.modo, self.idioma,
                                                self.recursivo, log=registrar)
                contagem = {}
                for l in linhas:
                    contagem[l["resultado"]] = contagem.get(l["resultado"], 0) + 1
                self.trabalho["fim"] = {"ok": True, "contagem": contagem}
            except (iti.ErroValidar, OSError) as e:
                self.trabalho["fim"] = {"ok": False, "erro": str(e)}
            finally:
                try:
                    escrever_estatico(self.saida, self.entrada, self.recursivo)
                except OSError:
                    pass
                self.trabalho["rodando"] = False

        threading.Thread(target=executar, daemon=True).start()
        return True

    def zip(self, ids, tipos):
        dados = coletar(self.saida)
        escolhidos = [d for d in dados["documentos"] if d["id"] in set(ids)]
        buf = io.BytesIO()
        usados = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for d in escolhidos:
                for tipo in tipos:
                    rel = d["arquivos"].get(tipo)
                    caminho = self.arquivo_seguro(rel) if rel else None
                    if not caminho:
                        continue
                    nome = caminho.name
                    if tipo == "original" and nome.startswith("original."):
                        nome = d["arquivo"]
                    elif tipo == "relatorio" and nome == f"{processo.NOME_RELATORIO}.pdf":
                        nome = f"{Path(d['arquivo']).stem} - {nome}"
                    base, n = nome, 1
                    while nome in usados:
                        n += 1
                        nome = f"{Path(base).stem} ({n}){Path(base).suffix}"
                    usados.add(nome)
                    z.write(caminho, nome)
        return buf.getvalue(), len(escolhidos)


def _cabecalho_anexo(nome, inline=False):
    seguro = "".join(c if c.isascii() and c not in '"\\' else "_" for c in nome)
    return (f'{"inline" if inline else "attachment"}; filename="{seguro}"; '
            f"filename*=UTF-8''{urllib.parse.quote(nome)}")


def _criar_handler(painel, servidor_ref):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _resposta(self, codigo, corpo=b"", tipo="text/plain; charset=utf-8", extras=None):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extras or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _json(self, obj, codigo=200):
            self._resposta(codigo, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")

        def _autorizado(self, consulta):
            # Token na URL e Host local: outras páginas do navegador não alcançam a API.
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost") and secrets.compare_digest(
                (consulta.get("t") or [""])[0], painel.token)

        def _corpo_json(self):
            tamanho = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            consulta = urllib.parse.parse_qs(url.query)
            painel.ultimo_acesso = time.time()
            if not self._autorizado(consulta):
                return self._resposta(403, "Acesso negado. Abra o painel pelo endereço informado pelo Claude.".encode())
            if url.path == "/":
                return self._resposta(200, html(painel.dados()).encode("utf-8"), "text/html; charset=utf-8")
            if url.path == "/api/dados":
                return self._json(painel.dados())
            if url.path == "/api/status":
                return self._json(painel.trabalho)
            if url.path == "/api/ping":
                return self._json({"ok": True})
            if url.path.startswith("/f/"):
                rel = urllib.parse.unquote(url.path[3:])
                alvo = painel.arquivo_seguro(rel)
                if not alvo:
                    return self._resposta(404, "Arquivo não encontrado.".encode())
                baixar = (consulta.get("baixar") or ["0"])[0] == "1"
                nome = (consulta.get("nome") or [alvo.name])[0]
                tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
                return self._resposta(200, alvo.read_bytes(), tipo,
                                      {"Content-Disposition": _cabecalho_anexo(nome, inline=not baixar)})
            return self._resposta(404, b"")

        def do_POST(self):
            url = urllib.parse.urlsplit(self.path)
            consulta = urllib.parse.parse_qs(url.query)
            painel.ultimo_acesso = time.time()
            if not self._autorizado(consulta) or self.headers.get("X-Painel") != "1":
                return self._resposta(403, b"")
            try:
                corpo = self._corpo_json()
                if url.path == "/api/validar":
                    if not painel.entrada:
                        return self._json({"erro": "Pasta de entrada não configurada."}, 400)
                    return self._json({"iniciado": painel.validar()})
                if url.path == "/api/zip":
                    conteudo, n = painel.zip(corpo.get("ids") or [], corpo.get("tipos") or ["original", "dossie"])
                    nome = f"Assinaturas - {n} documento{'s' if n != 1 else ''} - {dt.date.today():%Y-%m-%d}.zip"
                    return self._resposta(200, conteudo, "application/zip",
                                          {"Content-Disposition": _cabecalho_anexo(nome)})
                if url.path == "/api/pessoa":
                    destino = gerar_dossie_pessoa(painel.saida, corpo.get("nome") or "", corpo.get("cpf") or "")
                    return self._json({"arquivo": destino.relative_to(painel.saida).as_posix(),
                                       "nome": destino.name})
                if url.path == "/api/abrir":
                    alvo = corpo.get("alvo")
                    if alvo == "saida":
                        abrir_no_sistema(painel.saida)
                    elif alvo == "entrada" and painel.entrada:
                        abrir_no_sistema(painel.entrada)
                    else:
                        caminho = painel.arquivo_seguro(alvo or "")
                        if not caminho:
                            return self._json({"erro": "Arquivo não encontrado."}, 404)
                        abrir_no_sistema(caminho, selecionar=True)
                    return self._json({"ok": True})
                if url.path == "/api/encerrar":
                    self._json({"ok": True})
                    threading.Thread(target=servidor_ref[0].shutdown, daemon=True).start()
                    return None
            except (ValueError, OSError) as e:
                return self._json({"erro": str(e)}, 400)
            return self._resposta(404, b"")

    return Handler


def servir(cfg, abrir=True, porta=0):
    painel = Painel(cfg)
    ref = []
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), _criar_handler(painel, ref))
    ref.append(servidor)
    url = f"http://127.0.0.1:{servidor.server_address[1]}/?t={painel.token}"

    def vigiar():
        while True:
            time.sleep(30)
            if time.time() - painel.ultimo_acesso > OCIOSO and not painel.trabalho["rodando"]:
                servidor.shutdown()
                return

    threading.Thread(target=vigiar, daemon=True).start()
    print(f"Painel aberto em: {url}", flush=True)
    print("Ele se encerra sozinho 30 minutos depois de fechada a página.", flush=True)
    if abrir:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    print("Painel encerrado.", flush=True)
