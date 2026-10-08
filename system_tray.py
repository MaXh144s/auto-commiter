"""Bandeja de sistema em thread dedicada."""

import threading

import pystray
from PIL import Image, ImageDraw


class BandejaSistema:
    def __init__(self, ao_abrir, ao_pausar, ao_sair, obter_estado):
        self._ao_abrir = ao_abrir
        self._ao_pausar = ao_pausar
        self._ao_sair = ao_sair
        self._obter_estado = obter_estado
        self._icone = None
        self._thread = None
        self._primeira_ocultacao = True
        self._monitor = threading.Event()
        self._ultimo_erro = ""

    @staticmethod
    def _imagem(problema=False):
        imagem = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        desenho = ImageDraw.Draw(imagem)
        desenho.rounded_rectangle((5, 5, 59, 59), radius=17, fill="#202c40")
        desenho.rounded_rectangle((8, 8, 56, 56), radius=14, outline="#9eb9ff", width=2)
        desenho.text((18, 23), "AC", fill="#d7e2ff")
        if problema:
            desenho.ellipse((44, 5, 60, 21), fill="#ff7777")
        return imagem

    def iniciar(self, notificar_oculto=False):
        if self._icone:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Abrir", lambda _icone, _item: self._ao_abrir(), default=True),
            pystray.MenuItem(
                lambda _item: (
                    "Automação após o primeiro commit"
                    if not self._obter_estado().get("ativado")
                    else (
                        "Retomar commits automáticos"
                        if self._obter_estado().get("pausado")
                        else "Pausar commits automáticos"
                    )
                ),
                lambda _icone, _item: self._ao_pausar(),
                enabled=lambda _item: bool(
                    self._obter_estado().get("ativado")
                ),
            ),
            pystray.MenuItem("Sair", lambda _icone, _item: self._ao_sair()),
        )
        self._icone = pystray.Icon(
            "AutoCommitter",
            self._imagem(),
            "Auto Committer",
            menu,
        )
        self._thread = threading.Thread(
            target=self._icone.run,
            name="auto-committer-bandeja",
            daemon=True,
        )
        self._thread.start()
        if notificar_oculto:
            threading.Timer(1, self.ocultar_notificando).start()
        threading.Thread(
            target=self._monitorar_estado,
            name="auto-committer-bandeja-estado",
            daemon=True,
        ).start()

    def _monitorar_estado(self):
        while not self._monitor.wait(2):
            estado = self._obter_estado()
            self.atualizar_estado()
            erro = str(estado.get("erro") or "")
            if erro and erro != self._ultimo_erro:
                self.avisar(erro)
            self._ultimo_erro = erro

    def ocultar_notificando(self):
        if self._primeira_ocultacao and self._icone:
            self._primeira_ocultacao = False
            self._icone.notify(
                "O Auto Committer continua funcionando na bandeja do sistema.",
                "Auto Committer",
            )

    def atualizar_estado(self):
        if not self._icone:
            return
        estado = self._obter_estado()
        erro = bool(estado.get("erro") or estado.get("falhas_seguidas", 0) >= 3)
        self._icone.icon = self._imagem(erro)
        self._icone.title = (
            "Auto Committer — precisa de atenção"
            if erro
            else "Auto Committer"
        )
        self._icone.update_menu()

    def avisar(self, mensagem):
        if self._icone:
            self._ultimo_erro = str(mensagem)
            self._icone.notify(mensagem, "Auto Committer")

    def fechar(self):
        self._monitor.set()
        if self._icone:
            self._icone.stop()
            self._icone = None
