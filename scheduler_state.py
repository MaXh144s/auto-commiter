"""Leitura e gravação atômica do estado persistente do agendador."""

import json
import os


def carregar_estado(caminho):
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            estado = json.load(arquivo)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as erro:
        raise OSError("Não foi possível ler o estado do agendamento.") from erro
    if not isinstance(estado, dict):
        raise OSError("O estado salvo do agendamento está inválido.")
    return estado


def salvar_estado_atomico(caminho, estado):
    pasta = os.path.dirname(caminho)
    os.makedirs(pasta, exist_ok=True)
    temporario = f"{caminho}.tmp"
    try:
        with open(temporario, "w", encoding="utf-8", newline="\n") as arquivo:
            json.dump(estado, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except OSError:
        try:
            os.remove(temporario)
        except FileNotFoundError:
            pass
        raise
