import os
import tempfile
import unittest

import committer


class ValidacaoExecucaoTests(unittest.TestCase):
    def test_caminho_alvo_precisa_ficar_dentro_do_repositorio(self):
        with tempfile.TemporaryDirectory() as temporario:
            repo = os.path.join(temporario, "repo")
            os.makedirs(os.path.join(repo, ".git"))
            job = {
                "nome": "Teste",
                "repo_path": repo,
                "arquivo_alvo": "atualizacoes.md",
                "modo_conteudo": "linha_data",
                "hora_inicio": "08:00",
                "hora_fim": "22:00",
                "commits_min_dia": 1,
                "commits_max_dia": 3,
                "intervalo_min_minutos": 45,
                "chance_pular_dia": 0.15,
            }

            self.assertEqual(committer.validar_job(job), {})

            job["arquivo_alvo"] = "..\\fora.md"
            erros = committer.validar_job(job)

        self.assertIn("arquivo_alvo", erros)


if __name__ == "__main__":
    unittest.main()
