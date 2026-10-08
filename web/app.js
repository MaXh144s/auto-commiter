const API_USER_URL = "https://api.github.com/user";
const API_GRAPHQL_URL = "https://api.github.com/graphql";
const CONTRIBUTIONS_QUERY = `
  query($login: String!, $from: DateTime!, $to: DateTime!) {
    user(login: $login) {
      login
      contributionsCollection(from: $from, to: $to) {
        contributionCalendar {
          totalContributions
          weeks {
            contributionDays {
              date
              contributionCount
              color
            }
          }
        }
      }
    }
  }
`;

let apiReady = false;
let githubToken = null;
let githubUser = null;
let currentDays = [];
let commitBusy = false;
let validRepository = false;
let bankMessages = [];
let selectedBankMessage = null;
let selectedMessageUsage = null;
let schedulePollTimer = null;
let countdownTimer = null;
let scheduleNextAt = null;
let pendingTimingCommitTimestamp = null;
let pendingTimingNextTimestamp = null;
let lastScheduleErrorShown = "";
let startupAvailable = false;

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  bindEvents();
  initializePeriodControls();
  window.addEventListener("resize", fitCalendarGrid);
});

window.addEventListener("pywebviewready", async () => {
  apiReady = true;
  elements.bridgeStatus.textContent = "Pronto para usar";
  elements.commitButton.disabled = false;
  await restoreScheduleSettings();
  await restoreApplicationSettings();
  await refreshStatusAndHistory();
  await refreshScheduleStatus();
  schedulePollTimer = window.setInterval(refreshScheduleStatus, 1000);
  countdownTimer = window.setInterval(renderScheduleCountdown, 1000);
});

function cacheElements() {
  const ids = [
    "bridge-status", "page-title", "commit-page", "github-page", "commit-form",
    "repo-path", "repo-error", "repo-hint", "browse-button", "repo-status",
    "message-bank-field", "message-bank-select", "message-bank-button", "message-bank-name",
    "avoid-repeated", "message-usage",
    "weekday-options", "schedule-interval", "schedule-minimum", "schedule-maximum",
    "schedule-days-error", "schedule-interval-error", "schedule-minimum-error",
    "schedule-maximum-error", "schedule-form-error", "save-schedule",
    "toggle-schedule", "schedule-state", "schedule-progress", "schedule-progress-text",
    "schedule-next-commit", "schedule-progress-bar", "schedule-status-message",
    "schedule-last-commit", "schedule-log",
    "refresh-status", "commit-message", "message-error",
    "commit-button", "history-count", "history-list", "confirm-dialog",
    "confirm-repo", "confirm-message", "confirm-push", "confirm-submit",
    "toast-region", "token-form", "github-token", "token-error", "connect-button",
    "connect-form", "connected-user", "user-avatar", "user-name", "user-login",
    "disconnect-button", "period-select", "period-from", "period-to",
    "load-calendar", "stat-total", "stat-current", "stat-longest",
    "calendar-state", "calendar-skeleton", "heatmap-scroll", "heatmap",
    "month-labels",
    "calendar-subtitle", "calendar-feedback", "settings-error", "startup-toggle",
    "startup-state", "tray-toggle",
    "commit-timing-dialog", "timing-message"
  ];
  for (const id of ids) {
    elements[id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] =
      document.getElementById(id);
  }
}

function bindEvents() {
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.target));
  });
  elements.browseButton.addEventListener("click", chooseRepository);
  elements.refreshStatus.addEventListener("click", refreshStatusAndHistory);
  elements.repoPath.addEventListener("change", refreshStatusAndHistory);
  elements.repoPath.addEventListener("input", invalidateRepository);
  elements.messageBankButton.addEventListener("click", chooseMessageBank);
  elements.messageBankSelect.addEventListener("change", applyBankMessage);
  elements.avoidRepeated.addEventListener("change", onAvoidRepeatedChanged);
  elements.commitForm.addEventListener("submit", openCommitConfirmation);
  elements.confirmDialog.addEventListener("close", onConfirmationClosed);
  elements.commitTimingDialog.addEventListener("close", onTimingConfirmationClosed);
  elements.tokenForm.addEventListener("submit", connectGithub);
  elements.disconnectButton.addEventListener("click", disconnectGithub);
  elements.loadCalendar.addEventListener("click", loadContributions);
  elements.periodSelect.addEventListener("change", onPeriodChanged);
  elements.periodFrom.addEventListener("change", useCustomPeriod);
  elements.periodTo.addEventListener("change", useCustomPeriod);
  elements.saveSchedule.addEventListener("click", saveScheduleSettings);
  elements.toggleSchedule.addEventListener("click", toggleSchedule);
  elements.startupToggle.addEventListener("change", updateWindowsStartup);
  elements.trayToggle.addEventListener("change", updateTrayPreference);
}

