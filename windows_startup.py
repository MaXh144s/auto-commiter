"""Integração isolada com a inicialização do usuário no Windows."""

import os
import subprocess
import sys

REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE = "AutoCommitter"


def ler_inicio_com_windows():
    if os.name != "nt":
        return {"disponivel": False, "ativado": False}
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as chave:
            comando, _tipo = winreg.QueryValueEx(chave, REGISTRY_VALUE)
        return {"disponivel": True, "ativado": bool(comando)}
    except FileNotFoundError:
        return {"disponivel": True, "ativado": False}
    except OSError:
        return {
            "disponivel": True,
            "ativado": False,
            "erro": "Não foi possível consultar a inicialização do Windows.",
        }


def _comando_de_inicio():
    if getattr(sys, "frozen", False):
        executavel = sys.executable
        argumentos = [executavel, "--background"]
    else:
        executavel = sys.executable
        pythonw = os.path.join(os.path.dirname(executavel), "pythonw.exe")
        if os.path.isfile(pythonw):
            executavel = pythonw
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        argumentos = [executavel, script, "--background"]
    return subprocess.list2cmdline(argumentos)


def definir_inicio_com_windows(ativado):
    if os.name != "nt":
        return False, "A inicialização automática está disponível apenas no Windows."
    try:
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as chave:
            if ativado:
                winreg.SetValueEx(
                    chave, REGISTRY_VALUE, 0, winreg.REG_SZ, _comando_de_inicio()
                )
            else:
                try:
                    winreg.DeleteValue(chave, REGISTRY_VALUE)
                except FileNotFoundError:
                    pass
    except OSError:
        return False, "Não foi possível atualizar a inicialização do Windows."
    return True, "Inicialização com o Windows atualizada."
