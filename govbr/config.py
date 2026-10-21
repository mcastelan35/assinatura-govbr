"""Configuração do usuário e pastas sugeridas (incluindo Google Drive)."""

import json
import os
import sys
from pathlib import Path

MODOS = ("separado", "mesclado")


def pasta_config():
    """Fora da pasta do plugin, para sobreviver a atualizações e reinstalações.

    hooks/verificar_config.sh repete estes caminhos: mantenha os dois iguais.
    """
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


def pastas_google_drive():
    """Raízes do Google Drive para computador: Meu Drive e cada Drive compartilhado."""
    raizes = []
    if os.name == "nt":
        from string import ascii_uppercase

        for letra in ascii_uppercase[3:]:  # D: em diante
            if any(Path(f"{letra}:/{meu}").is_dir() for meu in ("Meu Drive", "My Drive")):
                raizes.append(Path(f"{letra}:/"))
    else:
        nuvem = Path.home() / "Library" / "CloudStorage"
        raizes += sorted(nuvem.glob("GoogleDrive-*")) if nuvem.is_dir() else []

    resultado = {"meu_drive": None, "compartilhados": []}
    for raiz in raizes:
        for meu in ("Meu Drive", "My Drive"):
            if (raiz / meu).is_dir() and not resultado["meu_drive"]:
                resultado["meu_drive"] = str(raiz / meu)
        for compart in ("Drives compartilhados", "Shared drives"):
            if (raiz / compart).is_dir():
                try:
                    resultado["compartilhados"] += sorted(
                        str(p) for p in (raiz / compart).iterdir() if p.is_dir()
                    )
                except OSError:
                    pass
    return resultado


def sugestoes_de_pastas():
    sugestoes = []
    drive = pastas_google_drive()
    # Drive compartilhado primeiro: os documentos ficam com o escritório, não com uma pessoa.
    for raiz in drive["compartilhados"]:
        sugestoes.append({"origem": f"Google Drive compartilhado ({Path(raiz).name})", "raiz": raiz})
    if drive["meu_drive"]:
        sugestoes.append({"origem": "Google Drive (Meu Drive)", "raiz": drive["meu_drive"]})
    sugestoes.append({"origem": "Somente este computador (Documentos)", "raiz": str(pasta_documentos())})
    for s in sugestoes:
        base = Path(s.pop("raiz")) / "Assinaturas GOV.BR"
        s["entrada"] = str(base / "A validar")
        s["saida"] = str(base / "Validados")
    return {
        "google_drive_instalado": bool(drive["meu_drive"] or drive["compartilhados"]),
        "sugestoes": sugestoes,
    }


def nuvem(caminho):
    """Nome do serviço de sincronização da pasta, ou None se for local."""
    texto = str(caminho).lower()
    drive = pastas_google_drive()
    raizes_drive = [drive["meu_drive"], *drive["compartilhados"]]
    if any(r and texto.startswith(str(Path(r).parent).lower()) for r in raizes_drive):
        return "Google Drive"
    for marca, nome in (
        ("google drive", "Google Drive"), ("googledrive", "Google Drive"), ("meu drive", "Google Drive"),
        ("my drive", "Google Drive"), ("onedrive", "OneDrive"), ("dropbox", "Dropbox"), ("icloud", "iCloud"),
    ):
        if marca in texto:
            return nome
    return None