function showPage(pageId) {
  const isGithub = pageId === "github-page";
  const isSettings = pageId === "settings-page";
  document.querySelectorAll(".page").forEach((page) => {
    const active = page.id === pageId;
    page.hidden = !active;
    page.classList.toggle("active", active);
  });
  document.querySelectorAll(".nav-link").forEach((button) => {
    const active = button.dataset.target === pageId;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.getElementById("page-title").textContent =
    isGithub ? "Gráfico do GitHub" : isSettings ? "Configurações" : "Auto Commit";
}

async function restoreApplicationSettings() {
  try {
    const result = await window.pywebview.api.obter_configuracoes_aplicativo();
    if (!result.ok) {
      setFieldError(elements.settingsError, result.erro || "Não foi possível carregar as configurações.");
      return;
    }
    const startup = result.iniciar_com_windows || {};
    startupAvailable = Boolean(startup.disponivel);
    elements.startupToggle.checked = Boolean(startup.ativado);
    elements.startupToggle.disabled = !startupAvailable;
    elements.startupState.textContent = startup.disponivel
      ? startup.ativado ? "Ativado no Registro do Windows." : "Desativado no Registro do Windows."
      : "Disponível somente no Windows.";
    elements.trayToggle.checked = result.fechar_para_bandeja;
    elements.trayToggle.disabled = !result.bandeja_disponivel;
  } catch {
    setFieldError(elements.settingsError, "Não foi possível consultar as configurações do sistema.");
  }
}

async function updateWindowsStartup() {
  const valorAnterior = !elements.startupToggle.checked;
  elements.startupToggle.disabled = true;
  try {
    const result = await window.pywebview.api.definir_inicio_com_windows(
      elements.startupToggle.checked
    );
    if (!result.ok) {
      elements.startupToggle.checked = valorAnterior;
      setFieldError(elements.settingsError, result.erro || "Não foi possível alterar a inicialização.");
      return;
    }
    elements.startupToggle.checked = Boolean(result.ativado);
    elements.startupState.textContent = result.ativado
      ? "Ativado no Registro do Windows."
      : "Desativado no Registro do Windows.";
    clearFieldError(elements.settingsError);
    showToast(result.mensagem || "Preferência atualizada.", "success");
  } catch {
    elements.startupToggle.checked = valorAnterior;
    setFieldError(elements.settingsError, "Não foi possível alterar a inicialização do Windows.");
  } finally {
    elements.startupToggle.disabled = !startupAvailable;
  }
}

async function updateTrayPreference() {
  const valorAnterior = !elements.trayToggle.checked;
  elements.trayToggle.disabled = true;
  try {
    const result = await window.pywebview.api.definir_fechar_para_bandeja(
      elements.trayToggle.checked
    );
    if (!result.ok) {
      elements.trayToggle.checked = valorAnterior;
      setFieldError(elements.settingsError, result.erro || "Não foi possível salvar a preferência.");
      return;
    }
    clearFieldError(elements.settingsError);
    showToast("Preferência da bandeja salva.", "success");
  } catch {
    elements.trayToggle.checked = valorAnterior;
    setFieldError(elements.settingsError, "Não foi possível salvar a preferência da bandeja.");
  } finally {
    elements.trayToggle.disabled = false;
  }
}

async function chooseRepository() {
  if (!apiReady) return;
  elements.browseButton.disabled = true;
  try {
    const result = await window.pywebview.api.selecionar_pasta();
    if (!result.ok) {
      showToast(result.erro || "Não foi possível escolher a pasta.", "error");
      return;
    }
    if (!result.cancelado && result.caminho) {
      elements.repoPath.value = result.caminho;
      clearFieldError(elements.repoError);
      await refreshStatusAndHistory();
    }
  } catch {
    showToast("Não foi possível abrir a seleção de pastas.", "error");
  } finally {
    elements.browseButton.disabled = false;
  }
}

async function refreshStatusAndHistory() {
  if (!apiReady) return;
  const path = elements.repoPath.value.trim();
  validRepository = false;
  updateMessageBankAvailability();
  setRepositoryStatus("Conferindo a pasta…", "loading");
  try {
    const result = await window.pywebview.api.listar_status(path);
    if (!result.ok) {
      setRepositoryStatus(result.erro || "Não foi possível conferir esta pasta.", "invalid");
      setFieldError(elements.repoError, result.erro || "Escolha um repositório Git válido.");
    } else {
      validRepository = Boolean(path);
      setRepositoryStatus(result.mensagem, path ? "valid" : "");
      clearFieldError(elements.repoError);
    }
    updateMessageBankAvailability();
    renderHistory(result.historico || []);
  } catch {
    setRepositoryStatus("Não foi possível conferir esta pasta.", "invalid");
    updateMessageBankAvailability();
  }
}

function invalidateRepository() {
  validRepository = false;
  updateMessageBankAvailability();
}

function updateMessageBankAvailability() {
  elements.messageBankField.hidden = !validRepository;
  elements.messageBankButton.disabled = !validRepository;
}

async function restoreScheduleSettings() {
  try {
    const result = await window.pywebview.api.obter_configuracoes_agendamento();
    if (!result.ok) {
      setScheduleError(result.erro || "Não foi possível carregar as configurações.");
      return;
    }
    const settings = result.configuracoes;
    for (const checkbox of elements.weekdayOptions.querySelectorAll("input[type=checkbox]")) {
      checkbox.checked = settings.dias_semana.includes(Number(checkbox.value));
    }
    elements.scheduleInterval.value = settings.intervalo_minutos;
    elements.scheduleMinimum.value = settings.commits_min_dia;
    elements.scheduleMaximum.value = settings.commits_max_dia;
    if (result.repo_path && !elements.repoPath.value) {
      elements.repoPath.value = result.repo_path;
    }
    if (result.banco_mensagens?.length) {
      bankMessages = result.banco_mensagens;
      populateMessageBank("Banco salvo", bankMessages);
      elements.messageBankSelect.value = "0";
      applyBankMessage(false);
    }
    renderScheduleStatus(result.estado);
  } catch {
    setScheduleError("Não foi possível carregar as configurações do agendamento.");
  }
}

function populateMessageBank(name, messages) {
  elements.messageBankSelect.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Selecione uma mensagem";
  elements.messageBankSelect.append(placeholder);
  messages.forEach((item, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${item.tipo}: ${item.mensagem}`;
    elements.messageBankSelect.append(option);
  });
  elements.messageBankSelect.disabled = messages.length === 0;
  elements.avoidRepeated.disabled = messages.length === 0;
  elements.messageBankName.textContent = `${name} · ${messages.length} mensagens.`;
}

async function chooseMessageBank() {
  if (!apiReady || !validRepository) return;
  elements.messageBankButton.disabled = true;
  try {
    const result = await window.pywebview.api.selecionar_banco_mensagens(
      elements.repoPath.value.trim()
    );
    if (!result.ok) {
      showToast(result.erro || "Não foi possível carregar esse banco.", "error");
      return;
    }
    if (result.cancelado) return;

    bankMessages = result.mensagens || [];
    populateMessageBank(result.nome, bankMessages);
    if (bankMessages.length > 0) {
      elements.messageBankSelect.value = "0";
      applyBankMessage();
      if (elements.avoidRepeated.checked && !(await refreshAvoidedSuggestion())) return;
    }
    showToast("Banco de mensagens carregado.", "success");
  } catch {
    showToast("Não foi possível carregar o banco de mensagens.", "error");
  } finally {
    elements.messageBankButton.disabled = !validRepository;
  }
}

function applyBankMessage(focus = true) {
  const index = Number(elements.messageBankSelect.value);
  const item = bankMessages[index];
  if (!item) return;
  selectedBankMessage = item;
  selectedMessageUsage = null;
  elements.commitMessage.value = `${item.tipo}: ${item.mensagem}`;
  elements.messageUsage.textContent = elements.avoidRepeated.checked
    ? ""
    : "A seleção segue a ordem do banco; a frequência não está sendo considerada.";
  clearFieldError(elements.messageError);
  if (focus) elements.commitMessage.focus();
}

async function onAvoidRepeatedChanged() {
  elements.messageBankSelect.disabled =
    elements.avoidRepeated.checked || bankMessages.length === 0;
  if (elements.avoidRepeated.checked) {
    await refreshAvoidedSuggestion();
    return;
  }
  if (bankMessages.length) {
    elements.messageBankSelect.value = "0";
    applyBankMessage();
  }
}

async function refreshAvoidedSuggestion() {
  if (!apiReady || !bankMessages.length) return false;
  try {
    const result = await window.pywebview.api.sugerir_mensagem_commit(
      elements.repoPath.value.trim(),
      bankMessages
    );
    if (!result.ok) {
      elements.messageUsage.textContent = "";
      setFieldError(elements.messageError, result.erro || "Não foi possível ler o histórico do repositório.");
      showToast(result.erro || "Não foi possível ler o histórico do repositório.", "error");
      return false;
    }
    applySuggestedMessage(result.mensagem, result.usos);
    return true;
  } catch {
    setFieldError(elements.messageError, "Não foi possível ler o histórico do repositório.");
    showToast("Não foi possível ler o histórico do repositório.", "error");
    return false;
  }
}

function applySuggestedMessage(item, usageCount) {
  const index = bankMessages.findIndex(
    (message) => message.tipo === item.tipo && message.mensagem === item.mensagem
  );
  if (index < 0) return false;
  elements.messageBankSelect.value = String(index);
  selectedBankMessage = bankMessages[index];
  selectedMessageUsage = Number(usageCount) || 0;
  elements.commitMessage.value = `${item.tipo}: ${item.mensagem}`;
  const count = selectedMessageUsage;
  elements.messageUsage.textContent =
    `Já usada ${count} ${count === 1 ? "vez" : "vezes"} antes deste commit.`;
  clearFieldError(elements.messageError);
  return true;
}

function readScheduleSettings() {
  clearScheduleValidation();
  const dias = [...elements.weekdayOptions.querySelectorAll("input:checked")]
    .map((checkbox) => Number(checkbox.value));
  const intervalo = Number(elements.scheduleInterval.value);
  const minimo = Number(elements.scheduleMinimum.value);
  const maximo = Number(elements.scheduleMaximum.value);
  let valid = true;

  if (!dias.length) {
    setFieldError(elements.scheduleDaysError, "Marque ao menos um dia da semana.");
    valid = false;
  }
  if (!Number.isInteger(intervalo) || intervalo < 1) {
    setFieldError(elements.scheduleIntervalError, "Use um número inteiro de pelo menos 1 minuto.");
    valid = false;
  }
  if (!Number.isInteger(minimo) || minimo < 1) {
    setFieldError(elements.scheduleMinimumError, "Use um número inteiro maior que zero.");
    valid = false;
  }
  if (!Number.isInteger(maximo) || maximo < 1) {
    setFieldError(elements.scheduleMaximumError, "Use um número inteiro maior que zero.");
    valid = false;
  } else if (Number.isInteger(minimo) && minimo > maximo) {
    setFieldError(elements.scheduleMaximumError, "O máximo precisa ser igual ou maior que o mínimo.");
    valid = false;
  }
  if (!valid) return null;
  return {
    dias_semana: dias,
    intervalo_minutos: intervalo,
    commits_min_dia: minimo,
    commits_max_dia: maximo,
  };
}

function clearScheduleValidation() {
  for (const element of [
    elements.scheduleDaysError,
    elements.scheduleIntervalError,
    elements.scheduleMinimumError,
    elements.scheduleMaximumError,
    elements.scheduleFormError,
  ]) clearFieldError(element);
}

function setScheduleError(message) {
  setFieldError(elements.scheduleFormError, message);
}

async function saveScheduleSettings() {
  const configuracoes = readScheduleSettings();
  if (!configuracoes) return;
  elements.saveSchedule.disabled = true;
  try {
    const hasRepositoryAndBank = validRepository && bankMessages.length > 0;
    const result = await window.pywebview.api.salvar_configuracoes_agendamento(
      configuracoes,
      hasRepositoryAndBank ? elements.repoPath.value.trim() : "",
      hasRepositoryAndBank ? bankMessages : []
    );
    if (!result.ok) {
      setScheduleError(result.erro || "Não foi possível salvar as configurações.");
      return;
    }
    showToast(result.mensagem || "Configurações salvas.", "success");
    clearScheduleValidation();
  } catch {
    setScheduleError("Não foi possível salvar as configurações.");
  } finally {
    elements.saveSchedule.disabled = false;
  }
}

async function toggleSchedule() {
  const current = await getScheduleStatus();
  if (!current) return;
  if (current.ativo && !current.pausado) {
    elements.toggleSchedule.disabled = true;
    try {
      const result = await window.pywebview.api.parar_agendamento();
      if (!result.ok) {
        setScheduleError(result.erro || "Não foi possível parar o agendamento.");
        return;
      }
      renderScheduleStatus(result.estado);
      showToast(result.mensagem || "Automação pausada.", "success");
    } catch {
      setScheduleError("Não foi possível parar o agendamento.");
    } finally {
      elements.toggleSchedule.disabled = false;
    }
    return;
  }
  if (!current.ativado) {
    setScheduleError("A automação será ativada automaticamente após o primeiro commit manual.");
    return;
  }
  elements.toggleSchedule.disabled = true;
  try {
    const result = await window.pywebview.api.retomar_agendamento();
    if (!result.ok) {
      setScheduleError(result.erro || "Não foi possível retomar a automação.");
      return;
    }
    clearScheduleValidation();
    renderScheduleStatus(result.estado);
    showToast(result.mensagem || "Automação retomada.", "success");
  } catch {
    setScheduleError("Não foi possível retomar a automação.");
  } finally {
    elements.toggleSchedule.disabled = false;
  }
}

async function getScheduleStatus() {
  if (!apiReady) return null;
  try {
    const response = await window.pywebview.api.obter_estado_agendamento();
    if (!response.ok) throw new Error("schedule-status-unavailable");
    return response.estado;
  } catch {
    setScheduleError("Não foi possível atualizar o estado do agendamento.");
    return null;
  }
}

async function refreshScheduleStatus() {
  const state = await getScheduleStatus();
  if (state) renderScheduleStatus(state);
}

function renderScheduleStatus(state) {
  if (!state) return;
  const aguardando = state.mensagem?.startsWith("Aguardando o próximo dia ativo");
  elements.scheduleState.textContent = !state.ativado
    ? "Aguardando 1º commit"
    : state.pausado ? "Pausado" : aguardando ? "Aguardando dia ativo" : "Ativo";
  elements.scheduleState.classList.toggle("active", Boolean(state.ativado) && !state.pausado);
  elements.scheduleState.classList.toggle("stopping", Boolean(state.pausado));
  elements.toggleSchedule.textContent = !state.ativado
    ? "Ativa após commit"
    : state.pausado ? "Retomar" : "Pausar";
  elements.toggleSchedule.disabled = !state.ativado;
  const automationRunning = Boolean(state.ativo) && !state.pausado;
  for (const input of elements.weekdayOptions.querySelectorAll("input")) {
    input.disabled = automationRunning;
  }
  for (const input of [
    elements.scheduleInterval,
    elements.scheduleMinimum,
    elements.scheduleMaximum,
    elements.saveSchedule,
  ]) input.disabled = automationRunning;
  elements.repoPath.disabled = automationRunning;
  elements.browseButton.disabled = automationRunning;
  elements.refreshStatus.disabled = automationRunning;
  elements.messageBankButton.disabled = automationRunning || !validRepository;
  elements.messageBankSelect.disabled =
    automationRunning || elements.avoidRepeated.checked || bankMessages.length === 0;
  elements.avoidRepeated.disabled = automationRunning || bankMessages.length === 0;
  elements.commitButton.disabled = !apiReady;
  elements.scheduleLastCommit.textContent = state.ultimo_commit
    ? `Último commit: ${new Date(state.ultimo_commit).toLocaleString("pt-BR")}`
    : "Último commit: ainda não realizado";
  elements.scheduleProgress.hidden =
    !state.ativado && (state.alvo === null || state.alvo === undefined);
  if (state.alvo !== null && state.alvo !== undefined) {
    elements.scheduleProgressText.textContent = `${state.feitos} de ${state.alvo} commits feitos`;
    elements.scheduleProgressBar.max = Math.max(1, state.alvo);
    elements.scheduleProgressBar.value = Math.min(state.feitos, state.alvo);
  } else if (state.ativado) {
    elements.scheduleProgressText.textContent = "Aguardando o início do dia ativo";
    elements.scheduleProgressBar.max = 1;
    elements.scheduleProgressBar.value = 0;
  }
  elements.scheduleStatusMessage.textContent = state.mensagem || "";
  scheduleNextAt = Number.isFinite(state.proximo_em_segundos)
    ? Date.now() + state.proximo_em_segundos * 1000
    : null;
  renderScheduleCountdown();
  renderScheduleLog(state.logs || []);
}

function renderScheduleCountdown() {
  if (!elements.scheduleNextCommit) return;
  if (!scheduleNextAt) {
    elements.scheduleNextCommit.textContent = "Próximo commit: —";
    return;
  }
  const segundos = Math.max(0, Math.ceil((scheduleNextAt - Date.now()) / 1000));
  const horas = String(Math.floor(segundos / 3600)).padStart(2, "0");
  const minutos = String(Math.floor((segundos % 3600) / 60)).padStart(2, "0");
  const restantes = String(segundos % 60).padStart(2, "0");
  const previsao = new Date(scheduleNextAt).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  elements.scheduleNextCommit.textContent =
    `Próximo commit em ${horas}:${minutos}:${restantes} · ${previsao}`;
}

function renderScheduleLog(entries) {
  elements.scheduleLog.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "schedule-log-empty";
    empty.textContent = "Os commits automáticos aparecerão aqui.";
    elements.scheduleLog.append(empty);
    return;
  }
  for (const entry of [...entries].reverse()) {
    const row = document.createElement("div");
    row.className = `schedule-log-item${entry.nivel === "error" ? " error" : ""}`;
    const time = document.createElement("time");
    time.textContent = entry.horario;
    const text = document.createElement("span");
    text.textContent = entry.texto;
    row.append(time, text);
    elements.scheduleLog.append(row);
  }
  const latestError = [...entries].reverse().find((entry) => entry.nivel === "error");
  if (latestError) {
    const key = `${latestError.horario}:${latestError.texto}`;
    if (key !== lastScheduleErrorShown) {
      lastScheduleErrorShown = key;
      showToast(latestError.texto, "error");
    }
  }
}

function setRepositoryStatus(message, state) {
  elements.repoStatus.classList.remove("valid", "invalid");
  if (state === "valid" || state === "invalid") elements.repoStatus.classList.add(state);
  elements.repoStatus.querySelector("span:nth-child(2)").textContent = message;
}

function validateCommitForm() {
  let valid = true;
  const repo = elements.repoPath.value.trim();
  clearFieldError(elements.repoError);
  clearFieldError(elements.messageError);
  if (!repo) {
    setFieldError(elements.repoError, "Escolha a pasta do repositório.");
    valid = false;
  }
  if (!selectedBankMessage) {
    setFieldError(elements.messageError, "Escolha um banco válido e selecione uma mensagem.");
    valid = false;
  }
  if (!valid) {
    if (!repo) elements.repoPath.focus();
    else if (!selectedBankMessage) elements.messageBankButton.focus();
  }
  return valid;
}

async function openCommitConfirmation(event) {
  event.preventDefault();
  if (!apiReady || commitBusy || !validateCommitForm()) return;
  commitBusy = true;
  setButtonLoading(elements.commitButton, true);
  const repo = elements.repoPath.value.trim();
  let status;
  try {
    status = await window.pywebview.api.listar_status(repo);
  } catch {
    setFieldError(elements.repoError, "Não foi possível conferir esta pasta.");
    setRepositoryStatus("Não foi possível conferir esta pasta.", "invalid");
    commitBusy = false;
    setButtonLoading(elements.commitButton, false);
    return;
  }
  if (!status.ok) {
    commitBusy = false;
    setButtonLoading(elements.commitButton, false);
    const message = status.erro || "Escolha um repositório Git válido.";
    setFieldError(elements.repoError, message);
    setRepositoryStatus(message, "invalid");
    return;
  }
  if (elements.avoidRepeated.checked && !(await refreshAvoidedSuggestion())) {
    commitBusy = false;
    setButtonLoading(elements.commitButton, false);
    return;
  }
  commitBusy = false;
  setButtonLoading(elements.commitButton, false);
  clearFieldError(elements.repoError);
  setRepositoryStatus(status.mensagem, "valid");
  try {
    const timing = await window.pywebview.api.prever_commit_manual();
    if (!timing.ok) throw new Error("manual-commit-preview-failed");
    if (timing.mostrar_modal) {
      showCommitTimingDialog(timing);
      return;
    }
  } catch {
    showToast("Não foi possível conferir o intervalo do próximo commit.", "error");
    return;
  }
  showCommitConfirmationDialog();
}

function showCommitTimingDialog(timing) {
  pendingTimingCommitTimestamp = timing.ultimo_commit_timestamp;
  pendingTimingNextTimestamp = timing.proximo_commit_timestamp;
  elements.timingMessage.textContent =
    `O último commit foi realizado há ${timing.tempo_desde}. ` +
    `O próximo commit será realizado em ${timing.tempo_ate}.`;
  elements.commitTimingDialog.showModal();
}

function onTimingConfirmationClosed() {
  if (elements.commitTimingDialog.returnValue !== "now") {
    pendingTimingCommitTimestamp = null;
    pendingTimingNextTimestamp = null;
    return;
  }
  void runCommit(
    true,
    pendingTimingCommitTimestamp,
    pendingTimingNextTimestamp
  );
  pendingTimingCommitTimestamp = null;
  pendingTimingNextTimestamp = null;
}

function showCommitConfirmationDialog() {
  document.getElementById("confirm-title").textContent = "Gerar esta contribuição?";
  document.querySelector(".dialog-description").textContent =
    "Confira os detalhes antes de continuar.";
  elements.confirmRepo.textContent = elements.repoPath.value.trim();
  const usage = elements.avoidRepeated.checked && selectedMessageUsage !== null
    ? ` (já usada ${selectedMessageUsage} ${selectedMessageUsage === 1 ? "vez" : "vezes"})`
    : "";
  elements.confirmMessage.textContent = `${elements.commitMessage.value.trim()}${usage}`;
  elements.confirmPush.textContent = "Adicionar ao log.md, git add ., commit e push";
  elements.confirmSubmit.textContent = "Confirmar e enviar";
  elements.confirmDialog.showModal();
}

function onConfirmationClosed() {
  if (elements.confirmDialog.returnValue === "confirm") {
    void runCommit(false, null, null);
  }
}

async function runCommit(
  confirmarAgora = false,
  timestampConfirmado = null,
  proximoTimestampConfirmado = null
) {
  if (commitBusy) return;
  commitBusy = true;
  setButtonLoading(elements.commitButton, true);
  setRepositoryStatus("Registrando contribuição e enviando…", "loading");
  let reconfirm = false;
  try {
    const result = await window.pywebview.api.fazer_commit(
      elements.repoPath.value.trim(),
      selectedBankMessage.tipo,
      selectedBankMessage.mensagem,
      elements.avoidRepeated.checked,
      bankMessages,
      confirmarAgora,
      timestampConfirmado,
      proximoTimestampConfirmado
    );
    if (result.historico) renderHistory(result.historico);
    if (!result.ok) {
      if (result.confirmar_agora) {
        showCommitTimingDialog(result);
        return;
      }
      if (result.reconfirmar && result.mensagem_escolhida) {
        applySuggestedMessage(result.mensagem_escolhida, result.usos);
        setRepositoryStatus("Mensagem atualizada; confirme novamente para continuar.", "valid");
        showToast("O histórico mudou. Confira a mensagem atualizada e confirme novamente.", "error");
        reconfirm = true;
        return;
      }
      if (elements.avoidRepeated.checked && result.mensagem_escolhida) {
        applySuggestedMessage(result.mensagem_escolhida, result.usos);
      }
      setRepositoryStatus(result.erro || "Não foi possível concluir o commit.", "invalid");
      showToast(result.erro || "Não foi possível concluir o commit.", "error");
      return;
    }
    if (elements.avoidRepeated.checked && result.mensagem_escolhida) {
      applySuggestedMessage(result.mensagem_escolhida, result.usos);
    }
    showToast(result.mensagem || "Commit concluído.", "success");
    if (result.automacao && !result.automacao.ativado) {
      showToast(result.automacao.mensagem, "error");
    }
    await refreshStatusAndHistory();
    await refreshScheduleStatus();
    if (githubToken) {
      elements.calendarFeedback.textContent =
        "Contribuição enviada. O GitHub pode levar alguns instantes para atualizar.";
      window.setTimeout(() => {
        if (githubToken) void loadContributions();
      }, 5000);
    }
  } catch {
    setRepositoryStatus("Não foi possível concluir o commit.", "invalid");
    showToast("Não foi possível concluir o commit. Tente novamente.", "error");
  } finally {
    commitBusy = false;
    setButtonLoading(elements.commitButton, false);
    if (reconfirm) showCommitConfirmationDialog();
  }
}

function renderHistory(items) {
  elements.historyList.replaceChildren();
  elements.historyCount.textContent = `${items.length} ${items.length === 1 ? "ação" : "ações"}`;
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-history";
    const icon = document.createElement("span");
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "◷";
    const text = document.createElement("p");
    text.textContent = "Suas ações recentes aparecerão aqui.";
    empty.append(icon, text);
    elements.historyList.append(empty);
    return;
  }

  for (const item of items) {
    const row = document.createElement("div");
    row.className = "history-item";
    const icon = document.createElement("span");
    icon.className = `history-icon${item.ok ? "" : " failed"}`;
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = item.ok ? "✓" : "!";
    const description = document.createElement("div");
    description.className = "history-description";
    const title = document.createElement("strong");
    title.textContent = item.ok
      ? `${item.push ? "Contribuição enviada" : "Commit"} · ${item.repositorio}`
      : `Não concluído · ${item.repositorio}`;
    const detail = document.createElement("span");
    detail.textContent = item.mensagem || item.resultado || "";
    const time = document.createElement("time");
    time.className = "history-time";
    time.textContent = item.data || "";
    description.append(title, detail);
    row.append(icon, description, time);
    elements.historyList.append(row);
  }
}

function initializePeriodControls() {
  const today = new Date();
  const currentYear = today.getFullYear();
  const startYear = currentYear - 10;
  for (let year = currentYear; year >= startYear; year -= 1) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    elements.periodSelect.append(option);
  }
  setLastYearRange();
}

function setLastYearRange() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 364);
  elements.periodFrom.value = formatDateInput(start);
  elements.periodTo.value = formatDateInput(end);
}

function onPeriodChanged() {
  const selected = elements.periodSelect.value;
  if (selected === "last-year") {
    setLastYearRange();
  } else {
    const year = Number(selected);
    const today = new Date();
    elements.periodFrom.value = `${year}-01-01`;
    elements.periodTo.value = year === today.getFullYear()
      ? formatDateInput(today)
      : `${year}-12-31`;
  }
}

function useCustomPeriod() {
  const year = Number(elements.periodFrom.value.slice(0, 4));
  if (!year || elements.periodFrom.value.slice(0, 4) !== elements.periodTo.value.slice(0, 4)) {
    elements.periodSelect.value = "last-year";
    return;
  }
  const option = [...elements.periodSelect.options].find((entry) => entry.value === String(year));
  elements.periodSelect.value = option ? option.value : "last-year";
}

async function connectGithub(event) {
  event.preventDefault();
  clearFieldError(elements.tokenError);
  const token = elements.githubToken.value.trim();
  if (!token) {
    setFieldError(elements.tokenError, "Cole seu token do GitHub para continuar.");
    elements.githubToken.focus();
    return;
  }

  setButtonLoading(elements.connectButton, true);
  clearCalendarFeedback();
  try {
    const response = await fetch(API_USER_URL, {
      method: "GET",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28"
      }
    });
    if (!response.ok) {
      if (response.status === 401) throw new Error("invalid-token");
      if (response.status === 403 || response.status === 429) throw new Error("rate-limit");
      throw new Error("github-unavailable");
    }
    const profile = await response.json();
    if (!profile || typeof profile.login !== "string" || !profile.login) {
      throw new Error("invalid-profile");
    }
    githubToken = token;
    githubUser = {
      login: profile.login,
      name: typeof profile.name === "string" && profile.name.trim()
        ? profile.name
        : profile.login,
      avatarUrl: safeAvatarUrl(profile.avatar_url)
    };
    elements.githubToken.value = "";
    renderConnectedUser();
    await loadContributions();
  } catch (error) {
    setFieldError(elements.tokenError, githubErrorMessage(error));
  } finally {
    setButtonLoading(elements.connectButton, false);
  }
}

function renderConnectedUser() {
  elements.connectForm.hidden = true;
  elements.connectedUser.hidden = false;
  elements.userName.textContent = githubUser.name;
  elements.userLogin.textContent = `@${githubUser.login}`;
  elements.userAvatar.src = githubUser.avatarUrl || "";
  elements.userAvatar.alt = `Avatar de ${githubUser.name}`;
  elements.loadCalendar.disabled = false;
  elements.calendarSubtitle.textContent = `Conectado como @${githubUser.login}`;
  elements.calendarState.hidden = true;
}

function disconnectGithub() {
  githubToken = null;
  githubUser = null;
  currentDays = [];
  elements.githubToken.value = "";
  elements.userAvatar.removeAttribute("src");
  elements.userAvatar.alt = "";
  elements.connectForm.hidden = false;
  elements.connectedUser.hidden = true;
  elements.loadCalendar.disabled = true;
  elements.calendarSubtitle.textContent = "Conecte uma conta para começar.";
  elements.heatmap.replaceChildren();
  elements.monthLabels.replaceChildren();
  elements.heatmapScroll.hidden = true;
  elements.calendarSkeleton.hidden = true;
  elements.calendarState.hidden = false;
  elements.calendarState.classList.remove("error");
  elements.calendarState.replaceChildren();
  const message = document.createElement("p");
  message.textContent = "Conecte sua conta do GitHub para carregar suas contribuições.";
  elements.calendarState.append(message);
  elements.statTotal.textContent = "—";
  elements.statCurrent.textContent = "—";
  elements.statLongest.textContent = "—";
  clearCalendarFeedback();
  clearFieldError(elements.tokenError);
}

function safeAvatarUrl(value) {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "avatars.githubusercontent.com"
      ? url.href
      : "";
  } catch {
    return "";
  }
}

async function loadContributions() {
  if (!githubToken || !githubUser) return;
  const period = getSelectedPeriod();
  if (!period) return;

  setCalendarLoading(true);
  try {
    const response = await fetch(API_GRAPHQL_URL, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${githubToken}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28"
      },
      body: JSON.stringify({
        query: CONTRIBUTIONS_QUERY,
        variables: {
          login: githubUser.login,
          from: `${period.from}T00:00:00Z`,
          to: `${period.to}T23:59:59Z`
        }
      })
    });
    if (!response.ok) {
      if (response.status === 401) throw new Error("invalid-token");
      if (response.status === 403 || response.status === 429) throw new Error("rate-limit");
      throw new Error("github-unavailable");
    }
    const payload = await response.json();
    if (Array.isArray(payload.errors) && payload.errors.length) {
      const rateLimited = payload.errors.some((entry) =>
        entry?.extensions?.code === "RATE_LIMITED"
      );
      const unauthorized = payload.errors.some((entry) =>
        ["UNAUTHENTICATED", "FORBIDDEN"].includes(entry?.extensions?.code)
      );
      if (rateLimited) throw new Error("rate-limit");
      if (unauthorized) throw new Error("invalid-token");
      throw new Error("contributions-unavailable");
    }
    const user = payload?.data?.user;
    const calendar = user?.contributionsCollection?.contributionCalendar;
    if (!user || !calendar || !Array.isArray(calendar.weeks)) {
      throw new Error("contributions-unavailable");
    }
    currentDays = calendar.weeks.flatMap((week) => week.contributionDays || []);
    const stats = calculateStatistics(currentDays, Number(calendar.totalContributions) || 0);
    renderStatistics(stats);
    elements.calendarSubtitle.textContent = `${formatDate(period.from)} – ${formatDate(period.to)}`;
    renderCalendar(currentDays);
    elements.calendarFeedback.textContent = "";
    if (stats.total === 0) {
      showCalendarState("Nenhuma contribuição foi encontrada neste período.", false);
    } else {
      elements.calendarState.hidden = true;
    }
  } catch (error) {
    if (error.message === "invalid-token") {
      disconnectGithub();
      setFieldError(elements.tokenError, githubErrorMessage(error));
      showToast("Sua conexão expirou. Conecte-se novamente para continuar.", "error");
    } else {
      showCalendarState(githubErrorMessage(error), true);
    }
  } finally {
    setCalendarLoading(false);
  }
}

function getSelectedPeriod() {
  const startText = elements.periodFrom.value;
  const endText = elements.periodTo.value;
  const start = parseDateInput(startText);
  const end = parseDateInput(endText);
  if (!start || !end) {
    showCalendarState("Informe datas válidas para consultar o calendário.", true);
    return null;
  }
  if (end < start) {
    showCalendarState("A data final precisa ser igual ou posterior à data inicial.", true);
    return null;
  }
  if ((end.getTime() - start.getTime()) / 86400000 > 365) {
    showCalendarState("Escolha um período de no máximo um ano.", true);
    return null;
  }
  return { from: startText, to: endText };
}

function calculateStatistics(days, totalFromApi) {
  const counts = new Map();
  for (const day of days) {
    if (typeof day?.date !== "string") continue;
    const count = Number(day.contributionCount);
    if (!Number.isFinite(count) || count < 0) continue;
    counts.set(day.date, count);
  }
  const activeDates = [...counts.entries()]
    .filter(([, count]) => count > 0)
    .map(([date]) => date)
    .sort();

  let longest = 0;
  let streak = 0;
  let previous = null;
  for (const date of activeDates) {
    const current = parseDateInput(date);
    const previousDate = previous ? parseDateInput(previous) : null;
    streak = previousDate && current - previousDate === 86400000 ? streak + 1 : 1;
    longest = Math.max(longest, streak);
    previous = date;
  }

  const today = formatDateInput(new Date());
  const yesterdayDate = new Date();
  yesterdayDate.setDate(yesterdayDate.getDate() - 1);
  const yesterday = formatDateInput(yesterdayDate);
  let currentStreak = 0;
  let anchor = counts.get(today) > 0 ? today : counts.get(yesterday) > 0 ? yesterday : null;
  while (anchor && counts.get(anchor) > 0) {
    currentStreak += 1;
    const dayBefore = parseDateInput(anchor);
    dayBefore.setUTCDate(dayBefore.getUTCDate() - 1);
    anchor = formatDateUTC(dayBefore);
  }

  const total = Number.isFinite(totalFromApi)
    ? totalFromApi
    : [...counts.values()].reduce((sum, value) => sum + value, 0);
  return { total, currentStreak, longest };
}

function renderStatistics(stats) {
  elements.statTotal.textContent = new Intl.NumberFormat("pt-BR").format(stats.total);
  elements.statCurrent.textContent = `${stats.currentStreak} ${stats.currentStreak === 1 ? "dia" : "dias"}`;
  elements.statLongest.textContent = `${stats.longest} ${stats.longest === 1 ? "dia" : "dias"}`;
}

function renderCalendar(days) {
  const daily = new Map();
  for (const day of days) {
    if (typeof day?.date === "string") daily.set(day.date, day);
  }
  const today = formatDateInput(new Date());
  const dates = [...daily.keys()].filter((date) => date <= today).sort();
  elements.heatmap.replaceChildren();
  elements.monthLabels.replaceChildren();
  if (!dates.length) {
    elements.heatmapScroll.hidden = true;
    return;
  }

  const firstDate = parseDateInput(dates[0]);
  const firstWeek = new Date(firstDate);
  firstWeek.setUTCDate(firstWeek.getUTCDate() - firstWeek.getUTCDay());
  const lastDate = parseDateInput(dates[dates.length - 1]);
  const lastWeek = new Date(lastDate);
  lastWeek.setUTCDate(lastWeek.getUTCDate() - lastWeek.getUTCDay());
  const weekCount = Math.floor((lastWeek - firstWeek) / 604800000) + 1;
  const monthByWeek = new Map();
  let previousMonth = "";
  for (const dateText of dates) {
    const date = parseDateInput(dateText);
    const monthKey = `${date.getUTCFullYear()}-${date.getUTCMonth()}`;
    if (monthKey === previousMonth) continue;
    previousMonth = monthKey;
    const weekIndex = Math.floor((date - firstWeek) / 604800000);
    const monthLabel = new Intl.DateTimeFormat("pt-BR", {
      month: "short",
      timeZone: "UTC"
    }).format(date).replace(/\.$/, "");
    const labels = monthByWeek.get(weekIndex) || [];
    labels.push(monthLabel);
    monthByWeek.set(weekIndex, labels);
  }
  elements.heatmap.closest(".calendar-plot").style.setProperty("--week-count", weekCount);
  for (let weekIndex = 0; weekIndex < weekCount; weekIndex += 1) {
    const labels = monthByWeek.get(weekIndex);
    if (!labels) continue;
    const label = document.createElement("span");
    label.className = "month-label";
    label.style.gridColumn = String(weekIndex + 1);
    label.textContent = labels.join("/");
    label.title = labels.join(" / ");
    elements.monthLabels.append(label);
  }

  const maxCount = Math.max(1, ...days.map((day) => Number(day.contributionCount) || 0));
  for (let weekIndex = 0; weekIndex < weekCount; weekIndex += 1) {
    const week = document.createElement("div");
    week.className = "week-column";
    const weekStart = new Date(firstWeek);
    weekStart.setUTCDate(weekStart.getUTCDate() + weekIndex * 7);
    for (let weekday = 0; weekday < 7; weekday += 1) {
      const dayDate = new Date(weekStart);
      dayDate.setUTCDate(dayDate.getUTCDate() + weekday);
      const dateText = formatDateUTC(dayDate);
      if (dateText > today) break;
      const data = daily.get(dateText);
      const count = data ? Number(data.contributionCount) || 0 : 0;
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = `day-cell ${getHeatLevel(count, maxCount)}`;
      cell.setAttribute("role", "listitem");
      cell.setAttribute("aria-label", `${formatDate(dateText)}: ${count} ${count === 1 ? "contribuição" : "contribuições"}`);
      cell.title = `${formatDate(dateText)} · ${count} ${count === 1 ? "contribuição" : "contribuições"}`;
      const apiColor = data?.color;
      if (count > 0 && typeof apiColor === "string" && /^#[\da-f]{6}$/i.test(apiColor)) {
        cell.style.backgroundColor = apiColor;
      }
      week.append(cell);
    }
    elements.heatmap.append(week);
  }
  elements.heatmapScroll.hidden = false;
  fitCalendarGrid();
}

function fitCalendarGrid() {
  const weekCount = elements.heatmap?.children.length || 0;
  const availableWidth = elements.heatmap?.clientWidth || 0;
  if (!weekCount || !availableWidth) return;

  const gap = Math.min(4, Math.max(1, availableWidth / (weekCount * 6)));
  const cellSize = (availableWidth - (weekCount - 1) * gap) / weekCount;
  const plot = elements.heatmap.closest(".calendar-plot");
  plot.style.setProperty("--heatmap-cell-size", `${cellSize}px`);
  plot.style.setProperty("--heatmap-gap", `${gap}px`);
}

function getHeatLevel(count, max) {
  if (count <= 0) return "level-0";
  const ratio = count / max;
  if (ratio <= 0.25) return "level-1";
  if (ratio <= 0.5) return "level-2";
  if (ratio <= 0.75) return "level-3";
  return "level-4";
}

function setCalendarLoading(loading) {
  elements.calendarSkeleton.hidden = !loading;
  elements.calendarState.hidden = loading;
  elements.heatmapScroll.hidden = loading;
  setButtonLoading(elements.loadCalendar, loading);
  elements.loadCalendar.disabled = loading || !githubToken;
}

function showCalendarState(message, isError, canRetry = true) {
  elements.calendarSkeleton.hidden = true;
  elements.heatmapScroll.hidden = true;
  elements.calendarState.hidden = false;
  elements.calendarState.classList.toggle("error", isError);
  elements.calendarState.replaceChildren();
  const text = document.createElement("p");
  text.textContent = message;
  elements.calendarState.append(text);
  if (canRetry && githubToken) {
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "button button-secondary";
    retry.textContent = "Tentar novamente";
    retry.addEventListener("click", loadContributions);
    elements.calendarState.append(retry);
  }
}

function githubErrorMessage(error) {
  switch (error?.message) {
    case "invalid-token":
      return "Token inválido ou expirado. Confira o token e tente novamente.";
    case "rate-limit":
      return "O GitHub limitou temporariamente as consultas. Aguarde um pouco e tente novamente.";
    case "invalid-profile":
      return "Não foi possível identificar a conta deste token.";
    case "contributions-unavailable":
      return "Não foi possível carregar as contribuições desta conta. Tente novamente.";
    default:
      return "Sem conexão com o GitHub. Confira sua internet e tente novamente.";
  }
}

function setFieldError(element, message) {
  element.textContent = message;
}

function clearFieldError(element) {
  element.textContent = "";
}

function setButtonLoading(button, loading) {
  button.classList.toggle("is-loading", loading);
  button.disabled = loading;
}

function showToast(message, type) {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function clearCalendarFeedback() {
  elements.calendarFeedback.textContent = "";
}

function parseDateInput(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null;
  }
  return date;
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateUTC(date) {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDate(value) {
  const date = parseDateInput(value);
  return date
    ? new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(date)
    : value;
}
