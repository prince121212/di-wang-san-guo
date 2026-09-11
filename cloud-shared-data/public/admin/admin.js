"use strict";

const state = {
  username: "",
  overview: null,
  selectedServerKey: "",
  mapKind: "bandit",
  mapData: null,
  filteredTargets: [],
  zoom: 1,
  pointElements: new Map(),
  refreshTimer: null,
  toastTimer: null,
  expandedPlatforms: new Set(),
};

const STATUS_LABELS = {
  available: "可用",
  reserved: "已预占",
  dispatching: "出征中",
  dispatched: "已出征",
  rejected: "已拒绝",
  missing: "已消失",
  uncertain: "待确认",
};
const BANDIT_COLORS = ["#82909a", "#5c9bd3", "#29a36a", "#d2a32f", "#d87932", "#d64d58"];
const MINE_COLORS = {
  "镌铁矿": "#636f7a", "水晶矿": "#44a9c5", "玄铁矿": "#343b45",
  "浆果园": "#b94d65", "灵草园": "#3f9d5f", "玉露园": "#7c62c5",
  "银矿": "#9aa7b1", "一级牧场": "#c59448", "二级牧场": "#ad762f",
  "三级牧场": "#875522",
};
const MAP_WIDTH = 2412;
const MAP_PADDING = 90;
const MAP_UNIT = 12;

function byId(id) { return document.getElementById(id); }
function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
function fmtNumber(value) { return new Intl.NumberFormat("zh-CN").format(Number(value || 0)); }
function fmtTime(value) {
  const timestamp = Number(value || 0);
  return timestamp ? new Date(timestamp).toLocaleString("zh-CN", { hour12: false }) : "未知";
}
function relativeTime(value, now = Date.now()) {
  const timestamp = Number(value || 0);
  if (!timestamp) return "未知";
  const seconds = Math.max(0, Math.floor((now - timestamp) / 1000));
  if (seconds < 5) return "刚刚";
  if (seconds < 60) return `${seconds}秒前`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  return fmtTime(timestamp);
}
function duration(value) {
  const milliseconds = Math.max(0, Number(value || 0));
  const minutes = Math.floor(milliseconds / 60000);
  if (minutes >= 60) return `${Math.floor(minutes / 60)}小时${minutes % 60}分`;
  if (minutes > 0) return `${minutes}分钟`;
  return `${Math.max(0, Math.ceil(milliseconds / 1000))}秒`;
}
function serverIdentity(server) { return `${server.platformKey}\u001f${server.serverKey}`; }
function platformName(server) { return String(server.platformName || server.platformKey || "未知平台"); }
function selectedServer() {
  return (state.overview?.servers || []).find(server => serverIdentity(server) === state.selectedServerKey) || null;
}
function svg(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body ? { "content-type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  let payload;
  try { payload = await response.json(); } catch { payload = { ok: false, error: "服务响应不是有效JSON" }; }
  if (response.status === 401 && path !== "/admin/api/login") {
    showLogin();
    throw new Error(payload.error || "登录已过期");
  }
  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.error || `请求失败（${response.status}）`);
    error.code = payload.code || "";
    error.retryAfterMillis = payload.retryAfterMillis || 0;
    throw error;
  }
  return payload;
}

function showToast(message, type = "success") {
  const toast = byId("toast");
  toast.textContent = String(message || "");
  toast.className = `toast${type === "error" ? " error" : ""}`;
  toast.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { toast.hidden = true; }, 3200);
}

function showLogin() {
  byId("dashboardView").hidden = true;
  byId("loginView").hidden = false;
  clearInterval(state.refreshTimer);
  state.refreshTimer = null;
  setTimeout(() => byId("username").focus(), 0);
}

async function showDashboard(username) {
  state.username = username;
  byId("adminName").textContent = username || "管理员";
  byId("loginView").hidden = true;
  byId("dashboardView").hidden = false;
  await loadOverview({ selectFirst: true });
  clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(() => {
    if (!document.hidden) loadOverview({ quiet: true }).catch(() => {});
  }, 30000);
}

