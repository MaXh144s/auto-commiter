"""
committer.py
Responsável por, de fato, alterar o arquivo alvo e rodar os comandos git
para um trabalho (job) específico.
"""

import datetime
import os
import subprocess

import config


def _proxima_mensagem(job):
    banco = job.get("banco_mensagens") or []
    prefixo = job.get("prefixo_mensagem", "")

    if not banco:
        return f"{prefixo}atualização automática"

    estado = config.carregar_estado_job(job["id"])
    indice = estado.get("indice_mensagem", 0)

    if job.get("usar_banco_sequencial", True):
        if indice >= len(banco):
            indice = 0
        mensagem = banco[indice]
        estado["indice_mensagem"] = indice + 1
    else:
        import random
        mensagem = random.choice(banco)

    config.salvar_estado_job(job["id"], estado)
    return f"{prefixo}{mensagem}"


def _rodar(comando, cwd):
    resultado = subprocess.run(
        comando,
        cwd=cwd,
        capture_output=True,
        text=True,
        shell=False
    )
    return resultado.returncode, resultado.stdout.strip(), resultado.stderr.strip()


def _alterar_arquivo(job, mensagem_atual):
    repo = job["repo_path"]
    caminho_arquivo = os.path.join(repo, job["arquivo_alvo"])
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    os.makedirs(os.path.dirname(caminho_arquivo) or repo, exist_ok=True)

    if job.get("modo_conteudo") == "comando_custom" and job.get("comando_custom"):
        # comando customizado é responsável por alterar o repo (ex: script)
        codigo, saida, erro = _rodar(job["comando_custom"], repo)
        return codigo == 0, saida or erro

    linha = f"- {agora}"
    if job.get("modo_conteudo") == "mensagens":
        # usa o texto puro (sem o prefixo tipo "chore: ") na linha do arquivo
        texto_puro = mensagem_atual
        prefixo = job.get("prefixo_mensagem", "")
        if prefixo and texto_puro.startswith(prefixo):
            texto_puro = texto_puro[len(prefixo):]
        linha += f" — {texto_puro}"

    with open(caminho_arquivo, "a", encoding="utf-8") as f:
        f.write(linha + "\n")

    return True, f"Arquivo atualizado: {caminho_arquivo}"


def executar_commit(job):
    """Executa um commit completo para o job. Retorna (sucesso: bool, log: str)."""
    repo = job.get("repo_path", "")
    logs = []

    if not repo or not os.path.isdir(repo):
        return False, "Caminho do repositório inválido ou não configurado."

    if not os.path.isdir(os.path.join(repo, ".git")):
        return False, "A pasta configurada não é um repositório git (falta .git)."

    if job.get("modo_conteudo") == "comando_custom":
        mensagem_commit = job.get("prefixo_mensagem", "chore: ") + "atualização automática"
    else:
        # calcula a mensagem UMA única vez e reaproveita no arquivo e no commit
        mensagem_commit = _proxima_mensagem(job)

    ok, msg = _alterar_arquivo(job, mensagem_commit)
    logs.append(msg)
    if not ok:
        return False, "\n".join(logs)

    codigo, saida, erro = _rodar(["git", "add", "-A"], repo)
    logs.append(saida or erro or "git add ok")
    if codigo != 0:
        return False, "\n".join(logs)

    codigo, saida, erro = _rodar(["git", "commit", "-m", mensagem_commit], repo)
    logs.append(saida or erro)
    if codigo != 0:
        # pode falhar por "nothing to commit" — não é um erro grave
        if "nothing to commit" in (saida + erro).lower():
            return True, "\n".join(logs + ["Nada para commitar neste momento."])
        return False, "\n".join(logs)

    if job.get("push_automatico", True):
        codigo, saida, erro = _rodar(["git", "push"], repo)
        logs.append(saida or erro or "git push ok")
        if codigo != 0:
            return False, "\n".join(logs)

    return True, "\n".join(logs)
