"""
main.py
Ponto de entrada do Auto Committer.

Comportamento:
- Ao iniciar (inclusive junto com o Windows), sobe silenciosamente com
  um ícone na bandeja do sistema — SEM abrir janela nenhuma.
- Se o usuário abrir o executável de novo enquanto já está rodando,
  a instância já ativa recebe um sinal e abre a janela de configuração.
- O agendador roda em background e dispara os commits conforme a
  agenda anti-spam configurada.
"""

import datetime
import logging
import logging.handlers
import os
import socket
import sys
import threading
import tkinter as tk

import pystray
from PIL import Image, ImageDraw

import config
import scheduler
from gui import JanelaPrincipal

PORTA_INSTANCIA_UNICA = 51765


def _precisa_separador_de_dia():
    """Verifica se a última linha já gravada no log é de um dia diferente
    de hoje — usado pra decidir se insere uma linha separadora antes de
    continuar gravando os registros de hoje, deixando o histórico
    organizado por dia em vez de tudo misturado."""
    if not os.path.exists(config.CAMINHO_LOG):
        return False
    try:
        with open(config.CAMINHO_LOG, "r", encoding="utf-8", errors="ignore") as arq:
            linhas = [linha for linha in arq if linha.strip()]
    except OSError:
        return False
    if not linhas:
        return False
    try:
        data_ultima_linha = datetime.datetime.strptime(linhas[-1][:10], "%Y-%m-%d").date()
    except ValueError:
        # última linha não começa com uma data reconhecível (ex: já é um
        # separador de dia) — não insere separador duplicado
        return False
    return data_ultima_linha != datetime.date.today()


def _escrever_separador_de_dia():
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    try:
        with open(config.CAMINHO_LOG, "a", encoding="utf-8") as arq:
            arq.write(f"--------- {hoje} ----------\n")
    except OSError:
        pass


def configurar_log_em_arquivo():
    """Grava logs em arquivo (rotacionando em até ~1MB x 3 arquivos), porque
    em modo --silencioso (bandeja, sem console) os print() não vão pra
    lugar nenhum — sem isso, um erro em segundo plano fica invisível.

    Se o programa já tinha registros de um dia anterior, insere uma linha
    separadora antes de continuar gravando os registros de hoje."""
    if _precisa_separador_de_dia():
        _escrever_separador_de_dia()

    logger = logging.getLogger("auto_committer")
    logger.setLevel(logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        config.CAMINHO_LOG, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger


LOGGER_ARQUIVO = configurar_log_em_arquivo()


def _registrar_excecao_nao_tratada(tipo, valor, traceback_obj):
    """Sem isso, um crash em modo --silencioso (sem console) simplesmente
    faz o programa sumir da bandeja sem deixar nenhum rastro do motivo."""
    LOGGER_ARQUIVO.error("Erro não tratado — o programa vai encerrar.",
                          exc_info=(tipo, valor, traceback_obj))
    sys.__excepthook__(tipo, valor, traceback_obj)


sys.excepthook = _registrar_excecao_nao_tratada


# ---------------- instância única ----------------

def ja_existe_instancia_rodando():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", PORTA_INSTANCIA_UNICA))
        s.sendall(b"MOSTRAR")
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def iniciar_ouvinte_instancia_unica(callback_mostrar_janela):
    def alvo():
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind(("127.0.0.1", PORTA_INSTANCIA_UNICA))
        servidor.listen(5)
        while True:
            conexao, _ = servidor.accept()
            try:
                dado = conexao.recv(1024)
                if dado.strip() == b"MOSTRAR":
                    callback_mostrar_janela()
            finally:
                conexao.close()

    thread = threading.Thread(target=alvo, daemon=True)
    thread.start()


# ---------------- ícone da bandeja ----------------

def _criar_imagem_icone():
    tamanho = 64
    imagem = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.ellipse((4, 4, tamanho - 4, tamanho - 4), fill=(0, 212, 255, 255))
    desenho.text((18, 16), "AC", fill=(13, 17, 23, 255))
    return imagem


class AplicativoBandeja:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # nunca mostra a janela raiz

        self.agendador = scheduler.Agendador(callback_log=self._log)
        self.janela = None
        self.icone = None

        config.carregar_config()  # garante que config.json existe

    def _log(self, texto):
        print(texto)
        LOGGER_ARQUIVO.info(texto)
        if self.janela is not None and self.janela.winfo_exists():
            try:
                self.janela.adicionar_log(texto)
            except tk.TclError:
                pass

    # ---------------- janela ----------------

    def mostrar_janela(self):
        def acao():
            if self.janela is None or not self.janela.winfo_exists():
                self.janela = JanelaPrincipal(self.root, self.agendador)
            self.janela.deiconify()
            self.janela.lift()
            self.janela.focus_force()

        self.root.after(0, acao)

    # ---------------- bandeja ----------------

    def _montar_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Abrir configurações", lambda: self.mostrar_janela(), default=True),
            pystray.MenuItem(
                "Pausar",
                self._alternar_pausa,
                checked=lambda item: self.agendador.esta_pausado()
            ),
            pystray.MenuItem("Sair", self._sair),
        )

    def _alternar_pausa(self, icone=None, item=None):
        if self.agendador.esta_pausado():
            self.agendador.retomar()
        else:
            self.agendador.pausar()

    def _sair(self, icone=None, item=None):
        self.agendador.parar()
        if self.icone:
            self.icone.stop()
        self.root.after(0, self.root.quit)

    def iniciar_bandeja(self):
        self.icone = pystray.Icon("AutoCommitter", _criar_imagem_icone(), "Auto Committer", self._montar_menu())
        thread = threading.Thread(target=self.icone.run, daemon=True)
        thread.start()

    # ---------------- ciclo de vida ----------------

    def rodar(self):
        self.agendador.iniciar()
        self.iniciar_bandeja()
        iniciar_ouvinte_instancia_unica(self.mostrar_janela)
        self.root.mainloop()


def main():
    if ja_existe_instancia_rodando():
        # já tem um processo rodando: só pedimos pra ele mostrar a janela e saímos
        sys.exit(0)

    app = AplicativoBandeja()

    # se foi aberto manualmente (não silencioso), mostra a janela de configuração
    # já na primeira execução, para o usuário configurar os trabalhos.
    if "--silencioso" not in sys.argv:
        app.root.after(300, app.mostrar_janela)

    app.rodar()


if __name__ == "__main__":
    main()