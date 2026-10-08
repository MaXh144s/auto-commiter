import io
import json
import unittest
import urllib.error
from datetime import date, timedelta
from unittest.mock import patch

import github_api


class ValidacaoTokenTests(unittest.TestCase):
    def test_token_valido_retorna_perfil_sem_expor_token(self):
        token = "ghp-token-de-teste"
        resposta = io.BytesIO(
            json.dumps(
                {
                    "login": "ana",
                    "name": "Ana",
                    "avatar_url": "https://avatars.githubusercontent.com/u/1",
                }
            ).encode("utf-8")
        )
        with patch("github_api.urllib.request.urlopen", return_value=resposta) as abrir:
            perfil = github_api.validar_token(token)

        requisicao = abrir.call_args.args[0]
        self.assertEqual(perfil["login"], "ana")
        self.assertEqual(perfil["name"], "Ana")
        self.assertEqual(requisicao.get_header("Authorization"), f"Bearer {token}")

    def test_token_invalido_retorna_mensagem_segura(self):
        token = "ghp-segredo-nao-exibido"
        falha = urllib.error.HTTPError(
            github_api.API_USER_URL, 401, "Unauthorized", None, io.BytesIO(b"")
        )
        with patch("github_api.urllib.request.urlopen", side_effect=falha):
            with self.assertRaises(github_api.ErroGitHub) as contexto:
                github_api.validar_token(token)

        self.assertIn("inválido ou expirado", str(contexto.exception))
        self.assertNotIn(token, str(contexto.exception))

    def test_token_vazio_nao_faz_requisicao(self):
        with patch("github_api.urllib.request.urlopen") as abrir:
            with self.assertRaises(github_api.ErroGitHub):
                github_api.validar_token(" ")
        abrir.assert_not_called()

    def test_periodo_superior_a_um_ano_e_recusado(self):
        inicio = date(2024, 1, 1)
        with self.assertRaises(github_api.ErroGitHub):
            github_api.validar_periodo(inicio, inicio + timedelta(days=366))

    def test_consulta_gql_envia_login_em_variables(self):
        token = "ghp-token-de-teste"
        inicio = date(2025, 1, 1)
        fim = date(2025, 1, 31)
        resposta = io.BytesIO(
            json.dumps(
                {
                    "data": {
                        "user": {
                            "login": "ana",
                            "contributionsCollection": {
                                "contributionCalendar": {
                                    "totalContributions": 2,
                                    "weeks": [{"contributionDays": []}],
                                }
                            },
                        }
                    }
                }
            ).encode("utf-8")
        )
        with patch("github_api.urllib.request.urlopen", return_value=resposta) as abrir:
            dados = github_api.buscar_contribuicoes(token, "ana", inicio, fim)

        requisicao = abrir.call_args.args[0]
        corpo = json.loads(requisicao.data.decode("utf-8"))
        self.assertEqual(corpo["variables"]["login"], "ana")
        self.assertNotIn("ana", corpo["query"])
        self.assertEqual(dados["total_contributions"], 2)


if __name__ == "__main__":
    unittest.main()