async function handleLogin(event) {
  event.preventDefault();
  const button = byId("loginButton");
  const errorBox = byId("loginError");
  button.disabled = true;
  errorBox.hidden = true;
  try {
    const result = await api("/admin/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: byId("username").value,
        password: byId("password").value,
      }),
    });
    byId("password").value = "";
    await showDashboard(result.username);
  } catch (error) {
    errorBox.textContent = error.code === "LOGIN_RATE_LIMITED"
      ? `${error.message}（剩余${duration(error.retryAfterMillis)}）`
      : error.message;
    errorBox.hidden = false;
  } finally {
    button.disabled = false;
  }
}

async function logout() {
  try { await api("/admin/api/logout", { method: "POST", body: "{}" }); } catch { /* clear locally */ }
  state.overview = null;
  state.mapData = null;
  showLogin();
}

function renderKpis(totals = {}) {
  byId("kpiServers").textContent = fmtNumber(totals.serverCount);
  byId("kpiOnline").textContent = fmtNumber(totals.onlineAccountCount);
  byId("kpiShared").textContent = fmtNumber(totals.cloudSharedServerCount);
  byId("kpiBandits").textContent = fmtNumber(totals.banditTargetCount);
  byId("kpiMines").textContent = fmtNumber(totals.mineTargetCount);
  byId("kpiLeases").textContent = fmtNumber(totals.activeLeaseCount);
}

function renderServers() {
  const servers = state.overview?.servers || [];
  const body = byId("serverTableBody");
  const grouped = new Map();
  servers.forEach(server => {
    const key = String(server.platformKey || "unknown");
    if (!grouped.has(key)) grouped.set(key, { key, name: platformName(server), servers: [] });
    grouped.get(key).servers.push(server);
  });
  const groups = [...grouped.values()].sort((left, right) =>
    left.name.localeCompare(right.name, "zh-CN")
  );
  if (!state.expandedPlatforms.size && groups.length) {
    const selectedPlatform = selectedServer()?.platformKey;
    state.expandedPlatforms.add(String(selectedPlatform || groups[0].key));
  }
  byId("serverCountPill").textContent = `${groups.length} 个平台 · ${servers.length} 个区服`;
  byId("serverEmpty").hidden = servers.length > 0;
  body.innerHTML = groups.map(group => {
    const expanded = state.expandedPlatforms.has(group.key);
    const online = group.servers.reduce((sum, server) => sum + Number(server.onlineAccountCount || 0), 0);
    const shared = group.servers.filter(server => server.mode === "CLOUD_SHARED").length;
    const serverRows = !expanded ? "" : group.servers.map(server => {
      const identity = serverIdentity(server);
      const selected = identity === state.selectedServerKey;
      const cloudShared = server.mode === "CLOUD_SHARED";
      const maps = server.maps || {};
      const regionCount = Number(maps.bandit?.regionCount || 0) + Number(maps.mine?.regionCount || 0);
      return `<tr class="clickable server-child${selected ? " selected" : ""}" data-server-key="${esc(identity)}">
        <td><span class="server-name">${esc(server.areaName || server.serverKey)}</span><span class="server-sub">${esc(server.serverKey)}</span></td>
        <td><span class="mode-chip ${cloudShared ? "shared" : "local"}">${cloudShared ? "云共享" : "本地模式"}</span></td>
        <td><span class="online-count">${fmtNumber(server.onlineAccountCount)} / ${fmtNumber(server.threshold)}</span></td>
        <td><b>${fmtNumber(maps.bandit?.targetCount)}</b> / <b>${fmtNumber(maps.mine?.targetCount)}</b></td>
        <td>${fmtNumber(regionCount)}</td>
        <td title="${esc(server.lastSeenAtMillis ? fmtTime(server.lastSeenAtMillis) : `目录同步：${fmtTime(server.lastDirectorySyncAtMillis)}`)}">${server.lastSeenAtMillis ? esc(relativeTime(server.lastSeenAtMillis)) : "尚无心跳"}</td>
        <td class="row-arrow">›</td>
      </tr>`;
    }).join("");
    return `<tr class="platform-row" data-platform-key="${esc(group.key)}" tabindex="0" role="button" aria-expanded="${expanded}">
      <td colspan="7"><span class="platform-chevron">${expanded ? "⌄" : "›"}</span><span class="platform-title">${esc(group.name)}</span><span class="platform-key">${esc(group.key)}</span><span class="platform-summary">${fmtNumber(group.servers.length)} 个区服 · ${fmtNumber(online)} 个在线 · ${fmtNumber(shared)} 个云共享区服</span></td>
    </tr>${serverRows}`;
  }).join("");
  body.querySelectorAll("[data-platform-key]").forEach(row => {
    const toggle = () => {
      const key = row.dataset.platformKey;
      if (state.expandedPlatforms.has(key)) state.expandedPlatforms.delete(key);
      else state.expandedPlatforms.add(key);
      renderServers();
    };
    row.addEventListener("click", toggle);
    row.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
    });
  });
  body.querySelectorAll("[data-server-key]").forEach(row => {
    row.addEventListener("click", () => selectServer(row.dataset.serverKey, true));
  });

  const select = byId("serverSelect");
  const current = state.selectedServerKey;
  select.replaceChildren(...groups.map(group => {
    const optgroup = document.createElement("optgroup");
    optgroup.label = `${group.name}（${group.servers.length}）`;
    optgroup.replaceChildren(...group.servers.map(server => {
      const option = document.createElement("option");
      option.value = serverIdentity(server);
      option.textContent = server.areaName || server.serverKey;
      return option;
    }));
    return optgroup;
  }));
  if (current) select.value = current;
}

