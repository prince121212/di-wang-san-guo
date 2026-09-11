"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.resolve(__dirname, "../assistant-api.js"),
  "utf8",
);
const appSource = fs.readFileSync(path.resolve(__dirname, "../app.js"), "utf8");

class TestCustomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.detail = init.detail;
  }
}

function createLocalStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(String(key), String(value)); },
    removeItem(key) { values.delete(String(key)); },
    value(key) { return values.get(String(key)); },
  };
}

function createHarness(responder, initialStorage = {}) {
  const listeners = new Map();
  const requestPaths = [];
  const localStorage = createLocalStorage(initialStorage);
  const window = {
    location: { href: "file:///android_asset/assistant/index.html" },
    fetch: async () => { throw new Error("native API calls must not use network fetch"); },
    addEventListener(type, listener) {
      const rows = listeners.get(type) || [];
      rows.push(listener);
      listeners.set(type, rows);
    },
    dispatchEvent(event) {
      (listeners.get(event.type) || []).forEach(listener => listener(event));
      return true;
    },
  };
  window.DWPMNativeApi = {
    postMessage(raw) {
      const request = JSON.parse(raw);
      requestPaths.push(request.path);
      queueMicrotask(() => responder({ request, window }));
    },
  };
  const context = {
    window,
    localStorage,
    CustomEvent: TestCustomEvent,
    URL,
    Response,
    setTimeout,
    clearTimeout,
    queueMicrotask,
    encodeURIComponent,
    console,
    Date,
  };
  vm.runInNewContext(source, context, { filename: "assistant-api.js" });
  return { window, localStorage, requestPaths };
}

function createDesktopHarness(responder, initialStorage = {}) {
  const listeners = new Map();
  const requestPaths = [];
  const localStorage = createLocalStorage(initialStorage);
  const window = {
    location: { href: "http://127.0.0.1:5566/" },
    async fetch(input, init = {}) {
      const path = typeof input === "string" ? input : input?.url;
      requestPaths.push(String(path || ""));
      return responder({ path: String(path || ""), init, window });
    },
    addEventListener(type, listener) {
      const rows = listeners.get(type) || [];
      rows.push(listener);
      listeners.set(type, rows);
    },
    dispatchEvent(event) {
      (listeners.get(event.type) || []).forEach(listener => listener(event));
      return true;
    },
  };
  const context = {
    window,
    localStorage,
    CustomEvent: TestCustomEvent,
    URL,
    Response,
    setTimeout,
    clearTimeout,
    queueMicrotask,
    encodeURIComponent,
    console,
    Date,
  };
  vm.runInNewContext(source, context, { filename: "assistant-api.js" });
  return { window, localStorage, requestPaths };
}

async function waitUntil(predicate, message, timeoutMillis = 1000) {
  const deadline = Date.now() + timeoutMillis;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 5));
  }
  assert.fail(message);
}

async function testEventDrivenCompletion() {
  let statusCalls = 0;
  const states = [];
  const harness = createHarness(({ request, window }) => {
    if (request.path.startsWith("/api/military/intel")) {
      window.AssistantApi.__resolve({
        apiVersion: "v1",
        id: request.id,
        status: 202,
        body: { ok: true, accepted: true, operationId: "op_fixture", status: "QUEUED" },
      });
      return;
    }
    if (request.path.startsWith("/api/core/operations/status")) {
      statusCalls += 1;
      const completed = statusCalls >= 2;
      window.AssistantApi.__resolve({
        apiVersion: "v1",
        id: request.id,
        status: 200,
        body: {
          ok: true,
          operation: {
            operationId: "op_fixture",
            kind: "route:GET:/api/military/intel",
            status: completed ? "SUCCEEDED" : "RUNNING",
            requestSent: !completed,
            progress: completed ? 100 : 10,
            result: completed
              ? { ok: true, militarySnapshot: { responded: true, actions: [] } }
              : null,
          },
        },
      });
      if (!completed) {
        queueMicrotask(() => {
          window.AssistantApi.__event({
            eventId: 10,
            type: "operation.progress",
            operationId: "op_fixture",
            kind: "route:GET:/api/military/intel",
            status: "RUNNING",
            progress: 55,
            progressDetails: { phase: "waiting-reply" },
            requestSent: true,
          });
          window.AssistantApi.__event({
            eventId: 9,
            type: "operation.progress",
            operationId: "op_fixture",
            status: "RUNNING",
            progress: 5,
            requestSent: false,
          });
          window.AssistantApi.__event({
            eventId: 11,
            type: "operation.completed",
            operationId: "op_fixture",
            status: "SUCCEEDED",
            progress: 100,
            requestSent: true,
          });
        });
      }
      return;
    }
    throw new Error(`unexpected request: ${request.path}`);
  });
  harness.window.addEventListener("assistant-operation-state", event => states.push(event.detail));

  const response = await harness.window.fetch("/api/military/intel?sessionId=202");
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.ok, true);
  assert.equal(payload.militarySnapshot.responded, true);
  assert.equal(statusCalls, 2);
  assert.equal(harness.requestPaths[0], "/api/military/intel?sessionId=202");
  assert.ok(harness.requestPaths.slice(1).every(item =>
    item.startsWith("/api/core/operations/status?operationId=op_fixture")
  ));
  assert.ok(states.some(row => row.operation.progress === 55));
  assert.ok(!states.some(row => row.operation.progress === 5));
  assert.equal(
    JSON.parse(harness.localStorage.value("dwpm.android.tracked-operations.v1") || "{}").op_fixture,
    undefined,
  );
}

