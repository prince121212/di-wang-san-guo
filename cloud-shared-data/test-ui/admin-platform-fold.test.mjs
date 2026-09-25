import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

// Exercise the shipped render function and its real click/keyboard handlers,
// without a browser dependency or requests to the production administrator API.
class Element {
  constructor(dataset = {}) {
    this.dataset = dataset;
    this.handlers = new Map();
    this.rows = [];
    this.children = [];
  }
  set innerHTML(value) {
    this.html = value;
    this.rows = [...value.matchAll(/<tr class="platform-row" data-platform-key="([^"]+)"[^>]*aria-expanded="([^"]+)"/g)]
      .map(([, key, expanded]) => Object.assign(new Element({ platformKey: key }), { expanded }));
  }
  get innerHTML() { return this.html || ""; }
  querySelectorAll(selector) { return selector === "[data-platform-key]" ? this.rows : []; }
  addEventListener(name, handler) { this.handlers.set(name, handler); }
  replaceChildren(...children) { this.children = children; }
  scrollIntoView() {}
}

const servers = [
  { platformKey: "sglm", platformName: "热血三国联盟", serverKey: "352", areaName: "352区" },
  { platformKey: "sglm", platformName: "热血三国联盟", serverKey: "351", areaName: "351区" },
  { platformKey: "dangle", platformName: "当乐帝王三国", serverKey: "51", areaName: "51区" },
];

function dashboard(rows = servers) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const context = vm.createContext({
    document: { getElementById: element, createElement: () => new Element() },
    setTimeout, clearTimeout, setInterval, clearInterval,
  });
  const source = readFileSync(new URL("../public/admin/admin.js", import.meta.url), "utf8")
    .replace(/\ninitialize\(\);\s*$/, "\n");
  vm.runInContext(source + `
    loadMap = async () => {};
    renderSelectedServerHeading = () => {};
    globalThis.ui = {
      state, renderServers, selectServer,
      refresh: async servers => {
        api = async () => ({servers, totals: {}, generatedAtMillis: 12345});
        await loadOverview({quiet: true});
      },
    };
  `, context);
  const ui = context.ui;
  ui.state.overview = { servers: rows };
  ui.state.selectedServerKey = rows.length ? `${rows[0].platformKey}\u001f${rows[0].serverKey}` : "";
  const row = key => element("serverTableBody").rows.find(row => row.dataset.platformKey === key);
  return {
    ...ui, element,
    click: key => row(key).handlers.get("click")(),
    key: (platform, key) => {
      let prevented = false;
      row(platform).handlers.get("keydown")({key, preventDefault: () => { prevented = true; }});
      assert.equal(prevented, true);
    },
    expanded: key => row(key).expanded === "true",
    childCount: () => (element("serverTableBody").innerHTML.match(/class="clickable server-child/g) || []).length,
  };
}

test("first non-empty render expands the selected platform only", () => {
  const ui = dashboard();
  ui.renderServers();
  assert.equal(ui.expanded("sglm"), true);
  assert.equal(ui.expanded("dangle"), false);
  assert.equal(ui.childCount(), 2);
});

test("clicking the last expanded platform leaves all platforms collapsed", () => {
  const ui = dashboard();
  ui.renderServers();
  ui.click("sglm");
  assert.equal(ui.expanded("sglm"), false);
  assert.equal(ui.state.expandedPlatforms.size, 0);
  assert.equal(ui.childCount(), 0);
  ui.renderServers();
  assert.equal(ui.childCount(), 0);
  ui.click("sglm");
  assert.equal(ui.childCount(), 2);
});

test("both platforms independently collapse, including the last open group", () => {
  const ui = dashboard();
  ui.renderServers();
  ui.click("dangle");
  assert.equal(ui.childCount(), 3);
  ui.click("sglm");
  assert.equal(ui.expanded("dangle"), true);
  assert.equal(ui.expanded("sglm"), false);
  ui.click("dangle");
  assert.equal(ui.childCount(), 0);
});

test("automatic overview refresh does not reopen an explicitly collapsed platform", async () => {
  const ui = dashboard();
  ui.renderServers();
  ui.click("sglm");
  await ui.refresh([...servers, { ...servers[0], serverKey: "353" }]);
  assert.equal(ui.expanded("sglm"), false);
  assert.equal(ui.childCount(), 0);
  assert.equal(ui.state.selectedServerKey, "sglm\u001f352");
});

test("an empty first response does not consume the default expansion", async () => {
  const ui = dashboard([]);
  ui.renderServers();
  await ui.refresh(servers);
  assert.equal(ui.expanded("sglm"), true);
  ui.click("sglm");
  await ui.refresh([]);
  await ui.refresh(servers);
  assert.equal(ui.childCount(), 0);
});

test("keyboard Enter and Space toggle a platform in both directions", () => {
  const ui = dashboard();
  ui.renderServers();
  ui.key("sglm", "Enter");
  assert.equal(ui.expanded("sglm"), false);
  ui.key("sglm", " ");
  assert.equal(ui.expanded("sglm"), true);
});

test("explicit server selection may still expand that server's platform", async () => {
  const ui = dashboard();
  ui.renderServers();
  ui.click("sglm");
  await ui.selectServer("dangle\u001f51");
  assert.equal(ui.expanded("dangle"), true);
  assert.equal(ui.expanded("sglm"), false);
  assert.equal(ui.state.selectedServerKey, "dangle\u001f51");
});
