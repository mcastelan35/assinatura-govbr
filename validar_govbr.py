#!/usr/bin/env python3
"""
Validador automático de assinaturas GOV.BR / ICP-Brasil pelo VALIDAR do ITI.

Envia os documentos assinados ao validar.iti.gov.br, guarda as respostas do ITI
para auditoria e entrega o Relatório de Conformidade oficial — separado do
documento ou mesclado a ele —, com um painel para consultar tudo.

ATENÇÃO: usa a API interna do portal VALIDAR (não documentada pelo ITI). Pode
mudar sem aviso. Ao usar, você aceita os termos do VALIDAR (Portaria ITI nº 22/2023).

Comandos:
    configurar --entrada PASTA --saida PASTA --modo separado|mesclado
    mostrar-config
    sugerir-pastas               pastas sugeridas, incluindo Google Drive
    escolher-pasta [--titulo T]
    diagnostico
    validar                      valida os documentos novos da pasta de entrada
    validar ARQUIVO              valida um arquivo avulso
    painel                       abre o painel (servidor local, com downloads em lote)
    painel --estatico            só regrava "Painel de Assinaturas.html" na saída
    demo [--pasta P]             painel com dados fictícios

Códigos de saída do comando validar:
    0  todos os documentos enviados foram aprovados (ou não havia nada novo)
    1  algum documento com ressalvas ou sem assinatura reconhecida
    2  erro (rede, VALIDAR fora do ar, configuração ou arquivo inválido)

Dependências: Python 3.9+ e pypdf; reportlab só para o comando demo (o uv instala sozinho).
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from govbr import CREDITO, CONTATO_URL, VERSAO, config, iti, processo


def _abortar(mensagem):
    print(f"ERRO: {mensagem}", file=sys.stderr)
    sys.exit(2)


def _mostrar(cfg, caminho):
    print(f"  Pasta de entrada (documentos assinados): {cfg['entrada']}")
    print(f"  Pasta de saída (relatórios e painel):    {cfg['saida']}")
    print(f"  Modo: {cfg['modo']}" + (
        " (documento assinado + relatório do ITI num PDF só)" if cfg["modo"] == "mesclado"
        else " (cópia do documento e relatório do ITI em arquivos separados)"
    ))
    print(f"  Subpastas da entrada: {'sim' if cfg.get('recursivo') else 'não'}")
    print(f"  Arquivo de configuração: {caminho}")
    for rotulo, pasta in (("entrada", cfg["entrada"]), ("saída", cfg["saida"])):
        servico = config.nuvem(pasta)
        if servico:
            print(f"  Pasta de {rotulo} sincronizada com {servico}: confira quem tem acesso a ela.")


def _painel_estatico(cfg_saida, entrada=None, recursivo=False):
    from govbr import painel

    try:
        return painel.escrever_estatico(cfg_saida, entrada, recursivo)
    except OSError as e:
        print(f"Aviso: não foi possível atualizar o painel ({e}).", file=sys.stderr)
        return None


# ---------------------------------------------------------------- comandos


def cmd_configurar(args):
    atual = config.ler_config() or {}
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
    caminho = config.salvar_config(cfg)
    print("Configuração salva.")
    _mostrar(cfg, caminho)
    painel = _painel_estatico(saida, entrada, cfg["recursivo"])
    if painel:
        print(f"  Painel: {painel}")
    return 0


def cmd_mostrar_config(args):
    cfg = config.ler_config()
    if not cfg:
        print(f"Não configurado (esperado em {config.arquivo_config()}).")
        return 3
    if args.json:
        print(json.dumps({**cfg, "arquivo": str(config.arquivo_config())}, ensure_ascii=False, indent=2))
    else:
        _mostrar(cfg, config.arquivo_config())
    return 0


def cmd_sugerir_pastas(args):
    print(json.dumps(config.sugestoes_de_pastas(), ensure_ascii=False, indent=2))
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
    print(f"assinatura-govbr {VERSAO} · Python {sys.version.split()[0]}")
    for pacote, uso in (("pypdf", "modo mesclado"), ("reportlab", "dados de demonstração")):
        try:
            modulo = __import__(pacote)
            print(f"{pacote} {getattr(modulo, '__version__', getattr(modulo, 'Version', ''))}: ok")
        except ImportError:
            ok = False
            print(f"{pacote}: ausente (necessário para {uso})")
    drive = config.pastas_google_drive()
    print("Google Drive para computador: " + (
        "instalado" if drive["meu_drive"] or drive["compartilhados"] else "não encontrado"))
    cfg = config.ler_config()
    if cfg:
        print("Configuração: ok")
        _mostrar(cfg, config.arquivo_config())
        for k in ("entrada", "saida"):
            if not Path(cfg[k]).is_dir():
                ok = False
                print(f"  PROBLEMA: pasta de {k} não existe: {cfg[k]}")
    else:
        ok = False
        print(f"Configuração: ausente ({config.arquivo_config()})")
    try:
        print(f"VALIDAR ({iti.BASE}): acessível (HTTP {iti.acessivel()})")
    except Exception as e:
        ok = False
        print(f"VALIDAR ({iti.BASE}): inacessível ({e})")
    else:
        api_ok, mensagem = iti.testar_api()
        ok = ok and api_ok
        print(f"Teste da API (arquivo de teste, sem dados pessoais): {mensagem}")
    return 0 if ok else 1


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
        print(f"  arquivo gerado: {processo.PASTA_DOCUMENTOS}/{g}")


def cmd_validar(args):
    cfg = config.ler_config() or {}
    saida = Path(args.saida or cfg.get("saida") or "")
    modo = args.modo or cfg.get("modo") or "separado"
    idioma = args.idioma or cfg.get("idioma", "portuga")
    if not str(saida) or str(saida) == ".":
        _abortar("pasta de saída não configurada. Rode 'configurar' ou informe --saida.")
    lote = processo.Lote(saida)
    entrada_cfg = args.entrada or cfg.get("entrada")
    recursivo = args.recursivo if args.recursivo is not None else cfg.get("recursivo", False)

    if args.arquivo:
        arquivo = Path(args.arquivo)
        if not arquivo.is_file():
            _abortar(f"arquivo não encontrado: {arquivo}")
        exts = processo.EXTENSOES_DESTACADA if args.destacado else processo.EXTENSOES_ASSINATURA
        if arquivo.suffix.lower() not in exts:
            _abortar(f"extensão não aceita: {arquivo.suffix} (aceitas: {', '.join(sorted(exts))})")
        destacado = Path(args.destacado) if args.destacado else None
        if destacado and not destacado.is_file():
            _abortar(f"arquivo não encontrado: {destacado}")
        try:
            with processo.Trava(saida):
                try:
                    linha = processo.validar_um(arquivo, lote, modo, idioma, destacado)
                except iti.ErroValidar as e:
                    linha = processo.linha_csv(arquivo, resultado="ERRO", detalhe=str(e))
                lote.registrar(processo.sha256(arquivo.read_bytes()), linha)
        except iti.ErroValidar as e:  # trava ocupada por outra validação
            _abortar(str(e))
        _imprimir_linha(linha)
        _painel_estatico(saida, entrada_cfg, recursivo)
        print(f"Pasta de saída: {saida}")
        return processo.codigo_saida([linha])

    entrada = Path(entrada_cfg or "")
    if not str(entrada) or str(entrada) == "." or not entrada.is_dir():
        _abortar(f"pasta de entrada não encontrada: {entrada}. Rode 'configurar' ou informe --entrada.")
    try:
        linhas = processo.validar_pasta(entrada, lote, modo, idioma, recursivo, args.refazer)
    except iti.ErroValidar as e:  # trava ocupada por outra validação
        _abortar(str(e))

    contagem = {}
    for l in linhas:
        contagem[l["resultado"]] = contagem.get(l["resultado"], 0) + 1
    if linhas:
        print("\nResumo: " + ", ".join(f"{k}: {v}" for k, v in sorted(contagem.items())))
        print(f"Planilha: {saida / processo.NOME_PLANILHA}")
    else:
        print("Nada novo para validar.")
    painel = _painel_estatico(saida, entrada, recursivo)
    if painel:
        print(f"Painel: {painel}")
    print(f"Pasta de saída: {saida}")
    return processo.codigo_saida(linhas)


def cmd_painel(args):
    from govbr import painel

    cfg = config.ler_config() or {}
    if args.saida:
        cfg = {**cfg, "saida": args.saida, "entrada": args.entrada or None}
    if not cfg.get("saida"):
        _abortar("pasta de saída não configurada. Rode 'configurar' ou informe --saida.")
    if not Path(cfg["saida"]).is_dir():
        _abortar(f"pasta de saída não encontrada: {cfg['saida']}")
    if args.estatico:
        destino = painel.escrever_estatico(cfg["saida"], cfg.get("entrada"), cfg.get("recursivo", False))
        print(f"Painel atualizado: {destino}")
        return 0
    painel.escrever_estatico(cfg["saida"], cfg.get("entrada"), cfg.get("recursivo", False))
    painel.servir(cfg, abrir=not args.sem_abrir, porta=args.porta)
    return 0


def cmd_demo(args):
    from govbr import demo, painel

    # A demonstração segue o formato escolhido na configuração (separado ou mesclado).
    modo = args.modo or (config.ler_config() or {}).get("modo") or "separado"
    base = Path(args.pasta) if args.pasta else Path(tempfile.mkdtemp(prefix="assinatura-govbr-demo-"))
    saida, entrada = demo.criar(base / "Validados (demonstração)", modo=modo)
    print(f"Dados fictícios criados em: {base}")
    cfg = {"saida": str(saida), "entrada": str(entrada), "modo": modo}
    painel.escrever_estatico(saida, entrada)
    if args.estatico:
        print(f"Painel: {saida / painel.NOME_PAINEL}")
        return 0
    painel.servir(cfg, abrir=not args.sem_abrir, porta=args.porta)
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        # Acentos legíveis no terminal do Windows e na saída capturada pelo Claude Code.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Valida assinaturas GOV.BR/ICP-Brasil no VALIDAR do ITI e entrega o relatório oficial.",
        epilog=f"{CREDITO} · {CONTATO_URL}",
    )
    ap.add_argument("--version", action="version", version=f"assinatura-govbr {VERSAO}")
    sub = ap.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("configurar", help="define pastas e modo de saída")
    p.add_argument("--entrada", help="pasta onde os documentos assinados serão colocados")
    p.add_argument("--saida", help="pasta onde os relatórios serão entregues")
    p.add_argument("--modo", choices=config.MODOS, help="separado ou mesclado")
    p.add_argument("--recursivo", action=argparse.BooleanOptionalAction, default=None,
                   help="incluir subpastas da entrada")
    p.add_argument("--idioma", choices=iti.IDIOMAS)
    p.set_defaults(func=cmd_configurar)

    p = sub.add_parser("mostrar-config", help="mostra a configuração atual")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_mostrar_config)

    p = sub.add_parser("sugerir-pastas", help="sugere pastas (Google Drive e Documentos)")
    p.set_defaults(func=cmd_sugerir_pastas)

    p = sub.add_parser("escolher-pasta", help="abre a janela do sistema para escolher uma pasta")
    p.add_argument("--titulo", default="Escolha a pasta")
    p.set_defaults(func=cmd_escolher_pasta)

    p = sub.add_parser("diagnostico", help="verifica dependências, configuração e acesso ao VALIDAR")
    p.set_defaults(func=cmd_diagnostico)

    p = sub.add_parser("validar", help="valida os documentos novos (ou um arquivo avulso)")
    p.add_argument("arquivo", nargs="?", help="arquivo avulso (.pdf, .xml, .p7s, .json)")
    p.add_argument("--destacado", help="documento original, quando 'arquivo' for assinatura destacada")
    p.add_argument("--entrada", help="sobrepõe a pasta de entrada configurada")
    p.add_argument("--saida", help="sobrepõe a pasta de saída configurada")
    p.add_argument("--modo", choices=config.MODOS, help="sobrepõe o modo configurado")
    p.add_argument("--recursivo", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--refazer", action="store_true", help="valida de novo o que já foi validado")
    p.add_argument("--idioma", choices=iti.IDIOMAS)
    p.set_defaults(func=cmd_validar)

    p = sub.add_parser("painel", help="abre o Painel de Assinaturas")
    p.add_argument("--estatico", action="store_true", help="só regrava o HTML na pasta de saída")
    p.add_argument("--sem-abrir", action="store_true", help="não abre o navegador")
    p.add_argument("--porta", type=int, default=0)
    p.add_argument("--saida", help="sobrepõe a pasta de saída configurada")
    p.add_argument("--entrada", help="pasta de entrada, quando --saida é informada")
    p.set_defaults(func=cmd_painel)

    p = sub.add_parser("demo", help="painel com dados fictícios")
    p.add_argument("--pasta", help="onde criar os dados (padrão: pasta temporária)")
    p.add_argument("--modo", choices=config.MODOS, help="padrão: o da configuração")
    p.add_argument("--estatico", action="store_true")
    p.add_argument("--sem-abrir", action="store_true")
    p.add_argument("--porta", type=int, default=0)
    p.set_defaults(func=cmd_demo)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
