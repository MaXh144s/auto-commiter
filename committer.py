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


def validar_job(job):
    """Retorna erros associados aos campos que impedem uma execução segura."""
    erros = {}
    nome = str(job.get("nome", "")).strip()
    repo = str(job.get("repo_path", "")).strip()
    caminho_alvo = str(job.get("arquivo_alvo", "")).strip()
    modo = job.get("modo_conteudo", "mensagens")

    if not nome:
        erros["nome"] = "Informe um nome para o trabalho."
    if not repo or not os.path.isdir(repo):
        erros["repo_path"] = "Escolha uma pasta de repositório existente."
    elif not os.path.isdir(os.path.join(repo, ".git")):
        erros["repo_path"] = "A pasta escolhida não contém um repositório Git."

    if modo != "comando_custom":
        if not caminho_alvo:
            erros["arquivo_alvo"] = "Informe o arquivo que será atualizado."
        elif os.path.isabs(caminho_alvo):
            erros["arquivo_alvo"] = "Use um caminho relativo à pasta do repositório."
        elif repo:
            raiz = os.path.realpath(repo)
            destino = os.path.realpath(os.path.join(raiz, caminho_alvo))
            try:
                dentro_do_repo = os.path.commonpath((raiz, destino)) == raiz
            except ValueError:
                dentro_do_repo = False
            if not dentro_do_repo:
                erros["arquivo_alvo"] = "O arquivo precisa ficar dentro do repositório."

    if modo == "comando_custom" and not str(job.get("comando_custom", "")).strip():
        erros["comando_custom"] = "Informe o comando que será executado."
    if modo not in ("mensagens", "linha_data", "comando_custom"):
        erros["modo_conteudo"] = "Escolha uma forma válida de atualização."

    for chave, rotulo in (("hora_inicio", "horário inicial"), ("hora_fim", "horário final")):
        try:
            datetime.datetime.strptime(str(job.get(chave, "")), "%H:%M")
        except ValueError:
            erros[chave] = f"Informe o {rotulo} no formato HH:MM."
    try:
        inicio = datetime.datetime.strptime(str(job.get("hora_inicio", "")), "%H:%M")
        fim = datetime.datetime.strptime(str(job.get("hora_fim", "")), "%H:%M")
        if inicio >= fim:
            erros["hora_fim"] = "O horário final precisa ser depois do inicial."
    except ValueError:
        pass

    try:
        minimo = int(job.get("commits_min_dia", 0))
        maximo = int(job.get("commits_max_dia", 0))
        if minimo < 0:
            erros["commits_min_dia"] = "Use zero ou um número maior."
        if maximo < 0:
            erros["commits_max_dia"] = "Use zero ou um número maior."
        if maximo < minimo:
            erros["commits_max_dia"] = "O máximo precisa ser igual ou maior que o mínimo."
    except (TypeError, ValueError):
        erros["commits_min_dia"] = "Informe quantidades inteiras de commits."
    try:
        if int(job.get("intervalo_min_minutos", 0)) < 1:
            erros["intervalo_min_minutos"] = "O intervalo precisa ser de pelo menos 1 minuto."
    except (TypeError, ValueError):
        erros["intervalo_min_minutos"] = "Informe o intervalo em minutos."
    try:
        chance = float(job.get("chance_pular_dia", 0))
        if not 0 <= chance <= 1:
            erros["chance_pular_dia"] = "A chance precisa ficar entre 0% e 100%."
    except (TypeError, ValueError):
        erros["chance_pular_dia"] = "Informe uma porcentagem válida."

    return erros


def obter_status_repositorio(repo_path):
    """Retorna se a pasta pertence a um repositório Git e quantas alterações há."""
    repo = str(repo_path or "").strip()
    if not repo or not os.path.isdir(repo):
        return False, 0

    codigo, raiz, _ = _rodar(["git", "rev-parse", "--show-toplevel"], repo, timeout=15)
    if codigo != 0 or not raiz:
        return False, 0

    codigo, saida, _ = _rodar(["git", "status", "--short"], repo, timeout=15)
    if codigo != 0:
        return False, 0
    return True, len([linha for linha in saida.splitlines() if linha.strip()])


def _commitar_alteracoes(repo, mensagem_commit, enviar):
    """Adiciona alterações e executa commit e, opcionalmente, push."""
    logs = []
    codigo, saida, erro = _rodar(["git", "add", "-A"], repo)
    logs.append(saida or erro or "git add ok")
    if codigo != 0:
        return False, "\n".join(logs)

    codigo, saida, erro = _rodar(["git", "commit", "-m", mensagem_commit], repo)
    logs.append(saida or erro)
    if codigo != 0:
        if "nothing to commit" in (saida + erro).lower():
            return True, "\n".join(logs + ["Nada para commitar neste momento."])
        return False, "\n".join(logs)

    if enviar:
        codigo, saida, erro = _rodar(["git", "push"], repo)
        logs.append(f"git push: {saida or erro or 'ok'}")
        if codigo != 0:
            return False, "\n".join(logs)

    return True, "\n".join(logs)


