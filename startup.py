"""
startup.py
Cria/remove o atalho na pasta de Inicialização do Windows
(shell:startup), fazendo o programa abrir sozinho ao ligar o PC,
em modo silencioso (só ícone na bandeja, sem janela).

Funciona tanto rodando via python (.pyw) quanto via .exe gerado com PyInstaller.
"""

import os
import sys

NOME_ATALHO = "AutoCommitter.lnk"


def _pasta_inicializacao():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def _alvo_execucao():
    """Retorna (caminho_executavel, argumentos) apontando para o próprio
    programa — funciona tanto para o .exe compilado quanto para o script.
    Sempre inclui --silencioso, pois esse atalho é usado só na
    inicialização do Windows (nunca deve abrir janela sozinho)."""
    if getattr(sys, "frozen", False):
        # Rodando como .exe compilado (PyInstaller)
        return sys.executable, "--silencioso"
    else:
        # Rodando como script .py — usa pythonw.exe para não abrir console
        pasta_python = os.path.dirname(sys.executable)
        pythonw = os.path.join(pasta_python, "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # fallback
        script_principal = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        return pythonw, f'"{script_principal}" --silencioso'


def instalar_inicializacao():
    caminho_atalho = os.path.join(_pasta_inicializacao(), NOME_ATALHO)
    executavel, argumentos = _alvo_execucao()

    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        atalho = shell.CreateShortCut(caminho_atalho)
        atalho.TargetPath = executavel
        atalho.Arguments = argumentos
        atalho.WorkingDirectory = os.path.dirname(os.path.abspath(__file__))
        atalho.WindowStyle = 7  # minimizado
        atalho.save()
        return True
    except ImportError:
        # fallback sem pywin32: usa um .vbs que chama o programa de forma silenciosa
        caminho_vbs = os.path.join(_pasta_inicializacao(), "AutoCommitter.vbs")
        conteudo = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.Run "{executavel} {argumentos}", 0, False\n'
        )
        with open(caminho_vbs, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return True


def remover_inicializacao():
    for nome in (NOME_ATALHO, "AutoCommitter.vbs"):
        caminho = os.path.join(_pasta_inicializacao(), nome)
        if os.path.exists(caminho):
            os.remove(caminho)


def esta_instalado():
    for nome in (NOME_ATALHO, "AutoCommitter.vbs"):
        if os.path.exists(os.path.join(_pasta_inicializacao(), nome)):
            return True
    return False
