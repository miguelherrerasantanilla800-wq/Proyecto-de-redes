const API = "";
const TOKEN_KEY = "mnm_token";
const ROLE_KEY = "mnm_role";
const PAGE_SIZE = 10;
const CURRENCY = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const DATE_FORMAT = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const loginView = document.querySelector("#login-view");
const dashboardView = document.querySelector("#dashboard-view");
const pageContent = document.querySelector("#page-content");
const toast = document.querySelector("#toast");
let currentRole = localStorage.getItem(ROLE_KEY);
let currentUser = null;
let activePage = "resumen";
let transactionPage = 1;
let alertPage = 1;
let activeCharts = [];
let toastTimer;

const pageLabels = {
  resumen: "Resumen",
  movimientos: "Movimientos",
  alertas: "Alertas",
  transferir: "Transferir dinero",
};

function formatMoney(amount) {
  return CURRENCY.format(Number(amount || 0));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

async function api(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401 && token) {
    logout("Tu sesión terminó. Ingresa de nuevo.");
    throw new Error("Sesión vencida");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || "No fue posible completar la solicitud.");
  }
  return body;
}

function showToast(message, isError = false) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.hidden = false;
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 3800);
}

function setLoginError(message = "") {
  const error = document.querySelector("#login-error");
  error.textContent = message;
  error.hidden = !message;
}

function setBusy(button, busy) {
  button.disabled = busy;
  button.textContent = busy ? "Validando..." : "Entrar →";
}

function showDashboard(user) {
  currentUser = user;
  currentRole = user.rol;
  localStorage.setItem(ROLE_KEY, currentRole);
  loginView.hidden = true;
  dashboardView.hidden = false;
  const name = user.email.split("@")[0].replace(/[._-]/g, " ");
  const firstName = name.split(" ")[0];
  document.querySelector("#profile-name").textContent = name.replace(/\b\w/g, (letter) => letter.toUpperCase());
  document.querySelector("#profile-role").textContent = currentRole === "analista" ? "Analista financiero" : "Cliente MNM";
  document.querySelector("#profile-avatar").textContent = firstName.charAt(0).toUpperCase();
  document.querySelector("#topbar-avatar").textContent = firstName.charAt(0).toUpperCase();
  document.querySelector("#today-label").textContent = new Intl.DateTimeFormat("es-CO", {
    weekday: "short", day: "numeric", month: "short",
  }).format(new Date());
  renderNavigation();
  navigate("resumen");
}

function showLogin(message = "") {
  dashboardView.hidden = true;
  loginView.hidden = false;
  currentUser = null;
  setLoginError(message);
  document.querySelector("#password").value = "";
}

function logout(message = "") {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
  currentRole = null;
  currentUser = null;
  destroyCharts();
  showLogin();
  if (message) showToast(message);
}

function renderNavigation() {
  const links = currentRole === "analista"
    ? [{ id: "resumen", icon: "▦", label: "Resumen" }, { id: "alertas", icon: "⚑", label: "Alertas" }]
    : [{ id: "resumen", icon: "▦", label: "Resumen" }, { id: "movimientos", icon: "⇄", label: "Movimientos" }, { id: "transferir", icon: "⇢", label: "Transferir" }];
  document.querySelector("#main-nav").innerHTML = links.map((link) => `
    <button class="nav-link" type="button" data-page="${link.id}" aria-current="false">
      <span class="nav-icon" aria-hidden="true">${link.icon}</span><span>${link.label}</span>
    </button>`).join("");
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.page));
  });
}

function destroyCharts() {
  activeCharts.forEach((chart) => chart.destroy());
  activeCharts = [];
}

function navigate(page) {
  const allowed = currentRole === "analista" ? ["resumen", "alertas"] : ["resumen", "movimientos", "transferir"];
  if (!allowed.includes(page)) return;
  activePage = page;
  document.querySelector("#current-section").textContent = pageLabels[page];
  document.querySelectorAll(".nav-link").forEach((button) => {
    const selected = button.dataset.page === page;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-current", selected ? "page" : "false");
  });
  destroyCharts();
  pageContent.innerHTML = '<div class="loading-state">Cargando información...</div>';
  pageContent.focus({ preventScroll: true });
  const loaders = {
    resumen: currentRole === "analista" ? renderAnalystDashboard : renderClientDashboard,
    movimientos: renderTransactions,
    alertas: renderAlerts,
    transferir: renderTransfers,
  };
  loaders[page]().catch(handlePageError);
}

