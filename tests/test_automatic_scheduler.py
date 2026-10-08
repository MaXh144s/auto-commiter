import datetime
import json
import os
import tempfile
import threading
import time
import unittest

import automatic_scheduler


class AgendamentoAutomaticoTests(unittest.TestCase):
    def test_sorteia_alvo_entre_os_limites_inclusivos(self):
        class SorteadorFalso:
            @staticmethod
            def randint(minimo, maximo):
                self.assertEqual((minimo, maximo), (2, 5))
                return 4

        self.assertEqual(
            automatic_scheduler.sortear_alvo_diario(2, 5, SorteadorFalso),
            4,
        )

    def test_dia_da_semana_ativo_e_inativo(self):
        segunda = datetime.datetime(2026, 10, 5)
        domingo = datetime.datetime(2026, 10, 11)

        self.assertTrue(automatic_scheduler.hoje_ativo(segunda, [0, 2, 4]))
        self.assertFalse(automatic_scheduler.hoje_ativo(domingo, [0, 2, 4]))

    def test_virada_do_dia_reinicia_alvo_e_contagem(self):
        estado = {
            "data": "2026-10-06",
            "alvo": 3,
            "feitos": 2,
            "ultima_mensagem": "feat: recurso",
            "proximo_commit": 1791320000,
        }

        novo = automatic_scheduler.restaurar_estado_diario(
            estado, datetime.date(2026, 10, 7)
        )

        self.assertEqual(novo["data"], "2026-10-07")
        self.assertIsNone(novo["alvo"])
        self.assertEqual(novo["feitos"], 0)
        self.assertEqual(novo["ultima_mensagem"], "feat: recurso")
        self.assertIsNone(novo["proximo_commit"])

    def test_mudar_repositorio_reinicia_progresso_do_dia(self):
        estado = {
            "data": datetime.date.today().isoformat(),
            "alvo": 3,
            "feitos": 2,
            "ultima_mensagem": "feat: recurso",
            "repo_path": "C:\\repositorio-antigo",
        }

        novo = automatic_scheduler.restaurar_estado_diario(
            estado, datetime.date.today(), "C:\\repositorio-novo"
        )

        self.assertIsNone(novo["alvo"])
        self.assertEqual(novo["feitos"], 0)
        self.assertEqual(novo["repo_path"], "C:\\repositorio-novo")

    def test_estado_diario_e_retomado_apos_recriar_agendador(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "agendamento.json")
            estado = {
                "data": datetime.date.today().isoformat(),
                "alvo": 4,
                "feitos": 2,
                "ultima_mensagem": "feat: item anterior",
                "proximo_commit": None,
            }
            with open(caminho, "w", encoding="utf-8") as arquivo:
                json.dump(estado, arquivo)

            agendador = automatic_scheduler.AgendadorAutomatico(
                lambda *_args: {"ok": True}, caminho
            )

            self.assertEqual(agendador.estado()["alvo"], 4)
            self.assertEqual(agendador.estado()["feitos"], 2)

    def test_commit_agendado_persiste_progresso_para_retomada(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "agendamento.json")
            commit_executado = threading.Event()

            def executar_commit(_repo, _mensagens, _anterior):
                commit_executado.set()
                return {
                    "ok": True,
                    "mensagem_escolhida": {
                        "tipo": "feat",
                        "mensagem": "novo recurso",
                    },
                }

            agendador = automatic_scheduler.AgendadorAutomatico(
                executar_commit, caminho
            )
            dias = [datetime.date.today().weekday()]
            iniciado, _ = agendador.iniciar(
                {
                    "dias_semana": dias,
                    "intervalo_minutos": 1,
                    "commits_min_dia": 1,
                    "commits_max_dia": 1,
                },
                "C:\\repositorio",
                [
                    {"tipo": "feat", "mensagem": "novo recurso"},
                    {"tipo": "fix", "mensagem": "corrige erro"},
                ],
            )
            self.assertTrue(iniciado)
            self.assertTrue(commit_executado.wait(2))

            limite = time.monotonic() + 2
            while agendador.estado()["feitos"] != 1 and time.monotonic() < limite:
                time.sleep(0.01)
            agendador.parar(aguardar=True)
            retomado = automatic_scheduler.AgendadorAutomatico(
                executar_commit, caminho
            )

            self.assertEqual(retomado.estado()["alvo"], 1)
            self.assertEqual(retomado.estado()["feitos"], 1)
            self.assertEqual(
                retomado._estado["ultima_mensagem"], "feat: novo recurso"
            )

    def test_agendamento_rejeita_banco_sem_mensagem_distinta(self):
        with tempfile.TemporaryDirectory() as pasta:
            agendador = automatic_scheduler.AgendadorAutomatico(
                lambda *_args: {"ok": True},
                os.path.join(pasta, "agendamento.json"),
            )

            iniciado, erro = agendador.iniciar(
                {
                    "dias_semana": [datetime.date.today().weekday()],
                    "intervalo_minutos": 1,
                    "commits_min_dia": 1,
                    "commits_max_dia": 1,
                },
                "C:\\repositorio",
                [{"tipo": "feat", "mensagem": "repetida"}],
            )

        self.assertFalse(iniciado)
        self.assertIn("duas mensagens diferentes", erro)

    def test_agendamento_para_apos_tres_falhas_consecutivas(self):
        with tempfile.TemporaryDirectory() as pasta:
            agendador = automatic_scheduler.AgendadorAutomatico(
                lambda *_args: {"ok": False, "erro": "Falha simulada."},
                os.path.join(pasta, "agendamento.json"),
            )
            agendador._configuracoes = {
                "dias_semana": [datetime.date.today().weekday()],
                "intervalo_minutos": 1,
                "commits_min_dia": 1,
                "commits_max_dia": 3,
            }
            agendador._repo_path = "C:\\repositorio"
            agendador._mensagens = [
                {"tipo": "feat", "mensagem": "mensagem A"},
                {"tipo": "fix", "mensagem": "mensagem B"},
            ]
            agendador._estado["alvo"] = 3
            for _ in range(3):
                agendador._estado["proximo_commit"] = None
                agendador._executar_um_commit()
            estado = agendador.estado()

        self.assertFalse(estado["ativo"])
        self.assertIn("3 falhas", estado["mensagem"])
        self.assertEqual(estado["falhas_seguidas"], 3)

    def test_intervalo_zero_e_rejeitado(self):
        with self.assertRaises(automatic_scheduler.SchedulerConfigError):
            automatic_scheduler.validar_configuracoes(
                {
                    "dias_semana": [0],
                    "intervalo_minutos": 0,
                    "commits_min_dia": 1,
                    "commits_max_dia": 1,
                }
            )

    def test_validacao_rejeita_minimo_maior_que_maximo(self):
        with self.assertRaises(automatic_scheduler.SchedulerConfigError):
            automatic_scheduler.validar_configuracoes(
                {
                    "dias_semana": [0],
                    "intervalo_minutos": 1,
                    "commits_min_dia": 3,
                    "commits_max_dia": 2,
                }
            )


if __name__ == "__main__":
    unittest.main()
