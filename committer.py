"""
committer.py
Responsável por, de fato, alterar o arquivo alvo e rodar os comandos git
para um trabalho (job) específico.
"""

import datetime
import os
import shlex
import subprocess

import config


def _item_mensagem(item):
    """Aceita tanto o formato atual ({"tipo", "mensagem"}) quanto uma
    string pura (banco antigo, sem tipo — assume "chore")."""
    if isinstance(item, dict):
        return item.get("tipo", "chore"), item.get("mensagem", "atualização automática")
    return "chore", str(item)


def _filtrar_banco_por_tipos_selecionados(job):
    banco = job.get("banco_mensagens") or []
    tipos_selecionados = set(job.get("tipos_commit_selecionados") or config.TIPOS_COMMIT_VALIDOS)
    filtrado = [item for item in banco if _item_mensagem(item)[0] in tipos_selecionados]
    # se o filtro zerar tudo (ex: usuário desmarcou os únicos tipos que
    # existem no banco importado), cai pro banco inteiro em vez de sempre
    # usar a mensagem genérica de fallback
    return filtrado or banco


def _proxima_mensagem(job):
    """Escolhe a próxima mensagem do banco (respeitando os tipos de commit
    selecionados no trabalho) e monta a mensagem final no estilo
    'tipo: mensagem' (ex: 'feat: adiciona tela de login') — cada mensagem
    carrega o seu próprio tipo, em vez de um prefixo fixo tipo 'chore: '
    pra tudo, o que deixa o histórico de commits bem mais humano."""
    banco = _filtrar_banco_por_tipos_selecionados(job)

    if not banco:
        prefixo = job.get("prefixo_mensagem") or "chore: "
        return f"{prefixo}atualização automática"

    estado = config.carregar_estado_job(job["id"])
    indice = estado.get("indice_mensagem", 0)

    if job.get("usar_banco_sequencial", True):
        if indice >= len(banco):
            indice = 0
        item = banco[indice]
        estado["indice_mensagem"] = indice + 1
    else:
        import random
        item = random.choice(banco)

    config.salvar_estado_job(job["id"], estado)

    tipo, texto = _item_mensagem(item)
    return f"{tipo}: {texto}"


TIMEOUT_PADRAO_SEGUNDOS = 60

# No Windows, todo subprocess.run() abre uma janelinha de console (o
# "flash" preto do cmd), mesmo com o app rodando --windowed. CREATE_NO_WINDOW
# manda o Windows não criar essa janela pro processo filho (git). Em outros
# SOs esse atributo não existe, então getattr cai pra 0 (sem efeito).
FLAGS_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _rodar(comando, cwd, timeout=TIMEOUT_PADRAO_SEGUNDOS):
    """Roda um comando com timeout. Sem timeout, um 'git push' que pede
    senha interativamente travaria essa thread para sempre — e como o
    agendador roda todos os jobs na mesma thread, isso pararia TODOS os
    trabalhos, não só o que falhou."""
    try:
        resultado = subprocess.run(
            comando,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,  # garante que o git nunca fique esperando input
            creationflags=FLAGS_SEM_JANELA,  # evita o pop-up de console no Windows
        )
        return resultado.returncode, resultado.stdout.strip(), resultado.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", (f"Comando excedeu o tempo limite de {timeout}s "
                        f"(possível pedido de credenciais travado): {' '.join(comando)}")
    except FileNotFoundError:
        return 1, "", (f"Comando não encontrado: '{comando[0]}'. "
                        f"Verifique se o git está instalado e no PATH.")


def _alterar_arquivo(job, mensagem_atual):
    repo = job["repo_path"]
    caminho_arquivo = os.path.join(repo, job["arquivo_alvo"])
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    os.makedirs(os.path.dirname(caminho_arquivo) or repo, exist_ok=True)

    if job.get("modo_conteudo") == "comando_custom" and job.get("comando_custom"):
        # comando customizado é responsável por alterar o repo (ex: script)
        # comando_custom vem como string do campo de texto da GUI — precisa
        # ser dividido em lista de argumentos, senão subprocess.run com
        # shell=False tenta achar um executável com o nome inteiro da string
        # (ex: "python script.py") e sempre falha com FileNotFoundError.
        try:
            comando_lista = shlex.split(job["comando_custom"], posix=(os.name != "nt"))
        except ValueError as exc:
            return False, f"Comando customizado inválido: {exc}"
        codigo, saida, erro = _rodar(comando_lista, repo)
        return codigo == 0, saida or erro

    linha = f"- {agora}"
    if job.get("modo_conteudo") == "mensagens":
        # mensagem_atual vem no formato "tipo: texto" (ex: "feat: adiciona
        # tela de login") — separa pra deixar a linha do arquivo legível,
        # mostrando o tipo entre colchetes em vez de repetir "tipo: " cru
        if ": " in mensagem_atual:
            tipo_atual, texto_puro = mensagem_atual.split(": ", 1)
        else:
            tipo_atual, texto_puro = "chore", mensagem_atual
        linha += f" — [{tipo_atual}] {texto_puro}"

    with open(caminho_arquivo, "a", encoding="utf-8") as f:
        f.write(linha + "\n")

    return True, f"Arquivo atualizado: {caminho_arquivo}"


def obter_data_ultimo_commit(repo_path):
    """Consulta o git log de verdade do repositório pra saber quando foi o
    último commit — em vez de manter um registro à parte, que ficaria
    'zerado' e não saberia de commits feitos antes dessa função existir
    (ou feitos manualmente, fora do programa). Retorna um datetime com
    timezone, ou None se o repo for inválido ou não tiver nenhum commit."""
    if not repo_path or not os.path.isdir(os.path.join(repo_path, ".git")):
        return None

    # %cI = data do commit em ISO 8601 com timezone (ex: 2026-08-19T21:35:00-03:00)
    codigo, saida, erro = _rodar(["git", "log", "-1", "--format=%cI"], repo_path, timeout=15)
    if codigo != 0 or not saida.strip():
        return None

    try:
        return datetime.datetime.fromisoformat(saida.strip())
    except ValueError:
        return None


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