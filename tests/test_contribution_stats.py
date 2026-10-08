import unittest
from datetime import date

from contribution_stats import calcular_estatisticas


class EstatisticasContribuicoesTests(unittest.TestCase):
    def test_calcula_total_sequencias_e_dia_mais_ativo(self):
        dias = [
            {"date": "2025-01-01", "contributionCount": 1},
            {"date": "2025-01-02", "contributionCount": 2},
            {"date": "2025-01-03", "contributionCount": 3},
            {"date": "2025-01-04", "contributionCount": 4},
            {"date": "2025-01-05", "contributionCount": 0},
            {"date": "2025-01-06", "contributionCount": 1},
        ]

        resultado = calcular_estatisticas(dias, hoje=date(2025, 1, 7))

        self.assertEqual(resultado["total_contributions"], 11)
        self.assertEqual(resultado["current_streak"], 1)
        self.assertEqual(resultado["longest_streak"], 4)
        self.assertEqual(
            resultado["most_productive_day"],
            {"date": "2025-01-04", "count": 4},
        )

    def test_sequencia_atual_pode_terminar_ontem(self):
        dias = [
            {"date": "2025-02-01", "contributionCount": 2},
            {"date": "2025-02-02", "contributionCount": 1},
            {"date": "2025-02-03", "contributionCount": 0},
        ]

        resultado = calcular_estatisticas(dias, hoje=date(2025, 2, 3))

        self.assertEqual(resultado["current_streak"], 2)

    def test_periodo_sem_contribuicoes(self):
        resultado = calcular_estatisticas([], hoje=date(2025, 1, 1))

        self.assertEqual(resultado["total_contributions"], 0)
        self.assertEqual(resultado["current_streak"], 0)
        self.assertEqual(resultado["longest_streak"], 0)
        self.assertIsNone(resultado["most_productive_day"])


if __name__ == "__main__":
    unittest.main()
