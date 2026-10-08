"""Acesso autenticado à API pública do GitHub."""

import json
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone


API_USER_URL = "https://api.github.com/user"
API_GRAPHQL_URL = "https://api.github.com/graphql"
TIMEOUT_SEGUNDOS = 20

CONSULTA_CONTRIBUICOES = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            color
          }
        }
      }
    }
  }
}
"""


class ErroGitHub(Exception):
    """Erro seguro para exibição: nunca inclui o token nem detalhes da requisição."""


def validar_periodo(data_inicio, data_fim):
    if data_inicio > data_fim:
        raise ErroGitHub("A data inicial precisa ser anterior à data final.")
    if (data_fim - data_inicio).days > 365:
        raise ErroGitHub("Escolha um período de no máximo um ano.")


def _formatar_data_api(valor, fim_do_dia=False):
    horario = time.max if fim_do_dia else time.min
    return datetime.combine(valor, horario, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _ler_json(resposta):
    try:
        dados = json.loads(resposta.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ErroGitHub("O GitHub respondeu de um jeito inesperado. Tente novamente.") from None
    if not isinstance(dados, dict):
        raise ErroGitHub("O GitHub respondeu de um jeito inesperado. Tente novamente.")
    return dados


def _mensagem_http(status):
    if status == 401:
        return "Token inválido ou expirado. Confira o token e tente novamente."
    if status in (403, 429):
        return "O GitHub limitou temporariamente as consultas. Aguarde um pouco e tente novamente."
    return "Não foi possível conversar com o GitHub. Tente novamente."


def _enviar_requisicao(url, token, dados=None):
    if not token or any(caractere.isspace() or ord(caractere) < 33 for caractere in token):
        raise ErroGitHub("Token inválido. Cole o token completo e tente novamente.")
    corpo = None if dados is None else json.dumps(dados).encode("utf-8")
    try:
        requisicao = urllib.request.Request(
            url,
            data=corpo,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET" if dados is None else "POST",
        )
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
            return _ler_json(resposta)
    except urllib.error.HTTPError as erro:
        raise ErroGitHub(_mensagem_http(erro.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ErroGitHub("Sem conexão com o GitHub. Confira sua internet e tente novamente.") from None


def validar_token(token):
    token = token.strip()
    if not token:
        raise ErroGitHub("Cole seu token do GitHub para continuar.")

    usuario = _enviar_requisicao(API_USER_URL, token)
    login = usuario.get("login")
    if not isinstance(login, str) or not login:
        raise ErroGitHub("Não foi possível identificar a conta deste token.")
    nome = usuario.get("name")
    avatar_url = usuario.get("avatar_url", "")
    return {
        "login": login,
        "name": nome if isinstance(nome, str) and nome else login,
        "avatar_url": avatar_url if isinstance(avatar_url, str) else "",
    }


def buscar_contribuicoes(token, login, data_inicio, data_fim):
    validar_periodo(data_inicio, data_fim)
    resposta = _enviar_requisicao(
        API_GRAPHQL_URL,
        token,
        {
            "query": CONSULTA_CONTRIBUICOES,
            "variables": {
                "login": login,
                "from": _formatar_data_api(data_inicio),
                "to": _formatar_data_api(data_fim, fim_do_dia=True),
            },
        },
    )

    erros = resposta.get("errors", [])
    if erros:
        codigos = set()
        for erro in erros:
            if not isinstance(erro, dict):
                continue
            extensoes = erro.get("extensions")
            if isinstance(extensoes, dict):
                codigos.add(extensoes.get("code"))
        if "RATE_LIMITED" in codigos:
            raise ErroGitHub("O GitHub limitou temporariamente as consultas. Aguarde um pouco e tente novamente.")
        if codigos.intersection({"UNAUTHENTICATED", "FORBIDDEN"}):
            raise ErroGitHub("Token inválido ou sem acesso. Confira o token e tente novamente.")
        raise ErroGitHub("Não foi possível carregar as contribuições. Tente novamente.")

    dados = resposta.get("data")
    if not isinstance(dados, dict):
        raise ErroGitHub("Não foi possível carregar as contribuições. Tente novamente.")
    usuario = dados.get("user")
    if usuario is None:
        raise ErroGitHub("Não encontramos essa conta do GitHub.")
    if not isinstance(usuario, dict):
        raise ErroGitHub("Não foi possível carregar o calendário dessa conta.")

    colecao = usuario.get("contributionsCollection")
    if not isinstance(colecao, dict):
        raise ErroGitHub("Não foi possível carregar o calendário dessa conta.")
    calendario = colecao.get("contributionCalendar")
    if not isinstance(calendario, dict):
        raise ErroGitHub("Não foi possível carregar o calendário dessa conta.")

    semanas = calendario.get("weeks")
    if not isinstance(semanas, list):
        raise ErroGitHub("Não foi possível carregar o calendário dessa conta.")
    dias = []
    try:
        for semana in semanas:
            if not isinstance(semana, dict):
                raise ValueError
            dias_da_semana = semana.get("contributionDays")
            if not isinstance(dias_da_semana, list):
                raise ValueError
            for dia in dias_da_semana:
                if not isinstance(dia, dict):
                    raise ValueError
                data_dia = date.fromisoformat(dia["date"])
                quantidade = int(dia["contributionCount"])
                if quantidade < 0:
                    raise ValueError
                cor = dia.get("color", "")
                dias.append(
                    {
                        "date": data_dia.isoformat(),
                        "contributionCount": quantidade,
                        "color": cor if isinstance(cor, str) else "",
                    }
                )
        total = int(calendario["totalContributions"])
        if total < 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ErroGitHub("O calendário recebido não está completo. Tente novamente.") from None

    return {
        "login": usuario.get("login", login),
        "total_contributions": total,
        "days": dias,
    }


def periodo_ultimo_ano(hoje=None):
    hoje = hoje or date.today()
    return hoje - timedelta(days=364), hoje
