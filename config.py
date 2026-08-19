"""
config.py
Gerencia leitura/escrita do arquivo de configuração (config.json)
e o estado de "banco de mensagens" de cada trabalho.
"""

import json
import os
import uuid

PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
CAMINHO_CONFIG = os.path.join(PASTA_BASE, "config.json")
PASTA_ESTADO = os.path.join(PASTA_BASE, "estado")
CAMINHO_LOG = os.path.join(PASTA_BASE, "auto-committer.log")

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
    "banco_mensagens": [],              # lista carregada em memória
    "usar_banco_sequencial": True,      # evita repetir até esgotar o banco
    "prefixo_mensagem": "chore: ",
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
    return dados


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
    padrao = {"indice_mensagem": 0, "data_agenda": None, "agenda_hoje": [], "executados_hoje": []}
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


def importar_banco_mensagens(caminho_arquivo):
    """Lê um .txt (uma mensagem por linha) ou .csv (primeira coluna)
    e retorna a lista de mensagens não vazias."""
    mensagens = []
    if not os.path.exists(caminho_arquivo):
        return mensagens

    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    with open(caminho_arquivo, "r", encoding="utf-8", errors="ignore") as f:
        if extensao == ".csv":
            import csv
            leitor = csv.reader(f)
            for linha in leitor:
                if linha and linha[0].strip():
                    mensagens.append(linha[0].strip())
        else:
            for linha in f:
                linha = linha.strip()
                if linha:
                    mensagens.append(linha)
    return mensagens