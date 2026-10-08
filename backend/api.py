"""Ponte entre a interface web e as operações locais do aplicativo."""

import os
import subprocess
import threading
from datetime import datetime

import committer
import commit_message_selector
import config
import windows_startup
from automatic_scheduler import (
    AgendadorAutomatico,
    SchedulerConfigError,
    validar_configuracoes,
)


class Api:
    def __init__(self, caminho_estado=None):
        self._historico = []
        self._agendador = AgendadorAutomatico(
            self._executar_commit_agendado, caminho_estado
        )
        self._commit_lock = threading.Lock()
        self._bandeja = None
        self._janela = None
        self._saindo = False

    def configurar_bandeja(self, bandeja, janela):
        self._bandeja = bandeja
        self._janela = janela

    def obter_configuracoes_aplicativo(self):
        try:
            geral = config.carregar_config().get("geral", {})
            inicio = windows_startup.ler_inicio_com_windows()
            if inicio.get("erro"):
                return {"ok": False, "erro": inicio["erro"]}
            return {
                "ok": True,
                "iniciar_com_windows": inicio,
                "bandeja_disponivel": os.name == "nt",
                "fechar_para_bandeja": (
                    os.name == "nt"
                    and bool(geral.get("fechar_para_bandeja", True))
                ),
            }
        except (OSError, TypeError, ValueError):
            return {
                "ok": False,
                "erro": "Não foi possível carregar as configurações do aplicativo.",
            }

    def definir_inicio_com_windows(self, ativado=False):
        sucesso, mensagem = windows_startup.definir_inicio_com_windows(bool(ativado))
        if not sucesso:
            return {"ok": False, "erro": mensagem}
        estado = windows_startup.ler_inicio_com_windows()
        if estado.get("erro"):
            return {"ok": False, "erro": estado["erro"]}
        return {"ok": True, "mensagem": mensagem, **estado}

    def definir_fechar_para_bandeja(self, ativado=False):
        try:
            dados = config.carregar_config()
            dados.setdefault("geral", {})["fechar_para_bandeja"] = bool(ativado)
            config.salvar_config(dados)
        except (OSError, TypeError, ValueError):
            return {
                "ok": False,
                "erro": "Não foi possível salvar a preferência da bandeja.",
            }
        return {"ok": True, "fechar_para_bandeja": bool(ativado)}

    def inicializar_agendamento_persistente(self):
        estado = self._agendador.estado()
        if not estado.get("ativado"):
            return {"ok": True, "estado": estado}
        if estado.get("pausado"):
            if estado.get("erro") and self._bandeja:
                self._bandeja.avisar(estado["erro"])
            return {"ok": True, "estado": estado}
        try:
            automatico = config.carregar_config()["agendamento_automatico"]
            configuracoes = validar_configuracoes(automatico)
            repo_path = str(automatico.get("repo_path", "")).strip()
            mensagens = automatico.get("banco_mensagens", [])
            valido, _ = committer.obter_status_repositorio(repo_path)
            if not valido or not mensagens:
                mensagem = (
                    "O repositório ou o banco de mensagens não está disponível. "
                    "O agendamento foi pausado."
                )
                self._agendador.pausar_por_erro(mensagem)
                if self._bandeja:
                    self._bandeja.avisar(mensagem)
                return {"ok": False, "erro": mensagem, "estado": self._agendador.estado()}
            self._agendador.atualizar_configuracoes(
                configuracoes, repo_path, mensagens
            )
            head = self._obter_commit_atual(repo_path)
            if head:
                self._agendador.sincronizar_head(
                    repo_path,
                    head["oid"],
                    head["timestamp"],
                    head["assunto"],
                )
            sucesso, mensagem = self._agendador.iniciar(
                configuracoes, repo_path, mensagens, retomada=True
            )
            return {
                "ok": sucesso,
                "mensagem": mensagem if sucesso else None,
                "erro": None if sucesso else mensagem,
                "estado": self._agendador.estado(),
            }
        except (OSError, TypeError, ValueError, KeyError, subprocess.SubprocessError):
            mensagem = (
                "Não foi possível retomar o agendamento. Confira as configurações "
                "e o repositório."
            )
            self._agendador.pausar_por_erro(mensagem)
            if self._bandeja:
                self._bandeja.avisar(mensagem)
            return {"ok": False, "erro": mensagem, "estado": self._agendador.estado()}

    def obter_configuracoes_agendamento(self):
        try:
            configuracoes = config.carregar_config().get(
                "agendamento_automatico", {}
            )
            return {
                "ok": True,
                "configuracoes": {
                    "dias_semana": configuracoes.get("dias_semana", [0, 1, 2, 3, 4, 5, 6]),
                    "intervalo_minutos": configuracoes.get("intervalo_minutos", 60),
                    "commits_min_dia": configuracoes.get("commits_min_dia", 1),
                    "commits_max_dia": configuracoes.get("commits_max_dia", 3),
                },
                "repo_path": configuracoes.get("repo_path", ""),
                "banco_mensagens": configuracoes.get("banco_mensagens", []),
                "estado": self._agendador.estado(),
            }
        except (OSError, TypeError, ValueError, KeyError):
            return {
                "ok": False,
                "erro": "Não foi possível carregar as configurações do agendamento.",
                "estado": self._agendador.estado(),
            }

    def salvar_configuracoes_agendamento(
        self, configuracoes=None, repo_path="", mensagens=None
    ):
        try:
            validas = validar_configuracoes(configuracoes or {})
        except SchedulerConfigError as erro:
            return {"ok": False, "erro": str(erro)}

        caminho = str(repo_path or "").strip()
        banco = mensagens or []
        if caminho or banco:
            if not caminho or not banco:
                return {
                    "ok": False,
                    "erro": "Escolha um repositório e um banco de mensagens.",
                }
            try:
                try:
                    valido, _ = committer.obter_status_repositorio(caminho)
                except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
                    valido = False
            except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
                valido = False
            if not valido:
                return {
                    "ok": False,
                    "erro": "Escolha um repositório Git válido antes de salvar.",
                }
            if not banco:
                return {
                    "ok": False,
                    "erro": "Escolha um banco de mensagens para o agendamento.",
                }

        try:
            dados = config.carregar_config()
            atual = dados.get("agendamento_automatico", {})
            novo = {**atual, **validas}
            if caminho:
                novo["repo_path"] = caminho
                novo["banco_mensagens"] = banco
            dados["agendamento_automatico"] = novo
            config.salvar_config(dados)
            if self._agendador.estado().get("ativado") and caminho and banco:
                self._agendador.atualizar_configuracoes(validas, caminho, banco)
        except (OSError, TypeError, ValueError):
            return {
                "ok": False,
                "erro": "Não foi possível salvar as configurações do agendamento.",
            }
        return {"ok": True, "mensagem": "Configurações salvas."}

    def iniciar_agendamento(self, configuracoes=None, repo_path="", mensagens=None):
        if not self._agendador.estado().get("ativado"):
            return {
                "ok": False,
                "erro": "A automação será ativada após o primeiro commit manual.",
                "estado": self._agendador.estado(),
            }
        if self._agendador.estado()["ativo"]:
            return {
                "ok": False,
                "erro": "O agendamento já está ativo.",
                "estado": self._agendador.estado(),
            }
        try:
            validas = validar_configuracoes(configuracoes or {})
        except SchedulerConfigError as erro:
            return {"ok": False, "erro": str(erro)}
        caminho = str(repo_path or "").strip()
        banco = mensagens or []
        try:
            valido, _ = committer.obter_status_repositorio(caminho)
        except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
            valido = False
        if not valido:
            return {"ok": False, "erro": "Escolha um repositório Git válido."}
        if not banco:
            return {"ok": False, "erro": "Escolha um banco com mensagens válidas."}
        resposta = self.salvar_configuracoes_agendamento(
            validas, caminho, banco
        )
        if not resposta["ok"]:
            return resposta
        try:
            sucesso, mensagem = self._agendador.iniciar(validas, caminho, banco)
        except OSError:
            return {
                "ok": False,
                "erro": "Não foi possível salvar o estado do agendamento.",
                "estado": self._agendador.estado(),
            }
        return {
            "ok": sucesso,
            "mensagem": mensagem if sucesso else None,
            "erro": None if sucesso else mensagem,
            "estado": self._agendador.estado(),
        }

    def parar_agendamento(self):
        try:
            sucesso, mensagem = self._agendador.pausar()
        except OSError:
            return {
                "ok": False,
                "erro": "Não foi possível salvar o estado da automação.",
                "estado": self._agendador.estado(),
            }
        return {
            "ok": sucesso,
            "mensagem": mensagem if sucesso else None,
            "erro": None if sucesso else mensagem,
            "estado": self._agendador.estado(),
        }

    def retomar_agendamento(self):
        estado = self._agendador.estado()
        if not estado.get("ativado"):
            return {
                "ok": False,
                "erro": "A automação será ativada após o primeiro commit manual.",
                "estado": estado,
            }
        try:
            automatico = config.carregar_config()["agendamento_automatico"]
            configuracoes = validar_configuracoes(automatico)
            repo_path = str(automatico.get("repo_path", "")).strip()
            mensagens = automatico.get("banco_mensagens", [])
            valido, _ = committer.obter_status_repositorio(repo_path)
            if not valido or not mensagens:
                return {
                    "ok": False,
                    "erro": "Confira o repositório e o banco de mensagens.",
                    "estado": estado,
                }
            self._agendador.atualizar_configuracoes(
                configuracoes, repo_path, mensagens
            )
            if estado.get("ativo") and estado.get("pausado"):
                sucesso, mensagem = self._agendador.retomar()
            else:
                sucesso, mensagem = self._agendador.iniciar(
                    configuracoes, repo_path, mensagens, retomada=True
                )
        except (OSError, TypeError, ValueError, KeyError, subprocess.SubprocessError):
            return {
                "ok": False,
                "erro": "Não foi possível retomar o agendamento.",
                "estado": self._agendador.estado(),
            }
        return {
            "ok": sucesso,
            "mensagem": mensagem if sucesso else None,
            "erro": None if sucesso else mensagem,
            "estado": self._agendador.estado(),
        }

    def obter_estado_agendamento(self):
        return {"ok": True, "estado": self._agendador.estado()}

    def prever_commit_manual(self):
        previsao = self._agendador.prever_commit_manual()
        if previsao.get("erro"):
            return {"ok": False, "erro": previsao["erro"]}
        return {"ok": True, **previsao}

    def _ao_fechar(self, *_args):
        self._agendador.parar(aguardar=True)

    def ao_fechar_janela(self, window):
        if self._saindo:
            return True
        try:
            geral = config.carregar_config().get("geral", {})
            fechar_para_bandeja = os.name == "nt" and geral.get(
                "fechar_para_bandeja", True
            )
        except (OSError, TypeError, ValueError):
            fechar_para_bandeja = False
        if fechar_para_bandeja and self._bandeja:
            window.hide()
            self._bandeja.ocultar_notificando()
            return False
        self._agendador.parar(aguardar=True)
        return True

    def _ao_ocultar(self):
        if self._janela:
            self._janela.hide()
        if self._bandeja:
            self._bandeja.ocultar_notificando()

    def abrir_janela(self):
        if not self._janela:
            return {"ok": False, "erro": "A janela ainda não está pronta."}
        try:
            self._janela.restore()
            self._janela.show()
            self._janela.focus()
            return {"ok": True}
        except (AttributeError, RuntimeError):
            return {"ok": False, "erro": "Não foi possível abrir a janela."}

    def alternar_pausa_agendamento(self):
        if self._agendador.estado().get("pausado"):
            return self.retomar_agendamento()
        return self.parar_agendamento()

    def sair_aplicativo(self):
        self._saindo = True
        self._agendador.parar(aguardar=True)
        if self._bandeja:
            self._bandeja.fechar()
        if self._janela:
            self._janela.destroy()
        return {"ok": True}

    def _executar_commit_agendado(self, repo_path, mensagens, mensagem_anterior):
        with self._commit_lock:
            if self._agendador.eh_thread_de_execucao() and not self._agendador.pode_executar_agora():
                return {
                    "ok": False,
                    "erro": "O agendamento mudou antes do commit; a execução foi adiada.",
                }
            try:
                valido, _ = committer.obter_status_repositorio(repo_path)
            except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
                valido = False
            if not valido:
                mensagem = (
                    "O repositório configurado não está disponível. "
                    "O agendamento foi pausado."
                )
                self._agendador.pausar_por_erro(mensagem)
                if self._bandeja:
                    self._bandeja.avisar(mensagem)
                return {
                    "ok": False,
                    "erro": mensagem,
                }
            head_anterior = self._obter_commit_atual(repo_path)
            if head_anterior and self._agendador.sincronizar_head(
                repo_path,
                head_anterior["oid"],
                head_anterior["timestamp"],
                head_anterior["assunto"],
            ):
                return {
                    "ok": False,
                    "adiado": True,
                    "erro": (
                        "Foi detectado um commit recente no repositório. "
                        "O intervalo foi recalculado antes de continuar."
                    ),
                }
            try:
                mensagens_log = commit_message_selector.ler_mensagens_commit(repo_path)
                candidata = commit_message_selector.escolher_mensagem_diferente(
                    mensagens_log, mensagens, mensagem_anterior
                )
            except commit_message_selector.CommitLogError as erro:
                return {"ok": False, "erro": str(erro)}
            if candidata is None:
                return {
                    "ok": False,
                    "erro": "Não há outra mensagem disponível diferente do commit anterior.",
                }

            try:
                sucesso, resultado = committer.executar_geracao_contribuicao(
                    repo_path, candidata["tipo"], candidata["mensagem"]
                )
            except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
                return {
                    "ok": False,
                    "erro": "O commit automático não foi concluído. Confira o repositório e o Git.",
                }
            if not sucesso:
                return {"ok": False, "erro": resultado}
            head_atual = self._obter_commit_atual(repo_path)
            return {
                "ok": True,
                "mensagem_escolhida": candidata,
                "usos": candidata["frequencia"],
                "resultado": resultado,
                "commit_oid": head_atual["oid"] if head_atual else None,
            }

    @staticmethod
    def _obter_commit_atual(repo_path):
        try:
            resultado = subprocess.run(
                ["git", "log", "-1", "--format=%H%x1f%ct%x1f%s"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if resultado.returncode != 0 or not resultado.stdout.strip():
            return None
        try:
            oid, timestamp, assunto = resultado.stdout.strip().split("\x1f", 2)
            return {
                "oid": oid,
                "timestamp": float(timestamp),
                "assunto": assunto,
            }
        except (TypeError, ValueError):
            return None

    def selecionar_pasta(self):
        try:
            import webview
        except ImportError:
            return {"ok": False, "erro": "O seletor de pastas não está disponível."}

        try:
            janelas = webview.windows
            if not janelas:
                return {"ok": False, "erro": "A janela ainda não está pronta."}
            selecionadas = janelas[0].create_file_dialog(webview.FOLDER_DIALOG)
            if not selecionadas:
                return {"ok": True, "cancelado": True}
            return {"ok": True, "caminho": selecionadas[0]}
        except (
            AttributeError,
            IndexError,
            OSError,
            RuntimeError,
            webview.errors.WebViewException,
        ):
            return {"ok": False, "erro": "Não foi possível abrir a seleção de pastas."}

    def selecionar_banco_mensagens(self, repo_path=""):
        caminho_repo = str(repo_path or "").strip()
        try:
            valido, _ = committer.obter_status_repositorio(caminho_repo)
        except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
            valido = False
        if not valido:
            return {"ok": False, "erro": "Escolha primeiro uma pasta de repositório Git válida."}

        try:
            import webview
        except ImportError:
            return {"ok": False, "erro": "O seletor de arquivos não está disponível."}

        try:
            janelas = webview.windows
            if not janelas:
                return {"ok": False, "erro": "A janela ainda não está pronta."}
            selecionados = janelas[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Arquivos de mensagens (*.txt;*.csv)",),
            )
            if not selecionados:
                return {"ok": True, "cancelado": True}

            caminho_arquivo = selecionados[0]
            if os.path.splitext(caminho_arquivo)[1].lower() not in (".txt", ".csv"):
                return {"ok": False, "erro": "Escolha um arquivo .txt ou .csv."}
            mensagens = config.importar_banco_mensagens(caminho_arquivo)
            if not mensagens:
                return {"ok": False, "erro": "Este arquivo não contém mensagens para usar."}

            return {
                "ok": True,
                "nome": os.path.basename(caminho_arquivo),
                "mensagens": mensagens,
            }
        except (
            AttributeError,
            IndexError,
            OSError,
            RuntimeError,
            webview.errors.WebViewException,
        ):
            return {"ok": False, "erro": "Não foi possível abrir o banco de mensagens."}

    def listar_status(self, repo_path=""):
        caminho = str(repo_path or "").strip()
        resposta = {"ok": True, "historico": self._historico[-10:][::-1]}
        if not caminho:
            resposta.update(
                {"mensagem": "Escolha uma pasta para conferir as alterações.", "alteracoes": 0}
            )
            return resposta

        try:
            valido, quantidade = committer.obter_status_repositorio(caminho)
        except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
            return {
                "ok": False,
                "erro": "Não foi possível conferir esta pasta.",
                "historico": resposta["historico"],
            }
        if not valido:
            return {
                "ok": False,
                "erro": "A pasta escolhida não é um repositório Git válido.",
                "historico": resposta["historico"],
            }

        mensagem = (
            f"{quantidade} alteração(ões) aguardando commit."
            if quantidade
            else "Nenhuma alteração pendente nesta pasta."
        )
        resposta.update({"mensagem": mensagem, "alteracoes": quantidade})
        return resposta

    def sugerir_mensagem_commit(self, repo_path="", mensagens=None):
        try:
            mensagens_log = commit_message_selector.ler_mensagens_commit(repo_path)
            sugestao = commit_message_selector.escolher_mensagem(
                mensagens_log, mensagens or []
            )
        except commit_message_selector.CommitLogError as erro:
            return {"ok": False, "erro": str(erro)}
        if sugestao is None:
            return {"ok": False, "erro": "O banco não contém mensagens válidas."}
        return {
            "ok": True,
            "mensagem": {
                "tipo": sugestao["tipo"],
                "mensagem": sugestao["mensagem"],
            },
            "usos": sugestao["frequencia"],
        }

    def fazer_commit(
        self,
        repo_path="",
        tipo="",
        mensagem="",
        evitar_repetidas=False,
        mensagens_banco=None,
        confirmar_agora=False,
        timestamp_confirmado=None,
        proximo_timestamp_confirmado=None,
    ):
        with self._commit_lock:
            aviso = self._agendador.prever_commit_manual()
            if aviso["mostrar_modal"] and not confirmar_agora:
                return {
                    "ok": False,
                    "confirmar_agora": True,
                    **aviso,
                }
            if (
                aviso["mostrar_modal"]
                and confirmar_agora
                and (
                    timestamp_confirmado != aviso["ultimo_commit_timestamp"]
                    or proximo_timestamp_confirmado
                    != aviso["proximo_commit_timestamp"]
                )
            ):
                return {
                    "ok": False,
                    "confirmar_agora": True,
                    **aviso,
                }
            resposta = self._fazer_commit(
                repo_path, tipo, mensagem, evitar_repetidas, mensagens_banco
            )
            if resposta.get("ok") and mensagens_banco:
                ativacao = self._ativar_agendamento_apos_commit(
                    repo_path,
                    mensagens_banco,
                    resposta["mensagem_escolhida"],
                )
                resposta["automacao"] = ativacao
            return resposta

    def _ativar_agendamento_apos_commit(self, repo_path, mensagens, item):
        try:
            mensagens_distintas = {
                commit_message_selector.normalizar_mensagem(
                    commit_message_selector.montar_assunto(mensagem)
                )
                for mensagem in mensagens
            }
            if len(mensagens_distintas) < 2:
                return {
                    "ativado": False,
                    "mensagem": (
                        "O commit foi concluído. Para ativar a automação, "
                        "o banco precisa ter duas mensagens diferentes."
                    ),
                }
            caminho = str(repo_path or "").strip()
            dados = config.carregar_config()
            automatico = dados.get("agendamento_automatico", {})
            configuracoes = validar_configuracoes(automatico)
            automatico.update(configuracoes)
            automatico["repo_path"] = caminho
            automatico["banco_mensagens"] = mensagens
            dados["agendamento_automatico"] = automatico
            config.salvar_config(dados)
            head = self._obter_commit_atual(caminho)
            sucesso, mensagem = self._agendador.registrar_commit_manual(
                caminho,
                mensagens,
                f"{item['tipo']}: {item['mensagem']}",
                commit_oid=head["oid"] if head else None,
            )
            if not sucesso:
                return {"ativado": False, "mensagem": mensagem}
            return {"ativado": True, "mensagem": "Automação ativada após o commit manual."}
        except (OSError, TypeError, ValueError, KeyError):
            return {
                "ativado": False,
                "mensagem": (
                    "O commit foi concluído, mas não foi possível ativar a automação. "
                    "Confira as configurações e salve-as novamente."
                ),
            }

    def _fazer_commit(
        self,
        repo_path="",
        tipo="",
        mensagem="",
        evitar_repetidas=False,
        mensagens_banco=None,
    ):
        caminho = str(repo_path or "").strip()
        texto = str(mensagem or "").strip()
        candidato = None
        if evitar_repetidas:
            try:
                mensagens_log = commit_message_selector.ler_mensagens_commit(caminho)
                grupo = commit_message_selector.grupo_menos_repetidas(
                    mensagens_log, mensagens_banco or []
                )
            except commit_message_selector.CommitLogError as erro:
                return {
                    "ok": False,
                    "erro": str(erro),
                    "historico": self._historico[::-1],
                }
            esperado = f"{str(tipo).strip()}: {texto}".strip()
            esperado_normalizado = commit_message_selector.normalizar_mensagem(esperado)
            candidato = next(
                (
                    item
                    for item in grupo
                    if commit_message_selector.normalizar_mensagem(item["assunto"])
                    == esperado_normalizado
                ),
                None,
            )
            if candidato is None:
                sugestao = commit_message_selector.escolher_mensagem(
                    mensagens_log, mensagens_banco or []
                )
                if sugestao is None:
                    return {
                        "ok": False,
                        "erro": "O banco não contém mensagens válidas.",
                        "historico": self._historico[::-1],
                    }
                return {
                    "ok": False,
                    "reconfirmar": True,
                    "erro": "O histórico mudou. Confira a nova mensagem e confirme novamente.",
                    "mensagem_escolhida": {
                        "tipo": sugestao["tipo"],
                        "mensagem": sugestao["mensagem"],
                    },
                    "usos": sugestao["frequencia"],
                    "historico": self._historico[::-1],
                }
            tipo = candidato["tipo"]
            texto = candidato["mensagem"]

        try:
            sucesso, resultado = committer.executar_geracao_contribuicao(
                caminho, tipo, texto
            )
        except (OSError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError):
            sucesso = False
            resultado = "Não foi possível concluir a operação. Confira os dados e tente novamente."

        acao = {
            "data": datetime.now().strftime("%H:%M"),
            "repositorio": os.path.basename(os.path.normpath(caminho)) or caminho,
            "mensagem": texto,
            "usos_anteriores": candidato["frequencia"] if evitar_repetidas else None,
            "ok": sucesso,
            "resultado": resultado,
            "push": True,
        }
        self._historico.append(acao)
        self._historico = self._historico[-10:]

        if not sucesso:
            return {"ok": False, "erro": resultado, "historico": self._historico[::-1]}
        return {
            "ok": True,
            "mensagem": "Registro adicionado, commit criado e enviado ao GitHub.",
            "mensagem_escolhida": {"tipo": tipo, "mensagem": texto},
            "usos": candidato["frequencia"] if evitar_repetidas else None,
            "historico": self._historico[::-1],
        }
