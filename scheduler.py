"""
scheduler.py
Roda em background (thread) e decide QUANDO cada trabalho deve commitar,
usando um algoritmo anti-spam:

- Gera a "agenda do dia" uma vez por dia, por trabalho.
- Quantidade de commits no dia é aleatória entre commits_min_dia e commits_max_dia.
- Chance de pular o dia inteiro (chance_pular_dia).
- Só gera horários dentro da janela [hora_inicio, hora_fim].
- Garante intervalo mínimo (intervalo_min_minutos) entre commits do mesmo dia.
- Só roda em dias da semana configurados (dias_semana).
"""

import datetime
import random
import threading
import time

import committer
import config


class Agendador:
    def __init__(self, callback_log=None):
        self._callback_log = callback_log or (lambda texto: None)
        self._parar = threading.Event()
        self._pausado = threading.Event()
        self._thread = None

    def log(self, texto):
        agora = datetime.datetime.now().strftime("%H:%M:%S")
        self._callback_log(f"[{agora}] {texto}")

    # ---------- controle da thread ----------

    def iniciar(self):
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log("Agendador iniciado.")

    def pausar(self):
        self._pausado.set()
        self.log("Agendador pausado.")

    def retomar(self):
        self._pausado.clear()
        self.log("Agendador retomado.")

    def esta_pausado(self):
        return self._pausado.is_set()

    def parar(self):
        self._parar.set()
        self.log("Agendador parado.")

    # ---------- lógica principal ----------

    def _loop(self):
        while not self._parar.is_set():
            if not self._pausado.is_set():
                try:
                    self._verificar_todos_jobs()
                except Exception as exc:
                    self.log(f"Erro no ciclo do agendador: {exc}")

            intervalo = config.carregar_config()["geral"].get("intervalo_verificacao_segundos", 30)
            self._parar.wait(intervalo)

    def _verificar_todos_jobs(self):
        cfg = config.carregar_config()
        agora = datetime.datetime.now()
        hoje_str = agora.strftime("%Y-%m-%d")

        for job in cfg.get("jobs", []):
            if not job.get("ativo", True):
                continue

            estado = config.carregar_estado_job(job["id"])

            if estado.get("data_agenda") != hoje_str:
                nova_agenda = self._gerar_agenda_do_dia(job, agora)
                estado["data_agenda"] = hoje_str
                estado["agenda_hoje"] = [h.strftime("%H:%M:%S") for h in nova_agenda]
                estado["executados_hoje"] = []
                estado["avisados_intervalo_hoje"] = []
                config.salvar_estado_job(job["id"], estado)
                if nova_agenda:
                    horarios = ", ".join(h.strftime("%H:%M") for h in nova_agenda)
                    self.log(f"[{job['nome']}] Agenda de hoje: {horarios}")
                else:
                    self.log(f"[{job['nome']}] Hoje não haverá commits (dia pulado ou fora da semana ativa).")

            self._executar_pendentes(job, estado, agora)
            self._verificar_execucao_manual_pendente(job)

    def _gerar_agenda_do_dia(self, job, agora):
        dia_semana = agora.weekday()  # 0=segunda
        if dia_semana not in job.get("dias_semana", list(range(7))):
            return []

        if random.random() < float(job.get("chance_pular_dia", 0)):
            return []

        # corrige intervalo mínimo <= 0 e garante que commits_min_dia/
        # commits_max_dia cabem de forma realista na janela de horário
        # configurada — se o job já tiver valores válidos, nada muda aqui.
        job, avisos = config.validar_job(job)
        for aviso in avisos:
            self.log(f"[{job['nome']}] {aviso}")

        minimo = max(0, int(job.get("commits_min_dia", 1)))
        maximo = max(minimo, int(job.get("commits_max_dia", 1)))
        quantidade = random.randint(minimo, maximo)
        if quantidade == 0:
            return []

        try:
            h_ini, m_ini = map(int, job.get("hora_inicio", "08:00").split(":"))
            h_fim, m_fim = map(int, job.get("hora_fim", "22:00").split(":"))
        except ValueError:
            h_ini, m_ini, h_fim, m_fim = 8, 0, 22, 0

        inicio_janela = agora.replace(hour=h_ini, minute=m_ini, second=0, microsecond=0)
        fim_janela = agora.replace(hour=h_fim, minute=m_fim, second=0, microsecond=0)
        if fim_janela <= inicio_janela:
            fim_janela = inicio_janela + datetime.timedelta(hours=1)

        intervalo_min = datetime.timedelta(minutes=int(job.get("intervalo_min_minutos", 30)))
        duracao_total = fim_janela - inicio_janela

        tentativas = 0
        horarios = []
        while len(horarios) < quantidade and tentativas < quantidade * 40:
            tentativas += 1
            segundos_aleatorios = random.uniform(0, duracao_total.total_seconds())
            candidato = inicio_janela + datetime.timedelta(seconds=segundos_aleatorios)

            # já passou da hora atual? ainda inclui, só não executa retroativo (tratado na execução)
            muito_perto = any(abs((candidato - h).total_seconds()) < intervalo_min.total_seconds() for h in horarios)
            if not muito_perto:
                horarios.append(candidato)

        return sorted(horarios)

    def _executar_pendentes(self, job, estado, agora):
        """Dispara os horários da agenda de hoje que já chegaram.

        Antes de disparar um horário atrasado (ex: o PC ficou desligado e
        passou da hora agendada), checa o intervalo mínimo desde o ÚLTIMO
        commit REAL do repositório (git log) — a mesma regra usada no
        'Rodar agora'. Isso vale tanto pra quando o agendador é iniciado
        pelo sistema (--silencioso no boot) quanto manualmente: ele nunca
        comita na hora só porque acabou de ligar; espera o intervalo desde
        o último commit real passar, senão viraria uma rajada de commits
        atrasados assim que o PC liga — o oposto do anti-spam."""
        agenda = [datetime.datetime.strptime(f"{agora.strftime('%Y-%m-%d')} {h}", "%Y-%m-%d %H:%M:%S")
                  for h in estado.get("agenda_hoje", [])]
        executados = set(estado.get("executados_hoje", []))
        avisados = set(estado.get("avisados_intervalo_hoje", []))

        houve_execucao = False
        houve_aviso_novo = False
        for horario in agenda:
            chave = horario.strftime("%H:%M:%S")
            if chave in executados:
                continue
            if agora >= horario:
                pode_rodar, _ = self.verificar_intervalo_minimo(job)
                if not pode_rodar:
                    # não marca como executado — tenta de novo no próximo
                    # ciclo do agendador, sem spammar o log a cada ciclo
                    if chave not in avisados:
                        self.log(f"[{job['nome']}] Horário {chave} já chegou, mas aguardando "
                                  f"o intervalo mínimo desde o último commit real antes de rodar.")
                        avisados.add(chave)
                        houve_aviso_novo = True
                    continue

                self.log(f"[{job['nome']}] Executando commit agendado para {chave}...")
                sucesso, saida = committer.executar_commit(job)
                status = "OK" if sucesso else "FALHOU"
                self.log(f"[{job['nome']}] Resultado ({status}): {saida}")
                executados.add(chave)
                houve_execucao = True

        if houve_execucao:
            estado["executados_hoje"] = sorted(executados)
        if houve_aviso_novo:
            estado["avisados_intervalo_hoje"] = sorted(avisados)
        if houve_execucao or houve_aviso_novo:
            config.salvar_estado_job(job["id"], estado)

    def verificar_intervalo_minimo(self, job):
        """Consulta o git log REAL do repositório (fonte de verdade, funciona
        até com commits feitos antes dessa checagem existir) e verifica se
        já passou tempo suficiente desde o último commit, respeitando o
        intervalo mínimo configurado.

        Retorna (pode_rodar: bool, mensagem: str | None). Se pode_rodar for
        False, 'mensagem' explica há quanto tempo foi o último commit."""
        ultimo = committer.obter_data_ultimo_commit(job.get("repo_path"))
        if ultimo is None:
            return True, None

        agora = datetime.datetime.now().astimezone()  # aware, no fuso horário local
        intervalo_min = datetime.timedelta(minutes=int(job.get("intervalo_min_minutos", 30)))
        decorrido = agora - ultimo

        if decorrido >= intervalo_min:
            return True, None

        faltam_minutos = int((intervalo_min - decorrido).total_seconds() // 60) + 1
        decorrido_minutos = int(decorrido.total_seconds() // 60)
        mensagem = (
            f"O último commit deste trabalho foi há {decorrido_minutos} min "
            f"(em {ultimo.strftime('%d/%m %H:%M')}).\n"
            f"O intervalo mínimo configurado é de {job.get('intervalo_min_minutos', 30)} min "
            f"— faltam ~{faltam_minutos} min."
        )
        return False, mensagem

    def agendar_para_depois(self, job):
        """Usado quando o usuário escolhe 'Commitar depois' no diálogo do
        'Rodar agora': marca o trabalho como pendente. O próprio loop em
        background (_verificar_execucao_manual_pendente) dispara o commit
        automaticamente assim que o intervalo mínimo configurado passar —
        não precisa o usuário voltar e clicar de novo."""
        config.marcar_execucao_pendente(job["id"], True)
        self.log(f"[{job['nome']}] Commit agendado — será feito automaticamente "
                  f"assim que o intervalo mínimo for atingido.")

    def _verificar_execucao_manual_pendente(self, job):
        if not config.esta_execucao_pendente(job["id"]):
            return

        pode_rodar, _ = self.verificar_intervalo_minimo(job)
        if not pode_rodar:
            return

        self.log(f"[{job['nome']}] Intervalo mínimo atingido — executando commit pendente...")
        sucesso, saida = committer.executar_commit(job)
        status = "OK" if sucesso else "FALHOU"
        self.log(f"[{job['nome']}] Resultado ({status}): {saida}")
        config.marcar_execucao_pendente(job["id"], False)

    def executar_agora(self, job):
        """Dispara um commit imediato, ignorando a agenda (botão 'Rodar agora')."""
        self.log(f"[{job['nome']}] Execução manual solicitada...")
        sucesso, saida = committer.executar_commit(job)
        status = "OK" if sucesso else "FALHOU"
        self.log(f"[{job['nome']}] Resultado ({status}): {saida}")
        # se havia um 'commitar depois' pendente e o usuário forçou agora,
        # cancela o pendente pra não commitar de novo automaticamente
        config.marcar_execucao_pendente(job["id"], False)
        return sucesso, saida