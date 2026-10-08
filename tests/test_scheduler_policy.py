import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from backend.api import Api
import automatic_scheduler
import scheduler_state


class PoliticaAgendamentoTests(unittest.TestCase):
    def test_decide_modal_por_intervalo_e_proximidade(self):
        agora = 1_800_000_000

        self.assertTrue(
            automatic_scheduler.deve_exibir_modal_commit(
                agora - 120,
                agora + 3_000,
                agora,
                intervalo_minutos=60,
            )
        )
        self.assertTrue(
            automatic_scheduler.deve_exibir_modal_commit(
                agora - 4_000,
                agora + 120,
                agora,
                intervalo_minutos=60,
            )
        )
        self.assertFalse(
            automatic_scheduler.deve_exibir_modal_commit(
                agora - 4_000,
                agora + 600,
                agora,
                intervalo_minutos=60,
            )
        )

    def test_formata_duracoes_legiveis(self):
        self.assertEqual(automatic_scheduler.formatar_duracao(12 * 60), "12 min")
        self.assertEqual(
            automatic_scheduler.formatar_duracao(80 * 60), "1 h 20 min"
        )
        self.assertEqual(
            automatic_scheduler.formatar_duracao(15), "agora há pouco"
        )

    def test_estado_persistido_e_gravado_atomicamente(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "estado.json")
            estado = {"ultimo_commit_timestamp": 1_800_000_000, "feitos": 2}

            scheduler_state.salvar_estado_atomico(caminho, estado)

            with open(caminho, encoding="utf-8") as arquivo:
                self.assertEqual(json.load(arquivo), estado)
            self.assertFalse(os.path.exists(f"{caminho}.tmp"))

    @patch("backend.api.config.salvar_config")
    @patch(
        "backend.api.config.carregar_config",
        return_value={
            "geral": {},
            "agendamento_automatico": {
                "dias_semana": [datetime.datetime.now().astimezone().weekday()],
                "intervalo_minutos": 60,
                "commits_min_dia": 2,
                "commits_max_dia": 2,
                "repo_path": "",
                "banco_mensagens": [],
            },
            "jobs": [],
        },
    )
    @patch.object(
        Api,
        "_obter_commit_atual",
        return_value={
            "oid": "abc123",
            "timestamp": 1_800_000_000,
            "assunto": "feat: inicia automação",
        },
    )
    @patch(
        "backend.api.committer.executar_geracao_contribuicao",
        return_value=(True, "Commit concluído."),
    )
    def test_primeiro_commit_manual_ativa_e_persiste_agendamento(
        self, _executar, _head, _salvar_config, _carregar_config
    ):
        with tempfile.TemporaryDirectory() as pasta:
            caminho_estado = os.path.join(pasta, "agendamento.json")
            api = Api(caminho_estado)
            estado_inicial = api.obter_estado_agendamento()["estado"]
            banco = [
                {"tipo": "feat", "mensagem": "inicia automação"},
                {"tipo": "fix", "mensagem": "corrige fluxo"},
            ]

            resposta = api.fazer_commit(
                "C:\\repositorio",
                "feat",
                "inicia automação",
                False,
                banco,
            )
            estado_final = api.obter_estado_agendamento()["estado"]
            api._agendador.parar(aguardar=True)

            self.assertFalse(estado_inicial["ativado"])
            self.assertTrue(resposta["ok"])
            self.assertTrue(estado_final["ativado"])
            self.assertEqual(estado_final["feitos"], 1)
            self.assertIsNotNone(estado_final["ultimo_commit_timestamp"])
            self.assertTrue(os.path.isfile(caminho_estado))

    def test_retomada_respeita_timestamp_utc_salvo(self):
        agora_local = datetime.datetime.now().astimezone()
        instante = agora_local.timestamp()
        estado = {
            "data": agora_local.date().isoformat(),
            "alvo": 3,
            "feitos": 1,
            "ultimo_commit_timestamp": instante,
            "ultimo_commit_oid": "abc123",
            "proximo_commit": instante + 3_600,
            "repo_path": "C:\\repositorio",
            "ativado": True,
            "pausado": False,
        }

        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "agendamento.json")
            scheduler_state.salvar_estado_atomico(caminho, estado)
            agendador = automatic_scheduler.AgendadorAutomatico(
                lambda *_args: {"ok": True}, caminho
            )
            agendador.atualizar_configuracoes(
                {
                    "dias_semana": [agora_local.weekday()],
                    "intervalo_minutos": 60,
                    "commits_min_dia": 1,
                    "commits_max_dia": 3,
                },
                "C:\\repositorio",
                [
                    {"tipo": "feat", "mensagem": "A"},
                    {"tipo": "fix", "mensagem": "B"},
                ],
            )
            previsao = agendador.prever_commit_manual()

        self.assertEqual(
            previsao["ultimo_commit_timestamp"], instante
        )
        self.assertTrue(previsao["mostrar_modal"])


if __name__ == "__main__":
    unittest.main()
