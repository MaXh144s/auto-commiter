"""Agendamento diário de commits da interface atual."""

import datetime
import os
import random
import threading
import time

import commit_message_selector
import config
import scheduler_state


MAX_LOG_ENTRIES = 100
MAX_CONSECUTIVE_FAILURES = 3
NOMES_DIAS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


class SchedulerConfigError(ValueError):
    """Configuração inválida para o agendamento automático."""


def sortear_alvo_diario(minimo, maximo, rng=random):
    """Sorteia um alvo inclusivo entre os limites configurados."""
    return rng.randint(minimo, maximo)


def hoje_ativo(agora, dias_semana):
    """Informa se o dia da semana local está habilitado (segunda = 0)."""
    return agora.weekday() in dias_semana


def segundos_desde_ultimo_commit(ultimo_commit, agora=None):
    """Calcula o tempo desde um timestamp UTC, devolvendo None sem histórico."""
    if ultimo_commit is None:
        return None
    instante = time.time() if agora is None else float(agora)
    return max(0, int(instante - float(ultimo_commit)))


def formatar_duracao(segundos):
    if segundos is None or segundos < 60:
        return "agora há pouco"
    minutos = int(segundos) // 60
    horas, minutos = divmod(minutos, 60)
    dias, horas = divmod(horas, 24)
    partes = []
    if dias:
        partes.append(f"{dias} d")
    if horas:
        partes.append(f"{horas} h")
    if minutos:
        partes.append(f"{minutos} min")
    return " ".join(partes)


def deve_exibir_modal_commit(
    ultimo_commit, proximo_commit, agora, intervalo_minutos, proximidade_minutos=5
):
    """Evita que um commit manual coincida com o intervalo automático."""
    decorrido = segundos_desde_ultimo_commit(ultimo_commit, agora)
    intervalo = int(intervalo_minutos) * 60
    faltam = (
        float(proximo_commit) - float(agora)
        if proximo_commit is not None
        else None
    )
    dentro_do_intervalo = decorrido is not None and decorrido < intervalo
    perto_do_proximo = (
        faltam is not None and 0 <= faltam <= proximidade_minutos * 60
    )
    return dentro_do_intervalo or perto_do_proximo


def validar_configuracoes(dados):
    dias = dados.get("dias_semana")
    if (
        not isinstance(dias, list)
        or any(type(dia) is not int or dia not in range(7) for dia in dias)
        or len(set(dias)) != len(dias)
    ):
        raise SchedulerConfigError("Marque ao menos um dia da semana.")
    if not dias:
        raise SchedulerConfigError("Marque ao menos um dia da semana.")

    intervalo = _inteiro_positivo(dados.get("intervalo_minutos"), "intervalo")
    minimo = _inteiro_positivo(dados.get("commits_min_dia"), "mínimo")
    maximo = _inteiro_positivo(dados.get("commits_max_dia"), "máximo")
    if minimo > maximo:
        raise SchedulerConfigError(
            "A quantidade mínima não pode ser maior que a máxima."
        )
    return {
        "dias_semana": sorted(dias),
        "intervalo_minutos": intervalo,
        "commits_min_dia": minimo,
        "commits_max_dia": maximo,
    }


def restaurar_estado_diario(estado, hoje, repo_path=None):
    """Restaura contadores do mesmo dia ou reinicia o progresso após a virada."""
    if not isinstance(estado, dict):
        estado = {}
    data = hoje.isoformat()
    if estado.get("data") != data or (
        repo_path is not None and estado.get("repo_path") != repo_path
    ):
        restaurado = dict(estado)
        mudou_repositorio = (
            repo_path is not None and estado.get("repo_path") != repo_path
        )
        restaurado.update({
            "data": data,
            "alvo": None,
            "feitos": 0,
            "proximo_commit": None,
            "repo_path": repo_path or estado.get("repo_path"),
        })
        if mudou_repositorio:
            restaurado["ultimo_commit_oid"] = None
        return restaurado
    alvo = estado.get("alvo")
    feitos = estado.get("feitos", 0)
    proximo = estado.get("proximo_commit")
    try:
        if alvo is not None:
            alvo = int(alvo)
        feitos = int(feitos)
        if proximo is not None:
            proximo = float(proximo)
    except (TypeError, ValueError):
        alvo, feitos, proximo = None, 0, None
    if (alvo is not None and alvo < 1) or feitos < 0:
        alvo, feitos, proximo = None, 0, None
    return {
        **estado,
        "data": data,
        "alvo": alvo,
        "feitos": feitos,
        "ultima_mensagem": estado.get("ultima_mensagem"),
        "proximo_commit": proximo,
        "repo_path": estado.get("repo_path"),
    }


