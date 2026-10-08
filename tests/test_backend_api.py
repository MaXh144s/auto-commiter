import os
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from backend.api import Api
import commit_message_selector


class ApiDesktopTests(unittest.TestCase):
    def setUp(self):
        self.pasta_temporaria = tempfile.TemporaryDirectory()
        self.caminho_estado = os.path.join(
            self.pasta_temporaria.name, "agendamento.json"
        )

    def tearDown(self):
        self.pasta_temporaria.cleanup()

    def criar_api(self):
        return Api(self.caminho_estado)

    def test_retomar_nao_ativa_antes_do_primeiro_commit_manual(self):
        api = self.criar_api()

        resposta = api.retomar_agendamento()

        self.assertFalse(resposta["ok"])
        self.assertIn("primeiro commit manual", resposta["erro"])

    @patch(
        "backend.api.config.carregar_config",
        return_value={
            "agendamento_automatico": {
                "dias_semana": [0, 1, 2, 3, 4, 5, 6],
                "intervalo_minutos": 30,
                "commits_min_dia": 1,
                "commits_max_dia": 2,
                "repo_path": "C:\\repositorio",
                "banco_mensagens": [{"tipo": "feat", "mensagem": "recurso"}],
            }
        },
    )
    @patch("backend.api.committer.obter_status_repositorio", return_value=(False, 0))
    def test_retomar_revalida_repositorio_de_agendamento_pausado(
        self, _status, _config
    ):
        api = self.criar_api()
        api._agendador.estado = Mock(
            return_value={"ativado": True, "ativo": True, "pausado": True}
        )

        with patch.object(api._agendador, "retomar") as retomar:
            resposta = api.retomar_agendamento()

        self.assertFalse(resposta["ok"])
        self.assertIn("repositório", resposta["erro"])
        retomar.assert_not_called()

    @patch(
        "backend.api.committer.executar_geracao_contribuicao",
        return_value=(True, "Registro atualizado."),
    )
    def test_fazer_commit_retorna_dicionario_e_registra_historico(self, executar):
        api = self.criar_api()

        resposta = api.fazer_commit("C:\\repositorio", "feat", "novo recurso")

        self.assertTrue(resposta["ok"])
        self.assertEqual(
            resposta["mensagem"], "Registro adicionado, commit criado e enviado ao GitHub."
        )
        self.assertEqual(resposta["historico"][0]["mensagem"], "novo recurso")
        executar.assert_called_once_with(
            "C:\\repositorio", "feat", "novo recurso"
        )

    @patch(
        "backend.api.committer.executar_geracao_contribuicao",
        return_value=(False, "Não foi possível criar o commit."),
    )
    def test_falha_e_retorno_amigavel_sem_excecao(self, _executar):
        resposta = self.criar_api().fazer_commit("C:\\repositorio", "fix", "corrige falha")

        self.assertFalse(resposta["ok"])
        self.assertIn("erro", resposta)

    @patch("backend.api.committer.executar_geracao_contribuicao", return_value=(False, "Escolha uma mensagem válida do banco."))
    def test_fazer_commit_sem_argumentos_retorna_erro_em_vez_de_lancar(self, _executar):
        resposta = self.criar_api().fazer_commit()

        self.assertFalse(resposta["ok"])
        self.assertIn("erro", resposta)

    @patch("backend.api.committer.obter_status_repositorio", return_value=(True, 3))
    def test_status_informa_quantidade_de_alteracoes(self, _status):
        resposta = self.criar_api().listar_status("C:\\repositorio")

        self.assertTrue(resposta["ok"])
        self.assertEqual(resposta["alteracoes"], 3)

    @patch("backend.api.config.importar_banco_mensagens")
    @patch("backend.api.committer.obter_status_repositorio", return_value=(True, 1))
    @patch("webview.windows", [Mock(create_file_dialog=Mock(return_value=["C:\\banco.txt"]))])
    def test_seleciona_banco_e_retorna_mensagens(self, _status, importar):
        importar.return_value = [{"tipo": "feat", "mensagem": "adiciona recurso"}]

        resposta = self.criar_api().selecionar_banco_mensagens("C:\\repositorio")

        self.assertTrue(resposta["ok"])
        self.assertEqual(resposta["nome"], "banco.txt")
        self.assertEqual(resposta["mensagens"][0]["tipo"], "feat")
        importar.assert_called_once_with("C:\\banco.txt")

    @patch("backend.api.committer.obter_status_repositorio", return_value=(False, 0))
    @patch("webview.windows")
    def test_banco_nao_pode_ser_aberto_sem_repositorio_valido(self, janelas, _status):
        resposta = self.criar_api().selecionar_banco_mensagens("C:\\nao-e-repositorio")

        self.assertFalse(resposta["ok"])
        janelas.assert_not_called()

    @patch(
        "backend.api.commit_message_selector.ler_mensagens_commit",
        return_value=["feat: adiciona recurso"],
    )
    def test_sugere_mensagem_menos_usada_com_frequencia(self, _ler_log):
        banco = [
            {"tipo": "feat", "mensagem": "adiciona recurso"},
            {"tipo": "fix", "mensagem": "corrige erro"},
        ]

        resposta = self.criar_api().sugerir_mensagem_commit("C:\\repositorio", banco)

        self.assertTrue(resposta["ok"])
        self.assertEqual(resposta["mensagem"]["tipo"], "fix")
        self.assertEqual(resposta["usos"], 0)

    @patch("backend.api.committer.obter_status_repositorio", return_value=(True, 0))
    @patch(
        "backend.api.commit_message_selector.ler_mensagens_commit",
        side_effect=[[], ["feat: recurso A"]],
    )
    @patch(
        "backend.api.committer.executar_geracao_contribuicao",
        return_value=(True, "Registro atualizado."),
    )
    def test_commit_agendado_rele_o_log_antes_de_cada_mensagem(
        self, _status, executar, ler_log
    ):
        api = self.criar_api()
        banco = [
            {"tipo": "feat", "mensagem": "recurso A"},
            {"tipo": "fix", "mensagem": "corrige B"},
        ]

        primeiro = api._executar_commit_agendado("C:\\repositorio", banco, None)
        segundo = api._executar_commit_agendado(
            "C:\\repositorio",
            banco,
            f"{primeiro['mensagem_escolhida']['tipo']}: "
            f"{primeiro['mensagem_escolhida']['mensagem']}",
        )

        self.assertTrue(primeiro["ok"])
        self.assertTrue(segundo["ok"])
        self.assertNotEqual(
            primeiro["mensagem_escolhida"]["assunto"],
            segundo["mensagem_escolhida"]["assunto"],
        )
        self.assertEqual(ler_log.call_count, 2)
        self.assertEqual(executar.call_count, 2)

    @patch("backend.api.config.salvar_config")
    @patch(
        "backend.api.config.carregar_config",
        return_value={"geral": {}, "jobs": []},
    )
    def test_salva_configuracoes_de_agendamento_em_config_local(
        self, _carregar, salvar
    ):
        resposta = self.criar_api().salvar_configuracoes_agendamento(
            {
                "dias_semana": [0, 2, 4],
                "intervalo_minutos": 15,
                "commits_min_dia": 1,
                "commits_max_dia": 4,
            }
        )

        self.assertTrue(resposta["ok"])
        dados_salvos = salvar.call_args.args[0]
        self.assertEqual(
            dados_salvos["agendamento_automatico"]["dias_semana"], [0, 2, 4]
        )
        self.assertEqual(
            dados_salvos["agendamento_automatico"]["intervalo_minutos"], 15
        )

    @patch(
        "backend.api.commit_message_selector.ler_mensagens_commit",
        side_effect=commit_message_selector.CommitLogError("Histórico inválido."),
    )
    @patch("backend.api.committer.executar_geracao_contribuicao")
    def test_falha_ao_ler_log_impede_commit(self, executar, _ler_log):
        resposta = self.criar_api().fazer_commit(
            "C:\\repositorio",
            "feat",
            "adiciona recurso",
            True,
            [{"tipo": "feat", "mensagem": "adiciona recurso"}],
        )

        self.assertFalse(resposta["ok"])
        self.assertEqual(resposta["erro"], "Histórico inválido.")
        executar.assert_not_called()

    @patch(
        "backend.api.commit_message_selector.ler_mensagens_commit",
        return_value=[
            "feat: adiciona recurso",
            "fix: corrige erro",
            "docs: atualiza guia",
            "docs: atualiza guia",
        ],
    )
    @patch("backend.api.commit_message_selector.random.choice", side_effect=lambda grupo: grupo[0])
    @patch(
        "backend.api.committer.executar_geracao_contribuicao",
        return_value=(True, "Registro atualizado."),
    )
    @patch.object(
        Api,
        "_ativar_agendamento_apos_commit",
        return_value={"ativado": False, "mensagem": "Teste isolado."},
    )
    def test_commit_com_modo_ativo_revalida_e_retorna_uso_anterior(
        self, _ativacao, executar, _escolher, _ler_log
    ):
        banco = [
            {"tipo": "feat", "mensagem": "adiciona recurso"},
            {"tipo": "fix", "mensagem": "corrige erro"},
        ]

        resposta = self.criar_api().fazer_commit(
            "C:\\repositorio", "feat", "adiciona recurso", True, banco
        )

        self.assertTrue(resposta["ok"])
        self.assertEqual(resposta["mensagem_escolhida"]["tipo"], "feat")
        self.assertEqual(resposta["usos"], 1)
        executar.assert_called_once_with(
            "C:\\repositorio", "feat", "adiciona recurso"
        )

    @patch(
        "backend.api.commit_message_selector.ler_mensagens_commit",
        return_value=[
            "feat: adiciona recurso",
            "fix: corrige erro",
            "docs: atualiza guia",
            "docs: atualiza guia",
        ],
    )
    @patch("backend.api.commit_message_selector.random.choice", side_effect=lambda grupo: grupo[0])
    @patch("backend.api.committer.executar_geracao_contribuicao")
    def test_historico_alterado_requer_nova_confirmacao_sem_commitar(
        self, executar, _escolher, _ler_log
    ):
        resposta = self.criar_api().fazer_commit(
            "C:\\repositorio",
            "docs",
            "atualiza guia",
            True,
            [
                {"tipo": "feat", "mensagem": "adiciona recurso"},
                {"tipo": "fix", "mensagem": "corrige erro"},
                {"tipo": "docs", "mensagem": "atualiza guia"},
            ],
        )

        self.assertFalse(resposta["ok"])
        self.assertTrue(resposta["reconfirmar"])
        self.assertEqual(resposta["mensagem_escolhida"]["tipo"], "feat")
        executar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
