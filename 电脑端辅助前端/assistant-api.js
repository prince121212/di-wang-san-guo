(() => {
  "use strict";

  const nativeBridge = window.DWPMNativeApi;
  if (!nativeBridge || typeof nativeBridge.postMessage !== "function") return;

  const pending = new Map();
  let sequence = 0;
  const OPERATION_STATUS_PATH = "/api/core/operations/status";
  const OPERATION_POLL_MILLIS = 250;
  const TERMINAL_OPERATION_STATES = new Set([
    "SUCCEEDED", "FAILED", "CANCELLED", "UNCERTAIN",
  ]);

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

  function delay(millis) {
    return new Promise(resolve => setTimeout(resolve, millis));
  }

  function operationFailure(operation) {
    const state = String(operation?.status || "FAILED");
    const error = operation?.error && typeof operation.error === "object"
      ? operation.error
      : {};
    const message = String(
      error.message
      || (state === "UNCERTAIN"
        ? "游戏服务器回执不明确，请刷新状态确认后再操作"
        : state === "CANCELLED"
          ? "操作已取消"
          : "网络操作失败")
    );
    return {
      status: state === "UNCERTAIN" ? 409 : (state === "CANCELLED" ? 409 : 500),
      body: {
        ok: false,
        error: message,
        code: String(error.code || state),
        operationId: String(operation?.operationId || ""),
        operationStatus: state,
      },
    };
  }

  async function waitForOperation(operationId) {
    const encodedId = encodeURIComponent(String(operationId || ""));
    if (!encodedId) {
      return { status: 500, body: { ok: false, error: "核心未返回 operationId" } };
    }
    while (true) {
      const response = await nativeRequest(
        "GET",
        `${OPERATION_STATUS_PATH}?operationId=${encodedId}`,
        null,
      );
      const status = Number(response?.status || 500);
      const operation = response?.body?.operation;
      if (status < 200 || status >= 300 || !operation) {
        return {
          status,
          body: response?.body && typeof response.body === "object"
            ? response.body
            : { ok: false, error: "无法读取网络操作状态" },
        };
      }
      const state = String(operation.status || "");
      if (state === "SUCCEEDED") {
        const result = operation.result && typeof operation.result === "object"
          ? operation.result
          : {};
        return { status: 200, body: { ok: true, ...result } };
      }
      if (TERMINAL_OPERATION_STATES.has(state)) {
        return operationFailure(operation);
      }
      await delay(OPERATION_POLL_MILLIS);
    }
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
    let response = await nativeRequest(method, `${url.pathname}${url.search}`, body);
    let status = Number(response.status || 500);
    let payload = response.body && typeof response.body === "object"
      ? response.body
      : { ok: false, error: "手机本地核心返回无效响应" };
    if (status === 202 && payload.operationId) {
      // The caller's old 30-second AbortController only governed synchronous backends.
      // Once the durable operation is accepted, wait for the real game-server result and
      // keep all later bridge calls short/local. Page reconstruction can recover the same
      // operation from its persisted ID.
      const completed = await waitForOperation(payload.operationId);
      status = completed.status;
      payload = completed.body;
    }
    return new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  };
})();
