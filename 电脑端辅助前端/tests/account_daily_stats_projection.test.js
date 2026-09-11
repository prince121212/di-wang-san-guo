"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../app.js"), "utf8");

function extractFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `app.js is missing function ${name}`);
  let parameterDepth = 0;
  let bodyStart = -1;
  for (let index = source.indexOf("(", start); index < source.length; index += 1) {
    if (source[index] === "(") parameterDepth += 1;
    if (source[index] === ")") parameterDepth -= 1;
    if (parameterDepth === 0 && source[index] === "{") {
      bodyStart = index;
      break;
    }
  }
  assert.notEqual(bodyStart, -1, `function ${name} has no body`);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  assert.fail(`function ${name} has no closing brace`);
}

const appState = {
  accountHabitsLoaded: {},
  area: null,
  sessionId: null,
  username: "",
};
let appliedSession = null;

const context = {
  appState,
  console,
  restoreAccountUi() {},
  applyServerHabits() {},
  snapshotCurrentAccountUi() {},
  ensureAccountLogLoaded() {},
  applySessionData(data) { appliedSession = data; },
};

[
  "normalizeDailyCount",
  "normalizeDailyStats",
  "dailyStatsForAccount",
  "applyAccountRecordMeta",
  "applyAccountRecord",
  "applyAccountSnapshot",
  "rowGeneralIds",
  "formationRowsForDesign",
].forEach(name => {
  vm.runInNewContext(extractFunction(name), context, { filename: `app.js#${name}` });
});

// Equal troop settings do not imply the same formation rule. The UI must keep
// two persisted rows visible when they use different generals.
appState.formations = [
  { enabled: true, generalIds: ["3752041", "3758051"], soldierType: "强弩兵", soldierCount: 99 },
  { enabled: true, generalIds: ["172738", "1826333"], soldierType: "强弩兵", soldierCount: 99 },
];
assert.equal(context.formationRowsForDesign().length, 2);
assert.equal(
  JSON.stringify(context.formationRowsForDesign().map(row => row.generalIds)),
  JSON.stringify([["3752041", "3758051"], ["172738", "1826333"]]),
);

function assertDailyStats(expectedBrush, expectedDungeon) {
  assert.equal(appState.dailyStats.brushYellowCount, expectedBrush);
  assert.equal(appState.dailyStats.dungeonCount, expectedDungeon);
}

// 手机端账号可以正常运行但不携带网页 session；顶层本地投影仍必须被展示。
context.applyAccountRecord({
  sessionId: "176",
  username: "1608601",
  areaName: "区352",
  dailyStats: { brushYellowCount: 11, dungeonCount: 2 },
}, { restoreUi: false });
assertDailyStats(11, 2);

// 轮询保留旧实时画面时只更新账号元数据，也必须同步最新本地计数。
context.applyAccountRecordMeta({
  sessionId: "176",
  username: "1608601",
  areaName: "区352",
  dailyStats: { brushYellowCount: 12, dungeonCount: 3 },
});
assertDailyStats(12, 3);

// 顶层是账号账本的当前投影，优先级高于 session 中可能滞后的旧计数。
context.applyAccountSnapshot({
  sessionId: "176",
  dailyStats: { brushYellowCount: 13, dungeonCount: 4 },
  session: {
    sessionId: "176",
    dailyStats: { brushYellowCount: 0, dungeonCount: 0 },
  },
}, { restoreUi: false });
assert.equal(appliedSession.dailyStats.brushYellowCount, 13);
assert.equal(appliedSession.dailyStats.dungeonCount, 4);

// 切换到另一个账号时必须使用该账号自己的值，不能沿用前一个账号。
context.applyAccountRecord({
  sessionId: "177",
  username: "other",
  dailyStats: { brushYellowCount: 1, dungeonCount: 0 },
}, { restoreUi: false });
assertDailyStats(1, 0);

// 入口必须全部走账号级投影，防止后续再次被硬编码 0 覆盖。
assert.match(source, /appState\.dailyStats = dailyStatsForAccount\(cur\);/);
assert.match(source, /applyAccountSnapshot\(acc, \{ restoreUi: true \}\);/);
