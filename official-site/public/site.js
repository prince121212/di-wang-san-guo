(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const day = ms => new Date(ms).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  const size = bytes => (bytes / 1048576).toFixed(1) + " MB";

  // WeChat / QQ in-app browsers silently swallow APK downloads. The standalone QQ Browser has no
  // " QQ/" token; the X5 "MQQBrowser" token also appears inside WeChat, so it cannot be excluded.
  const ua = navigator.userAgent;
  if (/MicroMessenger/i.test(ua) || /\sQQ\//.test(ua)) {
    $("inAppTip").hidden = false;
    $("downloadButton").addEventListener("click", event => {
      event.preventDefault();
      window.alert($("inAppTip").textContent);
    });
  }

  // navigator.clipboard is missing in some in-app browsers; fall back to a selected textarea.
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* fall back */ }
    const buffer = document.createElement("textarea");
    buffer.className = "copy-buffer";
    buffer.value = text;
    buffer.setAttribute("readonly", "");
    document.body.append(buffer);
    buffer.select();
    try { return document.execCommand("copy"); } catch { return false; } finally { buffer.remove(); }
  }
  $("groupCopy").addEventListener("click", async () => {
    const number = $("groupCopy").dataset.number;
    $("groupFeedback").textContent = await copy(number)
      ? `已复制群号 ${number}，打开 QQ 搜索群号即可申请加入。`
      : `复制失败，请长按群号 ${number} 手动复制。`;
  });

  async function load(path) {
    const response = await fetch(path, { cache: "no-cache" });
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  load("/app/latest.json").then(latest => {
    $("releaseMeta").textContent = `最新版 ${latest.versionName} · ${size(latest.sizeBytes)} · ${day(latest.publishedAt)} 发布`;
    $("downloadButton").textContent = `下载安卓版 ${latest.versionName}`;
    $("apkDigest").textContent = `${latest.versionName} 安装包 SHA-256：${latest.sha256}`;
    $("apkDigest").hidden = false;
  }).catch(() => { $("releaseMeta").textContent = "新版本即将发布，请稍后再来"; });

  load("/app/releases.json").then(history => {
    const list = $("changelog");
    list.replaceChildren();
    for (const release of (history.releases || []).slice(0, 10)) {
      const item = document.createElement("article");
      item.className = "release";
      const header = document.createElement("header");
      const name = document.createElement("span");
      name.textContent = release.versionName;
      const date = document.createElement("time");
      date.textContent = day(release.publishedAt);
      header.append(name, date);
      const notes = document.createElement("ul");
      for (const note of release.notes || []) {
        const line = document.createElement("li");
        line.textContent = note;
        notes.append(line);
      }
      item.append(header, notes);
      list.append(item);
    }
    if (!list.children.length) throw new Error("empty");
  }).catch(() => {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "暂无更新记录。";
    $("changelog").replaceChildren(empty);
  });
})();
