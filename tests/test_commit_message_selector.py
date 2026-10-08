import unittest
from unittest.mock import patch
from unittest.mock import Mock

import commit_message_selector


class SeletorMensagensCommitTests(unittest.TestCase):
    def setUp(self):
        self.banco = [
            {"tipo": "feat", "mensagem": "adiciona recurso"},
            {"tipo": "fix", "mensagem": "corrige erro"},
            {"tipo": "docs", "mensagem": "atualiza guia"},
        ]

    def test_conta_frequencia_de_cada_mensagem(self):
        resultado = commit_message_selector.contar_frequencias(
            ["feat: adiciona recurso", "feat: adiciona recurso", "fix: corrige erro"],
            self.banco,
        )

        self.assertEqual([item["frequencia"] for item in resultado], [2, 1, 0])

    def test_empate_inclui_todas_as_mensagens_menos_repetidas(self):
        grupo = commit_message_selector.grupo_menos_repetidas(
            ["feat: adiciona recurso"],
            self.banco,
        )

        self.assertEqual(
            [item["assunto"] for item in grupo],
            ["fix: corrige erro", "docs: atualiza guia"],
        )

    @patch("commit_message_selector.random.choice", side_effect=lambda grupo: grupo[-1])
    def test_escolhe_aleatoriamente_entre_as_mensagens_empatadas(self, escolha):
        escolhida = commit_message_selector.escolher_mensagem(
            ["feat: adiciona recurso"],
            self.banco,
        )

        self.assertEqual(escolhida["assunto"], "docs: atualiza guia")
        escolha.assert_called_once()

    def test_banco_totalmente_usado_escolhe_grupo_de_menor_frequencia(self):
        grupo = commit_message_selector.grupo_menos_repetidas(
            [
                "feat: adiciona recurso",
                "feat: adiciona recurso",
                "fix: corrige erro",
                "docs: atualiza guia",
            ],
            self.banco,
        )

        self.assertEqual(
            [item["assunto"] for item in grupo],
            ["fix: corrige erro", "docs: atualiza guia"],
        )
        self.assertEqual({item["frequencia"] for item in grupo}, {1})

    def test_repositorio_sem_commits_deixa_todas_com_frequencia_zero(self):
        grupo = commit_message_selector.grupo_menos_repetidas([], self.banco)

        self.assertEqual(len(grupo), 3)
        self.assertEqual({item["frequencia"] for item in grupo}, {0})

    def test_compara_ignorando_maiusculas_e_espacos_nas_pontas(self):
        resultado = commit_message_selector.contar_frequencias(
            ["  FEAT: ADICIONA RECURSO  "],
            self.banco,
        )

        self.assertEqual(resultado[0]["frequencia"], 1)

    @patch("commit_message_selector.random.choice", side_effect=lambda grupo: grupo[0])
    def test_mensagem_diferente_da_anterior_e_escolhida_a_cada_execucao(self, _escolher):
        escolhida = commit_message_selector.escolher_mensagem_diferente(
            ["feat: adiciona recurso"],
            self.banco,
            " FEAT: ADICIONA RECURSO ",
        )

        self.assertEqual(escolhida["assunto"], "fix: corrige erro")

    @patch("commit_message_selector.os.path.isdir", return_value=True)
    @patch(
        "commit_message_selector.subprocess.run",
        side_effect=[
            Mock(returncode=128, stdout="", stderr="sem commits ainda"),
            Mock(returncode=128, stdout="", stderr="HEAD não existe"),
            Mock(returncode=0, stdout="C:\\repositorio", stderr=""),
        ],
    )
    def test_historico_de_repositorio_sem_commits_e_lista_vazia(
        self, _rodar, _diretorio
    ):
        self.assertEqual(commit_message_selector.ler_mensagens_commit("C:\\repositorio"), [])


if __name__ == "__main__":
    unittest.main()
