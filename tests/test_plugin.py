"""Coerência do pacote do plugin: versões, skills, hook e linha de comando."""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from conftest import RAIZ
from govbr import VERSAO

COMANDO_BASE = 'uv run --no-project --python 3.12 --with pypdf --with reportlab "${CLAUDE_PLUGIN_ROOT}/validar_govbr.py"'


def test_versoes_iguais_em_todos_os_lugares():
    plugin = json.loads((RAIZ / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mercado = json.loads((RAIZ / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    [entrada] = mercado["plugins"]
    assert plugin["version"] == mercado["metadata"]["version"] == entrada["version"] == VERSAO
    assert plugin["name"] == entrada["name"] == "assinatura-govbr"
    assert entrada["source"] == "./"


@pytest.mark.parametrize("skill", ["configurar", "validar", "painel", "agendar"])
def test_skills_tem_cabecalho_e_comando_base(skill):
    texto = (RAIZ / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    cabecalho = texto.split("---")[1]
    assert re.search(rf"^name: {skill}$", cabecalho, re.M)
    assert re.search(r"^description: .{80,}", cabecalho, re.M)
    assert COMANDO_BASE in texto
    # Toda permissão pré-aprovada aponta para o mesmo script.
    for linha in re.findall(r"^\s+- (?:Bash|PowerShell)\((.*)\)$", cabecalho, re.M):
        assert "validar_govbr.py" in linha and "--with reportlab" in linha


def test_hook_procura_a_mesma_pasta_de_configuracao():
    script = (RAIZ / "hooks" / "verificar_config.sh").read_text(encoding="utf-8")
    assert "\r\n" not in script  # CRLF quebraria o bash
    for nome in ("AssinaturaGovBr", "assinatura-govbr", "ASSINATURA_GOVBR_CONFIG_DIR"):
        assert nome in script
    hooks = json.loads((RAIZ / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"]["SessionStart"][0]["matcher"] == "startup"


GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"
BASH = GIT_BASH if os.name == "nt" and os.path.exists(GIT_BASH) else shutil.which("bash")


@pytest.mark.skipif(not BASH, reason="bash indisponível")
def test_hook_avisa_quando_falta_configurar(tmp_path):
    env = {**os.environ, "ASSINATURA_GOVBR_CONFIG_DIR": str(tmp_path), "LOCALAPPDATA": str(tmp_path),
           "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)}
    bash = BASH
    script = str(RAIZ / "hooks" / "verificar_config.sh")
    saida = subprocess.run([bash, script], env=env, capture_output=True, text=True, encoding="utf-8").stdout
    assert json.loads(saida)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert subprocess.run([bash, script], env=env, capture_output=True, text=True).stdout == ""


def _cli(*args, env=None):
    return subprocess.run([sys.executable, str(RAIZ / "validar_govbr.py"), *args], capture_output=True,
                          text=True, encoding="utf-8", env={**os.environ, **(env or {})})


def test_cli_configurar_e_mostrar(tmp_path):
    r = _cli("mostrar-config")
    assert r.returncode == 3
    r = _cli("configurar", "--entrada", str(tmp_path / "e"), "--saida", str(tmp_path / "s"), "--modo", "mesclado")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "s" / "Painel de Assinaturas.html").is_file()
    cfg = json.loads(_cli("mostrar-config", "--json").stdout)
    assert cfg["modo"] == "mesclado" and cfg["entrada"].endswith("e")


def test_cli_recusa_entrada_igual_a_saida(tmp_path):
    r = _cli("configurar", "--entrada", str(tmp_path), "--saida", str(tmp_path), "--modo", "separado")
    assert r.returncode == 2 and "diferente" in r.stderr


def test_cli_versao():
    assert _cli("--version").stdout.strip() == f"assinatura-govbr {VERSAO}"
