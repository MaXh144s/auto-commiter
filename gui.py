"""
gui.py
Janela de configuração. Só é exibida quando o usuário abre o executável
manualmente ou clica em "Abrir configurações" no ícone da bandeja.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import config


DIAS_SEMANA_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


class DialogoEscolhaExecucao(tk.Toplevel):
    """Diálogo com 3 opções, usado quando o intervalo mínimo entre commits
    ainda não passou: commitar agora mesmo (força), commitar depois
    (agenda pro agendador disparar sozinho quando o intervalo for atingido)
    ou cancelar (não faz nada)."""

    def __init__(self, master, mensagem):
        super().__init__(master)
        self.title("Intervalo mínimo recente")
        self.resizable(False, False)
        self.resultado = "cancelar"

        ttk.Label(self, text=mensagem, wraplength=380, justify="left").pack(
            padx=16, pady=(16, 12))

        botoes = ttk.Frame(self)
        botoes.pack(padx=16, pady=(0, 16), fill="x")

        ttk.Button(botoes, text="Commitar agora",
                   command=self._commitar_agora).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(botoes, text="Commitar depois",
                   command=self._commitar_depois).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(botoes, text="Cancelar",
                   command=self._cancelar).pack(side="left", expand=True, fill="x", padx=2)

        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancelar)

    def _commitar_agora(self):
        self.resultado = "agora"
        self.destroy()

    def _commitar_depois(self):
        self.resultado = "depois"
        self.destroy()

    def _cancelar(self):
        self.resultado = "cancelar"
        self.destroy()


class JanelaPrincipal(tk.Toplevel):
    def __init__(self, master, agendador):
        super().__init__(master)
        self.agendador = agendador
        self.title("Auto Committer — Configurações")
        self.geometry("780x520")
        self.minsize(680, 460)

        self.cfg = config.carregar_config()

        self._montar_layout()
        self._atualizar_logs_periodicamente()

        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ---------------- layout ----------------

    def _montar_layout(self):
        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=8, pady=8)

        self.aba_jobs = ttk.Frame(abas)
        self.aba_geral = ttk.Frame(abas)
        self.aba_logs = ttk.Frame(abas)

        abas.add(self.aba_jobs, text="Trabalhos")
        abas.add(self.aba_geral, text="Configurações gerais")
        abas.add(self.aba_logs, text="Logs")

        self._montar_aba_jobs()
        self._montar_aba_geral()
        self._montar_aba_logs()

    def _montar_aba_jobs(self):
        painel_esquerda = ttk.Frame(self.aba_jobs)
        painel_esquerda.pack(side="left", fill="y", padx=(0, 8), pady=8)

        ttk.Label(painel_esquerda, text="Trabalhos configurados:").pack(anchor="w")
        self.lista_jobs = tk.Listbox(painel_esquerda, width=28, height=18)
        self.lista_jobs.pack(fill="y", expand=True, pady=4)
        self.lista_jobs.bind("<<ListboxSelect>>", self._ao_selecionar_job)

        botoes = ttk.Frame(painel_esquerda)
        botoes.pack(fill="x", pady=4)
        ttk.Button(botoes, text="+ Novo", command=self._novo_job).pack(side="left", expand=True, fill="x")
        ttk.Button(botoes, text="Remover", command=self._remover_job).pack(side="left", expand=True, fill="x")

        ttk.Button(painel_esquerda, text="▶ Rodar agora", command=self._rodar_agora).pack(fill="x", pady=(8, 0))

        self.painel_direita = ttk.Frame(self.aba_jobs)
        self.painel_direita.pack(side="left", fill="both", expand=True, pady=8)

        self._construir_formulario_job()
        self._recarregar_lista_jobs()

    def _construir_formulario_job(self):
        f = self.painel_direita
        for widget in f.winfo_children():
            widget.destroy()

        self.var_nome = tk.StringVar()
        self.var_ativo = tk.BooleanVar(value=True)
        self.var_repo = tk.StringVar()
        self.var_arquivo = tk.StringVar()
        self.var_modo = tk.StringVar(value="mensagens")
        self.var_comando_custom = tk.StringVar()
        self.var_prefixo = tk.StringVar(value="chore: ")
        self.var_banco_arquivo = tk.StringVar()
        self.var_sequencial = tk.BooleanVar(value=True)
        self.var_hora_inicio = tk.StringVar(value="08:00")
        self.var_hora_fim = tk.StringVar(value="22:00")
        self.var_min_dia = tk.StringVar(value="1")
        self.var_max_dia = tk.StringVar(value="3")
        self.var_intervalo_min = tk.StringVar(value="45")
        self.var_chance_pular = tk.StringVar(value="15")
        self.var_push = tk.BooleanVar(value=True)
        self.vars_dias = [tk.BooleanVar(value=True) for _ in range(7)]

        linha = 0
        ttk.Label(f, text="Nome do trabalho").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_nome, width=40).grid(row=linha, column=1, columnspan=3, sticky="we")
        ttk.Checkbutton(f, text="Ativo", variable=self.var_ativo).grid(row=linha, column=4, sticky="w")
        linha += 1

        ttk.Label(f, text="Pasta do repositório git").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_repo, width=40).grid(row=linha, column=1, columnspan=3, sticky="we")
        ttk.Button(f, text="Procurar...", command=self._escolher_repo).grid(row=linha, column=4)
        linha += 1

        ttk.Label(f, text="Arquivo alvo (relativo ao repo)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_arquivo, width=40).grid(row=linha, column=1, columnspan=3, sticky="we")
        linha += 1

        ttk.Label(f, text="O que commitar").grid(row=linha, column=0, sticky="w")
        combo_modo = ttk.Combobox(f, textvariable=self.var_modo, state="readonly",
                                   values=["mensagens", "linha_data", "comando_custom"])
        combo_modo.grid(row=linha, column=1, sticky="w")
        linha += 1

        ttk.Label(f, text="Comando customizado (opcional)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_comando_custom, width=40).grid(row=linha, column=1, columnspan=3, sticky="we")
        linha += 1

        ttk.Label(f, text="Prefixo (fallback p/ 'linha_data' / comando customizado)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_prefixo, width=20).grid(row=linha, column=1, sticky="w")
        linha += 1

        ttk.Label(f, text="Banco de mensagens (.txt/.csv)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_banco_arquivo, width=40).grid(row=linha, column=1, columnspan=3, sticky="we")
        ttk.Button(f, text="Importar...", command=self._importar_banco).grid(row=linha, column=4)
        linha += 1

        ttk.Checkbutton(f, text="Usar mensagens em ordem (sem repetir até esgotar)",
                         variable=self.var_sequencial).grid(row=linha, column=0, columnspan=3, sticky="w")
        linha += 1

        ttk.Label(f, text="Tipos de commit usados no sorteio").grid(row=linha, column=0, sticky="nw")
        frame_tipos = ttk.Frame(f)
        frame_tipos.grid(row=linha, column=1, columnspan=4, sticky="w")
        self.vars_tipos_commit = {}
        for i, tipo in enumerate(config.TIPOS_COMMIT_VALIDOS):
            var_tipo = tk.BooleanVar(value=True)
            self.vars_tipos_commit[tipo] = var_tipo
            ttk.Checkbutton(
                frame_tipos, text=config.TIPOS_COMMIT_LABELS[tipo], variable=var_tipo
            ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12))
        linha += 1

        ttk.Separator(f).grid(row=linha, column=0, columnspan=5, sticky="we", pady=6)
        linha += 1

        ttk.Label(f, text="Dias da semana ativos").grid(row=linha, column=0, sticky="w")
        frame_dias = ttk.Frame(f)
        frame_dias.grid(row=linha, column=1, columnspan=4, sticky="w")
        for i, label in enumerate(DIAS_SEMANA_LABELS):
            ttk.Checkbutton(frame_dias, text=label, variable=self.vars_dias[i]).pack(side="left")
        linha += 1

        ttk.Label(f, text="Janela de horário (início / fim)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_hora_inicio, width=8).grid(row=linha, column=1, sticky="w")
        ttk.Entry(f, textvariable=self.var_hora_fim, width=8).grid(row=linha, column=2, sticky="w")
        linha += 1

        ttk.Label(f, text="Commits por dia (mín / máx)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_min_dia, width=8).grid(row=linha, column=1, sticky="w")
        ttk.Entry(f, textvariable=self.var_max_dia, width=8).grid(row=linha, column=2, sticky="w")
        linha += 1

        ttk.Label(f, text="Intervalo mínimo entre commits (min)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_intervalo_min, width=8).grid(row=linha, column=1, sticky="w")
        linha += 1

        ttk.Label(f, text="Chance de pular o dia (%)").grid(row=linha, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.var_chance_pular, width=8).grid(row=linha, column=1, sticky="w")
        linha += 1

        ttk.Checkbutton(f, text="Fazer 'git push' automaticamente após o commit",
                         variable=self.var_push).grid(row=linha, column=0, columnspan=3, sticky="w")
        linha += 1

        ttk.Button(f, text="💾 Salvar trabalho", command=self._salvar_job).grid(row=linha, column=0, pady=10, sticky="w")

        for col in range(5):
            f.columnconfigure(col, weight=1)

        self.job_selecionado_id = None

    def _montar_aba_geral(self):
        f = self.aba_geral
        self.var_iniciar_windows = tk.BooleanVar(value=self.cfg["geral"].get("iniciar_com_windows", True))
        ttk.Checkbutton(f, text="Iniciar automaticamente com o Windows",
                         variable=self.var_iniciar_windows).pack(anchor="w", padx=12, pady=12)

        ttk.Label(f, text="Intervalo de verificação do agendador (segundos):").pack(anchor="w", padx=12)
        self.var_intervalo_verificacao = tk.StringVar(
            value=str(self.cfg["geral"].get("intervalo_verificacao_segundos", 30)))
        ttk.Entry(f, textvariable=self.var_intervalo_verificacao, width=10).pack(anchor="w", padx=12, pady=4)

        ttk.Button(f, text="💾 Salvar configurações gerais", command=self._salvar_geral).pack(anchor="w", padx=12, pady=12)

    def _montar_aba_logs(self):
        f = self.aba_logs
        self.texto_logs = tk.Text(f, state="disabled", wrap="word")
        self.texto_logs.pack(fill="both", expand=True, padx=8, pady=8)
        self._carregar_log_persistido()

    def _carregar_log_persistido(self):
        """Preenche a aba de Logs com o que já está salvo em disco (a
        partir do último separador de dia, ou tudo se não houver nenhum)
        — assim, ao reabrir o programa, o histórico de hoje continua
        visível em vez de começar em branco toda vez."""
        if not os.path.exists(config.CAMINHO_LOG):
            return
        try:
            with open(config.CAMINHO_LOG, "r", encoding="utf-8", errors="ignore") as arq:
                linhas = arq.readlines()
        except OSError:
            return

        indice_ultimo_separador = None
        for i, linha in enumerate(linhas):
            if linha.startswith("---------"):
                indice_ultimo_separador = i

        if indice_ultimo_separador is not None:
            linhas_para_mostrar = linhas[indice_ultimo_separador:]
        else:
            linhas_para_mostrar = linhas[-500:]  # sem separador ainda: mostra o fim do arquivo

        if not linhas_para_mostrar:
            return

        self.texto_logs.configure(state="normal")
        for linha in linhas_para_mostrar:
            self.texto_logs.insert(tk.END, linha if linha.endswith("\n") else linha + "\n")
        self.texto_logs.see(tk.END)
        self.texto_logs.configure(state="disabled")

    # ---------------- ações ----------------

    def _recarregar_lista_jobs(self):
        self.cfg = config.carregar_config()
        self.lista_jobs.delete(0, tk.END)
        for job in self.cfg["jobs"]:
            marcador = "✔" if job.get("ativo", True) else "✖"
            self.lista_jobs.insert(tk.END, f"{marcador} {job['nome']}")

    def _job_atual_da_lista(self):
        selecao = self.lista_jobs.curselection()
        if not selecao:
            return None
        return self.cfg["jobs"][selecao[0]]

    def _ao_selecionar_job(self, evento):
        job = self._job_atual_da_lista()
        if not job:
            return
        self.job_selecionado_id = job["id"]
        self.var_nome.set(job["nome"])
        self.var_ativo.set(job.get("ativo", True))
        self.var_repo.set(job.get("repo_path", ""))
        self.var_arquivo.set(job.get("arquivo_alvo", "log.md"))
        self.var_modo.set(job.get("modo_conteudo", "mensagens"))
        self.var_comando_custom.set(job.get("comando_custom", ""))
        self.var_prefixo.set(job.get("prefixo_mensagem", "chore: "))
        self.var_banco_arquivo.set(job.get("banco_mensagens_arquivo", ""))
        self.var_sequencial.set(job.get("usar_banco_sequencial", True))
        self.var_hora_inicio.set(job.get("hora_inicio", "08:00"))
        self.var_hora_fim.set(job.get("hora_fim", "22:00"))
        self.var_min_dia.set(str(job.get("commits_min_dia", 1)))
        self.var_max_dia.set(str(job.get("commits_max_dia", 3)))
        self.var_intervalo_min.set(str(job.get("intervalo_min_minutos", 45)))
        self.var_chance_pular.set(str(int(job.get("chance_pular_dia", 0.15) * 100)))
        self.var_push.set(job.get("push_automatico", True))
        dias_ativos = job.get("dias_semana", list(range(7)))
        for i, var in enumerate(self.vars_dias):
            var.set(i in dias_ativos)

        tipos_ativos = job.get("tipos_commit_selecionados", list(config.TIPOS_COMMIT_VALIDOS))
        for tipo, var in self.vars_tipos_commit.items():
            var.set(tipo in tipos_ativos)

    def _novo_job(self):
        job = config.novo_job()
        self.cfg["jobs"].append(job)
        config.salvar_config(self.cfg)
        self._recarregar_lista_jobs()
        self.lista_jobs.selection_clear(0, tk.END)
        self.lista_jobs.selection_set(tk.END)
        self._ao_selecionar_job(None)

    def _remover_job(self):
        job = self._job_atual_da_lista()
        if not job:
            return
        if not messagebox.askyesno("Confirmar", f"Remover o trabalho '{job['nome']}'?"):
            return
        self.cfg["jobs"] = [j for j in self.cfg["jobs"] if j["id"] != job["id"]]
        config.salvar_config(self.cfg)
        self._recarregar_lista_jobs()

    def _escolher_repo(self):
        caminho = filedialog.askdirectory(title="Selecione a pasta do repositório git")
        if caminho:
            self.var_repo.set(caminho)

    def _importar_banco(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o arquivo de mensagens",
            filetypes=[("Texto ou CSV", "*.txt *.csv"), ("Todos os arquivos", "*.*")]
        )
        if caminho:
            self.var_banco_arquivo.set(caminho)

    def _salvar_job(self):
        if not self.job_selecionado_id:
            messagebox.showwarning("Aviso", "Selecione ou crie um trabalho primeiro.")
            return

        try:
            min_dia = int(self.var_min_dia.get())
            max_dia = int(self.var_max_dia.get())
            intervalo_min = int(self.var_intervalo_min.get())
            chance_pular = float(self.var_chance_pular.get()) / 100.0
        except ValueError:
            messagebox.showerror("Erro", "Valores numéricos inválidos (commits/dia, intervalo ou chance de pular).")
            return

        banco_mensagens = []
        caminho_banco = self.var_banco_arquivo.get().strip()
        if caminho_banco:
            banco_mensagens = config.importar_banco_mensagens(caminho_banco)

        dias_semana = [i for i, var in enumerate(self.vars_dias) if var.get()]

        tipos_selecionados = [tipo for tipo, var in self.vars_tipos_commit.items() if var.get()]
        aviso_tipos = []
        if not tipos_selecionados:
            tipos_selecionados = list(config.TIPOS_COMMIT_VALIDOS)
            for var in self.vars_tipos_commit.values():
                var.set(True)
            aviso_tipos = ["Nenhum tipo de commit estava selecionado — todos foram marcados automaticamente."]

        avisos = []
        for job in self.cfg["jobs"]:
            if job["id"] == self.job_selecionado_id:
                job.update({
                    "nome": self.var_nome.get().strip() or "Trabalho sem nome",
                    "ativo": self.var_ativo.get(),
                    "repo_path": self.var_repo.get().strip(),
                    "arquivo_alvo": self.var_arquivo.get().strip() or "log.md",
                    "modo_conteudo": self.var_modo.get(),
                    "comando_custom": self.var_comando_custom.get().strip(),
                    "prefixo_mensagem": self.var_prefixo.get(),
                    "banco_mensagens_arquivo": caminho_banco,
                    "banco_mensagens": banco_mensagens if banco_mensagens else job.get("banco_mensagens", []),
                    "usar_banco_sequencial": self.var_sequencial.get(),
                    "tipos_commit_selecionados": tipos_selecionados,
                    "dias_semana": dias_semana,
                    "hora_inicio": self.var_hora_inicio.get().strip(),
                    "hora_fim": self.var_hora_fim.get().strip(),
                    "commits_min_dia": min_dia,
                    "commits_max_dia": max_dia,
                    "intervalo_min_minutos": intervalo_min,
                    "chance_pular_dia": chance_pular,
                    "push_automatico": self.var_push.get(),
                })

                # corrige intervalo mínimo <= 0 e commits_min_dia/commits_max_dia
                # que não cabem de forma realista na janela de horário configurada;
                # se os valores já eram válidos, o job não é alterado.
                job_corrigido, avisos = config.validar_job(job)
                job.update(job_corrigido)
                avisos = aviso_tipos + avisos

                # reflete na tela os valores efetivamente salvos, caso algo tenha sido ajustado
                self.var_min_dia.set(str(job["commits_min_dia"]))
                self.var_max_dia.set(str(job["commits_max_dia"]))
                self.var_intervalo_min.set(str(job["intervalo_min_minutos"]))
                break

        config.salvar_config(self.cfg)
        self._recarregar_lista_jobs()

        if avisos:
            messagebox.showwarning(
                "Salvo com ajustes",
                "Trabalho salvo, mas alguns valores foram ajustados automaticamente:\n\n"
                + "\n".join(f"• {a}" for a in avisos)
            )
        else:
            messagebox.showinfo("Salvo", "Trabalho salvo com sucesso.")

    def _rodar_agora(self):
        job = self._job_atual_da_lista()
        if not job:
            messagebox.showwarning("Aviso", "Selecione um trabalho na lista.")
            return

        # Verifica no git log real se o intervalo mínimo já foi respeitado —
        # cobre o caso de o último commit ter sido feito numa execução
        # anterior do programa, ou até manualmente fora dele.
        pode_rodar, aviso = self.agendador.verificar_intervalo_minimo(job)

        if not pode_rodar:
            dialogo = DialogoEscolhaExecucao(self, aviso + "\n\nO que deseja fazer?")
            self.wait_window(dialogo)
            escolha = dialogo.resultado

            if escolha == "cancelar":
                return

            if escolha == "depois":
                self.agendador.agendar_para_depois(job)
                messagebox.showinfo(
                    "Agendado",
                    "O commit será feito automaticamente assim que o intervalo mínimo for atingido."
                )
                return

            # escolha == "agora" -> segue o fluxo abaixo, forçando mesmo assim

        messagebox.showinfo("Auto Committer", "Commits iniciados")

        sucesso, saida = self.agendador.executar_agora(job)
        if sucesso:
            messagebox.showinfo("Concluído", "Commit executado. Veja detalhes na aba Logs.")
        else:
            messagebox.showerror("Falhou", f"O commit falhou:\n\n{saida}")

    def _salvar_geral(self):
        try:
            intervalo = int(self.var_intervalo_verificacao.get())
        except ValueError:
            messagebox.showerror("Erro", "Intervalo de verificação inválido.")
            return

        self.cfg["geral"]["iniciar_com_windows"] = self.var_iniciar_windows.get()
        self.cfg["geral"]["intervalo_verificacao_segundos"] = intervalo
        config.salvar_config(self.cfg)

        try:
            import startup
            if self.var_iniciar_windows.get():
                startup.instalar_inicializacao()
            else:
                startup.remover_inicializacao()
        except Exception as exc:
            messagebox.showwarning("Aviso", f"Configuração salva, mas não foi possível atualizar a "
                                            f"inicialização automática: {exc}")
            return

        messagebox.showinfo("Salvo", "Configurações gerais salvas.")

    # ---------------- logs ----------------

    def adicionar_log(self, texto):
        self.texto_logs.configure(state="normal")
        self.texto_logs.insert(tk.END, texto + "\n")
        self.texto_logs.see(tk.END)
        self.texto_logs.configure(state="disabled")

    def _atualizar_logs_periodicamente(self):
        # placeholder — logs chegam via callback direto do agendador (ver main.py)
        pass

    def _ao_fechar(self):
        self.withdraw()  # some a janela, mas o processo continua rodando na bandeja