const categories = ["角色", "军事", "刷黄", "军情", "打矿", "六部", "常规"];
const sideMenus = {
  "起号": ["任务列表", "活动列表", "角色", "军队", "宝物", "英雄", "记录", "招将"],
  "角色": ["角色", "英雄", "宝物", "任务", "提示", "记录"],
  "军事": ["配兵", "掠夺", "抢城", "无损", "副本", "押镖", "寻宝"],
  "刷黄": [],
  "军情": ["军情", "国家"],
  "打矿": [],
  "六部": [],
  "常规": ["常用", "日常", "主号物品", "连体物品", "警报"],
};
const soldierTypes = ["民兵","轻步兵","重步兵","近卫兵","弓兵","弩兵","强弩兵","轻骑兵","弩骑兵","重骑兵","铁骑兵","弩车","冲城车","投石车"];
const brushLevelOptions = Array.from({length: 10}, (_, i) => i + 1);
const brushDropOptions = ["宝物", "资源", "装备", "宝箱"];
const defaultBrushDrops = [...brushDropOptions];
const compositionDigitOptions = [0, 1, 2, 3, 4, 5];
const copperFloorOptions = [1, 10, 20, 50];
const mineResourceOptions = [
  "镔铁矿", "水晶矿", "玄铁矿", "浆果园", "灵草园",
  "玉露园", "银矿", "一级牧场", "二级牧场", "三级牧场"
];
const autoOpenItemOptions = [
  "50两银票", "100两银票", "300两银票", "1000两银票",
  "惊喜宝箱", "实木宝箱", "青铜宝箱", "精铁宝箱",
  "铜钱辎重", "粮食辎重"
];
const discardItemOptions = ["山贼头巾", "精铁宝箱", "青铜宝箱", "传音符", "屯田令"];
const dungeonClearModeOption = "打通副本模式";
const dungeonChapters = [
  { value: "第一章", title: "山贼之乱", stageCount: 12 },
  { value: "第二章", title: "第二章", stageCount: 12 },
  { value: "第三章", title: "长安之乱", stageCount: 14 },
  { value: "第四章", title: "徐州之争", stageCount: 14 },
  { value: "第五章", title: "伪帝袁术", stageCount: 11 },
  { value: "第六章", title: "官渡之战（上）", stageCount: 12 },
  { value: "第七章", title: "官渡之战（下）", stageCount: 11 },
];
const roleStatusNames = [
  "休战",
  "军队攻击增加10%",
  "军队防御增加10%",
  "增加抓将的几率",
  "战斗后资源、声望的获取增加50%",
  "将领获取的经验增加50%",
  "加强破坏封地的威力",
  "增加夺取降忠效果",
  "增加夺取收益效果",
  "增加俘虏玩家将领的几率",
  "军队攻击速度增加5%",
];
let activeCategory = "角色";
let activeSide = "任务";
let activeMainPage = "助手";
let activeOtherView = "home";
let pickerOpen = false;
let saveSettingsInFlight = false;
let treasureSearchQuery = "";
let successRecordType = "military";
const urlParams = new URLSearchParams(window.location.search);
const isEmbeddedContainer = urlParams.get("embedded") === "1";
const isMobileRemote = urlParams.get("mobile") === "1";
const isStarterContainer = urlParams.get("starter") === "1";
const starterContainerAccountId = String(urlParams.get("starterAccountId") || "");
const starterContainerUsername = String(urlParams.get("starterUsername") || "");
const starterContainerAreaName = String(urlParams.get("starterAreaName") || "");
const currentContainerId = String(urlParams.get("containerId") || (isEmbeddedContainer ? "embedded" : "1"));
const CONTAINER_STORAGE_KEY = "dwsg_display_containers_v1";
const ACCOUNT_EVENT_CHANNEL = "dwsg_account_events_v1";
const ACCOUNT_EVENT_STORAGE_KEY = "dwsg_account_events_updated_at";
const CONTAINER_SELECTED_ACCOUNT_KEY = "dwsg_container_selected_accounts_v1";
let displayContainerIds = [1];
let nextDisplayContainerId = 2;
let accountEventChannel = null;
if (isEmbeddedContainer || isMobileRemote) document.body.classList.add("embedded-mode");
if (isMobileRemote) document.body.classList.add("mobile-remote-mode");
if (isStarterContainer) {
  document.body.classList.add("starter-container-mode");
  document.querySelector(".bottom-nav")?.remove();
  activeCategory = "起号";
  activeSide = "任务列表";
}

const appState = {
  accounts: [],
  accountUiState: {},
  accountHabitsLoaded: {},
  sessionId: null,
  displayDataSessionId: null,
  role: null,
  roleState: null,
  area: null,
  username: "",
  generals: [],
  army: [],
  inventory: { items: [] },
  militaryIntel: { events: [], statusByName: {} },
  dailyActivity: {},
  dailyStats: { brushYellowCount: 0, dungeonCount: 0 },
  roleQueueSummary: {},
  generalVisitCandidates: [],
  generalVisitCandidatesAccountId: null,
  generalVisitCandidatesLoading: false,
  generalVisitCandidatesError: "",
  generalVisitCandidatesNotice: "",
  generalVisitCandidatesUpdatedAt: 0,
  unresolvedGeneralIds: [],
  taskOverview: { resident: [], daily: [] },
  successRecords: [],
  starterRecords: [],
  targets: [],
  selectedTargetId: null,
  lastBattleText: "",
  formations: [],
  formationOptions: { clearOtherGenerals: false },
  savedFormationRules: [],
  brushSettings: {
    enabled: true, startHour: 0, startX: 0, startY: 0, scanLimit: 80, targetKind: "山贼", level: 1, generalId: "",
    reconnectDelayMinutes: 5,
    compositionCode: "0500", maxFoot: 0, maxBow: 5, maxCavalry: 0, maxChariot: 0, requireFoot: false,
    drops: [...defaultBrushDrops], drop: defaultBrushDrops[0],
    dailyLimit: 500, cycleDelaySec: 10, returnWaitSec: 0, healWounded: true, replenishTroops: false,
    autoEnergy: true, energyThreshold: 20, foodToCopper: true, copperFloorWan: 1,
    cleanMail: false, cleanInventory: false, discardItemNames: "",
    discardEquipment: false, maxEquipmentQuality: "良好", maxEquipmentLevel: 20,
    autoOpenEnabled: false, autoOpenItemNames: [],
    domestic: {
      enabled: false, emptyBuildingType: 1, upgradeBuildings: true,
      upgradeTechnology: false, technologyId: 5, technologyIds: [5], technologyTargetLevel: 2
    },
    dailyTasks: {
      autoSignIn: true, arenaCoins: true, autoDonate: false, salary: false,
      nationalCollect: false, cityLordCollect: false, generalVisit: false
    },
    generalVisitGeneralIds: [],
  },
  raidSettings: {
    fullTroops: true, duration: "立即出征", fullLoyalty: false,
    rows: [{ enabled: true, generalIds: [], generalId: "", playerName: "天雄星", fiefIndex: 10 }]
  },
  mineSettings: {
    speed: false, fullLoyalty: true, replenishTroops: true, maxMarchMinutes: 45, centerX: 91, centerY: 26,
    rows: [{ enabled: false, generalIds: [], generalId: "", resourceType: "镔铁矿", x: 91, y: 26, scope: "附近" }]
  },
  militaryFutureSettings: null,
  automation: { taskId: null, status: "idle", lastLogs: [] },
  systemLogs: [],
  technologyStates: [],
  accountLogLoadedFor: null,
  proxyNodes: [],
  localRoute: null,
  proxyNodesLoaded: false,
  areaCatalog: [],
  areaCatalogUpdatedAt: null,
};

let runtimeLog = "";
let toastTimer = null;
let systemLogTimer = null;
let systemLogHasLoaded = false;
let systemLogCursorId = 0;
let systemLogRequestPending = false;
let systemLogSelectionStart = null;
let accountLogSelectionStart = null;
let desktopDashboardData = null;
let desktopDashboardTimer = null;
let desktopDashboardLoading = false;
let desktopDashboardQuery = "";
let desktopDashboardFilter = "online";
let desktopDashboardLevelFilter = "all";
let desktopDashboardCountryFilter = "all";
const desktopDashboardExpanded = new Set();
const DESKTOP_DASHBOARD_POLL_INTERVAL_MS = 60 * 1000;
const SYSTEM_LOG_INITIAL_LIMIT = 1000;
const SYSTEM_LOG_INCREMENT_LIMIT = 500;
const SYSTEM_LOG_BROWSER_LIMIT = 1500;
const technologyNames = [
  "工程设计", "征召技巧", "种植技术", "行军技巧", "市场贸易", "建筑学",
  "铸铁技术", "甲胄制造", "药草研究", "阵法技巧", "抛射技巧", "驾驭技巧",
  "战车设计", "统帅能力", "信仰", "仓储", "安置", "格斗", "精准", "驯马", "精工", "悬赏",
];

function updateContainerCount() {
  const el = document.getElementById("containerCount");
  if (el) el.textContent = `${displayContainerIds.length} 个容器`;
}

function loadDisplayContainerState() {
  if (isEmbeddedContainer) return { ids: [1], nextId: 2 };
  try {
    const raw = localStorage.getItem(CONTAINER_STORAGE_KEY);
    if (!raw) return { ids: [1], nextId: 2 };
    const data = JSON.parse(raw);
    const extraIds = Array.isArray(data.ids)
      ? data.ids.map(x => Number(x)).filter(x => Number.isInteger(x) && x > 1)
      : [];
    const ids = [1, ...Array.from(new Set(extraIds)).sort((a, b) => a - b)];
    const maxId = Math.max(...ids, 1);
    const savedNextId = Number(data.nextId);
    const nextId = Number.isInteger(savedNextId) && savedNextId > maxId ? savedNextId : maxId + 1;
    return { ids, nextId: Math.max(2, nextId) };
  } catch (_) {
    return { ids: [1], nextId: 2 };
  }
}

function saveDisplayContainerState() {
  if (isEmbeddedContainer) return;
  try {
    localStorage.setItem(CONTAINER_STORAGE_KEY, JSON.stringify({
      ids: displayContainerIds.filter(id => id > 1),
      nextId: nextDisplayContainerId,
    }));
  } catch (_) {}
}

function syncAccountsAcrossContainers() {
  syncAccounts({ silent: true }).then(() => render()).catch(() => {});
}

function notifyAccountsChanged(reason = "accounts-changed") {
  const payload = { type: "accounts-changed", reason, at: Date.now() };
  try { accountEventChannel?.postMessage(payload); } catch (_) {}
  try { localStorage.setItem(ACCOUNT_EVENT_STORAGE_KEY, JSON.stringify(payload)); } catch (_) {}
}

function initAccountEventBridge() {
  try {
    accountEventChannel = new BroadcastChannel(ACCOUNT_EVENT_CHANNEL);
    accountEventChannel.onmessage = e => {
      if (e.data?.type === "accounts-changed") syncAccountsAcrossContainers();
    };
  } catch (_) {
    accountEventChannel = null;
  }
  window.addEventListener("storage", e => {
    if (e.key !== ACCOUNT_EVENT_STORAGE_KEY || !e.newValue) return;
    syncAccountsAcrossContainers();
  });
}

function loadContainerSelectedAccounts() {
  try {
    const raw = localStorage.getItem(CONTAINER_SELECTED_ACCOUNT_KEY);
    const data = raw ? JSON.parse(raw) : {};
    return data && typeof data === "object" && !Array.isArray(data) ? data : {};
  } catch (_) {
    return {};
  }
}

function saveContainerSelectedAccounts(data) {
  try { localStorage.setItem(CONTAINER_SELECTED_ACCOUNT_KEY, JSON.stringify(data || {})); } catch (_) {}
}

function accountSelectionRef(acc) {
  if (!acc && !appState.sessionId) return null;
  const session = acc?.session || {};
  const area = session.area || {};
  const role = session.role || {};
  return {
    sessionId: String(acc?.sessionId || appState.sessionId || ""),
    username: String(acc?.username || session.username || appState.username || ""),
    areaName: String(acc?.areaName || area.areaName || appState.area?.areaName || ""),
    roleName: String(acc?.roleName || role.roleName || appState.role?.roleName || ""),
    at: Date.now(),
  };
}

function saveCurrentContainerSelection(acc = selectedAccount()) {
  const ref = accountSelectionRef(acc);
  if (!ref?.sessionId && !ref?.username) return;
  const data = loadContainerSelectedAccounts();
  data[currentContainerId] = ref;
  saveContainerSelectedAccounts(data);
}

function clearCurrentContainerSelection() {
  const data = loadContainerSelectedAccounts();
  delete data[currentContainerId];
  saveContainerSelectedAccounts(data);
}

function savedSelectionForCurrentContainer() {
  return loadContainerSelectedAccounts()[currentContainerId] || null;
}

function findAccountBySelectionRef(ref, accounts = appState.accounts || []) {
  if (!ref) return null;
  const sessionId = String(ref.sessionId || "");
  if (sessionId) {
    const bySession = accounts.find(a => String(a.sessionId) === sessionId);
    if (bySession) return bySession;
  }
  const username = String(ref.username || "");
  const areaName = String(ref.areaName || "");
  if (username) {
    const byIdentity = accounts.find(a =>
      String(a.username || "") === username &&
      (!areaName || String(a.areaName || a.session?.area?.areaName || "") === areaName)
    );
    if (byIdentity) return byIdentity;
    return accounts.find(a => String(a.username || "") === username) || null;
  }
  return null;
}

function savedAccountForCurrentContainer(accounts = appState.accounts || []) {
  // 起号容器由父页面明确绑定账号，不受该容器上一次手动选择的账号影响。
  if (starterContainerAccountId || starterContainerUsername) {
    const bound = accounts.find(account =>
      (starterContainerAccountId && String(account.sessionId || account.accountId || account.id || "") === starterContainerAccountId) ||
      (starterContainerUsername &&
        String(account.username || "") === starterContainerUsername &&
        (!starterContainerAreaName || String(account.areaName || account.session?.area?.areaName || "") === starterContainerAreaName))
    );
    if (bound) return bound;
  }
  return findAccountBySelectionRef(savedSelectionForCurrentContainer(), accounts);
}

function containerIframeSrc(id) {
  return `./index.html?embedded=1&containerId=${encodeURIComponent(id)}`;
}

function buildDisplayContainerPanel(id) {
  const panel = document.createElement("section");
  panel.className = "container-panel";
  panel.dataset.containerId = String(id);
  const isMain = Number(id) === 1;
  panel.innerHTML = `
    <div class="container-titlebar">
      <span>容器 ${id}</span>
      <div class="container-title-actions">
        <small>${isMain ? "主容器" : "展示容器"}</small>
        ${isMain ? "" : `<button class="container-delete-btn" type="button" data-container-delete="${id}" title="删除容器 ${id}">删除</button>`}
      </div>
    </div>
    <div class="container-phone-wrap">
      <iframe class="container-iframe" src="${containerIframeSrc(id)}" title="容器 ${id}"></iframe>
    </div>
  `;
  panel.querySelector(".container-delete-btn")?.addEventListener("click", () => removeDisplayContainer(id));
  return panel;
}

function restoreDisplayContainers() {
  if (isEmbeddedContainer) return;
  const grid = document.getElementById("containerGrid");
  if (!grid) return;
  const state = loadDisplayContainerState();
  displayContainerIds = state.ids;
  nextDisplayContainerId = state.nextId;
  grid.querySelectorAll(".container-panel[data-container-id]").forEach(panel => {
    if (String(panel.dataset.containerId) !== "1") panel.remove();
  });
  displayContainerIds.filter(id => id > 1).forEach(id => grid.appendChild(buildDisplayContainerPanel(id)));
  updateContainerCount();
}

function addDisplayContainer() {
  if (isEmbeddedContainer) return;
  const grid = document.getElementById("containerGrid");
  if (!grid) return;
  const id = nextDisplayContainerId++;
  displayContainerIds.push(id);
  const panel = buildDisplayContainerPanel(id);
  grid.appendChild(panel);
  saveDisplayContainerState();
  updateContainerCount();
}

function removeDisplayContainer(id) {
  if (isEmbeddedContainer || Number(id) === 1) return;
  const numericId = Number(id);
  const panel = document.querySelector(`.container-panel[data-container-id="${numericId}"]`);
  panel?.remove();
  displayContainerIds = displayContainerIds.filter(x => x !== numericId);
  saveDisplayContainerState();
  updateContainerCount();
}

function h(strings, ...values) { return strings.map((s, i) => s + (values[i] ?? "")).join(""); }
const checked = `<span class="checkbox">✓</span>`;
const empty = `<span class="checkbox empty"></span>`;
function escHtml(v) { return String(v ?? "").replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'); }
function fmtNum(v) {
  if (v === undefined || v === null || v === "") return "";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("zh-CN") : String(v);
}
function formatTaskCountdown(until) {
  const end = Number(until || 0);
  if (!Number.isFinite(end) || end <= 0) return "";
  const total = Math.max(0, Math.ceil((end - Date.now()) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return [hours, minutes, seconds].map(x => String(x).padStart(2, "0")).join(":");
}
function taskCooldownHtml(until) {
  const end = Number(until || 0);
  if (!Number.isFinite(end) || end <= 0) return "";
  return `<span class="task-stack-countdown" data-task-countdown-until="${end}">冷却 ${formatTaskCountdown(end)}</span>`;
}
function updateTaskCountdowns() {
  document.querySelectorAll("[data-task-countdown-until]").forEach(el => {
    const until = Number(el.dataset.taskCountdownUntil || 0);
    const value = formatTaskCountdown(until);
    el.textContent = value && Date.now() < until ? `冷却 ${value}` : "等待状态更新";
    el.classList.toggle("is-expired", !value || Date.now() >= until);
  });
}
function statusLabel(status) {
  if (status === undefined || status === null || status === "") return "未知";
  const text = String(status);
  const normalized = {
    "空闲": "闲",
    "出征": "征",
    "防守": "防",
    "驻防": "防",
    "被俘虏": "俘",
    "被俘": "俘",
    "死亡": "亡",
    "阵亡": "亡",
    "修炼": "修",
    "修炼中": "修",
    "作战中": "战",
    "待招募": "招",
    "返回": "返",
  }[text];
  if (normalized) return normalized;
  if (["闲", "征", "防", "俘", "亡", "修", "战", "招", "返", "解雇", "未知"].includes(text)) return text;
  const n = Number(status);
  if (!Number.isFinite(n)) return String(status);
  return ({
    0: "闲",
    1: "征",
    2: "防",
    3: "俘",
    4: "亡",
    5: "修",
    6: "战",
    7: "招",
    8: "返",
    9: "解雇",
  })[n] || `状态${status}`;
}
function liveRoleState() {
  return appState.roleState && Object.keys(appState.roleState).length ? appState.roleState : (appState.role || {});
}
function fmtProgress(current, target, fallback = "-") {
  if (current === undefined || current === null || current === "") return fallback;
  if (target === undefined || target === null || target === "") return fmtNum(current);
  return `${fmtNum(current)} / ${fmtNum(target)}`;
}
function selectedAccount() {
  return (appState.accounts || []).find(a => String(a.sessionId) === String(appState.sessionId)) || null;
}
function hasLiveDisplayForCurrentAccount() {
  return !!appState.displayDataSessionId && String(appState.displayDataSessionId) === String(appState.sessionId);
}
function applyAccountRecordMeta(acc) {
  if (!acc) return;
  appState.sessionId = acc.sessionId || appState.sessionId || null;
  appState.username = acc.username || appState.username || "";
  appState.area = { areaName: acc.areaName || appState.area?.areaName || "" };
  ensureAccountLogLoaded(appState.sessionId);
}
function accountStatusClass(status) {
  if (status === "online") return "status-online";
  if (status === "offline") return "status-offline";
  if (status === "checking") return "status-checking";
  return "status-stopped";
}
function accountStatusText(status) {
  return ({ online: "已开启", offline: "掉线", checking: "检测中", stopped: "未开启" })[status] || "未开启";
}
function accountReconnectStatusText(acc) {
  if (!acc || acc.reconnectState !== "countdown") return "";
  const seconds = Math.max(0, Number(acc.reconnectRemainingSec || 0));
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `，${minutes}:${String(rest).padStart(2, "0")}后重连`;
}
function accountLabel(acc) {
  if (!acc) return "请先添加账号";
  const role = acc.roleName ? ` · ${acc.roleName}${acc.level ? " Lv." + acc.level : ""}` : "";
  return `${acc.username || ""}@${acc.areaName || ""}${role}`;
}
function accountProximityCompare(left, right) {
  const leftUsername = String(left?.username || "");
  const rightUsername = String(right?.username || "");
  const usernameOrder = leftUsername.localeCompare(
    rightUsername,
    "zh-CN",
    { numeric: true, sensitivity: "base" },
  );
  if (usernameOrder) return usernameOrder;
  // 同一登录账号的不同区服必须紧挨在一起，再按区服自然顺序排列。
  const areaOrder = String(left?.areaName || "").localeCompare(
    String(right?.areaName || ""),
    "zh-CN",
    { numeric: true, sensitivity: "base" },
  );
  if (areaOrder) return areaOrder;
  return String(left?.roleName || "").localeCompare(
    String(right?.roleName || ""),
    "zh-CN",
    { numeric: true, sensitivity: "base" },
  );
}
function renderRecentRequestDots(acc) {
  const root = document.getElementById("requestHealthDots");
  if (!root) return;
  const history = Array.isArray(acc?.recentGameRequests)
    ? acc.recentGameRequests.slice(-30)
    : [];
  const dots = Array.from({ length: 30 }, (_, index) => {
    const item = history[index];
    const status = item?.status === "success"
      ? "success"
      : (item?.status === "failure" ? "failure" : "");
    const latestPulse = index === 29 && item ? "latest-pulse" : "";
    const statusText = status === "success" ? "成功" : (status === "failure" ? "失败" : "暂无请求");
    const timeText = item?.time ? new Date(Number(item.time)).toLocaleTimeString("zh-CN", { hour12: false }) : "";
    const detail = item
      ? `第${index + 1}个：${statusText}${item.purpose ? ` · ${item.purpose}` : ""}${timeText ? ` · ${timeText}` : ""}`
      : `第${index + 1}个：${statusText}`;
    return `<span class="request-health-dot ${status} ${latestPulse}" title="${escAttr(detail)}" aria-label="${escAttr(detail)}"></span>`;
  });
  const signature = JSON.stringify(history.map(item => [item.status, item.time, item.purpose]));
  if (root.dataset.signature !== signature) {
    root.innerHTML = dots.join("");
    root.dataset.signature = signature;
  }
}
function updateAccountHeader() {
  const rs = liveRoleState();
  const open = document.querySelector(".open-count");
  const expire = document.querySelector(".expire-label");
  const renew = document.querySelector(".renew-btn");
  const enabled = document.querySelector(".enabled-text");
  const server = document.querySelector(".server-input");
  const accountCustom = document.getElementById("accountCustomSelect");
  const accountTrigger = document.getElementById("accountCustomTrigger");
  const accountOptions = document.getElementById("accountCustomOptions");
  const acc = selectedAccount();
  const sortedAccounts = [...(appState.accounts || [])].sort(accountProximityCompare);
  if (server) {
    const options = sortedAccounts.map(a => {
      const cls = a.status === "offline" ? " class=\"offline-option\"" : "";
      return `<option value="${escAttr(a.sessionId)}"${String(a.sessionId) === String(appState.sessionId) ? " selected" : ""}${cls}>${escHtml(accountLabel(a))}</option>`;
    }).join("");
    server.innerHTML = options || `<option value="">请先添加账号</option>`;
  }
  if (accountCustom && accountTrigger && accountOptions) {
    accountTrigger.textContent = accountLabel(acc);
    accountTrigger.disabled = !sortedAccounts.length;
    accountCustom.classList.toggle("is-disabled", !sortedAccounts.length);
    const signature = JSON.stringify(sortedAccounts.map(account => [
      account.sessionId,
      account.username,
      account.areaName,
      account.roleName,
      account.level,
      account.status,
    ]));
    if (
      !accountCustom.classList.contains("is-open")
      && accountOptions.dataset.optionsSignature !== signature
    ) {
      accountOptions.innerHTML = sortedAccounts.map((account, index) => {
        const previous = sortedAccounts[index - 1];
        const newAccountGroup = index > 0
          && String(previous?.username || "") !== String(account.username || "");
        const selected = String(account.sessionId) === String(appState.sessionId);
        return `<button type="button" role="option"
          class="account-custom-option status-${escAttr(account.status || "stopped")}${selected ? " is-selected" : ""}${newAccountGroup ? " is-new-account-group" : ""}"
          data-account-option="${escAttr(account.sessionId)}"
          aria-selected="${selected ? "true" : "false"}">
          <b>${escHtml(account.username || "-")}</b>
          <span>${escHtml(account.areaName || "未知区服")}</span>
          <small>${escHtml(account.roleName || "未读取角色")}${account.level ? ` · Lv.${fmtNum(account.level)}` : ""}</small>
        </button>`;
      }).join("");
      accountOptions.dataset.optionsSignature = signature;
    } else {
      accountOptions.querySelectorAll("[data-account-option]").forEach(option => {
        const selected = option.dataset.accountOption === String(appState.sessionId || "");
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-selected", selected ? "true" : "false");
      });
    }
  }
  if (open) open.textContent = appState.accounts.length ? `${appState.accounts.length}开` : "未登录";
  if (expire) {
    expire.textContent = acc ? "到期时间2026-07-08 03:59:04" : "到期时间2026-07-08 03:59:04";
  }
  if (renew) renew.textContent = "续期";
  if (enabled) {
    const status = acc?.status || "stopped";
    enabled.textContent = accountStatusText(status) + accountReconnectStatusText(acc);
    enabled.className = `enabled-text ${accountStatusClass(status)}`;
  }
  renderRecentRequestDots(acc);
  renderProxySelect();
}

function proxySelectValue(acc) {
  const mode = acc?.proxyMode || "auto";
  return mode === "manual" ? `manual:${acc?.proxyNode || ""}` : `${mode}:`;
}

function renderProxySelect() {
  const select = document.getElementById("proxySelect");
  const custom = document.getElementById("proxyCustomSelect");
  const trigger = document.getElementById("proxyCustomTrigger");
  const customOptions = document.getElementById("proxyCustomOptions");
  const ipText = document.getElementById("proxyIpText");
  if (!select) return;
  const acc = selectedAccount();
  const current = proxySelectValue(acc);
  const localRoute = appState.localRoute || {};
  const proxyUseCounts = {};
  (appState.accounts || []).forEach(account => {
    if (!account.started) return;
    const ip = String(account.proxyIp || "").trim();
    if (ip) proxyUseCounts[ip] = (proxyUseCounts[ip] || 0) + 1;
  });
  const usageLabel = ip => {
    const count = proxyUseCounts[String(ip || "").trim()] || 0;
    if (count >= 4) return "proxy-ip-usage-4";
    if (count === 3) return "proxy-ip-usage-3";
    if (count === 2) return "proxy-ip-usage-2";
    return count === 1 ? "proxy-ip-usage-1" : "";
  };
  const usageClasses = [
    "proxy-ip-usage-1",
    "proxy-ip-usage-2",
    "proxy-ip-usage-3",
    "proxy-ip-usage-4",
  ];
  // option 本身着色用于展开后的可选 IP 列表；select 同步着色用于
  // 下拉框收起后仍能看到当前账号所用 IP 的占用等级。
  select.classList.remove(...usageClasses);
  const selectedUsageClass = usageLabel(acc?.proxyIp);
  if (selectedUsageClass) select.classList.add(selectedUsageClass);
  const localLabel = `${localRoute.displayName || "直连（本机网络）"}${localRoute.ip ? ` · ${localRoute.ip}` : ""}${localRoute.ipDetected === false ? " · IP检测失败" : ""}`;
  const options = [
    { value: "auto:", label: "自动选择" },
    { value: "local:", label: localLabel, className: usageLabel(localRoute.ip) },
    ...(appState.proxyNodes || []).map(item => ({
      value: `manual:${item.node}`,
      label: `${item.displayName || item.node}${item.ip ? ` · ${item.ip}` : ""}${item.duplicateIp ? ` · 同出口×${item.duplicateCount}` : ""}${item.ipDetected === false ? " · IP检测失败" : ""}`,
      className: usageLabel(item.ip),
    })),
  ];

  // 账号状态会被后台频繁轮询。以前每次轮询都重写 innerHTML，会让已经展开的
  // 原生下拉框丢失滚动位置，表现为查看上方节点时突然跳回底部。
  // 用户正在操作时完全冻结列表；未操作时也只在节点内容确实变化后重建。
  const isInteracting = document.activeElement === select || select.dataset.userInteracting === "1";
  const optionsSignature = JSON.stringify(options.map(item => [
    item.value,
    item.label,
    Boolean(item.disabled),
    item.className || "",
  ]));
  if (!isInteracting && select.dataset.optionsSignature !== optionsSignature) {
    select.innerHTML = options.map(item =>
      `<option value="${escAttr(item.value)}"${item.disabled ? " disabled" : ""}${item.className ? ` class="${escAttr(item.className)}"` : ""}>${escHtml(item.label)}</option>`
    ).join("");
    select.dataset.optionsSignature = optionsSignature;
  }
  if (!isInteracting && select.value !== current && options.some(item => item.value === current)) {
    select.value = current;
  }
  if (!isInteracting) select.disabled = !acc;
  if (custom && trigger && customOptions) {
    const selectedOption = options.find(item => item.value === current) || options[0];
    trigger.classList.remove(...usageClasses);
    if (selectedOption?.className) trigger.classList.add(selectedOption.className);
    trigger.textContent = selectedOption?.label || "自动选择";
    trigger.disabled = !acc;
    custom.classList.toggle("is-disabled", !acc);
    const customSignature = JSON.stringify(options.map(item => [
      item.value,
      item.label,
      item.className || "",
    ]));
    if (
      !custom.classList.contains("is-open")
      && customOptions.dataset.optionsSignature !== customSignature
    ) {
      customOptions.innerHTML = options.map(item => `
        <button type="button" role="option"
          class="proxy-custom-option ${escAttr(item.className || "")}${item.value === current ? " is-selected" : ""}"
          data-proxy-option="${escAttr(item.value)}"
          aria-selected="${item.value === current ? "true" : "false"}">${escHtml(item.label)}</button>
      `).join("");
      customOptions.dataset.optionsSignature = customSignature;
    } else {
      customOptions.querySelectorAll("[data-proxy-option]").forEach(option => {
        const selected = option.dataset.proxyOption === current;
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-selected", selected ? "true" : "false");
      });
    }
  }
  if (ipText) {
    ipText.textContent = acc?.proxyIp || (acc?.proxyMode === "auto" ? "自动" : "IP待检测");
    ipText.title = acc?.proxyError || "";
  }
}

async function loadProxyNodes({ silent = true, manageButton = true, inspectIps = false } = {}) {
  const button = document.getElementById("refreshProxyBtn");
  if (manageButton && button) button.disabled = true;
  try {
    const query = new URLSearchParams({
      sessionId: appState.sessionId || "",
      inspectIps: inspectIps ? "1" : "0",
    });
    const res = await fetch(`/api/proxy/nodes?${query}`, { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "节点列表读取失败");
    appState.proxyNodes = data.nodes || [];
    appState.localRoute = data.localRoute || null;
    appState.proxyScanStats = data.scanStats || null;
    appState.proxyNodesLoaded = true;
    renderProxySelect();
    return true;
  } catch (e) {
    if (!silent) {
      appendLog("刷新IP节点失败：" + e.message);
      showToast("IP节点读取失败", "error");
    }
    return false;
  } finally {
    if (manageButton && button) button.disabled = false;
  }
}

function loginPlatformKey(platform = "") {
  const text = String(
    platform || document.getElementById("loginPlatform")?.value || "热血三国联盟"
  ).trim().toLowerCase();
  return /当乐|downjoy|dangley/.test(text) ? "downjoy" : "sglm";
}

function defaultLoginServerQuery(platform = "") {
  return loginPlatformKey(platform) === "downjoy" ? "1025区" : "周年服351区";
}

function renderLoginAreaOptions(preferred = "", platform = "") {
  let select = document.getElementById("loginServer");
  if (!select) return;
  // 兼容浏览器曾缓存的旧版 index.html：即使旧 DOM 还是输入框，
  // 新版脚本也会原地替换为真正的区服下拉框。
  if (select.tagName !== "SELECT") {
    const replacement = document.createElement("select");
    replacement.id = "loginServer";
    replacement.className = select.className || "";
    select.replaceWith(replacement);
    select = replacement;
  }
  const areas = appState.areaCatalog || [];
  if (!areas.length) {
    const platformKey = loginPlatformKey(platform);
    select.innerHTML = platformKey === "downjoy"
      ? `<option value="1025区">1025区（首次登录后自动校准名称）</option>`
      : [
          `<option value="351区">351区（首次登录后自动校准名称）</option>`,
          `<option value="352区">352区（首次登录后自动校准名称）</option>`,
        ].join("");
    select.disabled = false;
    const wanted = String(preferred || "").trim();
    select.value = platformKey === "downjoy"
      ? "1025区"
      : (/352/.test(wanted) ? "352区" : "351区");
    return;
  }
  select.disabled = false;
  select.innerHTML = areas.map(area =>
    `<option value="${escAttr(area.areaName || "")}">${escHtml(area.areaName || area.serverKey || area.areaId || "未知区服")}</option>`
  ).join("");
  const wanted = String(preferred || "").trim();
  const match = areas.find(area =>
    wanted && [area.areaName, area.serverKey, area.areaId].map(String).includes(wanted)
  );
  const defaultQuery = defaultLoginServerQuery(platform);
  const defaultZone = defaultQuery.match(/(\d+)\s*区/)?.[1] || "";
  const fallback = areas.find(area => {
    const key = String(area.serverKey || "");
    const name = String(area.areaName || "");
    return key === `qzone_${defaultZone}`
      || key === `qzone${defaultZone}`
      || new RegExp(`(^|\\D)${defaultZone}\\s*区`).test(name);
  }) || areas[0];
  select.value = String((match || fallback)?.areaName || "");
}

async function loadAreaCatalog(preferred = "", platform = "") {
  try {
    const selectedPlatform = String(
      platform || document.getElementById("loginPlatform")?.value || "热血三国联盟"
    ).trim();
    const query = new URLSearchParams({ platform: selectedPlatform });
    const res = await fetch(`/api/areas?${query}`, { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "区服目录读取失败");
    appState.areaCatalog = data.areas || [];
    appState.areaCatalogUpdatedAt = data.updatedAt || null;
    renderLoginAreaOptions(preferred, selectedPlatform);
    return true;
  } catch (e) {
    appState.areaCatalog = [];
    renderLoginAreaOptions(preferred, platform);
    appendLog("读取后台区服备份失败：" + e.message);
    return false;
  }
}

async function detectCurrentProxyIp({ manageButton = true, showSuccess = true } = {}) {
  const button = document.getElementById("refreshProxyBtn");
  const ipText = document.getElementById("proxyIpText");
  try {
    if (!appState.sessionId) throw new Error("请先选择账号");
    if (manageButton && button) {
      button.disabled = true;
      button.classList.add("is-loading");
    }
    if (ipText) ipText.textContent = "检测中...";
    const data = await apiPost("/api/proxy/detect", { sessionId: appState.sessionId });
    const index = appState.accounts.findIndex(a => String(a.sessionId) === String(appState.sessionId));
    if (index >= 0 && data.account) appState.accounts[index] = data.account;
    renderProxySelect();
    appendLog(`当前所选线路IP检测完成：${data.route || "当前线路"} ${data.ip}`);
    if (showSuccess) showToast(`当前IP：${data.ip}`, "success");
    notifyAccountsChanged("proxy-ip-detected");
    return true;
  } catch (e) {
    renderProxySelect();
    appendLog("检测当前IP失败：" + e.message);
    showToast("IP检测失败", "error");
    return false;
  } finally {
    if (manageButton && button) {
      button.disabled = false;
      button.classList.remove("is-loading");
    }
  }
}

async function refreshProxyNodesAndCurrentIp() {
  const button = document.getElementById("refreshProxyBtn");
  const ipText = document.getElementById("proxyIpText");
  try {
    if (button) {
      button.disabled = true;
      button.classList.add("is-loading");
    }
    if (ipText) ipText.textContent = "刷新可用节点...";
    // 可用范围已经逐节点验证并缓存了出口 IP。刷新列表时不再轮流切换
    // Clash 节点，避免影响浏览器和其他正在使用系统代理的连接。
    const nodesLoaded = await loadProxyNodes({ silent: false, manageButton: false, inspectIps: false });
    const ipDetected = await detectCurrentProxyIp({ manageButton: false, showSuccess: false });
    if (nodesLoaded) {
      appendLog(`已加载 ${appState.proxyNodes.length} 个游戏服实测可用节点${ipDetected ? "；当前IP已更新" : ""}`);
      showToast(`节点刷新完成：${appState.proxyNodes.length} 个可用IP`, "success");
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.classList.remove("is-loading");
    }
  }
}

async function selectProxy(value) {
  const separator = value.indexOf(":");
  const mode = separator >= 0 ? value.slice(0, separator) : "auto";
  const node = separator >= 0 ? value.slice(separator + 1) : "";
  try {
    if (!appState.sessionId) throw new Error("请先选择账号");
    showToast("正在切换IP...", "info");
    const data = await apiPost("/api/proxy/select", { sessionId: appState.sessionId, mode, node });
    const index = appState.accounts.findIndex(a => String(a.sessionId) === String(appState.sessionId));
    if (index >= 0 && data.account) appState.accounts[index] = data.account;
    renderProxySelect();
    const label = mode === "auto"
      ? "自动选择"
      : (mode === "local"
        ? (appState.localRoute?.displayName || "直连（本机网络）")
        : (data.account?.proxyNode || node));
    appendLog(`当前IP已切换为：${label}${data.ip ? ` ${data.ip}` : ""}`);
    showToast("当前IP已保存", "success");
    notifyAccountsChanged("proxy");
  } catch (e) {
    appendLog("切换IP失败：" + e.message);
    showToast("切换IP失败", "error");
    renderProxySelect();
  }
}

function snapshotCurrentAccountUi() {
  if (!appState.sessionId) return;
  appState.accountUiState[appState.sessionId] = {
    formations: JSON.parse(JSON.stringify(appState.formations || [])),
    formationOptions: JSON.parse(JSON.stringify(appState.formationOptions || { clearOtherGenerals: false })),
    brushSettings: JSON.parse(JSON.stringify(appState.brushSettings || {})),
    raidSettings: JSON.parse(JSON.stringify(appState.raidSettings || defaultRaidSettings())),
    mineSettings: JSON.parse(JSON.stringify(appState.mineSettings || defaultMineSettings())),
    militaryFutureSettings: JSON.parse(JSON.stringify(appState.militaryFutureSettings || defaultMilitaryFutureSettings())),
    automation: JSON.parse(JSON.stringify(appState.automation || { taskId: null, status: "idle", lastLogs: [] })),
  };
}

function defaultRaidSettings() {
  return {
    fullTroops: true,
    duration: "立即出征",
    fullLoyalty: false,
    rows: [{ enabled: true, generalIds: [], generalId: "", playerName: "天雄星", fiefIndex: 10 }]
  };
}

function defaultMineSettings() {
  return {
    speed: false,
    fullLoyalty: true,
    replenishTroops: true,
    maxMarchMinutes: 45,
    centerX: 91,
    centerY: 26,
    rows: [{
      enabled: false,
      generalIds: [],
      generalId: "",
      resourceType: "镔铁矿",
      x: 91,
      y: 26,
      scope: "附近"
    }]
  };
}

function mineSpeedEnabled(value) {
  if (typeof value === "boolean") return value;
  return !["", "不加速", "false", "0"].includes(String(value ?? "").trim());
}

function defaultMilitaryFutureSettings() {
  return {
    lossless: {
      fullTroops: false,
      rows: [{ enabled: false, generalIds: [], generalId: "", level: "10级" }]
    },
    dungeon: {
      mode: "loop",
      rows: [{ enabled: false, generalIds: [], generalId: "", chapter: "第四章", stage: "5", chest: "右" }]
    },
    escort: {
      advancedFirst: true,
      fullTroops: true,
      nationalCar: true,
      countryName: "美国",
      rows: [{ enabled: true, generalIds: [], generalId: "", type: "史诗" }]
    },
    treasure: {
      useCount: 10,
      refreshCount: 10,
      fullTroops: true,
      autoBuy: false,
      speed: "不加速",
      rows: [{ enabled: true, generalIds: [], generalId: "", type: "60级高级..." }]
    }
  };
}

function mergeMilitaryFutureSettings(saved) {
  const base = defaultMilitaryFutureSettings();
  const src = saved && typeof saved === "object" ? saved : {};
  Object.keys(base).forEach(key => {
    if (src[key] && typeof src[key] === "object") {
      base[key] = { ...base[key], ...src[key] };
      if (Array.isArray(src[key].rows)) base[key].rows = src[key].rows.map(r => ({ ...r }));
    }
  });
  return base;
}

function enforceSingleDungeonEnabled(preferred = null, scope = document) {
  const checks = Array.from(scope.querySelectorAll(".dungeon-enabled"));
  const keep = preferred?.checked ? preferred : checks.find(check => check.checked);
  checks.forEach(check => {
    if (check !== keep) check.checked = false;
  });
}

function defaultBrushSettings() {
  return {
    enabled: true, startHour: 0, startX: 0, startY: 0, scanLimit: 80, targetKind: "山贼", level: 1, generalId: "",
    reconnectDelayMinutes: 5,
    compositionCode: "0500", maxFoot: 0, maxBow: 5, maxCavalry: 0, maxChariot: 0, requireFoot: false,
    drops: [...defaultBrushDrops], drop: defaultBrushDrops[0],
    dailyLimit: 500, cycleDelaySec: 10, returnWaitSec: 0, healWounded: true, replenishTroops: false,
    autoEnergy: true, energyThreshold: 20, foodToCopper: true, copperFloorWan: 1,
    cleanMail: false, cleanInventory: false, discardItemNames: "",
    discardEquipment: false, maxEquipmentQuality: "良好", maxEquipmentLevel: 20,
    autoOpenEnabled: false, autoOpenItemNames: [],
    domestic: {
      enabled: false, emptyBuildingType: 1, upgradeBuildings: true,
      upgradeTechnology: false, technologyId: 5, technologyIds: [5], technologyTargetLevel: 2
    },
    dailyTasks: {
      autoSignIn: true, arenaCoins: true, autoDonate: false, salary: false,
      nationalCollect: false, cityLordCollect: false, generalVisit: false
    },
    generalVisitGeneralIds: [],
  };
}

function applyServerHabits(data) {
  const habits = data?.accountHabits || {};
  appState.unresolvedGeneralIds = Array.isArray(
    data?.unresolvedGeneralIds || habits.unresolvedGeneralIds
  )
    ? [...new Set((data?.unresolvedGeneralIds || habits.unresolvedGeneralIds).map(id => String(id)))]
    : [];
  if (Array.isArray(habits.formations) && habits.formations.length) {
    appState.formations = habits.formations.map(f => ({ ...f }));
    appState.savedFormationRules = habits.formations.map(f => ({ ...f }));
  }
  if (habits.formationOptions && typeof habits.formationOptions === "object") {
    appState.formationOptions = { clearOtherGenerals: false, ...habits.formationOptions };
  }
  const cfg = habits.config || {};
  const brush = cfg.brush || {};
  if (cfg && Object.keys(cfg).length) {
    const next = { ...defaultBrushSettings(), ...brush };
    [
      "startHour", "reconnectDelayMinutes", "dailyLimit", "cycleDelaySec", "returnWaitSec", "healWounded", "replenishTroops",
      "autoEnergy", "energyThreshold", "foodToCopper", "copperFloorWan",
      "cleanMail", "cleanInventory", "discardItemNames",
      "discardEquipment", "maxEquipmentQuality", "maxEquipmentLevel", "autoOpenEnabled", "autoOpenItemNames"
    ].forEach(k => {
      if (cfg[k] !== undefined) next[k] = cfg[k];
    });
    next.domestic = {
      ...defaultBrushSettings().domestic,
      ...(cfg.domestic && typeof cfg.domestic === "object" ? cfg.domestic : {})
    };
    next.dailyTasks = {
      ...defaultBrushSettings().dailyTasks,
      ...(cfg.dailyTasks && typeof cfg.dailyTasks === "object" ? cfg.dailyTasks : {})
    };
    next.generalVisitGeneralIds = Array.from(new Set(
      (Array.isArray(cfg.generalVisitGeneralIds) ? cfg.generalVisitGeneralIds : [])
        .map(id => String(id || "").trim())
        .filter(Boolean)
    )).slice(0, 4);
    next.copperFloorWan = normalizeCopperFloor(next.copperFloorWan);
    if (brush.compositionFilter) {
      Object.assign(next, brush.compositionFilter);
    }
    if (brush.compositionCode) next.compositionCode = brush.compositionCode;
    if (Array.isArray(brush.rows)) next.rows = brush.rows.map(r => ({ ...r }));
    appState.brushSettings = next;
  }
  if (habits.raid && typeof habits.raid === "object") {
    appState.raidSettings = { ...defaultRaidSettings(), ...habits.raid };
    if (Array.isArray(habits.raid.rows)) appState.raidSettings.rows = habits.raid.rows.map(r => ({ ...r }));
  }
  if (habits.mine && typeof habits.mine === "object") {
    appState.mineSettings = { ...defaultMineSettings(), ...habits.mine };
    if (Array.isArray(habits.mine.rows)) {
      appState.mineSettings.rows = habits.mine.rows.map(row => ({ ...row }));
    }
  }
  if (habits.militaryFuture && typeof habits.militaryFuture === "object") {
    appState.militaryFutureSettings = mergeMilitaryFutureSettings(habits.militaryFuture);
  }
  snapshotCurrentAccountUi();
}

function restoreAccountUi(sessionId) {
  const saved = appState.accountUiState[sessionId];
  appState.formations = saved?.formations ? JSON.parse(JSON.stringify(saved.formations)) : [];
  appState.formationOptions = saved?.formationOptions ? JSON.parse(JSON.stringify(saved.formationOptions)) : { clearOtherGenerals: false };
  appState.brushSettings = saved?.brushSettings
    ? { ...defaultBrushSettings(), ...JSON.parse(JSON.stringify(saved.brushSettings)) }
    : defaultBrushSettings();
  appState.raidSettings = saved?.raidSettings ? JSON.parse(JSON.stringify(saved.raidSettings)) : defaultRaidSettings();
  appState.mineSettings = saved?.mineSettings ? JSON.parse(JSON.stringify(saved.mineSettings)) : defaultMineSettings();
  appState.militaryFutureSettings = saved?.militaryFutureSettings ? mergeMilitaryFutureSettings(saved.militaryFutureSettings) : defaultMilitaryFutureSettings();
  appState.automation = saved?.automation ? JSON.parse(JSON.stringify(saved.automation)) : { taskId: null, status: "idle", lastLogs: [] };
}

function applySessionData(data, { restoreUi = true } = {}) {
  appState.sessionId = data.sessionId;
  appState.displayDataSessionId = data.sessionId || null;
  appState.username = data.username || "";
  appState.role = data.role || null;
  appState.roleState = data.roleState || {};
  appState.technologyStates = data.technologyStates || [];
  appState.area = data.area || null;
  appState.generals = data.generals || [];
  appState.army = data.army || data.roleState?.idleArmy || [];
  appState.inventory = data.inventory || { items: [] };
  appState.militaryIntel = data.militaryIntel || { events: [], statusByName: {} };
  appState.dailyActivity = data.dailyActivity || {};
  appState.dailyStats = data.dailyStats || { brushYellowCount: 0, dungeonCount: 0 };
  appState.unresolvedGeneralIds = Array.isArray(data.unresolvedGeneralIds)
    ? [...new Set(data.unresolvedGeneralIds.map(id => String(id)))]
    : [];
  appState.roleQueueSummary = data.roleQueueSummary || {};
  appState.generalVisitCandidates = [];
  appState.generalVisitCandidatesAccountId = null;
  appState.generalVisitCandidatesLoading = false;
  appState.generalVisitCandidatesError = "";
  appState.generalVisitCandidatesNotice = "";
  appState.generalVisitCandidatesUpdatedAt = 0;
  appState.taskOverview = data.taskOverview || { resident: [], daily: [] };
  appState.successRecords = [];
  appState.starterRecords = [];
  appState.savedFormationRules = [];
  appState.targets = [];
  appState.selectedTargetId = null;
  if (restoreUi) restoreAccountUi(appState.sessionId);
  applyServerHabits(data);
  appState.accountHabitsLoaded[appState.sessionId] = true;
  snapshotCurrentAccountUi();
  ensureAccountLogLoaded(appState.sessionId);
  ensureDefaultGeneral();
}

function applyAccountRecord(acc, { restoreUi = true } = {}) {
  appState.sessionId = acc?.sessionId || null;
  appState.displayDataSessionId = null;
  appState.username = acc?.username || "";
  appState.role = null;
  appState.roleState = {};
  appState.area = acc ? { areaName: acc.areaName || "" } : null;
  appState.generals = [];
  appState.army = [];
  appState.inventory = { items: [] };
  appState.militaryIntel = { events: [], statusByName: {} };
  appState.dailyActivity = {};
  appState.dailyStats = { brushYellowCount: 0, dungeonCount: 0 };
  appState.roleQueueSummary = {};
  appState.generalVisitCandidates = [];
  appState.generalVisitCandidatesAccountId = null;
  appState.generalVisitCandidatesLoading = false;
  appState.generalVisitCandidatesError = "";
  appState.generalVisitCandidatesNotice = "";
  appState.generalVisitCandidatesUpdatedAt = 0;
  appState.taskOverview = { resident: [], daily: [] };
  appState.successRecords = [];
  appState.starterRecords = [];
  appState.savedFormationRules = [];
  appState.targets = [];
  appState.selectedTargetId = null;
  if (restoreUi && appState.sessionId) restoreAccountUi(appState.sessionId);
  applyServerHabits(acc || {});
  if (appState.sessionId) {
    appState.accountHabitsLoaded[appState.sessionId] = true;
    snapshotCurrentAccountUi();
  }
  ensureAccountLogLoaded(appState.sessionId);
}

function renderTabs() {
  const visibleCategories = isStarterContainer ? ["起号", "刷黄", "副本"] : categories;
  document.getElementById("topTabs").innerHTML = visibleCategories.map(c =>
    `<button class="top-tab ${c === activeCategory ? "active" : ""}" data-cat="${c}">${c}</button>`
  ).join("");
  document.querySelectorAll(".top-tab").forEach(btn => btn.onclick = () => {
    discardActivePageChanges();
    activeCategory = btn.dataset.cat;
    activeSide = currentSideMenus()[0] || activeCategory;
    render();
    if (activeCategory === "角色") void refreshRoleSide(activeSide, { silent: true });
    if (isStarterContainer && ["刷黄", "副本"].includes(activeCategory)) {
      if (activeSide.endsWith("记录")) void refreshSuccessRecords({ silent: true });
    }
  });
}

function currentSideMenus() {
  if (isStarterContainer && activeCategory === "刷黄") return ["刷黄记录", "刷黄配置"];
  if (isStarterContainer && activeCategory === "副本") return ["副本记录", "副本配置"];
  return sideMenus[activeCategory] || [];
}

function roleSideRefreshScope(side) {
  if (side === "宝物") return "inventory";
  if (side === "角色") return "role-queues";
  return "role";
}

function renderSide() {
  const menus = currentSideMenus();
  document.getElementById("sideTabs").innerHTML = menus.length ? menus.map(m =>
    `<button class="side-tab ${m === activeSide ? "active" : ""}" data-side="${m}">${m}</button>`
  ).join("") : "";
  document.querySelectorAll(".side-tab[data-side]").forEach(btn => btn.onclick = () => {
    discardActivePageChanges();
    activeSide = btn.dataset.side;
    render();
    if (activeCategory === "角色") void refreshRoleSide(activeSide, { silent: true });
    if (activeCategory === "起号" && ["角色", "宝物", "英雄", "记录", "军队"].includes(activeSide)) {
      if (activeSide === "记录") void refreshSuccessRecords({ silent: true });
      else void refreshLiveState({
        silent: true,
        scope: activeSide === "宝物" ? "inventory" : activeSide === "军队" ? "military" : "role",
        side: activeSide,
      });
    }
    if (isStarterContainer && ["刷黄记录", "副本记录"].includes(activeSide)) {
      void refreshSuccessRecords({ silent: true });
    }
  });
}

function table(headers, rows, cls = "") {
  return `<table class="grid-table ${cls}"><thead><tr>${headers.map(x => `<th>${x}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
function actionButtons() {
  return `<div class="table-actions design-actions"><button class="add dynamic-add" type="button">+添加编队</button><button class="copy dynamic-copy" type="button">📋 复制编队</button><button class="delete dynamic-clear" type="button">🗑 一键删除</button></div>`;
}
function note(text) { return `<div class="note-box"><div class="note-title">说明：</div>${text}</div>`; }
function dCheck(on = true, cls = "") {
  return `<input class="design-check ${cls}" type="checkbox" ${on ? "checked" : ""}>`;
}
function dInput(value = "", cls = "", type = "text") {
  return `<input class="design-input ${cls}" type="${type}" value="${escAttr(value)}">`;
}
function dSelect(options, selected, cls = "") {
  return `<select class="design-select ${cls}">${simpleOptionsHtml(options, selected)}</select>`;
}
function dungeonChapterMeta(value) {
  const text = String(value ?? "").trim();
  const exact = dungeonChapters.find(chapter => chapter.value === text || chapter.title === text);
  if (exact) return exact;
  if (/^\d+$/.test(text)) {
    const index = Number(text);
    if (index >= 0 && index < dungeonChapters.length) return dungeonChapters[index];
  }
  return dungeonChapters[0];
}
function dungeonClearModeSelected(value) {
  return String(value ?? "").trim() === dungeonClearModeOption;
}
function dungeonStageOptions(chapterValue) {
  if (dungeonClearModeSelected(chapterValue)) return [dungeonClearModeOption];
  const count = dungeonChapterMeta(chapterValue).stageCount;
  return Array.from({ length: count }, (_, index) => String(index + 1));
}
function normalizeDungeonStage(chapterValue, stageValue) {
  if (dungeonClearModeSelected(chapterValue)) return dungeonClearModeOption;
  const count = dungeonChapterMeta(chapterValue).stageCount;
  const stage = Number(stageValue);
  if (!Number.isFinite(stage) || stage < 1) return "1";
  return String(Math.min(Math.trunc(stage), count));
}
function syncDungeonStageSelect(chapterSelect) {
  const row = chapterSelect?.closest("tr");
  const stageSelect = row?.querySelector(".dungeon-stage");
  if (!stageSelect) return;
  const options = dungeonStageOptions(chapterSelect.value);
  const selected = normalizeDungeonStage(chapterSelect.value, stageSelect.value);
  stageSelect.innerHTML = simpleOptionsHtml(options, selected);
  stageSelect.disabled = dungeonClearModeSelected(chapterSelect.value);
}
function designRow(label, body, cls = "") {
  return `<div class="design-row ${cls}"><span class="design-label">${label}</span>${body}</div>`;
}
function generalIdAt(index = 0) {
  return appState.generals[index]?.id || appState.generals[0]?.id || "";
}
function generalSelect(selectedId = undefined, cls = "") {
  const value = selectedId === undefined ? generalIdAt(0) : selectedId;
  return militaryGeneralMultiHtml(value ? [value] : [], cls || "legacy");
}
function designTable(headers, rows, cls = "") {
  return `<table class="grid-table design-table dynamic-table ${cls}"><thead><tr>${headers.map(x => `<th>${x}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
function normalizePolicyNames(value) {
  const values = Array.isArray(value) ? value : String(value || "").split(/[,，;；|]+/);
  return [...new Set(values.map(name => String(name || "").trim()).filter(Boolean))];
}
function normalizeCopperFloor(value) {
  const amount = Number(value);
  return copperFloorOptions.includes(amount) ? amount : 1;
}
function inventoryItemNameOptions(selected = []) {
  return [...discardItemOptions];
}
function policyMultiSummary(selected) {
  const names = normalizePolicyNames(selected);
  if (!names.length) return "未选择";
  if (names.length <= 2) return names.join("、");
  return `${names.slice(0, 2).join("、")} 等${names.length}项`;
}
function policyMultiHtml(selected, options, key, extraClass = "") {
  const selectedNames = normalizePolicyNames(selected);
  const selectedSet = new Set(selectedNames);
  const allOptions = [...new Set([...options, ...selectedNames])];
  const rows = allOptions.length
    ? allOptions.map(name => `<label class="policy-multi-option ${selectedSet.has(name) ? "selected" : ""}">
        <span>${escHtml(name)}</span>
        <input class="policy-multi-check" type="checkbox" value="${escAttr(name)}" ${selectedSet.has(name) ? "checked" : ""}>
      </label>`).join("")
    : `<div class="policy-multi-empty">角色宝物列表为空</div>`;
  return `<div class="policy-multi ${extraClass}" data-policy="${escAttr(key)}">
    <button class="policy-multi-summary" type="button">${escHtml(policyMultiSummary(selectedNames))}</button>
    <div class="policy-multi-panel">
      <input class="policy-multi-search" type="text" placeholder="搜索物品">
      <div class="policy-multi-actions"><button class="policy-multi-all" type="button">全选</button><button class="policy-multi-clear" type="button">清除</button></div>
      <div class="policy-multi-list">${rows}</div>
    </div>
  </div>`;
}

function technologyMultiHtml(selectedIds = []) {
  const selected = new Set((selectedIds || []).map(Number));
  const levels = new Map((appState.technologyStates || []).map(item => [Number(item.technologyId), item]));
  const rows = technologyNames.map((name, id) => {
    const state = levels.get(id) || {};
    const status = state.researching ? "，升级中" : "";
    return `<label class="policy-multi-option ${selected.has(id) ? "selected" : ""}">
      <span>${escHtml(name)}（${fmtNum(state.level || 0)}级${status}）</span>
      <input class="policy-multi-check" type="checkbox" value="${id}" ${selected.has(id) ? "checked" : ""}>
    </label>`;
  }).join("");
  const selectedNames = [...selected].map(id => technologyNames[id]).filter(Boolean);
  return `<div class="policy-multi technology-multi" data-policy="technology-ids">
    <button class="policy-multi-summary" type="button">${escHtml(policyMultiSummary(selectedNames))}</button>
    <div class="policy-multi-panel">
      <input class="policy-multi-search" type="text" placeholder="搜索科技">
      <div class="policy-multi-actions"><button class="policy-multi-all" type="button">全选</button><button class="policy-multi-clear" type="button">清除</button></div>
      <div class="policy-multi-list">${rows}</div>
    </div>
  </div>`;
}

function normalizeGeneralVisitIds(value) {
  const source = Array.isArray(value)
    ? value
    : String(value || "").split(/[,，;；|\s]+/);
  const result = [];
  source.forEach(raw => {
    let id = String(raw || "").trim();
    if (!id) return;
    if (/^0x[0-9a-f]+$/i.test(id)) id = String(Number.parseInt(id.slice(2), 16));
    if (!/^\d+$/.test(id) || result.includes(id) || result.length >= 4) return;
    result.push(id);
  });
  return result;
}

function generalVisitCandidateAvailable(candidate) {
  if (candidate?.available !== undefined) return !!candidate.available;
  return Number(candidate?.captiveState) === 0;
}

function generalVisitUnavailableReason(candidate) {
  if (generalVisitCandidateAvailable(candidate)) return "可拜访";
  return ({
    1: "已经被结交",
    2: "当前被俘虏",
    3: "当前状态不可拜访",
    4: "已经结交或不可拜访",
  })[Number(candidate?.captiveState)] || `当前不可拜访（状态${candidate?.captiveState ?? "未知"}）`;
}

function generalVisitCandidateName(candidate, id = "") {
  const rawId = String(id || candidate?.id || candidate?.idInt || "");
  return String(candidate?.name || (rawId ? `名将#${rawId}` : "名将"));
}

function generalVisitSummary(selectedIds = [], candidates = []) {
  const ids = normalizeGeneralVisitIds(selectedIds);
  if (!ids.length) return "请选择名将（0/4）";
  const byId = new Map(
    (Array.isArray(candidates) ? candidates : [])
      .map(candidate => [String(candidate?.id ?? candidate?.idInt ?? ""), candidate])
      .filter(([id]) => id)
  );
  const names = ids.map(id => generalVisitCandidateName(byId.get(id), id));
  const head = names.length <= 2
    ? names.join("、")
    : `${names.slice(0, 2).join("、")}等${names.length}个`;
  return `${head}（${ids.length}/4）`;
}

function generalVisitPanelHtml() {
  const b = appState.brushSettings;
  if (!b.dailyTasks?.generalVisit) return "";
  const selectedIds = normalizeGeneralVisitIds(b.generalVisitGeneralIds);
  const priorityById = new Map(selectedIds.map((id, index) => [id, index + 1]));
  const sameAccount = String(appState.generalVisitCandidatesAccountId || "") === String(appState.sessionId || "");
  const candidates = sameAccount && Array.isArray(appState.generalVisitCandidates)
    ? appState.generalVisitCandidates
    : [];
  const availableCount = candidates.filter(generalVisitCandidateAvailable).length;
  const updatedAt = Number(appState.generalVisitCandidatesUpdatedAt || 0);
  const updatedText = updatedAt
    ? new Date(updatedAt).toLocaleTimeString("zh-CN", { hour12: false })
    : "尚未查询";
  const loading = !!(appState.generalVisitCandidatesLoading && sameAccount);
  let summaryText = generalVisitSummary(selectedIds, candidates);
  if (loading) summaryText = "正在查询名将…";
  else if (appState.generalVisitCandidatesError && sameAccount) {
    summaryText = appState.generalVisitCandidatesError;
  }

  let body = "";
  if (loading) {
    body = `<div class="general-visit-state is-loading">正在查询当前账号可拜访名将…</div>`;
  } else if (appState.generalVisitCandidatesError && sameAccount) {
    body = `<div class="general-visit-state is-error">${escHtml(appState.generalVisitCandidatesError)}</div>`;
  } else if (appState.generalVisitCandidatesNotice && sameAccount) {
    body = `<div class="general-visit-state">${escHtml(appState.generalVisitCandidatesNotice)}</div>`;
  } else if (!sameAccount || !candidates.length) {
    body = `<div class="general-visit-state">当前没有候选数据，点击“重新查询”读取名将列表。</div>`;
  } else {
    const limitReached = selectedIds.length >= 4;
    const rows = candidates.map(candidate => {
      const id = String(candidate.id ?? candidate.idInt ?? "");
      const available = generalVisitCandidateAvailable(candidate);
      const priority = priorityById.get(id) || 0;
      const checked = priority > 0;
      const disabled = !available || (!checked && limitReached);
      const force = fmtNum(candidate.force ?? candidate.strengthTotal);
      const intelligence = fmtNum(candidate.intelligence ?? candidate.intelligenceTotal);
      const command = fmtNum(candidate.command);
      const status = generalVisitUnavailableReason(candidate);
      return `<label class="general-visit-option ${available ? "is-available" : "is-unavailable"} ${checked ? "is-selected" : ""} ${!checked && limitReached ? "is-limit-reached" : ""}">
        <span class="general-visit-priority">${priority || "—"}</span>
        <input class="general-visit-candidate-check" type="checkbox" value="${escAttr(id)}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}>
        <span class="general-visit-option-main">
          <strong>${escHtml(generalVisitCandidateName(candidate, id))}</strong>
          <small>武${force} 智${intelligence} 统${command} · ${escHtml(status)}</small>
        </span>
      </label>`;
    }).join("");
    body = `<div class="general-visit-hint">按勾选先后形成 1～4 优先级；可选 ${availableCount} 名 · 更新 ${escHtml(updatedText)}</div>
      <div class="general-visit-list">${rows}</div>`;
  }

  return `<div class="general-visit-multi">
    <div class="general-visit-toolbar">
      <button class="general-visit-summary" type="button" title="${escAttr(summaryText)}">${escHtml(summaryText)}</button>
      <button id="refreshGeneralVisitCandidates" class="table-btn general-visit-refresh" type="button" ${loading ? "disabled" : ""}>${loading ? "查询中…" : "重新查询"}</button>
    </div>
    <div class="general-visit-dropdown">${body}</div>
  </div>`;
}

function syncGeneralVisitMultiUi(root = document.querySelector(".general-visit-multi")) {
  if (!root) return;
  const selectedIds = normalizeGeneralVisitIds(appState.brushSettings.generalVisitGeneralIds);
  const priorityById = new Map(selectedIds.map((id, index) => [id, index + 1]));
  const limitReached = selectedIds.length >= 4;
  const sameAccount = String(appState.generalVisitCandidatesAccountId || "") === String(appState.sessionId || "");
  const candidates = sameAccount && Array.isArray(appState.generalVisitCandidates)
    ? appState.generalVisitCandidates
    : [];
  const candidateById = new Map(
    candidates
      .map(candidate => [String(candidate?.id ?? candidate?.idInt ?? ""), candidate])
      .filter(([id]) => id)
  );

  root.querySelectorAll(".general-visit-option").forEach(label => {
    const input = label.querySelector(".general-visit-candidate-check");
    if (!input) return;
    const id = String(input.value || "");
    const candidate = candidateById.get(id);
    const available = candidate ? generalVisitCandidateAvailable(candidate) : !input.disabled || !!priorityById.get(id);
    const priority = priorityById.get(id) || 0;
    const checked = priority > 0;
    input.checked = checked;
    input.disabled = !available || (!checked && limitReached);
    label.classList.toggle("is-selected", checked);
    label.classList.toggle("is-available", available);
    label.classList.toggle("is-unavailable", !available);
    label.classList.toggle("is-limit-reached", !checked && limitReached);
    const badge = label.querySelector(".general-visit-priority");
    if (badge) badge.textContent = priority || "—";
  });

  const summary = root.querySelector(".general-visit-summary");
  if (summary) {
    const text = generalVisitSummary(selectedIds, candidates);
    summary.textContent = text;
    summary.title = text;
  }
}

function renderCommon() {
  const b = appState.brushSettings;
  if (activeSide === "常用") return h`
    <div class="design-page common-design-page">
      <div class="design-card design-setting-card">
        ${designRow("掉线重连：", `<span title="成功重连后连续失败次数会清零">网络 3→5→10 分钟；Token/服务器拒绝 10→20→30 分钟</span>`)}
        ${designRow("刷黄上限：", `<input id="commonDailyLimit" class="design-input num-compact" type="number" min="1" max="500" value="${escAttr(b.dailyLimit ?? 500)}"><span>次</span>`)}
        ${designRow("治疗伤兵：", `<span>开启</span><input id="healWounded" class="design-check" type="checkbox" ${b.healWounded !== false ? "checked" : ""}>`)}
        ${designRow("自动内政：", `<span>开启</span><input id="autoDomestic" class="design-check" type="checkbox" ${b.domestic?.enabled ? "checked" : ""}><span>空地建筑</span><select id="emptyBuildingType" class="design-select w-wide">${[
          [1,"房屋"],[2,"农场"],[3,"书院"],[4,"步兵营"],[5,"弓兵营"],[6,"战车营"],[8,"骑兵营"]
        ].map(([value,label]) => `<option value="${value}" ${Number(b.domestic?.emptyBuildingType ?? 1) === value ? "selected" : ""}>${label}</option>`).join("")}</select>`)}
        ${designRow("升级科技：", `${technologyMultiHtml(b.domestic?.technologyIds || [b.domestic?.technologyId ?? 5])}<input id="upgradeTechnology" class="design-check" type="checkbox" ${b.domestic?.upgradeTechnology ? "checked" : ""}>`)}
        ${designRow("建筑加速：", `<span>未接入</span><select class="design-select w-mid" disabled><option>不加速</option></select>`)}
        ${designRow("自动加体：", `<span>开启</span><input id="autoEnergy" class="design-check" type="checkbox" ${b.autoEnergy !== false ? "checked" : ""}><span>体力&lt;</span><input id="energyThreshold" class="design-input num-compact" type="number" min="20" max="100" value="${escAttr(b.energyThreshold ?? 20)}">`)}
        ${designRow("释放俘虏：", `<span>开启</span>${dCheck(false)}<span>成长&gt;</span>${dInput(80, "num-compact", "number")}`)}
        ${designRow("劝降俘虏：", `<span>开启</span>${dCheck(false)}<span>成长&gt;</span>${dInput(80, "num-compact", "number")}<button class="table-btn design-mini-btn" type="button">铜钱劝降</button>`)}
        ${designRow("粮食转铜：", `<span>开启</span><input id="foodToCopper" class="design-check" type="checkbox" ${b.foodToCopper !== false ? "checked" : ""}><select id="copperFloorWan" class="design-select num-compact">${simpleOptionsHtml(copperFloorOptions, normalizeCopperFloor(b.copperFloorWan))}</select><span>万</span>`)}
      </div>
    </div>`;
  if (activeSide === "日常") return h`
    <div class="design-page common-design-page">
      <div class="design-card design-setting-card">
        ${[
          ["autoSignIn", "自动签到", true],
          ["arenaCoins", "领竞技币", true],
          ["autoDonate", "自动捐献", true],
          ["salary", "领取俸禄", true],
          ["generalVisit", "名将拜访", true],
          ["nationalCollect", "国家征收", true],
          ["cityLordCollect", "城主征收", true]
        ].map(([key, label, ready]) => designRow(`${label}：`,
          `<span>${ready ? "开启" : "待接入"}</span><input class="design-check daily-task-toggle" data-task="${key}" type="checkbox" ${b.dailyTasks?.[key] ? "checked" : ""} ${ready ? "" : "disabled"}>${
            key === "autoDonate" && Number(appState.role?.level || 0) > 0
              ? `<span class="daily-task-note">最高 ${Number(appState.role.level) * 1000} 铜钱 + ${Number(appState.role.level) * 3000} 粮食 + ${Number(appState.role.level) * 1000} 科技积分</span>`
              : key === "generalVisit"
                ? `<span class="daily-task-note">最多选择4名，按勾选顺序尝试</span>`
                : key === "nationalCollect"
                  ? `<span class="daily-task-note">比较州城、郡城、县城可征铜钱；不查询小城</span>`
                  : key === "cityLordCollect"
                    ? `<span class="daily-task-note">所有自有城池各征收一次</span>`
                    : ""
          }`
        )).join("")}
        ${generalVisitPanelHtml()}
        ${designRow("开启免战：", `<span>开启</span>${dCheck(false)}`)}
        ${designRow("连体整理：", `<span>开启</span>${dCheck(false)}`)}
      </div>
      ${note("各项日常任务独立设置、独立执行；普通失败会写入角色-提示，但不会阻断其他任务。")}
    </div>`;
  if (activeSide === "主号物品") return h`
    <div class="design-page common-design-page">
      <div class="design-card design-setting-card">
        ${designRow("丢弃物品：", policyMultiHtml(b.discardItemNames, inventoryItemNameOptions(b.discardItemNames), "discard-items"))}
        ${designRow("丢弃装备：", `<input id="discardEquipment" class="design-check" type="checkbox" ${b.discardEquipment ? "checked" : ""}><select id="maxEquipmentQuality" class="design-select w-short">${simpleOptionsHtml(["普通","良好","优秀","卓越"], b.maxEquipmentQuality || "良好")}</select><span>等级&lt;</span><input id="maxEquipmentLevel" class="design-input num-compact" type="number" min="1" max="100" value="${escAttr(b.maxEquipmentLevel ?? 20)}">`)}
        ${designRow("自动开箱：", `<input id="autoOpenEnabled" class="design-check" type="checkbox" ${b.autoOpenEnabled ? "checked" : ""}>${policyMultiHtml(b.autoOpenItemNames, autoOpenItemOptions, "auto-open-items")}`)}
      </div>
      ${note("不丢强化、炼魂、80级以上装备<br/>青铜宝箱和精铁宝箱需要对应钥匙")}
    </div>`;
  if (activeSide === "连体物品") return h`
    <div class="design-page common-design-page">
      <div class="design-card design-setting-card">
        ${designRow("整理物品：", `<span>开启</span>${dCheck(false)}${dInput("青铜钥匙", "w-mid")}`)}
        ${designRow("保留数量：", dInput(3, "num-compact", "number"))}
        ${designRow("自动开箱：", `<span>开启</span>${dCheck(false)}${dInput("50两银票、...", "w-long")}`)}
      </div>
      ${note("连体物品整理同主号物品：按保留清单转移、丢弃、开箱。")}
    </div>`;
  return h`
    <div class="design-page common-design-page">
      <div class="design-card design-setting-card">
        ${designRow("来袭警报：", `<span>开启</span>${dCheck(true)}${dSelect(["声音+日志", "仅日志", "关闭"], "声音+日志", "w-mid")}`)}
        ${designRow("军情提醒：", `<span>开启</span>${dCheck(true)}${dSelect(["出征/返回", "仅来袭", "全部"], "出征/返回", "w-mid")}`)}
        ${designRow("异常提醒：", `<span>开启</span>${dCheck(true)}`)}
      </div>
      ${note("警报页面：用于配置来袭提醒、军情提醒和任务异常提醒。")}
    </div>`;
}

function renderLiubu() {
  return h`<div class="design-page liubu-design-page">
    <div class="design-card design-setting-card">
      ${designRow("种菜收菜：", `<span>开启</span>${dCheck(true)}<span>作物</span>${dSelect(["金银花", "草药", "稻谷", "棉花"], "金银花", "w-short")}<span>高级优先</span>${dCheck(true)}`)}
      ${designRow("偷菜：", `<span>开启</span>${dCheck(true)}`)}
      ${designRow("礼部任务：", `<span>开启</span>${dCheck(true)}<span>使用俸禄刷新</span>${dCheck(true)}`)}
    </div>
    ${note("礼部任务成功率和文官等级、特长、技能有关")}
  </div>`;
}
function renderMine() {
  const settings = { ...defaultMineSettings(), ...(appState.mineSettings || {}) };
  const rows = (Array.isArray(settings.rows) && settings.rows.length ? settings.rows : defaultMineSettings().rows)
    .map((row, index) => {
      const generalIds = rowGeneralIds(row);
      return [
        `<input class="design-check mine-enabled" type="checkbox" ${row.enabled ? "checked" : ""}>`,
        militaryGeneralMultiHtml(generalIds, `mine-${index}`),
        `<select class="design-select table-select mine-resource">${simpleOptionsHtml(mineResourceOptions, row.resourceType || "镔铁矿")}</select>`,
        `<input class="design-input table-num mine-x" type="number" min="0" max="186" value="${escAttr(row.x ?? 0)}">`,
        `<input class="design-input table-num mine-y" type="number" min="0" max="66" value="${escAttr(row.y ?? 0)}">`,
        `<select class="design-select table-select mine-scope">${simpleOptionsHtml(["定点", "附近", "全国"], row.scope || "附近")}</select>`,
        `<button class="table-btn dynamic-delete" type="button">删除</button>`
      ];
    });
  return h`<div class="design-page mine-design-page">
    <div class="design-card design-setting-card">
      ${designRow("中心坐标：", `<span>x=</span><input class="design-input coord-input mine-center-x" type="number" min="0" max="186" value="${escAttr(settings.centerX ?? 91)}"><span>y=</span><input class="design-input coord-input mine-center-y" type="number" min="0" max="66" value="${escAttr(settings.centerY ?? 26)}">`)}
      ${designRow("打矿加速：", `<input class="design-check mine-speed" type="checkbox" ${mineSpeedEnabled(settings.speed) ? "checked" : ""}>`)}
      ${designRow("打矿满忠：", `<input class="design-check mine-full-loyalty" type="checkbox" ${settings.fullLoyalty ? "checked" : ""}>`)}
      ${designRow("批量补满：", `<input class="design-check mine-replenish-troops" type="checkbox" ${settings.replenishTroops !== false ? "checked" : ""}>`)}
      ${designRow("目标范围：", `<select class="design-select mine-max-march-minutes">${simpleOptionsHtml(["45", "60", "90"], String(settings.maxMarchMinutes || 45))}</select><span>分钟内可到达</span>`)}
    </div>
    ${designTable(["", "出征将领", "资源类型", "x坐标", "y坐标", "范围", "操作"], rows, "mine-table")}${actionButtons()}
    ${note("附近和全国搜索以中心坐标为起点；表格中的 x、y 仅在“定点”范围下作为目标坐标。自动打矿只攻击未被玩家占领的资源点。")}
  </div>`;
}
function escAttr(v) { return String(v ?? "").replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;'); }
function compositionFromCode(code) {
  const digits = String(code || "").replace(/\D/g, "");
  if (digits.length !== 4) return null;
  return { maxFoot: Number(digits[0]), maxBow: Number(digits[1]), maxCavalry: Number(digits[2]), maxChariot: Number(digits[3]) };
}
function updateCodeFromFields() {
  const b = appState.brushSettings;
  b.compositionCode = `${Number(b.maxFoot||0)}${Number(b.maxBow||0)}${Number(b.maxCavalry||0)}${Number(b.maxChariot||0)}`;
}
function generalMatchesId(general, id) {
  const value = String(id ?? "");
  return String(general?.id ?? "") === value || String(general?.idHex ?? "") === value;
}
function configuredGeneralNameSnapshot(id) {
  const value = String(id ?? "");
  const sources = [
    ...(appState.formations || []),
    ...(appState.savedFormationRules || []),
    ...(appState.brushSettings?.rows || []),
  ];
  for (const row of sources) {
    const snapshots = row?.generalNameSnapshots;
    if (snapshots && typeof snapshots === "object" && snapshots[value]) {
      return String(snapshots[value]);
    }
  }
  return "";
}
function selectedGeneralRecords(selectedIds = []) {
  const ids = [...new Set((selectedIds || []).map(value => String(value || "").trim()).filter(Boolean))];
  const records = [];
  const known = new Set();
  ids.forEach(id => {
    const general = appState.generals.find(item => generalMatchesId(item, id));
    if (general) {
      const key = String(general.id ?? general.idHex ?? id);
      if (!known.has(key)) {
        known.add(key);
        records.push(general);
      }
      return;
    }
    const snapshot = configuredGeneralNameSnapshot(id);
    records.push({
      id,
      name: snapshot ? `${snapshot}（待同步）` : `#${id}（待同步）`,
      unresolved: true,
      fiefId: "",
      placeID: "",
    });
  });
  return records;
}
function generalOptionsHtml(selectedId = "", placeholder = "请选择") {
  const selected = String(selectedId || "");
  const selectedRecord = selected && !appState.generals.some(g => generalMatchesId(g, selected))
    ? [{
      id: selected,
      name: configuredGeneralNameSnapshot(selected)
        ? `${configuredGeneralNameSnapshot(selected)}（待同步）`
        : `#${selected}（待同步）`,
      unresolved: true,
    }]
    : [];
  const options = [...appState.generals, ...selectedRecord];
  if (!options.length) return `<option value="">请先登录/同步</option>`;
  const prefix = `<option value="" ${selected ? "" : "selected"}>${placeholder}</option>`;
  return prefix + options.map(g => {
    const name = g.name || `#${g.id}`;
    const selectedOption = generalMatchesId(g, selected);
    return `<option value="${escAttr(g.id)}" ${selectedOption ? "selected" : ""}>${escHtml(name)}</option>`;
  }).join("");
}
function rowGeneralIds(row) {
  if (Array.isArray(row?.generalIds)) {
    const ids = [...new Set(row.generalIds.map(x => String(x)).filter(Boolean))];
    if (ids.length) return ids;
  }
  return row?.generalId ? [String(row.generalId)] : [];
}
function generalTaskAnnotation(gid) {
  const parts = [];
  const form = (appState.formations || []).find(f => rowGeneralIds(f).includes(String(gid)) && Number(f.soldierCount || 0) > 0);
  if (form) parts.push(`配兵${Number(form.soldierCount || 0)}${form.soldierType || "兵"}`);
  const brushRows = Array.isArray(appState.brushSettings?.rows) ? appState.brushSettings.rows : [];
  const brushIdx = [];
  brushRows.forEach((r, idx) => {
    if (rowGeneralIds(r).includes(String(gid))) brushIdx.push(idx + 1);
  });
  if (!brushIdx.length && String(appState.brushSettings?.generalId || "") === String(gid)) brushIdx.push(1);
  if (brushIdx.length) parts.push(`刷黄${brushIdx.join("/")}`);
  const raidRows = Array.isArray(appState.raidSettings?.rows) ? appState.raidSettings.rows : [];
  const raidIdx = [];
  raidRows.forEach((r, idx) => {
    if (rowGeneralIds(r).includes(String(gid))) raidIdx.push(idx + 1);
  });
  if (raidIdx.length) parts.push(`掠夺${raidIdx.join("/")}`);
  return parts.length ? `（${parts.join("，")}）` : "";
}
function generalMultiLabel(g) {
  return `${g.name || `#${g.id}`}${generalTaskAnnotation(g.id)}`;
}
function formationGeneralSummary(ids) {
  const names = selectedGeneralRecords(ids).map(g => g.name || `#${g.id}`);
  if (!names.length) return "请选择将领";
  if (names.length <= 2) return names.join("、");
  return `${names.slice(0, 2).join("、")}等${names.length}个`;
}
function generalMultiSelectHtml(selectedIds = [], key = "", extraClass = "", maxSelected = 0) {
  const selectedOrder = [...new Set((selectedIds || []).map(x => String(x)).filter(Boolean))];
  const selected = new Set(selectedOrder);
  const selectedRecords = selectedGeneralRecords(selectedOrder);
  const records = [
    ...appState.generals,
    ...selectedRecords.filter(g => g.unresolved && !appState.generals.some(item => generalMatchesId(item, g.id))),
  ];
  if (!records.length) return `<div class="formation-general-multi empty">请先登录/同步</div>`;
  const items = records.map(g => {
    const id = String(g.id);
    const isSelected = selected.has(id) || selectedRecords.some(item => generalMatchesId(g, item.id));
    const fiefId = String(g.fiefId || g.placeID || "");
    return `<label class="formation-general-option ${isSelected ? "selected" : ""} ${g.unresolved ? "unresolved" : ""}" data-fief-id="${escAttr(fiefId)}">
      <span>${escHtml(generalMultiLabel(g))}</span>
      <input class="formation-general-check" type="checkbox" value="${escAttr(id)}" data-fief-id="${escAttr(fiefId)}" ${isSelected ? "checked" : ""}>
    </label>`;
  }).join("");
  return `<div class="formation-general-multi ${extraClass}" data-key="${escAttr(key)}" data-selected-order="${escAttr(selectedOrder.join(","))}" data-max-selected="${escAttr(maxSelected || "")}">
    <button class="formation-general-summary" type="button">${escHtml(formationGeneralSummary(selectedOrder))}</button>
    <div class="formation-general-panel">
      <input class="formation-general-search" type="text" placeholder="🔍  请输入关键字搜索">
      <div class="formation-general-actions"><button class="fg-all" type="button">全选</button><button class="fg-clear" type="button">清除</button></div>
      <div class="formation-general-list">${items}</div>
    </div>
  </div>`;
}
function formationGeneralMultiHtml(selectedIds = [], rowIndex = 0) {
  return generalMultiSelectHtml(selectedIds, `formation-${rowIndex}`, "formation-picker");
}
function militaryGeneralMultiHtml(selectedIds = [], key = "") {
  return generalMultiSelectHtml(selectedIds, `military-${key}`, "military-general-picker", 5);
}
function brushGeneralMultiHtml(selectedIds = [], rowIndex = 0) {
  return generalMultiSelectHtml(selectedIds, `brush-${rowIndex}`, "brush-general-picker", 5);
}
function simpleOptionsHtml(options, selected) {
  return options.map(x => `<option value="${escAttr(x)}" ${String(selected) === String(x) ? "selected" : ""}>${escHtml(x)}</option>`).join("");
}
function normalizeBrushDropValue(drop) {
  const text = String(drop || "").trim();
  if (brushDropOptions.includes(text)) return text;
  if (["铜钱", "粮食", "粮草", "资源类"].includes(text)) return "资源";
  return "";
}
function normalizeBrushDrops(value, fallback = defaultBrushDrops) {
  if (Array.isArray(value)) {
    const out = [...new Set(value.map(normalizeBrushDropValue).filter(Boolean))];
    return out;
  }
  const text = String(value || "").trim();
  if (!text) return fallback.slice();
  if (text === "不限") return brushDropOptions.slice();
  const out = [...new Set(text.split(/[,\uFF0C;；|\s]+/).map(normalizeBrushDropValue).filter(Boolean))];
  return out.length ? out : fallback.slice();
}
function firstBrushDrop(value) {
  return normalizeBrushDrops(value, [])[0] || "";
}
function normalizeBrushLevels(value, fallbackLevel = 1) {
  const raw = Array.isArray(value) ? value : [];
  const levels = [...new Set(raw.map(Number).filter(level => Number.isInteger(level) && brushLevelOptions.includes(level)))].sort((a, b) => a - b);
  if (levels.length) return levels;
  const fallback = Number(fallbackLevel);
  return Number.isInteger(fallback) && brushLevelOptions.includes(fallback) ? [fallback] : [1];
}
function brushLevelSummary(levels, level = 1) {
  const selected = normalizeBrushLevels(levels, level);
  if (selected.length <= 3) return `${selected.join("、")}级`;
  return `${selected.slice(0, 3).join("、")}等${selected.length}级`;
}
function brushLevelMultiHtml(levels, level = 1) {
  const selectedLevels = normalizeBrushLevels(levels, level);
  const selected = new Set(selectedLevels);
  const options = brushLevelOptions.map(value => `<label class="brush-level-option ${selected.has(value) ? "selected" : ""}">
    <span>${value}级山贼</span>
    <input class="brush-level-check" type="checkbox" value="${value}" ${selected.has(value) ? "checked" : ""}>
  </label>`).join("");
  return `<div class="brush-level-multi">
    <button class="brush-level-summary" type="button">${escHtml(brushLevelSummary(selectedLevels))}</button>
    <div class="brush-level-panel">
      <div class="brush-level-list">${options}</div>
    </div>
  </div>`;
}
function selectedBrushLevelsInRoot(root) {
  return normalizeBrushLevels(
    Array.from(root?.querySelectorAll(".brush-level-check:checked") || []).map(input => Number(input.value)),
    1,
  );
}
function syncBrushLevelMultiUi(root) {
  if (!root) return;
  const levels = selectedBrushLevelsInRoot(root);
  root.querySelectorAll(".brush-level-option").forEach(option => {
    option.classList.toggle("selected", !!option.querySelector(".brush-level-check")?.checked);
  });
  const summary = root.querySelector(".brush-level-summary");
  if (summary) summary.textContent = brushLevelSummary(levels);
}
function brushDropMultiHtml(drops) {
  const selected = new Set(normalizeBrushDrops(drops, defaultBrushDrops));
  return brushDropOptions.map(x => `<label class="drop-option"><input class="brush-drop" type="checkbox" value="${escAttr(x)}" ${selected.has(x) ? "checked" : ""}>${escHtml(x)}</label>`).join("");
}
function compositionDigitSelect(cls, value) {
  return `<select class="table-input brush-compose-select ${cls}">${simpleOptionsHtml(compositionDigitOptions, Number(value || 0))}</select>`;
}
function ensureDefaultGeneral() {
  if (!appState.generals.length) return;
  const firstFormation = appState.formations.find(f => f.enabled && rowGeneralIds(f).length) || appState.formations[0];
  const firstFormationId = rowGeneralIds(firstFormation)[0];
  if (!appState.brushSettings.generalId) appState.brushSettings.generalId = String(firstFormationId || appState.generals[0].id);
}
function readPolicyMultiValues(key) {
  const root = document.querySelector(`.policy-multi[data-policy="${key}"]`);
  if (!root) return null;
  return Array.from(root.querySelectorAll(".policy-multi-check:checked"))
    .map(input => String(input.value || "").trim())
    .filter(Boolean);
}

function commonSettingsScope(side = activeSide) {
  return {
    "常用": "common.frequent",
    "日常": "common.daily",
    "主号物品": "common.items",
  }[side] || "";
}

function selectedGeneralVisitIdsFromDom() {
  const inputs = Array.from(document.querySelectorAll(".general-visit-candidate-check"));
  if (!inputs.length) return normalizeGeneralVisitIds(appState.brushSettings.generalVisitGeneralIds);
  const checked = new Set(
    inputs.filter(input => input.checked).map(input => String(input.value || "")).filter(Boolean)
  );
  const ordered = normalizeGeneralVisitIds(appState.brushSettings.generalVisitGeneralIds)
    .filter(id => checked.has(id));
  inputs.forEach(input => {
    const id = String(input.value || "");
    if (input.checked && id && !ordered.includes(id) && ordered.length < 4) ordered.push(id);
  });
  return ordered.slice(0, 4);
}

function saveDailySettingsDom() {
  const b = appState.brushSettings;
  b.dailyTasks = { ...(b.dailyTasks || {}) };
  document.querySelectorAll(".daily-task-toggle").forEach(input => {
    b.dailyTasks[String(input.dataset.task || "")] = !!input.checked;
  });
  b.generalVisitGeneralIds = selectedGeneralVisitIdsFromDom();
}

function buildCommonSettingsPatch(side = activeSide) {
  if (side === "常用") {
    const technologyIds = readPolicyMultiValues("technology-ids");
    return {
      dailyLimit: Math.max(1, Math.min(500, Number(document.getElementById("commonDailyLimit")?.value || 500))),
      healWounded: !!document.getElementById("healWounded")?.checked,
      autoEnergy: !!document.getElementById("autoEnergy")?.checked,
      energyThreshold: Math.max(20, Math.min(100, Number(document.getElementById("energyThreshold")?.value || 20))),
      foodToCopper: !!document.getElementById("foodToCopper")?.checked,
      copperFloorWan: normalizeCopperFloor(document.getElementById("copperFloorWan")?.value),
      domestic: {
        enabled: !!document.getElementById("autoDomestic")?.checked,
        emptyBuildingType: Number(document.getElementById("emptyBuildingType")?.value || 1),
        upgradeTechnology: !!document.getElementById("upgradeTechnology")?.checked,
        technologyIds: (technologyIds || []).map(Number).filter(Number.isInteger),
      },
    };
  }
  if (side === "日常") {
    const dailyTasks = {};
    document.querySelectorAll(".daily-task-toggle").forEach(input => {
      dailyTasks[String(input.dataset.task || "")] = !!input.checked;
    });
    const generalVisitGeneralIds = selectedGeneralVisitIdsFromDom();
    return { dailyTasks, generalVisitGeneralIds };
  }
  if (side === "主号物品") {
    const discardItemNames = readPolicyMultiValues("discard-items") || [];
    const autoOpenItemNames = readPolicyMultiValues("auto-open-items") || [];
    const discardEquipment = !!document.getElementById("discardEquipment")?.checked;
    return {
      cleanInventory: discardItemNames.length > 0 || discardEquipment,
      discardItemNames: discardItemNames.join("，"),
      discardEquipment,
      maxEquipmentQuality: document.getElementById("maxEquipmentQuality")?.value || "良好",
      maxEquipmentLevel: Math.max(1, Math.min(100, Number(document.getElementById("maxEquipmentLevel")?.value || 20))),
      autoOpenEnabled: !!document.getElementById("autoOpenEnabled")?.checked,
      autoOpenItemNames,
    };
  }
  throw new Error(`当前子页面“${side}”没有可保存的设置`);
}

function saveSharedAutomationDom() {
  const b = appState.brushSettings;
  const reconnectDelayMinutes = document.getElementById("reconnectDelayMinutes");
  if (reconnectDelayMinutes) {
    b.reconnectDelayMinutes = Math.max(1, Math.min(1440, Number(reconnectDelayMinutes.value || 5)));
  }
  const autoEnergy = document.getElementById("autoEnergy");
  const energyThreshold = document.getElementById("energyThreshold");
  if (autoEnergy) b.autoEnergy = !!autoEnergy.checked;
  if (energyThreshold) b.energyThreshold = Number(energyThreshold.value || 20);
  const foodToCopper = document.getElementById("foodToCopper");
  const copperFloorWan = document.getElementById("copperFloorWan");
  if (foodToCopper) b.foodToCopper = !!foodToCopper.checked;
  if (copperFloorWan) b.copperFloorWan = normalizeCopperFloor(copperFloorWan.value);
  const autoDomestic = document.getElementById("autoDomestic");
  const emptyBuildingType = document.getElementById("emptyBuildingType");
  const upgradeBuildings = document.getElementById("upgradeBuildings");
  const upgradeTechnology = document.getElementById("upgradeTechnology");
  const technologyIds = readPolicyMultiValues("technology-ids");
  if (autoDomestic || emptyBuildingType || upgradeBuildings || upgradeTechnology || technologyIds !== null) {
    b.domestic = { ...defaultBrushSettings().domestic, ...(b.domestic || {}) };
    if (autoDomestic) b.domestic.enabled = !!autoDomestic.checked;
    if (emptyBuildingType) b.domestic.emptyBuildingType = Number(emptyBuildingType.value || 1);
    if (upgradeBuildings) b.domestic.upgradeBuildings = !!upgradeBuildings.checked;
    else b.domestic.upgradeBuildings = true;
    if (upgradeTechnology) b.domestic.upgradeTechnology = !!upgradeTechnology.checked;
    if (technologyIds !== null) b.domestic.technologyIds = technologyIds.map(Number).filter(Number.isInteger);
  }

  const discardNames = readPolicyMultiValues("discard-items");
  const autoOpenNames = readPolicyMultiValues("auto-open-items");
  const autoOpenEnabled = document.getElementById("autoOpenEnabled");
  const discardEquipment = document.getElementById("discardEquipment");
  const maxEquipmentQuality = document.getElementById("maxEquipmentQuality");
  const maxEquipmentLevel = document.getElementById("maxEquipmentLevel");
  if (discardNames !== null) b.discardItemNames = discardNames.join("，");
  if (autoOpenNames !== null) b.autoOpenItemNames = autoOpenNames;
  if (autoOpenEnabled) b.autoOpenEnabled = !!autoOpenEnabled.checked;
  if (discardEquipment) b.discardEquipment = !!discardEquipment.checked;
  if (maxEquipmentQuality) b.maxEquipmentQuality = maxEquipmentQuality.value || "良好";
  if (maxEquipmentLevel) b.maxEquipmentLevel = Number(maxEquipmentLevel.value || 20);
  if (discardNames !== null || discardEquipment) {
    b.cleanInventory = normalizePolicyNames(b.discardItemNames).length > 0 || !!b.discardEquipment;
  }
  const dailyToggles = Array.from(document.querySelectorAll(".daily-task-toggle"));
  if (dailyToggles.length) {
    saveDailySettingsDom();
  }
}
function saveBrushDom() {
  saveSharedAutomationDom();
  if (!document.getElementById("shStartX")) return;
  const b = appState.brushSettings;
  b.startHour = Number(document.getElementById("brushStartHour")?.value || 0);
  b.startX = Number(document.getElementById("shStartX")?.value || 0);
  b.startY = Number(document.getElementById("shStartY")?.value || 0);
  b.scanLimit = Number(document.getElementById("shScanLimit")?.value || 80);
  b.targetKind = document.getElementById("shTargetKind")?.value || "山贼";
  const rows = Array.from(document.querySelectorAll("tr.brush-rule-row"));
  const existingRows = brushRowsForDesign();
  b.rows = rows.map((tr, idx) => {
    const generalIds = selectedGeneralIdsInRoot(tr);
    const levels = selectedBrushLevelsInRoot(tr.querySelector(".brush-level-multi"));
    const maxFoot = Number(tr.querySelector(".brush-foot")?.value || 0);
    const maxBow = Number(tr.querySelector(".brush-bow")?.value || 0);
    const maxCavalry = Number(tr.querySelector(".brush-cavalry")?.value || 0);
    const maxChariot = Number(tr.querySelector(".brush-chariot")?.value || 0);
    const drops = normalizeBrushDrops(Array.from(tr.querySelectorAll(".brush-drop:checked")).map(el => el.value), []);
    return {
      enabled: !!tr.querySelector(".brush-enabled")?.checked,
      generalIds,
      generalId: generalIds[0] || "",
      levels,
      level: levels[0],
      drops,
      drop: drops[0] || "",
      maxFoot, maxBow, maxCavalry, maxChariot,
      compositionCode: `${maxFoot}${maxBow}${maxCavalry}${maxChariot}`,
      generalNameSnapshots: {
        ...(existingRows[idx]?.generalNameSnapshots || {}),
      },
      idx
    };
  });
  const active = b.rows.find(row => row.enabled && rowGeneralIds(row).length) || b.rows[0];
  const activeIds = rowGeneralIds(active);
  b.enabled = !!active?.enabled;
  b.levels = normalizeBrushLevels(active?.levels, active?.level);
  b.level = b.levels[0];
  b.drops = normalizeBrushDrops(active?.drops ?? active?.drop, []);
  b.drop = b.drops[0] || "";
  b.generalIds = activeIds;
  b.generalId = activeIds[0] || b.generalId || rowGeneralIds(appState.formations[0])[0] || "";
  b.maxFoot = Number(active?.maxFoot || 0);
  b.maxBow = Number(active?.maxBow || 0);
  b.maxCavalry = Number(active?.maxCavalry || 0);
  b.maxChariot = Number(active?.maxChariot || 0);
  b.requireFoot = !!document.getElementById("requireFoot")?.checked;
  b.compositionCode = active?.compositionCode || `${b.maxFoot}${b.maxBow}${b.maxCavalry}${b.maxChariot}`;
  b.dailyLimit = Number(document.getElementById("dailyLimit")?.value || b.dailyLimit || 500);
  b.cycleDelaySec = Number(document.getElementById("cycleDelaySec")?.value || b.cycleDelaySec || 10);
  b.returnWaitSec = Number(document.getElementById("returnWaitSec")?.value || b.returnWaitSec || 0);
  b.replenishTroops = !!document.getElementById("replenishTroops")?.checked;
  b.cleanMail = !!document.getElementById("cleanMail")?.checked;
}
function saveFormationDom() {
  const rows = Array.from(document.querySelectorAll("tr.formation-row"));
  const existingRows = formationRowsForDesign();
  appState.formationOptions = { clearOtherGenerals: false };
  if (!rows.length) return;
  appState.formations = rows.map((tr, idx) => ({
    enabled: !!tr.querySelector(".formation-enabled")?.checked,
    generalIds: selectedGeneralIdsInRoot(tr),
    generalId: selectedGeneralIdsInRoot(tr)[0] || "",
    soldierType: tr.querySelector(".formation-soldier")?.value || "轻骑兵",
    soldierCount: Number(tr.querySelector(".formation-count")?.value || 0),
    generalNameSnapshots: {
      ...(existingRows[idx]?.generalNameSnapshots || {}),
    },
    idx
  }));
  const first = appState.formations.find(f => f.enabled && rowGeneralIds(f).length) || appState.formations[0];
  const firstId = rowGeneralIds(first)[0];
  if (firstId) appState.brushSettings.generalId = String(firstId);
}
function saveRaidDom() {
  const root = document.querySelector(".raid-page");
  if (!root) return;
  const rows = Array.from(root.querySelectorAll(".raid-table tbody tr"));
  appState.raidSettings = {
    fullTroops: !!root.querySelector(".raid-full-troops")?.checked,
    duration: "立即出征",
    fullLoyalty: !!root.querySelector(".raid-full-loyalty")?.checked,
    rows: rows.map((tr, idx) => {
      const generalIds = selectedGeneralIdsInRoot(tr);
      return {
        enabled: !!tr.querySelector(".raid-enabled")?.checked,
        generalIds,
        generalId: generalIds[0] || "",
        playerName: String(tr.querySelector(".raid-player")?.value || "").trim(),
        fiefIndex: Number(tr.querySelector(".raid-fief-index")?.value || 0),
        idx
      };
    })
  };
}
function saveMineDom() {
  const root = document.querySelector(".mine-design-page");
  if (!root) return;
  appState.mineSettings = {
    speed: !!root.querySelector(".mine-speed")?.checked,
    fullLoyalty: !!root.querySelector(".mine-full-loyalty")?.checked,
    replenishTroops: !!root.querySelector(".mine-replenish-troops")?.checked,
    maxMarchMinutes: Number(root.querySelector(".mine-max-march-minutes")?.value || 45),
    centerX: Math.max(0, Math.min(186, Number(root.querySelector(".mine-center-x")?.value || 0))),
    centerY: Math.max(0, Math.min(66, Number(root.querySelector(".mine-center-y")?.value || 0))),
    rows: Array.from(root.querySelectorAll(".mine-table tbody tr")).map((tr, idx) => {
      const generalIds = selectedGeneralIdsInRoot(tr);
      return {
        enabled: !!tr.querySelector(".mine-enabled")?.checked,
        generalIds,
        generalId: generalIds[0] || "",
        resourceType: tr.querySelector(".mine-resource")?.value || "镔铁矿",
        x: Math.max(0, Math.min(186, Number(tr.querySelector(".mine-x")?.value || 0))),
        y: Math.max(0, Math.min(66, Number(tr.querySelector(".mine-y")?.value || 0))),
        scope: tr.querySelector(".mine-scope")?.value || "附近",
        idx
      };
    })
  };
}
function saveFutureMilitaryDom() {
  const settings = mergeMilitaryFutureSettings(appState.militaryFutureSettings);
  const readIds = tr => selectedGeneralIdsInRoot(tr);
  const losslessRoot = document.querySelector(".lossless-page");
  if (losslessRoot) {
    settings.lossless = {
      fullTroops: !!losslessRoot.querySelector(".lossless-full-troops")?.checked,
      rows: Array.from(losslessRoot.querySelectorAll(".lossless-table tbody tr")).map((tr, idx) => {
        const generalIds = readIds(tr);
        return {
          enabled: !!tr.querySelector(".lossless-enabled")?.checked,
          generalIds,
          generalId: generalIds[0] || "",
          level: tr.querySelector(".lossless-level")?.value || "10级",
          idx
        };
      })
    };
  }
  const dungeonRoot = document.querySelector(".dungeon-page");
  if (dungeonRoot) {
    enforceSingleDungeonEnabled(null, dungeonRoot);
    const dungeonRows = Array.from(dungeonRoot.querySelectorAll(".dungeon-table tbody tr"));
    const modeRow = dungeonRows.find(tr => tr.querySelector(".dungeon-enabled")?.checked)
      || dungeonRows.find(tr => dungeonClearModeSelected(tr.querySelector(".dungeon-chapter")?.value))
      || dungeonRows[0];
    settings.dungeon = {
      mode: dungeonClearModeSelected(modeRow?.querySelector(".dungeon-chapter")?.value) ? "clear" : "loop",
      rows: dungeonRows.map((tr, idx) => {
        const generalIds = readIds(tr);
        const chapterValue = tr.querySelector(".dungeon-chapter")?.value || "第四章";
        const clearMode = dungeonClearModeSelected(chapterValue);
        const chapter = clearMode ? "第一章" : dungeonChapterMeta(chapterValue).value;
        return {
          enabled: !!tr.querySelector(".dungeon-enabled")?.checked,
          generalIds,
          generalId: generalIds[0] || "",
          chapter,
          stage: clearMode ? "1" : normalizeDungeonStage(chapter, tr.querySelector(".dungeon-stage")?.value || "5"),
          chest: tr.querySelector(".dungeon-chest")?.value || "右",
          idx
        };
      })
    };
  }
  const escortRoot = document.querySelector(".escort-page");
  if (escortRoot) {
    settings.escort = {
      advancedFirst: !!escortRoot.querySelector(".escort-advanced")?.checked,
      fullTroops: !!escortRoot.querySelector(".escort-full-troops")?.checked,
      nationalCar: !!escortRoot.querySelector(".escort-national")?.checked,
      countryName: escortRoot.querySelector(".escort-country")?.value || "",
      rows: Array.from(escortRoot.querySelectorAll(".escort-table tbody tr")).map((tr, idx) => {
        const generalIds = readIds(tr);
        return {
          enabled: !!tr.querySelector(".escort-enabled")?.checked,
          generalIds,
          generalId: generalIds[0] || "",
          type: tr.querySelector(".escort-type")?.value || "史诗",
          idx
        };
      })
    };
  }
  const treasureRoot = document.querySelector(".treasure-hunt-page");
  if (treasureRoot) {
    settings.treasure = {
      useCount: Number(treasureRoot.querySelector(".treasure-use-count")?.value || 0),
      refreshCount: Number(treasureRoot.querySelector(".treasure-refresh-count")?.value || 0),
      fullTroops: !!treasureRoot.querySelector(".treasure-full-troops")?.checked,
      autoBuy: !!treasureRoot.querySelector(".treasure-auto-buy")?.checked,
      speed: treasureRoot.querySelector(".treasure-speed")?.value || "不加速",
      rows: Array.from(treasureRoot.querySelectorAll(".hunt-table tbody tr")).map((tr, idx) => {
        const generalIds = readIds(tr);
        return {
          enabled: !!tr.querySelector(".treasure-enabled")?.checked,
          generalIds,
          generalId: generalIds[0] || "",
          type: tr.querySelector(".treasure-type")?.value || "60级高级...",
          idx
        };
      })
    };
  }
  appState.militaryFutureSettings = settings;
}
function formationPlaceholderRow() {
  return { enabled: false, generalIds: [], generalId: "", soldierType: "民兵", soldierCount: 3000 };
}
function raidPlaceholderRow() {
  return { enabled: false, generalIds: [], generalId: "", playerName: "", fiefIndex: 1 };
}
function raidRowsForDesign() {
  const settings = appState.raidSettings || defaultRaidSettings();
  let rows = Array.isArray(settings.rows) && settings.rows.length ? settings.rows : defaultRaidSettings().rows;
  return rows.map((row, idx) => {
    let generalIds = rowGeneralIds(row);
    if (!generalIds.length && idx === 0 && appState.generals.length) generalIds = [String(generalIdAt(0))];
    return {
      enabled: row.enabled !== false,
      generalIds,
      generalId: generalIds[0] || "",
      playerName: row.playerName || "",
      fiefIndex: Number(row.fiefIndex || 1),
    };
  });
}
function brushPlaceholderRow() {
  return { enabled: false, generalIds: [], generalId: "", levels: [1], level: 1, drops: [...defaultBrushDrops], drop: defaultBrushDrops[0], maxFoot: 0, maxBow: 5, maxCavalry: 0, maxChariot: 0, compositionCode: "0500" };
}
function brushRowsForDesign() {
  const b = appState.brushSettings;
  if (Array.isArray(b.rows)) return b.rows.map(row => {
    const drops = normalizeBrushDrops(row.drops ?? row.drop, defaultBrushDrops);
    const levels = normalizeBrushLevels(row.levels, row.level);
    const generalIds = rowGeneralIds(row);
    return { ...row, generalIds, generalId: generalIds[0] || "", levels, level: levels[0], drops, drop: drops[0] || "" };
  });
  const drops = normalizeBrushDrops(b.drops ?? b.drop, defaultBrushDrops);
  const levels = normalizeBrushLevels(b.levels, b.level);
  const generalIds = rowGeneralIds(b);
  return [{
    enabled: b.enabled !== false,
    generalIds,
    generalId: generalIds[0] || "",
    levels,
    level: levels[0],
    drops,
    drop: drops[0] || "",
    maxFoot: Number(b.maxFoot ?? 0),
    maxBow: Number(b.maxBow ?? 5),
    maxCavalry: Number(b.maxCavalry || 0),
    maxChariot: Number(b.maxChariot || 0),
    compositionCode: b.compositionCode || "0500",
  }];
}
function formationRowsForDesign() {
  const grouped = [];
  const bySetting = new Map();
  (appState.formations || []).forEach(row => {
    const normalized = {
      enabled: !!row.enabled,
      generalIds: rowGeneralIds(row),
      soldierType: row.soldierType || "民兵",
      soldierCount: Number(row.soldierCount || 3000),
      generalNameSnapshots: {
        ...(row.generalNameSnapshots || {}),
      },
    };
    // Blank placeholders stay independent; configured rows with identical
    // troop type/count/enabled state share one multi-general picker.
    if (!normalized.generalIds.length) {
      grouped.push({ ...normalized, generalId: "" });
      return;
    }
    const key = `${normalized.enabled ? 1 : 0}|${normalized.soldierType}|${normalized.soldierCount}`;
    const existing = bySetting.get(key);
    if (existing) {
      existing.generalIds = [...new Set([...existing.generalIds, ...normalized.generalIds])];
      existing.generalId = existing.generalIds[0] || "";
      existing.generalNameSnapshots = {
        ...(existing.generalNameSnapshots || {}),
        ...normalized.generalNameSnapshots,
      };
      return;
    }
    const next = { ...normalized, generalId: normalized.generalIds[0] || "" };
    bySetting.set(key, next);
    grouped.push(next);
  });
  return grouped;
}
function discardActivePageChanges() {
  const saved = appState.accountUiState[appState.sessionId];
  if (!saved) return;
  const clone = value => JSON.parse(JSON.stringify(value));

  if (activeCategory === "刷黄") {
    appState.brushSettings = {
      ...defaultBrushSettings(),
      ...clone(saved.brushSettings || defaultBrushSettings())
    };
    return;
  }
  if (activeCategory === "打矿") {
    appState.mineSettings = clone(saved.mineSettings || defaultMineSettings());
    return;
  }
  if (activeCategory === "军事" || (activeCategory === "起号" && activeSide === "军队")) {
    if (activeSide === "配兵" || activeSide === "军队") {
      appState.formations = clone(saved.formations || []);
      appState.formationOptions = clone(saved.formationOptions || { clearOtherGenerals: false });
    } else if (activeSide === "掠夺") {
      appState.raidSettings = clone(saved.raidSettings || defaultRaidSettings());
    } else {
      const feature = militaryFutureFeatureMap[activeSide];
      if (feature) {
        const committed = mergeMilitaryFutureSettings(saved.militaryFutureSettings);
        appState.militaryFutureSettings = mergeMilitaryFutureSettings(appState.militaryFutureSettings);
        appState.militaryFutureSettings[feature] = clone(committed[feature]);
      }
    }
    return;
  }
  if (activeCategory !== "常规") return;

  const committed = {
    ...defaultBrushSettings(),
    ...clone(saved.brushSettings || defaultBrushSettings())
  };
  const current = appState.brushSettings;
  if (activeSide === "常用") {
    ["dailyLimit", "healWounded", "autoEnergy", "energyThreshold", "foodToCopper", "copperFloorWan"]
      .forEach(key => { current[key] = clone(committed[key]); });
    current.domestic = clone(committed.domestic);
  } else if (activeSide === "日常") {
    current.dailyTasks = clone(committed.dailyTasks);
    current.generalVisitGeneralIds = clone(committed.generalVisitGeneralIds || []);
  } else if (activeSide === "主号物品") {
    [
      "cleanInventory", "discardItemNames", "discardEquipment",
      "maxEquipmentQuality", "maxEquipmentLevel", "autoOpenEnabled", "autoOpenItemNames"
    ].forEach(key => { current[key] = clone(committed[key]); });
  }
}
function applyActiveBrushRuleOrThrow() {
  const b = appState.brushSettings;
  if (Array.isArray(b.rows)) {
    if (!b.rows.length) throw new Error("请先点击“添加编队”新增刷黄规则");
    if (b.rows.some(row => row.enabled && !rowGeneralIds(row).length)) throw new Error("已勾选的刷黄规则必须选择出征将领");
    const activeRow = b.rows.find(row => row.enabled && rowGeneralIds(row).length);
    if (!activeRow) throw new Error("刷黄规则左侧未勾选，请先勾选要启用的刷黄规则");
    const activeIds = rowGeneralIds(activeRow);
    const levels = normalizeBrushLevels(activeRow.levels, activeRow.level);
    Object.assign(b, {
      enabled: true,
      levels,
      level: levels[0],
      drops: normalizeBrushDrops(activeRow.drops ?? activeRow.drop, []),
      drop: firstBrushDrop(activeRow.drops ?? activeRow.drop),
      generalIds: activeIds,
      generalId: String(activeIds[0] || ""),
      maxFoot: Number(activeRow.maxFoot || 0),
      maxBow: Number(activeRow.maxBow || 0),
      maxCavalry: Number(activeRow.maxCavalry || 0),
      maxChariot: Number(activeRow.maxChariot || 0),
      compositionCode: activeRow.compositionCode || `${activeRow.maxFoot || 0}${activeRow.maxBow || 0}${activeRow.maxCavalry || 0}${activeRow.maxChariot || 0}`,
    });
    return activeRow;
  }
  if (!b.enabled) throw new Error("刷黄规则左侧未勾选，请先勾选要启用的刷黄规则");
  return null;
}
function buildAutoConfig({ settingsOnly = false } = {}) {
  saveBrushDom(); ensureDefaultGeneral();
  const b = appState.brushSettings;
  const enabledRows = Array.isArray(b.rows)
    ? b.rows.filter(row => row.enabled)
    : (b.enabled ? [b] : []);
  const autoStart = enabledRows.length > 0 && (!settingsOnly || Array.isArray(b.rows));
  if (autoStart) {
    applyActiveBrushRuleOrThrow();
  } else {
    b.enabled = false;
  }
  const selectedFormation = appState.formations.find(f => f.enabled && rowGeneralIds(f).length) || appState.formations[0];
  const selectedFormationId = rowGeneralIds(selectedFormation)[0] || "";
  if (selectedFormationId && !b.generalId) b.generalId = String(selectedFormationId);
  return {
    sessionId: appState.sessionId,
    autoStart,
    reconnectDelayMinutes: Math.max(1, Math.min(1440, Number(b.reconnectDelayMinutes || 5))),
    startHour: Number(b.startHour || 0),
    dailyLimit: Number(b.dailyLimit || 500),
    cycleDelaySec: Number(b.cycleDelaySec || 10),
    returnWaitSec: Number(b.returnWaitSec || 0),
    healWounded: b.healWounded !== false,
    replenishTroops: !!b.replenishTroops,
    autoEnergy: !!b.autoEnergy,
    energyThreshold: Number(b.energyThreshold || 20),
    foodToCopper: !!b.foodToCopper,
    copperFloorWan: normalizeCopperFloor(b.copperFloorWan),
    cleanMail: !!b.cleanMail,
    cleanInventory: !!b.cleanInventory,
    discardItemNames: String(b.discardItemNames || ""),
    discardEquipment: !!b.discardEquipment,
    maxEquipmentQuality: b.maxEquipmentQuality || "良好",
    maxEquipmentLevel: Number(b.maxEquipmentLevel || 20),
    autoOpenItemNames: normalizePolicyNames(b.autoOpenItemNames),
    autoOpenEnabled: !!b.autoOpenEnabled,
    domestic: { ...defaultBrushSettings().domestic, ...(b.domestic || {}) },
    dailyTasks: { ...(b.dailyTasks || {}) },
    generalVisitGeneralIds: normalizeGeneralVisitIds(b.generalVisitGeneralIds),
    brush: {
      startX: Number(b.startX || 0), startY: Number(b.startY || 0), scanLimit: Number(b.scanLimit || 80),
      targetKind: b.targetKind || "山贼",
      levels: normalizeBrushLevels(b.levels, b.level),
      level: normalizeBrushLevels(b.levels, b.level)[0],
      generalId: String(b.generalId || selectedFormationId || ""),
      drops: normalizeBrushDrops(b.drops ?? b.drop, []),
      drop: firstBrushDrop(b.drops ?? b.drop),
      rows: Array.isArray(b.rows) ? b.rows.map(row => {
        const ids = rowGeneralIds(row);
        const levels = normalizeBrushLevels(row.levels, row.level);
        return { ...row, generalIds: ids, generalId: String(ids[0] || ""), levels, level: levels[0] };
      }) : [],
      compositionCode: b.compositionCode || `${b.maxFoot}${b.maxBow}${b.maxCavalry}${b.maxChariot}`,
      compositionFilter: { maxFoot: Number(b.maxFoot || 0), maxBow: Number(b.maxBow || 0), maxCavalry: Number(b.maxCavalry || 0), maxChariot: Number(b.maxChariot || 0), requireFoot: !!b.requireFoot }
    }
  };
}

function renderShuaHuang() {
  ensureDefaultGeneral();
  const b = appState.brushSettings;
  const brushRows = brushRowsForDesign();
  const rowsHtml = brushRows.length ? brushRows.map((row, i) => `<tr class="brush-rule-row">
          <td class="brush-enabled-cell"><input class="brush-enabled" type="checkbox" ${row.enabled ? "checked" : ""} title="勾选后启用这一条刷黄规则" aria-label="启用此刷黄编队"/></td>
          <td>${brushGeneralMultiHtml(rowGeneralIds(row), i)}</td>
          <td>${brushLevelMultiHtml(row.levels, row.level)}</td>
          <td><div class="drop-multi-cell">${brushDropMultiHtml(row.drops ?? row.drop)}</div></td>
          <td class="composition-cell">
            ${compositionDigitSelect("brush-foot", row.maxFoot)}
            ${compositionDigitSelect("brush-bow", row.maxBow)}
            ${compositionDigitSelect("brush-cavalry", row.maxCavalry)}
            ${compositionDigitSelect("brush-chariot", row.maxChariot)}
          </td>
          <td><button class="table-btn brush-delete" data-index="${i}" type="button">删除</button></td>
        </tr>`).join("") : `<tr><td colspan="6" class="empty-rule-cell">暂无刷黄编队，请点击“添加编队”新增空白编队</td></tr>`;
  return h`<div class="panel-box form-grid shua-panel prototype-shua">
    <input id="shTargetKind" type="hidden" value="${escAttr(b.targetKind || "山贼")}"/>
    <input id="shScanLimit" type="hidden" value="${escAttr(b.scanLimit || 80)}"/>
    <input id="dailyLimit" type="hidden" value="${escAttr(b.dailyLimit || 500)}"/>
    <input id="cycleDelaySec" type="hidden" value="${escAttr(b.cycleDelaySec || 10)}"/>
    <input id="returnWaitSec" type="hidden" value="${escAttr(b.returnWaitSec || 0)}"/>
    <input id="requireFoot" type="checkbox" ${b.requireFoot ? "checked" : ""} hidden/>
    <div class="form-row sh-row">开始时间：<select id="brushStartHour" class="small-input">${simpleOptionsHtml(Array.from({length: 24}, (_, i) => i), Number(b.startHour || 0))}</select><span>点</span></div>
    <div class="form-row sh-row">中心坐标：<span>x=</span><input id="shStartX" class="input coord-input" type="number" min="0" max="186" value="${b.startX}"/><span>y=</span><input id="shStartY" class="input coord-input" type="number" min="0" max="66" value="${b.startY}"/></div>
    <div class="form-row sh-row">加速：<input class="input speed-input" value="不加速"/><label class="refill-toggle"><span>批量补满</span><input id="replenishTroops" type="checkbox" ${b.replenishTroops === true ? "checked" : ""}/></label></div>
    <div class="brush-maintenance">
      <label><input id="foodToCopper" type="checkbox" ${b.foodToCopper !== false ? "checked" : ""}><span>粮食转铜</span><select id="copperFloorWan" class="maintenance-number">${simpleOptionsHtml(copperFloorOptions, normalizeCopperFloor(b.copperFloorWan))}</select><span>万保底</span></label>
      <label><input id="cleanMail" type="checkbox" ${b.cleanMail ? "checked" : ""}><span>清空邮件</span></label>
    </div>
    <table class="grid-table brush-config-table">
      <thead><tr><th><input id="toggleAllBrushRules" type="checkbox" aria-label="全选或取消全部刷黄编队"></th><th>出征将领</th><th>山贼等级</th><th>掉落</th><th>步弓骑车</th><th>操作</th></tr></thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
    <div class="table-actions formation-design-actions two-actions"><button class="add" id="addBrushRuleBtn" type="button">+添加编队</button><button class="delete" id="clearBrushRulesBtn" type="button">🗑 一键删除</button></div>
  </div>${note("添加编队：新增一个空白刷黄编队，需要手动勾选并选择将领、山贼等级、掉落多选和步弓骑车<br/>掉落可同时勾选宝物/资源/装备/宝箱，匹配任意一种即可；步弓骑车 4 个下拉框的范围都是 0-5；一键删除会清空全部刷黄编队")}`;
}
function renderMilitary() {
  if (activeSide === "配兵") {
    ensureDefaultGeneral();
    const rows = formationRowsForDesign().map((f, i) => `<tr class="formation-row">
      <td class="formation-check-cell"><input class="formation-enabled" type="checkbox" ${f.enabled ? "checked" : ""}></td>
      <td>${formationGeneralMultiHtml(f.generalIds, i)}</td>
      <td><select class="table-input formation-soldier">
        ${soldierTypes.map(x=>`<option ${f.soldierType===x?"selected":""}>${x}</option>`).join("")}
      </select></td>
      <td><input class="table-input formation-count" value="${escAttr(f.soldierCount || 3000)}"></td>
      <td><button class="table-btn formation-delete" data-index="${i}">删除</button></td>
    </tr>`).join("");
    return h`<div class="panel-box form-grid formation-design-panel">
      <div class="formation-army-panel">
        ${armyTableHtml()}
        <button class="unassign-all-btn" id="unassignAllTroopsBtn" type="button"><span class="unassign-spinner">↻</span> 一键卸兵</button>
      </div>
      <table class="grid-table formation-design-table"><thead><tr><th></th><th>出征将领</th><th>类型</th><th>数量</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="table-actions formation-design-actions two-actions"><button class="add" id="addFormationBtn">+添加编队</button><button class="delete" id="clearFormationBtn">🗑 一键删除</button></div>
      <div class="note-box formation-design-note"><div class="note-title">说明:</div>出征将领支持多选；名字后括号显示该将领当前保存的配兵设置和刷黄编队位置<br/>若目标兵种闲兵不足，系统会中止该将领配兵并保持原配兵不变</div>
    </div>`;
  }
  if (activeSide === "掠夺") {
    ensureDefaultGeneral();
    const raid = appState.raidSettings || defaultRaidSettings();
    const rows = raidRowsForDesign().map((row, i) => ([
      `<input class="design-check raid-enabled" type="checkbox" ${row.enabled ? "checked" : ""}>`,
      militaryGeneralMultiHtml(row.generalIds, `raid-${i}`),
      dInput(row.playerName || "天雄星", "table-text raid-player"),
      dInput(row.fiefIndex || 10, "table-num raid-fief-index", "number"),
      `<button class="table-btn dynamic-delete" type="button">删除</button>`
    ]));
    return h`
    <div class="design-page military-design-page raid-page">
      <div class="design-card design-setting-card military-top-card">
        ${designRow("满兵：", `${dCheck(raid.fullTroops !== false, "raid-full-troops")}<span>出征方式：</span><span class="design-static-text">立即出征</span>`)}
        ${designRow("满忠：", dCheck(!!raid.fullLoyalty, "raid-full-loyalty"))}
      </div>
      ${designTable(["", "出征将领", "玩家名称", "封地序号", "操作"], rows, "military-table pill-table raid-table")}${actionButtons()}
      ${note("保存后会按“玩家名称 + 封地序号”查询目标封地，再发送 0x1520/0x1522 普通立即掠夺出征。<br/>将领必须为“闲”、体力可靠且当前有兵；勾选满兵会先请求批量补满当前兵种。")}
    </div>`;
  }
  if (activeSide === "抢城") return h`
    <div class="design-page military-design-page">
      <div class="design-card design-setting-card military-top-card">
        ${designRow("满兵：", dCheck(true))}
      </div>
      ${designTable(["", "出征将领", "类型", "操作"], [[
        dCheck(false),
        militaryGeneralMultiHtml([generalIdAt(1), generalIdAt(2)].filter(Boolean), "city-0"),
        dSelect(["长安、洛阳", "长安", "洛阳", "襄阳", "成都"], "长安、洛阳", "table-select"),
        `<button class="table-btn dynamic-delete" type="button">删除</button>`
      ]], "military-table city-table")}${actionButtons()}
      ${note("抢城兵力设置最低1200(冲车不能低于200)")}
    </div>`;
  if (activeSide === "无损") {
    ensureDefaultGeneral();
    const lossless = mergeMilitaryFutureSettings(appState.militaryFutureSettings).lossless;
    const rows = (Array.isArray(lossless.rows) && lossless.rows.length ? lossless.rows : defaultMilitaryFutureSettings().lossless.rows).map((row, i) => {
      let ids = rowGeneralIds(row);
      if (!ids.length && i === 0 && appState.generals.length) ids = [String(generalIdAt(2) || generalIdAt(0) || "")].filter(Boolean);
      return [
        `<input class="design-check lossless-enabled" type="checkbox" ${row.enabled === true ? "checked" : ""}>`,
        militaryGeneralMultiHtml(ids, `lossless-${i}`),
        dSelect(["1级","2级","3级","4级","5级","6级","7级","8级","9级","10级"], row.level || "10级", "table-select lossless-level"),
        `<button class="table-btn dynamic-delete" type="button">删除</button>`
      ];
    });
    return h`
    <div class="design-page military-design-page lossless-page">
      <div class="design-card design-setting-card military-top-card">
        ${designRow("满兵：", dCheck(lossless.fullTroops === true, "lossless-full-troops"))}
      </div>
      ${designTable(["", "出征将领", "无损等级", "操作"], rows, "military-table lossless-table")}${actionButtons()}
      ${note("无损是常驻任务，每日最多5次；失败或完成都会消耗1次。按卫兵、小队长、大队长、头目、首领推进。<br/>10级卫兵会自动筛选至少3名战车敌军且投石车排在其他战车之后；共享将领按“无损 > 刷黄 > 副本”由指挥中心安排。")}
    </div>`;
  }
  if (activeSide === "副本") {
    ensureDefaultGeneral();
    const dungeon = mergeMilitaryFutureSettings(appState.militaryFutureSettings).dungeon;
    const savedRows = Array.isArray(dungeon.rows) ? dungeon.rows : defaultMilitaryFutureSettings().dungeon.rows;
    const sourceRows = savedRows.length
      ? savedRows
      : [{ ...defaultMilitaryFutureSettings().dungeon.rows[0], enabled: false }];
    const enabledRowIndex = sourceRows.findIndex(row => row.enabled === true);
    const clearModeRowIndex = dungeon.mode === "clear"
      ? (enabledRowIndex >= 0 ? enabledRowIndex : 0)
      : -1;
    const rows = sourceRows.map((row, i) => {
      let ids = rowGeneralIds(row);
      if (!ids.length && i === 0 && appState.generals.length) ids = [String(generalIdAt(0) || "")].filter(Boolean);
      const chapter = i === clearModeRowIndex
        ? dungeonClearModeOption
        : dungeonChapterMeta(row.chapterName || row.chapter || "第四章").value;
      const stage = normalizeDungeonStage(chapter, row.stage || "5");
      return [
        `<input class="design-check dungeon-enabled" type="checkbox" ${i === enabledRowIndex ? "checked" : ""}>`,
        militaryGeneralMultiHtml(ids, `dungeon-${i}`),
        dSelect([...dungeonChapters.map(item => item.value), dungeonClearModeOption], chapter, "table-select dungeon-chapter"),
        `<select class="design-select table-select dungeon-stage" ${dungeonClearModeSelected(chapter) ? "disabled" : ""}>${simpleOptionsHtml(dungeonStageOptions(chapter), stage)}</select>`,
        dSelect(["左", "中", "右"], row.chest || "右", "table-select dungeon-chest"),
        `<button class="table-btn dynamic-delete" type="button">删除</button>`
      ];
    });
    const pauseNote = dungeon.pausedAfterDefeat?.paused
      ? `<br><span class="daily-task-note">上次因战败已暂停：${escHtml(dungeon.pausedAfterDefeat.reason || "战败")}；重新保存本页后才会继续。</span>`
      : "";
    return h`
    <div class="design-page military-design-page dungeon-page">
      ${designTable(["", "出征将领", "章节", "关卡", "开箱", "操作"], rows, "military-table dungeon-table")}${actionButtons()}
      ${note(`副本编队同一时间最多启用一条；全部不勾选并保存时关闭副本任务。选择具体章节时循环刷选定关卡；在“章节”选择“${dungeonClearModeOption}”后，“关卡”会同步显示打通模式，并按服务器目录从首个未通关关卡逐关推进。${pauseNote}`)}
    </div>`;
  }
  if (activeSide === "押镖") {
    ensureDefaultGeneral();
    const escort = mergeMilitaryFutureSettings(appState.militaryFutureSettings).escort;
    const rows = (Array.isArray(escort.rows) && escort.rows.length ? escort.rows : defaultMilitaryFutureSettings().escort.rows).map((row, i) => {
      let ids = rowGeneralIds(row);
      if (!ids.length && i === 0 && appState.generals.length) ids = [String(generalIdAt(0) || "")].filter(Boolean);
      return [
        `<input class="design-check escort-enabled" type="checkbox" ${row.enabled !== false ? "checked" : ""}>`,
        militaryGeneralMultiHtml(ids, `escort-${i}`),
        dSelect(["史诗", "高级", "普通"], row.type || "史诗", "table-select escort-type"),
        `<button class="table-btn dynamic-delete" type="button">删除</button>`
      ];
    });
    return h`
    <div class="design-page military-design-page escort-page">
      <div class="design-card design-setting-card military-top-card">
        ${designRow("高级优先：", `${dCheck(escort.advancedFirst !== false, "escort-advanced")}<span>满兵：</span>${dCheck(escort.fullTroops !== false, "escort-full-troops")}`)}
        ${designRow("国家镖车：", `${dCheck(escort.nationalCar !== false, "escort-national")}${dInput(escort.countryName || "美国", "w-long escort-country")}`)}
      </div>
      ${designTable(["", "出征将领", "类型", "操作"], rows, "military-table escort-table")}${actionButtons()}
      ${note("押镖如果受到玩家攻击，会自动撤军；真实发起押镖仍需补抓“选择镖车/发车/撤军或结束”的完整接口。")}
    </div>`;
  }
  if (activeSide === "寻宝") {
    ensureDefaultGeneral();
    const treasure = mergeMilitaryFutureSettings(appState.militaryFutureSettings).treasure;
    const rows = (Array.isArray(treasure.rows) && treasure.rows.length ? treasure.rows : defaultMilitaryFutureSettings().treasure.rows).map((row, i) => {
      let ids = rowGeneralIds(row);
      if (!ids.length && i === 0 && appState.generals.length) ids = [String(generalIdAt(0) || "")].filter(Boolean);
      return [
        `<input class="design-check treasure-enabled" type="checkbox" ${row.enabled !== false ? "checked" : ""}>`,
        militaryGeneralMultiHtml(ids, `hunt-${i}`),
        dSelect(["60级高级...", "30级普通", "40级高级", "80级高级"], row.type || "60级高级...", "table-select treasure-type"),
        `<button class="table-btn dynamic-delete" type="button">删除</button>`
      ];
    });
    return h`
    <div class="design-page military-design-page treasure-hunt-page">
      <div class="design-card design-setting-card military-top-card">
        ${designRow("使用次数：", `${dInput(treasure.useCount ?? 10, "num-compact treasure-use-count", "number")}<span>次</span>`)}
        ${designRow("每次刷新藏宝图的个数：", dInput(treasure.refreshCount ?? 10, "num-wide treasure-refresh-count", "number"))}
        ${designRow("满兵：", `${dCheck(treasure.fullTroops !== false, "treasure-full-troops")}<span>自动购买藏宝图：</span>${dCheck(!!treasure.autoBuy, "treasure-auto-buy")}`)}
        ${designRow("加速：", dSelect(["不加速", "初级行军符", "中级行军符", "高级行军符"], treasure.speed || "不加速", "w-short treasure-speed"))}
      </div>
      ${designTable(["", "出征将领", "宝藏类型", "操作"], rows, "military-table hunt-table")}${actionButtons()}
      ${note("使用次数：每天使用藏宝图的最大次数<br/>建议加速出征，否则有可能撞车<br/>真实寻宝仍需补抓“刷新藏宝图/选宝藏/发起寻宝/结果”的完整接口。")}
    </div>`;
  }
}
function renderJunqing() {
  const intel = appState.militaryIntel || { events: [], statusByName: {} };
  const events = (intel.events || []).filter(e => e.text);
  const busy = (appState.generals || []).filter(g => statusLabel(g.displayStatus || g.statusText || intel.statusByName?.[g.name]) !== "闲");
  const timeText = new Date(intel.updatedAt || Date.now()).toLocaleTimeString("zh-CN", { hour12: false });
  const feedItems = events.length
    ? events.map(e => ({
        time: e.timeText || e.time || timeText,
        text: e.text,
      }))
    : busy.map(g => ({
        time: timeText,
        text: `【${statusLabel(g.displayStatus || g.statusText)}】${g.name || g.id}${g.soldierType ? "，" + g.soldierType : ""}${g.soldierCount ? " " + fmtNum(g.soldierCount) : ""}`,
      }));
  const body = feedItems.length
    ? feedItems.map(item => `<div class="junqing-item"><div class="junqing-time">${escHtml(item.time)}</div><div class="junqing-text">${escHtml(item.text)}</div></div>`).join("")
    : `<div class="junqing-empty">暂无出征/返回军情</div>`;
  return h`<div class="junqing-page">
    <button class="table-btn live-btn blue-live junqing-hidden-refresh" id="refreshStateBtn" type="button">立即刷新</button>
    <div class="junqing-feed">${body}</div>
  </div>`;
}
function roleStatusTableHtml() {
  const effects = appState.roleState?.statusEffects || appState.roleState?.effects || [];
  const byName = new Map((effects || []).map(e => [String(e.name || e.label || ""), e]));
  const rows = roleStatusNames.map(name => {
    const effect = byName.get(name) || {};
    const mins = effect.remainingMinutes ?? effect.minutes ?? effect.remaining ?? 0;
    const label = typeof mins === "string" ? mins : `${fmtNum(mins || 0)}分钟`;
    return [escHtml(name), escHtml(label)];
  });
  return table(["名称", "剩余时间"], rows, "status-table");
}
function armyTableHtml() {
  const rows = (appState.army || appState.roleState?.idleArmy || [])
    .filter(x => Number(x.idleCount ?? x.count ?? x.amount ?? 0) > 0 || Number(x.woundedCount ?? x.hurtSoldierCount ?? 0) > 0)
    .map(x => [
      escHtml(x.soldierType || (x.soldierTypeCode !== undefined ? `兵种${x.soldierTypeCode}` : "未知")),
      fmtNum(x.idleCount ?? x.count ?? x.amount ?? 0),
      fmtNum(x.woundedCount ?? x.hurtSoldierCount ?? 0),
      escHtml(x.fiefName || (x.fiefId ? `封地${x.fiefId}` : "基地")),
    ]);
  return rows.length
    ? table(["兵种", "闲兵数量", "伤兵数量", "封地"], rows, "army-design-table")
    : table(["实时军队数据"], [["当前账号未解析到闲兵信息"]]);
}
function renderRole() {
  const rs = liveRoleState();
  const role = appState.role || {};
  if (!appState.sessionId && activeSide !== "状态") {
    return table(["", ""], [["实时数据", "请先点击“添加”登录账号"]], "role-info-table");
  }
  if (activeSide === "角色") {
    const stats = appState.dailyStats || {};
    const queues = appState.roleQueueSummary || {};
    const queueProgress = queue => {
      const current = Number(queue?.current);
      const capacity = Number(queue?.capacity);
      return Number.isFinite(current) && Number.isFinite(capacity)
        ? `${fmtNum(current)} / ${fmtNum(capacity)}`
        : "-";
    };
    const rows = [
      ["君主", escHtml(rs.roleName || role.roleName || "-")],
      ["账号", escHtml(appState.username || "-")],
      ["服务器", escHtml(appState.area?.areaName || appState.area?.serverKey || "-")],
      ["等级", escHtml(rs.level ?? role.level ?? "-")],
      ["国家", escHtml(role.country || rs.nation || role.title || "-")],
      ["官阶", escHtml(rs.officeName || role.officeName || "-")],
      ["铜钱", `${fmtNum(rs.copper)}${rs.copperPerHour !== undefined ? `（+${fmtNum(rs.copperPerHour)}/小时）` : ""}`],
      ["粮食", `${fmtNum(rs.food)}${rs.foodPerHour !== undefined ? `（+${fmtNum(rs.foodPerHour)}/小时）` : ""}`],
      ["声望", fmtNum(rs.prestige)],
      ["人口", `${fmtNum(rs.populationCurrent)} / ${fmtNum(rs.populationCap)}`],
      ["资源点", `${fmtNum(rs.resourcePointCurrent)} / ${fmtNum(rs.resourcePointCap)}`],
      ["宝藏", escHtml(stats.treasureProgress || fmtProgress(stats.treasureOccupied, stats.treasureLimit))],
      ["建筑队列", queueProgress(queues.buildingQueue)],
      ["研究队列", queueProgress(queues.researchQueue)],
    ];
    return `<div class="role-overview-tables">
      <section>${table(["", ""], rows, "role-info-table")}</section>
      <section>${roleStatusTableHtml()}</section>
    </div>`;
  }
  if (activeSide === "英雄") {
    const rows = (appState.generals || []).map(g => {
      const status = statusLabel(g.displayStatus || g.statusText || g.status);
      const fiefName = String(g.fiefName || g.cityName || "").trim();
      const shortFiefName = fiefName ? `${Array.from(fiefName)[0]}.` : "-";
      const soldierCount = Number(g.soldierCount ?? g.currentSoldierCount ?? 0);
      const soldierType = soldierCount > 0
        ? String(g.soldierType || (g.soldierTypeCode !== undefined ? `兵种${g.soldierTypeCode}` : "")).trim()
        : "无兵";
      const shortSoldierType = soldierType === "无配兵" || soldierType === "未配兵"
        ? "无兵"
        : Array.from(soldierType).slice(0, 2).join("");
      return {
        className: soldierCount > 0 ? "has-troops" : "no-troops",
        cells: [
          escHtml(g.name || g.id || "-"),
          `<span class="hero-status ${status === "闲" ? "is-idle" : "is-busy"}">${escHtml(status)}</span>`,
          `<span title="${escAttr(fiefName || "未解析到封地名称")}">${escHtml(shortFiefName)}</span>`,
          escHtml(g.kind || ""),
          escHtml(g.level ?? ""),
          `${fmtNum(g.tili)}${g.tiliLimit ? "/" + fmtNum(g.tiliLimit) : ""}`,
          `${fmtNum(g.loyalty)}${g.loyaltyLimit ? "/" + fmtNum(g.loyaltyLimit) : ""}`,
          `${fmtNum(g.soldierCount ?? g.currentSoldierCount)}${g.troopLimit ? "/" + fmtNum(g.troopLimit) : ""}`,
          `<span title="${escAttr(soldierType || "未解析到兵种")}">${escHtml(shortSoldierType || "-")}</span>`,
        ],
      };
    });
    if (!rows.length) return table(["实时英雄数据"], [["当前账号未解析到将领，请重新登录同步"]]);
    const headers = ["将", "态", "封地", "类", "级", "体", "忠", "统/兵", "兵种"];
    return `<div class="hero-table-scroll">
      <table class="grid-table hero-data-table">
        <thead><tr>${headers.map(value => `<th>${value}</th>`).join("")}</tr></thead>
        <tbody>${rows.map(row => `<tr class="hero-data-row ${row.className}">${row.cells.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>`;
  }
  if (activeSide === "宝物") {
    const items = appState.inventory?.items || [];
    const ownedItems = items.filter(it => Number(it.count ?? 0) > 0);
    const query = treasureSearchQuery.trim().toLocaleLowerCase();
    const visibleItems = ownedItems.filter(it => {
      const name = String(it.name || `道具#${it.itemId ?? it.id}`);
      return !query || name.toLocaleLowerCase().includes(query);
    });
    const rows = visibleItems
      .map(it => [escHtml(it.name || `道具#${it.itemId ?? it.id}`), fmtNum(it.count)]);
    if (!ownedItems.length) {
      return table(["实时宝物数据"], [[appState.inventory?.parseError ? escHtml(appState.inventory.parseError) : "当前账号背包为空或暂未解析到 0x8104 背包数据"]]);
    }
    const countText = query
      ? `找到 ${visibleItems.length} 种 / 共 ${ownedItems.length} 种宝物`
      : `共 ${ownedItems.length} 种宝物`;
    return `<section class="treasure-browser">
      <div class="treasure-toolbar">
        <label class="treasure-search">
          <span aria-hidden="true">⌕</span>
          <input id="treasureSearchInput" type="search" value="${escAttr(treasureSearchQuery)}" placeholder="搜索宝物名称" autocomplete="off">
        </label>
        <span id="treasureCount" class="treasure-count">${countText}</span>
      </div>
      <div class="treasure-table-scroll">
        ${rows.length
          ? table(["名称", "数量"], rows, "treasure-table")
          : `<div class="treasure-empty">没有找到匹配的宝物</div>`}
      </div>
    </section>`;
  }
  if (activeSide === "任务") {
    const overview = appState.taskOverview || {};
    const schedulerStateNames = {
      checking: "检查中",
      ready: "准备执行",
      dispatching: "正在下发",
      fighting: "执行中",
      cooldown: "冷却",
      waiting_account: "等账号",
      waiting_generals: "等将领",
      waiting_priority: "等优先任务",
      waiting_target: "等目标",
      daily_done: "今日完成",
      disabled: "未启用",
      stopped: "已停止",
      error: "异常",
      running: "执行中",
      starting: "启动中",
      queued: "排队中",
      stopping: "停止中",
    };
    const residentDefaults = [
      ["dungeon", "副本"], ["brushYellow", "刷黄"], ["mine", "打矿"], ["raid", "掠夺"],
      ["siege", "抢城"], ["lossless", "无损"], ["escort", "押镖"], ["treasure", "寻宝"],
    ];
    const dailyDefaults = [
      ["autoSignIn", "自动签到"], ["arenaCoins", "领竞技币"],
      ["autoDonate", "自动捐献"], ["salary", "领取俸禄"],
      ["nationalCollect", "国家征收"], ["cityLordCollect", "城主征收"],
      ["generalVisit", "名将拜访"],
    ];
    const residentByKey = new Map((overview.resident || []).map(item => [item.key, item]));
    const dailyByKey = new Map((overview.daily || []).map(item => [item.key, item]));
    const startSavedTasksButton = overview.savedTasksStarted
      ? ""
      : `<button id="startSavedTasksBtn" class="table-btn start-saved-tasks-btn" type="button">开始执行任务</button>`;
    const taskStackItems = (overview.taskStack || []).map(item => {
      const stateName = schedulerStateNames[item.state] || schedulerStateNames[item.status] || item.state || "等待";
      const cooldown = item.state === "cooldown" ? taskCooldownHtml(item.cooldownUntil) : "";
      const remaining = item.key === "lossless" && item.remainingAttempts !== null && item.remainingAttempts !== undefined
        ? `今日剩余 ${fmtNum(item.remainingAttempts)}/5 次`
        : "";
      const detail = item.state === "cooldown"
        ? remaining
        : [item.message, remaining].filter(Boolean).join("；");
      const stateHtml = cooldown || `<span class="task-stack-state">${escHtml(stateName)}</span>`;
      return `<div class="task-stack-item ${item.current ? "is-current" : ""} ${item.state === "cooldown" ? "is-cooldown" : ""}">
        <span class="task-stack-position">${fmtNum(item.position)}</span>
        <div class="task-stack-body">
          <div class="task-stack-name">${escHtml(item.name || "后台任务")}</div>
          <div class="task-stack-detail">${escHtml(detail || stateName)}</div>
        </div>
        ${stateHtml}
      </div>`;
    }).join("");
    const residentItems = residentDefaults.map(([key, name]) => {
      const item = residentByKey.get(key) || {};
      const running = !!item.running;
      const displayName = key === "lossless"
        ? `${name}（${fmtNum(item.usedAttempts || 0)}/5）`
        : key === "brushYellow"
          ? `${name}（${fmtNum(appState.dailyStats?.brushYellowCount || 0)}/${fmtNum(appState.brushSettings?.dailyLimit || 500)}）`
        : key === "dungeon"
          ? `${item.mode === "clear" ? "打通副本" : name}（${fmtNum(item.dailyDungeonCount ?? appState.dailyStats?.dungeonCount ?? 0)}次）`
        : key === "mine"
          ? `${name}（${fmtNum(item.resourcePointCurrent ?? appState.roleState?.resourcePointCurrent ?? 0)} / ${fmtNum(item.resourcePointCap ?? appState.roleState?.resourcePointCap ?? 0)}）`
        : name;
      const stateName = running
        ? (schedulerStateNames[item.schedulerState] || item.schedulerState || "运行中")
        : "未运行";
      const cooldown = key === "lossless" && item.schedulerState === "cooldown"
        ? taskCooldownHtml(item.schedulerNextCheckAt)
        : "";
      return `<div class="role-task-item ${running ? "is-running" : ""}" title="${escAttr(item.schedulerMessage || "")}">
        <span class="role-task-name">${escHtml(displayName)}</span>
        <span class="role-task-resident-status">
          ${cooldown || `<span class="role-task-resident-state">${escHtml(stateName)}</span>`}
          <span class="role-task-loop" title="${running ? "循环任务正在运行" : "循环任务未运行"}" aria-label="${running ? "正在运行" : "未运行"}">↻</span>
        </span>
      </div>`;
    }).join("");
    const dailyItems = dailyDefaults.map(([key, name]) => {
      const item = dailyByKey.get(key) || {};
      const completed = !!item.completed;
      const statusText = item.statusText || (completed ? "已做" : "未做");
      const statusTitle = item.message || (completed ? "今日已完成" : "今日未完成");
      return `<div class="role-task-item ${completed ? "is-completed" : ""}">
        <span class="role-task-name">${escHtml(name)}</span>
        <span class="role-task-daily-status ${completed ? "is-done" : "is-pending"}" title="${escAttr(statusTitle)}">${escHtml(statusText)}</span>
      </div>`;
    }).join("");
    return `<div class="role-task-page">
      <section class="role-task-section">
        <div class="role-task-section-header"><h2>任务栈</h2>${startSavedTasksButton}</div>
        <div class="task-stack-list">${taskStackItems || `<div class="task-stack-empty">当前没有后台任务</div>`}</div>
      </section>
      <section class="role-task-section">
        <h2>常驻任务</h2>
        <div class="role-task-list resident-task-list">${residentItems}</div>
      </section>
      <section class="role-task-section">
        <h2>每日任务</h2>
        <div class="role-task-list daily-task-list">${dailyItems}</div>
      </section>
    </div>`;
  }
  if (activeSide === "提示") {
    const notices = Array.isArray(appState.taskOverview?.notices)
      ? appState.taskOverview.notices
      : [];
    const noticeItems = notices.map(item => {
      const severity = ["critical", "error", "warning", "info"].includes(item.severity)
        ? item.severity
        : "warning";
      return `<button class="important-notice-brief is-${severity}" type="button"
        data-notice-key="${escAttr(item.key || "")}" title="点击删除这条提示">
        <span aria-hidden="true">!</span>
        <p>${escHtml(item.summary || item.title || "重要提示")}</p>
      </button>`;
    }).join("");
    return `<div class="important-notice-page">${noticeItems || `<div class="important-notice-empty">暂无重要提示</div>`}</div>`;
  }
  if (activeSide === "记录") {
    if (activeCategory === "起号") {
      const records = Array.isArray(appState.starterRecords)
        ? appState.starterRecords.slice(0, 200)
        : [];
      const items = records.map(item => {
        const clock = String(item.timeText || "")
          .match(/(\d{2}:\d{2}:\d{2})/)?.[1] || "--:--:--";
        return `<div class="success-record-item">
          <time>${escHtml(clock)}</time>
          <b>起号</b>
          <span>${escHtml(item.message || "")}</span>
        </div>`;
      }).join("");
      return `<div class="success-record-page starter-action-record-page">
        <div class="success-record-head"><strong>起号记录</strong>
          <button type="button" class="table-btn" data-starter-record-refresh>刷新</button>
        </div>
        <div class="success-record-list">${items || `<div class="success-record-empty">暂无起号记录</div>`}</div>
      </div>`;
    }
    const militaryCategories = new Set([
      "刷黄", "副本", "掠夺", "无损", "打矿", "抢城", "押镖", "寻宝",
      "出征", "治疗", "加体"
    ]);
    const allRecords = Array.isArray(appState.successRecords) ? appState.successRecords : [];
    const records = allRecords
      .filter(item => successRecordType === "military"
        ? militaryCategories.has(String(item.category || ""))
        : !militaryCategories.has(String(item.category || "")))
      .slice(0, 50);
    const items = records.map(item => {
      const timeText = String(item.timeText || "");
      const clock = timeText.match(/(\d{2}:\d{2}:\d{2})/)?.[1] || "--:--:--";
      return `<div class="success-record-item">
        <time>${escHtml(clock)}</time>
        <b>${escHtml(item.category || "其他")}</b>
        <span>${escHtml(item.message || "")}</span>
      </div>`;
    }).join("");
    return `<div class="success-record-page">
      <div class="success-record-head">
        <div class="success-record-switch" role="group" aria-label="记录类型">
          <button type="button" data-record-type="military" class="${successRecordType === "military" ? "is-active" : ""}">军事</button>
          <button type="button" data-record-type="politics" class="${successRecordType === "politics" ? "is-active" : ""}">政事</button>
        </div>
      </div>
      <div class="success-record-list">${items || `<div class="success-record-empty">暂无${successRecordType === "military" ? "军事" : "政事"}成功记录</div>`}</div>
    </div>`;
  }
  return roleStatusTableHtml();
}
function renderSelectOverlay() {
  const names = (appState.generals || []).map(g => g.name).filter(Boolean);
  const list = names.length ? names : ["何颜鸥","冯岚","单于钧","台达元[掠夺1]","尹诩静","松翠岚","宋寿","龚单","蒲鸥莫"];
  return `<input class="search-box picker-search" placeholder="🔍  请输入关键字搜索"/>
    <div class="select-list">
      <div class="toolbar"><button class="picker-all" type="button">全选</button><button class="picker-clear" type="button">清除</button></div>
      ${list.map((n,i)=>`<label class="item picker-item ${i===4||i===5?'active':''}"><span>${escHtml(n)}</span><input type="checkbox" ${i===4||i===5?'checked':''}></label>`).join("")}
    </div>`;
}
function renderPickerLayer() {
  document.getElementById("pickerLayer")?.remove();
  if (!pickerOpen) return;
  const layer = document.createElement("div");
  layer.id = "pickerLayer";
  layer.className = "picker-layer";
  layer.innerHTML = renderSelectOverlay();
  document.querySelector(".phone-stage").appendChild(layer);
  layer.querySelectorAll(".picker-item input").forEach(input => input.onchange = () => input.closest(".picker-item")?.classList.toggle("active", input.checked));
  layer.querySelector(".picker-all")?.addEventListener("click", () => {
    layer.querySelectorAll(".picker-item input").forEach(input => { input.checked = true; input.closest(".picker-item")?.classList.add("active"); });
  });
  layer.querySelector(".picker-clear")?.addEventListener("click", () => {
    layer.querySelectorAll(".picker-item input").forEach(input => { input.checked = false; input.closest(".picker-item")?.classList.remove("active"); });
  });
  layer.querySelector(".picker-search")?.addEventListener("input", e => {
    const q = String(e.target.value || "").trim();
    layer.querySelectorAll(".picker-item").forEach(item => {
      item.style.display = !q || item.textContent.includes(q) ? "flex" : "none";
    });
  });
}
function renderContent() {
  if (activeCategory === "起号") {
    if (activeSide === "军队") {
      const starterSide = activeSide;
      activeSide = "配兵";
      const html = renderMilitary();
      activeSide = starterSide;
      return html;
    }
    if (activeSide === "招将") return renderStarterRecruitPage();
    if (["角色", "宝物", "英雄", "记录"].includes(activeSide)) return renderRole();
    return renderStarterListsPage();
  }
  if (isStarterContainer && activeCategory === "刷黄") {
    return activeSide === "刷黄配置" ? renderShuaHuang() : renderStarterActionRecords("刷黄");
  }
  if (isStarterContainer && activeCategory === "副本") {
    if (activeSide === "副本配置") {
      const starterSide = activeSide;
      activeSide = "副本";
      const html = renderMilitary();
      activeSide = starterSide;
      return html;
    }
    return renderStarterActionRecords("副本");
  }
  if (activeCategory === "常规") return renderCommon();
  if (activeCategory === "六部") return renderLiubu();
  if (activeCategory === "打矿") return renderMine();
  if (activeCategory === "刷黄") return renderShuaHuang();
  if (activeCategory === "军情") return renderJunqing();
  if (activeCategory === "军事") return renderMilitary();
  if (activeCategory === "角色") return renderRole();
  return "";
}

let starterContainerView = null;
let starterContainerViewAccountId = "";
let starterContainerViewPending = false;
let starterTaskGroup = "growth";
let starterSelectedTaskId = "";
let starterTaskDetailPending = false;
let starterTaskRefreshPending = false;
let starterRecruitRefreshPending = false;
let starterRecruitAutoRefreshAccountId = "";
const starterTaskDetailCache = new Map();

function renderStarterActionRecords(category) {
  const rows = (appState.successRecords || []).filter(
    item => String(item.category || "") === category,
  ).slice(0, 50);
  return `<div class="success-record-page starter-action-record-page">
    <div class="success-record-head"><strong>${escHtml(category)}记录</strong>
      <button type="button" class="table-btn" data-starter-record-refresh>刷新</button></div>
    <div class="success-record-list">${rows.map(item => `<div class="success-record-item">
      <time>${escHtml(String(item.timeText || "").match(/\d{2}:\d{2}:\d{2}/)?.[0] || "--:--:--")}</time>
      <b>${escHtml(item.category || category)}</b><span>${escHtml(item.message || "")}</span>
    </div>`).join("") || `<div class="success-record-empty">暂无${escHtml(category)}记录</div>`}</div>
  </div>`;
}

function renderStarterRecruitPage() {
  const currentId = String(appState.sessionId || "");
  if (!starterContainerView && currentId && !starterContainerViewPending) {
    starterContainerViewPending = true;
    fetch(`/api/starter/account-view?accountId=${encodeURIComponent(currentId)}`, { cache: "no-store" })
      .then(response => response.json())
      .then(data => { starterContainerView = data.view || {}; })
      .catch(error => showToast(error.message || "读取招将页面失败", "error"))
      .finally(() => { starterContainerViewPending = false; render(); });
  }
  const recruit = starterContainerView?.recruit || {};
  const candidates = recruit.candidates || [];
  if (
    starterContainerView
    && currentId
    && starterRecruitAutoRefreshAccountId !== currentId
    && !starterRecruitRefreshPending
  ) {
    starterRecruitAutoRefreshAccountId = currentId;
    queueMicrotask(() => refreshStarterRecruitPage({ silent: true }));
  }
  const updatedText = recruit.updatedAt
    ? new Date(Number(recruit.updatedAt)).toLocaleTimeString("zh-CN", { hour12: false })
    : "尚未刷新";
  return `<div class="starter-recruit-page">
    <header><h2>招募将领</h2><button type="button" data-starter-recruit-refresh
      ${starterRecruitRefreshPending ? "disabled" : ""}>${starterRecruitRefreshPending ? "刷新中…" : "刷新"}</button></header>
    <div class="starter-recruit-summary">
      <span>将领数：${escHtml(recruit.generalCount ?? appState.generals.length)}/${escHtml(recruit.generalLimit ?? "-")}</span>
      <span>刷新：${escHtml(updatedText)}</span>
    </div>
    ${recruit.success === false ? `<div class="starter-task-empty-detail">实时招将列表读取失败：${escHtml(recruit.warning || "游戏服未返回最新数据")}</div>` : ""}
    <div class="starter-recruit-purchase">
      <span>皇榜 <b>${escHtml(recruit.royalCount ?? 0)}个</b></span>
      <span>招贤金榜 <b>${escHtml(recruit.goldListCount ?? 0)}个</b></span>
      <span>招贤令 <b>${escHtml(recruit.recruitOrderCount ?? 0)}个</b></span>
    </div>
    <div class="starter-recruit-list">${candidates.map((item, index) => `
      <article class="${index === 0 ? "active" : ""}">
        <div class="starter-recruit-avatar">${escHtml(String(item.name || "将").slice(0, 1))}</div>
        <div><h3>${escHtml(item.name || `候选将领${index + 1}`)}${item.kind ? `<small>[${escHtml(item.kind)}]</small>` : ""}</h3>
          <p>成长 <b>${escHtml(item.growth ?? "-")}</b>${item.quality ? `（${escHtml(item.quality)}）` : ""}</p>
          <p>武力 ${escHtml(item.attack ?? "-")}　智力 ${escHtml(item.intelligence ?? "-")}　统帅 ${escHtml(item.command ?? "-")}</p>
        </div>
      </article>`).join("") || `<div class="starter-task-empty-detail">${starterRecruitRefreshPending ? "正在读取游戏服务器最新招将列表…" : "当前没有可展示的实时候选将领"}</div>`}
    </div>
    <footer><button type="button" disabled>名将画册</button><button type="button" disabled>拜访名将</button><button type="button">返回</button></footer>
  </div>`;
}

async function refreshStarterRecruitPage({ silent = false } = {}) {
  const currentId = String(appState.sessionId || "");
  if (!currentId || starterRecruitRefreshPending) return;
  starterRecruitRefreshPending = true;
  render();
  try {
    const data = await apiPost("/api/starter/recruit/refresh", { sessionId: currentId });
    starterContainerView = starterContainerView || {};
    starterContainerView.recruit = data.result || {};
    render();
    if (data.result?.success) {
      if (!silent) showToast("招将列表已从游戏服务器刷新", "success");
    } else {
      showToast(data.result?.warning || "游戏服未返回最新招将列表", "error");
    }
  } catch (error) {
    showToast(error.message || "刷新招将列表失败", "error");
  } finally {
    starterRecruitRefreshPending = false;
    render();
  }
}

function starterListEmpty(text) {
  return `<div class="starter-list-page-empty">${escHtml(text)}</div>`;
}

function starterTaskNumericId(item) {
  const raw = item?.id ?? item?.idHex ?? "";
  if (typeof raw === "number") return raw;
  const text = String(raw).trim();
  if (!text) return 0;
  if (/^0x/i.test(text)) return Number.parseInt(text.slice(2), 16) || 0;
  if (/^[0-9a-f]+$/i.test(text) && /[a-f]/i.test(text)) return Number.parseInt(text, 16) || 0;
  return Number.parseInt(text, 10) || 0;
}

function starterTaskDetailFor(item) {
  const id = starterTaskNumericId(item);
  const key = `${starterContainerViewAccountId}:${starterTaskGroup}:${id}`;
  if (starterTaskDetailCache.has(key)) return starterTaskDetailCache.get(key);
  const details = starterContainerView?.taskRewards?.growthDetails || [];
  return details.find(detail => starterTaskNumericId(detail) === id) || null;
}

function starterTaskDetailFields(detail) {
  const fields = detail?.responses?.[0]?.textFields?.filter(value => String(value || "").trim()) || [];
  return {
    description: fields[0] || "暂无任务描述",
    target: fields[1] || "暂无任务目标",
    guide: fields[2] || "暂无任务指引",
    reward: fields.slice(3).join("、") || "奖励数据已读取，具体奖励以游戏内显示为准",
  };
}

async function loadStarterTaskDetail() {
  const currentId = String(appState.sessionId || "");
  const groups = starterContainerView?.taskRewards?.groups || {};
  const item = (groups[starterTaskGroup] || [])
    .find(row => String(starterTaskNumericId(row)) === String(starterSelectedTaskId));
  if (!currentId || !item || starterTaskDetailPending) return;
  const id = starterTaskNumericId(item);
  const key = `${currentId}:${starterTaskGroup}:${id}`;
  if (starterTaskDetailCache.has(key)) return;
  starterTaskDetailPending = true;
  render();
  try {
    const group = starterTaskGroup === "country" ? 2 : starterTaskGroup === "special" ? 1 : 0;
    const data = await apiPost("/api/starter/tasks/details", {
      sessionId: currentId, group, taskIds: [id],
    });
    const detail = data.result?.details?.[0];
    if (detail) starterTaskDetailCache.set(key, detail);
  } catch (error) {
    starterTaskDetailCache.set(key, { error: error.message || "任务详情读取失败" });
    showToast(error.message || "任务详情读取失败", "error");
  } finally {
    starterTaskDetailPending = false;
    if (isStarterContainer && activeCategory === "起号") render();
  }
}

async function refreshStarterTaskPage() {
  const currentId = String(appState.sessionId || "");
  if (!currentId || starterTaskRefreshPending) return;
  starterTaskRefreshPending = true;
  render();
  try {
    await apiPost("/api/starter/rewards/refresh", { sessionId: currentId });
    const response = await fetch(`/api/starter/account-view?accountId=${encodeURIComponent(currentId)}`, {
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "刷新任务列表失败");
    starterContainerView = data.view || {};
    showToast("任务列表已刷新", "success");
  } catch (error) {
    showToast(error.message || "刷新任务列表失败", "error");
  } finally {
    starterTaskRefreshPending = false;
    render();
  }
}

function renderStarterListsPage() {
  const currentId = String(appState.sessionId || "");
  if (!currentId) return starterListEmpty("请先在上方选择一个起号账号");
  if (starterContainerViewAccountId !== currentId) {
    starterContainerView = null;
    starterContainerViewAccountId = currentId;
  }
  if (!starterContainerView && !starterContainerViewPending) {
    starterContainerViewPending = true;
    fetch(`/api/starter/account-view?accountId=${encodeURIComponent(currentId)}`, { cache: "no-store" })
      .then(response => response.json().then(data => {
        if (!response.ok || !data.ok) throw new Error(data.error || "读取起号列表失败");
        starterContainerView = data.view || {};
      }))
      .catch(error => {
        starterContainerView = { loadError: error.message || "读取起号列表失败" };
      })
      .finally(() => {
        starterContainerViewPending = false;
        if (isStarterContainer && activeCategory === "起号") render();
      });
  }
  if (!starterContainerView) return starterListEmpty("正在读取任务与活动列表...");
  if (starterContainerView.loadError) return starterListEmpty(starterContainerView.loadError);
  if (activeSide === "活动列表") {
    const activities = starterContainerView.activityRewards?.activities || [];
    if (!activities.length) return starterListEmpty("暂无活动数据，运行或刷新起号任务后自动显示");
    return `<div class="starter-list-page starter-activity-page">
      <div class="section-title">活动列表 <span>${activities.length}项</span></div>
      <div class="starter-activity-catalog">${activities.map(item => `
        <article class="starter-activity-item">
          <div class="starter-activity-gift" aria-hidden="true">🎁</div>
          <div class="starter-activity-name">
            <strong>${escHtml(item.title || "-")}</strong>
            <small>${escHtml(item.idHex || item.id || "-")}</small>
          </div>
          <span class="starter-claim-status ${escAttr(item.claimStatusKey || "unavailable")}">${escHtml(item.claimStatus || "无法领取")}</span>
        </article>
      `).join("")}</div>
    </div>`;
  }
  const groups = starterContainerView.taskRewards?.groups || {};
  const items = groups[starterTaskGroup] || [];
  if (!items.some(item => String(starterTaskNumericId(item)) === String(starterSelectedTaskId))) {
    starterSelectedTaskId = items.length ? String(starterTaskNumericId(items[0])) : "";
  }
  const selected = items.find(item => String(starterTaskNumericId(item)) === String(starterSelectedTaskId));
  const detail = selected ? starterTaskDetailFor(selected) : null;
  if (selected && !detail && !starterTaskDetailPending) setTimeout(loadStarterTaskDetail, 0);
  const fields = starterTaskDetailFields(detail);
  const groupLabels = { growth: "成长", country: "国家", special: "特殊" };
  return `<div class="starter-list-page starter-task-page">
    <div class="starter-task-shell">
      <div class="starter-task-toolbar"><strong>任务</strong><button type="button"
        data-starter-task-refresh ${starterTaskRefreshPending ? "disabled" : ""}>
        ${starterTaskRefreshPending ? "刷新中…" : "刷新任务"}
      </button></div>
      <nav class="starter-task-groups">
        ${Object.entries(groupLabels).map(([key, label]) => `<button type="button"
          class="${starterTaskGroup === key ? "active" : ""}" data-starter-task-group="${key}">
          ${label}<small>${(groups[key] || []).length}</small>
        </button>`).join("")}
      </nav>
      <div class="starter-task-body">
        <aside class="starter-task-list">
          ${items.length ? items.map(item => {
            const id = String(starterTaskNumericId(item));
            return `<button type="button" class="${id === starterSelectedTaskId ? "active" : ""}"
              data-starter-task-id="${escAttr(id)}"><span>${escHtml(item.title || item.name || `任务 ${item.idHex || id}`)}</span>
              <small class="${escAttr(item.claimStatusKey || "progress")}">${escHtml(item.claimStatus || "进行中")}</small></button>`;
          }).join("") : `<div class="starter-task-none">当前分类暂无任务</div>`}
        </aside>
        <article class="starter-task-detail">
          ${selected ? `
            <header><h3>${escHtml(selected.title || selected.name || "任务详情")}</h3>
              <div><span class="starter-task-detail-status ${escAttr(selected.claimStatusKey || "progress")}">${escHtml(selected.claimStatus || "进行中")}</span>
              <code>${escHtml(selected.idHex || selected.id || "")}</code></div></header>
            ${starterTaskDetailPending && !detail ? `<div class="starter-task-loading">正在读取任务详情…</div>` : `
              <section><h4>任务描述</h4><p>${escHtml(fields.description)}</p></section>
              <section><h4>任务目标</h4><p>${escHtml(fields.target)}</p></section>
              <section><h4>任务指引</h4><p>${escHtml(fields.guide)}</p></section>
              <section><h4>任务奖励</h4><p>${escHtml(fields.reward)}</p></section>
            `}
          ` : `<div class="starter-task-empty-detail">请在左侧选择任务</div>`}
        </article>
      </div>
    </div>
  </div>`;
}
function showToast(message, type = "success", duration = 1600) {
  const el = document.getElementById("toast");
  if (!el) return;
  if (toastTimer) clearTimeout(toastTimer);
  el.textContent = message;
  el.className = `toast ${type || "info"}`;
  toastTimer = setTimeout(() => {
    el.classList.add("hidden");
  }, duration);
}
function renderMainPageShell() {
  const assistant = document.getElementById("assistantPage");
  const logPage = document.getElementById("logPage");
  const otherPage = document.getElementById("otherPage");
  const homePage = document.getElementById("homePage");
  const otherHome = document.getElementById("otherHome");
  const dungeonGuide = document.getElementById("dungeonGuide");
  const banditMapPage = document.getElementById("banditMapPage");
  const title = document.querySelector(".app-title");
  if (assistant) assistant.classList.toggle("page-hidden", activeMainPage !== "助手");
  if (logPage) logPage.classList.toggle("page-hidden", activeMainPage !== "日志");
  if (otherPage) otherPage.classList.toggle("page-hidden", activeMainPage !== "其他");
  if (homePage) homePage.classList.toggle("page-hidden", activeMainPage !== "Home");
  if (otherHome) otherHome.classList.toggle("page-hidden", activeOtherView !== "home");
  if (dungeonGuide) dungeonGuide.classList.toggle("page-hidden", activeOtherView !== "dungeon-guide");
  if (banditMapPage) banditMapPage.classList.toggle("page-hidden", activeOtherView !== "bandit-map");
  if (title) {
    title.textContent = activeMainPage === "其他"
      ? (activeOtherView === "dungeon-guide" ? "副本攻略" : activeOtherView === "bandit-map" ? "山贼地图" : "攻略")
      : activeMainPage;
  }
  document.querySelectorAll(".bottom-item[data-page]").forEach(item => {
    item.classList.toggle("active", item.dataset.page === activeMainPage);
  });
  document.querySelectorAll(".quick-switch-btn[data-page]").forEach(item => {
    item.classList.toggle("active", item.dataset.page === activeMainPage);
  });
  if (activeMainPage === "Home") renderHomeAccountOptions();
}

function renderHomeAccountOptions() {
  const select = document.getElementById("homeAccountSelect");
  if (!select) return;
  const previous = String(select.value || appState.sessionId || "");
  select.innerHTML = `<option value="">请选择账号</option>${(appState.accounts || []).map(account =>
    `<option value="${escAttr(account.sessionId)}">${escHtml(accountLabel(account))}</option>`
  ).join("")}`;
  if ((appState.accounts || []).some(account => String(account.sessionId) === previous)) {
    select.value = previous;
  }
}

async function loadRawAccountSettings() {
  const select = document.getElementById("homeAccountSelect");
  const content = document.getElementById("homeSettingsContent");
  const sid = String(select?.value || "");
  if (!content || !sid) {
    showToast("请先选择账号", "error");
    return;
  }
  content.innerHTML = `<div class="home-settings-empty">正在读取设置文件...</div>`;
  try {
    const response = await fetch(`/api/accounts/settings?sessionId=${encodeURIComponent(sid)}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "读取设置失败");
    content.innerHTML = `
      <div class="home-settings-account">${escHtml(accountLabel(data.account))}</div>
      <div class="home-settings-dir">${escHtml(data.configDir || "")}</div>
      ${(data.files || []).map(file => `
        <section class="raw-settings-file">
          <header>
            <b>${escHtml(file.name)}</b>
            <span>${file.exists ? escHtml(file.path) : "文件不存在"}</span>
          </header>
          <pre>${file.exists ? escHtml(file.content) : "文件不存在"}</pre>
        </section>
      `).join("")}`;
  } catch (error) {
    content.innerHTML = `<div class="home-settings-empty">读取失败：${escHtml(error.message)}</div>`;
    showToast("读取账号设置失败", "error");
  }
}

function formatAccountLogEntry(entry) {
  const timeText = String(entry?.timeText || "");
  const shortTime = timeText.includes(" ") ? timeText.split(" ")[1] : timeText;
  return `[${shortTime || "--:--:--"}] ${entry?.message || ""}`;
}

function formatSystemLogEntry(entry) {
  const timeText = String(entry?.timeText || "");
  const shortTime = timeText ? timeText.replace(/^\d{4}-/, "") : "--";
  if (String(entry?.source || "").startsWith("game:")) {
    return `[${shortTime}] ${entry?.message || ""}`;
  }
  const level = String(entry?.level || "info").toUpperCase().padEnd(5, " ");
  const source = entry?.source ? ` ${entry.source}` : "";
  const account = entry?.accountKey ? ` ${entry.accountKey}` : "";
  return `[${shortTime}] ${level}${source}${account} ｜ ${entry?.message || ""}`;
}

function isSystemAlertEntry(entry) {
  const level = String(entry?.level || "").trim().toLowerCase();
  const source = String(entry?.source || "").trim().toLowerCase();
  const detail = entry?.detail || {};
  const text = [
    level,
    source,
    entry?.message,
    detail?.message,
    detail?.failureReason,
    detail?.error,
  ].filter(Boolean).join(" ").toLowerCase();
  const sessionAlert = [
    "被退出",
    "会话失效",
    "sessioninvalid",
    "session invalid",
    "fffc0000",
    "0x8016",
    "没有角色信息",
    "账号异常",
    "掉线/会话失效",
  ].some(k => text.includes(k.toLowerCase()));
  if (sessionAlert) return true;

  const isGameRequest = source.startsWith("game:");
  if (isGameRequest && (
    level === "error"
    || level === "warn"
    || detail?.transportFailed === true
    || Number(detail?.http || 0) >= 400
    || String(detail?.error || "").trim()
    || /(?:失败|错误|异常|拒绝|未返回)/.test(String(entry?.message || ""))
  )) return true;

  const message = String(entry?.message || "");
  if (source.startsWith("account:") && level === "error") {
    return true;
  }
  if (source === "account:task" && /(?:失败|错误|异常|拒绝|未确认成功|未生效)/.test(message)) {
    return true;
  }
  const explicitServerFailure = /(?:失败|错误|异常|拒绝|未确认成功|未生效)/.test(message)
    && /(?:服务器|服务端|原服|响应|status\s*=|sub\s*=|HTTP\s*[=:]?|opcode|0x[0-9a-f]+)/i.test(message);
  return explicitServerFailure;
}

function isHeartbeatSystemLogEntry(entry) {
  const source = String(entry?.source || "").trim().toLowerCase();
  const message = String(entry?.message || "").trim();
  return source.includes("heartbeat")
    || /^心跳(?:检测|失败|异常|未确认)/.test(message)
    || /^启动后心跳/.test(message);
}

function systemLogEntryKey(entry) {
  if (Number.isFinite(Number(entry?.id))) return `id:${Number(entry.id)}`;
  return [
    entry?.time ?? "",
    entry?.level ?? "",
    entry?.source ?? "",
    entry?.sessionId ?? "",
    entry?.accountKey ?? "",
    entry?.message ?? "",
  ].join("\u001f");
}

function appendedSystemLogEntries(previousEntries, nextEntries) {
  const previous = Array.isArray(previousEntries) ? previousEntries : [];
  const next = Array.isArray(nextEntries) ? nextEntries : [];
  if (!previous.length) return next;
  const previousTailKey = systemLogEntryKey(previous[previous.length - 1]);
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (systemLogEntryKey(next[i]) === previousTailKey) return next.slice(i + 1);
  }
  const previousLatestTime = Math.max(...previous.map(entry => Number(entry?.time)).filter(Number.isFinite));
  if (Number.isFinite(previousLatestTime)) {
    return next.filter(entry => Number(entry?.time) > previousLatestTime);
  }
  const previousKeys = new Set(previous.map(systemLogEntryKey));
  return next.filter(entry => !previousKeys.has(systemLogEntryKey(entry)));
}

function renderSystemLog({
  scrollMainToLatest = false,
  scrollAlertsToLatest = false,
  mainScrollTop,
  alertScrollTop,
} = {}) {
  const body = document.getElementById("systemLogBody");
  const alertBody = document.getElementById("systemAlertBody");
  const meta = document.getElementById("systemLogMeta");
  if (!body) return;
  const entries = appState.systemLogs || [];
  const selectedIndex = systemLogSelectionStart === null
    ? -1
    : entries.findIndex(entry => systemLogEntryKey(entry) === systemLogSelectionStart);
  body.innerHTML = entries.length
    ? entries.map((entry, index) => `<div class="system-log-line ${isSystemAlertEntry(entry) ? "alert" : ""} ${index === selectedIndex ? "copy-start" : ""}" data-log-index="${index}">${escHtml(formatSystemLogEntry(entry))}</div>`).join("")
    : `<div class="system-log-line">暂无系统日志</div>`;
  if (systemLogSelectionStart !== null && selectedIndex < 0) systemLogSelectionStart = null;
  body.onclick = handleSystemLogLineClick;
  if (scrollMainToLatest) {
    body.scrollTop = body.scrollHeight;
  } else if (Number.isFinite(mainScrollTop)) {
    body.scrollTop = Math.min(mainScrollTop, Math.max(0, body.scrollHeight - body.clientHeight));
  }
  if (alertBody) {
    const alerts = entries.filter(isSystemAlertEntry).slice(-100);
    alertBody.innerHTML = alerts.length
      ? alerts.map(entry => `<div class="system-alert-line">${escHtml(formatSystemLogEntry(entry))}</div>`).join("")
      : "暂无红色告警";
    if (scrollAlertsToLatest) {
      alertBody.scrollTop = alertBody.scrollHeight;
    } else if (Number.isFinite(alertScrollTop)) {
      alertBody.scrollTop = Math.min(alertScrollTop, Math.max(0, alertBody.scrollHeight - alertBody.clientHeight));
    }
  }
  if (meta) meta.textContent = `显示最近 ${entries.length} 条，SQLite 最多保留 10000 条`;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}

async function handleSystemLogLineClick(event) {
  const line = event.target.closest(".system-log-line[data-log-index]");
  if (!line) return;
  const body = document.getElementById("systemLogBody");
  const index = Number(line.dataset.logIndex);
  if (!Number.isInteger(index)) return;
  if (systemLogSelectionStart === null) {
    systemLogSelectionStart = systemLogEntryKey((appState.systemLogs || [])[index]);
    body?.querySelectorAll(".system-log-line").forEach(item => item.classList.remove("copy-start"));
    line.classList.add("copy-start");
    showToast("已选择复制起始行，请点击结束行", "info");
    return;
  }
  const clickedKey = systemLogEntryKey((appState.systemLogs || [])[index]);
  if (clickedKey === systemLogSelectionStart) {
    systemLogSelectionStart = null;
    body?.querySelectorAll(".system-log-line").forEach(item => item.classList.remove("copy-start"));
    showToast("已取消日志选择", "info");
    return;
  }
  const startIndex = (appState.systemLogs || []).findIndex(entry => systemLogEntryKey(entry) === systemLogSelectionStart);
  if (startIndex < 0) {
    systemLogSelectionStart = null;
    showToast("起始日志已被清除，请重新选择", "error");
    return;
  }
  const from = Math.min(startIndex, index);
  const to = Math.max(startIndex, index);
  const text = (appState.systemLogs || []).slice(from, to + 1).map(formatSystemLogEntry).join("\n");
  systemLogSelectionStart = null;
  body?.querySelectorAll(".system-log-line").forEach(item => item.classList.remove("copy-start"));
  try {
    await copyTextToClipboard(text);
    showToast(`已复制 ${to - from + 1} 行日志`, "success");
  } catch (error) {
    showToast("复制日志失败：" + error.message, "error");
  }
}

function applySystemLogEntries(nextEntries) {
  const body = document.getElementById("systemLogBody");
  const alertBody = document.getElementById("systemAlertBody");
  const previousEntries = appState.systemLogs || [];
  const appended = appendedSystemLogEntries(previousEntries, nextEntries);
  const firstLoad = !systemLogHasLoaded;
  const hasNewNonHeartbeat = appended.some(entry => !isHeartbeatSystemLogEntry(entry));
  const hasNewAlert = appended.some(isSystemAlertEntry);
  const mainScrollTop = body?.scrollTop;
  const alertScrollTop = alertBody?.scrollTop;
  appState.systemLogs = Array.isArray(nextEntries) ? nextEntries : [];
  renderSystemLog({
    scrollMainToLatest: firstLoad || hasNewNonHeartbeat,
    scrollAlertsToLatest: firstLoad || hasNewAlert,
    mainScrollTop,
    alertScrollTop,
  });
  systemLogHasLoaded = true;
  return { appended, hasNewNonHeartbeat, hasNewAlert };
}

async function refreshSystemLog({ forceInitial = false } = {}) {
  if (isEmbeddedContainer || document.hidden || systemLogRequestPending) return;
  systemLogRequestPending = true;
  try {
    const initial = forceInitial || !systemLogHasLoaded || systemLogCursorId <= 0;
    const query = initial
      ? `limit=${SYSTEM_LOG_INITIAL_LIMIT}`
      : `limit=${SYSTEM_LOG_INCREMENT_LIMIT}&afterId=${encodeURIComponent(systemLogCursorId)}`;
    const res = await fetch(`/api/logs/system?${query}`, { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "系统日志读取失败");
    if (!initial && Number(data.latestId || 0) < systemLogCursorId) {
      systemLogHasLoaded = false;
      systemLogCursorId = 0;
      appState.systemLogs = [];
      systemLogRequestPending = false;
      setTimeout(() => refreshSystemLog({ forceInitial: true }), 0);
      return;
    }
    const incoming = Array.isArray(data.entries) ? data.entries : [];
    if (initial) {
      applySystemLogEntries(incoming.slice(-SYSTEM_LOG_BROWSER_LIMIT));
    } else if (incoming.length) {
      applySystemLogEntries(
        [...(appState.systemLogs || []), ...incoming].slice(-SYSTEM_LOG_BROWSER_LIMIT)
      );
    }
    systemLogCursorId = Number(
      data.cursorId
      ?? incoming[incoming.length - 1]?.id
      ?? systemLogCursorId
    ) || 0;
  } catch (e) {
    const body = document.getElementById("systemLogBody");
    if (body) body.textContent = "系统日志读取失败：" + e.message;
    const alertBody = document.getElementById("systemAlertBody");
    if (alertBody) alertBody.textContent = "系统日志读取失败：" + e.message;
  } finally {
    systemLogRequestPending = false;
  }
}

function startSystemLogPolling() {
  if (isEmbeddedContainer || systemLogTimer) return;
  refreshSystemLog();
  systemLogTimer = setInterval(refreshSystemLog, 5000);
}

async function persistAccountLog(message, level = "info", source = "frontend") {
  try {
    await fetch("/api/logs/account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId: appState.sessionId || "", message, level, source }),
      keepalive: true,
    });
  } catch (_) {}
}

async function loadAccountLog(sessionId = appState.sessionId, { force = false } = {}) {
  if (!sessionId) {
    runtimeLog = "";
    appState.accountLogLoadedFor = null;
    renderLog();
    return;
  }
  if (!force && appState.accountLogLoadedFor === sessionId) return;
  try {
    const before = runtimeLog;
    const res = await fetch(`/api/logs/account?sessionId=${encodeURIComponent(sessionId)}&limit=100`, { cache: "no-store" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "账号日志读取失败");
    if (String(appState.sessionId) !== String(sessionId)) return;
    const loaded = (data.entries || []).map(formatAccountLogEntry).join("\n");
    if (runtimeLog !== before && runtimeLog.trim()) {
      const seen = new Set(loaded.split("\n").filter(Boolean));
      const extra = runtimeLog.split("\n").filter(line => line && !seen.has(line)).join("\n");
      runtimeLog = loaded + (loaded && extra ? "\n" : "") + extra;
    } else {
      runtimeLog = loaded;
    }
    appState.accountLogLoadedFor = sessionId;
    renderLog();
  } catch (_) {}
}

function ensureAccountLogLoaded(sessionId) {
  if (!sessionId || appState.accountLogLoadedFor === sessionId) return;
  loadAccountLog(sessionId);
}

function appendLog(message) {
  const d = new Date();
  const t = `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}:${String(d.getSeconds()).padStart(2,"0")}`;
  runtimeLog += `${runtimeLog ? "\n" : ""}[${t}] ${message}`;
  renderAccountLogLines(true);
  if (!/^后台[:：]/.test(String(message || ""))) persistAccountLog(message);
}
async function apiPost(path, data, { timeoutMs = 30000, timeoutMessage = "" } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {}),
      signal: controller.signal,
    });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch (_) { throw new Error(`接口返回非 JSON：HTTP ${res.status} ${text.slice(0, 120)}`); }
    if (!json.ok) throw new Error(json.error || `请求失败 HTTP ${res.status}`);
    return json;
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error(timeoutMessage || `请求超时：后端 ${Math.round(timeoutMs / 1000)} 秒内没有返回，请检查 server.py 是否卡住或正在重启`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function dailySettingsPageIsActive() {
  return activeMainPage === "助手" && activeCategory === "常规" && activeSide === "日常";
}

async function loadGeneralVisitCandidates({ force = false } = {}) {
  const sessionId = String(appState.sessionId || "");
  if (!sessionId) {
    showToast("请先添加并选择账号", "error");
    return;
  }
  if (appState.generalVisitCandidatesLoading) return;
  if (
    !force
    && String(appState.generalVisitCandidatesAccountId || "") === sessionId
    && appState.generalVisitCandidates.length
  ) return;
  if (!selectedAccount()?.session) {
    appState.generalVisitCandidatesAccountId = sessionId;
    appState.generalVisitCandidatesError = "当前账号尚未启动，请先启动账号后再查询名将";
    appState.generalVisitCandidatesNotice = "";
    if (dailySettingsPageIsActive()) render();
    return;
  }

  appState.generalVisitCandidatesAccountId = sessionId;
  appState.generalVisitCandidatesLoading = true;
  appState.generalVisitCandidatesError = "";
  appState.generalVisitCandidatesNotice = "";
  if (dailySettingsPageIsActive()) render();
  try {
    const data = await apiPost(
      "/api/daily/general-visit/candidates",
      { sessionId },
      { timeoutMs: 90000, timeoutMessage: "查询可拜访名将超时，请稍后重试" },
    );
    if (String(appState.sessionId || "") !== sessionId) return;
    const candidates = Array.isArray(data.generals)
      ? data.generals
      : (Array.isArray(data.candidates) ? data.candidates : []);
    appState.generalVisitCandidates = candidates.map(candidate => ({ ...candidate }));
    appState.generalVisitCandidatesNotice = data.skipped
      ? (data.message || "国民跳过")
      : data.alreadyVisited
        ? (data.message || "本日已经完成名将拜访")
        : "";
    appState.generalVisitCandidatesUpdatedAt = Number(data.updatedAt || Date.now());
    const availableIds = new Set(
      appState.generalVisitCandidates
        .filter(generalVisitCandidateAvailable)
        .map(candidate => String(candidate.id ?? candidate.idInt ?? ""))
        .filter(Boolean)
    );
    const before = normalizeGeneralVisitIds(appState.brushSettings.generalVisitGeneralIds);
    const retained = before.filter(id => availableIds.has(id));
    appState.brushSettings.generalVisitGeneralIds = retained;
    const removed = before.filter(id => !availableIds.has(id));
    if (removed.length) {
      appendLog(`名将候选已更新：${removed.length}个原优先目标当前不可拜访，已从本次未保存选择中移除。`);
    }
    appendLog(data.skipped
      ? `名将候选查询已跳过：${appState.generalVisitCandidatesNotice}`
      : data.alreadyVisited
      ? `名将候选查询完成：${appState.generalVisitCandidatesNotice}`
      : `名将候选查询完成：共${candidates.length}名，其中${availableIds.size}名当前可拜访。`);
  } catch (error) {
    if (String(appState.sessionId || "") !== sessionId) return;
    appState.generalVisitCandidates = [];
    appState.generalVisitCandidatesUpdatedAt = 0;
    appState.generalVisitCandidatesError = error.message || "名将候选查询失败";
    appState.generalVisitCandidatesNotice = "";
    appendLog(`名将候选查询失败：${appState.generalVisitCandidatesError}`);
    showToast("名将候选查询失败", "error");
  } finally {
    if (String(appState.sessionId || "") === sessionId) {
      appState.generalVisitCandidatesLoading = false;
      if (dailySettingsPageIsActive()) render();
    }
  }
}
async function syncAccounts({ silent = true, summary = false } = {}) {
  if (summary && document.hidden) return appState.accounts || [];
  try {
    const res = await fetch(summary ? "/api/accounts?summary=1" : "/api/accounts");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "账号列表刷新失败");
    const previousDailyStatsSignature = JSON.stringify(appState.dailyStats || {});
    const incomingAccounts = Array.isArray(data.accounts) ? data.accounts : [];
    if (summary) {
      const existingById = new Map(
        (appState.accounts || []).map(account => [String(account.sessionId), account])
      );
      let needsFullRefresh = false;
      appState.accounts = incomingAccounts.map(summaryAccount => {
        const previous = existingById.get(String(summaryAccount.sessionId));
        if (summaryAccount.hasLiveSession && !previous?.session) needsFullRefresh = true;
        const merged = { ...(previous || {}), ...summaryAccount };
        if (merged.session && summaryAccount.dailyStats) {
          merged.session = {
            ...merged.session,
            dailyStats: summaryAccount.dailyStats,
          };
        }
        if (!summaryAccount.hasLiveSession) {
          merged.session = null;
          merged.accountHabits = summaryAccount.accountHabits || previous?.accountHabits;
        }
        return merged;
      });
      if (needsFullRefresh) return syncAccounts({ silent, summary: false });
    } else {
      appState.accounts = incomingAccounts;
    }
    const preferredSaved = savedAccountForCurrentContainer(appState.accounts);
    if (appState.sessionId) {
      let cur = appState.accounts.find(a => String(a.sessionId) === String(appState.sessionId));
      if (!cur) {
        const currentUsername = String(appState.username || "");
        const currentAreaName = String(appState.area?.areaName || "");
        cur = appState.accounts.find(a =>
          String(a.username || "") === currentUsername &&
          (!currentAreaName || String(a.areaName || "") === currentAreaName)
        ) || preferredSaved || null;
        if (cur?.sessionId) appState.sessionId = cur.sessionId;
      }
      if (cur?.session) {
        appState.displayDataSessionId = appState.sessionId;
        appState.role = cur.session.role || appState.role;
        appState.roleState = cur.session.roleState || appState.roleState || {};
        appState.technologyStates = cur.session.technologyStates || appState.technologyStates || [];
        appState.generals = cur.session.generals || appState.generals || [];
        appState.army = cur.session.army || cur.session.roleState?.idleArmy || appState.army || [];
        appState.inventory = cur.session.inventory || appState.inventory || { items: [] };
        appState.militaryIntel = cur.session.militaryIntel || appState.militaryIntel || { events: [], statusByName: {} };
        appState.dailyActivity = cur.session.dailyActivity || appState.dailyActivity || {};
        appState.dailyStats = cur.dailyStats || cur.session.dailyStats || appState.dailyStats || { brushYellowCount: 0, dungeonCount: 0 };
        appState.roleQueueSummary = cur.session.roleQueueSummary || appState.roleQueueSummary || {};
        appState.taskOverview = cur.session.taskOverview || appState.taskOverview || { resident: [], daily: [] };
        if (!appState.accountHabitsLoaded[appState.sessionId]) {
          restoreAccountUi(appState.sessionId);
          applyServerHabits(cur.session);
          appState.accountHabitsLoaded[appState.sessionId] = true;
          snapshotCurrentAccountUi();
        }
      } else if (cur) {
        if (hasLiveDisplayForCurrentAccount()) applyAccountRecordMeta(cur);
        else applyAccountRecord(cur, { restoreUi: true });
      } else if (preferredSaved?.session) {
        applySessionData(preferredSaved.session);
      } else if (preferredSaved) {
        applyAccountRecord(preferredSaved);
      } else if (appState.accounts[0]?.session) {
        applySessionData(appState.accounts[0].session);
      } else if (appState.accounts[0]) {
        applyAccountRecord(appState.accounts[0]);
      }
    } else if (preferredSaved?.session) {
      applySessionData(preferredSaved.session);
    } else if (preferredSaved) {
      applyAccountRecord(preferredSaved);
    } else if (appState.accounts[0]?.session) {
      applySessionData(appState.accounts[0].session);
    } else if (appState.accounts[0]) {
      applyAccountRecord(appState.accounts[0]);
    }
    updateAccountHeader();
    const dailyStatsChanged = previousDailyStatsSignature !== JSON.stringify(appState.dailyStats || {});
    if (
      summary
      && dailyStatsChanged
      && activeMainPage === "助手"
      && activeCategory === "角色"
      && activeSide === "任务"
    ) {
      render();
    } else if (!summary && activeMainPage === "助手" && (activeCategory === "军情" || activeCategory === "角色")) {
      render();
    }
    return appState.accounts;
  } catch (e) {
    if (!silent) appendLog("刷新账号列表失败：" + e.message);
    return appState.accounts || [];
  }
}

async function selectAccount(sessionId) {
  const acc = (appState.accounts || []).find(a => String(a.sessionId) === String(sessionId));
  if (!acc) {
    showToast("账号记录不存在", "error");
    return;
  }
  if (acc.session) applySessionData(acc.session, { restoreUi: true });
  else applyAccountRecord(acc, { restoreUi: true });
  saveCurrentContainerSelection(acc);
  await loadAccountLog(appState.sessionId, { force: true });
  if (activeCategory === "角色" && activeSide === "记录") {
    await refreshSuccessRecords({ silent: true });
  }
  await loadProxyNodes();
  appendLog(`已切换展示账号：${accountLabel(acc)}；不改变该账号启动/掉线状态。${acc.session ? "" : " 当前还未启动，暂无实时角色/将领数据。"}`);
  render();
}

async function startSelectedAccount() {
  try {
    if (!appState.sessionId) throw new Error("请先添加并选择账号");
    const acc = selectedAccount();
    if (!confirm(`确认启动当前账号？\n${accountLabel(acc)}`)) return;
    const oldSessionId = appState.sessionId;
    appendLog(`正在启动账号：${accountLabel(selectedAccount())}；现在才执行真实登录并开启保活...`);
    const data = await apiPost("/api/accounts/start", { sessionId: oldSessionId });
    const newSessionId = data.account?.sessionId || oldSessionId;
    if (newSessionId !== oldSessionId) {
      appState.accountUiState[newSessionId] = appState.accountUiState[oldSessionId] || {};
      delete appState.accountUiState[oldSessionId];
      appState.sessionId = newSessionId;
    }
    if (data.account?.session) applySessionData(data.account.session, { restoreUi: true });
    await syncAccounts();
    await loadProxyNodes();
    saveCurrentContainerSelection(selectedAccount() || data.account);
    notifyAccountsChanged("start");
    showToast(data.account?.status === "online" ? "账号启动成功" : "账号疑似掉线", data.account?.status === "online" ? "success" : "error");
    appendLog(`账号状态：${data.account?.statusText || accountStatusText(data.account?.status)}；${data.account?.lastHeartbeat?.message || ""}`);
    if (data.account?.session) {
      const rs = data.account.session.roleState || {};
      appendLog(`真实登录完成：${rs.roleName || data.account.session.role?.roleName || accountLabel(data.account)} Lv.${rs.level ?? data.account.session.role?.level ?? "-"}，将领 ${appState.generals.length} 个`);
    }
    render();
  } catch (e) {
    appendLog("启动账号失败：" + e.message);
    showToast("启动账号失败", "error");
  }
}

async function stopSelectedAccount() {
  try {
    if (!appState.sessionId) throw new Error("请先选择账号");
    const acc = selectedAccount();
    if (!confirm(`确认关闭当前账号？\n${accountLabel(acc)}`)) return;
    const data = await apiPost("/api/accounts/stop", { sessionId: appState.sessionId });
    await syncAccounts();
    saveCurrentContainerSelection(selectedAccount() || data.account);
    notifyAccountsChanged("stop");
    appendLog(`已关闭账号并退出本地会话：${accountLabel(data.account)}`);
    showToast("账号已关闭", "success");
    render();
  } catch (e) {
    appendLog("关闭账号失败：" + e.message);
    showToast("关闭账号失败", "error");
  }
}

async function deleteSelectedAccount() {
  try {
    if (!appState.sessionId) throw new Error("请先选择账号");
    const acc = selectedAccount();
    if (!confirm(`确认删除当前账号？\n${accountLabel(acc)}`)) return;
    const old = appState.sessionId;
    const data = await apiPost("/api/accounts/delete", { sessionId: old });
    delete appState.accountUiState[old];
    appState.accounts = data.accounts || [];
    const next = appState.accounts[0];
    if (next?.session) {
      applySessionData(next.session);
    } else if (next) {
      applyAccountRecord(next);
    } else {
      appState.sessionId = null;
      appState.displayDataSessionId = null;
      appState.username = "";
      appState.role = null;
      appState.roleState = {};
      appState.area = null;
      appState.generals = [];
      appState.army = [];
      appState.inventory = { items: [] };
      appState.militaryIntel = { events: [], statusByName: {} };
      appState.dailyStats = { brushYellowCount: 0, dungeonCount: 0 };
      appState.roleQueueSummary = {};
      restoreAccountUi("");
    }
    if (appState.sessionId) saveCurrentContainerSelection(selectedAccount());
    else clearCurrentContainerSelection();
    notifyAccountsChanged("delete");
    appendLog(`已删除账号：${accountLabel(acc)}`);
    showToast("账号已删除", "success");
    render();
  } catch (e) {
    appendLog("删除账号失败：" + e.message);
    showToast("删除账号失败", "error");
  }
}

function renderLog() {
  const defaultLog = "暂无运行日志。点击“启动”登录账号，或在配兵/刷黄页保存设置后，这里会显示真实操作日志。";
  renderAccountLogLines(true, defaultLog);
}

function renderAccountLogLines(scrollToLatest = false, defaultLog = "") {
  const lines = (runtimeLog || defaultLog).split("\n");
  document.querySelectorAll("#taskLog,#taskLogPage").forEach(el => {
    el.innerHTML = lines.map((line, index) => {
      const selected = accountLogSelectionStart?.index === index && accountLogSelectionStart?.text === line ? " copy-start" : "";
      return `<div class="account-log-line${selected}" data-log-index="${index}">${escHtml(line)}</div>`;
    }).join("");
    el.onclick = handleAccountLogLineClick;
    if (scrollToLatest) el.scrollTop = el.scrollHeight;
  });
}

async function handleAccountLogLineClick(event) {
  const line = event.target.closest(".account-log-line[data-log-index]");
  if (!line || !runtimeLog) return;
  const lines = runtimeLog.split("\n");
  const index = Number(line.dataset.logIndex);
  const clicked = lines[index];
  if (!Number.isInteger(index) || clicked === undefined) return;
  if (accountLogSelectionStart === null) {
    accountLogSelectionStart = { index, text: clicked };
    renderAccountLogLines(false);
    showToast("已选择复制起始行，请点击结束行", "info");
    return;
  }
  if (index === accountLogSelectionStart.index && clicked === accountLogSelectionStart.text) {
    accountLogSelectionStart = null;
    renderAccountLogLines(false);
    showToast("已取消日志选择", "info");
    return;
  }
  const startIndex = accountLogSelectionStart.index;
  if (startIndex < 0 || lines[startIndex] !== accountLogSelectionStart.text) {
    accountLogSelectionStart = null;
    renderAccountLogLines(false);
    showToast("起始日志已被清除，请重新选择", "error");
    return;
  }
  const from = Math.min(startIndex, index);
  const to = Math.max(startIndex, index);
  accountLogSelectionStart = null;
  renderAccountLogLines(false);
  try {
    await copyTextToClipboard(lines.slice(from, to + 1).join("\n"));
    showToast(`已复制 ${to - from + 1} 行日志`, "success");
  } catch (error) {
    showToast("复制日志失败：" + error.message, "error");
  }
}
function getBrushForm() {
  saveBrushDom();
  applyActiveBrushRuleOrThrow();
  const b = appState.brushSettings;
  (b.rows || []).forEach((row, index) => {
    if (row.enabled && rowGeneralIds(row).length > 5) {
      throw new Error(`第 ${index + 1} 条刷黄规则最多选择5名出征将领`);
    }
  });
  return {
    sessionId: appState.sessionId,
    startX: Number(b.startX || 0),
    startY: Number(b.startY || 0),
    scanLimit: Number(b.scanLimit || 80),
    targetKind: b.targetKind || "山贼",
    levels: normalizeBrushLevels(b.levels, b.level),
    level: normalizeBrushLevels(b.levels, b.level)[0],
    drops: normalizeBrushDrops(b.drops ?? b.drop, []),
    drop: firstBrushDrop(b.drops ?? b.drop),
    generalId: String(b.generalId || rowGeneralIds(appState.formations[0])[0] || ""),
    generalIds: rowGeneralIds(b),
    rows: Array.isArray(b.rows) ? b.rows.map(row => {
      const ids = rowGeneralIds(row);
      const levels = normalizeBrushLevels(row.levels, row.level);
      return { ...row, generalIds: ids, generalId: String(ids[0] || ""), levels, level: levels[0] };
    }) : [],
    compositionCode: b.compositionCode,
    compositionFilter: {
      maxFoot: Number(b.maxFoot || 0),
      maxBow: Number(b.maxBow || 0),
      maxCavalry: Number(b.maxCavalry || 0),
      maxChariot: Number(b.maxChariot || 0),
      requireFoot: !!b.requireFoot,
    }
  };
}
function getRaidForm() {
  saveRaidDom();
  const raid = appState.raidSettings || defaultRaidSettings();
  const rows = (raid.rows || []).map(row => {
    const ids = rowGeneralIds(row);
    return {
      enabled: !!row.enabled,
      generalIds: ids,
      generalId: String(ids[0] || ""),
      playerName: String(row.playerName || "").trim(),
      fiefIndex: Number(row.fiefIndex || 0),
      fullTroops: raid.fullTroops !== false,
      fullLoyalty: !!raid.fullLoyalty,
      duration: "立即出征",
    };
  });
  if (!rows.some(r => r.enabled)) throw new Error("请先勾选至少一条掠夺规则");
  rows.forEach((r, idx) => {
    if (!r.enabled) return;
    if (!r.generalIds.length) throw new Error(`第 ${idx + 1} 条掠夺规则未选择出征将领`);
    if (r.generalIds.length > 5) throw new Error(`第 ${idx + 1} 条掠夺规则最多选择5名出征将领`);
    if (!r.playerName) throw new Error(`第 ${idx + 1} 条掠夺规则未填写玩家名称`);
    if (!r.fiefIndex || r.fiefIndex <= 0) throw new Error(`第 ${idx + 1} 条掠夺规则封地序号必须大于 0`);
  });
  return {
    sessionId: appState.sessionId,
    confirm: "raid",
    rows
  };
}
const militaryFutureFeatureMap = { "无损": "lossless", "副本": "dungeon", "押镖": "escort", "寻宝": "treasure" };
function getMilitaryFutureForm(feature) {
  saveFutureMilitaryDom();
  const all = mergeMilitaryFutureSettings(appState.militaryFutureSettings);
  const settings = all[feature];
  if (!settings) throw new Error("未知军事配置页");
  return {
    sessionId: appState.sessionId,
    feature,
    settings,
  };
}
function getLosslessForm() {
  saveFutureMilitaryDom();
  const settings = mergeMilitaryFutureSettings(appState.militaryFutureSettings).lossless;
  const rows = (settings.rows || []).map(row => {
    const generalIds = rowGeneralIds(row);
    return {
      enabled: row.enabled === true,
      generalIds,
      generalId: String(generalIds[0] || ""),
      level: row.level || "10级",
      fullTroops: settings.fullTroops !== false,
    };
  });
  rows.forEach((row, index) => {
    if (!row.enabled) return;
    if (!row.generalIds.length) throw new Error(`第 ${index + 1} 条无损规则未选择出征将领`);
    if (row.generalIds.length > 5) throw new Error(`第 ${index + 1} 条无损规则最多选择5名出征将领`);
  });
  return {
    sessionId: appState.sessionId,
    confirm: "lossless",
    settings: {
      fullTroops: settings.fullTroops !== false,
      rows,
    },
  };
}
function getDungeonForm() {
  saveFutureMilitaryDom();
  const settings = mergeMilitaryFutureSettings(appState.militaryFutureSettings).dungeon;
  const rows = (settings.rows || []).map(row => {
    const ids = rowGeneralIds(row);
    return {
      enabled: !!row.enabled,
      generalIds: ids,
      generalId: String(ids[0] || ""),
      chapter: row.chapter || "第一章",
      stage: String(row.stage || "1"),
      chest: row.chest || "右",
      openChest: true,
    };
  });
  if (rows.filter(r => r.enabled).length > 1) throw new Error("副本编队同一时间只能启用一条");
  rows.forEach((r, idx) => {
    if (!r.enabled) return;
    if (!r.generalIds.length) throw new Error(`第 ${idx + 1} 条副本规则未选择出征将领`);
    if (r.generalIds.length > 5) throw new Error(`第 ${idx + 1} 条副本规则最多选择5名出征将领`);
    if (settings.mode !== "clear") {
      if (!r.chapter) throw new Error(`第 ${idx + 1} 条副本规则未选择章节`);
      if (!r.stage) throw new Error(`第 ${idx + 1} 条副本规则未选择关卡`);
    }
  });
  return {
    sessionId: appState.sessionId,
    confirm: "dungeon",
    mode: settings.mode === "clear" ? "clear" : "loop",
    rows
  };
}
function selectedGeneralIdsInRoot(root) {
  const picker = root?.classList?.contains("formation-general-multi")
    ? root
    : root?.querySelector?.(".formation-general-multi");
  if (!picker) return [];
  const checked = new Set(Array.from(picker.querySelectorAll(".formation-general-check:checked"))
    .map(x => String(x.value || "")).filter(Boolean));
  const stored = String(picker.dataset.selectedOrder || "").split(",").filter(id => checked.has(id));
  const storedSet = new Set(stored);
  for (const input of picker.querySelectorAll(".formation-general-check:checked")) {
    const id = String(input.value || "");
    if (id && !storedSet.has(id)) {
      stored.push(id);
      storedSet.add(id);
    }
  }
  picker.dataset.selectedOrder = stored.join(",");
  return stored;
}
function syncGeneralMultiUi(root) {
  if (!root) return;
  const ids = selectedGeneralIdsInRoot(root);
  const maxSelected = Number(root.dataset.maxSelected || 0);
  const limitReached = maxSelected > 0 && ids.length >= maxSelected;
  const anchorId = ids[0] || "";
  const anchorInput = anchorId
    ? Array.from(root.querySelectorAll(".formation-general-check"))
      .find(input => String(input.value) === anchorId)
    : null;
  const anchorFiefId = String(anchorInput?.dataset.fiefId || "");
  root.querySelectorAll(".formation-general-option").forEach(label => {
    const input = label.querySelector(".formation-general-check");
    const selected = !!input?.checked;
    const fiefId = String(input?.dataset.fiefId || "");
    const incompatible = !selected && !!anchorFiefId && fiefId !== anchorFiefId;
    const disabledByLimit = !selected && limitReached;
    label.classList.toggle("selected", selected);
    label.classList.toggle("disabled-by-fief", incompatible);
    label.classList.toggle("disabled-by-limit", disabledByLimit);
    if (input) input.disabled = incompatible || disabledByLimit;
    label.title = incompatible
      ? "该将领与当前编队首位将领不在同一封地"
      : (disabledByLimit ? `每个出征编队最多选择${maxSelected}名将领` : "");
  });
  root.dataset.anchorFiefId = anchorFiefId;
  const summary = root.querySelector(".formation-general-summary");
  if (summary) summary.textContent = formationGeneralSummary(ids);
}
function syncGeneralMultiScope(scope = document) {
  scope.querySelectorAll(".formation-general-multi").forEach(syncGeneralMultiUi);
}
function saveGeneralMultiOwner(root) {
  if (!root) return;
  if (root.classList.contains("formation-picker") || root.closest(".formation-row")) {
    saveFormationDom();
    return;
  }
  if (root.classList.contains("brush-general-picker") || root.closest(".brush-rule-row")) {
    saveBrushDom();
    return;
  }
  if (root.classList.contains("military-general-picker") || root.closest(".raid-table") || root.closest(".mine-table") || root.closest(".lossless-table") || root.closest(".dungeon-table") || root.closest(".escort-table") || root.closest(".hunt-table")) {
    saveRaidDom();
    saveMineDom();
    saveFutureMilitaryDom();
  }
}
function bindDesignDynamicControls() {
  document.querySelectorAll(".dynamic-delete").forEach(btn => btn.onclick = () => {
    const tr = btn.closest("tr");
    const tbody = tr?.parentElement;
    if (!tr || !tbody) return;
    if (tbody.children.length <= 1) {
      tr.querySelectorAll("input").forEach(input => {
        if (input.type === "checkbox") input.checked = false;
        else input.value = "";
      });
      tr.querySelectorAll("select").forEach(select => { select.selectedIndex = 0; });
      syncDungeonStageSelect(tr.querySelector(".dungeon-chapter"));
      syncGeneralMultiScope(tr);
      return;
    }
    tr.remove();
  });
  document.querySelectorAll(".dynamic-add").forEach(btn => btn.onclick = () => {
    const root = btn.closest(".design-page") || document;
    const tbody = root.querySelector("table.dynamic-table tbody");
    const base = tbody?.querySelector("tr:last-child");
    if (!tbody || !base) return;
    const clone = base.cloneNode(true);
    clone.querySelectorAll("input").forEach(input => {
      if (input.type === "checkbox") input.checked = false;
      else if (input.type === "number") input.value = input.value || "0";
      else input.value = input.placeholder || "";
    });
    clone.querySelectorAll("select").forEach(select => { select.selectedIndex = 0; });
    syncGeneralMultiScope(clone);
    tbody.appendChild(clone);
    bindDesignDynamicControls();
  });
  document.querySelectorAll(".dynamic-copy").forEach(btn => btn.onclick = () => {
    const root = btn.closest(".design-page") || document;
    const tbody = root.querySelector("table.dynamic-table tbody");
    if (!tbody) return;
    const checkedRows = Array.from(tbody.querySelectorAll("tr")).filter(tr => tr.querySelector("input[type='checkbox']")?.checked);
    const srcRows = checkedRows.length ? checkedRows : Array.from(tbody.querySelectorAll("tr")).slice(0, 1);
    srcRows.forEach(row => {
      const clone = row.cloneNode(true);
      if (root.classList.contains("dungeon-page")) {
        const enabled = clone.querySelector(".dungeon-enabled");
        if (enabled) enabled.checked = false;
      }
      tbody.appendChild(clone);
    });
    bindDesignDynamicControls();
  });
  document.querySelectorAll(".dynamic-clear").forEach(btn => btn.onclick = () => {
    const root = btn.closest(".design-page") || document;
    const tbody = root.querySelector("table.dynamic-table tbody");
    if (!tbody) return;
    Array.from(tbody.querySelectorAll("tr")).slice(1).forEach(tr => tr.remove());
    const first = tbody.querySelector("tr");
    if (first) {
      first.querySelectorAll("input").forEach(input => {
        if (input.type === "checkbox") input.checked = false;
        else if (input.type === "number") input.value = "0";
        else input.value = "";
      });
      first.querySelectorAll("select").forEach(select => { select.selectedIndex = 0; });
      syncDungeonStageSelect(first.querySelector(".dungeon-chapter"));
      syncGeneralMultiScope(first);
    }
  });
  document.querySelectorAll(".ghost-add-general").forEach(btn => btn.onclick = () => {
    const td = btn.closest("td");
    if (!td) return;
    btn.insertAdjacentHTML("beforebegin", generalSelect("", "extra-general-select"));
  });
  document.querySelectorAll(".design-mini-btn").forEach(btn => btn.onclick = () => {
    appendLog(`已点击“${btn.textContent.trim()}”：该按钮目前作为配置开关占位，后续接入对应原版接口。`);
    showToast("按钮可点击，接口待接入", "info");
  });
  document.querySelectorAll(".dungeon-chapter").forEach(select => {
    syncDungeonStageSelect(select);
    select.onchange = () => {
      syncDungeonStageSelect(select);
      saveFutureMilitaryDom();
    };
  });
  document.querySelectorAll(".dungeon-stage,.dungeon-chest").forEach(el => {
    el.onchange = saveFutureMilitaryDom;
  });
  document.querySelectorAll(".dungeon-enabled").forEach(el => {
    el.onchange = () => {
      enforceSingleDungeonEnabled(el);
      saveFutureMilitaryDom();
    };
  });
}
function syncPolicyMultiUi(root) {
  if (!root) return;
  const selected = Array.from(root.querySelectorAll(".policy-multi-check:checked")).map(input => input.value);
  root.querySelectorAll(".policy-multi-option").forEach(option => {
    option.classList.toggle("selected", !!option.querySelector(".policy-multi-check")?.checked);
  });
  const summary = root.querySelector(".policy-multi-summary");
  const summaryValues = root.dataset.policy === "technology-ids"
    ? selected.map(value => technologyNames[Number(value)]).filter(Boolean)
    : selected;
  if (summary) summary.textContent = policyMultiSummary(summaryValues);
}
function bindPolicyMultiControls() {
  document.querySelectorAll(".policy-multi").forEach(root => {
    syncPolicyMultiUi(root);
    root.querySelector(".policy-multi-summary")?.addEventListener("click", event => {
      event.stopPropagation();
      document.querySelectorAll(".policy-multi.open").forEach(other => {
        if (other !== root) other.classList.remove("open");
      });
      root.classList.toggle("open");
    });
    root.querySelectorAll(".policy-multi-check").forEach(input => {
      input.onchange = () => {
        syncPolicyMultiUi(root);
      };
    });
    root.querySelector(".policy-multi-search")?.addEventListener("input", event => {
      const query = String(event.target.value || "").trim();
      root.querySelectorAll(".policy-multi-option").forEach(option => {
        option.style.display = !query || option.textContent.includes(query) ? "flex" : "none";
      });
    });
    root.querySelector(".policy-multi-all")?.addEventListener("click", () => {
      root.querySelectorAll(".policy-multi-check").forEach(input => { input.checked = true; });
      syncPolicyMultiUi(root);
    });
    root.querySelector(".policy-multi-clear")?.addEventListener("click", () => {
      root.querySelectorAll(".policy-multi-check").forEach(input => { input.checked = false; });
      syncPolicyMultiUi(root);
    });
  });
}
function bindBrushLevelMultiControls() {
  document.querySelectorAll(".brush-level-multi").forEach(root => {
    syncBrushLevelMultiUi(root);
    root.querySelector(".brush-level-summary")?.addEventListener("click", event => {
      event.stopPropagation();
      document.querySelectorAll(".brush-level-multi.open").forEach(other => {
        if (other !== root) other.classList.remove("open");
      });
      root.classList.toggle("open");
    });
    root.querySelectorAll(".brush-level-check").forEach(input => {
      input.onchange = () => {
        if (!root.querySelector(".brush-level-check:checked")) input.checked = true;
        syncBrushLevelMultiUi(root);
        saveBrushDom();
      };
    });
  });
}
function bindLiveControls() {
  bindDesignDynamicControls();
  syncGeneralMultiScope();
  bindPolicyMultiControls();
  bindBrushLevelMultiControls();
  document.querySelectorAll(".daily-task-toggle").forEach(input => {
    input.onchange = () => {
      saveDailySettingsDom();
      if (String(input.dataset.task || "") !== "generalVisit") return;
      if (input.checked) {
        void loadGeneralVisitCandidates({ force: false });
      } else {
        render();
      }
    };
  });
  const refreshGeneralVisit = document.getElementById("refreshGeneralVisitCandidates");
  if (refreshGeneralVisit) {
    refreshGeneralVisit.onclick = (e) => {
      e.stopPropagation();
      saveDailySettingsDom();
      void loadGeneralVisitCandidates({ force: true });
    };
  }
  document.querySelectorAll(".general-visit-summary").forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const root = btn.closest(".general-visit-multi");
      document.querySelectorAll(".general-visit-multi.open").forEach(x => {
        if (x !== root) x.classList.remove("open");
      });
      root?.classList.toggle("open");
    };
  });
  document.querySelectorAll(".general-visit-candidate-check").forEach(input => {
    input.onchange = () => {
      const id = String(input.value || "");
      const root = input.closest(".general-visit-multi");
      let selected = normalizeGeneralVisitIds(appState.brushSettings.generalVisitGeneralIds);
      if (input.checked) {
        if (!selected.includes(id) && selected.length >= 4) {
          input.checked = false;
          showToast("名将拜访最多选择4名将领", "error");
          syncGeneralVisitMultiUi(root);
          return;
        }
        selected = selected.filter(value => value !== id);
        selected.push(id);
      } else {
        selected = selected.filter(value => value !== id);
      }
      appState.brushSettings.generalVisitGeneralIds = selected.slice(0, 4);
      if (input.checked) showToast(`已设为第${appState.brushSettings.generalVisitGeneralIds.length}优先`, "info");
      // 就地同步，避免 render() 关闭下拉
      syncGeneralVisitMultiUi(root);
    };
  });
  const visitToggle = document.querySelector('.daily-task-toggle[data-task="generalVisit"]');
  const visitAccountMatches = String(appState.generalVisitCandidatesAccountId || "") === String(appState.sessionId || "");
  if (
    visitToggle?.checked
    && !appState.generalVisitCandidatesLoading
    && !appState.generalVisitCandidatesError
    && (!visitAccountMatches || !appState.generalVisitCandidatesUpdatedAt)
  ) {
    Promise.resolve().then(() => loadGeneralVisitCandidates({ force: false }));
  }
  document.querySelectorAll(".success-record-switch button").forEach(button => {
    button.onclick = () => {
      successRecordType = button.dataset.recordType === "politics" ? "politics" : "military";
      render();
    };
  });
  const treasureSearch = document.getElementById("treasureSearchInput");
  if (treasureSearch) {
    treasureSearch.oninput = () => {
      treasureSearchQuery = treasureSearch.value;
      render();
      const nextInput = document.getElementById("treasureSearchInput");
      nextInput?.focus();
      nextInput?.setSelectionRange(nextInput.value.length, nextInput.value.length);
    };
  }
  document.querySelectorAll('input[name="targetPick"]').forEach(r => r.onchange = () => { appState.selectedTargetId = r.value; });
  [
    "brushStartHour","shStartX","shStartY","shScanLimit","shTargetKind","requireFoot","dailyLimit",
    "cycleDelaySec","returnWaitSec","replenishTroops","cleanMail"
  ].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.onchange = () => { saveBrushDom(); };
  });
  document.querySelectorAll(".brush-enabled,.brush-drop,.brush-compose-select").forEach(el => el.onchange = saveBrushDom);
  const toggleAllBrush = document.getElementById("toggleAllBrushRules");
  if (toggleAllBrush) {
    const checks = Array.from(document.querySelectorAll(".brush-enabled"));
    const checked = checks.filter(x => x.checked).length;
    toggleAllBrush.checked = checks.length > 0 && checked === checks.length;
    toggleAllBrush.indeterminate = checked > 0 && checked < checks.length;
    toggleAllBrush.onchange = () => {
      checks.forEach(x => { x.checked = toggleAllBrush.checked; });
      toggleAllBrush.indeterminate = false;
      saveBrushDom();
    };
  }
  document.querySelectorAll(".brush-delete").forEach(btn => btn.onclick = () => {
    saveBrushDom();
    appState.brushSettings.rows.splice(Number(btn.dataset.index), 1);
    render();
  });
  const addBrush = document.getElementById("addBrushRuleBtn");
  if (addBrush) addBrush.onclick = () => {
    saveBrushDom();
    if (!Array.isArray(appState.brushSettings.rows)) appState.brushSettings.rows = brushRowsForDesign();
    appState.brushSettings.rows.push(brushPlaceholderRow());
    render();
  };
  const clearBrush = document.getElementById("clearBrushRulesBtn");
  if (clearBrush) clearBrush.onclick = () => {
    appState.brushSettings.rows = [];
    render();
  };
  document.querySelectorAll(".formation-soldier,.formation-count,.formation-enabled").forEach(el => el.onchange = saveFormationDom);
  document.querySelectorAll(".formation-general-summary").forEach(btn => btn.onclick = (e) => {
    e.stopPropagation();
    const root = btn.closest(".formation-general-multi");
    document.querySelectorAll(".formation-general-multi.open").forEach(x => { if (x !== root) x.classList.remove("open"); });
    root?.classList.toggle("open");
  });
  document.querySelectorAll(".formation-general-check").forEach(el => el.onchange = () => {
    const root = el.closest(".formation-general-multi");
    const maxSelected = Number(root?.dataset.maxSelected || 0);
    if (el.checked && maxSelected > 0 && selectedGeneralIdsInRoot(root).length > maxSelected) {
      el.checked = false;
      showToast(`每个出征编队最多选择${maxSelected}名将领`, "error");
      syncGeneralMultiUi(root);
      return;
    }
    const currentIds = selectedGeneralIdsInRoot(root);
    const anchorInput = currentIds.length
      ? Array.from(root.querySelectorAll(".formation-general-check"))
        .find(input => String(input.value) === currentIds[0])
      : null;
    const anchorFiefId = String(anchorInput?.dataset.fiefId || "");
    const selectedFiefId = String(el.dataset.fiefId || "");
    if (el.checked && anchorFiefId && selectedFiefId !== anchorFiefId) {
      el.checked = false;
      showToast("同一编队的将领必须位于同一封地", "error");
      syncGeneralMultiUi(root);
      return;
    }
    const order = selectedGeneralIdsInRoot(root).filter(id => id !== String(el.value || ""));
    if (el.checked) order.push(String(el.value || ""));
    if (root) root.dataset.selectedOrder = order.join(",");
    syncGeneralMultiUi(root);
    saveGeneralMultiOwner(root);
  });
  document.querySelectorAll(".formation-general-search").forEach(input => input.oninput = () => {
    const q = String(input.value || "").trim();
    input.closest(".formation-general-panel")?.querySelectorAll(".formation-general-option").forEach(label => {
      label.style.display = !q || label.textContent.includes(q) ? "flex" : "none";
    });
  });
  document.querySelectorAll(".fg-all").forEach(btn => btn.onclick = (e) => {
    e.stopPropagation();
    const root = btn.closest(".formation-general-multi");
    const currentIds = selectedGeneralIdsInRoot(root);
    const inputs = Array.from(root?.querySelectorAll(".formation-general-check") || []);
    const firstInput = currentIds.length
      ? inputs.find(input => String(input.value) === currentIds[0])
      : inputs.find(input => !input.disabled);
    const anchorFiefId = String(firstInput?.dataset.fiefId || "");
    const maxSelected = Number(root?.dataset.maxSelected || 0);
    let selectedCount = 0;
    inputs.forEach(input => {
      const eligible = !!anchorFiefId && String(input.dataset.fiefId || "") === anchorFiefId;
      input.checked = eligible && (!maxSelected || selectedCount < maxSelected);
      if (input.checked) selectedCount += 1;
    });
    if (root) {
      const previous = currentIds.filter(id => inputs.some(input => input.checked && String(input.value) === id));
      const added = inputs.map(input => String(input.value || "")).filter(id => (
        inputs.some(input => input.checked && String(input.value) === id) && !previous.includes(id)
      ));
      root.dataset.selectedOrder = [...previous, ...added].join(",");
    }
    syncGeneralMultiUi(root);
    saveGeneralMultiOwner(root);
  });
  document.querySelectorAll(".fg-clear").forEach(btn => btn.onclick = (e) => {
    e.stopPropagation();
    const root = btn.closest(".formation-general-multi");
    root?.querySelectorAll(".formation-general-check").forEach(x => { x.checked = false; });
    if (root) root.dataset.selectedOrder = "";
    syncGeneralMultiUi(root);
    saveGeneralMultiOwner(root);
  });
  document.querySelectorAll(".formation-delete").forEach(btn => btn.onclick = () => { saveFormationDom(); appState.formations.splice(Number(btn.dataset.index), 1); render(); });
  const addF = document.getElementById("addFormationBtn");
  if (addF) addF.onclick = () => { saveFormationDom(); appState.formations.push(formationPlaceholderRow()); render(); };
  const clearF = document.getElementById("clearFormationBtn");
  if (clearF) clearF.onclick = () => { appState.formations = []; render(); };
  const unassignAll = document.getElementById("unassignAllTroopsBtn");
  if (unassignAll) unassignAll.onclick = async () => {
    try {
      unassignAll.disabled = true;
      unassignAll.classList.add("is-running");
      const data = await apiPost(
        "/api/formations/unassign-all",
        {
          sessionId: appState.sessionId,
          confirm: "unassign-all-troops",
        },
        {
          timeoutMs: 300000,
          timeoutMessage: "一键卸兵执行超过5分钟，请先不要重复点击；后端可能仍在继续处理，请稍后刷新军队数据确认结果",
        },
      );
      if (data.generals) appState.generals = data.generals;
      if (data.army) appState.army = data.army;
      if (data.roleState) appState.roleState = data.roleState;
      appendLog(`一键卸兵完成：卸下 ${data.clearedCount || 0} 名将领，跳过 ${data.skippedCount || 0} 名`);
      showToast("一键卸兵完成", "success");
      render();
    } catch (e) {
      appendLog("一键卸兵失败：" + e.message);
      showToast("一键卸兵失败", "error");
    } finally {
      unassignAll.disabled = false;
      unassignAll.classList.remove("is-running");
    }
  };
  const refreshStateBtn = document.getElementById("refreshStateBtn");
  if (refreshStateBtn) refreshStateBtn.onclick = () => refreshLiveState({ silent: false, scope: "military" });
  const b0525 = document.getElementById("apply0525Btn");
  if (b0525) b0525.onclick = () => { appState.brushSettings.rows = brushRowsForDesign(); const row = appState.brushSettings.rows[0] || brushPlaceholderRow(); Object.assign(row, {maxFoot:0,maxBow:5,maxCavalry:2,maxChariot:5,compositionCode:"0525"}); appState.brushSettings.rows[0]=row; appendLog("已填入步弓骑车 0525：步≤0 弓≤5 骑≤2 车≤5"); render(); };
  const b5000 = document.getElementById("apply5000Btn");
  if (b5000) b5000.onclick = () => { appState.brushSettings.rows = brushRowsForDesign(); const row = appState.brushSettings.rows[0] || brushPlaceholderRow(); Object.assign(row, {maxFoot:5,maxBow:0,maxCavalry:0,maxChariot:0,compositionCode:"5000"}); appState.brushSettings.rows[0]=row; appState.brushSettings.requireFoot=true; appendLog("已填入步弓骑车 5000：必须含步，且不含弓骑车"); render(); };
  const sync = document.getElementById("syncLoginBtn");
  if (sync) sync.onclick = () => document.getElementById("accountModal").classList.remove("hidden");
  document.querySelectorAll('input.table-input').forEach(input => {
    if ((input.value || "").includes("请选择") || input.classList.contains("muted-input")) {
      input.classList.add("open-picker");
      input.onclick = (e) => {
        e.preventDefault();
        pickerOpen = true;
        renderPickerLayer();
      };
    }
  });
  const exec = document.getElementById("executeYellowBtn");
  if (exec) exec.onclick = async () => {
    try {
      if (!appState.sessionId) throw new Error("请先添加账号");
      if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录");
      const target = appState.targets.find(t => String(t.id) === String(appState.selectedTargetId)) || appState.targets[0];
      if (!target) throw new Error("请先找黄并选择目标");
      saveBrushDom();
      applyActiveBrushRuleOrThrow();
      const generalId = appState.brushSettings.generalId || rowGeneralIds(appState.brushSettings)[0] || "";
      if (!generalId) throw new Error("请选择出征将领");
      if (!confirm(`确认真实出征？\n将领ID=${generalId}\n目标=${target.name || target.kind}(${target.x},${target.y})`)) return;
      appendLog("开始真实刷黄：发送原版 actionType=3 的 0x1520/0x1522...");
      const data = await apiPost("/api/brush/execute", { sessionId: appState.sessionId, generalId, targetId: target.id, target, confirm: "brush-yellow" });
      appState.lastBattleText = data.battleText || "";
      if (data.dailyStats) appState.dailyStats = data.dailyStats;
      appendLog(data.success
        ? `出征已受理：battleId=${data.successBattleId || "未知"}；等待目标战报结算，当前不计数`
        : "刷黄响应未确认成功：" + (data.battleText || "无战报文本"));
      if (data.success && data.dailyBrushCount !== undefined) appendLog(`当前今日刷黄次数：${data.dailyBrushCount}`);
      if (data.reportFile) appendLog("证据文件：" + data.reportFile);
      render();
    } catch (e) { appendLog("真实出征失败：" + e.message); }
  };
}

async function saveFormationSettings() {
  try {
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录并同步将领数据");
    saveFormationDom();
    const formations = appState.formations.map(f => ({
      enabled: !!f.enabled,
      generalIds: rowGeneralIds(f),
      generalId: rowGeneralIds(f)[0] || "",
      soldierType: f.soldierType || "轻骑兵",
      soldierCount: Number(f.soldierCount || 0),
      generalNameSnapshots: {
        ...(f.generalNameSnapshots || {}),
      },
    }));
    const data = await apiPost("/api/formations/save", { sessionId: appState.sessionId, formations, formationOptions: { clearOtherGenerals: false } });
    appState.formations = data.formations || formations;
    appState.savedFormationRules = data.normalizedFormations || data.formations || formations;
    if (data.formationOptions) appState.formationOptions = { clearOtherGenerals: false, ...data.formationOptions };
    if (data.accountHabits) applyServerHabits(data);
    appendLog(`配兵规则已保存：${appState.formations.map(f => `将领=${rowGeneralIds(f).join("/")} ${f.soldierCount}${f.soldierType}`).join("；")}`);
    if (data.unresolvedGeneralIds?.length) {
      appendLog(`以下将领当前待同步，配置已保留且本次不会执行配兵：${data.unresolvedGeneralIds.join("、")}`);
    }
    if (data.savedFile) appendLog(`配兵规则文件：${data.savedFile}`);
    if (data.task?.taskId) {
      appState.automation.taskId = data.task.taskId;
      appState.automation.status = data.task.status || "starting";
      appState.automation.lastLogs = [];
      appendLog(`配兵任务已加入任务栈并开始执行：${data.task.taskId}`);
      startStatusPolling();
    } else if (data.applyTask?.reason) {
      appendLog(`配兵规则已保存，但暂不执行：${data.applyTask.reason}`);
    } else {
      appendLog("配兵规则已保存；当前没有返回配兵执行任务。");
    }
    showToast("保存配兵设置成功", "success");
    render();
  } catch (e) {
    appendLog("保存配兵规则失败：" + e.message);
    showToast("保存配兵设置失败", "error");
  }
}
async function saveRaidSettings() {
  try {
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录并同步将领数据");
    const cfg = getRaidForm();
    const enabledRows = cfg.rows.filter(r => r.enabled);
    appendLog(`保存掠夺规则：${enabledRows.map(r => `将领=${r.generalIds.join("/")} → ${r.playerName} 第${r.fiefIndex}封地`).join("；")}；满兵=${enabledRows[0]?.fullTroops ? "开启" : "关闭"}`);
    const data = await apiPost("/api/raid/execute", cfg);
    if (data.accountHabits) applyServerHabits({ accountHabits: data.accountHabits });
    if (data.savedFiles?.militaryFile) appendLog(`掠夺配置文件：${data.savedFiles.militaryFile}`);
    if (data.task?.taskId) {
      appState.automation.taskId = data.task.taskId;
      appState.automation.status = data.task.status || "starting";
      appState.automation.lastLogs = [];
      appendLog(`掠夺任务已加入任务栈并开始执行：${data.task.taskId}`);
      startStatusPolling();
    } else if (data.raidTask?.reason) {
      appendLog(`掠夺规则已提交，但暂不执行：${data.raidTask.reason}`);
    } else {
      appendLog("掠夺规则已提交；当前没有返回执行任务。");
    }
    showToast("掠夺任务已提交", "success");
    render();
  } catch (e) {
    appendLog("保存掠夺规则失败：" + e.message);
    showToast("保存掠夺设置失败", "error");
  }
}
async function saveMineSettings() {
  try {
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先启动账号并同步将领数据");
    saveMineDom();
    const settings = JSON.parse(JSON.stringify(appState.mineSettings || defaultMineSettings()));
    const enabledRows = settings.rows.filter(row => row.enabled);
    enabledRows.forEach((row, index) => {
      if (!rowGeneralIds(row).length) throw new Error(`第 ${index + 1} 条打矿规则未选择出征将领`);
      if (!mineResourceOptions.includes(row.resourceType)) throw new Error(`第 ${index + 1} 条打矿规则未选择资源类型`);
    });
    appendLog(enabledRows.length
      ? `保存打矿规则：${enabledRows.map(row => `将领=${rowGeneralIds(row).join("/")} → ${row.resourceType} ${row.scope}(${row.x},${row.y})`).join("；")}`
      : "保存打矿规则：未启用任何编队，打矿常驻任务将关闭");
    const data = await apiPost("/api/mine/save", {
      sessionId: appState.sessionId,
      settings
    });
    if (data.accountHabits) applyServerHabits({ accountHabits: data.accountHabits });
    if (data.taskOverview) appState.taskOverview = data.taskOverview;
    if (data.savedFiles?.militaryFile) appendLog(`打矿配置文件：${data.savedFiles.militaryFile}`);
    if (data.disabled) {
      appendLog(data.stoppedTaskIds?.length
        ? `打矿配置已关闭，已请求停止任务：${data.stoppedTaskIds.join("、")}`
        : "打矿配置已关闭；当前没有运行中的打矿任务。");
    } else if (data.task?.taskId) {
      appState.automation.taskId = data.task.taskId;
      appState.automation.status = data.task.status || "starting";
      appState.automation.lastLogs = [];
      appendLog(`打矿常驻任务已加入任务栈：${data.task.taskId}`);
      startStatusPolling();
    }
    showToast(data.disabled ? "打矿任务已关闭" : "打矿任务已启动", "success");
    render();
  } catch (e) {
    appendLog("保存打矿规则失败：" + e.message);
    showToast("保存打矿设置失败", "error");
  }
}
async function saveLosslessSettings() {
  try {
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录并同步将领数据");
    const cfg = getLosslessForm();
    const enabledRows = cfg.settings.rows.filter(row => row.enabled);
    appendLog(enabledRows.length
      ? `保存无损规则：${enabledRows.map(row => `将领=${row.generalIds.join("/")} → ${row.level}`).join("；")}；满兵=${cfg.settings.fullTroops ? "开启" : "关闭"}`
      : "保存无损规则：未启用任何编队，无损常驻任务将关闭");
    const data = await apiPost("/api/lossless/execute", cfg);
    if (data.accountHabits) applyServerHabits({ accountHabits: data.accountHabits });
    if (data.taskOverview) appState.taskOverview = data.taskOverview;
    if (data.savedFiles?.militaryFile) appendLog(`无损配置文件：${data.savedFiles.militaryFile}`);
    if (data.disabled) {
      const stoppedIds = Array.isArray(data.stoppedTaskIds) ? data.stoppedTaskIds : [];
      if (stoppedIds.includes(appState.automation.taskId)) appState.automation.status = "stopping";
      appendLog(stoppedIds.length
        ? `无损配置已关闭，已请求安全停止无损任务：${stoppedIds.join("、")}`
        : "无损配置已关闭；当前没有运行中的无损任务。");
    } else if (data.task?.taskId) {
      appState.automation.taskId = data.task.taskId;
      appState.automation.status = data.task.status || "starting";
      appState.automation.lastLogs = [];
      appendLog(`无损常驻任务已交给指挥中心：${data.task.taskId}，优先级低于打矿、高于刷黄和副本`);
      startStatusPolling();
    } else if (data.losslessTask?.reason) {
      appendLog(`无损规则已提交，但暂不执行：${data.losslessTask.reason}`);
    } else {
      appendLog("无损规则已提交；当前没有返回执行任务。");
    }
    showToast(data.disabled ? "无损任务已关闭" : "无损常驻任务已启动", "success");
    render();
  } catch (e) {
    appendLog("保存无损规则失败：" + e.message);
    showToast("保存无损设置失败", "error");
  }
}
async function saveDungeonSettings() {
  try {
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录并同步将领数据");
    const cfg = getDungeonForm();
    const enabledRows = cfg.rows.filter(r => r.enabled);
    appendLog(enabledRows.length
      ? `${cfg.mode === "clear" ? "保存打通副本编队" : "保存副本规则"}：${enabledRows.map(r => `将领=${r.generalIds.join("/")} → ${r.chapter}第${r.stage}关，开箱=${r.chest}`).join("；")}`
      : "保存副本规则：未启用任何编队，副本循环任务将关闭");
    const data = await apiPost("/api/dungeon/execute", cfg);
    if (data.accountHabits) applyServerHabits({ accountHabits: data.accountHabits });
    if (data.savedFiles?.militaryFile) appendLog(`副本配置文件：${data.savedFiles.militaryFile}`);
    if (data.disabled) {
      const stoppedIds = Array.isArray(data.stoppedTaskIds) ? data.stoppedTaskIds : [];
      if (stoppedIds.includes(appState.automation.taskId)) appState.automation.status = "stopping";
      appendLog(stoppedIds.length
        ? `副本配置已关闭，已请求停止副本循环任务：${stoppedIds.join("、")}`
        : "副本配置已关闭；当前没有运行中的副本任务。");
    } else if (data.task?.taskId) {
      appState.automation.taskId = data.task.taskId;
      appState.automation.status = data.task.status || "starting";
      appState.automation.lastLogs = [];
      appendLog(`${cfg.mode === "clear" ? "打通副本任务" : "副本循环任务"}已加入任务栈并开始执行：${data.task.taskId}`);
      startStatusPolling();
    } else if (data.dungeonTask?.reason) {
      appendLog(`副本规则已提交，但暂不执行：${data.dungeonTask.reason}`);
    } else {
      appendLog("副本规则已提交；当前没有返回执行任务。");
    }
    showToast(
      data.disabled
        ? "副本任务已关闭"
        : (cfg.mode === "clear" ? "打通副本任务已提交" : "副本循环任务已提交"),
      "success",
    );
    render();
  } catch (e) {
    appendLog("保存副本规则失败：" + e.message);
    showToast("保存副本设置失败", "error");
  }
}
async function saveMilitaryFutureSettings() {
  const feature = militaryFutureFeatureMap[activeSide];
  try {
    if (!feature) throw new Error("当前页面不是可保存的军事预备功能");
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录并同步将领数据");
    const payload = getMilitaryFutureForm(feature);
    const data = await apiPost("/api/military/future/save", payload);
    if (data.accountHabits) applyServerHabits({ accountHabits: data.accountHabits });
    const r = data.readiness || {};
    appendLog(`${activeSide}配置已保存：${r.message || "等待接入真实接口"}`);
    if (data.savedFiles?.militaryFile) appendLog(`${activeSide}配置文件：${data.savedFiles.militaryFile}`);
    showToast(`${activeSide}配置已保存`, "success");
    render();
  } catch (e) {
    appendLog(`保存${activeSide}配置失败：` + e.message);
    showToast(`保存${activeSide}配置失败`, "error");
  }
}

async function saveCommonSettings() {
  const side = activeSide;
  try {
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录");
    const scope = commonSettingsScope(side);
    if (!scope) throw new Error(`当前子页面“${side}”没有可保存的设置`);
    const patch = buildCommonSettingsPatch(side);
    const data = await apiPost("/api/settings/save", {
      sessionId: appState.sessionId,
      scope,
      patch,
    });
    if (data.accountHabits) applyServerHabits({ accountHabits: data.accountHabits });
    const settingsWarnings = Array.isArray(data.settingsWarnings)
      ? data.settingsWarnings.filter(Boolean)
      : [];
    settingsWarnings.forEach(message => appendLog(`设置提示：${message}`));

    if (side === "常用") {
      appendLog(
        `常规-常用保存成功：治疗伤兵=${patch.healWounded ? "开启" : "关闭"}，` +
        `自动加体=${patch.autoEnergy ? `开启（体力<${patch.energyThreshold}）` : "关闭"}，` +
        `自动内政=${patch.domestic.enabled ? "开启" : "关闭"}，粮食转铜=${patch.foodToCopper ? "开启" : "关闭"}；` +
        "其他子页面设置未修改。"
      );
      if (data.domesticTask && !data.domesticTask.skipped) {
        appendLog(data.domesticTask.started
          ? `自动内政已启动：任务 ${data.domesticTask.task?.taskId || "已创建"}`
          : `自动内政未启动：${data.domesticTask.reason || "开关已关闭"}`);
      }
      if (data.technologyTask && !data.technologyTask.skipped) {
        appendLog(data.technologyTask.started
          ? `升级科技已启动：任务 ${data.technologyTask.task?.taskId || "已创建"}`
          : `升级科技未启动：${data.technologyTask.reason || "开关已关闭"}`);
      }
    } else if (side === "日常") {
      const enabled = Object.entries(patch.dailyTasks)
        .filter(([, value]) => value)
        .map(([key]) => ({
          autoSignIn: "自动签到",
          arenaCoins: "领竞技币",
          autoDonate: "自动捐献",
          salary: "领取俸禄",
          nationalCollect: "国家征收",
          cityLordCollect: "城主征收",
          generalVisit: "名将拜访",
        })[key] || key);
      const visitPriority = patch.dailyTasks.generalVisit
        ? `；名将优先级=${patch.generalVisitGeneralIds.join("→")}`
        : "";
      appendLog(`常规-日常保存成功：${enabled.length ? `已开启${enabled.join("、")}` : "全部关闭"}${visitPriority}；其他子页面设置未修改。`);
    } else {
      appendLog(
        `常规-主号物品保存成功：宝库清理=${patch.cleanInventory ? "开启" : "关闭"}，` +
        `自动开箱=${patch.autoOpenEnabled ? "开启" : "关闭"}；其他子页面设置未修改。`
      );
      const result = data.autoOpenResult || {};
      const opened = Number(result.opened || 0);
      if (opened) appendLog(`自动开箱完成：本轮成功开启 ${opened} 个`);
      (result.actions || []).filter(item => item?.success).forEach(item => {
        const quantity = Math.max(1, Number(item.openedCount || item.count || 1));
        const reward = String(item.message || "")
          .replace(/<br\s*\/?>/gi, "；")
          .replace(/<[^>]+>/g, "")
          .split(/[；;]/)
          .map(part => part.trim())
          .filter(Boolean)
          .join("；") || "服务器确认成功，未返回奖励说明";
        appendLog(`自动开箱结果：${item.itemName || "宝箱"}${quantity > 1 ? ` ×${quantity}` : ""} → ${reward}`);
      });
      (result.skipped || []).forEach(item => appendLog(`自动开箱跳过：${item.name}；${item.reason}`));
    }
    if (data.savedFile) appendLog(`设置文件：${data.savedFile}`);
    showToast(
      settingsWarnings.length
        ? `常规-${side}其他设置已保存，名将拜访未开启`
        : `常规-${side}设置保存成功`,
      settingsWarnings.length ? "info" : "success"
    );
    render();
  } catch (e) {
    appendLog(`保存常规-${side}设置失败：${e.message}`);
    showToast(`保存常规-${side}设置失败`, "error");
  }
}

async function saveSettingsAndStart() {
  try {
    if (!appState.sessionId) throw new Error("请先添加账号");
    if (!selectedAccount()?.session) throw new Error("当前账号还未启动，请先点击“启动”完成真实登录并同步将领数据");
    const cfg = buildAutoConfig();
    if (cfg.autoStart && !cfg.brush.generalId) throw new Error("请先在“军事-配兵”或“刷黄”页选择出征将领");
    if (cfg.autoStart) {
      const generalIds = (cfg.brush.rows || [])
        .filter(row => row.enabled)
        .flatMap(row => row.generalIds || []);
      try {
        const recommendation = await apiPost("/api/brush/recommended-center", {
          sessionId: appState.sessionId,
          generalIds,
        });
        const accepted = await showBrushCenterRecommendation(recommendation);
        if (accepted) {
          cfg.brush.startX = Number(recommendation.x);
          cfg.brush.startY = Number(recommendation.y);
          appState.brushSettings.startX = cfg.brush.startX;
          appState.brushSettings.startY = cfg.brush.startY;
          const xInput = document.getElementById("shStartX");
          const yInput = document.getElementById("shStartY");
          if (xInput) xInput.value = String(cfg.brush.startX);
          if (yInput) yInput.value = String(cfg.brush.startY);
        }
      } catch (error) {
        appendLog(`无法计算推荐中心坐标，将按当前坐标保存：${error.message}`);
      }
    }
    appendLog(cfg.autoStart
        ? `保存刷黄规则：将领=${cfg.brush.generalId}，每日${cfg.startHour}点开始，中心=(${cfg.brush.startX},${cfg.brush.startY})，筛选=${cfg.brush.compositionCode}，批量补满=${cfg.replenishTroops ? "开启" : "关闭"}；将按“军事-配兵”规则检查后启动后台刷黄...`
        : "保存刷黄规则：当前未勾选任何编队，将关闭刷黄常驻任务。");
    const data = await apiPost("/api/settings/save", {
      sessionId: appState.sessionId,
      scope: "brush",
      patch: cfg,
    });
    if (data.accountHabits) applyServerHabits({ accountHabits: data.accountHabits });
    appState.automation.taskId = data.disabled ? null : (data.task?.taskId || null);
    appState.automation.status = data.disabled ? "stopped" : (data.task?.status || "saved");
    appState.automation.lastLogs = [];
    appendLog(data.disabled
      ? `保存成功，刷黄任务已关闭${data.stoppedTaskIds?.length ? `：${data.stoppedTaskIds.join("、")}` : ""}`
      : data.waitingForMilitaryStart
        ? "保存成功，刷黄任务等待点击“开始执行任务”"
        : `保存成功，后台任务已启动：${appState.automation.taskId || "未返回任务ID"}`);
    if (data.savedFile) appendLog(`设置文件：${data.savedFile}`);
    const dailyResults = data.dailyResults || {};
    Object.entries(dailyResults).forEach(([key, result]) => {
      const label = { autoSignIn: "自动签到", arenaCoins: "领取竞技币", autoDonate: "自动捐献" }[key] || key;
      const fallback = key === "arenaCoins"
        ? "当前不可领取：可能未到22点，或今日已经领取"
        : "服务器未返回说明";
      appendLog(`${label}${result.success ? "完成" : "失败"}：${result.message || fallback}`);
    });
    if (data.autoOpenResult) {
      const opened = Number(data.autoOpenResult.opened || 0);
      const actions = Array.isArray(data.autoOpenResult.actions) ? data.autoOpenResult.actions : [];
      const skipped = Array.isArray(data.autoOpenResult.skipped) ? data.autoOpenResult.skipped : [];
      if (opened) appendLog(`自动开箱完成：本轮成功开启 ${opened} 个`);
      actions.filter(item => item?.success).forEach(item => {
        const quantity = Math.max(1, Number(item.openedCount || item.count || 1));
        const reward = String(item.message || "")
          .replace(/<br\s*\/?>/gi, "；")
          .replace(/<[^>]+>/g, "")
          .split(/[；;]/)
          .map(part => part.trim())
          .filter(Boolean)
          .join("；") || "服务器确认成功，未返回奖励说明";
        appendLog(`自动开箱结果：${item.itemName || "宝箱"}${quantity > 1 ? ` ×${quantity}` : ""} → ${reward}`);
      });
      skipped.forEach(item => appendLog(`自动开箱跳过：${item.name}；${item.reason}`));
    }
    if (data.domesticTask && !data.domesticTask.skipped) {
      appendLog(data.domesticTask.started
        ? `自动内政已启动：任务 ${data.domesticTask.task?.taskId || "已创建"}`
        : `自动内政未启动：${data.domesticTask.reason || "开关已关闭"}`);
    }
    if (data.technologyTask && !data.technologyTask.skipped) {
      appendLog(data.technologyTask.started
        ? `升级科技已启动：任务 ${data.technologyTask.task?.taskId || "已创建"}`
        : `升级科技未启动：${data.technologyTask.reason || "开关已关闭"}`);
    }
    showToast(data.disabled ? "刷黄任务已关闭" : "保存刷黄设置成功", "success");
    if (!data.disabled) startStatusPolling();
    if (activeCategory === "刷黄") render();
  } catch (e) {
    appendLog("保存设置失败：" + e.message);
    showToast("保存刷黄设置失败", "error");
  }
}
function showBrushCenterRecommendation(recommendation) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "center-recommend-overlay";
    const location = [recommendation.cityName, recommendation.fiefName].filter(Boolean).join(" · ");
    overlay.innerHTML = `
      <section class="center-recommend-dialog" role="dialog" aria-modal="true" aria-labelledby="centerRecommendTitle">
        <h2 id="centerRecommendTitle">推荐中心坐标</h2>
        <p>建议您将中心坐标设置为 <b>(${escHtml(recommendation.x)}, ${escHtml(recommendation.y)})</b>，这个设置距离山贼更近，可以加快任务进度！</p>
        ${location ? `<div class="center-recommend-source">依据：${escHtml(location)}</div>` : ""}
        <div class="center-recommend-actions">
          <button class="accept" type="button">接受并保存</button>
          <button class="keep" type="button">不改了直接保存</button>
        </div>
      </section>`;
    const finish = accepted => {
      overlay.remove();
      resolve(accepted);
    };
    overlay.querySelector(".accept").onclick = () => finish(true);
    overlay.querySelector(".keep").onclick = () => finish(false);
    document.body.appendChild(overlay);
  });
}
let statusTimer = null;
let stateRefreshTimer = null;
let accountsTimer = null;
let taskOverviewTimer = null;
let taskCountdownTimer = null;
let successRecordsTimer = null;
let automationStatusRequestPending = false;

async function refreshRoleSide(side = activeSide, { silent = true } = {}) {
  if (side === "任务" || side === "提示") return refreshTaskOverview({ silent });
  if (side === "记录") return refreshSuccessRecords({ silent });
  return refreshLiveState({ silent, scope: roleSideRefreshScope(side), side });
}

async function refreshTaskOverview({ silent = true } = {}) {
  return pollAutomationStatus({ silent });
}

async function refreshSuccessRecords({ silent = true } = {}) {
  if (!appState.sessionId) {
    appState.successRecords = [];
    if (!silent) appendLog("请先选择账号");
    if (activeCategory === "角色" && activeSide === "记录") render();
    return;
  }
  try {
    if (activeCategory === "起号" && activeSide === "记录") {
      const response = await fetch(
        `/api/starter/account-view?accountId=${encodeURIComponent(appState.sessionId)}`,
        { cache: "no-store" },
      );
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || "读取起号记录失败");
      }
      const previous = JSON.stringify(appState.starterRecords || []);
      starterContainerView = data.view || {};
      starterContainerViewAccountId = String(appState.sessionId || "");
      appState.starterRecords = starterContainerView.records || [];
      if (previous !== JSON.stringify(appState.starterRecords)) render();
      return;
    }
    const category = isStarterContainer && activeSide === "刷黄记录"
      ? "刷黄"
      : isStarterContainer && activeSide === "副本记录"
        ? "副本"
        : "";
    const response = await fetch(
      `/api/success-records?sessionId=${encodeURIComponent(appState.sessionId)}&limit=50`
        + (category ? `&category=${encodeURIComponent(category)}` : ""),
      { cache: "no-store" },
    );
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "读取成功记录失败");
    const previous = JSON.stringify(appState.successRecords || []);
    appState.successRecords = data.entries || [];
    if (
      (
        ((activeCategory === "角色" || activeCategory === "起号") && activeSide === "记录")
        || (isStarterContainer && ["刷黄记录", "副本记录"].includes(activeSide))
      )
      && previous !== JSON.stringify(appState.successRecords)
    ) render();
  } catch (error) {
    if (!silent) appendLog("成功记录刷新失败：" + error.message);
  }
}

async function startSavedTasks() {
  const button = document.getElementById("startSavedTasksBtn");
  if (!appState.sessionId || !selectedAccount()?.session) {
    showToast("请先启动账号", "error");
    return;
  }
  try {
    if (button) button.disabled = true;
    const data = await apiPost("/api/automation/start-saved", { sessionId: appState.sessionId });
    if (data.taskOverview) appState.taskOverview = data.taskOverview;
    const resumed = Object.keys(data.result?.resumed || {});
    const errors = Object.entries(data.result?.errors || {});
    appendLog(data.alreadyStarted
      ? "该账号本次登录的保存任务已经提交，无需重复启动"
      : `开始执行保存任务：${resumed.length ? resumed.join("、") : "当前没有可恢复的常驻任务"}`);
    errors.forEach(([name, message]) => appendLog(`恢复任务失败：${name}；${message}`));
    showToast(errors.length ? "任务已提交，部分恢复失败" : "任务已开始执行", errors.length ? "error" : "success");
    render();
  } catch (error) {
    if (button) button.disabled = false;
    appendLog("开始执行任务失败：" + error.message);
    showToast("开始执行任务失败", "error");
  }
}

async function startAllSavedTasks() {
  const button = document.getElementById("startAllSavedTasksBtn");
  if (!button || button.disabled) return;
  const originalText = button.textContent;
  try {
    button.disabled = true;
    button.textContent = "正在提交...";
    const data = await apiPost("/api/automation/start-saved-all", {});
    const eligible = Number(data.eligibleCount || 0);
    const started = Number(data.startedCount || 0);
    const already = Number(data.alreadyStartedCount || 0);
    const failed = Number(data.failedCount || 0);
    appendLog(
      `一键开始全部任务：运行中账号${eligible}个，已提交${started}个，`
      + `已启动${already}个，失败${failed}个`,
    );
    (data.results || []).filter(item => item.status === "error" || item.status === "partial")
      .forEach(item => {
        const label = [item.username, item.areaName].filter(Boolean).join("@");
        const reason = Object.values(item.errors || {}).join("；") || "未知错误";
        appendLog(`批量开始任务失败：${label || item.sessionId}；${reason}`);
      });
    showToast(
      eligible
        ? `已对${eligible}个运行中账号提交任务${failed ? `，${failed}个有异常` : ""}`
        : "当前没有已启动且在线的账号",
      failed ? "error" : "success",
    );
    if (appState.sessionId) void refreshAutomationStatus(true);
    if (!document.getElementById("desktopDashboard")?.classList.contains("page-hidden")) {
      void loadDesktopDashboard();
    }
  } catch (error) {
    appendLog("一键开始全部任务失败：" + error.message);
    showToast("一键开始全部任务失败", "error");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function dismissImportantNotice(button) {
  const noticeKey = String(button?.dataset?.noticeKey || "");
  if (!noticeKey || !appState.sessionId || button.disabled) return;
  button.disabled = true;
  try {
    const data = await apiPost("/api/notices/dismiss", {
      sessionId: appState.sessionId,
      noticeKey,
    });
    if (data.taskOverview) {
      appState.taskOverview = data.taskOverview;
    } else {
      appState.taskOverview.notices = (appState.taskOverview?.notices || [])
        .filter(item => String(item.key || "") !== noticeKey);
    }
    render();
    showToast("提示已删除", "success");
  } catch (error) {
    button.disabled = false;
    showToast("删除提示失败", "error");
    appendLog("删除提示失败：" + error.message);
  }
}

document.addEventListener("click", event => {
  if (event.target?.closest?.("#startAllSavedTasksBtn")) startAllSavedTasks();
  if (event.target?.closest?.("#startSavedTasksBtn")) startSavedTasks();
  const noticeButton = event.target?.closest?.(".important-notice-brief[data-notice-key]");
  if (noticeButton) dismissImportantNotice(noticeButton);
  const taskGroupButton = event.target?.closest?.("[data-starter-task-group]");
  if (taskGroupButton) {
    starterTaskGroup = String(taskGroupButton.dataset.starterTaskGroup || "growth");
    starterSelectedTaskId = "";
    render();
  }
  const taskButton = event.target?.closest?.("[data-starter-task-id]");
  if (taskButton) {
    starterSelectedTaskId = String(taskButton.dataset.starterTaskId || "");
    render();
  }
  if (event.target?.closest?.("[data-starter-task-refresh]")) {
    refreshStarterTaskPage();
  }
  if (event.target?.closest?.("[data-starter-recruit-refresh]")) {
    refreshStarterRecruitPage();
  }
  if (event.target?.closest?.("[data-starter-record-refresh]")) {
    refreshSuccessRecords({ silent: false });
  }
});

async function refreshLiveState({ silent = false, scope = "all", side = activeSide } = {}) {
  if (!appState.sessionId) return;
  if (!selectedAccount()?.session) {
    if (!silent) appendLog("当前账号还未启动，暂无实时状态；请先点击“启动”完成真实登录。");
    return;
  }
  try {
    const url = `/api/state/refresh?sessionId=${encodeURIComponent(appState.sessionId)}&scope=${encodeURIComponent(scope)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "刷新失败");
    appState.displayDataSessionId = appState.sessionId;
    appState.role = data.role || appState.role;
    appState.roleState = data.roleState || appState.roleState || {};
    appState.technologyStates = data.technologyStates || appState.technologyStates || [];
    appState.generals = data.generals || appState.generals || [];
    appState.army = data.army || data.roleState?.idleArmy || appState.army || [];
    appState.inventory = data.inventory || appState.inventory || { items: [] };
    appState.militaryIntel = data.militaryIntel || appState.militaryIntel || { events: [], statusByName: {} };
    appState.dailyActivity = data.dailyActivity || appState.dailyActivity || {};
    appState.dailyStats = data.dailyStats || appState.dailyStats || { brushYellowCount: 0, dungeonCount: 0 };
    appState.roleQueueSummary = data.roleQueueSummary || appState.roleQueueSummary || {};
    if (Array.isArray(data.unresolvedGeneralIds)) {
      appState.unresolvedGeneralIds = [...new Set(data.unresolvedGeneralIds.map(id => String(id)))];
    }
    appState.taskOverview = data.taskOverview || appState.taskOverview || { resident: [], daily: [] };
    updateAccountHeader();
    if (!silent) appendLog(`实时状态已刷新：${side || activeSide}，将领 ${appState.generals.length} 个，铜钱=${fmtNum(appState.roleState?.copper)}，粮食=${fmtNum(appState.roleState?.food)}`);
    if (
      activeCategory === "角色" || activeCategory === "军情"
      || (isStarterContainer && activeCategory === "起号")
    ) render();
  } catch (e) {
    if (!silent) appendLog("实时状态刷新失败：" + e.message);
  }
}

function updateStateRefreshPolling() {
  if (stateRefreshTimer) {
    clearInterval(stateRefreshTimer);
    stateRefreshTimer = null;
  }
  const taskPageOpen = activeMainPage === "助手"
    && activeCategory === "角色"
    && (activeSide === "任务" || activeSide === "提示");
  if (taskPageOpen && !statusTimer && !taskOverviewTimer) {
    taskOverviewTimer = setInterval(() => refreshTaskOverview({ silent: true }), 2000);
  } else if ((!taskPageOpen || statusTimer) && taskOverviewTimer) {
    clearInterval(taskOverviewTimer);
    taskOverviewTimer = null;
  }
  const countdownPageOpen = taskPageOpen && activeSide === "任务";
  if (countdownPageOpen && !taskCountdownTimer) {
    taskCountdownTimer = setInterval(updateTaskCountdowns, 1000);
  } else if (!countdownPageOpen && taskCountdownTimer) {
    clearInterval(taskCountdownTimer);
    taskCountdownTimer = null;
  }
  if (countdownPageOpen) updateTaskCountdowns();
  const recordPageOpen = activeMainPage === "助手"
    && (
      (activeCategory === "角色" && activeSide === "记录")
      || (isStarterContainer && ["记录", "刷黄记录", "副本记录"].includes(activeSide))
    );
  if (recordPageOpen && !successRecordsTimer) {
    successRecordsTimer = setInterval(
      () => refreshSuccessRecords({ silent: true }),
      3000,
    );
  } else if (!recordPageOpen && successRecordsTimer) {
    clearInterval(successRecordsTimer);
    successRecordsTimer = null;
  }
}

function startStatusPolling() {
  if (statusTimer) clearInterval(statusTimer);
  if (taskOverviewTimer) {
    clearInterval(taskOverviewTimer);
    taskOverviewTimer = null;
  }
  statusTimer = setInterval(pollAutomationStatus, 2000);
  pollAutomationStatus();
}
function startAccountsPolling() {
  if (accountsTimer) return;
  accountsTimer = setInterval(() => syncAccounts({ silent: true, summary: true }), 5000);
}
async function pollAutomationStatus({ silent = true } = {}) {
  if (!appState.sessionId || document.hidden || automationStatusRequestPending) return;
  automationStatusRequestPending = true;
  try {
    const previousOverviewSignature = JSON.stringify(appState.taskOverview || {});
    const previousTaskSignature = JSON.stringify([
      appState.automation.currentTask?.taskId,
      appState.automation.currentTask?.status,
      appState.automation.currentTask?.updatedAt,
    ]);
    const res = await fetch(`/api/automation/status?sessionId=${encodeURIComponent(appState.sessionId)}`);
    const data = await res.json();
    if (!data.ok) return;
    if (data.taskOverview) appState.taskOverview = data.taskOverview;
    const task = appState.automation.taskId
      ? (data.tasks || []).find(t => t.taskId === appState.automation.taskId) || data.tasks?.[0]
      : data.tasks?.[0];
    const taskPageOpen = activeCategory === "角色" && (activeSide === "任务" || activeSide === "提示");
    if (!task) {
      if (taskPageOpen && previousOverviewSignature !== JSON.stringify(appState.taskOverview || {})) render();
      return;
    }
    appState.automation.currentTask = task;
    appState.automation.taskId = task.taskId;
    appState.automation.status = task.status;
    const old = new Set(appState.automation.lastLogs || []);
    const fresh = (task.logs || []).filter(line => !old.has(line));
    fresh.slice(-8).forEach(line => appendLog(line.replace(/^\[\d\d:\d\d:\d\d\]\s*/, "后台：")));
    appState.automation.lastLogs = task.logs || [];
    if (["finished","stopped","error"].includes(task.status) && statusTimer && !taskPageOpen) {
      clearInterval(statusTimer);
      statusTimer = null;
    }
    const nextTaskSignature = JSON.stringify([task.taskId, task.status, task.updatedAt]);
    if (
      taskPageOpen
      && (
        previousOverviewSignature !== JSON.stringify(appState.taskOverview || {})
        || previousTaskSignature !== nextTaskSignature
      )
    ) {
      render();
    }
  } catch (error) {
    if (!silent) appendLog("任务状态刷新失败：" + error.message);
  } finally {
    automationStatusRequestPending = false;
  }
}

function render() {
  renderMainPageShell();
  updateAccountHeader();
  if (activeMainPage === "助手") {
    renderTabs();
    renderSide();
    const menus = currentSideMenus();
    document.querySelector(".workspace")?.classList.toggle("no-side", menus.length === 0);
    document.getElementById("contentCard").innerHTML = renderContent();
    bindLiveControls();
    renderPickerLayer();
  } else {
    pickerOpen = false;
    renderPickerLayer();
  }
  renderLog();
  updateStateRefreshPolling();
  updateTaskCountdowns();
}

window.addEventListener("error", e => appendLog("页面脚本错误：" + (e.message || e.error?.message || "unknown")));
window.addEventListener("unhandledrejection", e => appendLog("页面异步错误：" + (e.reason?.message || e.reason || "unknown")));
const saveBtn = document.querySelector(".save-btn");
if (saveBtn) {
  saveBtn.onclick = async () => {
    if (saveSettingsInFlight) {
      showToast("设置正在保存，请勿重复点击", "info");
      return;
    }
    saveSettingsInFlight = true;
    saveBtn.disabled = true;
    const originalText = saveBtn.textContent;
    saveBtn.textContent = "保存中...";
    try {
      if (
        (activeCategory === "军事" && activeSide === "配兵")
        || (activeCategory === "起号" && activeSide === "军队")
      ) {
        appendLog("已点击保存设置：当前为“军事-配兵”，保存规则；若任务栈空闲则立即执行配兵。");
        await saveFormationSettings();
        return;
      }
      if (activeCategory === "军事" && activeSide === "掠夺") {
        appendLog("已点击保存设置：当前为“军事-掠夺”，保存规则；若任务栈空闲则立即执行掠夺。");
        await saveRaidSettings();
        return;
      }
      if (activeCategory === "军事" && activeSide === "无损") {
        appendLog("已点击保存设置：当前为“军事-无损”，保存规则并交给指挥中心持续调度。");
        await saveLosslessSettings();
        return;
      }
      if (
        (activeCategory === "军事" && activeSide === "副本")
        || (isStarterContainer && activeCategory === "副本" && activeSide === "副本配置")
      ) {
        appendLog("已点击保存设置：当前为“军事-副本”，保存规则；若任务栈空闲则启动持续副本循环。");
        await saveDungeonSettings();
        return;
      }
      if (activeCategory === "军事" && militaryFutureFeatureMap[activeSide]) {
        appendLog(`已点击保存设置：当前为“军事-${activeSide}”，先保存配置；真实执行按抓包完整度逐步接入。`);
        await saveMilitaryFutureSettings();
        return;
      }
      if (activeCategory === "刷黄" && (!isStarterContainer || activeSide === "刷黄配置")) {
        appendLog("已点击保存设置：当前为“刷黄”，保存刷黄规则并启动后台。");
        await saveSettingsAndStart();
        return;
      }
      if (activeCategory === "打矿") {
        appendLog("已点击保存设置：当前为“打矿”，保存规则并启停打矿常驻任务。");
        await saveMineSettings();
        return;
      }
      if (activeCategory === "常规" && ["常用", "日常", "主号物品"].includes(activeSide)) {
        await saveCommonSettings();
        return;
      }
      appendLog(`当前页面“${activeCategory}-${activeSide}”暂不需要保存。`);
      showToast("当前页面暂无可保存设置", "info");
    } finally {
      saveSettingsInFlight = false;
      saveBtn.disabled = false;
      saveBtn.textContent = originalText;
    }
  };
}
document.querySelectorAll(".bottom-item[data-page]").forEach(item => {
  item.onclick = () => {
    discardActivePageChanges();
    const nextPage = item.dataset.page || "助手";
    if (nextPage === "其他" && activeMainPage !== "其他") activeOtherView = "home";
    activeMainPage = nextPage;
    render();
  };
});
document.querySelectorAll(".quick-switch-btn[data-page]").forEach(item => {
  item.onclick = () => {
    discardActivePageChanges();
    activeMainPage = item.dataset.page || "助手";
    render();
  };
});
const viewAccountSettingsBtn = document.getElementById("viewAccountSettingsBtn");
if (viewAccountSettingsBtn) viewAccountSettingsBtn.onclick = loadRawAccountSettings;
const homeAccountSelect = document.getElementById("homeAccountSelect");
if (homeAccountSelect) {
  homeAccountSelect.onchange = () => {
    const content = document.getElementById("homeSettingsContent");
    if (content) content.innerHTML = `<div class="home-settings-empty">点击“查看设置”读取该账号的原始设置文件</div>`;
  };
}
const clearLogBtn = document.getElementById("clearLogBtn");
if (clearLogBtn) {
  clearLogBtn.onclick = () => {
    runtimeLog = "";
    if (appState.automation) appState.automation.lastLogs = [];
    renderLog();
  };
}
const openDungeonGuideBtn = document.getElementById("openDungeonGuideBtn");
if (openDungeonGuideBtn) {
  openDungeonGuideBtn.onclick = () => {
    activeMainPage = "其他";
    activeOtherView = "dungeon-guide";
    renderMainPageShell();
    const guide = document.getElementById("dungeonGuide");
    if (guide) guide.scrollTop = 0;
  };
}
const closeDungeonGuideBtn = document.getElementById("closeDungeonGuideBtn");
if (closeDungeonGuideBtn) {
  closeDungeonGuideBtn.onclick = () => {
    activeOtherView = "home";
    renderMainPageShell();
  };
}
function formatBanditMapTime(timestamp) {
  const value = Number(timestamp || 0);
  if (!value) return "未知";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
async function loadBanditMap() {
  const canvas = document.getElementById("banditMapCanvas");
  const empty = document.getElementById("banditMapEmpty");
  const popup = document.getElementById("banditMapPopup");
  const meta = document.getElementById("banditMapMeta");
  if (!canvas || !empty || !popup || !meta) return;
  popup.classList.add("page-hidden");
  meta.textContent = "正在读取最新地图...";
  try {
    const response = await fetch(`/api/maps/bandits?sessionId=${encodeURIComponent(appState.sessionId || "")}`, {
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "地图读取失败");
    const points = Array.isArray(data.points) ? data.points : [];
    canvas.replaceChildren();
    empty.classList.toggle("page-hidden", points.length > 0);
    meta.textContent = `${data.serverKey || "当前区服"} · ${points.length} 个最新山贼点位`;
    if (!points.length) return;
    const minX = 0, maxX = 186;
    const minY = 0, maxY = 55;
    const padding = 70;
    const unit = 8;
    const width = 186 * unit + padding * 2;
    const height = 55 * unit + padding * 2;
    const sx = x => padding + ((Number(x) - minX) / Math.max(1, maxX - minX)) * (width - padding * 2);
    const sy = y => padding + ((Number(y) - minY) / Math.max(1, maxY - minY)) * (height - padding * 2);
    canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
    appendLuoyangMarker(canvas, sx(91), sy(26), 1.35);
    const colors = ["#82909a", "#5c9bd3", "#29a36a", "#d2a32f", "#d87932", "#d64d58"];
    points.forEach(point => {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", sx(point.x));
      circle.setAttribute("cy", sy(point.y));
      circle.setAttribute("r", point.selectedForAttack ? 18 : 14);
      circle.setAttribute("fill", colors[Math.min(5, Math.max(0, Math.ceil(Number(point.level || 0) / 2)))]);
      circle.setAttribute("class", `bandit-map-point${point.selectedForAttack ? " is-selected" : ""}`);
      circle.addEventListener("click", event => {
        event.stopPropagation();
        popup.innerHTML = `
          <b>${escHtml(point.level)}级山贼</b>
          <div>坐标：(${escHtml(point.x)}, ${escHtml(point.y)})</div>
          <div>阵容：${escHtml(point.compositionCode || "无法确认")}</div>
          <div>战利品：${escHtml((point.dropCategories || []).join("、") || point.rewardDescription || "无额外掉落")}</div>
          <div>掉落ID：${escHtml((point.lootIds || []).join("、") || "无")}</div>
          <div>更新时间：${escHtml(formatBanditMapTime(point.updatedAt))}</div>
          <div>已被选中进攻：<span class="${point.selectedForAttack ? "attack-yes" : "attack-no"}">${point.selectedForAttack ? "是" : "否"}</span></div>`;
        popup.classList.remove("page-hidden");
      });
      canvas.appendChild(circle);
    });
    canvas.onclick = () => popup.classList.add("page-hidden");
  } catch (error) {
    canvas.replaceChildren();
    empty.textContent = error.message || "地图读取失败";
    empty.classList.remove("page-hidden");
    meta.textContent = "地图读取失败";
  }
}
const openBanditMapBtn = document.getElementById("openBanditMapBtn");
if (openBanditMapBtn) {
  openBanditMapBtn.onclick = () => {
    activeMainPage = "其他";
    activeOtherView = "bandit-map";
    renderMainPageShell();
    loadBanditMap();
  };
}
const closeBanditMapBtn = document.getElementById("closeBanditMapBtn");
if (closeBanditMapBtn) {
  closeBanditMapBtn.onclick = () => {
    activeOtherView = "home";
    renderMainPageShell();
  };
}
const refreshBanditMapBtn = document.getElementById("refreshBanditMapBtn");
if (refreshBanditMapBtn) refreshBanditMapBtn.onclick = loadBanditMap;
function svgElement(name, attrs = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}
function appendLuoyangMarker(canvas, x, y, scale = 1) {
  const marker = svgElement("g", {
    class: "luoyang-map-marker",
    transform: `translate(${x} ${y}) scale(${scale})`,
    "aria-label": "洛阳中心坐标（91，26）",
  });
  for (let angle = 0; angle < 360; angle += 45) {
    const radians = angle * Math.PI / 180;
    marker.appendChild(svgElement("line", {
      x1: Math.cos(radians) * 15,
      y1: Math.sin(radians) * 15,
      x2: Math.cos(radians) * 25,
      y2: Math.sin(radians) * 25,
      class: "luoyang-map-ray",
    }));
  }
  marker.appendChild(svgElement("circle", {
    cx: 0, cy: 0, r: 12, class: "luoyang-map-sun",
  }));
  const label = svgElement("text", {
    x: 31, y: 7, class: "luoyang-map-label",
  });
  label.textContent = "洛阳";
  marker.appendChild(label);
  canvas.appendChild(marker);
}

const dashboardTaskStateNames = {
  checking: "检查中",
  ready: "准备执行",
  dispatching: "正在下发",
  fighting: "执行中",
  cooldown: "冷却",
  waiting_account: "等账号",
  waiting_generals: "等将领",
  waiting_priority: "等优先任务",
  waiting_target: "等目标",
  capacity_done: "额度已满",
  daily_done: "今日完成",
  starting: "启动中",
  queued: "排队中",
  running: "执行中",
  stopping: "停止中",
  stopped: "已停止",
  error: "异常",
  idle: "空闲",
};

function dashboardTime(value) {
  const time = Number(value || 0);
  if (!time) return "-";
  return new Date(time).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function dashboardStackHtml(items, total) {
  const denominator = Math.max(1, Number(total || 0));
  return `<div class="dashboard-stack">${items.map(item => {
    const count = Math.max(0, Number(item.count || 0));
    const width = count ? Math.max(2, count * 100 / denominator) : 0;
    return `<span class="dashboard-stack-segment is-${escAttr(item.key)}" style="width:${width}%"
      title="${escAttr(item.label)} ${fmtNum(count)}"></span>`;
  }).join("")}</div>
  <div class="dashboard-chart-legend">${items.map(item =>
    `<span><i class="is-${escAttr(item.key)}"></i>${escHtml(item.label)} ${fmtNum(item.count || 0)}</span>`
  ).join("")}</div>`;
}

function dashboardRequestDots(history, limit = 10) {
  const recent = (Array.isArray(history) ? history : []).slice(-limit);
  const padded = Array(Math.max(0, limit - recent.length)).fill(null).concat(recent);
  return padded.map(item => {
    const status = item?.status === "success" ? "success" : (item?.status === "failure" ? "failure" : "");
    const title = item
      ? `${item.status === "success" ? "成功" : "失败"}${item.purpose ? ` · ${item.purpose}` : ""}${item.time ? ` · ${dashboardTime(item.time)}` : ""}`
      : "暂无请求";
    return `<span class="dashboard-request-dot ${status}" title="${escAttr(title)}"></span>`;
  }).join("");
}
function dashboardActivityHtml(activity) {
  const line = (label, value) => {
    const item = value || {};
    return `<div class="dashboard-activity-period">
      <b>${label}</b><strong>${fmtNum(item.total || 0)}</strong>
      <span>黄${fmtNum(item.brushYellow || 0)} · 副${fmtNum(item.dungeon || 0)} · 矿${fmtNum(item.mine || 0)} · 无${fmtNum(item.lossless || 0)}</span>
    </div>`;
  };
  return `<div class="dashboard-activity">
    <div class="dashboard-activity-search"><b>近5分钟找黄</b><strong>${fmtNum(activity?.banditSearch5m || 0)}</strong></div>
    <div class="dashboard-activity-periods">
      ${line("近15分钟", activity?.sorties15m)}
      ${line("近60分钟", activity?.sorties60m)}
    </div>
  </div>`;
}

function dashboardTaskHtml(account) {
  const task = account.currentTask;
  if (!task) {
    return `<div class="dashboard-current-task"><b>无后台任务</b><span>当前空闲</span></div>`;
  }
  const state = dashboardTaskStateNames[task.state] || dashboardTaskStateNames[task.status] || task.state || "执行中";
  return `<div class="dashboard-current-task">
    <b>${escHtml(task.name || "后台任务")} · ${escHtml(state)}</b>
    <span title="${escAttr(task.message || "")}">${escHtml(task.message || state)}</span>
  </div>`;
}

function dashboardDailyHtml(dailyTasks) {
  const names = [
    ["autoSignIn", "签"],
    ["arenaCoins", "竞技"],
    ["autoDonate", "捐"],
    ["salary", "俸"],
    ["nationalCollect", "国征"],
    ["cityLordCollect", "城征"],
    ["generalVisit", "访"],
  ];
  return `<div class="dashboard-daily">${names.map(([key, name]) => {
    const done = !!dailyTasks?.[key]?.completed;
    return `<b class="${done ? "is-done" : "is-pending"}" title="${escAttr(dailyTasks?.[key]?.name || name)}">${name}${done ? "✓" : "×"}</b>`;
  }).join("")}</div>`;
}

function dashboardGeneralSummaryHtml(generals) {
  const data = generals || {};
  return `<div class="dashboard-general-summary">
    <b class="is-idle">闲${fmtNum(data.idle || 0)}</b>
    <b class="is-active">战${fmtNum(data.active || 0)}</b>
    <b class="is-returning">返${fmtNum(data.returning || 0)}</b>
    <b class="is-defending">防${fmtNum(data.defending || 0)}</b>
    ${data.other ? `<b>其他${fmtNum(data.other)}</b>` : ""}
  </div>`;
}

function dashboardProgressHtml(progress) {
  const brush = progress?.brushYellow || {};
  const mine = progress?.mine || {};
  const lossless = progress?.lossless || {};
  const dungeon = progress?.dungeon || {};
  return `<div class="dashboard-progress">
    <b>黄 ${fmtNum(brush.current || 0)}/${fmtNum(brush.limit || 0)}</b>
    <b>矿 ${fmtNum(mine.current || 0)}/${fmtNum(mine.limit || 0)}</b>
    <b>无损 ${fmtNum(lossless.current || 0)}/${fmtNum(lossless.limit || 5)}</b>
    <b>副本 ${fmtNum(dungeon.current || 0)}次</b>
  </div>`;
}

function dashboardDetailHtml(account) {
  const taskItems = (account.taskStack || []).map(task => {
    const state = dashboardTaskStateNames[task.state] || task.state || task.status || "等待";
    return `<div class="dashboard-detail-item">
      <b>${escHtml(task.name || "后台任务")}</b>
      <span title="${escAttr(task.message || "")}">${escHtml(task.message || state)}</span>
    </div>`;
  }).join("");
  const generalItems = (account.generals?.items || []).map(general =>
    `<div class="dashboard-general-item">
      <b title="${escAttr(general.name || "")}">${escHtml(general.name || "未知将领")}</b>
      <span>${escHtml(general.status || "未知")}${general.soldierType ? ` · ${escHtml(general.soldierType)}${general.soldierCount !== null && general.soldierCount !== undefined ? fmtNum(general.soldierCount) : ""}` : ""}</span>
    </div>`
  ).join("");
  const noticeItems = (account.notices || []).map(notice =>
    `<div class="dashboard-notice-line" title="${escAttr(notice.message || "")}">${escHtml(notice.summary || notice.title || "重要提示")}</div>`
  ).join("");
  const logItems = (account.recentLogs || []).slice(-5).reverse().map(log =>
    `<div class="dashboard-log-line" title="${escAttr(log.message || "")}">[${escHtml(String(log.timeText || "").split(" ").pop() || "--:--:--")}] ${escHtml(log.message || "")}</div>`
  ).join("");
  const resources = account.resources || {};
  const proxy = account.proxy || {};
  const requestSummary = account.requestSummary || {};
  return `<div class="dashboard-detail">
    <section class="dashboard-detail-section">
      <h3>任务栈</h3>
      <div class="dashboard-detail-list">${taskItems || `<div class="dashboard-detail-empty">当前没有后台任务</div>`}</div>
    </section>
    <section class="dashboard-detail-section">
      <h3>将领</h3>
      <div class="dashboard-general-list">${generalItems || `<div class="dashboard-detail-empty">暂无实时将领数据</div>`}</div>
    </section>
    <section class="dashboard-detail-section">
      <h3>提示与最近日志</h3>
      ${noticeItems || ""}
      ${logItems || `<div class="dashboard-detail-empty">暂无最近日志</div>`}
    </section>
    <section class="dashboard-detail-section">
      <h3>资源与网络</h3>
      <div class="dashboard-detail-list">
        <div class="dashboard-detail-item"><b>铜钱 / 粮食</b><span>${fmtNum(resources.copper)} / ${fmtNum(resources.food)}</span></div>
        <div class="dashboard-detail-item"><b>资源点</b><span>${fmtNum(resources.resourcePointCurrent)} / ${fmtNum(resources.resourcePointCap)}</span></div>
        <div class="dashboard-detail-item"><b>公网 IP</b><span>${escHtml(proxy.ip || "-")}</span></div>
        <div class="dashboard-detail-item"><b>节点</b><span title="${escAttr(proxy.node || "")}">${escHtml(proxy.node || "-")}</span></div>
        <div class="dashboard-detail-item"><b>请求成功率</b><span>${requestSummary.successRate === null || requestSummary.successRate === undefined ? "-" : `${fmtNum(requestSummary.successRate)}%`}（${fmtNum(requestSummary.total || 0)}次）</span></div>
        <div class="dashboard-detail-item"><b>更新时间</b><span>${escHtml(dashboardTime(account.updatedAt))}</span></div>
      </div>
      <div class="dashboard-full-dots">${dashboardRequestDots(account.recentGameRequests, 30)}</div>
    </section>
  </div>`;
}

function dashboardAccountVisible(account) {
  const query = desktopDashboardQuery.trim().toLowerCase();
  // 搜索框只匹配登录账号，角色、区服、节点和 IP 不参与搜索。
  const matchesQuery = !query
    || String(account.username || "").toLowerCase().includes(query);
  if (!matchesQuery) return false;
  if (
    desktopDashboardLevelFilter !== "all"
    && String(account.level ?? "") !== desktopDashboardLevelFilter
  ) return false;
  if (
    desktopDashboardCountryFilter !== "all"
    && String(account.countryShort || "") !== desktopDashboardCountryFilter
  ) return false;
  if (desktopDashboardFilter === "online") return account.status === "online";
  if (desktopDashboardFilter === "stopped") return account.status === "stopped";
  if (desktopDashboardFilter === "attention") {
    return account.status === "offline"
      || account.status === "checking"
      || account.networkDegraded
      || account.responseUnconfirmed
      || (account.notices || []).length > 0;
  }
  return true;
}

function dashboardAccountNeedsAttention(account) {
  return account.status === "offline"
    || account.status === "checking"
    || account.networkDegraded
    || account.responseUnconfirmed
    || (account.notices || []).length > 0;
}

function syncDashboardFilterOptions(accounts) {
  const levelSelect = document.getElementById("desktopDashboardLevelFilter");
  const countrySelect = document.getElementById("desktopDashboardCountryFilter");
  const levels = [...new Set((accounts || [])
    .map(account => Number(account.level))
    .filter(Number.isFinite))]
    .sort((a, b) => a - b);
  const countries = [...new Set((accounts || [])
    .map(account => String(account.countryShort || "").trim())
    .filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "zh-CN"));
  if (levelSelect) {
    const signature = levels.join(",");
    if (levelSelect.dataset.signature !== signature) {
      levelSelect.innerHTML = `<option value="all">全部等级</option>${levels.map(level =>
        `<option value="${level}">Lv.${level}</option>`
      ).join("")}`;
      levelSelect.dataset.signature = signature;
      levelSelect.value = levels.some(level => String(level) === desktopDashboardLevelFilter)
        ? desktopDashboardLevelFilter
        : "all";
      desktopDashboardLevelFilter = levelSelect.value;
    }
  }
  if (countrySelect) {
    const signature = countries.join(",");
    if (countrySelect.dataset.signature !== signature) {
      countrySelect.innerHTML = `<option value="all">全部国家</option>${countries.map(country =>
        `<option value="${escAttr(country)}">${escHtml(country)}国</option>`
      ).join("")}`;
      countrySelect.dataset.signature = signature;
      countrySelect.value = countries.includes(desktopDashboardCountryFilter)
        ? desktopDashboardCountryFilter
        : "all";
      desktopDashboardCountryFilter = countrySelect.value;
    }
  }
}

function dashboardIpUsageClass(count) {
  if (count >= 4) return "is-usage-4";
  if (count === 3) return "is-usage-3";
  if (count === 2) return "is-usage-2";
  return "is-usage-1";
}

function dashboardIpListHtml(accounts) {
  const groups = new Map();
  (accounts || []).filter(account => account.started).forEach(account => {
    const ip = String(account.proxy?.ip || "").trim();
    if (!ip) return;
    if (!groups.has(ip)) groups.set(ip, []);
    groups.get(ip).push(account);
  });
  const items = [...groups.entries()].sort(([left], [right]) =>
    left.localeCompare(right, undefined, { numeric: true })
  );
  if (!items.length) {
    return `<div class="dashboard-ip-empty">当前没有已连接并检测到公网 IP 的账号</div>`;
  }
  return items.map(([ip, connectedAccounts]) => `
    <div class="dashboard-ip-item ${dashboardIpUsageClass(connectedAccounts.length)}">
      <div class="dashboard-ip-title">
        <b>${escHtml(ip)}</b>
        <span>${fmtNum(connectedAccounts.length)} 个账号</span>
      </div>
      <div class="dashboard-ip-accounts">${connectedAccounts.map(account =>
        `<span title="${escAttr(account.roleName || "")}">${escHtml(account.username || "-")}${account.roleName ? `（${escHtml(account.roleName)}）` : ""}</span>`
      ).join("")}</div>
    </div>
  `).join("");
}

function dashboardAttentionHtml(accounts) {
  const attentionAccounts = (accounts || []).filter(dashboardAccountNeedsAttention);
  if (!attentionAccounts.length) {
    return `<div class="dashboard-attention-empty">目前没有需要提示或关注的账号</div>`;
  }
  return attentionAccounts.map(account => {
    const messages = (account.notices || []).map(notice =>
      notice.summary || notice.title || notice.message
    ).filter(Boolean);
    if (account.status === "offline") messages.unshift(account.lastError || "账号当前掉线");
    else if (account.status === "checking") messages.unshift("账号正在检测");
    if (account.networkDegraded) messages.push("网络状态异常");
    if (account.responseUnconfirmed) messages.push("游戏服响应未确认");
    return `<div class="dashboard-attention-item">
      <b>${escHtml(account.username || "-")}</b>
      <span>${escHtml(account.roleName || "未读取角色")}</span>
      <p title="${escAttr(messages.join("；"))}">${escHtml(messages.join("；") || "需要关注")}</p>
    </div>`;
  }).join("");
}

function renderDesktopDashboard() {
  const body = document.getElementById("desktopDashboardBody");
  const meta = document.getElementById("desktopDashboardMeta");
  if (!body || !desktopDashboardData) return;
  const previousScrollTop = body.scrollTop;
  const data = desktopDashboardData;
  const mineCandidateSelect = document.getElementById("desktopDashboardMineCandidateCount");
  if (mineCandidateSelect && document.activeElement !== mineCandidateSelect) {
    mineCandidateSelect.value = String(data.mineSettings?.candidateTargetCount || 3);
  }
  syncDashboardFilterOptions(data.accounts || []);
  const totals = data.totals || {};
  const generalTotals = data.generalTotals || {};
  const visibleAccounts = (data.accounts || []).filter(dashboardAccountVisible);
  if (meta) meta.textContent = `本地快照 · ${dashboardTime(data.updatedAt)} · ${fmtNum(data.accounts?.length || 0)} 个账号 · 每60秒自动更新`;
  const accountChart = [
    { key: "online", label: "在线", count: totals.online || 0 },
    { key: "offline", label: "掉线", count: totals.offline || 0 },
    { key: "checking", label: "检测中", count: totals.checking || 0 },
    { key: "stopped", label: "未启动", count: totals.stopped || 0 },
  ];
  const generalChart = [
    { key: "idle", label: "闲", count: generalTotals.idle || 0 },
    { key: "active", label: "征/战/修", count: generalTotals.active || 0 },
    { key: "returning", label: "返", count: generalTotals.returning || 0 },
    { key: "defending", label: "防", count: generalTotals.defending || 0 },
    { key: "other", label: "其他", count: generalTotals.other || 0 },
  ];
  const rows = visibleAccounts.map(account => {
    const expanded = desktopDashboardExpanded.has(String(account.accountKey));
    const notice = (account.notices || [])[0];
    const attention = account.status === "offline" || account.networkDegraded || (account.notices || []).length;
    const requestRate = account.requestSummary?.successRate;
    return `<tr class="account-row ${attention ? "is-attention" : ""}">
      <td><button class="dashboard-expand-btn ${expanded ? "is-open" : ""}" type="button"
        data-dashboard-expand="${escAttr(account.accountKey)}" title="${expanded ? "收起详情" : "展开详情"}" aria-label="${expanded ? "收起详情" : "展开详情"}">›</button></td>
      <td>
        <div class="dashboard-account-title">
          <b class="dashboard-account-name" title="${escAttr(account.roleName || account.username || "")}">${escHtml(account.roleName || account.username || "-")}</b>
          ${account.countryShort ? `<span class="dashboard-country-badge" title="${escAttr(`${account.countryShort}国`)}">${escHtml(account.countryShort)}</span>` : ""}
        </div>
        <span class="dashboard-account-meta">${escHtml(account.username || "-")} · Lv.${fmtNum(account.level)}</span>
      </td>
      <td>${dashboardActivityHtml(account.recentActivity)}</td>
      <td>
        <div class="dashboard-status-line"><i class="dashboard-status-dot is-${escAttr(account.status || "stopped")}"></i><b>${escHtml(account.statusText || "未启动")}</b></div>
        <span class="dashboard-cell-muted" title="${escAttr(account.proxy?.node || "")}">${escHtml(account.proxy?.ip || account.areaName || "-")}</span>
      </td>
      <td>${dashboardTaskHtml(account)}</td>
      <td>${dashboardGeneralSummaryHtml(account.generals)}</td>
      <td>${dashboardProgressHtml(account.dailyProgress)}</td>
      <td>${dashboardDailyHtml(account.dailyTasks)}</td>
      <td class="dashboard-notice-cell ${notice ? "" : "is-empty"}" title="${escAttr(notice?.message || "")}">${notice ? `${escHtml(notice.summary || notice.title || "重要提示")}${account.notices.length > 1 ? `（${fmtNum(account.notices.length)}）` : ""}` : "无"}</td>
      <td>
        <div class="dashboard-request-dots">${dashboardRequestDots(account.recentGameRequests, 10)}</div>
        <span class="dashboard-request-rate">${requestRate === null || requestRate === undefined ? "暂无请求" : `成功 ${fmtNum(requestRate)}%`}</span>
      </td>
      <td class="dashboard-enter-cell"><button class="dashboard-enter-btn" type="button" data-dashboard-enter="${escAttr(account.sessionId)}">进入</button></td>
    </tr>
    ${expanded ? `<tr class="dashboard-detail-row"><td colspan="11">${dashboardDetailHtml(account)}</td></tr>` : ""}`;
  }).join("");
  body.innerHTML = `
    <section class="dashboard-kpis">
      <div class="dashboard-kpi"><span>账号总数</span><b>${fmtNum(totals.accounts || 0)}</b></div>
      <div class="dashboard-kpi is-good"><span>在线</span><b>${fmtNum(totals.online || 0)}</b></div>
      <div class="dashboard-kpi is-bad"><span>掉线</span><b>${fmtNum(totals.offline || 0)}</b></div>
      <div class="dashboard-kpi"><span>未启动</span><b>${fmtNum(totals.stopped || 0)}</b></div>
      <div class="dashboard-kpi"><span>有后台任务</span><b>${fmtNum(totals.active || 0)}</b></div>
      <div class="dashboard-kpi is-warn"><span>需要关注</span><b>${fmtNum(totals.noticeAccounts || 0)}</b></div>
    </section>
    <section class="dashboard-charts">
      <div class="dashboard-chart"><h2>账号状态</h2>${dashboardStackHtml(accountChart, totals.accounts || 0)}</div>
      <div class="dashboard-chart"><h2>将领状态</h2>${dashboardStackHtml(generalChart, generalTotals.total || 0)}</div>
    </section>
    <section class="dashboard-overview-grid">
      <div class="dashboard-attention-band">
        <div class="dashboard-table-heading"><h2>当前提示账号</h2><span>${fmtNum((data.accounts || []).filter(dashboardAccountNeedsAttention).length)} 个</span></div>
        <div class="dashboard-attention-list">${dashboardAttentionHtml(data.accounts || [])}</div>
      </div>
      <div class="dashboard-ip-band">
        <div class="dashboard-table-heading"><h2>IP 当前连接账号</h2><span>绿1 / 浅黄2 / 深橙3 / 红4+</span></div>
        <div class="dashboard-ip-list">${dashboardIpListHtml(data.accounts || [])}</div>
      </div>
    </section>
    <section class="dashboard-table-band">
      <div class="dashboard-table-heading"><h2>全部账号（固定顺序）</h2><span>显示 ${fmtNum(visibleAccounts.length)}/${fmtNum(data.accounts?.length || 0)}</span></div>
      <div class="dashboard-table-scroll">
        ${rows ? `<table class="dashboard-account-table">
          <thead><tr><th></th><th>账号</th><th>今日出征</th><th>连接 / IP</th><th>当前任务</th><th>将领</th><th>今日进度</th><th>日常</th><th>提示</th><th>最近请求</th><th class="dashboard-enter-head">操作</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>` : `<div class="desktop-dashboard-empty">没有符合条件的账号</div>`}
      </div>
    </section>`;
  body.scrollTop = previousScrollTop;
}

async function loadDesktopDashboard({ showLoading = false } = {}) {
  if (desktopDashboardLoading) return;
  const body = document.getElementById("desktopDashboardBody");
  const refreshButton = document.getElementById("refreshDesktopDashboardBtn");
  desktopDashboardLoading = true;
  if (refreshButton) {
    refreshButton.disabled = true;
    refreshButton.textContent = "刷新中…";
  }
  if (showLoading && body && !desktopDashboardData) {
    body.innerHTML = `<div class="desktop-dashboard-loading">正在读取全部账号状态...</div>`;
  }
  try {
    const response = await fetch("/api/dashboard", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "总控数据读取失败");
    desktopDashboardData = data;
    renderDesktopDashboard();
  } catch (error) {
    if (body) body.innerHTML = `<div class="desktop-dashboard-error">读取失败：${escHtml(error.message)}</div>`;
  } finally {
    desktopDashboardLoading = false;
    if (refreshButton) {
      refreshButton.disabled = false;
      refreshButton.textContent = "↻ 立即刷新";
    }
  }
}

function openDesktopDashboard() {
  const dashboard = document.getElementById("desktopDashboard");
  if (!dashboard) return;
  dashboard.classList.remove("page-hidden");
  loadDesktopDashboard({ showLoading: true });
  loadDashboardStarterMode({ silent: true });
  if (desktopDashboardTimer) clearInterval(desktopDashboardTimer);
  desktopDashboardTimer = setInterval(() => {
    if (!document.hidden && !dashboard.classList.contains("page-hidden")) {
      loadDesktopDashboard();
      loadDashboardStarterMode({ silent: true });
    }
  }, DESKTOP_DASHBOARD_POLL_INTERVAL_MS);
}

function closeDesktopDashboard() {
  document.getElementById("desktopDashboard")?.classList.add("page-hidden");
  if (desktopDashboardTimer) {
    clearInterval(desktopDashboardTimer);
    desktopDashboardTimer = null;
  }
}

async function enterDashboardAccount(sessionId) {
  const account = (appState.accounts || []).find(item => String(item.sessionId) === String(sessionId));
  if (!account) {
    showToast("未找到要进入的账号", "error");
    return;
  }
  // 总控的“进入”固定联动主容器（容器1），不影响其他展示容器。
  const selections = loadContainerSelectedAccounts();
  selections["1"] = accountSelectionRef(account);
  saveContainerSelectedAccounts(selections);
  await selectAccount(sessionId);
  activeMainPage = "助手";
  activeCategory = "角色";
  activeSide = "任务";
  closeDesktopDashboard();
  render();
}

document.getElementById("openDesktopDashboardBtn")?.addEventListener("click", openDesktopDashboard);
document.getElementById("closeDesktopDashboardBtn")?.addEventListener("click", closeDesktopDashboard);
document.getElementById("refreshDesktopDashboardBtn")?.addEventListener("click", () => loadDesktopDashboard({ showLoading: true }));
document.getElementById("desktopDashboardMineCandidateCount")?.addEventListener("change", async event => {
  try {
    const data = await apiPost("/api/dashboard/mine-settings", {
      candidateTargetCount: Number(event.target.value || 3),
    });
    if (desktopDashboardData) desktopDashboardData.mineSettings = data.mineSettings;
    showToast(`打矿候选目标数已设为 ${data.mineSettings.candidateTargetCount}`, "success");
  } catch (error) {
    showToast(error.message || "保存打矿候选目标数失败", "error");
    loadDesktopDashboard();
  }
});
document.getElementById("desktopDashboardSearch")?.addEventListener("input", event => {
  desktopDashboardQuery = String(event.target.value || "");
  renderDesktopDashboard();
});
document.getElementById("desktopDashboardFilter")?.addEventListener("change", event => {
  desktopDashboardFilter = String(event.target.value || "all");
  renderDesktopDashboard();
});
document.getElementById("desktopDashboardLevelFilter")?.addEventListener("change", event => {
  desktopDashboardLevelFilter = String(event.target.value || "all");
  renderDesktopDashboard();
});
document.getElementById("desktopDashboardCountryFilter")?.addEventListener("change", event => {
  desktopDashboardCountryFilter = String(event.target.value || "all");
  renderDesktopDashboard();
});
document.getElementById("desktopDashboardBody")?.addEventListener("click", event => {
  const expandButton = event.target.closest?.("[data-dashboard-expand]");
  if (expandButton) {
    const key = String(expandButton.dataset.dashboardExpand || "");
    if (desktopDashboardExpanded.has(key)) desktopDashboardExpanded.delete(key);
    else desktopDashboardExpanded.add(key);
    renderDesktopDashboard();
    return;
  }
  const enterButton = event.target.closest?.("[data-dashboard-enter]");
  if (enterButton) enterDashboardAccount(String(enterButton.dataset.dashboardEnter || ""));
});

let desktopMapZoom = 1;
const DESKTOP_MAP_UNIT = 12;
const DESKTOP_MAP_PADDING = 90;
const DESKTOP_MAP_WIDTH = 186 * DESKTOP_MAP_UNIT + DESKTOP_MAP_PADDING * 2;
const DESKTOP_MAP_HEIGHT = 55 * DESKTOP_MAP_UNIT + DESKTOP_MAP_PADDING * 2;
function selectedDesktopMapDrops() {
  return Array.from(document.querySelectorAll(".desktop-map-drop-filter:checked")).map(input => input.value);
}
function selectedDesktopMapComposition() {
  const values = Array.from(document.querySelectorAll(".desktop-map-composition-digit"))
    .map(select => select.value);
  if (values.length !== 4 || values.some(value => value === "")) return null;
  return values.map(Number);
}
function desktopMapCompositionMatches(point, limits) {
  if (!limits) return true;
  const parsed = compositionFromCode(point.compositionCode);
  if (!parsed) return false;
  const actual = [parsed.maxFoot, parsed.maxBow, parsed.maxCavalry, parsed.maxChariot];
  return actual.every((count, index) => count <= limits[index]);
}
function initializeDesktopMapCompositionFilter() {
  document.querySelectorAll(".desktop-map-composition-digit").forEach(select => {
    if (select.options.length) return;
    select.innerHTML = `<option value="">不限</option>${compositionDigitOptions
      .map(value => `<option value="${value}">${value}</option>`).join("")}`;
  });
}
function applyDesktopMapZoom() {
  const canvas = document.getElementById("desktopBanditMapCanvas");
  const text = document.getElementById("desktopMapZoomText");
  if (canvas) {
    canvas.style.width = `${Math.round(DESKTOP_MAP_WIDTH * desktopMapZoom)}px`;
    canvas.style.height = `${Math.round(DESKTOP_MAP_HEIGHT * desktopMapZoom)}px`;
  }
  if (text) text.textContent = `${Math.round(desktopMapZoom * 100)}%`;
}
async function loadDesktopBanditMap() {
  const canvas = document.getElementById("desktopBanditMapCanvas");
  const empty = document.getElementById("desktopBanditMapEmpty");
  const popup = document.getElementById("desktopBanditMapPopup");
  const meta = document.getElementById("desktopBanditMapMeta");
  if (!canvas || !empty || !popup || !meta) return;
  popup.classList.add("page-hidden");
  meta.textContent = "正在读取最新地图...";
  try {
    const response = await fetch(`/api/maps/bandits?sessionId=${encodeURIComponent(appState.sessionId || "")}`, {
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "地图读取失败");
    const allPoints = Array.isArray(data.points) ? data.points : [];
    const selectedLevel = Number(document.getElementById("desktopMapLevelFilter")?.value || 0);
    const selectedDrops = selectedDesktopMapDrops();
    const selectedComposition = selectedDesktopMapComposition();
    const points = allPoints.filter(point => (
      (!selectedLevel || Number(point.level) === selectedLevel)
      && selectedDrops.some(category => (point.dropCategories || []).includes(category))
      && desktopMapCompositionMatches(point, selectedComposition)
    ));
    canvas.replaceChildren();
    empty.classList.toggle("page-hidden", points.length > 0);
    meta.textContent = `${data.serverKey || "当前区服"} · 显示 ${points.length}/${allPoints.length} 个最新山贼点位 · 点击点位查看详情`;
    if (!points.length) return;

    const width = DESKTOP_MAP_WIDTH;
    const height = DESKTOP_MAP_HEIGHT;
    const padding = DESKTOP_MAP_PADDING;
    const minX = 0, maxX = 186;
    const minY = 0, maxY = 55;
    const sx = x => padding + ((Number(x) - minX) / Math.max(1, maxX - minX)) * (width - padding * 2);
    const sy = y => padding + ((Number(y) - minY) / Math.max(1, maxY - minY)) * (height - padding * 2);
    canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
    applyDesktopMapZoom();

    const grid = svgElement("g");
    for (let index = 0; index <= 10; index += 1) {
      const px = padding + index * (width - padding * 2) / 10;
      const py = padding + index * (height - padding * 2) / 10;
      grid.appendChild(svgElement("line", { x1: px, y1: padding, x2: px, y2: height - padding, stroke: "#dbe3e7", "stroke-width": 2 }));
      grid.appendChild(svgElement("line", { x1: padding, y1: py, x2: width - padding, y2: py, stroke: "#dbe3e7", "stroke-width": 2 }));
      const xText = svgElement("text", { x: px, y: height - 42, "text-anchor": "middle", fill: "#506572", "font-size": 26 });
      xText.textContent = String(Math.round(minX + index * (maxX - minX) / 10));
      grid.appendChild(xText);
      const yText = svgElement("text", { x: 55, y: padding + index * (height - padding * 2) / 10 + 9, "text-anchor": "middle", fill: "#506572", "font-size": 26 });
      yText.textContent = String(Math.round(minY + index * (maxY - minY) / 10));
      grid.appendChild(yText);
    }
    grid.appendChild(svgElement("line", { x1: padding, y1: padding, x2: width - padding, y2: padding, stroke: "#344b5b", "stroke-width": 4 }));
    grid.appendChild(svgElement("line", { x1: padding, y1: padding, x2: padding, y2: height - padding, stroke: "#344b5b", "stroke-width": 4 }));
    canvas.appendChild(grid);
    appendLuoyangMarker(canvas, sx(91), sy(26));

    const colors = ["#82909a", "#5c9bd3", "#29a36a", "#d2a32f", "#d87932", "#d64d58"];
    points.forEach(point => {
      const circle = svgElement("circle", {
        cx: sx(point.x), cy: sy(point.y), r: point.selectedForAttack ? 13 : 9,
        fill: colors[Math.min(5, Math.max(0, Math.ceil(Number(point.level || 0) / 2)))],
        class: `bandit-map-point${point.selectedForAttack ? " is-selected" : ""}`,
      });
      circle.addEventListener("click", event => {
        event.stopPropagation();
        popup.innerHTML = `
          <b>${escHtml(point.level)}级山贼</b>
          <div>X 坐标：${escHtml(point.x)}</div>
          <div>Y 坐标：${escHtml(point.y)}</div>
          <div>阵容：${escHtml(point.compositionCode || "无法确认")}</div>
          <div>战利品：${escHtml((point.dropCategories || []).join("、") || point.rewardDescription || "无额外掉落")}</div>
          <div>奖励描述：${escHtml(point.rewardDescription || "无")}</div>
          <div>掉落ID：${escHtml((point.lootIds || []).join("、") || "无")}</div>
          <div>更新时间：${escHtml(formatBanditMapTime(point.updatedAt))}</div>
          <div>已被选中进攻：<span class="${point.selectedForAttack ? "attack-yes" : "attack-no"}">${point.selectedForAttack ? "是" : "否"}</span></div>`;
        popup.classList.remove("page-hidden");
      });
      canvas.appendChild(circle);
    });
    canvas.onclick = () => popup.classList.add("page-hidden");
  } catch (error) {
    canvas.replaceChildren();
    empty.textContent = error.message || "地图读取失败";
    empty.classList.remove("page-hidden");
    meta.textContent = "地图读取失败";
  }
}
const openDesktopBanditMapBtn = document.getElementById("openDesktopBanditMapBtn");
if (openDesktopBanditMapBtn) {
  openDesktopBanditMapBtn.onclick = () => {
    document.getElementById("desktopBanditMap")?.classList.remove("page-hidden");
    loadDesktopBanditMap();
  };
}
const closeDesktopBanditMapBtn = document.getElementById("closeDesktopBanditMapBtn");
if (closeDesktopBanditMapBtn) {
  closeDesktopBanditMapBtn.onclick = () => {
    document.getElementById("desktopBanditMap")?.classList.add("page-hidden");
  };
}
const refreshDesktopBanditMapBtn = document.getElementById("refreshDesktopBanditMapBtn");
if (refreshDesktopBanditMapBtn) refreshDesktopBanditMapBtn.onclick = loadDesktopBanditMap;
const desktopMapFilterBtn = document.getElementById("desktopMapFilterBtn");
if (desktopMapFilterBtn) {
  desktopMapFilterBtn.onclick = event => {
    event.stopPropagation();
    initializeDesktopMapCompositionFilter();
    document.getElementById("desktopMapFilterPanel")?.classList.toggle("page-hidden");
  };
}
const desktopMapApplyFilterBtn = document.getElementById("desktopMapApplyFilterBtn");
if (desktopMapApplyFilterBtn) {
  desktopMapApplyFilterBtn.onclick = () => {
    document.getElementById("desktopMapFilterPanel")?.classList.add("page-hidden");
    loadDesktopBanditMap();
  };
}
const desktopMapResetFilterBtn = document.getElementById("desktopMapResetFilterBtn");
if (desktopMapResetFilterBtn) {
  desktopMapResetFilterBtn.onclick = () => {
    const level = document.getElementById("desktopMapLevelFilter");
    if (level) level.value = "0";
    document.querySelectorAll(".desktop-map-drop-filter").forEach(input => { input.checked = true; });
    document.querySelectorAll(".desktop-map-composition-digit").forEach(select => { select.value = ""; });
    loadDesktopBanditMap();
  };
}
const desktopMapZoomOutBtn = document.getElementById("desktopMapZoomOutBtn");
if (desktopMapZoomOutBtn) {
  desktopMapZoomOutBtn.onclick = () => {
    desktopMapZoom = Math.max(.4, Math.round((desktopMapZoom - .2) * 10) / 10);
    applyDesktopMapZoom();
  };
}
const desktopMapZoomInBtn = document.getElementById("desktopMapZoomInBtn");
if (desktopMapZoomInBtn) {
  desktopMapZoomInBtn.onclick = () => {
    desktopMapZoom = Math.min(2.4, Math.round((desktopMapZoom + .2) * 10) / 10);
    applyDesktopMapZoom();
  };
}
document.addEventListener("click", event => {
  const panel = document.getElementById("desktopMapFilterPanel");
  if (!panel || panel.classList.contains("page-hidden")) return;
  if (!panel.contains(event.target) && event.target !== desktopMapFilterBtn) panel.classList.add("page-hidden");
});

let desktopMineMapZoom = 1;
const mineMapColors = {
  "镔铁矿": "#636f7a", "水晶矿": "#44a9c5", "玄铁矿": "#343b45",
  "浆果园": "#b94d65", "灵草园": "#3f9d5f", "玉露园": "#7c62c5",
  "银矿": "#9aa7b1", "一级牧场": "#c59448", "二级牧场": "#ad762f",
  "三级牧场": "#875522",
};
function applyDesktopMineMapZoom() {
  const canvas = document.getElementById("desktopMineMapCanvas");
  const text = document.getElementById("desktopMineMapZoomText");
  const height = 66 * DESKTOP_MAP_UNIT + DESKTOP_MAP_PADDING * 2;
  if (canvas) {
    canvas.style.width = `${Math.round(DESKTOP_MAP_WIDTH * desktopMineMapZoom)}px`;
    canvas.style.height = `${Math.round(height * desktopMineMapZoom)}px`;
  }
  if (text) text.textContent = `${Math.round(desktopMineMapZoom * 100)}%`;
}
function formatRemainingMineMapTime(ms) {
  const minutes = Math.max(0, Math.floor(Number(ms || 0) / 60000));
  if (minutes >= 60) return `${Math.floor(minutes / 60)}小时${minutes % 60}分`;
  return `${minutes}分钟`;
}
async function loadDesktopMineMap() {
  const canvas = document.getElementById("desktopMineMapCanvas");
  const empty = document.getElementById("desktopMineMapEmpty");
  const popup = document.getElementById("desktopMineMapPopup");
  const meta = document.getElementById("desktopMineMapMeta");
  if (!canvas || !empty || !popup || !meta) return;
  popup.classList.add("page-hidden");
  meta.textContent = "正在读取最新地图...";
  try {
    const response = await fetch(`/api/maps/mines?sessionId=${encodeURIComponent(appState.sessionId || "")}`, {
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "资源地图读取失败");
    const allPoints = Array.isArray(data.points) ? data.points : [];
    const kind = document.getElementById("desktopMineMapKindFilter")?.value || "";
    const owner = document.getElementById("desktopMineMapOwnerFilter")?.value || "";
    const points = allPoints.filter(point => (
      (!kind || point.kind === kind)
      && (!owner || (owner === "occupied" ? point.playerOccupied : !point.playerOccupied))
    ));
    canvas.replaceChildren();
    empty.classList.toggle("page-hidden", points.length > 0);
    meta.textContent = `${data.serverKey || "当前区服"} · 显示 ${points.length}/${allPoints.length} 个资源点 · 数据有效期3小时`;
    if (!points.length) return;

    const width = DESKTOP_MAP_WIDTH;
    const height = 66 * DESKTOP_MAP_UNIT + DESKTOP_MAP_PADDING * 2;
    const padding = DESKTOP_MAP_PADDING;
    const sx = x => padding + Number(x) / 186 * (width - padding * 2);
    const sy = y => padding + Number(y) / 66 * (height - padding * 2);
    canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
    canvas.style.width = `${Math.round(width * desktopMineMapZoom)}px`;
    canvas.style.height = `${Math.round(height * desktopMineMapZoom)}px`;
    document.getElementById("desktopMineMapZoomText").textContent = `${Math.round(desktopMineMapZoom * 100)}%`;

    const grid = svgElement("g");
    for (let index = 0; index <= 10; index += 1) {
      const px = padding + index * (width - padding * 2) / 10;
      const py = padding + index * (height - padding * 2) / 10;
      grid.appendChild(svgElement("line", { x1: px, y1: padding, x2: px, y2: height - padding, stroke: "#dbe3e7", "stroke-width": 2 }));
      grid.appendChild(svgElement("line", { x1: padding, y1: py, x2: width - padding, y2: py, stroke: "#dbe3e7", "stroke-width": 2 }));
      const xText = svgElement("text", { x: px, y: height - 42, "text-anchor": "middle", fill: "#506572", "font-size": 26 });
      xText.textContent = String(Math.round(index * 18.6));
      grid.appendChild(xText);
      const yText = svgElement("text", { x: 55, y: py + 9, "text-anchor": "middle", fill: "#506572", "font-size": 26 });
      yText.textContent = String(Math.round(index * 6.6));
      grid.appendChild(yText);
    }
    grid.appendChild(svgElement("line", { x1: padding, y1: padding, x2: width - padding, y2: padding, stroke: "#344b5b", "stroke-width": 4 }));
    grid.appendChild(svgElement("line", { x1: padding, y1: padding, x2: padding, y2: height - padding, stroke: "#344b5b", "stroke-width": 4 }));
    canvas.appendChild(grid);
    appendLuoyangMarker(canvas, sx(91), sy(26));

    points.forEach(point => {
      const circle = svgElement("circle", {
        cx: sx(point.x), cy: sy(point.y),
        r: point.selectedForAttack ? 13 : 9,
        fill: mineMapColors[point.kind] || "#5b8fa8",
        class: `bandit-map-point${point.selectedForAttack ? " is-selected" : ""}`,
      });
      circle.addEventListener("click", event => {
        event.stopPropagation();
        popup.innerHTML = `
          <b>${escHtml(point.name || point.kind)}</b>
          <div>业务编号：${escHtml(point.businessId ?? "-")}</div>
          <div>坐标：(${escHtml(point.x)}, ${escHtml(point.y)})</div>
          <div>玩家归属：${point.playerOccupied ? `${escHtml(point.ownerName || "未知玩家")}（${escHtml(point.ownerCountry || "未知国家")}）` : "无"}</div>
          <div>NPC守军：${escHtml(point.defenderCount || 0)}队</div>
          <div>数量A：${escHtml(point.amountA ?? "未知")}</div>
          <div>数量B：${escHtml(point.amountB ?? "未知")}</div>
          <div>说明：${escHtml(point.description || "无")}</div>
          <div>发现时间：${escHtml(formatBanditMapTime(point.updatedAt))}</div>
          <div>剩余有效期：${escHtml(formatRemainingMineMapTime(point.remainingMs))}</div>`;
        popup.classList.remove("page-hidden");
      });
      canvas.appendChild(circle);
    });
    canvas.onclick = () => popup.classList.add("page-hidden");
  } catch (error) {
    canvas.replaceChildren();
    empty.textContent = error.message || "资源地图读取失败";
    empty.classList.remove("page-hidden");
    meta.textContent = "资源地图读取失败";
  }
}
const openDesktopMineMapBtn = document.getElementById("openDesktopMineMapBtn");
if (openDesktopMineMapBtn) openDesktopMineMapBtn.onclick = () => {
  document.getElementById("desktopMineMap")?.classList.remove("page-hidden");
  loadDesktopMineMap();
};
const closeDesktopMineMapBtn = document.getElementById("closeDesktopMineMapBtn");
if (closeDesktopMineMapBtn) closeDesktopMineMapBtn.onclick = () => {
  document.getElementById("desktopMineMap")?.classList.add("page-hidden");
};
const refreshDesktopMineMapBtn = document.getElementById("refreshDesktopMineMapBtn");
if (refreshDesktopMineMapBtn) refreshDesktopMineMapBtn.onclick = loadDesktopMineMap;
const desktopMineMapFilterBtn = document.getElementById("desktopMineMapFilterBtn");
if (desktopMineMapFilterBtn) desktopMineMapFilterBtn.onclick = event => {
  event.stopPropagation();
  document.getElementById("desktopMineMapFilterPanel")?.classList.toggle("page-hidden");
};
document.getElementById("desktopMineMapApplyFilterBtn")?.addEventListener("click", () => {
  document.getElementById("desktopMineMapFilterPanel")?.classList.add("page-hidden");
  loadDesktopMineMap();
});
document.getElementById("desktopMineMapResetFilterBtn")?.addEventListener("click", () => {
  document.getElementById("desktopMineMapKindFilter").value = "";
  document.getElementById("desktopMineMapOwnerFilter").value = "";
  loadDesktopMineMap();
});
document.getElementById("desktopMineMapZoomOutBtn")?.addEventListener("click", () => {
  desktopMineMapZoom = Math.max(.4, Math.round((desktopMineMapZoom - .2) * 10) / 10);
  applyDesktopMineMapZoom();
});
document.getElementById("desktopMineMapZoomInBtn")?.addEventListener("click", () => {
  desktopMineMapZoom = Math.min(2.4, Math.round((desktopMineMapZoom + .2) * 10) / 10);
  applyDesktopMineMapZoom();
});
document.addEventListener("click", event => {
  const panel = document.getElementById("desktopMineMapFilterPanel");
  if (!panel || panel.classList.contains("page-hidden")) return;
  if (!panel.contains(event.target) && event.target !== desktopMineMapFilterBtn) panel.classList.add("page-hidden");
});
const refreshSystemLogBtn = document.getElementById("refreshSystemLogBtn");
if (refreshSystemLogBtn) refreshSystemLogBtn.onclick = refreshSystemLog;
const clearSystemLogBtn = document.getElementById("clearSystemLogBtn");
if (clearSystemLogBtn) {
  clearSystemLogBtn.onclick = async () => {
    try {
      clearSystemLogBtn.disabled = true;
      const data = await apiPost("/api/logs/system/clear", {});
      if (!data.cleared) throw new Error("后端未确认清除");
      appState.systemLogs = [];
      systemLogHasLoaded = true;
      systemLogCursorId = 0;
      systemLogSelectionStart = null;
      renderSystemLog();
      showToast("系统日志已清除", "success");
    } catch (error) {
      showToast("清除系统日志失败", "error");
    } finally {
      clearSystemLogBtn.disabled = false;
    }
  };
}
const addContainerBtn = document.getElementById("addContainerBtn");
if (addContainerBtn) addContainerBtn.onclick = addDisplayContainer;
document.getElementById("addAccountBtn").onclick = async () => {
  const modal = document.getElementById("accountModal");
  if (isStarterContainer) modal.dataset.mode = "starter";
  else delete modal.dataset.mode;
  const title = modal.querySelector("h2");
  if (title) title.textContent = isStarterContainer ? "添加起号账号" : "添加游戏账号";
  document.getElementById("loginPassword").value = "123459";
  await loadAreaCatalog();
  modal.classList.remove("hidden");
};
document.getElementById("modifyAccountBtn").onclick = async () => {
  const acc = selectedAccount();
  if (acc) {
    document.getElementById("loginUsername").value = acc.username || "";
    document.getElementById("loginPlatform").value = acc.platform || "热血三国联盟";
    document.getElementById("loginSerial").value = acc.serial ?? "0";
  }
  await loadAreaCatalog(acc?.areaName || acc?.serverQuery || appState.area?.areaName || "");
  document.getElementById("accountModal").classList.remove("hidden");
};
document.getElementById("startAccountBtn").onclick = startSelectedAccount;
document.getElementById("stopAccountBtn").onclick = stopSelectedAccount;
document.getElementById("deleteAccountBtn").onclick = deleteSelectedAccount;
document.getElementById("accountSelect").onchange = e => selectAccount(e.target.value);
const accountCustomSelect = document.getElementById("accountCustomSelect");
const accountCustomTrigger = document.getElementById("accountCustomTrigger");
if (accountCustomSelect && accountCustomTrigger) {
  accountCustomTrigger.onclick = event => {
    event.stopPropagation();
    if (accountCustomTrigger.disabled) return;
    const open = accountCustomSelect.classList.toggle("is-open");
    accountCustomTrigger.setAttribute("aria-expanded", open ? "true" : "false");
  };
  accountCustomSelect.addEventListener("click", event => {
    const option = event.target.closest?.("[data-account-option]");
    if (!option) return;
    event.stopPropagation();
    accountCustomSelect.classList.remove("is-open");
    accountCustomTrigger.setAttribute("aria-expanded", "false");
    selectAccount(String(option.dataset.accountOption || ""));
  });
}
document.addEventListener("click", event => {
  if (!accountCustomSelect || accountCustomSelect.contains(event.target)) return;
  accountCustomSelect.classList.remove("is-open");
  accountCustomTrigger?.setAttribute("aria-expanded", "false");
});
const proxySelect = document.getElementById("proxySelect");
if (proxySelect) {
  proxySelect.onfocus = () => {
    proxySelect.dataset.userInteracting = "1";
  };
  proxySelect.onblur = () => {
    delete proxySelect.dataset.userInteracting;
    // 展开期间积累的账号状态或节点变化在关闭后一次性同步。
    renderProxySelect();
  };
  proxySelect.onchange = e => selectProxy(e.target.value);
}
const proxyCustomSelect = document.getElementById("proxyCustomSelect");
const proxyCustomTrigger = document.getElementById("proxyCustomTrigger");
if (proxyCustomSelect && proxyCustomTrigger) {
  proxyCustomTrigger.onclick = event => {
    event.stopPropagation();
    if (proxyCustomTrigger.disabled) return;
    const open = proxyCustomSelect.classList.toggle("is-open");
    proxyCustomTrigger.setAttribute("aria-expanded", open ? "true" : "false");
  };
  proxyCustomSelect.addEventListener("click", event => {
    const option = event.target.closest?.("[data-proxy-option]");
    if (!option) return;
    event.stopPropagation();
    proxyCustomSelect.classList.remove("is-open");
    proxyCustomTrigger.setAttribute("aria-expanded", "false");
    selectProxy(String(option.dataset.proxyOption || ""));
  });
}
document.addEventListener("click", event => {
  if (!proxyCustomSelect || proxyCustomSelect.contains(event.target)) return;
  proxyCustomSelect.classList.remove("is-open");
  proxyCustomTrigger?.setAttribute("aria-expanded", "false");
});
const refreshProxyBtn = document.getElementById("refreshProxyBtn");
if (refreshProxyBtn) refreshProxyBtn.onclick = refreshProxyNodesAndCurrentIp;
document.getElementById("closeModal").onclick = () => {
  const modal = document.getElementById("accountModal");
  modal.classList.add("hidden");
  delete modal.dataset.mode;
  const title = modal.querySelector("h2");
  if (title) title.textContent = "添加游戏账号";
};
document.getElementById("accountModal").addEventListener("click", e => {
  if (e.target.id !== "accountModal") return;
  e.currentTarget.classList.add("hidden");
  delete e.currentTarget.dataset.mode;
  const title = e.currentTarget.querySelector("h2");
  if (title) title.textContent = "添加游戏账号";
});
document.getElementById("loginPlatform")?.addEventListener("change", event => {
  loadAreaCatalog("", event.target.value);
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    document.querySelectorAll(".formation-general-multi.open").forEach(x => x.classList.remove("open"));
    document.querySelectorAll(".policy-multi.open").forEach(x => x.classList.remove("open"));
    document.querySelectorAll(".brush-level-multi.open").forEach(x => x.classList.remove("open"));
    document.querySelectorAll(".general-visit-multi.open").forEach(x => x.classList.remove("open"));
  }
  if (e.key === "Escape" && pickerOpen) {
    pickerOpen = false;
    renderPickerLayer();
  }
});
document.addEventListener("click", e => {
  const target = e.target;
  if (!target?.closest?.(".formation-general-multi")) {
    document.querySelectorAll(".formation-general-multi.open").forEach(x => x.classList.remove("open"));
  }
  if (!target?.closest?.(".policy-multi")) {
    document.querySelectorAll(".policy-multi.open").forEach(x => x.classList.remove("open"));
  }
  if (!target?.closest?.(".brush-level-multi")) {
    document.querySelectorAll(".brush-level-multi.open").forEach(x => x.classList.remove("open"));
  }
  if (!target?.closest?.(".general-visit-multi")) {
    document.querySelectorAll(".general-visit-multi.open").forEach(x => x.classList.remove("open"));
  }
});
document.addEventListener("click", e => {
  if (!pickerOpen) return;
  const layer = document.getElementById("pickerLayer");
  if (!layer) return;
  if (layer.contains(e.target) || e.target.classList?.contains("open-picker")) return;
  pickerOpen = false;
  renderPickerLayer();
}, true);
document.getElementById("loginSubmit").onclick = async () => {
  try {
    const accountModal = document.getElementById("accountModal");
    const addingStarterAccount = accountModal?.dataset.mode === "starter";
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    const platform = document.getElementById("loginPlatform")?.value?.trim() || "";
    const serverQuery = document.getElementById("loginServer").value.trim()
      || defaultLoginServerQuery(platform);
    const serial = document.getElementById("loginSerial")?.value?.trim() || "0";
    appendLog(`正在本地添加账号记录 ${username} / ${serverQuery} ...`);
    const data = await apiPost("/api/accounts/add", { username, password, serverQuery, platform, serial });
    await syncAccounts();
    await loadProxyNodes();
    notifyAccountsChanged("add");
    const acc = data.account || (appState.accounts || []).find(a => a.username === username && a.areaName === serverQuery);
    if (acc) {
      applyAccountRecord(acc, { restoreUi: true });
      saveCurrentContainerSelection(acc);
      if (addingStarterAccount) {
        await apiPost("/api/starter/jobs/create", {
          accountId: acc.sessionId,
          targetLevel: 66,
        });
        await loadDashboardStarterMode();
      }
    }
    updateAccountHeader();
    appendLog(`添加账号成功：${accountLabel(acc)}；当前状态=未开启。注意：添加只保存本地记录，不会登录游戏；请在上方下拉框选中该账号后点击“启动”。`);
    showToast(addingStarterAccount ? "起号账号添加成功" : "添加账号成功", "success");
    accountModal?.classList.add("hidden");
    if (accountModal) delete accountModal.dataset.mode;
    activeCategory = "刷黄"; activeSide = "刷黄";
    render();
  } catch (e) {
    appendLog("添加账号失败：" + e.message);
    showToast("添加账号失败", "error");
  }
};

const starterContainerTabs = new Map();
let dashboardStarterJobs = [];
let dashboardStarterViews = new Map();
const STARTER_CONTAINER_COUNT_KEY = "dwsg_starter_container_count_v1";
let dashboardStarterContainerCount = Math.max(1, Number(localStorage.getItem(STARTER_CONTAINER_COUNT_KEY) || 1));
const starterStatusText = status => ({
  queued: "等待执行", running: "执行中", paused: "已暂停",
  waiting: "等待协议接入", stopped: "已停止", completed: "已完成",
})[String(status || "")] || String(status || "未知");
const starterTabNames = {
  basic: "基本信息", tasks: "任务奖励", activities: "活动奖励",
  treasury: "宝库", role: "角色详情", military: "将领和军队", records: "记录",
};

function renderDashboardStarterAccountOptions() {
  const select = document.getElementById("dashboardStarterAccountSelect");
  if (!select) return;
  const used = new Set((dashboardStarterJobs || []).map(job => String(job.account_id || "")));
  const available = (appState.accounts || []).filter(account => !used.has(String(account.sessionId)));
  select.innerHTML = `<option value="">选择账号加入起号模式</option>${available.map(account =>
    `<option value="${escAttr(account.sessionId)}">${escHtml(accountLabel(account))}</option>`
  ).join("")}`;
}

function starterPairsHtml(values) {
  return `<div class="starter-info-grid">${Object.entries(values || {}).map(([key, value]) =>
    `<div><b>${escHtml(key)}</b><span>${escHtml(value ?? "-")}</span></div>`
  ).join("")}</div>`;
}

function starterTaskListHtml(items, emptyText) {
  if (!Array.isArray(items) || !items.length) return `<div class="starter-tab-empty">${escHtml(emptyText)}</div>`;
  return `<div class="starter-data-list">${items.map(item => `<div>
    <b>${escHtml(item.title || item.name || item.label || item.key || "任务")}</b>
    <span>${escHtml(item.message || item.statusText || item.summary || (item.completed ? "已完成" : "进行中"))}</span>
  </div>`).join("")}</div>`;
}

function starterTabContent(view, tab) {
  const basic = view.basic || {};
  const recruiting = view.development?.recruitmentStates?.[0] || null;
  const recruitingText = recruiting
    ? `${recruiting.soldierType || "士兵"}×${fmtNum(recruiting.count || 0)} · ${
        recruiting.remainingSec > 0
          ? `剩余约${Math.ceil(Number(recruiting.remainingSec || 0) / 60)}分钟`
          : "等待完成复查"
      }`
    : "当前无征兵队列";
  const pendingTransfer = view.development?.pendingTransferChecks?.[0] || null;
  const transferText = pendingTransfer
    ? `等待转兵确认 · ${fmtNum(pendingTransfer.observedOwnedTotal || 0)}/${
        fmtNum(pendingTransfer.expectedMinimumTotal || 0)
      }弩车`
    : "无待确认转兵";
  if (tab === "basic") return starterPairsHtml({
    "账号": view.account?.username, "平台": view.account?.platform,
    "区服": view.account?.areaName, "状态": view.account?.statusText,
    "角色": basic.roleName, "等级": basic.level, "国家": basic.country,
    "铜钱": fmtNum(basic.copper), "粮食": fmtNum(basic.food),
    "人口": `${fmtNum(basic.populationCurrent)}/${fmtNum(basic.populationCap)}`,
    "声望": fmtNum(basic.prestige),
    "起号征兵": recruitingText,
    "弃地转兵": transferText,
  });
  if (tab === "tasks") return starterTaskListHtml([
    ...(view.taskRewards?.taskStack || []), ...(view.taskRewards?.resident || []),
  ], "暂无任务奖励数据");
  if (tab === "activities") return starterTaskListHtml([
    ...(view.activityRewards?.daily || []), ...(view.activityRewards?.notices || []),
  ], "暂无活动奖励数据");
  if (tab === "treasury") {
    const items = view.treasury?.items || [];
    return items.length ? `<div class="starter-treasury-grid">${items.map(item => `<div>
      <b>${escHtml(item.name || item.itemName || `物品${item.id || ""}`)}</b>
      <span>×${fmtNum(item.count ?? item.amount ?? 0)}</span>
    </div>`).join("")}</div>` : `<div class="starter-tab-empty">暂无宝库物品数据</div>`;
  }
  if (tab === "role") {
    const state = view.roleDetail?.state || {};
    const role = view.roleDetail?.role || {};
    return starterPairsHtml({
      "角色ID": role.roleId, "角色名": role.roleName || role.name,
      "等级": state.level || role.level, "铜钱": fmtNum(state.copper),
      "粮食": fmtNum(state.food), "声望": fmtNum(state.prestige),
      "资源点": `${fmtNum(state.resourcePointCurrent)}/${fmtNum(state.resourcePointCap)}`,
      "人口": `${fmtNum(state.populationCurrent)}/${fmtNum(state.populationCap)}`,
    });
  }
  if (tab === "military") {
    const generals = view.military?.generals || [];
    const army = view.military?.army || [];
    return `<div class="starter-military-columns"><section><h4>将领（${generals.length}）</h4>${generals.length ? generals.map(g => `<div class="starter-military-row"><b>${escHtml(g.name || g.generalName || `将领${g.id || ""}`)}</b><span>Lv.${fmtNum(g.level)} · ${escHtml(g.statusText || g.roleStateStatusText || "-")} · 统兵${fmtNum(g.command || g.commandLimit || g.soldierLimit || 0)}</span></div>`).join("") : `<div class="starter-tab-empty">暂无将领数据</div>`}</section><section><h4>军队</h4>${army.length ? army.map(a => `<div class="starter-military-row"><b>${escHtml(a.name || a.soldierName || a.typeName || `兵种${a.id || ""}`)}</b><span>${fmtNum(a.count ?? a.amount ?? a.idle ?? 0)}</span></div>`).join("") : `<div class="starter-tab-empty">暂无军队数据</div>`}</section></div>`;
  }
  const records = view.records || [];
  return records.length ? `<div class="starter-record-list">${records.map(record => `<div><time>${escHtml(record.timeText || "")}</time><span>${escHtml(record.message || "")}</span></div>`).join("")}</div>` : `<div class="starter-tab-empty">暂无动作记录</div>`;
}

function renderDashboardStarterContainers() {
  const root = document.getElementById("dashboardStarterContainers");
  if (!root) return;
  renderDashboardStarterAccountOptions();
  dashboardStarterContainerCount = Math.max(1, dashboardStarterContainerCount, dashboardStarterJobs.length);
  localStorage.setItem(STARTER_CONTAINER_COUNT_KEY, String(dashboardStarterContainerCount));
  root.innerHTML = Array.from({ length: dashboardStarterContainerCount }, (_, jobIndex) => {
    const job = dashboardStarterJobs[jobIndex] || null;
    if (!job) {
      const iframeQuery = new URLSearchParams({
        embedded: "1", starter: "1", containerId: `starter_empty_${jobIndex + 1}`,
      });
      return `<section class="container-panel starter-phone-container" data-starter-slot="${jobIndex}">
        <div class="container-titlebar starter-mode-titlebar">
          <div class="starter-mode-identity"><span>起号容器 ${jobIndex + 1}</span><b class="starter-mode-badge">起号模式</b></div>
          <div class="starter-mode-state"><strong>未绑定账号</strong><small>可在容器内选择账号</small></div>
          ${jobIndex > 0 ? `<div class="container-title-actions"><button class="container-delete-btn" type="button" data-starter-container-remove="${jobIndex}">删除</button></div>` : ""}
        </div>
        <div class="container-phone-wrap"><iframe class="container-iframe" src="./index.html?${escAttr(iframeQuery.toString())}" title="起号容器 ${jobIndex + 1}"></iframe></div>
      </section>`;
    }
    const accountId = String(job.account_id || "");
    const view = dashboardStarterViews.get(accountId) || {};
    const account = view.account || {};
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    const containerId = `starter_${accountId || jobIndex + 1}`;
    const iframeQuery = new URLSearchParams({
      embedded: "1",
      starter: "1",
      containerId,
      starterAccountId: accountId,
      starterUsername: String(account.username || job.username || ""),
      starterAreaName: String(account.areaName || job.target_server || ""),
    });
    const status = String(job.status || "");
    const controlButtons = `
      ${["paused", "waiting", "queued"].includes(status) ? `<button type="button" data-starter-action="resume">运行</button>` : ""}
      ${["running", "queued"].includes(status) ? `<button type="button" data-starter-action="pause">暂停</button>` : ""}
      ${!["stopped", "completed"].includes(status) ? `<button type="button" class="danger" data-starter-action="stop">停止</button>` : ""}
    `;
    return `<section class="container-panel starter-phone-container" data-starter-account="${escAttr(accountId)}" data-starter-job="${escAttr(job.job_id)}">
      <div class="container-titlebar starter-mode-titlebar">
        <div class="starter-mode-identity">
          <span>起号容器 ${jobIndex + 1}</span>
          <b class="starter-mode-badge">起号模式</b>
        </div>
        <div class="starter-mode-state">
          <strong>${escHtml(starterStatusText(job.status))} · ${progress}%</strong>
          <small title="${escAttr(job.current_step || "")}">${escHtml(job.current_step || "等待执行")}</small>
        </div>
        <div class="container-title-actions starter-mode-controls">${controlButtons}
          ${jobIndex > 0 ? `<button class="container-delete-btn" type="button"
            data-starter-container-remove="${jobIndex}" data-starter-job-id="${escAttr(job.job_id)}">删除</button>` : ""}
        </div>
      </div>
      <div class="container-phone-wrap">
        <iframe class="container-iframe" src="./index.html?${escAttr(iframeQuery.toString())}" title="起号容器 ${jobIndex + 1}"></iframe>
      </div>
    </section>`;
  }).join("");
}

async function loadDashboardStarterMode({ silent = false } = {}) {
  try {
    const response = await fetch("/api/starter/jobs", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "读取起号任务失败");
    dashboardStarterJobs = data.jobs || [];
    dashboardStarterContainerCount = Math.max(
      1, Number(data.containerCount || 1), dashboardStarterJobs.length,
    );
    localStorage.setItem(STARTER_CONTAINER_COUNT_KEY, String(dashboardStarterContainerCount));
    const views = await Promise.all(dashboardStarterJobs.map(async job => {
      const accountId = String(job.account_id || "");
      const viewResponse = await fetch(`/api/starter/account-view?accountId=${encodeURIComponent(accountId)}`, { cache: "no-store" });
      const viewData = await viewResponse.json();
      return [accountId, viewData.view || {}];
    }));
    dashboardStarterViews = new Map(views);
    renderDashboardStarterContainers();
  } catch (error) {
    if (!silent) showToast(error.message || "读取起号模式失败", "error");
  }
}

document.getElementById("dashboardCreateStarterBtn")?.addEventListener("click", async () => {
  const modal = document.getElementById("accountModal");
  if (!modal) return;
  modal.dataset.mode = "starter";
  const title = modal.querySelector("h2");
  if (title) title.textContent = "添加起号账号";
  document.getElementById("loginUsername").value = "";
  document.getElementById("loginPassword").value = "";
  document.getElementById("loginSerial").value = "0";
  await loadAreaCatalog("", document.getElementById("loginPlatform")?.value || "");
  modal.classList.remove("hidden");
});
document.getElementById("dashboardRefreshStarterBtn")?.addEventListener("click", () => loadDashboardStarterMode());
document.getElementById("dashboardAddStarterContainerBtn")?.addEventListener("click", () => {
  dashboardStarterContainerCount += 1;
  localStorage.setItem(STARTER_CONTAINER_COUNT_KEY, String(dashboardStarterContainerCount));
  apiPost("/api/starter/layout", { containerCount: dashboardStarterContainerCount })
    .catch(error => showToast(error.message || "保存容器布局失败", "error"));
  renderDashboardStarterContainers();
});
document.getElementById("dashboardStarterContainers")?.addEventListener("click", async event => {
  const remove = event.target.closest?.("[data-starter-container-remove]");
  if (remove) {
    const jobId = String(remove.dataset.starterJobId || "");
    if (jobId) {
      try {
        await apiPost("/api/starter/jobs/delete", { jobId });
        await loadDashboardStarterMode();
      } catch (error) {
        showToast(error.message || "删除起号容器失败", "error");
      }
      return;
    }
    dashboardStarterContainerCount = Math.max(
      1, dashboardStarterJobs.length, dashboardStarterContainerCount - 1,
    );
    localStorage.setItem(STARTER_CONTAINER_COUNT_KEY, String(dashboardStarterContainerCount));
    apiPost("/api/starter/layout", { containerCount: dashboardStarterContainerCount })
      .catch(error => showToast(error.message || "保存容器布局失败", "error"));
    renderDashboardStarterContainers();
    return;
  }
  const container = event.target.closest?.("[data-starter-account]");
  if (!container) return;
  const accountId = String(container.dataset.starterAccount || "");
  const tab = event.target.closest?.("[data-starter-tab]");
  if (tab) {
    starterContainerTabs.set(accountId, String(tab.dataset.starterTab || "basic"));
    renderDashboardStarterContainers();
    return;
  }
  const action = event.target.closest?.("[data-starter-action]");
  if (action) {
    try {
      await apiPost("/api/starter/jobs/control", { jobId: container.dataset.starterJob, action: action.dataset.starterAction });
      await loadDashboardStarterMode();
    } catch (error) { showToast(error.message || "操作失败", "error"); }
  }
});

initAccountEventBridge();
restoreDisplayContainers();
startAccountsPolling();
startSystemLogPolling();
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  syncAccounts({ silent: true, summary: true });
  refreshSystemLog();
  if (activeCategory === "角色" && (activeSide === "任务" || activeSide === "提示")) {
    refreshTaskOverview({ silent: true });
  }
});
syncAccounts()
  .then(() => Promise.all([loadProxyNodes(), loadAreaCatalog()]))
  .finally(() => render());
