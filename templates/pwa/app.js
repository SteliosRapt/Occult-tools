// Spell Explorer (explorer.py, `make pwa`): filter, sort, search and read spells.json.
// Facets AND together; values inside a facet OR (Wizard or Sorcerer). Search words AND, "quoted
// phrases" match as written; accents and case are ignored. The hash is the router: #/fireball
// opens a spell, so links, Back and the installed app all work offline.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const STORE = "occult-explorer";
const LEVEL = (l) => (l === 0 ? "Cantrip" : `Level ${l}`);
const GROUP = (l) => (l === 0 ? "Cantrips" : `Level ${l}`);
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ESC[c]);

// One character per character (as text.fold in Python), so an index into fold(s) is one into s.
const fold = (s) => s.replace(/[^\x00-\x7f]/g, (c) => c.normalize("NFD")[0]).toLowerCase();

let SPELLS = [], BY_ID = new Map(), shown = [];
const state = { q: "", c: new Set(), l: new Set(), s: new Set(), b: new Set(), f: new Set(), sort: "level" };

function load() {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) || "{}");
    for (const k of ["c", "l", "s", "b", "f"]) state[k] = new Set(v[k] || []);
    if (v.sort === "az" || v.sort === "level") state.sort = v.sort;
  } catch (e) { /* private mode: start empty */ }
}
function save() {
  try {
    const v = { sort: state.sort === "match" ? "level" : state.sort };
    for (const k of ["c", "l", "s", "b", "f"]) v[k] = [...state[k]];
    localStorage.setItem(STORE, JSON.stringify(v));
  } catch (e) { /* ignore */ }
}

// ------------------------------------------------------------------ search
function terms(q) {
  const out = [];
  fold(q).replace(/"([^"]+)"|(\S+)/g, (_, p, w) => { const t = (p || w).trim(); if (t) out.push(t); });
  return out;
}
// 0 = no match; higher is better. Every term must occur in the name or the text.
function score(sp, ts) {
  let total = 0;
  for (const t of ts) {
    const i = sp.ft.indexOf(t);
    if (i === 0) total += 100;
    else if (i > 0) total += sp.ft[i - 1] === " " ? 60 : 30;
    else if (sp.fx.includes(t)) total += 1;
    else return 0;
  }
  return total;
}
function snippet(sp, ts) {
  if (!ts.length || ts.every((t) => sp.ft.includes(t))) return "";
  const t = ts.find((t) => !sp.ft.includes(t) && sp.fx.includes(t));
  if (!t) return "";
  const i = sp.fx.indexOf(t);
  let a = Math.max(0, i - 50), b = Math.min(sp.x.length, i + t.length + 70);
  if (a > 0) a = sp.x.indexOf(" ", a) + 1 || a;
  if (b < sp.x.length) { const j = sp.x.lastIndexOf(" ", b); if (j > i + t.length) b = j; }
  return (a > 0 ? "…" : "") + mark(sp.x.slice(a, b), ts) + (b < sp.x.length ? "…" : "");
}
// Escape s and wrap every occurrence of a term in <mark>.
function mark(s, ts) {
  const f = fold(s), hits = [];
  for (const t of ts) for (let i = f.indexOf(t); i >= 0; i = f.indexOf(t, i + t.length)) hits.push([i, i + t.length]);
  if (!hits.length) return esc(s);
  hits.sort((x, y) => x[0] - y[0]);
  let out = "", at = 0;
  for (const [a, b] of hits) {
    if (a < at) continue;
    out += esc(s.slice(at, a)) + "<mark>" + esc(s.slice(a, b)) + "</mark>";
    at = b;
  }
  return out + esc(s.slice(at));
}

