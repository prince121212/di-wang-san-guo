import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source=readFileSync(new URL("../../电脑端辅助前端/app.js",import.meta.url),"utf8");
const extract=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
// Exercise actual cloned-row handlers without touching a real game account.
function page() {
  const rows=[];const notices=[];let saved=0;
  const classes=initial=>{const set=new Set(initial);return {contains:k=>set.has(k),add:k=>set.add(k),remove:k=>set.delete(k),toggle(k,force){const on=force??!set.has(k);on?set.add(k):set.delete(k);return on;}};};
  function row(copy) {
    const r={};const picker={dataset:{selectedOrder:copy?.picker.dataset.selectedOrder||"",maxSelected:"5"},classList:classes(["formation-general-multi"])};
    const inputs=Array.from({length:7},(_,i)=>({type:"checkbox",value:String(i+1),checked:copy?.inputs[i].checked||false,
      disabled:copy?.inputs[i].disabled||false,dataset:{fiefId:i===6?"B":"A"},closest:()=>picker}));
    const labels=inputs.map((input,i)=>({style:{display:copy?.labels[i].style.display||""},textContent:`将领${i+1}`,classList:classes([]),querySelector:()=>input}));
    const button=()=>({closest:()=>picker,click(){this.onclick?.({stopPropagation(){}});}});
    const summary=button(),all=button(),clear=button();
    const panel={querySelectorAll:()=>labels};
    const search={type:"text",placeholder:"搜索",value:copy?.search.value||"",closest:()=>panel};
    picker.querySelectorAll=q=>q===".formation-general-check"?inputs:q===".formation-general-check:checked"?inputs.filter(i=>i.checked):q===".formation-general-option"?labels:[];
    picker.querySelector=q=>q===".formation-general-summary"?summary:q===".formation-general-search"?search:null;
    picker.closest=()=>null;
    const enabled={type:"checkbox",checked:copy?.enabled.checked||false};
    r.picker=picker;r.inputs=inputs;r.labels=labels;r.summary=summary;r.search=search;r.enabled=enabled;r.all=all;r.clear=clear;
    r.querySelectorAll=q=>q==="input"?[enabled,...inputs,search]:q===".formation-general-multi"?[picker]:[];
    r.querySelector=q=>q==="input[type='checkbox']"?enabled:null;
    r.cloneNode=()=>row(r);
    if(copy?.picker.classList.contains("open"))picker.classList.add("open");
    return r;
  }
  const tbody={get children(){return rows;},appendChild:r=>rows.push(r),querySelector:q=>q==="tr:last-child"?rows.at(-1):rows[0],querySelectorAll:()=>rows};
  const root={querySelector:()=>tbody};
  const add={closest:()=>root},copy={closest:()=>root};
  const document={querySelectorAll(q){
    if(q===".dynamic-add")return [add];if(q===".dynamic-copy")return [copy];
    const map={".formation-general-multi":r=>[r.picker],".formation-general-multi.open":r=>r.picker.classList.contains("open")?[r.picker]:[],
      ".formation-general-summary":r=>[r.summary],".formation-general-check":r=>r.inputs,".formation-general-search":r=>[r.search],".fg-all":r=>[r.all],".fg-clear":r=>[r.clear]};
    return map[q]?rows.flatMap(map[q]):[];
  }};
  rows.push(row());
  const sync=extract("function selectedGeneralIdsInRoot(","function saveGeneralMultiOwner(");
  const dynamic=extract("function bindDesignDynamicControls()","function syncPolicyMultiUi(");
  const binding=source.includes("function bindGeneralMultiControls()")
    ?extract("function resetClonedGeneralPickers(","function bindDesignDynamicControls()")
    :`function bindGeneralMultiControls(){${extract('  document.querySelectorAll(".formation-general-summary")','  document.querySelectorAll(".formation-delete")')}}`;
  const context=vm.createContext({document,formationGeneralSummary:ids=>ids.join(","),showToast:t=>notices.push(t),saveGeneralMultiOwner:()=>saved++,syncDungeonStageSelect(){}});
  vm.runInContext(sync+binding+dynamic+";bindGeneralMultiControls();bindDesignDynamicControls();",context);
  return {rows,notices,add:()=>add.onclick(),copy:()=>copy.onclick(),saved:()=>saved,bind:()=>vm.runInContext("bindDesignDynamicControls()",context)};
}

test("new second and third mine rows open their own general picker",()=>{
  const ui=page();ui.add();ui.add();
  assert.equal(ui.rows[1].search.value,"");
  for(const r of ui.rows){r.summary.click();assert.equal(r.picker.classList.contains("open"),true);assert.equal(ui.rows.filter(x=>x.picker.classList.contains("open")).length,1);}
});
test("cloned rows keep change/search/select-all/clear working without changing the original",()=>{
  const ui=page();ui.rows[0].inputs[0].checked=true;ui.rows[0].picker.dataset.selectedOrder="1";
  ui.copy();const r=ui.rows[1];r.clear.click();assert.equal(r.inputs.some(i=>i.checked),false);assert.equal(ui.rows[0].inputs[0].checked,true);
  r.inputs[1].checked=true;r.inputs[1].onchange();assert.equal(r.picker.dataset.selectedOrder,"2");
  r.search.value="将领2";r.search.oninput();assert.equal(r.labels[0].style.display,"none");assert.equal(r.labels[1].style.display,"flex");
  r.all.click();assert.equal(r.inputs.filter(i=>i.checked).length,5);assert.equal(r.inputs[6].checked,false);
});
test("repeated rebinding does not double-toggle a picker",()=>{
  const ui=page();ui.add();ui.bind();ui.bind();const r=ui.rows[1];
  r.summary.click();assert.equal(r.picker.classList.contains("open"),true);
  r.summary.click();assert.equal(r.picker.classList.contains("open"),false);
});

test("copy resets transient open/search state but preserves selected generals",()=>{
  const ui=page();const first=ui.rows[0];first.inputs[0].checked=true;first.picker.dataset.selectedOrder="1";
  first.summary.click();first.search.value="missing";first.search.oninput();ui.copy();
  const r=ui.rows[1];assert.equal(r.picker.classList.contains("open"),false);assert.equal(r.search.value,"");
  assert.equal(r.labels.every(l=>l.style.display!=="none"),true);assert.equal(r.inputs[0].checked,true);
});
