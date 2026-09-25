import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../../电脑端辅助前端/index.html", import.meta.url), "utf8");
const source = readFileSync(new URL("../../电脑端辅助前端/app.js", import.meta.url), "utf8");
const shell = source.slice(source.indexOf("function renderMainPageShell() {"), source.indexOf("async function callGuideReference("));

function navigation(mobile = true) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, { textContent: "", dataset: {}, classes,
        classList: { toggle: (key,on) => on ? classes.add(key) : classes.delete(key) } });
    }
    return elements.get(id);
  };
  const buttons = [...html.matchAll(/class="bottom-item[^"]*" data-page="([^"]+)"/g)]
    .map(([,page])=>Object.assign(element("tab:"+page),{dataset:{page}}));
  const context = vm.createContext({document:{getElementById:element,
    querySelector:()=>element("title"),querySelectorAll:selector=>selector.startsWith(".bottom-item")?buttons:[]}});
  vm.runInContext(`let activeMainPage="助手",activeOtherView="home",settingsRenders=0;
    const isMobileLocal=${mobile};
    function renderHomeAccountOptions(){settingsRenders++;}
    ${shell}
    globalThis.navigate=page=>{activeMainPage=page;renderMainPageShell();};
    globalThis.settingsCount=()=>settingsRenders;`, context);
  return {element,buttons,navigate:context.navigate,settingsCount:context.settingsCount};
}

test("bottom navigation order is guide, assistant, Home", () => {
  assert.deepEqual(navigation().buttons.map(x=>x.dataset.page), ["其他","助手","Home"]);
  const home = html.slice(html.indexOf('<section id="homePage"'), html.indexOf('<footer class="bottom-nav"'));
  assert.match(home,/id="homeMembershipSlot"/);
  assert.equal((html.match(/id="homeMembershipSlot"/g)||[]).length,1);
});

test("only the selected page is visible; Home content cannot leak into assistant or guide", () => {
  const ui = navigation();
  const pages = {"助手":"assistantPage","其他":"otherPage","Home":"homePage","日志":"logPage"};
  for(const active of ["Home","助手","其他","日志","Home"]) {
    ui.navigate(active);
    for(const [name,id] of Object.entries(pages)) {
      assert.equal(ui.element(id).classes.has("page-hidden"),name!==active,`${active}: ${id}`);
    }
    for(const button of ui.buttons) assert.equal(button.classes.has("active"),button.dataset.page===active);
  }
});

test("mobile Home no longer runs the legacy game-account settings viewer", () => {
  const ui = navigation(); ui.navigate("Home");
  assert.equal(ui.settingsCount(),0);
  const css=readFileSync(new URL("../../电脑端辅助前端/styles.css",import.meta.url),"utf8");
  assert.match(css,/body\.mobile-local-mode #homePage > \.home-settings-toolbar,\s*body\.mobile-local-mode #homeSettingsContent\s*\{\s*display: none;/);
});

test("desktop Home retains the existing settings viewer", () => {
  const ui=navigation(false); ui.navigate("Home");
  assert.equal(ui.settingsCount(),1);
  assert.match(html,/id="homeAccountSelect"/);
  assert.match(html,/id="viewAccountSettingsBtn"/);
});

test("phone navigation uses the real viewport instead of the tall desktop canvas", () => {
  const css=readFileSync(new URL("../../电脑端辅助前端/styles.css",import.meta.url),"utf8");
  assert.match(css,/body\.mobile-local-mode \.bottom-nav\s*\{\s*position: fixed;/);
  assert.match(css,/body\.mobile-local-mode \.app-shell\s*\{\s*padding-bottom: 170px;/);
  assert.match(css,/body\.mobile-local-mode #homePage\s*\{\s*height: calc\(100vh - 170px\);/);
});