def executar_commit_direto(repo_path, mensagem, push=False):
    """Cria um commit das alterações atuais sem modificar arquivos do repositório."""
    repo = str(repo_path or "").strip()
    mensagem_commit = str(mensagem or "").strip()
    if not mensagem_commit:
        return False, "Informe uma mensagem para o commit."
    if not repo or not os.path.isdir(repo):
        return False, "Escolha uma pasta existente."

    valido, quantidade_alteracoes = obter_status_repositorio(repo)
    if not valido:
        return False, "A pasta escolhida não é um repositório Git válido."
    if not quantidade_alteracoes:
        return True, "Não há alterações novas para commitar."

    sucesso, saida = _commitar_alteracoes(repo, mensagem_commit, bool(push))
    if not sucesso and push and "git push" in saida:
        return False, "O commit foi criado, mas não foi possível enviá-lo ao GitHub."
    if not sucesso:
        return False, "Não foi possível criar o commit. Confira a configuração do Git e tente novamente."
    return True, saida


def executar_geracao_contribuicao(repo_path, tipo, mensagem):
    """Registra uma mensagem no log.md e cria e envia o commit correspondente."""
    repo = str(repo_path or "").strip()
    tipo_commit = str(tipo or "").strip().lower()
    texto = " ".join(str(mensagem or "").split())
    if not repo or not os.path.isdir(repo):
        return False, "Escolha uma pasta existente."
    valido, _ = obter_status_repositorio(repo)
    if not valido:
        return False, "A pasta escolhida não é um repositório Git válido."
    if tipo_commit not in config.TIPOS_COMMIT_VALIDOS or not texto:
        return False, "Escolha uma mensagem válida do banco."

    caminho_log = os.path.join(repo, "log.md")
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha_log = f"- {agora} — [{tipo_commit}] {texto}\n"
    novo_arquivo = not os.path.exists(caminho_log)
    if novo_arquivo:
        with open(caminho_log, "w", encoding="utf-8", newline="") as arquivo:
            arquivo.write("# Registro de contribuições\n\n")
            arquivo.write(linha_log)
    else:
        tamanho = os.path.getsize(caminho_log)
        precisa_quebra = False
        if tamanho:
            with open(caminho_log, "rb") as arquivo:
                arquivo.seek(-1, os.SEEK_END)
                precisa_quebra = arquivo.read(1) not in (b"\n", b"\r")
        with open(caminho_log, "a", encoding="utf-8", newline="") as arquivo:
            if precisa_quebra:
                arquivo.write("\n")
            arquivo.write(linha_log)

    mensagem_commit = f"{tipo_commit}: {texto}"
    logs = [f"Registro atualizado: {caminho_log}"]
    codigo, saida, erro = _rodar(["git", "add", "."], repo)
    logs.append(saida or erro or "Alterações preparadas.")
    if codigo != 0:
        return False, "\n".join(logs)

    codigo, saida, erro = _rodar(["git", "commit", "-m", mensagem_commit], repo)
    logs.append(saida or erro)
    if codigo != 0:
        return False, "\n".join(logs)

    codigo, saida, erro = _rodar(["git", "push"], repo)
    logs.append(saida or erro or "Alterações enviadas.")
    if codigo != 0:
        return False, "\n".join(logs)

    return True, "\n".join(logs)


def executar_commit(job):
    """Executa um commit completo para o job. Retorna (sucesso: bool, log: str)."""
    repo = job.get("repo_path", "")
    logs = []

    erros = validar_job(job)
    if erros:
        return False, "Confira os dados do trabalho:\n" + "\n".join(erros.values())

    if job.get("modo_conteudo") == "comando_custom":
        mensagem_commit = job.get("prefixo_mensagem", "chore: ") + "atualização automática"
    else:
        # calcula a mensagem UMA única vez e reaproveita no arquivo e no commit
        mensagem_commit = _proxima_mensagem(job)

    ok, msg = _alterar_arquivo(job, mensagem_commit)
    logs.append(msg)
    if not ok:
        return False, "\n".join(logs)

    sucesso, saida = _commitar_alteracoes(
        repo, mensagem_commit, job.get("push_automatico", True)
    )
    logs.append(saida)
    return sucesso, "\n".join(logs)