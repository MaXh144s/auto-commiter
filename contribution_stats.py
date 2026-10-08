"""Cálculos independentes para o calendário de contribuições."""

from datetime import date, timedelta


def calcular_estatisticas(dias, hoje=None):
    hoje = hoje or date.today()
    contagens = {}
    for dia in dias:
        data_dia = date.fromisoformat(dia["date"])
        contagens[data_dia] = int(dia.get("contributionCount", 0))

    total = sum(contagens.values())
    datas_ativas = sorted(data for data, quantidade in contagens.items() if quantidade > 0)

    maior_sequencia = 0
    sequencia = 0
    data_anterior = None
    for data_dia in datas_ativas:
        if data_anterior == data_dia - timedelta(days=1):
            sequencia += 1
        else:
            sequencia = 1
        maior_sequencia = max(maior_sequencia, sequencia)
        data_anterior = data_dia

    atual = 0
    ancora = hoje if contagens.get(hoje, 0) else hoje - timedelta(days=1)
    if contagens.get(ancora, 0):
        atual = 1
        dia_atual = ancora - timedelta(days=1)
        while contagens.get(dia_atual, 0):
            atual += 1
            dia_atual -= timedelta(days=1)

    dia_produtivo = None
    if contagens:
        melhor_data = max(contagens, key=lambda data_dia: contagens[data_dia])
        if contagens[melhor_data] > 0:
            dia_produtivo = {
                "date": melhor_data.isoformat(),
                "count": contagens[melhor_data],
            }

    return {
        "total_contributions": total,
        "current_streak": atual,
        "longest_streak": maior_sequencia,
        "most_productive_day": dia_produtivo,
    }
