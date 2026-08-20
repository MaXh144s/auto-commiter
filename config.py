"""
config.py
Gerencia leitura/escrita do arquivo de configuração (config.json)
e o estado de "banco de mensagens" de cada trabalho.
"""

import json
import os
import re
import sys
import uuid

def _detectar_pasta_base():
    """Pasta onde config.json, o log e o estado devem ficar salvos.

    CUIDADO: __file__ não pode ser usado aqui quando o programa está
    rodando como .exe gerado pelo PyInstaller em modo --onefile. Nesse
    modo, o PyInstaller extrai tudo pra uma pasta TEMPORÁRIA a cada
    execução (e apaga essa pasta ao fechar) — então
    os.path.dirname(os.path.abspath(__file__)) apontaria pra um lugar
    diferente e vazio a cada vez que o programa abre, fazendo o
    config.json (trabalhos configurados) e o log "sumirem" toda vez
    que o PC liga de novo. sys.executable, ao contrário, sempre aponta
    pro .exe de verdade, parado sempre no mesmo lugar."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


PASTA_BASE = _detectar_pasta_base()
CAMINHO_CONFIG = os.path.join(PASTA_BASE, "config.json")
PASTA_ESTADO = os.path.join(PASTA_BASE, "estado")
CAMINHO_LOG = os.path.join(PASTA_BASE, "auto-committer.log")

# Tipos de commit no estilo "Conventional Commits". Cada mensagem do banco
# carrega o seu próprio tipo (em vez de um prefixo fixo tipo "chore: " pra
# tudo), o que deixa o histórico bem mais humano e variado.
TIPOS_COMMIT_LABELS = {
    "feat": "feat — nova funcionalidade",
    "fix": "fix — correção de bug",
    "docs": "docs — documentação",
    "style": "style — formatação/estilo",
    "refactor": "refactor — refatoração",
    "test": "test — testes",
    "chore": "chore — tarefas diversas",
    "perf": "perf — performance",
    "build": "build — build/dependências",
    "ci": "ci — integração contínua",
}
TIPOS_COMMIT_VALIDOS = list(TIPOS_COMMIT_LABELS.keys())

CONFIG_PADRAO = {
    "geral": {
        "iniciar_com_windows": True,
        "intervalo_verificacao_segundos": 30
    },
    "jobs": []
}

JOB_PADRAO = {
    "id": None,
    "nome": "Novo trabalho",
    "ativo": True,
    "repo_path": "",
    "arquivo_alvo": "log.md",
    "modo_conteudo": "mensagens",       # "mensagens" | "linha_data" | "comando_custom"
    "comando_custom": "",
    "banco_mensagens_arquivo": "",      # caminho pro .txt/.csv importado
    "banco_mensagens": [],              # lista de {"tipo": "feat", "mensagem": "..."}
    "usar_banco_sequencial": True,      # evita repetir até esgotar o banco
    "tipos_commit_selecionados": list(TIPOS_COMMIT_VALIDOS),  # quais tipos entram no sorteio
    "prefixo_mensagem": "chore: ",      # fallback: só usado em "linha_data" / "comando_custom"
    "dias_semana": [0, 1, 2, 3, 4, 5, 6],  # 0=segunda ... 6=domingo
    "hora_inicio": "08:00",
    "hora_fim": "22:00",
    "commits_min_dia": 1,
    "commits_max_dia": 3,
    "intervalo_min_minutos": 45,
    "chance_pular_dia": 0.15,
    "push_automatico": True
}


def garantir_pastas():
    os.makedirs(PASTA_ESTADO, exist_ok=True)


def carregar_config():
    garantir_pastas()
    if not os.path.exists(CAMINHO_CONFIG):
        salvar_config(CONFIG_PADRAO)
        return json.loads(json.dumps(CONFIG_PADRAO))

    with open(CAMINHO_CONFIG, "r", encoding="utf-8") as f:
        try:
            dados = json.load(f)
        except json.JSONDecodeError:
            dados = json.loads(json.dumps(CONFIG_PADRAO))

    # garante chaves novas em configs antigas
    for chave, valor in CONFIG_PADRAO.items():
        dados.setdefault(chave, valor)

    for job in dados.get("jobs", []):
        _migrar_job_para_formato_atual(job)

    return dados


def _migrar_job_para_formato_atual(job):
    """Preenche campos que não existiam em versões antigas do config.json
    e converte o banco_mensagens do formato antigo (lista de strings, sem
    tipo) para o formato atual (lista de {"tipo", "mensagem"}), assumindo
    tipo "chore" pras mensagens antigas — mantém o comportamento anterior
    intacto pra quem já tinha um banco configurado."""
    for chave, valor in JOB_PADRAO.items():
        if chave == "id":
            continue
        job.setdefault(chave, json.loads(json.dumps(valor)) if isinstance(valor, (list, dict)) else valor)

    job["banco_mensagens"] = [_normalizar_item_mensagem(item) for item in job.get("banco_mensagens", [])]

    tipos_validos = [t for t in job.get("tipos_commit_selecionados", []) if t in TIPOS_COMMIT_VALIDOS]
    job["tipos_commit_selecionados"] = tipos_validos or list(TIPOS_COMMIT_VALIDOS)


def _normalizar_item_mensagem(item):
    """Aceita tanto o formato novo ({"tipo": ..., "mensagem": ...}) quanto
    uma string pura (formato antigo, sem tipo — vira "chore")."""
    if isinstance(item, dict) and "mensagem" in item:
        tipo = str(item.get("tipo", "chore")).strip().lower()
        if tipo not in TIPOS_COMMIT_VALIDOS:
            tipo = "chore"
        return {"tipo": tipo, "mensagem": str(item["mensagem"]).strip()}
    return {"tipo": "chore", "mensagem": str(item).strip()}


def salvar_config(dados):
    garantir_pastas()
    with open(CAMINHO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def novo_job():
    job = json.loads(json.dumps(JOB_PADRAO))
    job["id"] = str(uuid.uuid4())
    return job


def caminho_estado_job(job_id):
    """Arquivo que guarda o índice atual do banco de mensagens e o
    histórico de horários já executados hoje, por trabalho."""
    return os.path.join(PASTA_ESTADO, f"{job_id}.json")


def carregar_estado_job(job_id):
    caminho = caminho_estado_job(job_id)
    padrao = {"indice_mensagem": 0, "data_agenda": None, "agenda_hoje": [],
              "executados_hoje": [], "execucao_manual_pendente": False,
              "avisados_intervalo_hoje": []}
    if not os.path.exists(caminho):
        return padrao
    with open(caminho, "r", encoding="utf-8") as f:
        try:
            dados = json.load(f)
        except json.JSONDecodeError:
            return padrao
    for chave, valor in padrao.items():
        dados.setdefault(chave, valor)
    return dados


def salvar_estado_job(job_id, estado):
    garantir_pastas()
    with open(caminho_estado_job(job_id), "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

def marcar_execucao_pendente(job_id, pendente=True):
    """Marca (ou desmarca) que existe um 'commitar depois' pendente pra esse
    trabalho — o agendador em background vai disparar automaticamente assim
    que o intervalo mínimo configurado for atingido."""
    estado = carregar_estado_job(job_id)
    estado["execucao_manual_pendente"] = pendente
    salvar_estado_job(job_id, estado)


def esta_execucao_pendente(job_id):
    return bool(carregar_estado_job(job_id).get("execucao_manual_pendente", False))


def calcular_capacidade_maxima(hora_inicio, hora_fim, intervalo_min_minutos):
    """Calcula quantos commits cabem, de forma realista, dentro da janela
    de horário [hora_inicio, hora_fim) respeitando o intervalo mínimo
    configurado entre um commit e outro.

    O agendador sorteia os horários dentro da janela (não usa intervalos
    100% exatos), então o teto realista é "quantos blocos do tamanho do
    intervalo mínimo cabem na duração da janela" — ex: janela de 10h com
    intervalo mínimo de 2h → 10 // 2 = 5 commits possíveis nesse dia."""
    try:
        h_ini, m_ini = map(int, str(hora_inicio).split(":"))
        h_fim, m_fim = map(int, str(hora_fim).split(":"))
    except (ValueError, AttributeError):
        h_ini, m_ini, h_fim, m_fim = 8, 0, 22, 0

    duracao_minutos = (h_fim * 60 + m_fim) - (h_ini * 60 + m_ini)
    if duracao_minutos <= 0:
        # janela mal configurada (fim <= início) — mesmo fallback de 1h
        # usado pelo agendador ao montar a agenda do dia
        duracao_minutos = 60

    # intervalo mínimo nunca pode ser <= 0 — senão a "capacidade" daria
    # infinita (ou erro de divisão por zero)
    intervalo = max(1, int(intervalo_min_minutos))

    return max(1, duracao_minutos // intervalo)


def validar_job(job):
    """Corrige valores inconsistentes de um job antes de salvar/usar:

    - intervalo_min_minutos nunca pode ser <= 0 (vira 1 minuto no mínimo).
    - commits_max_dia não pode passar da capacidade real da janela de
      horário configurada com esse intervalo mínimo — se passar, é
      reduzido para o máximo que realmente cabe. Se já estiver dentro do
      limite (mesmo que bem menor), NÃO é alterado.
    - commits_min_dia é limitado da mesma forma e nunca pode ficar maior
      que commits_max_dia (já corrigido).

    Retorna (job_corrigido, avisos), onde avisos é uma lista de strings
    descrevendo o que foi ajustado (vazia se nada precisou de correção)."""
    job = dict(job)
    avisos = []

    intervalo_original = int(job.get("intervalo_min_minutos", 45))
    if intervalo_original <= 0:
        job["intervalo_min_minutos"] = 1
        avisos.append(
            "Intervalo mínimo entre commits não pode ser 0 ou negativo — ajustado para 1 minuto."
        )
    else:
        job["intervalo_min_minutos"] = intervalo_original

    capacidade = calcular_capacidade_maxima(
        job.get("hora_inicio", "08:00"),
        job.get("hora_fim", "22:00"),
        job["intervalo_min_minutos"],
    )

    max_original = int(job.get("commits_max_dia", 1))
    if max_original > capacidade:
        job["commits_max_dia"] = capacidade
        avisos.append(
            f"Commits máximos por dia ({max_original}) não cabem na janela de horário "
            f"configurada com esse intervalo mínimo — ajustado para o máximo realista: "
            f"{capacidade}."
        )
    else:
        job["commits_max_dia"] = max_original

    min_original = int(job.get("commits_min_dia", 1))
    if min_original > job["commits_max_dia"]:
        job["commits_min_dia"] = job["commits_max_dia"]
        avisos.append(
            f"Commits mínimos por dia ({min_original}) era maior que o máximo permitido "
            f"— ajustado para {job['commits_max_dia']}."
        )
    else:
        job["commits_min_dia"] = min_original

    return job, avisos


_PADRAO_TIPO_MENSAGEM = re.compile(r'^([a-zA-Z]+)\s*:\s*(.+)$')


def _dividir_tipo_mensagem(linha):
    """Extrai (tipo, texto) de uma linha no formato 'tipo: mensagem'
    (ex: 'feat: adiciona tela de login'). Se a linha não começar com um
    tipo reconhecido (feat/fix/docs/style/refactor/test/chore/perf/
    build/ci), a linha inteira vira o texto e o tipo cai pra "chore" —
    assim um banco de mensagens antigo (texto puro, sem tipo) continua
    funcionando normalmente."""
    encontrado = _PADRAO_TIPO_MENSAGEM.match(linha)
    if encontrado:
        tipo = encontrado.group(1).strip().lower()
        texto = encontrado.group(2).strip()
        if tipo in TIPOS_COMMIT_VALIDOS:
            return tipo, texto
    return "chore", linha.strip()


def importar_banco_mensagens(caminho_arquivo):
    """Lê um .txt (uma mensagem por linha, no formato 'tipo: mensagem' —
    ex: 'feat: adiciona endpoint de login') ou .csv (primeira coluna) e
    retorna uma lista de {"tipo": ..., "mensagem": ...}.

    Cada tipo tem suas próprias mensagens, permitindo escolher na GUI
    quais tipos entram no sorteio (em vez de um prefixo único e fixo
    tipo "chore: " pra tudo)."""
    itens = []
    if not os.path.exists(caminho_arquivo):
        return itens

    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    with open(caminho_arquivo, "r", encoding="utf-8", errors="ignore") as f:
        if extensao == ".csv":
            import csv
            leitor = csv.reader(f)
            for linha in leitor:
                if linha and linha[0].strip():
                    tipo, texto = _dividir_tipo_mensagem(linha[0].strip())
                    itens.append({"tipo": tipo, "mensagem": texto})
        else:
            for linha in f:
                linha = linha.strip()
                if linha:
                    tipo, texto = _dividir_tipo_mensagem(linha)
                    itens.append({"tipo": tipo, "mensagem": texto})
    return itens