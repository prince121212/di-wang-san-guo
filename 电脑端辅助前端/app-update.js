(() => {
  "use strict";
  // Phone app only: the official site distributes the Android package.
  if (!window.DWPMNativeApi) return;
  const mount = document.getElementById("memberUpdateSlot");
  if (!mount) return;
  const AUTO_CHECK_MILLIS = 12 * 60 * 60_000, LAST_CHECK_KEY = "app-update:auto-checked-at";
  const card = document.createElement("section");
  card.id = "appUpdatePanel";
  card.className = "member-card";
  card.innerHTML = `<div class="member-section-heading"><h3>版本与更新</h3><span id="appUpdateBadge" hidden>有新版本</span></div>
    <p id="appUpdateCurrent" class="member-copy">当前版本：读取中…</p>
    <div id="appUpdateLatest" hidden><p id="appUpdateSummary" class="member-copy"></p><ul id="appUpdateNotes"></ul>
      <button type="button" class="member-primary" id="appUpdateDownload">下载新版本</button></div>
    <button type="button" id="appUpdateCheck">检查更新</button>
    <p id="appUpdateFeedback" class="member-copy" role="status" hidden></p>`;
  mount.append(card);
  const $ = id => document.getElementById(id);
  let busy = false;
  const day = ms => new Date(ms).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  function feedback(message) { $("appUpdateFeedback").textContent = message; $("appUpdateFeedback").hidden = !message; }
  async function call(path, body) {
    const r = await fetch("/api/app/" + path, { method: body === undefined ? "GET" : "POST",
      headers: { "content-type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const data = await r.json();
    if (!r.ok || data.ok === false) throw new Error(data.error || data.message || "暂时无法检查更新");
    return data;
  }
  function render(state) {
    $("appUpdateCurrent").textContent = `当前版本：${state.currentVersionName}` +
      (state.supported ? "" : "（测试或内部版本，不通过官网更新）");
    $("appUpdateCheck").hidden = !state.supported;
    const latest = state.updateAvailable ? state.latest : null;
    $("appUpdateLatest").hidden = !latest;
    $("appUpdateBadge").hidden = !latest;
    document.querySelector('.bottom-item[data-page="Home"]')?.classList.toggle("has-update", Boolean(latest));
    if (!latest) return;
    $("appUpdateSummary").textContent =
      `发现新版本 ${latest.versionName}（${(latest.sizeBytes / 1048576).toFixed(1)} MB，${day(latest.publishedAt)} 发布）`;
    const notes = $("appUpdateNotes");
    notes.replaceChildren();
    for (const note of latest.notes || []) {
      const item = document.createElement("li");
      item.textContent = note;
      notes.append(item);
    }
  }
  $("appUpdateCheck").onclick = async () => {
    if (busy) return;
    busy = true; $("appUpdateCheck").disabled = true; feedback("正在连接官网…");
    try {
      const state = await call("update?check=1&force=1");
      render(state);
      feedback(state.message || "");
    } catch (e) { feedback(e.message); } finally { busy = false; $("appUpdateCheck").disabled = false; }
  };
  $("appUpdateDownload").onclick = async () => {
    if (busy) return;
    busy = true;
    try {
      await call("update-open", {});
      feedback("已在浏览器打开下载。下载完成后点开安装包覆盖安装即可，游戏账号和设置都会保留。");
    } catch (e) { feedback(e.message); } finally { busy = false; }
  };
  // Show the version right away; ask the official site at most twice a day, silently.
  call("update").then(state => {
    render(state);
    const last = Number(localStorage.getItem(LAST_CHECK_KEY) || 0);
    if (!state.supported || Date.now() - last < AUTO_CHECK_MILLIS) return;
    return call("update?check=1").then(checked => {
      localStorage.setItem(LAST_CHECK_KEY, String(Date.now()));
      render(checked);
    });
  }).catch(() => { /* A failed silent check never disturbs Home; the button reports errors. */ });
})();
