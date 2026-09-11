(() => {
  "use strict";

  const nativeBridge = window.DWPMNativeApi;
  const hasNativeBridge = !!nativeBridge && typeof nativeBridge.postMessage === "function";
  const networkFetch = window.fetch.bind(window);

  const pending = new Map();
  const operationWaiters = new Map();
  const operationReads = new Map();
  const operationReconcileTimers = new Map();
  const operationEventIds = new Map();
  let sequence = 0;
  const OPERATION_STATUS_PATH = "/api/core/operations/status";
  const OPERATION_CANCEL_PATH = "/api/core/operations/cancel";
  const TRACKED_OPERATIONS_KEY = "dwpm.android.tracked-operations.v1";
  // Android receives native progress events, so polling is only a watchdog there.
  // Desktop HTTP has no event bridge and therefore reconciles its local operation
  // ledger promptly while still avoiding a busy loop.
  const OPERATION_RECONCILE_MILLIS = hasNativeBridge ? 15000 : 750;
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

  async function networkRequest(method, path, body) {
    const normalizedMethod = String(method || "GET").toUpperCase();
    const init = {
      method: normalizedMethod,
      headers: { "Accept": "application/json" },
      cache: "no-store",
    };
    if (normalizedMethod !== "GET" && normalizedMethod !== "HEAD" && body !== null) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body ?? {});
    }
    const response = await networkFetch(path, init);
    const text = await response.text();
    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch (_) {
      payload = {
        ok: false,
        error: `核心状态接口返回非 JSON：HTTP ${response.status} ${text.slice(0, 120)}`,
      };
    }
    return {
      status: Number(response.status || 500),
      body: payload && typeof payload === "object"
        ? payload
        : { ok: false, error: "核心状态接口返回无效响应" },
    };
  }

  function coreRequest(method, path, body) {
    return hasNativeBridge
      ? nativeRequest(method, path, body)
      : networkRequest(method, path, body);
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

  function trackedOperations() {
    try {
      const value = JSON.parse(localStorage.getItem(TRACKED_OPERATIONS_KEY) || "{}");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch (_) {
      return {};
    }
  }

  function saveTrackedOperations(value) {
    try { localStorage.setItem(TRACKED_OPERATIONS_KEY, JSON.stringify(value || {})); } catch (_) {}
  }

  function trackOperation(operationId, metadata = {}) {
    const id = String(operationId || "");
    if (!id) return;
    const tracked = trackedOperations();
    const existing = tracked[id] && typeof tracked[id] === "object" ? tracked[id] : {};
    tracked[id] = {
      ...existing,
      ...metadata,
      operationId: id,
      acceptedAt: Number(existing.acceptedAt || Date.now()),
    };
    saveTrackedOperations(tracked);
  }

  function isTrackedOperation(operationId) {
    const id = String(operationId || "");
    return !!id && Object.prototype.hasOwnProperty.call(trackedOperations(), id);
  }

  function untrackOperation(operationId) {
    const id = String(operationId || "");
    if (!id) return;
    const tracked = trackedOperations();
    if (!(id in tracked)) return;
    delete tracked[id];
    saveTrackedOperations(tracked);
  }

  function operationResponse(operation) {
    const state = String(operation?.status || "");
    if (state === "SUCCEEDED") {
      const result = operation.result && typeof operation.result === "object"
        ? operation.result
        : {};
      // Python-owned workflows intentionally persist an envelope such as
      // {ok:true, result:{success:true,...}}. Preserve that envelope for
      // diagnostics while also exposing the route result at the same level as
      // a synchronous response, so old callers keep reading data.success etc.
      const routeResult = result.result && typeof result.result === "object"
        ? result.result
        : {};
      return { status: 200, body: { ok: true, ...result, ...routeResult } };
    }
    return TERMINAL_OPERATION_STATES.has(state) ? operationFailure(operation) : null;
  }

  function emitOperationState(operation, source) {
    const id = String(operation?.operationId || "");
    const metadata = trackedOperations()[id] || {};
    window.dispatchEvent(new CustomEvent("assistant-operation-state", {
      detail: { operation, metadata, source: String(source || "native-event") },
    }));
  }

  function emitOperationReadIssue(operationId, failure, source, recoverable) {
    const id = String(operationId || "");
    window.dispatchEvent(new CustomEvent("assistant-operation-recovery", {
      detail: {
        operationId: id,
        metadata: trackedOperations()[id] || {},
        failure,
        recoverable: !!recoverable,
        source: String(source || "status-read"),
      },
    }));
  }

  function settleOperation(operation, source) {
    const id = String(operation?.operationId || "");
    if (!id) return null;
    emitOperationState(operation, source);
    const completed = operationResponse(operation);
    if (!completed) return null;
    untrackOperation(id);
    const timer = operationReconcileTimers.get(id);
    if (timer) clearTimeout(timer);
    operationReconcileTimers.delete(id);
    const waiters = operationWaiters.get(id) || [];
    operationWaiters.delete(id);
    waiters.forEach(resolve => resolve(completed));
    return completed;
  }

  function invalidOperationResponse(response) {
    const status = Number(response?.status || 500);
    return {
      status,
      body: response?.body && typeof response.body === "object"
        ? response.body
        : { ok: false, error: "无法读取网络操作状态" },
    };
  }

  function finishOperationReadFailure(operationId, failure, source) {
    const id = String(operationId || "");
    const status = Number(failure?.status || 0);
    const permanent = status >= 400 && status < 500;
    emitOperationReadIssue(id, failure, source, !permanent);
    if (!permanent) return { ...failure, recoverable: true };
    untrackOperation(id);
    const timer = operationReconcileTimers.get(id);
    if (timer) clearTimeout(timer);
    operationReconcileTimers.delete(id);
    const waiters = operationWaiters.get(id) || [];
    operationWaiters.delete(id);
    waiters.forEach(resolve => resolve(failure));
    return { ...failure, recoverable: false };
  }

  async function refreshOperation(operationId, source = "status-read") {
    const id = String(operationId || "");
    if (!id) return { status: 500, body: { ok: false, error: "核心未返回 operationId" } };
    if (operationReads.has(id)) return operationReads.get(id);
    const read = (async () => {
      try {
        const response = await coreRequest(
          "GET",
          `${OPERATION_STATUS_PATH}?operationId=${encodeURIComponent(id)}`,
          null,
        );
        const status = Number(response?.status || 500);
        const operation = response?.body?.operation;
        if (status < 200 || status >= 300 || !operation) {
          return finishOperationReadFailure(
            id,
            invalidOperationResponse(response),
            source,
          );
        }
        settleOperation(operation, source);
        return { status, operation };
      } catch (error) {
        return finishOperationReadFailure(id, {
          status: 0,
          body: {
            ok: false,
            error: String(error?.message || error || "网络操作状态暂时无法读取"),
            code: "OPERATION_STATUS_TEMPORARILY_UNAVAILABLE",
            operationId: id,
          },
        }, source);
      }
    })().finally(() => operationReads.delete(id));
    operationReads.set(id, read);
    return read;
  }

  function scheduleOperationReconcile(operationId) {
    const id = String(operationId || "");
    if (!id || operationReconcileTimers.has(id)) return;
    operationReconcileTimers.set(id, setTimeout(async () => {
      operationReconcileTimers.delete(id);
      await refreshOperation(id, "event-watchdog");
      if (operationWaiters.has(id) || isTrackedOperation(id)) {
        scheduleOperationReconcile(id);
      }
    }, OPERATION_RECONCILE_MILLIS));
  }

  async function waitForOperation(operationId) {
    const id = String(operationId || "");
    if (!id) {
      return { status: 500, body: { ok: false, error: "核心未返回 operationId" } };
    }
    trackOperation(id);
    return new Promise(resolve => {
      const waiters = operationWaiters.get(id) || [];
      waiters.push(resolve);
      operationWaiters.set(id, waiters);
      scheduleOperationReconcile(id);
      void refreshOperation(id, "wait-registration");
    });
  }

  async function cancelOperation(operationId) {
    const id = String(operationId || "");
    if (!id) return { status: 400, body: { ok: false, error: "缺少 operationId" } };
    const response = await coreRequest("POST", OPERATION_CANCEL_PATH, { operationId: id });
    const operation = response?.body?.operation;
    if (operation) settleOperation(operation, "user-cancel");
    return response;
  }

  async function recoverTrackedOperations() {
    const tracked = trackedOperations();
    await Promise.all(Object.keys(tracked).map(async operationId => {
      const state = await refreshOperation(operationId, "page-recovery");
      if (state?.operation && !TERMINAL_OPERATION_STATES.has(String(state.operation.status || ""))) {
        scheduleOperationReconcile(operationId);
      } else if (state?.recoverable) {
        scheduleOperationReconcile(operationId);
      }
    }));
  }

  window.AssistantApi = Object.freeze({
    request: coreRequest,
    waitForOperation,
    cancelOperation,
    recoverTrackedOperations,
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
    __event(rawEvent) {
      let event;
      try { event = typeof rawEvent === "string" ? JSON.parse(rawEvent) : rawEvent; } catch (_) { return; }
      window.dispatchEvent(new CustomEvent("assistant-core-event", { detail: event }));
      const operationId = String(event?.operationId || "");
      if (!operationId) return;
      const eventId = Number(event?.eventId || 0);
      const previousEventId = Number(operationEventIds.get(operationId) || 0);
      if (eventId > 0 && eventId <= previousEventId) return;
      if (eventId > 0) operationEventIds.set(operationId, eventId);
      if (TERMINAL_OPERATION_STATES.has(String(event.status || ""))) {
        void refreshOperation(operationId, "native-terminal-event");
      } else {
        emitOperationState({
          ...event,
          operationId,
          kind: String(event.kind || ""),
          operationType: String(event.operationType || ""),
          accountRef: String(event.accountRef || ""),
          status: String(event.status || "RUNNING"),
          progress: Number(event.progress || 0),
          progressDetails: event.progressDetails || null,
          requestSent: !!event.requestSent,
          cancellationDenied: event.cancellationDenied || null,
          error: event.error || null,
        }, "native-progress-event");
      }
    },
  });

  if (hasNativeBridge) {
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
        trackOperation(payload.operationId, {
          method,
          path: url.pathname,
          accountRef: String(body?.accountRef || body?.sessionId || ""),
        });
        const completed = await waitForOperation(payload.operationId);
        status = completed.status;
        payload = completed.body;
      }
      return new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      });
    };
  }

  setTimeout(() => { void recoverTrackedOperations(); }, 0);
})();