function handlePageError(error) {
  pageContent.innerHTML = `<div class="panel empty-state">${escapeHtml(error.message || "No se pudo cargar la información.")}</div>`;
}

function pageHeading(kicker, title, subtitle, action = "") {
  return `<div class="page-heading"><div><p class="eyebrow">${kicker}</p><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;
}

function metricCard(label, value, icon, foot, accent = false) {
  return `<article class="metric${accent ? " accent" : ""}">
    <div class="metric-top"><span>${label}</span><span class="metric-icon" aria-hidden="true">${icon}</span></div>
    <strong>${value}</strong><div class="metric-foot">${foot}</div>
  </article>`;
}

function chartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { display: false },
      tooltip: { backgroundColor: "#123b34", padding: 11, titleFont: { family: "DM Sans" }, bodyFont: { family: "DM Sans" }, callbacks: { label: (item) => `${item.dataset.label}: ${formatMoney(item.raw)}` } },
    },
    scales: {
      x: { grid: { display: false }, border: { display: false }, ticks: { color: "#849088", font: { family: "DM Sans", size: 9 } } },
      y: { beginAtZero: true, border: { display: false }, grid: { color: "#edf0ed" }, ticks: { color: "#849088", font: { family: "DM Sans", size: 9 }, callback: (value) => new Intl.NumberFormat("es-CO", { notation: "compact", maximumFractionDigits: 1 }).format(value) } },
    },
  };
}

async function renderClientDashboard() {
  const [summary, monthly, categories, transactions] = await Promise.all([
    api("/api/cliente/resumen"),
    api("/api/cliente/mensual"),
    api("/api/cliente/categorias"),
    api(`/api/cliente/transacciones?pagina=1&por_pagina=${PAGE_SIZE}`),
  ]);
  pageContent.innerHTML = `${pageHeading("TU PANORAMA FINANCIERO", `Hola, ${escapeHtml(currentUser.email.split("@")[0])}`, "Aquí tienes el estado de tu cuenta y tus movimientos recientes.", '<span class="heading-date">Actualizado ahora</span>')}
    <section class="metrics-grid" aria-label="Resumen de cuenta">
      ${metricCard("Saldo disponible", formatMoney(summary.saldo), "◉", "Saldo de tu último movimiento", true)}
      ${metricCard("Ingresos acumulados", formatMoney(summary.ingresos), "↙", "Total de créditos registrados")}
      ${metricCard("Egresos acumulados", formatMoney(summary.egresos), "↗", "Total de débitos registrados")}
    </section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Ingresos y egresos</h2><p class="panel-subtitle">Comparativo mensual de tu actividad</p></div><span class="panel-period">Por mes</span></div>
        <div class="chart-wrap"><canvas id="monthly-chart" aria-label="Gráfico de ingresos y egresos mensuales"></canvas></div>
        <div class="legend-row"><span class="legend-key"><i class="legend-swatch"></i>Ingresos</span><span class="legend-key"><i class="legend-swatch coral"></i>Egresos</span></div>
      </article>
      <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Gastos por categoría</h2><p class="panel-subtitle">Distribución de tus débitos</p></div></div>
        <div class="chart-wrap small-chart"><canvas id="category-chart" aria-label="Gráfico de gastos por categoría"></canvas></div>
      </article>
    </section>
    ${recentTransactionsSection(transactions.items)}`;
  const labels = monthly.map((item) => monthLabel(item.mes));
  activeCharts.push(new Chart(document.querySelector("#monthly-chart"), {
    type: "bar",
    data: { labels, datasets: [
      { label: "Ingresos", data: monthly.map((item) => item.ingresos), backgroundColor: "#27745e", borderRadius: 3, maxBarThickness: 19 },
      { label: "Egresos", data: monthly.map((item) => item.egresos), backgroundColor: "#d97962", borderRadius: 3, maxBarThickness: 19 },
    ] }, options: { ...chartOptions(), scales: { ...chartOptions().scales, x: { ...chartOptions().scales.x, stacked: false } } },
  }));
  activeCharts.push(new Chart(document.querySelector("#category-chart"), {
    type: "doughnut",
    data: { labels: categories.map((item) => item.categoria), datasets: [{ data: categories.map((item) => item.monto), backgroundColor: ["#27745e", "#d97962", "#d6eb8a", "#497b94", "#e9b765", "#85aaa0"], borderWidth: 2, borderColor: "#fff", hoverOffset: 5 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: "69%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 7, padding: 12, color: "#77817c", font: { family: "DM Sans", size: 9 } } }, tooltip: { callbacks: { label: (item) => `${item.label}: ${formatMoney(item.raw)}` } } } },
  }));
  document.querySelector("#see-transactions").addEventListener("click", () => navigate("movimientos"));
}

async function renderAnalystDashboard() {
  const [summary, monthly, alerts] = await Promise.all([
    api("/api/global/resumen"),
    api("/api/global/mensual"),
    api("/api/global/alertas?pagina=1&por_pagina=5"),
  ]);
  pageContent.innerHTML = `${pageHeading("VISTA CONSOLIDADA", "Actividad del banco", "Indicadores globales y movimientos que requieren atención.", '<span class="heading-date">Actualizado ahora</span>')}
    <section class="metrics-grid" aria-label="Indicadores del banco">
      ${metricCard("Transacciones registradas", Number(summary.total_transacciones).toLocaleString("es-CO"), "⇄", "Movimientos en todas las cuentas")}
      ${metricCard("Monto total procesado", formatMoney(summary.monto_total), "◈", "Suma de los montos registrados", true)}
      ${metricCard("Alertas por revisar", Number(alerts.total).toLocaleString("es-CO"), "⚑", `Umbral actual: ${formatMoney(alerts.umbral)}`)}
    </section>
    <section class="dashboard-grid">
      <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Volumen mensual</h2><p class="panel-subtitle">Transacciones y monto procesado</p></div><span class="panel-period">Por mes</span></div>
        <div class="chart-wrap"><canvas id="global-monthly-chart" aria-label="Gráfico de actividad mensual del banco"></canvas></div>
        <div class="legend-row"><span class="legend-key"><i class="legend-swatch"></i>Monto procesado</span></div>
      </article>
      <article class="panel"><div class="panel-header"><div><h2 class="panel-title">Atención prioritaria</h2><p class="panel-subtitle">Mayores montos sobre el umbral</p></div></div>
        <div class="mini-alerts">${alerts.items.length ? alerts.items.slice(0, 4).map((item) => `<div class="mini-alert"><span class="alert-mark">!</span><span class="mini-alert-copy"><strong>${formatMoney(item.monto)}</strong><small>Cuenta ${escapeHtml(item.id_cuenta)} · ${escapeHtml(item.categoria)}</small></span></div>`).join("") : '<div class="empty-state">No hay alertas para mostrar.</div>'}</div>
        <div class="mini-alert-footer"><button id="see-alerts" class="text-link" type="button">Ver todas las alertas →</button></div>
      </article>
    </section>
    <div class="section-row"><div><h2>Transacciones recientes</h2><p>Últimos registros de todas las cuentas</p></div></div>
    <section class="table-panel"><div class="table-scroll">${transactionsTable(alerts.items, true)}</div></section>`;
  activeCharts.push(new Chart(document.querySelector("#global-monthly-chart"), {
    type: "bar",
    data: { labels: monthly.map((item) => monthLabel(item.mes)), datasets: [{ label: "Monto", data: monthly.map((item) => item.monto), backgroundColor: "#27745e", borderRadius: 3, maxBarThickness: 28, yAxisID: "y" }] },
    options: chartOptions(),
  }));
  document.querySelector("#see-alerts").addEventListener("click", () => navigate("alertas"));
}

function recentTransactionsSection(items) {
  return `<div class="section-row"><div><h2>Movimientos recientes</h2><p>Actividad más reciente de tu cuenta</p></div><button id="see-transactions" class="text-link" type="button">Ver todos →</button></div>
    <section class="table-panel"><div class="table-scroll">${transactionsTable(items, false)}</div></section>`;
}

function transactionsTable(items, showAccount) {
  if (!items?.length) return '<div class="empty-state">No hay movimientos para mostrar.</div>';
  return `<table class="data-table"><thead><tr><th>Fecha</th>${showAccount ? "<th>Cuenta</th>" : ""}<th>Descripción</th><th>Categoría</th><th>Tipo</th><th>Monto</th></tr></thead><tbody>${items.map((item) => `<tr>
    <td>${formatDate(item.fecha)}</td>${showAccount ? `<td>${escapeHtml(item.id_cuenta)}</td>` : ""}<td>${escapeHtml(item.operacion)}</td><td>${escapeHtml(item.categoria)}</td>
    <td><span class="type-pill ${item.tipo === "debito" ? "debit" : ""}">${item.tipo === "debito" ? "↗ Débito" : "↙ Crédito"}</span></td><td class="amount">${formatMoney(item.monto)}</td>
  </tr>`).join("")}</tbody></table>`;
}

async function renderTransactions() {
  const params = new URLSearchParams({ pagina: String(transactionPage), por_pagina: String(PAGE_SIZE) });
  const desde = document.querySelector("#filter-from")?.value;
  const hasta = document.querySelector("#filter-to")?.value;
  const tipo = document.querySelector("#filter-type")?.value;
  if (desde) params.set("desde", desde);
  if (hasta) params.set("hasta", hasta);
  if (tipo) params.set("tipo", tipo);
  const data = await api(`/api/cliente/transacciones?${params}`);
  pageContent.innerHTML = `${pageHeading("TU ACTIVIDAD", "Movimientos", "Consulta y filtra las transacciones de tu cuenta.")}
    <section class="table-panel">
      <form id="transaction-filters" class="table-tools">
        <div class="filter-field"><label for="filter-from">Desde</label><input class="filter-control" id="filter-from" type="date" value="${escapeHtml(desde || "")}"></div>
        <div class="filter-field"><label for="filter-to">Hasta</label><input class="filter-control" id="filter-to" type="date" value="${escapeHtml(hasta || "")}"></div>
        <div class="filter-field"><label for="filter-type">Tipo de movimiento</label><select class="filter-control" id="filter-type"><option value="">Todos</option><option value="credito" ${tipo === "credito" ? "selected" : ""}>Créditos</option><option value="debito" ${tipo === "debito" ? "selected" : ""}>Débitos</option></select></div>
        <div class="filter-actions"><button class="button button-primary button-compact" type="submit">Filtrar</button><button class="button button-secondary button-compact" id="clear-filters" type="button">Limpiar</button></div>
      </form>
      <div class="table-scroll">${transactionsTable(data.items, false)}</div>
      ${paginationFooter(data, "transactions")}
    </section>`;
  document.querySelector("#transaction-filters").addEventListener("submit", (event) => {
    event.preventDefault();
    transactionPage = 1;
    renderTransactions().catch(handlePageError);
  });
  document.querySelector("#clear-filters").addEventListener("click", () => {
    transactionPage = 1;
    renderTransactions().catch(handlePageError);
  });
  bindPagination("transactions", data);
}

async function renderTransfers() {
  const recipients = await api("/api/cliente/destinatarios");
  pageContent.innerHTML = `${pageHeading("PAGOS ENTRE CLIENTES", "Enviar dinero", "Transfiere desde tu cuenta a otro cliente Banco MNM.")}
    <section class="panel transfer-panel">
      <div class="panel-header"><div><h2 class="panel-title">Nueva transferencia</h2><p class="panel-subtitle">El dinero se descuenta y acredita al confirmar.</p></div></div>
      <form id="transfer-form" class="transfer-form">
        <div class="transfer-field"><label for="transfer-recipient">Usuario destinatario</label><select id="transfer-recipient" class="filter-control" name="destinatario" required ${recipients.length ? "" : "disabled"}><option value="" selected disabled>Selecciona un usuario</option>${recipients.map((item) => `<option value="${escapeHtml(item.usuario)}">${escapeHtml(item.usuario)}</option>`).join("")}</select></div>
        <div class="transfer-field"><label for="transfer-amount">Importe (COP)</label><input id="transfer-amount" class="filter-control" name="monto" type="number" min="0.01" step="0.01" inputmode="decimal" placeholder="0,00" required></div>
        <button class="button button-primary transfer-submit" type="submit" ${recipients.length ? "" : "disabled"}>Enviar transferencia <span aria-hidden="true">→</span></button>
      </form>
      <p class="transfer-note">Solo puedes transferir el saldo disponible de tu cuenta. El destinatario verá el abono en sus movimientos.</p>
      ${recipients.length ? "" : '<p class="empty-state">No hay otros usuarios disponibles para recibir transferencias.</p>'}
    </section>`;

  const form = document.querySelector("#transfer-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Enviando...";
    const formData = new FormData(form);
    try {
      const result = await api("/api/cliente/transferencias", {
        method: "POST",
        body: JSON.stringify({
          destinatario: formData.get("destinatario"),
          monto: formData.get("monto"),
        }),
      });
      showToast(`Transferencia enviada a ${result.destinatario}: ${formatMoney(result.monto)}`);
      form.reset();
    } catch (error) {
      showToast(error.message, true);
    } finally {
      button.disabled = false;
      button.innerHTML = 'Enviar transferencia <span aria-hidden="true">→</span>';
    }
  });
}

async function renderAlerts() {
  const data = await api(`/api/global/alertas?pagina=${alertPage}&por_pagina=${PAGE_SIZE}`);
  pageContent.innerHTML = `${pageHeading("MONITOREO", "Alertas inusuales", "Movimientos por encima del umbral, ordenados por monto.", `<span class="heading-date">Umbral · ${formatMoney(data.umbral)}</span>`)}
    <section class="table-panel">
      <div class="panel-header"><div><h2 class="panel-title">Transacciones para revisión</h2><p class="panel-subtitle">${Number(data.total).toLocaleString("es-CO")} registros detectados</p></div><span class="type-pill neutral">⚑ Revisión manual</span></div>
      <div class="table-scroll">${data.items.length ? `<table class="data-table"><thead><tr><th>Fecha</th><th>Cuenta</th><th>Operación</th><th>Categoría</th><th>Tipo</th><th>Monto</th></tr></thead><tbody>${data.items.map((item) => `<tr><td>${formatDate(item.fecha)}</td><td>${escapeHtml(item.id_cuenta)}</td><td>${escapeHtml(item.operacion)}</td><td>${escapeHtml(item.categoria)}</td><td><span class="type-pill ${item.tipo === "debito" ? "debit" : ""}">${item.tipo === "debito" ? "↗ Débito" : "↙ Crédito"}</span></td><td class="amount">${formatMoney(item.monto)}</td></tr>`).join("")}</tbody></table>` : '<div class="empty-state">No hay transacciones sobre el umbral actual.</div>'}</div>
      ${paginationFooter(data, "alerts")}
    </section>`;
  bindPagination("alerts", data);
}

function paginationFooter(data, kind) {
  const first = data.total ? ((data.pagina - 1) * data.por_pagina) + 1 : 0;
  const last = Math.min(data.pagina * data.por_pagina, data.total);
  return `<div class="table-footer"><span>Mostrando ${first}–${last} de ${Number(data.total).toLocaleString("es-CO")}</span><div class="pagination"><button type="button" data-page-step="-1" data-kind="${kind}" aria-label="Página anterior" ${data.pagina <= 1 ? "disabled" : ""}>‹</button><button type="button" data-page-step="1" data-kind="${kind}" aria-label="Página siguiente" ${last >= data.total ? "disabled" : ""}>›</button></div></div>`;
}

function bindPagination(kind, data) {
  document.querySelectorAll(`[data-kind="${kind}"]`).forEach((button) => {
    button.addEventListener("click", () => {
      if (kind === "transactions") transactionPage = data.pagina + Number(button.dataset.pageStep);
      else alertPage = data.pagina + Number(button.dataset.pageStep);
      navigate(kind === "transactions" ? "movimientos" : "alertas");
    });
  });
}

function monthLabel(value) {
  const [year, month] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("es-CO", { month: "short", year: "2-digit" }).format(new Date(year, month - 1, 1));
}

function formatDate(value) {
  return DATE_FORMAT.format(new Date(`${value}T12:00:00`));
}

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#login-submit");
  setLoginError();
  setBusy(button, true);
  const form = new FormData(event.currentTarget);
  try {
    const result = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    const body = await result.json().catch(() => ({}));
    if (!result.ok) throw new Error(body.detail || "No fue posible iniciar sesión.");
    localStorage.setItem(TOKEN_KEY, body.token);
    localStorage.setItem(ROLE_KEY, body.rol);
    const user = await api("/api/auth/me");
    showDashboard(user);
  } catch (error) {
    setLoginError(error.message === "Failed to fetch" ? "No se pudo conectar con Banco MNM. Verifica que los servicios estén activos." : error.message);
  } finally {
    setBusy(button, false);
  }
});

document.querySelector("#logout-button").addEventListener("click", () => logout());

async function restoreSession() {
  if (!localStorage.getItem(TOKEN_KEY)) return;
  try {
    const user = await api("/api/auth/me");
    showDashboard(user);
  } catch {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    showLogin();
  }
}

document.addEventListener("DOMContentLoaded", restoreSession);