"""Leitura e seleção de mensagens de commit com menor frequência."""

import os
import random
import subprocess
from collections import Counter


class CommitLogError(Exception):
    """Falha ao consultar o histórico Git local."""


def normalizar_mensagem(mensagem):
    return str(mensagem or "").strip().casefold()


def montar_assunto(item):
    if isinstance(item, dict):
        tipo = str(item.get("tipo", "chore")).strip()
        mensagem = str(item.get("mensagem", "")).strip()
        return f"{tipo}: {mensagem}".strip()
    return str(item or "").strip()


def contar_frequencias(mensagens_log, banco_mensagens):
    contagens = Counter(
        normalizar_mensagem(mensagem)
        for mensagem in mensagens_log
        if normalizar_mensagem(mensagem)
    )
    resultado = []
    for item in banco_mensagens:
        assunto = montar_assunto(item)
        resultado.append(
            {
                "tipo": item.get("tipo", "chore") if isinstance(item, dict) else "chore",
                "mensagem": item.get("mensagem", "") if isinstance(item, dict) else assunto,
                "assunto": assunto,
                "frequencia": contagens[normalizar_mensagem(assunto)],
            }
        )
    return resultado


def grupo_menos_repetidas(mensagens_log, banco_mensagens):
    frequencias = contar_frequencias(mensagens_log, banco_mensagens)
    if not frequencias:
        return []
    menor_frequencia = min(item["frequencia"] for item in frequencias)
    return [
        item for item in frequencias if item["frequencia"] == menor_frequencia
    ]


def escolher_mensagem(mensagens_log, banco_mensagens):
    grupo = grupo_menos_repetidas(mensagens_log, banco_mensagens)
    return random.choice(grupo) if grupo else None


def escolher_mensagem_diferente(mensagens_log, banco_mensagens, mensagem_anterior):
    """Escolhe a menos repetida que não repita a mensagem anterior."""
    frequencias = contar_frequencias(mensagens_log, banco_mensagens)
    frequencias.sort(key=lambda item: item["frequencia"])
    anterior = normalizar_mensagem(mensagem_anterior)
    minimo_atual = None
    grupo = []
    for item in frequencias:
        if minimo_atual is not None and item["frequencia"] != minimo_atual:
            escolha = [candidato for candidato in grupo if normalizar_mensagem(candidato["assunto"]) != anterior]
            if escolha:
                return random.choice(escolha)
            grupo = []
        minimo_atual = item["frequencia"]
        grupo.append(item)
    escolha = [candidato for candidato in grupo if normalizar_mensagem(candidato["assunto"]) != anterior]
    return random.choice(escolha) if escolha else None


def ler_mensagens_commit(repo_path):
    caminho = str(repo_path or "").strip()
    if not caminho or not os.path.isdir(caminho):
        raise CommitLogError(
            "Não foi possível ler o histórico. Escolha uma pasta de repositório Git válida."
        )

    try:
        resultado = subprocess.run(
            ["git", "log", "--format=%s"],
            cwd=caminho,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=15,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        raise CommitLogError(
            "Não foi possível ler o histórico. Confira se a pasta é um repositório Git válido e se o Git está instalado."
        ) from erro

    if resultado.returncode != 0:
        try:
            verificacao = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=caminho,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=15,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            raiz = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=caminho,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=15,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError) as erro:
            raise CommitLogError(
                "Não foi possível ler o histórico. Confira se a pasta é um repositório Git válido e se o Git está instalado."
            ) from erro
        if verificacao.returncode != 0 and raiz.returncode == 0:
            return []
        raise CommitLogError(
            "Não foi possível ler o histórico. Confira se a pasta é um repositório Git válido e se o Git está instalado."
        )
    return [linha for linha in resultado.stdout.splitlines() if linha.strip()]