// ------------------------------------------------------------------ filtering
const TESTS = {
  c: (sp, v) => v.some((c) => sp.c.includes(c)),
  l: (sp, v) => v.includes(String(sp.l)),
  s: (sp, v) => v.includes(sp.s),
  b: (sp, v) => v.includes(sp.b),
  f: (sp, v) => v.every((f) => (f === "rit" ? sp.rit : f === "con" ? sp.con : !sp.con)),
};
function passes(sp, skip) {
  for (const k in TESTS) if (k !== skip && state[k].size && !TESTS[k](sp, [...state[k]])) return false;
  return true;
}
function apply() {
  const ts = terms(state.q);
  const base = SPELLS.filter((sp) => (sp._score = ts.length ? score(sp, ts) : 1) > 0);
  shown = base.filter((sp) => passes(sp));
  const sort = state.sort === "match" && !ts.length ? "level" : state.sort;
  const az = (a, b) => (a.ft < b.ft ? -1 : a.ft > b.ft ? 1 : 0);
  shown.sort(sort === "az" ? az : sort === "match" ? (a, b) => b._score - a._score || a.l - b.l || az(a, b)
    : (a, b) => a.l - b.l || az(a, b));
  renderList(ts, sort);
  renderFacets(base);
  renderActive();
  $('[data-sort="match"]').hidden = !ts.length;
  $$(".sort [data-sort]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.sort === sort)));
  save();
  const id = current();
  if (id) renderReader(id, false);
}

function renderFacets(base) {
  for (const box of $$(".chips[data-facet]")) {
    const k = box.dataset.facet;
    const pool = base.filter((sp) => passes(sp, k));
    for (const chip of $$(".chip", box)) {
      const v = chip.dataset.v;
      const n = pool.filter((sp) => TESTS[k](sp, [v])).length;
      const on = state[k].has(v);
      chip.setAttribute("aria-pressed", String(on));
      chip.querySelector("em").textContent = n;
      chip.classList.toggle("zero", !n && !on);
    }
  }
  const n = ["c", "l", "s", "b", "f"].reduce((a, k) => a + state[k].size, 0);
  const badge = $("#filter-badge");
  badge.hidden = !n;
  badge.textContent = n;
}

const FLAG_LABEL = { rit: "Ritual", con: "Concentration", nocon: "No concentration" };
function renderActive() {
  const pills = [];
  for (const k of ["c", "l", "s", "f", "b"]) for (const v of state[k]) {
    const label = k === "l" ? LEVEL(+v) : k === "f" ? FLAG_LABEL[v] : k === "b" ? $(`[data-facet="b"] [data-v="${v}"] span`).textContent : v;
    pills.push(`<button type="button" class="pill" data-k="${k}" data-v="${esc(v)}" aria-label="Remove ${esc(label)}">${esc(label)} <span aria-hidden="true">×</span></button>`);
  }
  $("#active").innerHTML = pills.join("");
}

function renderList(ts, sort) {
  const html = [];
  let group = null;
  for (const sp of shown) {
    if (sort === "level" && sp.l !== group) {
      group = sp.l;
      const n = shown.filter((x) => x.l === group).length;
      html.push(`<li class="group" role="presentation"><h3>${GROUP(group)}</h3><span>${n}</span></li>`);
    } else if (sort === "az") {
      const L = sp.t[0].toUpperCase();
      if (L !== group) { group = L; html.push(`<li class="group letter" role="presentation"><h3>${L}</h3></li>`); }
    }
    const tags = (sp.con ? '<i class="tag" title="Concentration">C</i>' : "") + (sp.rit ? '<i class="tag" title="Ritual">R</i>' : "");
    const snip = ts.length ? snippet(sp, ts) : "";
    html.push(`<li><a class="row" href="#/${sp.id}" data-id="${sp.id}">
<svg class="school-ic" aria-hidden="true"><use href="#school-${sp.s.toLowerCase()}"/></svg>
<span class="name">${ts.length ? mark(sp.t, ts) : esc(sp.t)}${tags}</span>
<span class="sub">${sp.l ? `Level ${sp.l} ${sp.s}` : `${sp.s} cantrip`} · ${esc(sp.ct.replace(/, which you take .*/, ", reaction"))} · ${esc(sp.r)}${sp.b !== "phb" ? ` · <b>${esc(sp.p.split(" ")[0])}</b>` : ""}</span>
${snip ? `<span class="snip">${snip}</span>` : ""}</a></li>`);
  }
  $("#list").innerHTML = html.join("");
  $("#empty").hidden = !!shown.length;
  const total = SPELLS.length;
  $("#count").innerHTML = shown.length === total ? `All <b>${total}</b> spells` : `<b>${shown.length}</b> of ${total} spells`;
  markSelected(current());
}

// ------------------------------------------------------------------ reader
function current() {
  const m = location.hash.match(/^#\/([a-z0-9-]+)$/);
  return m && BY_ID.has(m[1]) ? m[1] : null;
}
function markSelected(id) {
  $$(".row[aria-current]").forEach((r) => r.removeAttribute("aria-current"));
  const r = id && $(`.row[data-id="${id}"]`);
  if (r) r.setAttribute("aria-current", "true");
  return r;
}
function highlight(root, ts) {
  if (!ts.length) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const html = mark(n.nodeValue, ts);
    if (html.includes("<mark>")) {
      const span = document.createElement("span");
      span.innerHTML = html;
      n.replaceWith(...span.childNodes);
    }
  }
}
function renderReader(id, scrollTop = true) {
  const sp = BY_ID.get(id);
  const i = shown.indexOf(sp);
  $("#page").innerHTML = sp.h + `<p class="source">${esc(sp.p.replace(/ p(\d+)$/, ", page $1"))}</p>`;
  highlight($("#page"), terms(state.q));
  $("#pos").textContent = i >= 0 ? `${i + 1} of ${shown.length}` : "Not in this list";
  const prev = i > 0 ? shown[i - 1] : null, next = i >= 0 && i < shown.length - 1 ? shown[i + 1] : null;
  for (const [el, to] of [[$("#prev"), prev], [$("#next"), next]]) {
    el.href = to ? `#/${to.id}` : "#";
    el.classList.toggle("off", !to);
    el.setAttribute("aria-disabled", String(!to));
    el.title = to ? to.t : "";
  }
  if (scrollTop) $("#reader-scroll").scrollTop = 0;
  document.title = `${sp.t} · Spell Explorer`;
}
function route() {
  const id = current();
  const app = $("#app");
  if (id) {
    renderReader(id);
    $("#reader").hidden = false;
    app.classList.add("reading");
    const r = markSelected(id);
    if (r && wide()) r.scrollIntoView({ block: "nearest" });
  } else {
    $("#reader").hidden = true;
    app.classList.remove("reading");
    document.title = "Spell Explorer";
    markSelected(null);
  }
}
const wide = () => matchMedia("(min-width: 960px)").matches;

// ------------------------------------------------------------------ events
function wire() {
  const q = $("#q");
  let t;
  q.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      const had = !!terms(state.q).length;
      state.q = q.value;
      const has = !!terms(state.q).length;
      if (has && !had && state.sort === "level") state.sort = "match";
      if (!has && state.sort === "match") state.sort = "level";
      apply();
    }, 90);
  });
  q.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === "ArrowDown") {
      const first = $(".row");
      if (first) { e.preventDefault(); if (e.key === "Enter") { q.blur(); location.hash = first.getAttribute("href"); } else first.focus(); }
    }
  });
  $("#filters").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const set = state[chip.closest("[data-facet]").dataset.facet], v = chip.dataset.v;
    if (set.has(v)) set.delete(v); else set.add(v);
    if (v === "con") set.delete("nocon");
    if (v === "nocon") set.delete("con");
    apply();
  });
  $("#active").addEventListener("click", (e) => {
    const p = e.target.closest(".pill");
    if (p) { state[p.dataset.k].delete(p.dataset.v); apply(); }
  });
  const clear = () => { for (const k of ["c", "l", "s", "b", "f"]) state[k].clear(); apply(); };
  $("#clear").addEventListener("click", clear);
  $("#empty-clear").addEventListener("click", () => { q.value = state.q = ""; clear(); });
  $(".sort").addEventListener("click", (e) => {
    const b = e.target.closest("[data-sort]");
    if (b) { state.sort = b.dataset.sort; apply(); }
  });
  const toggle = $("#filters-toggle");
  const setOpen = (open) => { $("#app").classList.toggle("filters-open", open); toggle.setAttribute("aria-expanded", String(open)); };
  toggle.addEventListener("click", () => setOpen(!$("#app").classList.contains("filters-open")));
  $("#filters-done").addEventListener("click", () => setOpen(false));
  $("#back").addEventListener("click", (e) => {
    e.preventDefault();
    if (history.state && history.state.fromList) history.back();
    else history.replaceState(null, "", location.pathname + location.search);
    route();
  });
  $("#list").addEventListener("click", (e) => {
    const a = e.target.closest(".row");
    if (!a) return;
    e.preventDefault();
    const url = a.getAttribute("href");
    if (current()) history.replaceState({ fromList: true }, "", url);   // stepping: Back returns to the list
    else history.pushState({ fromList: true }, "", url);
    route();
  });
  for (const id of ["#prev", "#next"]) $(id).addEventListener("click", (e) => {
    e.preventDefault();
    const h = e.currentTarget.getAttribute("href");
    if (h !== "#") { history.replaceState(history.state, "", h); route(); }
  });
  addEventListener("hashchange", route);
  addEventListener("popstate", route);
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
    if (e.key === "/" && !typing) { e.preventDefault(); q.focus(); q.select(); }
    else if (e.key === "Escape") {
      if (typing) { q.blur(); }
      else if ($("#app").classList.contains("filters-open")) setOpen(false);
      else if (current()) $("#back").click();
    } else if (!typing && current() && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      $(e.key === "ArrowLeft" ? "#prev" : "#next").click();
    } else if (!typing && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      const rows = $$(".row"), i = rows.indexOf(document.activeElement);
      const to = rows[e.key === "ArrowDown" ? i + 1 : Math.max(0, i - 1)];
      if (to) { e.preventDefault(); to.focus(); if (wide()) { history.replaceState({ fromList: true }, "", to.getAttribute("href")); route(); } }
    }
  });
  // colour theme: auto -> light -> dark
  $("#theme").addEventListener("click", () => {
    const order = [undefined, "light", "dark"];
    const next = order[(order.indexOf(document.documentElement.dataset.theme) + 1) % 3];
    if (next) document.documentElement.dataset.theme = next; else delete document.documentElement.dataset.theme;
    try { next ? localStorage.setItem(STORE + "-theme", next) : localStorage.removeItem(STORE + "-theme"); } catch (e) { /* ignore */ }
    toast(next ? `${next[0].toUpperCase() + next.slice(1)} theme` : "Theme follows your device");
  });
}

