import { readFileSync } from "node:fs";
import vm from "node:vm";

// Minimal DOM for executing the shipped handlers. No production requests or emails.
export function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
export const flush = () => new Promise(resolve => setImmediate(resolve));
export function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}
export function harness(source, initialStorage = {}, initialFetch) {
  const elements = new Map(), events = new Map(), documentEvents = new Map(), intervals = [], requests = [], alerts = [], confirmations = [];
  const storage = new Map(Object.entries(initialStorage));
  const modes = [];
  function element(id = "") {
    if (elements.has(id)) return elements.get(id);
    const handlers = new Map();
    const value = { id, value: "", textContent: "", innerHTML: "", hidden: false, disabled: false, dataset: {}, children: [],
      classList: { toggle() {} }, append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      click() { this.onclick?.(); },
      addEventListener(name, fn) { handlers.set(name, fn); }, emit(name) { handlers.get(name)?.(); },
      focus() {}, checkValidity() { return true; }, reportValidity() {}, scrollIntoView() {},
      querySelectorAll(selector) {
        if (selector === "[data-mode]") return modes;
        if (selector === "button") return [element("memberGrant"), element("memberDisable"), element("memberRevoke")];
        return [];
      },
    };
    if (id) elements.set(id, value);
    return value;
  }
  for (const mode of ["login", "register", "reset-password"]) {
    modes.push(Object.assign(element("mode-" + mode), { dataset: { mode } }));
  }
  const storageApi = { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, String(v)), removeItem: k => storage.delete(k) };
  let fetchHandler = initialFetch || (() => Promise.resolve(response({ ok: true, authenticated: false, allowed: false })));
  const window = { DWPMNativeApi: {}, addEventListener: (name, fn) => events.set(name, fn),
    dispatchEvent: event => events.get(event.type)?.(event),
    confirm: message => { confirmations.push(message); return true; }, alert: message => alerts.push(message) };
  const context=vm.createContext({
    window, document: { getElementById: element, createElement: () => element(), body: element("body"),
      hidden: false, querySelectorAll: () => [],
      querySelector: selector => selector === '.bottom-item[data-page="Home"]' ? element("homeTab") : null,
      addEventListener: (name, fn) => documentEvents.set(name, fn) },
    sessionStorage: storageApi, localStorage: storageApi, crypto: { randomUUID: () => crypto.randomUUID() },
    AbortSignal, Event, setInterval: (fn, ms) => intervals.push({ fn, ms }),
    fetch: async (path, init = {}) => {
      const r = { path, ...init, body: init.body ? JSON.parse(init.body) : undefined };
      requests.push(r); return fetchHandler(r);
    },
  });
  vm.runInContext(readFileSync(new URL("../../电脑端辅助前端/membership-view.js",import.meta.url),"utf8"),context);
  vm.runInContext(readFileSync(new URL(source, import.meta.url), "utf8"),context);
  element("memberPlan").value = "month";
  return { element, window, intervals, requests, storage, alerts, confirmations,
    onFetch: fn => { fetchHandler = fn; },
    ready: () => events.get("dwpm-admin-ready")?.(),
    renew: () => documentEvents.get("click")?.({target:{closest:selector=>selector===".renew-btn"?{}:null}}),
    mode: name => element("mode-" + name).onclick(),
    search: email => { element("memberEmail").value = email; return element("memberSearch").onsubmit({ preventDefault() {} }); },
    submit: () => element("memberForm").onsubmit({ preventDefault() {} }),
  };
}
