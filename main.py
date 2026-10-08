"""Inicialização da janela nativa, bandeja e controle de instância única."""

import argparse
import os
from pathlib import Path

import webview

from backend.api import Api
from single_instance import adquirir_instancia
from system_tray import BandejaSistema


def _mostrar_janela(janela):
    try:
        janela.restore()
        janela.show()
        janela.focus()
    except (AttributeError, RuntimeError):
        pass


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--background", action="store_true")
    argumentos, _desconhecidos = parser.parse_known_args()

    instancia = adquirir_instancia()
    if instancia is None:
        return

    pagina = (Path(__file__).resolve().parent / "web" / "index.html").as_uri()
    api = Api()
    bandeja = None
    janela = webview.create_window(
        "Auto Committer",
        pagina,
        js_api=api,
        width=1120,
        height=800,
        min_size=(360, 560),
        hidden=argumentos.background,
    )
    if os.name == "nt":
        bandeja = BandejaSistema(
            lambda: _mostrar_janela(janela),
            api.alternar_pausa_agendamento,
            api.sair_aplicativo,
            lambda: api.obter_estado_agendamento().get("estado", {}),
        )
        api.configurar_bandeja(bandeja, janela)
        bandeja.iniciar(argumentos.background)
    instancia.observar_ativacao(lambda: _mostrar_janela(janela))
    janela.events.closing += api.ao_fechar_janela

    try:
        api.inicializar_agendamento_persistente()
        webview.start(debug=False)
    finally:
        api._ao_fechar()
        if bandeja:
            bandeja.fechar()
        instancia.fechar()


if __name__ == "__main__":
    main()