function toast(msg, action) {
  const el = $("#toast");
  el.innerHTML = esc(msg) + (action ? ` <button type="button">${esc(action.label)}</button>` : "");
  el.hidden = false;
  if (action) el.querySelector("button").onclick = action.run;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.hidden = true), action ? 12000 : 1800);
}

// ------------------------------------------------------------------ install and offline
function pwa() {
  let deferred;
  addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e;
    $("#install").hidden = false;
  });
  $("#install").addEventListener("click", async () => {
    if (!deferred) return;
    deferred.prompt();
    await deferred.userChoice;
    deferred = null;
    $("#install").hidden = true;
  });
  if (!("serviceWorker" in navigator) || location.protocol === "file:") return;
  navigator.serviceWorker.register("sw.js").then((reg) => {
    const offer = (w) => toast("A new version of the spells is ready.", { label: "Reload", run: () => w.postMessage("skip-waiting") });
    if (reg.waiting && navigator.serviceWorker.controller) offer(reg.waiting);
    reg.addEventListener("updatefound", () => {
      const w = reg.installing;
      w.addEventListener("statechange", () => {
        if (w.state === "installed") navigator.serviceWorker.controller ? offer(w) : toast("Ready to use offline");
      });
    });
  }).catch(() => { /* no offline mode */ });
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => { if (!reloaded) { reloaded = true; location.reload(); } });
}

// ------------------------------------------------------------------ start
async function start() {
  // the level headings stick just under the (phone) header, whatever its height
  const top = $(".top");
  new ResizeObserver(() => document.documentElement.style.setProperty("--top-h", top.offsetHeight + "px")).observe(top);
  load();
  wire();
  pwa();
  try {
    const data = await (await fetch("spells.json")).json();
    SPELLS = data.spells;
  } catch (e) {
    $("#count").textContent = "Could not load the spells. Check your connection and reload.";
    return;
  }
  for (const sp of SPELLS) {
    sp.ft = fold(sp.t);
    sp.fx = fold(sp.x);
    BY_ID.set(sp.id, sp);
  }
  const q = new URLSearchParams(location.search).get("q");
  if (q) { $("#q").value = state.q = q; state.sort = "match"; }
  apply();
  route();
  document.body.dataset.ready = "";
}
start();
