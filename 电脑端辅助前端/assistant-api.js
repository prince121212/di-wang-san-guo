(() => {
  "use strict";

  const nativeBridge = window.DWPMNativeApi;
  if (!nativeBridge || typeof nativeBridge.postMessage !== "function") return;

  const pending = new Map();
  let sequence = 0;

  function nextRequestId() {
    sequence = (sequence + 1) % Number.MAX_SAFE_INTEGER;
    return `android-${Date.now()}-${sequence}`;
  }

  function nativeRequest(method, path, body) {
    const id = nextRequestId();
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        pending.delete(id);
        reject(new Error("手机本地核心响应超时"));
      }, 30000);
      pending.set(id, { resolve, reject, timeout });
      try {
        nativeBridge.postMessage(JSON.stringify({
          apiVersion: "v1",
          id,
          method,
          path,
          body: body ?? null,
        }));
      } catch (error) {
        clearTimeout(timeout);
        pending.delete(id);
        reject(error);
      }
    });
  }

  window.AssistantApi = Object.freeze({
    request: nativeRequest,
    __resolve(rawResponse) {
      let response;
      try {
        response = typeof rawResponse === "string" ? JSON.parse(rawResponse) : rawResponse;
      } catch (_) {
        return;
      }
      const waiter = pending.get(String(response?.id || ""));
      if (!waiter) return;
      clearTimeout(waiter.timeout);
      pending.delete(String(response.id));
      waiter.resolve(response);
    },
  });

  const networkFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const rawUrl = typeof input === "string" ? input : input?.url;
    const url = new URL(rawUrl, window.location.href);
    if (!url.pathname.startsWith("/api/")) return networkFetch(input, init);

    const method = String(init.method || "GET").toUpperCase();
    let body = null;
    if (typeof init.body === "string" && init.body.length) {
      try { body = JSON.parse(init.body); } catch (_) { body = init.body; }
    }
    const response = await nativeRequest(method, `${url.pathname}${url.search}`, body);
    const status = Number(response.status || 500);
    const payload = response.body && typeof response.body === "object"
      ? response.body
      : { ok: false, error: "手机本地核心返回无效响应" };
    return new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  };
})();