async function testCancellationAndSentBoundary() {
  const states = [];
  const harness = createHarness(({ request, window }) => {
    if (request.path === "/api/core/operations/cancel") {
      const operationId = String(request.body.operationId);
      const sent = operationId === "op_sent";
      window.AssistantApi.__resolve({
        apiVersion: "v1",
        id: request.id,
        status: 200,
        body: {
          ok: true,
          operation: {
            operationId,
            status: sent ? "RUNNING" : "CANCELLED",
            requestSent: sent,
            cancellationDenied: sent ? "request-already-sent" : null,
          },
        },
      });
      return;
    }
    throw new Error(`unexpected request: ${request.path}`);
  });
  harness.window.addEventListener("assistant-operation-state", event => states.push(event.detail));

  const cancelled = await harness.window.AssistantApi.cancelOperation("op_cancel");
  const denied = await harness.window.AssistantApi.cancelOperation("op_sent");
  assert.equal(cancelled.body.operation.status, "CANCELLED");
  assert.equal(denied.body.operation.status, "RUNNING");
  assert.equal(denied.body.operation.cancellationDenied, "request-already-sent");
  assert.ok(states.some(row => row.operation.status === "CANCELLED"));
  assert.ok(states.some(row => row.operation.cancellationDenied === "request-already-sent"));
}

async function testPageRecoveryAndTemporaryReadFailure() {
  let statusCalls = 0;
  const states = [];
  const recoveryIssues = [];
  const tracked = JSON.stringify({
    op_recovered: {
      operationId: "op_recovered",
      path: "/api/troops/heal",
      acceptedAt: 100,
    },
  });
  const harness = createHarness(({ request, window }) => {
    if (!request.path.startsWith("/api/core/operations/status")) {
      throw new Error(`unexpected request: ${request.path}`);
    }
    statusCalls += 1;
    if (statusCalls === 1) {
      // Reject through the same bridge timeout/error channel without leaving an
      // unhandled Promise; the persisted operation must remain recoverable.
      window.AssistantApi.__resolve({
        apiVersion: "v1",
        id: request.id,
        status: 500,
        body: { ok: false, error: "temporary local read failure" },
      });
      return;
    }
    const terminal = statusCalls >= 3;
    window.AssistantApi.__resolve({
      apiVersion: "v1",
      id: request.id,
      status: 200,
      body: {
        ok: true,
        operation: {
          operationId: "op_recovered",
          kind: "route:POST:/api/troops/heal",
          status: terminal ? "UNCERTAIN" : "RUNNING",
          requestSent: terminal,
          progress: terminal ? 80 : 25,
          error: terminal ? { code: "UNCERTAIN", message: "reply unknown" } : null,
        },
      },
    });
  }, { "dwpm.android.tracked-operations.v1": tracked });
  harness.window.addEventListener("assistant-operation-state", event => states.push(event.detail));
  harness.window.addEventListener("assistant-operation-recovery", event => recoveryIssues.push(event.detail));

  await waitUntil(() => recoveryIssues.length === 1, "page recovery did not report the temporary read failure");
  assert.equal(recoveryIssues[0].recoverable, true);
  assert.ok(JSON.parse(harness.localStorage.value("dwpm.android.tracked-operations.v1")).op_recovered);

  // Trigger a native event instead of waiting for the 15-second watchdog.
  harness.window.AssistantApi.__event({
    eventId: 20,
    type: "operation.progress",
    operationId: "op_recovered",
    status: "RUNNING",
    progress: 25,
    requestSent: false,
  });
  await harness.window.AssistantApi.recoverTrackedOperations();
  assert.ok(states.some(row => row.source === "page-recovery" && row.operation.status === "RUNNING"));

  harness.window.AssistantApi.__event({
    eventId: 21,
    type: "operation.uncertain",
    operationId: "op_recovered",
    status: "UNCERTAIN",
    progress: 80,
    requestSent: true,
  });
  await waitUntil(
    () => states.some(row => row.operation.status === "UNCERTAIN"),
    "terminal event did not reconcile the recovered operation",
  );
  assert.equal(
    JSON.parse(harness.localStorage.value("dwpm.android.tracked-operations.v1") || "{}").op_recovered,
    undefined,
  );
}

