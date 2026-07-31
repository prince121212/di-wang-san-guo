"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

async function main() {
  const source = fs.readFileSync(
    path.resolve(__dirname, "../assistant-api.js"),
    "utf8",
  );
  const appSource = fs.readFileSync(path.resolve(__dirname, "../app.js"), "utf8");
  assert.match(
    appSource,
    /scope === "military"[\s\S]*\/api\/military\/intel\?sessionId=/,
  );
  let statusCalls = 0;
  const requestPaths = [];
  const window = {
    location: { href: "file:///android_asset/assistant/index.html" },
    fetch: async () => {
      throw new Error("native API calls must not use network fetch");
    },
  };
  window.DWPMNativeApi = {
    postMessage(raw) {
      const request = JSON.parse(raw);
      requestPaths.push(request.path);
      queueMicrotask(() => {
        if (request.path.startsWith("/api/military/intel")) {
          window.AssistantApi.__resolve({
            apiVersion: "v1",
            id: request.id,
            status: 202,
            body: {
              ok: true,
              accepted: true,
              operationId: "op_fixture",
              status: "QUEUED",
            },
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
                status: completed ? "SUCCEEDED" : "RUNNING",
                result: completed
                  ? { ok: true, militarySnapshot: { responded: true, actions: [] } }
                  : null,
              },
            },
          });
          return;
        }
        throw new Error(`unexpected request: ${request.path}`);
      });
    },
  };

  const context = {
    window,
    URL,
    Response,
    setTimeout,
    clearTimeout,
    queueMicrotask,
    encodeURIComponent,
    console,
  };
  vm.runInNewContext(source, context, { filename: "assistant-api.js" });

  const response = await window.fetch("/api/military/intel?sessionId=202");
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.ok, true);
  assert.equal(payload.militarySnapshot.responded, true);
  assert.equal(statusCalls, 2);
  assert.equal(requestPaths[0], "/api/military/intel?sessionId=202");
  assert.ok(requestPaths.slice(1).every(item =>
    item.startsWith("/api/core/operations/status?operationId=op_fixture")
  ));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