def _inteiro_positivo(valor, campo):
    try:
        convertido = int(valor)
    except (TypeError, ValueError) as erro:
        raise SchedulerConfigError(f"Informe um número inteiro válido para {campo}.") from erro
    if isinstance(valor, bool) or str(valor).strip() != str(convertido) or convertido <= 0:
        raise SchedulerConfigError(
            f"O campo {campo} precisa ser um número inteiro maior que zero."
        )
    return convertido


class AgendadorAutomatico:
    def __init__(self, executar_commit, caminho_estado=None):
        self._executar_commit = executar_commit
        self._caminho_estado = caminho_estado or os.path.join(
            config.PASTA_ESTADO, "agendamento-automatico.json"
        )
        self._lock = threading.RLock()
        self._parar = threading.Event()
        self._thread = None
        self._ativo = False
        self._pausado = False
        self._mensagem_estado = "Agendamento parado."
        self._configuracoes = {}
        self._repo_path = ""
        self._mensagens = []
        self._falhas_seguidas = 0
        self._logs = []
        self._erro_estado = ""
        self._estado = self._carregar_estado()
        self._erro_estado = self._erro_estado or str(self._estado.get("erro", ""))

    def _carregar_estado(self):
        try:
            estado = scheduler_state.carregar_estado(self._caminho_estado)
        except OSError as erro:
            self._erro_estado = str(erro)
            estado = {}
        self._falhas_seguidas = int(estado.get("falhas_seguidas", 0) or 0)
        self._pausado = bool(estado.get("pausado", False))
        return restaurar_estado_diario(estado, datetime.date.today())

    def _salvar_estado(self):
        self._estado["falhas_seguidas"] = self._falhas_seguidas
        self._estado["pausado"] = self._pausado
        if self._erro_estado:
            self._estado["erro"] = self._erro_estado
        else:
            self._estado.pop("erro", None)
        scheduler_state.salvar_estado_atomico(self._caminho_estado, self._estado)

    def iniciar(self, configuracoes, repo_path, mensagens, retomada=False):
        if self._thread and self._thread.is_alive():
            if self._pausado:
                return self.retomar()
            return False, "O agendamento já está ativo."
        try:
            validas = validar_configuracoes(configuracoes)
        except SchedulerConfigError as erro:
            return False, str(erro)
        if not repo_path or not mensagens:
            return False, "Escolha um repositório e um banco com mensagens válidas."
        assuntos = {
            commit_message_selector.normalizar_mensagem(
                commit_message_selector.montar_assunto(item)
            )
            for item in mensagens
        }
        if len(assuntos) < 2:
            return (
                False,
                "O banco precisa ter pelo menos duas mensagens diferentes para evitar repetições seguidas.",
            )

        with self._lock:
            self._configuracoes = validas
            self._repo_path = repo_path
            self._mensagens = list(mensagens)
            self._estado = restaurar_estado_diario(
                self._estado, datetime.date.today(), repo_path
            )
            self._estado["ativado"] = True
            self._pausado = False
            self._falhas_seguidas = 0
            self._erro_estado = ""
            self._parar.clear()
            self._ativo = True
            self._mensagem_estado = (
                "Agendamento retomado." if retomada else "Agendamento ativo."
            )
            self._salvar_estado()
            self._thread = threading.Thread(
                target=self._loop,
                name="auto-committer-agendamento",
                daemon=True,
            )
            self._thread.start()
        self._adicionar_log(
            "Agendamento retomado." if retomada else "Agendamento iniciado."
        )
        return True, "Agendamento iniciado."

    def parar(self, aguardar=False):
        with self._lock:
            thread = self._thread
            if not self._ativo:
                return
            self._parar.set()
            self._mensagem_estado = "Parando após a operação em andamento…"
        self._adicionar_log("Parada solicitada; aguardando a operação atual.")
        if aguardar and thread and thread is not threading.current_thread():
            thread.join()

    def pausar(self):
        with self._lock:
            if not self._estado.get("ativado"):
                return False, "A automação será ativada após o primeiro commit manual."
            self._pausado = True
            self._estado["pausado"] = True
            self._mensagem_estado = "Agendamento pausado."
            self._salvar_estado()
        self._adicionar_log("Agendamento pausado.")
        return True, "Agendamento pausado."

    def pausar_por_erro(self, mensagem):
        with self._lock:
            self._estado["ativado"] = True
            self._pausado = True
            self._estado["pausado"] = True
            self._erro_estado = str(mensagem)
            self._mensagem_estado = str(mensagem)
            self._parar.set()
            self._salvar_estado()
        self._adicionar_log(str(mensagem), "error")

    def retomar(self):
        thread_para_aguardar = None
        with self._lock:
            if not self._estado.get("ativado"):
                return False, "A automação será ativada após o primeiro commit manual."
            if self._thread and self._thread.is_alive():
                if not self._parar.is_set():
                    self._pausado = False
                    self._estado["pausado"] = False
                    self._falhas_seguidas = 0
                    self._erro_estado = ""
                    self._mensagem_estado = "Agendamento retomado."
                    self._salvar_estado()
                    return True, "Agendamento retomado."
                thread_para_aguardar = self._thread
        if thread_para_aguardar:
            thread_para_aguardar.join()
        with self._lock:
            configuracoes = dict(self._configuracoes)
            repo_path = self._estado.get("repo_path") or self._repo_path
            mensagens = list(self._mensagens)
            self._pausado = False
            self._falhas_seguidas = 0
            self._erro_estado = ""
            self._estado["pausado"] = False
        return self.iniciar(configuracoes, repo_path, mensagens, retomada=True)

    def registrar_commit_manual(
        self, repo_path, mensagens, assunto, timestamp=None, commit_oid=None
    ):
        instante = time.time() if timestamp is None else float(timestamp)
        with self._lock:
            estava_ativado = bool(self._estado.get("ativado"))
            estava_pausado = self._pausado
            dados_config = self._configuracoes
            if not dados_config:
                dados_config = validar_configuracoes(
                    config.carregar_config()["agendamento_automatico"]
                )
                self._configuracoes = dados_config
            self._repo_path = repo_path
            self._mensagens = list(mensagens or [])
            self._estado = restaurar_estado_diario(
                self._estado, datetime.datetime.now().astimezone().date(), repo_path
            )
            dia_ativo = hoje_ativo(
                datetime.datetime.fromtimestamp(instante).astimezone(),
                dados_config["dias_semana"],
            )
            if dia_ativo and self._estado.get("alvo") is None:
                self._estado["alvo"] = sortear_alvo_diario(
                    dados_config["commits_min_dia"], dados_config["commits_max_dia"]
                )
            self._estado["ativado"] = True
            self._estado["ultimo_commit_timestamp"] = instante
            self._estado["ultimo_commit_local"] = datetime.datetime.fromtimestamp(
                instante
            ).astimezone().isoformat(timespec="seconds")
            self._estado["ultima_mensagem"] = assunto
            self._estado["repo_path"] = repo_path
            if commit_oid:
                self._estado["ultimo_commit_oid"] = commit_oid
            if dia_ativo:
                self._estado["feitos"] = int(self._estado.get("feitos", 0)) + 1
            self._estado["proximo_commit"] = (
                instante + dados_config["intervalo_minutos"] * 60
                if dia_ativo
                and self._estado.get("alvo") is not None
                and self._estado["feitos"] < self._estado["alvo"]
                else None
            )
            estava_pausado = self._pausado
            self._pausado = estava_pausado if estava_ativado else False
            self._estado["pausado"] = self._pausado
            self._salvar_estado()
        if self._thread and self._thread.is_alive():
            return True, "O commit manual foi registrado no progresso diário."
        if self._pausado:
            return True, "O commit foi registrado; a automação continua pausada."
        return self.iniciar(dados_config, repo_path, mensagens, retomada=True)

    def sincronizar_head(self, repo_path, oid, timestamp, assunto):
        if not oid:
            return False
        instante = float(timestamp)
        with self._lock:
            if self._estado.get("repo_path") != repo_path:
                self._estado["ultimo_commit_oid"] = oid
                self._estado["repo_path"] = repo_path
                self._salvar_estado()
                return False
            anterior = self._estado.get("ultimo_commit_oid")
            if anterior is None:
                self._estado["ultimo_commit_oid"] = oid
                self._salvar_estado()
                return False
            if anterior == oid:
                return False

            agora_local = datetime.datetime.fromtimestamp(instante).astimezone()
            self._estado = restaurar_estado_diario(
                self._estado, agora_local.date(), repo_path
            )
            self._estado["ultimo_commit_oid"] = oid
            self._estado["ultimo_commit_timestamp"] = instante
            self._estado["ultimo_commit_local"] = agora_local.isoformat(
                timespec="seconds"
            )
            self._estado["ultima_mensagem"] = assunto
            if self._configuracoes and hoje_ativo(
                agora_local, self._configuracoes["dias_semana"]
            ):
                if self._estado.get("alvo") is None:
                    self._estado["alvo"] = sortear_alvo_diario(
                        self._configuracoes["commits_min_dia"],
                        self._configuracoes["commits_max_dia"],
                    )
                self._estado["feitos"] = int(self._estado.get("feitos", 0)) + 1
                self._estado["proximo_commit"] = (
                    instante + self._configuracoes["intervalo_minutos"] * 60
                    if self._estado["feitos"] < self._estado["alvo"]
                    else None
                )
            self._salvar_estado()
            self._adicionar_log(
                "Um commit recente foi reconhecido no repositório e contabilizado."
            )
            return True

    def atualizar_configuracoes(self, configuracoes, repo_path, mensagens):
        validas = validar_configuracoes(configuracoes)
        with self._lock:
            self._configuracoes = validas
            self._repo_path = repo_path
            self._mensagens = list(mensagens or [])
            self._estado["repo_path"] = repo_path
            self._estado = restaurar_estado_diario(
                self._estado, datetime.datetime.now().astimezone().date(), repo_path
            )
            ultimo = self._estado.get("ultimo_commit_timestamp")
            self._estado["proximo_commit"] = (
                float(ultimo) + validas["intervalo_minutos"] * 60
                if ultimo is not None
                and self._estado.get("alvo") is not None
                and self._estado.get("feitos", 0) < self._estado["alvo"]
                else None
            )
            self._salvar_estado()

    def prever_commit_manual(self):
        with self._lock:
            try:
                salvo = scheduler_state.carregar_estado(self._caminho_estado)
            except OSError as erro:
                self._erro_estado = str(erro)
                return {
                    "mostrar_modal": False,
                    "erro": self._erro_estado,
                }
            if salvo:
                self._estado = restaurar_estado_diario(
                    salvo, datetime.datetime.now().astimezone().date()
                )
                self._pausado = bool(self._estado.get("pausado", self._pausado))
            agora = time.time()
            ultimo = self._estado.get("ultimo_commit_timestamp")
            proximo = self._estado.get("proximo_commit")
            intervalo = self._configuracoes.get("intervalo_minutos", 60)
            agora_local = datetime.datetime.now().astimezone()
            if proximo is None and self._estado.get("ativado"):
                if (
                    self._estado.get("alvo") is not None
                    and self._estado.get("feitos", 0) >= self._estado["alvo"]
                ):
                    proxima_data = self._proximo_dia_ativo(
                        agora_local, self._configuracoes.get("dias_semana", [])
                    )
                    proximo = self._inicio_do_dia(proxima_data)
                elif ultimo is not None:
                    proximo = float(ultimo) + intervalo * 60
            mostrar = bool(self._estado.get("ativado")) and deve_exibir_modal_commit(
                ultimo, proximo, agora, intervalo
            )
            desde = segundos_desde_ultimo_commit(ultimo, agora)
            falta = max(0, int(float(proximo) - agora)) if proximo else 0
            return {
                "mostrar_modal": mostrar,
                "tempo_desde": formatar_duracao(desde),
                "tempo_ate": formatar_duracao(falta),
                "ultimo_commit_timestamp": ultimo,
                "proximo_commit_timestamp": proximo,
            }

    def eh_thread_de_execucao(self):
        return threading.current_thread() is self._thread

    def pode_executar_agora(self, timestamp=None):
        instante = time.time() if timestamp is None else float(timestamp)
        agora_local = datetime.datetime.fromtimestamp(instante).astimezone()
        with self._lock:
            self._estado = restaurar_estado_diario(
                self._estado, agora_local.date()
            )
            return (
                self._ativo
                and not self._pausado
                and not self._parar.is_set()
                and hoje_ativo(agora_local, self._configuracoes["dias_semana"])
                and self._estado.get("alvo") is not None
                and self._estado.get("feitos", 0) < self._estado["alvo"]
                and (
                    self._estado.get("proximo_commit") is None
                    or instante >= float(self._estado["proximo_commit"])
                )
            )

    def estado(self):
        with self._lock:
            agora = time.time()
            proximo = self._estado.get("proximo_commit")
            segundos = (
                max(0, int(float(proximo) - agora))
                if proximo is not None and self._ativo and not self._pausado
                else None
            )
            return {
                "ativo": self._ativo,
                "ativado": bool(self._estado.get("ativado")),
                "pausado": self._pausado,
                "mensagem": self._erro_estado or self._mensagem_estado,
                "data": self._estado["data"],
                "alvo": self._estado.get("alvo"),
                "feitos": self._estado.get("feitos", 0),
                "proximo_em_segundos": segundos,
                "ultimo_commit_timestamp": self._estado.get("ultimo_commit_timestamp"),
                "ultimo_commit": self._estado.get("ultimo_commit_local"),
                "ativacao_automatica": bool(self._estado.get("ativado")),
                "falhas_seguidas": self._falhas_seguidas,
                "erro": self._erro_estado or (
                    self._mensagem_estado if self._falhas_seguidas >= MAX_CONSECUTIVE_FAILURES else ""
                ),
                "logs": list(self._logs),
            }

    def _adicionar_log(self, texto, nivel="info"):
        entrada = {
            "horario": datetime.datetime.now().strftime("%H:%M:%S"),
            "texto": texto,
            "nivel": nivel,
        }
        with self._lock:
            self._logs.append(entrada)
            self._logs = self._logs[-MAX_LOG_ENTRIES:]

    def _loop(self):
        try:
            while not self._parar.is_set():
                agora = datetime.datetime.now().astimezone()
                with self._lock:
                    self._estado = restaurar_estado_diario(
                        self._estado, agora.date()
                    )
                    pausado = self._pausado
                    dias = self._configuracoes["dias_semana"]
                    alvo = self._estado.get("alvo")
                    feitos = self._estado.get("feitos", 0)
                    if pausado:
                        self._mensagem_estado = "Agendamento pausado."
                if pausado:
                    self._aguardar(1)
                    continue

                if not hoje_ativo(agora, dias):
                    proximo = self._proximo_dia_ativo(agora, dias)
                    with self._lock:
                        self._estado["proximo_commit"] = self._inicio_do_dia(proximo)
                        self._salvar_estado()
                        self._mensagem_estado = (
                            f"Aguardando o próximo dia ativo: "
                            f"{NOMES_DIAS[proximo.weekday()]}, {proximo:%d/%m}."
                        )
                    self._aguardar(30)
                    continue

                if alvo is None:
                    alvo = sortear_alvo_diario(
                        self._configuracoes["commits_min_dia"],
                        self._configuracoes["commits_max_dia"],
                    )
                    with self._lock:
                        self._estado["alvo"] = alvo
                        ultimo = self._estado.get("ultimo_commit_timestamp")
                        proximo_por_intervalo = (
                            float(ultimo)
                            + self._configuracoes["intervalo_minutos"] * 60
                            if ultimo is not None
                            else None
                        )
                        if proximo_por_intervalo and proximo_por_intervalo > time.time():
                            self._estado["proximo_commit"] = proximo_por_intervalo
                        self._salvar_estado()
                    self._adicionar_log(f"Alvo de hoje: {alvo} commits.")

                if feitos >= alvo:
                    proximo = self._proximo_dia_ativo(agora, dias)
                    with self._lock:
                        self._estado["proximo_commit"] = self._inicio_do_dia(proximo)
                        self._salvar_estado()
                        self._mensagem_estado = (
                            f"Meta diária concluída. Próximo dia ativo: "
                            f"{NOMES_DIAS[proximo.weekday()]}, {proximo:%d/%m}."
                        )
                    self._aguardar(30)
                    continue

                proximo_commit = self._estado.get("proximo_commit")
                if proximo_commit is not None and time.time() < float(proximo_commit):
                    with self._lock:
                        self._mensagem_estado = "Aguardando o próximo commit."
                    self._aguardar(min(1, float(proximo_commit) - time.time()))
                    continue

                self._executar_um_commit()
        except Exception:
            self._adicionar_log(
                "O agendamento foi interrompido por uma falha ao salvar ou atualizar o progresso.",
                "error",
            )
            with self._lock:
                self._mensagem_estado = (
                    "Agendamento pausado por uma falha interna. "
                    "Confira o registro de atividade."
                )
                self._erro_estado = self._mensagem_estado
                self._pausado = True
                self._estado["pausado"] = True
                self._salvar_estado()
        finally:
            with self._lock:
                self._ativo = False
                self._thread = None
                if self._parar.is_set():
                    if self._mensagem_estado.startswith("Parando"):
                        self._mensagem_estado = "Agendamento parado."

    def _executar_um_commit(self):
        with self._lock:
            agora = time.time()
            hoje = datetime.datetime.now().astimezone().date()
            self._estado = restaurar_estado_diario(self._estado, hoje)
            if (
                self._parar.is_set()
                or self._pausado
                or not hoje_ativo(datetime.datetime.now().astimezone(), self._configuracoes["dias_semana"])
                or self._estado.get("alvo") is None
                or self._estado.get("feitos", 0) >= self._estado["alvo"]
                or (
                    self._estado.get("proximo_commit") is not None
                    and agora < float(self._estado["proximo_commit"])
                )
            ):
                return
            repo_path = self._repo_path
            mensagens = list(self._mensagens)
            ultima_mensagem = self._estado.get("ultima_mensagem")
        try:
            resultado = self._executar_commit(
                repo_path, mensagens, ultima_mensagem
            )
        except Exception as erro:
            resultado = {"ok": False, "erro": str(erro)}

        if not resultado.get("ok"):
            if resultado.get("adiado"):
                self._adicionar_log(
                    resultado.get(
                        "erro",
                        "Commit adiado para respeitar o intervalo configurado.",
                    )
                )
                return
            with self._lock:
                self._falhas_seguidas += 1
                falhas = self._falhas_seguidas
                limite = self._configuracoes["intervalo_minutos"] * 60
                self._estado["proximo_commit"] = time.time() + limite
                self._salvar_estado()
                if falhas >= MAX_CONSECUTIVE_FAILURES:
                    self._parar.set()
                    self._pausado = True
                    self._estado["pausado"] = True
                    self._estado["ativado"] = True
                    self._mensagem_estado = (
                        "Agendamento parado após 3 falhas seguidas."
                    )
                    self._erro_estado = self._mensagem_estado
            self._adicionar_log(
                f"Falha {falhas}/3: {resultado.get('erro', 'Commit não concluído.')}",
                "error",
            )
            if falhas >= MAX_CONSECUTIVE_FAILURES:
                self._adicionar_log(
                    "Agendamento parado após 3 falhas consecutivas.", "error"
                )
            return

        item = resultado["mensagem_escolhida"]
        assunto = f"{item['tipo']}: {item['mensagem']}"
        with self._lock:
            self._falhas_seguidas = 0
            self._erro_estado = ""
            self._estado["feitos"] += 1
            self._estado["ultima_mensagem"] = assunto
            if resultado.get("commit_oid"):
                self._estado["ultimo_commit_oid"] = resultado["commit_oid"]
            instante = time.time()
            self._estado["ultimo_commit_timestamp"] = instante
            self._estado["ultimo_commit_local"] = datetime.datetime.fromtimestamp(
                instante
            ).astimezone().isoformat(timespec="seconds")
            feitos = self._estado["feitos"]
            alvo = self._estado["alvo"]
            self._estado["proximo_commit"] = (
                time.time() + self._configuracoes["intervalo_minutos"] * 60
                if feitos < alvo
                else None
            )
            self._salvar_estado()
            self._mensagem_estado = (
                "Meta diária concluída."
                if feitos >= alvo
                else "Aguardando o próximo commit."
            )
        self._adicionar_log(f"Commit {feitos} de {alvo}: {assunto}.")

    def _aguardar(self, segundos):
        self._parar.wait(max(0.1, segundos))

    @staticmethod
    def _proximo_dia_ativo(agora, dias):
        for deslocamento in range(1, 8):
            data = (agora + datetime.timedelta(days=deslocamento)).date()
            if data.weekday() in dias:
                return data
        return agora.date()

    @staticmethod
    def _inicio_do_dia(data):
        return datetime.datetime.combine(
            data, datetime.time.min
        ).astimezone().timestamp()