async function testDesktopPollingAndNestedWorkflowResult() {
  let statusCalls = 0;
  const states = [];
  const harness = createDesktopHarness(({ path }) => {
    assert.match(path, /^\/api\/core\/operations\/status\?operationId=op_desktop$/);
    statusCalls += 1;
    const completed = statusCalls >= 2;
    return new Response(JSON.stringify({
      ok: true,
      operation: {
        operationId: "op_desktop",
        kind: "route:POST:/api/brush/execute",
        status: completed ? "SUCCEEDED" : "RUNNING",
        progress: completed ? 100 : 45,
        requestSent: true,
        result: completed ? {
          ok: true,
          result: {
            success: true,
            successBattleId: 321,
            settlementPending: true,
          },
        } : null,
      },
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  harness.window.addEventListener("assistant-operation-state", event => states.push(event.detail));

  const completed = await harness.window.AssistantApi.waitForOperation("op_desktop");

  assert.equal(completed.status, 200);
  assert.equal(completed.body.ok, true);
  assert.equal(completed.body.success, true);
  assert.equal(completed.body.successBattleId, 321);
  assert.equal(completed.body.result.success, true);
  assert.equal(statusCalls, 2);
  assert.ok(states.some(row => row.operation.status === "RUNNING"));
  assert.ok(states.some(row => row.operation.status === "SUCCEEDED"));
  assert.equal(
    JSON.parse(harness.localStorage.value("dwpm.android.tracked-operations.v1") || "{}").op_desktop,
    undefined,
  );
}

async function main() {
  assert.match(appSource, /scope === "military"[\s\S]*\/api\/military\/intel\?sessionId=/);
  assert.match(appSource, /assistant-operation-state/);
  const trayListenerIndex = appSource.indexOf('window.addEventListener("assistant-operation-state"');
  const visibleRecoveryIndex = appSource.indexOf("recoverVisibleNetworkOperationsAfterPageLoad();");
  assert.ok(trayListenerIndex >= 0);
  assert.ok(visibleRecoveryIndex > trayListenerIndex);
  assert.match(appSource, /window\.AssistantApi\?\.recoverTrackedOperations/);
  assert.match(appSource, /data-network-operation-action="cancel"/);
  assert.match(appSource, /回执不明确/);
  assert.match(appSource, /res\.status === 202 && json\.operationId/);
  assert.match(appSource, /AssistantApi\?\.waitForOperation/);
  assert.match(appSource, /const dailyExecution = data\.dailyExecution \|\| \{\}/);
  assert.match(appSource, /dailyExecution\.accepted && Array\.isArray\(dailyExecution\.queuedKeys\)/);
  assert.match(appSource, /typeof result !== "object" \|\| Array\.isArray\(result\)/);
  assert.doesNotMatch(source, /OPERATION_POLL_MILLIS/);
  assert.doesNotMatch(source, /250\s*\)/);
  await testEventDrivenCompletion();
  await testCancellationAndSentBoundary();
  await testPageRecoveryAndTemporaryReadFailure();
  await testDesktopPollingAndNestedWorkflowResult();
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
