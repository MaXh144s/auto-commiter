import json
import os
import tempfile
import unittest
from unittest.mock import patch

import config


class PersistenciaTokenTests(unittest.TestCase):
    def test_configuracao_nunca_grava_o_token(self):
        with tempfile.TemporaryDirectory() as temporario:
            caminho_gerados = os.path.join(temporario, "gerados")
            caminho_estado = os.path.join(caminho_gerados, "estado")
            caminho_config = os.path.join(caminho_gerados, "config.json")
            dados = {
                "geral": {"github_token": "token-de-teste", "iniciar_com_windows": False},
                "jobs": [],
            }
            with (
                patch.object(config, "PASTA_GERADOS", caminho_gerados),
                patch.object(config, "PASTA_ESTADO", caminho_estado),
                patch.object(config, "CAMINHO_CONFIG", caminho_config),
            ):
                config.salvar_config(dados)
                with open(caminho_config, encoding="utf-8") as arquivo:
                    salvo = json.load(arquivo)

        self.assertNotIn("github_token", salvo["geral"])
        self.assertNotIn("token-de-teste", json.dumps(salvo))

    def test_migracao_remove_token_de_configuracao_antiga(self):
        with tempfile.TemporaryDirectory() as temporario:
            caminho_gerados = os.path.join(temporario, "gerados")
            caminho_estado = os.path.join(caminho_gerados, "estado")
            caminho_config = os.path.join(caminho_gerados, "config.json")
            os.makedirs(caminho_gerados)
            with open(caminho_config, "w", encoding="utf-8") as arquivo:
                json.dump(
                    {"geral": {"github_token": "token-antigo"}, "jobs": []},
                    arquivo,
                )
            with (
                patch.object(config, "PASTA_GERADOS", caminho_gerados),
                patch.object(config, "PASTA_ESTADO", caminho_estado),
                patch.object(config, "CAMINHO_CONFIG", caminho_config),
            ):
                config.carregar_config()
                with open(caminho_config, encoding="utf-8") as arquivo:
                    salvo = json.load(arquivo)

        self.assertNotIn("github_token", salvo["geral"])
        self.assertNotIn("token-antigo", json.dumps(salvo))


if __name__ == "__main__":
    unittest.main()
