import unittest
import os
import tempfile
from unittest.mock import patch

import committer


class CommitDiretoTests(unittest.TestCase):
    def test_gera_log_e_executa_add_commit_push_sem_exigir_alteracoes_preexistentes(self):
        with tempfile.TemporaryDirectory() as repo:
            os.mkdir(os.path.join(repo, ".git"))
            log_path = os.path.join(repo, "log.md")
            with open(log_path, "w", encoding="utf-8", newline="") as log:
                log.write("# Histórico\n\n- entrada anterior sem newline")

            with (
                patch("committer.obter_status_repositorio", return_value=(True, 0)),
                patch(
                    "committer._rodar",
                    side_effect=[
                        (0, "", ""),
                        (0, "commit criado", ""),
                        (0, "push enviado", ""),
                    ],
                ) as rodar,
            ):
                sucesso, resultado = committer.executar_geracao_contribuicao(
                    repo, "feat", "adiciona uma melhoria"
                )

            with open(log_path, encoding="utf-8") as log:
                conteudo = log.read()

        self.assertTrue(sucesso)
        self.assertIn("entrada anterior sem newline\n- ", conteudo)
        self.assertIn("[feat] adiciona uma melhoria", conteudo)
        self.assertIn("push enviado", resultado)
        self.assertEqual(
            [chamada.args[0] for chamada in rodar.call_args_list],
            [
                ["git", "add", "."],
                ["git", "commit", "-m", "feat: adiciona uma melhoria"],
                ["git", "push"],
            ],
        )

    def test_cria_log_markdown_quando_ausente(self):
        with tempfile.TemporaryDirectory() as repo:
            os.mkdir(os.path.join(repo, ".git"))
            with (
                patch("committer.obter_status_repositorio", return_value=(True, 0)),
                patch("committer._rodar", return_value=(0, "ok", "")),
            ):
                sucesso, _ = committer.executar_geracao_contribuicao(
                    repo, "docs", "documenta a melhoria"
                )

            with open(os.path.join(repo, "log.md"), encoding="utf-8") as log:
                conteudo = log.read()

        self.assertTrue(sucesso)
        self.assertTrue(conteudo.startswith("# Registro de contribuições\n\n"))
        self.assertIn("[docs] documenta a melhoria", conteudo)

    def test_tipo_fora_do_banco_nao_altera_arquivo(self):
        with tempfile.TemporaryDirectory() as repo:
            os.mkdir(os.path.join(repo, ".git"))
            with patch("committer.obter_status_repositorio", return_value=(True, 0)):
                sucesso, erro = committer.executar_geracao_contribuicao(
                    repo, "desconhecido", "mensagem inválida"
                )

            self.assertFalse(sucesso)
            self.assertIn("mensagem válida", erro)
            self.assertFalse(os.path.exists(os.path.join(repo, "log.md")))

    def test_falha_no_commit_nao_tenta_push(self):
        with tempfile.TemporaryDirectory() as repo:
            os.mkdir(os.path.join(repo, ".git"))
            with (
                patch("committer.obter_status_repositorio", return_value=(True, 0)),
                patch(
                    "committer._rodar",
                    side_effect=[(0, "add", ""), (1, "", "falha no commit")],
                ) as rodar,
            ):
                sucesso, _ = committer.executar_geracao_contribuicao(
                    repo, "fix", "corrige uma falha"
                )

        self.assertFalse(sucesso)
        self.assertEqual(rodar.call_count, 2)

    @patch("committer._rodar", side_effect=[(0, "added", ""), (0, "committed", ""), (0, "pushed", "")])
    def test_fluxo_comum_executa_add_commit_e_push_em_ordem(self, rodar):
        sucesso, saida = committer._commitar_alteracoes(
            "C:\\repositorio", "feat: novo recurso", True
        )

        self.assertTrue(sucesso)
        self.assertIn("committed", saida)
        self.assertEqual(
            [chamada.args[0] for chamada in rodar.call_args_list],
            [
                ["git", "add", "-A"],
                ["git", "commit", "-m", "feat: novo recurso"],
                ["git", "push"],
            ],
        )

    @patch("committer._commitar_alteracoes", return_value=(True, "Commit concluído."))
    @patch("committer.obter_status_repositorio", return_value=(True, 2))
    @patch("committer.os.path.isdir", return_value=True)
    def test_reutiliza_fluxo_git_com_mensagem_fornecida(
        self, _diretorio, obter_status, commitar
    ):
        resultado = committer.executar_commit_direto(
            "C:\\repositorio", "feat: adiciona recurso", push=True
        )

        self.assertEqual(resultado, (True, "Commit concluído."))
        obter_status.assert_called_once_with("C:\\repositorio")
        commitar.assert_called_once_with(
            "C:\\repositorio", "feat: adiciona recurso", True
        )

    @patch("committer._commitar_alteracoes")
    @patch("committer.obter_status_repositorio", return_value=(True, 0))
    @patch("committer.os.path.isdir", return_value=True)
    def test_nao_cria_commit_quando_nao_ha_alteracoes(
        self, _diretorio, _obter_status, commitar
    ):
        resultado = committer.executar_commit_direto(
            "C:\\repositorio", "docs: atualiza instruções"
        )

        self.assertEqual(resultado, (True, "Não há alterações novas para commitar."))
        commitar.assert_not_called()

    def test_mensagem_vazia_e_recusada(self):
        resultado = committer.executar_commit_direto("C:\\repositorio", "  ")

        self.assertEqual(resultado, (False, "Informe uma mensagem para o commit."))

    def test_fluxo_automatico_existente_continua_usando_commit_compartilhado(self):
        job = {
            "repo_path": "C:\\repositorio",
            "modo_conteudo": "mensagens",
            "push_automatico": True,
        }
        with (
            patch("committer.validar_job", return_value={}),
            patch("committer._proxima_mensagem", return_value="feat: recurso"),
            patch("committer._alterar_arquivo", return_value=(True, "Arquivo atualizado.")),
            patch(
                "committer._commitar_alteracoes",
                return_value=(True, "commit concluído"),
            ) as fluxo_git,
        ):
            sucesso, saida = committer.executar_commit(job)

        self.assertTrue(sucesso)
        self.assertIn("Arquivo atualizado.", saida)
        fluxo_git.assert_called_once_with("C:\\repositorio", "feat: recurso", True)


if __name__ == "__main__":
    unittest.main()