async function loadOverview({ selectFirst = false, quiet = false } = {}) {
  const refresh = byId("refreshButton");
  refresh.disabled = true;
  try {
    const result = await api("/admin/api/overview");
    state.overview = result;
    if ((!state.selectedServerKey || !selectedServer()) && (selectFirst || result.servers?.length)) {
      state.selectedServerKey = result.servers?.length ? serverIdentity(result.servers[0]) : "";
    }
    renderKpis(result.totals);
    renderServers();
    byId("updatedAt").textContent = `更新于 ${new Date(result.generatedAtMillis).toLocaleTimeString("zh-CN", { hour12: false })}`;
    if (state.selectedServerKey) {
      byId("serverDetail").hidden = false;
      renderSelectedServerHeading();
      await loadMap({ quiet });
    } else {
      byId("serverDetail").hidden = true;
    }
  } catch (error) {
    if (!quiet) showToast(error.message, "error");
    throw error;
  } finally {
    refresh.disabled = false;
  }
}

async function refreshAll() {
  try {
    await loadOverview({ quiet: true });
    showToast("共享数据已刷新");
  } catch (error) { showToast(error.message, "error"); }
}

async function selectServer(identity, scroll = false) {
  if (!identity || identity === state.selectedServerKey && state.mapData) {
    if (scroll) byId("serverDetail").scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  state.selectedServerKey = identity;
  const server = selectedServer();
  if (server) state.expandedPlatforms.add(String(server.platformKey));
  state.mapData = null;
  state.zoom = 1;
  renderServers();
  renderSelectedServerHeading();
  byId("serverDetail").hidden = false;
  await loadMap();
  if (scroll) byId("serverDetail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSelectedServerHeading() {
  const server = selectedServer();
  if (!server) return;
  const shared = server.mode === "CLOUD_SHARED";
  byId("detailServerName").textContent = server.areaName || server.serverKey;
  const platform = `${platformName(server)} (${server.platformKey})`;
  byId("detailServerMeta").textContent = server.observationCount
    ? `${platform} · ${server.serverKey} · 心跳观测 ${fmtNumber(server.observationCount)} 次`
    : `${platform} · ${server.serverKey} · 已收录完整目录，尚无账号心跳`;
  const badge = byId("detailModeBadge");
  badge.textContent = shared ? "云共享模式" : "本地模式";
  badge.className = `mode-badge ${shared ? "shared" : "local"}`;
  byId("serverSelect").value = state.selectedServerKey;
}

function renderServerDetail() {
  const data = state.mapData;
  if (!data) return;
  const server = data.server;
  const shared = server.mode === "CLOUD_SHARED";
  byId("modeExplainer").innerHTML = shared
    ? `<strong>云共享已启用</strong>当前 ${fmtNumber(server.onlineAccountCount)} 个匿名账号在线，已达到 ${fmtNumber(server.threshold)} 个的共享门槛。`
    : `<strong>当前使用本地地图</strong>在线 ${fmtNumber(server.onlineAccountCount)} 个，未达到 ${fmtNumber(server.threshold)} 个的云共享门槛。`;
  const actorList = byId("actorList");
  actorList.innerHTML = data.onlineActors?.length
    ? data.onlineActors.map(actor => `<div class="actor-row"><b>${esc(actor.actor)}</b><span>${esc(relativeTime(actor.lastSeenAtMillis, data.generatedAtMillis))}</span></div>`).join("")
    : `<div class="actor-empty">当前没有有效在线心跳</div>`;
  const facts = [
    ["游戏入口", server.gameHttp || "未记录"],
    ["最后心跳", server.lastSeenAtMillis ? fmtTime(server.lastSeenAtMillis) : "尚无账号心跳"],
    ["地图类型", state.mapKind === "bandit" ? "山贼" : "资源点"],
    ["有效周期", duration(data.ttlMillis)],
    ["扫描分块", `${fmtNumber(data.regions?.length)} 个`],
    ["活动租约", `${fmtNumber(data.scanLeases?.length)} 个`],
  ];
  byId("serverFacts").innerHTML = facts.map(([term, value]) => `<div><dt>${esc(term)}</dt><dd>${esc(value)}</dd></div>`).join("");
}

function compositionCode(target) {
  const data = target.data || {};
  if (data.compositionCode) return String(data.compositionCode);
  const composition = data.composition;
  if (!composition || typeof composition !== "object") return "";
  const values = [composition.foot, composition.bow, composition.cavalry, composition.chariot]
    .map(value => Number(value || 0));
  return values.every(value => Number.isFinite(value) && value >= 0 && value <= 9)
    ? values.join("") : "";
}
function compositionMatches(target, limits) {
  if (!limits) return true;
  const code = compositionCode(target);
  if (!/^\d{4}$/.test(code)) return false;
  return code.split("").map(Number).every((count, index) => count <= limits[index]);
}
function mineKind(target) { return String(target.data?.name || target.data?.kind || target.type || "资源点"); }
function mineOccupied(target) { return Boolean(target.data?.playerOccupied ?? target.data?.occupied); }

function selectedComposition() {
  const values = Array.from(byId("compositionFilters").querySelectorAll("select")).map(select => select.value);
  return values.length === 4 && values.every(value => value !== "") ? values.map(Number) : null;
}

function applyFilters() {
  const targets = state.mapData?.targets || [];
  const status = byId("statusFilter").value;
  if (state.mapKind === "bandit") {
    const level = Number(byId("banditLevel").value || 0);
    const drops = Array.from(document.querySelectorAll(".drop-filter:checked")).map(input => input.value);
    const limits = selectedComposition();
    state.filteredTargets = targets.filter(target => {
      const targetDrops = Array.isArray(target.data?.dropCategories) ? target.data.dropCategories : [];
      return (!level || Number(target.level) === level)
        && (!status || target.status === status)
        && drops.some(category => targetDrops.includes(category))
        && compositionMatches(target, limits);
    });
  } else {
    const kind = byId("mineKind").value;
    const owner = byId("mineOwner").value;
    state.filteredTargets = targets.filter(target => (
      (!kind || mineKind(target) === kind)
      && (!status || target.status === status)
      && (!owner || (owner === "occupied" ? mineOccupied(target) : !mineOccupied(target)))
    ));
  }
  renderMap();
  renderTargetTable();
  byId("filterPanel").hidden = true;
}

function populateDynamicFilters() {
  const levels = byId("banditLevel");
  if (levels.options.length === 1) {
    for (let level = 1; level <= 10; level += 1) levels.add(new Option(`${level}级`, String(level)));
  }
  const composition = byId("compositionFilters");
  if (!composition.children.length) {
    for (const label of ["步", "弓", "骑", "车"]) {
      const select = document.createElement("select");
      select.setAttribute("aria-label", `${label}兵将领上限`);
      select.add(new Option("不限", ""));
      for (let value = 0; value <= 5; value += 1) select.add(new Option(String(value), String(value)));
      composition.appendChild(select);
    }
  }
  const kinds = [...new Set((state.mapData?.targets || []).map(mineKind).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
  const mineSelect = byId("mineKind");
  const current = mineSelect.value;
  mineSelect.replaceChildren(new Option("全部资源", ""), ...kinds.map(kind => new Option(kind, kind)));
  mineSelect.value = kinds.includes(current) ? current : "";
}

async function loadMap({ quiet = false } = {}) {
  const server = selectedServer();
  if (!server) return;
  const loading = byId("mapLoading");
  loading.hidden = false;
  byId("mapRefresh").disabled = true;
  byId("pointPopup").hidden = true;
  try {
    const query = new URLSearchParams({
      platformKey: server.platformKey,
      serverKey: server.serverKey,
      mapKind: state.mapKind,
    });
    state.mapData = await api(`/admin/api/map?${query}`);
    populateDynamicFilters();
    state.filteredTargets = [...(state.mapData.targets || [])];
    renderServerDetail();
    applyFilters();
  } catch (error) {
    state.mapData = null;
    state.filteredTargets = [];
    byId("mapCanvas").replaceChildren();
    byId("mapEmpty").hidden = false;
    byId("mapMeta").textContent = error.message;
    renderTargetTable();
    if (!quiet) showToast(error.message, "error");
  } finally {
    loading.hidden = true;
    byId("mapRefresh").disabled = false;
  }
}

function appendGrid(canvas, width, height, maxX, maxY, sx, sy) {
  const group = svg("g");
  for (let index = 0; index <= 10; index += 1) {
    const x = index * maxX / 10;
    const y = index * maxY / 10;
    group.appendChild(svg("line", { class: "map-grid-line", x1: sx(x), y1: MAP_PADDING, x2: sx(x), y2: height - MAP_PADDING }));
    group.appendChild(svg("line", { class: "map-grid-line", x1: MAP_PADDING, y1: sy(y), x2: width - MAP_PADDING, y2: sy(y) }));
    const xText = svg("text", { class: "map-axis-label", x: sx(x), y: height - 42, "text-anchor": "middle" });
    xText.textContent = String(Math.round(x));
    group.appendChild(xText);
    const yText = svg("text", { class: "map-axis-label", x: 52, y: sy(y) + 7, "text-anchor": "middle" });
    yText.textContent = String(Math.round(y));
    group.appendChild(yText);
  }
  group.appendChild(svg("line", { class: "map-axis", x1: MAP_PADDING, y1: MAP_PADDING, x2: width - MAP_PADDING, y2: MAP_PADDING }));
  group.appendChild(svg("line", { class: "map-axis", x1: MAP_PADDING, y1: MAP_PADDING, x2: MAP_PADDING, y2: height - MAP_PADDING }));
  canvas.appendChild(group);
}

function appendLuoyang(canvas, x, y) {
  const group = svg("g", { transform: `translate(${x} ${y})`, "pointer-events": "none" });
  for (let index = 0; index < 8; index += 1) {
    const angle = index * Math.PI / 4;
    group.appendChild(svg("line", {
      class: "luoyang-ray", x1: Math.cos(angle) * 13, y1: Math.sin(angle) * 13,
      x2: Math.cos(angle) * 23, y2: Math.sin(angle) * 23,
    }));
  }
  group.appendChild(svg("circle", { class: "luoyang-sun", cx: 0, cy: 0, r: 9 }));
  const label = svg("text", { class: "luoyang-label", x: 28, y: 8 });
  label.textContent = "洛阳";
  group.appendChild(label);
  canvas.appendChild(group);
}

function renderLegend() {
  const items = state.mapKind === "bandit"
    ? [
      ["bandit-low", "1—2级"], ["bandit-middle", "3—4级"], ["bandit-upper", "5—6级"],
      ["bandit-high", "7—8级"], ["bandit-top", "9—10级"], ["reserved", "预占/出征"],
    ]
    : [
      ["mine-iron", "镌铁矿"], ["mine-crystal", "水晶矿"], ["mine-dark", "玄铁矿"],
      ["mine-berry", "浆果园"], ["mine-herb", "灵草园"], ["mine-jade", "玉露园"],
    ];
  byId("mapLegend").innerHTML = items.map(([className, label]) => `<span class="legend-item"><i class="legend-dot ${esc(className)}"></i>${esc(label)}</span>`).join("");
}

function targetColor(target) {
  if (state.mapKind === "mine") return MINE_COLORS[mineKind(target)] || "#5b8fa8";
  return BANDIT_COLORS[Math.min(5, Math.max(0, Math.ceil(Number(target.level || 0) / 2)))];
}

function renderMap() {
  const data = state.mapData;
  const canvas = byId("mapCanvas");
  canvas.replaceChildren();
  state.pointElements.clear();
  if (!data) return;
  const maxX = Number(data.bounds?.maxX || 186);
  const maxY = Number(data.bounds?.maxY || (state.mapKind === "bandit" ? 55 : 66));
  const height = maxY * MAP_UNIT + MAP_PADDING * 2;
  const sx = x => MAP_PADDING + Number(x) / maxX * (MAP_WIDTH - MAP_PADDING * 2);
  const sy = y => MAP_PADDING + Number(y) / maxY * (height - MAP_PADDING * 2);
  canvas.setAttribute("viewBox", `0 0 ${MAP_WIDTH} ${height}`);
  canvas.setAttribute("width", String(Math.round(MAP_WIDTH * state.zoom)));
  canvas.setAttribute("height", String(Math.round(height * state.zoom)));
  byId("zoomLabel").textContent = `${Math.round(state.zoom * 100)}%`;
  appendGrid(canvas, MAP_WIDTH, height, maxX, maxY, sx, sy);

  if (byId("showRegions").checked) {
    const width = Math.max(10, (MAP_WIDTH - MAP_PADDING * 2) / maxX * 1.35);
    const cellHeight = Math.max(10, (height - MAP_PADDING * 2) / maxY * 1.35);
    for (const region of data.regions || []) {
      canvas.appendChild(svg("rect", {
        class: "region-cell", x: sx(region.x) - width / 2, y: sy(region.y) - cellHeight / 2,
        width, height: cellHeight, rx: 3,
      }));
    }
  }
  if (byId("showLeases").checked) {
    const width = Math.max(16, (MAP_WIDTH - MAP_PADDING * 2) / maxX * 1.8);
    const cellHeight = Math.max(16, (height - MAP_PADDING * 2) / maxY * 1.8);
    for (const lease of data.scanLeases || []) {
      canvas.appendChild(svg("rect", {
        class: "lease-cell", x: sx(lease.x) - width / 2, y: sy(lease.y) - cellHeight / 2,
        width, height: cellHeight, rx: 4,
      }));
    }
  }
  appendLuoyang(canvas, sx(91), sy(26));

  for (const target of state.filteredTargets) {
    const circle = svg("circle", {
      class: `map-point${target.selectedForAttack ? " is-selected" : ""}`,
      cx: sx(target.x), cy: sy(target.y), r: target.selectedForAttack ? 13 : 9,
      fill: targetColor(target), opacity: ["missing", "rejected"].includes(target.status) ? .5 : 1,
      "data-target-id": target.targetId,
    });
    circle.addEventListener("click", event => {
      event.stopPropagation();
      showTarget(target, { scrollMap: false });
    });
    canvas.appendChild(circle);
    state.pointElements.set(String(target.targetId), circle);
  }
  // Replace the handler instead of adding one on every refresh; the map can be
  // refreshed repeatedly during a long admin session.
  canvas.onclick = () => { byId("pointPopup").hidden = true; };
  const layerCount = (byId("showRegions").checked ? data.regions?.length || 0 : 0)
    + (byId("showLeases").checked ? data.scanLeases?.length || 0 : 0);
  byId("mapEmpty").hidden = state.filteredTargets.length > 0 || layerCount > 0;
  const kindLabel = state.mapKind === "bandit" ? "山贼" : "资源点";
  byId("mapMeta").textContent = `${data.server.areaName || data.server.serverKey} · 显示 ${state.filteredTargets.length}/${data.targets.length} 个${kindLabel}目标 · ${data.regions.length} 个扫描分块 · ${data.scanLeases.length} 个活动租约`;
  renderLegend();
}

function statusChip(status) {
  return `<span class="status-chip ${esc(status)}">${esc(STATUS_LABELS[status] || status)}</span>`;
}
function targetName(target) {
  return state.mapKind === "bandit"
    ? String(target.data?.name || `${target.level || "?"}级山贼`)
    : mineKind(target);
}

function showTarget(target, { scrollMap = true } = {}) {
  state.pointElements.forEach(element => element.classList.remove("focused"));
  const point = state.pointElements.get(String(target.targetId));
  if (point) {
    point.classList.add("focused");
    if (scrollMap) {
      const canvas = byId("mapCanvas");
      const scroll = byId("mapScroll");
      const bounds = state.mapData.bounds;
      const maxY = Number(bounds.maxY);
      const height = maxY * MAP_UNIT + MAP_PADDING * 2;
      const left = (MAP_PADDING + Number(target.x) / Number(bounds.maxX) * (MAP_WIDTH - MAP_PADDING * 2)) * state.zoom;
      const top = (MAP_PADDING + Number(target.y) / maxY * (height - MAP_PADDING * 2)) * state.zoom;
      scroll.scrollTo({ left: Math.max(0, left - scroll.clientWidth / 2), top: Math.max(0, top - scroll.clientHeight / 2), behavior: "smooth" });
      void canvas;
    }
  }
  const data = target.data || {};
  const common = [
    ["目标ID", target.targetId],
    ["坐标", `(${target.x}, ${target.y})`],
    ["协调状态", STATUS_LABELS[target.status] || target.status],
    ["最后发现", fmtTime(target.lastSeenAtMillis)],
    ["剩余有效期", duration(target.remainingMillis)],
  ];
  const details = state.mapKind === "bandit" ? [
    ["山贼等级", `${target.level ?? "?"}级`],
    ["步弓骑车", compositionCode(target) || "无法确认"],
    ["战利品", (data.dropCategories || []).join("、") || "无额外分类"],
    ["奖励描述", data.rewardDescription || "无"],
    ["掉落ID", (data.lootIds || []).join("、") || "无"],
  ] : [
    ["业务编号", data.businessId ?? "未知"],
    ["玩家归属", mineOccupied(target) ? `${data.ownerName || "未知玩家"}（${data.ownerCountry || "未知国家"}）` : "无"],
    ["NPC守军", `${data.defenderCount || 0}队`],
    ["数量A", data.amountA ?? "未知"],
    ["数量B", data.amountB ?? "未知"],
    ["说明", data.description || "无"],
  ];
  if (target.reservedBy) common.push(["匿名预占者", target.reservedBy]);
  if (target.leaseUntilMillis > Date.now()) common.push(["目标租约到期", fmtTime(target.leaseUntilMillis)]);
  if (target.statusReason) common.push(["状态原因", target.statusReason]);
  byId("pointPopupContent").innerHTML = `<h4>${esc(targetName(target))}</h4><dl>${[...details, ...common].map(([term, value]) => `<dt>${esc(term)}</dt><dd>${esc(value)}</dd>`).join("")}</dl>`;
  byId("pointPopup").hidden = false;
}

function renderTargetTable() {
  const targets = state.filteredTargets || [];
  byId("targetCountPill").textContent = `${targets.length} 个目标`;
  byId("targetEmpty").hidden = targets.length > 0;
  byId("recordsTitle").textContent = state.mapKind === "bandit" ? "山贼目标明细" : "资源点明细";
  byId("targetTableHead").innerHTML = state.mapKind === "bandit"
    ? `<tr><th>目标</th><th>坐标</th><th>阵容</th><th>战利品</th><th>协调状态</th><th>最后发现</th></tr>`
    : `<tr><th>资源点</th><th>坐标</th><th>归属</th><th>NPC守军</th><th>协调状态</th><th>最后发现</th></tr>`;
  byId("targetTableBody").innerHTML = targets.map(target => state.mapKind === "bandit"
    ? `<tr class="clickable" data-target-id="${esc(target.targetId)}"><td><span class="target-main">${esc(targetName(target))}</span><span class="target-sub">ID ${esc(target.targetId)}</span></td><td class="coordinate">(${esc(target.x)}, ${esc(target.y)})</td><td>${esc(compositionCode(target) || "未知")}</td><td>${esc((target.data?.dropCategories || []).join("、") || "无")}</td><td>${statusChip(target.status)}</td><td title="${esc(fmtTime(target.lastSeenAtMillis))}">${esc(relativeTime(target.lastSeenAtMillis, state.mapData?.generatedAtMillis))}</td></tr>`
    : `<tr class="clickable" data-target-id="${esc(target.targetId)}"><td><span class="target-main">${esc(targetName(target))}</span><span class="target-sub">ID ${esc(target.targetId)}</span></td><td class="coordinate">(${esc(target.x)}, ${esc(target.y)})</td><td>${mineOccupied(target) ? esc(target.data?.ownerName || "已占领") : "未占领"}</td><td>${fmtNumber(target.data?.defenderCount)}队</td><td>${statusChip(target.status)}</td><td title="${esc(fmtTime(target.lastSeenAtMillis))}">${esc(relativeTime(target.lastSeenAtMillis, state.mapData?.generatedAtMillis))}</td></tr>`
  ).join("");
  byId("targetTableBody").querySelectorAll("[data-target-id]").forEach(row => {
    row.addEventListener("click", () => {
      const target = targets.find(item => String(item.targetId) === row.dataset.targetId);
      if (target) showTarget(target, { scrollMap: true });
    });
  });
}

function switchMapKind(kind) {
  if (kind !== "bandit" && kind !== "mine" || kind === state.mapKind) return;
  state.mapKind = kind;
  state.mapData = null;
  state.zoom = 1;
  document.querySelectorAll(".map-tab").forEach(button => {
    const active = button.dataset.mapKind === kind;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  byId("banditFilters").hidden = kind !== "bandit";
  byId("mineFilters").hidden = kind !== "mine";
  byId("pointPopup").hidden = true;
  loadMap();
}

function resetFilters() {
  byId("banditLevel").value = "0";
  document.querySelectorAll(".drop-filter").forEach(input => { input.checked = true; });
  byId("compositionFilters").querySelectorAll("select").forEach(select => { select.value = ""; });
  byId("mineKind").value = "";
  byId("mineOwner").value = "";
  byId("statusFilter").value = "";
  byId("showRegions").checked = true;
  byId("showLeases").checked = true;
  applyFilters();
}

function changeZoom(delta) {
  state.zoom = Math.min(2.4, Math.max(.4, Math.round((state.zoom + delta) * 10) / 10));
  renderMap();
}

function bindEvents() {
  byId("loginForm").addEventListener("submit", handleLogin);
  byId("passwordToggle").addEventListener("click", () => {
    const password = byId("password");
    const visible = password.type === "text";
    password.type = visible ? "password" : "text";
    byId("passwordToggle").textContent = visible ? "显示" : "隐藏";
    byId("passwordToggle").setAttribute("aria-label", visible ? "显示密码" : "隐藏密码");
  });
  byId("logoutButton").addEventListener("click", logout);
  byId("refreshButton").addEventListener("click", refreshAll);
  byId("serverSelect").addEventListener("change", event => selectServer(event.target.value));
  document.querySelectorAll(".map-tab").forEach(button => button.addEventListener("click", () => switchMapKind(button.dataset.mapKind)));
  byId("filterToggle").addEventListener("click", event => {
    event.stopPropagation();
    byId("filterPanel").hidden = !byId("filterPanel").hidden;
  });
  byId("filterPanel").addEventListener("click", event => event.stopPropagation());
  document.addEventListener("click", () => { byId("filterPanel").hidden = true; });
  byId("filterApply").addEventListener("click", applyFilters);
  byId("filterReset").addEventListener("click", resetFilters);
  byId("mapRefresh").addEventListener("click", () => loadMap());
  byId("zoomOut").addEventListener("click", () => changeZoom(-.2));
  byId("zoomIn").addEventListener("click", () => changeZoom(.2));
  byId("closePointPopup").addEventListener("click", () => { byId("pointPopup").hidden = true; });
  byId("showRegions").addEventListener("change", () => renderMap());
  byId("showLeases").addEventListener("change", () => renderMap());
}

async function initialize() {
  bindEvents();
  populateDynamicFilters();
  try {
    const session = await api("/admin/api/session");
    if (session.authenticated) await showDashboard(session.username);
    else showLogin();
  } catch { showLogin(); }
}

initialize();
