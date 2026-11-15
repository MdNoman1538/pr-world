// The world model: facts from world.json (Cartographer), plus the PR overlay (diff + review findings).
const cache = {};
export function getJSON(p) {
  if (!cache[p]) {
    const once = (n) => fetch("data/" + p).then((r) => { if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); })
      .catch((e) => (n > 0 && !/: (401|403|404)$/.test(e.message) ? new Promise((ok) => setTimeout(ok, 400)).then(() => once(n - 1)) : Promise.reject(e)));
    cache[p] = once(2).catch((e) => { delete cache[p]; throw e; });   // a failed fetch is never remembered
  }
  return cache[p];
}

export const MEMBER_KINDS = ["method", "ctor", "property", "field", "endpoint", "state", "column"];

export class World {
  constructor(w) {
    this.w = w;
    this.nodes = w.nodes;
    this.edges = w.edges;
    this.byId = new Map();
    this.kids = new Map();
    this.out = new Map();
    this.inn = new Map();
    for (const n of w.nodes) { n.attrs = n.attrs || {}; this.byId.set(n.id, n); }
    for (const n of w.nodes) { if (!this.kids.has(n.parent)) this.kids.set(n.parent, []); this.kids.get(n.parent).push(n); }
    for (const e of w.edges) {
      if (!this.out.has(e.source)) this.out.set(e.source, []); this.out.get(e.source).push(e);
      if (!this.inn.has(e.target)) this.inn.set(e.target, []); this.inn.get(e.target).push(e);
    }
    this.tested = new Set();
    for (const e of w.edges) { const s = this.byId.get(e.source); if (e.kind === "calls" && s && s.attrs.is_test) this.tested.add(e.target); }
    for (const e of w.edges) if (e.kind === "resolves" && this.tested.has(e.target)) this.tested.add(e.source);
    this.lite = w.generated_by === "lite";
  }
  node(id) { return this.byId.get(id); }
  children(id) { return this.kids.get(id) || []; }
  outE(id) { return this.out.get(id) || []; }
  inE(id) { return this.inn.get(id) || []; }
  typeOf(id) { let n = this.node(id); while (n && n.kind !== "type" && n.kind !== "table") n = this.node(n.parent); return n ? n.id : null; }
  memberOf(id) { let n = this.node(id); while (n && !MEMBER_KINDS.includes(n.kind)) n = this.node(n.parent); return n ? n.id : null; }
  descendants(id) { const out = [], st = [id]; while (st.length) { const c = st.pop(); for (const k of this.children(c)) { out.push(k); st.push(k.id); } } return out; }
  isTest(n) { return !!n && (n.module === "Tests" || n.attrs.is_test); }
  tier(module) { const n = this.node("module:" + module); return (n && n.attrs.tier) || "none"; }
  modules() { return this.nodes.filter((n) => n.kind === "module"); }
  moduleStats(m) {
    const mn = this.node("module:" + m);
    if (mn && mn.attrs.locked) return { types: 0, members: mn.attrs.size || 0, eps: [], methods: 0, tested: 0, pii: 0, unprotected: [], locked: true };
    const ds = this.descendants("module:" + m);
    const types = ds.filter((n) => n.kind === "type" || n.kind === "table");
    const eps = ds.filter((n) => n.kind === "endpoint");
    const methods = ds.filter((n) => n.kind === "method" && !this.isTest(n));
    const pii = ds.filter((n) => (n.kind === "property" || n.kind === "column") && n.attrs.pii);
    return { types: types.length, members: ds.filter((n) => MEMBER_KINDS.includes(n.kind)).length, eps, methods: methods.length,
      tested: methods.filter((n) => this.tested.has(n.id)).length, pii: pii.length, unprotected: eps.filter((e) => !e.attrs.protected) };
  }
  implOf(id) { const r = this.outE(id).filter((e) => e.kind === "resolves").map((e) => e.target).filter((x) => !this.isTest(this.node(x))); return r[0] || id; }
  innermost(file, line) {
    let best = null;
    for (const n of this.nodes) {
      if (n.file !== file || !n.line) continue;
      if (n.line <= line && (n.end_line || n.line) >= line && ["method", "ctor", "property", "field", "type", "endpoint"].includes(n.kind)) {
        const span = (n.end_line || n.line) - n.line, bs = best ? (best.end_line || best.line) - best.line : Infinity;
        if (!best || span < bs || (span === bs && n.kind !== "type")) best = n;
      }
    }
    if (!best) best = this.nodes.find((n) => n.file === file && n.kind === "type") || null;
    return best ? best.id : null;
  }
}

export function displayName(n) {
  if (!n) return "?";
  if (String(n.name).startsWith("<Main>")) return "startup";
  if (n.kind === "method" || n.kind === "ctor") return n.name + "()";
  return n.name;
}
export const shortType = (s) => String(s || "").replace(/System\.(Threading\.Tasks\.|Collections\.Generic\.)?/g, "").replace(/Bank\.[\w.]+\./g, "");

// PR overlay: what changed, what is affected, which findings sit where, and the trust evidence (notes/<PR>.json)
export class Overlay {
  constructor(W, diff, review, notes) {
    this.W = W;
    this.diff = diff || {};
    this.review = review || { findings: [] };
    this.notes = notes || null;
    this.changed = new Map(Object.entries(this.diff.changed || {}));
    this.up = new Map(Object.entries(this.diff.upstream || {}));
    this.down = new Map(Object.entries(this.diff.downstream || {}));
    this.hot = new Set((this.diff.hot_edges || []).map((h) => h.join("|")));
    this.newE = new Set((this.diff.new_edges || []).map((h) => h.join("|")));
    this.lines = this.diff.changed_lines || {};
    this.findingsAt = new Map();
    this.rollC = new Set();
    this.rollA = new Set();
    const mark = (set, id) => { let cur = id; while (cur) { set.add(cur); cur = (W.node(cur) || {}).parent; } };
    const isChg = (id) => this.changed.has(id) && this.changed.get(id) !== "contains";
    this.changed.forEach((how, id) => { if (how !== "contains" && W.node(id)) mark(this.rollC, id); });
    this.up.forEach((_, id) => W.node(id) && !isChg(id) && mark(this.rollA, id));
    this.down.forEach((_, id) => W.node(id) && !isChg(id) && mark(this.rollA, id));
    for (const f of this.review.findings || []) {
      const id = f.locked && f.module ? "module:" + f.module : W.innermost(f.file, f.line_start);
      f._at = id;
      let cur = id;
      while (cur) { if (!this.findingsAt.has(cur)) this.findingsAt.set(cur, []); this.findingsAt.get(cur).push(f); cur = (W.node(cur) || {}).parent; }
    }
    this.mode = { changed: true, affected: true };
  }
  // a copy that shows only what the reviewer switched on
  view(mode) { const v = Object.create(this); v.mode = mode; return v; }
  status(id) {
    if (this.mode.changed && this.rollC.has(id)) return "changed";
    if (this.mode.affected && this.rollA.has(id)) return "impacted";
    return null;
  }
  touched(id) { return this.rollC.has(id) || this.rollA.has(id); }
  isNew(id) { return this.changed.get(id) === "new"; }
  hotEdge(e) {
    const k = `${e.source}|${e.target}|${e.kind}`;
    if (this.mode.changed && (this.newE.has(k) || (this.changed.has(e.source) && this.changed.get(e.source) !== "contains"))) return true;
    return !!(this.mode.affected && this.hot.has(k));
  }
  findings(id) { return this.findingsAt.get(id) || []; }
  changedLine(file, ln) { return !!this.mode.changed && (this.lines[file] || []).some(([a, b]) => ln >= a && ln <= b); }
  unit(id) { return (this.notes && this.notes.units[id]) || null; }
  roll(id) { return (this.notes && this.notes.roll[id]) || null; }
  note(id) { return (this.notes && this.notes.notes[id]) || null; }
}
export const NO_OVERLAY = { status: () => null, touched: () => false, isNew: () => false, hotEdge: () => false, findings: () => [], changedLine: () => false,
  unit: () => null, roll: () => null, note: () => null, view() { return this; }, mode: {}, changed: new Map(), up: new Map(), down: new Map(), review: { findings: [] }, diff: {}, notes: null };

export const LEVEL = {
  verified: { label: "Verified by passing tests", short: "verified", icon: "✓", cls: "ok" },
  contradicted: { label: "Contradicted: a test failed or the reviewer found a problem", short: "contradicted", icon: "✕", cls: "bad" },
  not_run: { label: "Tests reach it but were not run", short: "not run", icon: "○", cls: "mute" },
  none: { label: "No test evidence (only the reviewer looked)", short: "no evidence", icon: "–", cls: "warn" },
};

export const VERDICT = {
  fix: { label: "Fix before merge", cls: "bad", who: "The Builder agent (or the test) must change, then review again." },
  check: { label: "Check needed", cls: "warn", who: "The named human checks the open items below." },
  ready: { label: "Ready to sign", cls: "ok", who: "Nothing open: the named human can sign." },
};
// Reviewer severities shown with the common defect scale (the engine's names map to Conventional Comments:
// Blocker = blocking, ShouldFix = non-blocking issue, Nit = nitpick)
export const SEV = {
  Blocker: { label: "Critical", cls: "bad", rank: 0, means: "must be fixed before merge" },
  ShouldFix: { label: "Major", cls: "warn", rank: 1, means: "a real problem; a human decides" },
  Nit: { label: "Minor", cls: "mute", rank: 2, means: "optional polish" },
};
export const sev = (s) => (SEV[s] || { label: s, cls: "mute", rank: 3, means: "" });
export const REVIEWER = { BLOCKED: "do not merge yet", NEEDS_HUMAN: "a human must check", READY_FOR_SIGNOFF: "ready for sign-off" };
export const pct = (x) => (x == null ? "?" : Math.round(x * 100));
export const range = (s) => (s && s.lo != null ? `${pct(s.lo)}–${pct(s.hi)}%` : "–");
export const conf = (s) => (s && s.conf != null ? `${pct(s.conf)}%` : "–");
export const basis = (s) => (s ? `${s.verified} of ${s.n} changed method${s.n === 1 ? "" : "s"} verified` : "");

// ---------------------------------------------------------------- personal view (A1-A3)
// Set from the server (/api/settings) or, without a server, from data/settings.json and this browser.
export const VIEW = { trust_view: "level", severity_min: "Nit", lenses: null, layout: "split", density: "comfortable", theme: "dark", language: "en", start: "list" };
export function setView(v) { Object.assign(VIEW, v || {}); TRUST.view = VIEW.trust_view === "percent" ? "percent" : "level"; }
// Severity filter: findings below the chosen level are folded, never deleted
export const shownSev = (s) => sev(s).rank <= sev(VIEW.severity_min || "Nit").rank;

// ---------------------------------------------------------------- trust level (A1)
export const TRUST = { view: "level" };
export function setTrustView(v) { TRUST.view = v === "percent" ? "percent" : "level"; VIEW.trust_view = TRUST.view; }
// Low / Medium / High from the same counted evidence as the percentage; no new weights.
//  Low    = a failing test or a Critical finding contradicts a changed method (or the PR is labelled "Fix before merge"),
//           or even the top of the 95% range says fewer than half the changed methods are verified
//  High   = every changed method is verified, nothing contradicts it, the 95% range stays above one half
//           (so at least 3 verified methods), for a whole PR nothing is open (label "Ready to sign"), and no area is "Not checked"
//  Medium = everything in between
export const LEVELS = {
  low: { label: "Low", cls: "bad" }, medium: { label: "Medium", cls: "warn" }, high: { label: "High", cls: "ok" },
};
export function trustLevel(s, label, notChecked) {
  if (!s || !s.n) return null;
  if (s.contradicted > 0) return { key: "low", why: `${s.contradicted} changed method${s.contradicted === 1 ? " is" : "s are"} contradicted by a failing test or a Critical finding` };
  if (label === "fix") return { key: "low", why: "the PR is labelled Fix before merge" };
  if (s.hi != null && s.hi < 0.5) return { key: "low", why: `only ${s.verified} of ${s.n} changed methods are verified; even the top of the 95% range is below one half` };
  if (s.verified >= 0.75 * s.n && s.lo != null && s.lo >= 0.5 && (!label || label === "ready")) {   // High: at least 3 in 4 changed methods verified
    if (notChecked && notChecked.length) return { key: "medium", why: `${s.verified} of ${s.n} changed methods are verified, but these areas were not checked: ${notChecked.join(", ")}` };
    return { key: "high", why: `${s.verified} of ${s.n} changed methods are verified by passing tests and nothing contradicts them` };
  }
  if (s.verified === s.n && s.lo != null && s.lo < 0.5) return { key: "medium", why: `all ${s.n} changed method${s.n === 1 ? " is" : "s are"} verified, but ${s.n === 1 ? "one method is" : "so few methods are"} too little evidence for High` };
  if (s.verified === s.n) return { key: "medium", why: "every change is verified, but the PR still has open items to check" };
  return { key: "medium", why: `${s.verified} of ${s.n} changed methods are verified; ${s.n - s.verified} have no test evidence yet` };
}
// what to print for a roll, in the chosen view
export function trustShow(s, label, notChecked) {
  const t = trustLevel(s, label, notChecked);
  if (!t) return null;
  const pctText = `${conf(s)} confidence, 95% range ${range(s)}`;
  if (TRUST.view === "percent") return { text: conf(s), word: "confidence", cls: LEVELS[t.key].cls, title: `${pctText}. Trust level: ${LEVELS[t.key].label} (${t.why}).`, why: t.why };
  return { text: LEVELS[t.key].label, word: "trust", cls: LEVELS[t.key].cls, title: `${t.why}. ${pctText}.`, why: t.why };
}
export const notCheckedAreas = (review) => ((review && review.areas) || []).filter((a) => a.status === "not_checked").map((a) => a.area);

// Requirement met (D2): from the three blind requirement agents, counted
export function reqSummary(review) {
  const rc = review && review.requirement_check;
  if (!rc || !rc.ran || !(rc.items || []).length) return null;
  const c = rc.counts, n = rc.items.length;
  const cls = c.contradicted ? "bad" : c.missing || c.partly || c.no_evidence ? "warn" : "ok";
  return { met: c.met, n, cls, text: `${c.met} of ${n} met`, counts: c };
}

// How many things in THIS PR each lens has to show
// ---------------------------------------------------------------- lens facts
// For one PR, what each lens can state as fact from the map and the diff: every item names real nodes and edges,
// so the count on the lens button, the lines on the map and the list in the panel are the same thing.
export function inPR(O) { return !!(O && O.changed && O.changed.size); }
export function lensFacts(W, O, lens) {
  const isTest = (id) => W.isTest(W.node(id));
  const st = (id) => (O.changed.get(id) === "new" ? "new" : O.changed.has(id) && O.changed.get(id) !== "contains" ? "changed" : O.touched(id) ? "affected" : null);
  const mod = (id) => (W.node(id) || {}).module || "";
  const nm = (id) => {
    const n = W.node(id); if (!n) return id;
    if (["method", "ctor", "property", "field", "column", "state"].includes(n.kind)) { const t = W.node(W.typeOf(id)); return (t ? t.name + "." : "") + displayName(n); }
    if (n.kind === "table") return n.name + " table";
    return displayName(n);
  };
  const where = (id, home) => (mod(id) && mod(id) !== home ? `${mod(id)} · ` : "");
  const isNewE = (e) => O.newE.has(`${e.source}|${e.target}|${e.kind}`);
  const fromChanged = (e) => O.changed.has(e.source) && O.changed.get(e.source) !== "contains";
  const facts = [];

  if (lens === "risk") {
    return (O.review.findings || []).map((f) => ({ id: f._at, title: f.title, sev: f.severity, status: "finding", lines: [`${f.file}:${f.line_start}`], links: [] }));
  }

  if (lens === "apis") {
    W.nodes.filter((n) => n.kind === "endpoint" && O.touched(n.id)).forEach((ep) => {
      const handler = ep.attrs.handler, home = ep.module;
      const status = st(ep.id) === "new" || st(handler) === "new" ? "new" : st(handler) || st(ep.id) || "affected";
      const links = [], lines = [], chain = new Set([ep.id]), q = [[ep.id, 0]];
      while (q.length) {   // the call path from the endpoint into the code this PR touched
        const [id, h] = q.shift(); if (h > 5) continue;
        W.outE(id).filter((e) => ["routes", "calls", "resolves"].includes(e.kind) && !isTest(e.target) && O.touched(e.target)).forEach((e) => {
          links.push([e.source, e.target, e.kind]);
          if (!chain.has(e.target)) { chain.add(e.target); q.push([e.target, h + 1]); }
        });
      }
      // what the endpoint runs, said once per method: changed code in its own module, then what it reaches elsewhere
      const isIface = (id) => ((W.node(W.typeOf(id)) || {}).attrs || {}).type_kind === "interface";
      const members = [...chain].filter((id) => id !== ep.id && id !== handler && ["method", "ctor"].includes((W.node(id) || {}).kind) && !isIface(id));
      members.filter((id) => mod(id) === home && st(id) !== "affected").forEach((id) => lines.push(`runs ${nm(id)} · ${st(id)}`));
      const quiet = members.filter((id) => mod(id) === home && st(id) === "affected").length;
      if (quiet) lines.push(`and ${quiet} unchanged method${quiet === 1 ? "" : "s"} in ${home}`);
      members.filter((id) => mod(id) !== home).forEach((id) => lines.push(`reaches ${mod(id)} · ${nm(id)} · ${st(id)}`));
      // other modules that use the same code the endpoint runs (directly or through its interface)
      const users = new Map();
      chain.forEach((id) => {
        if (mod(id) !== home) return;
        const targets = [id, ...W.inE(id).filter((e) => e.kind === "resolves").map((e) => e.source)];
        targets.forEach((t) => W.inE(t).filter((e) => e.kind === "calls" && !isTest(e.source) && mod(e.source) !== home && !chain.has(e.source)).forEach((e) => {
          users.set(e.source + ">" + t, [e.source, t]);
        }));
      });
      users.forEach(([u, t]) => { links.push([u, t, "uses"]); lines.push(`used by ${mod(u)} · ${nm(u)} → ${nm(t)}`); });
      const u = O.unit(handler), tests = u && u.tests;
      const auth = (ep.attrs.auth || []).join(", ");
      facts.push({ id: ep.id, title: ep.name, status, home,
        sub: `${handler ? nm(handler) : "no handler found"} · ${auth ? "auth: " + auth : "no authorization"}`,
        lines: lines.concat(tests && tests.passed_n + tests.failed_n + tests.broken_n ? [`tests on its handler: ${tests.passed_n} pass, ${tests.failed_n} fail${tests.broken_n ? ", " + tests.broken_n + " broken" : ""}`] : ["no test reaches its handler"]), links });
    });
    return facts.sort((a, b) => ["new", "changed", "affected"].indexOf(a.status) - ["new", "changed", "affected"].indexOf(b.status));
  }

  if (lens === "calls") {
    const bySrc = new Map();
    W.edges.filter((e) => ["calls", "resolves"].includes(e.kind) && !isTest(e.source) && !isTest(e.target) && (isNewE(e) || fromChanged(e))).forEach((e) => {
      if (!bySrc.has(e.source)) bySrc.set(e.source, []); bySrc.get(e.source).push(e);
    });
    bySrc.forEach((es, src) => facts.push({ id: src, title: nm(src), status: st(src), home: mod(src),
      sub: `${es.length} call${es.length === 1 ? "" : "s"}${es.some(isNewE) ? ` · ${es.filter(isNewE).length} new` : ""}`,
      lines: es.map((e) => `${e.kind === "resolves" ? "implemented by" : "→"} ${where(e.target, mod(src))}${nm(e.target)}${isNewE(e) ? " · new call" : ""}`),
      links: es.map((e) => [e.source, e.target, e.kind]) }));
    return facts;
  }

  if (lens === "events") {
    const evs = new Set();
    W.edges.filter((e) => e.kind === "publishes" && (isNewE(e) || fromChanged(e) || O.touched(e.target))).forEach((e) => evs.add(e.target));
    W.nodes.filter((n) => n.kind === "type" && n.attrs.is_event && O.touched(n.id)).forEach((n) => evs.add(n.id));
    evs.forEach((ev) => {
      const pubs = W.inE(ev).filter((e) => e.kind === "publishes" && !isTest(e.source));
      const subs = W.inE(ev).filter((e) => e.kind === "subscribes" && !isTest(e.source));
      facts.push({ id: ev, title: nm(ev), status: st(ev) || "affected", home: mod(ev), sub: `${pubs.length} publisher${pubs.length === 1 ? "" : "s"} · ${subs.length} handler${subs.length === 1 ? "" : "s"}`,
        lines: [...pubs.map((e) => `published by ${where(e.source, mod(ev))}${nm(e.source)}${isNewE(e) ? " · new" : ""}`),
                ...subs.map((e) => `handled by ${where(e.source, mod(ev))}${nm(e.source)}${isNewE(e) ? " · new" : ""}`)],
        links: [...pubs.map((e) => [e.source, ev, "publishes"]), ...subs.map((e) => [ev, e.source, "delivers"])] });
    });
    return facts;
  }

  if (lens === "data") {
    const byT = new Map();
    W.edges.filter((e) => ["reads", "writes"].includes(e.kind) && !isTest(e.source) && (isNewE(e) || O.touched(e.source))).forEach((e) => {
      if (!byT.has(e.target)) byT.set(e.target, []); byT.get(e.target).push(e);
    });
    W.nodes.filter((n) => (n.kind === "table" || n.kind === "column") && O.changed.has(n.id) && O.changed.get(n.id) !== "contains").forEach((n) => { if (!byT.has(n.id)) byT.set(n.id, []); });
    // settings and defaults this PR changed, with every piece of code that reads them ("uses" links)
    const sets = new Map();
    W.edges.filter((e) => e.kind === "uses" && !isTest(e.source) && O.changed.has(e.target) && O.changed.get(e.target) !== "contains").forEach((e) => {
      if (!sets.has(e.target)) sets.set(e.target, []); sets.get(e.target).push(e);
    });
    sets.forEach((es, t) => facts.push({ id: t, title: nm(t), status: st(t), home: mod(t), sub: `setting · read by ${es.length} place${es.length === 1 ? "" : "s"}`,
      lines: es.map((e) => `read by ${where(e.source, "")}${nm(e.source)}`), links: es.map((e) => [e.source, e.target, "uses"]) }));
    byT.forEach((es, t) => facts.push({ id: t, title: nm(t), status: st(t) || (es.some((e) => st(e.source) !== "affected") ? "changed" : "affected"), home: mod(t),
      sub: es.length ? `${es.filter((e) => e.kind === "writes").length} write · ${es.filter((e) => e.kind === "reads").length} read` : `${st(t)} ${(W.node(t) || {}).kind || "item"}`,
      lines: es.map((e) => `${e.kind === "writes" ? "written" : "read"} by ${where(e.source, "")}${nm(e.source)} · ${st(e.source)}${isNewE(e) ? " · new" : ""}`),
      links: es.map((e) => [e.source, e.target, e.kind]) }));
    return facts;
  }

  if (lens === "security") {
    W.nodes.filter((n) => n.kind === "endpoint" && O.touched(n.id)).forEach((ep) => {
      const auth = (ep.attrs.auth || []).join(", ");
      facts.push({ id: ep.id, title: ep.name, status: ep.attrs.protected ? st(ep.attrs.handler) || "affected" : "open", home: ep.module,
        sub: ep.attrs.protected ? `protected · ${auth}` : "no authorization on this endpoint", lines: [], links: [] });
    });
    const authCalls = W.edges.filter((e) => e.kind === "calls" && !isTest(e.source) && mod(e.target) === "Auth" && mod(e.source) !== "Auth" && (isNewE(e) || fromChanged(e)));
    authCalls.forEach((e) => facts.push({ id: e.source, title: nm(e.source), status: st(e.source), home: mod(e.source), sub: `checks access: ${nm(e.target)}${isNewE(e) ? " · new check" : ""}`, lines: [], links: [[e.source, e.target, "calls"]] }));
    W.nodes.filter((n) => (n.kind === "property" || n.kind === "column") && n.attrs.pii && O.touched(n.id) && !isTest(n.id)).forEach((n) =>
      facts.push({ id: n.id, title: nm(n.id), status: st(n.id), home: n.module, sub: "personal data", lines: [], links: [] }));
    (O.review.findings || []).filter((f) => /secur|safety|access|auth/i.test(f.dimension || "")).forEach((f) =>
      facts.push({ id: f._at, title: f.title, status: "finding", sev: f.severity, home: mod(f._at), sub: `reviewer · ${f.file}:${f.line_start}`, lines: [], links: [] }));
    return facts;
  }

  if (lens === "tests") {
    const res = new Map();   // test name -> result, from the notes
    Object.values((O.notes && O.notes.units) || {}).forEach((u) => {
      const t = u.tests || {};
      (t.passed || []).forEach((x) => res.set(x, "passed"));
      (t.failed || []).forEach((x) => res.set(x.name || x, "failed"));
      (t.broken || []).forEach((x) => res.set(x.name || x, "broken"));
    });
    W.nodes.filter((n) => W.isTest(n) && n.kind === "method" && O.changed.has(n.id) && O.changed.get(n.id) !== "contains").forEach((t) => {
      const reach = W.outE(t.id).filter((e) => e.kind === "calls" && !isTest(e.target)).map((e) => e.target);
      const r = res.get(t.name) || "not run";
      facts.push({ id: t.id, title: nm(t.id), status: r, home: t.module, sub: `${st(t.id)} test · ${r}`,
        lines: reach.slice(0, 6).map((x) => `calls ${where(x, "")}${nm(x)}`), links: reach.map((x) => [t.id, x, "tests"]) });
    });
    const order = { failed: 0, broken: 1, "not run": 2, passed: 3 };
    return facts.sort((a, b) => order[a.status] - order[b.status]);
  }
  return facts;
}

export function lensCounts(W, O) {
  const out = {};
  for (const k of Object.keys(LENSES)) out[k] = lensFacts(W, O, k).length;
  return out;
}

export const LENSES = {
  risk: { label: "Risk", key: "1" },
  calls: { label: "Calls", key: "2" },
  apis: { label: "APIs", key: "3" },
  events: { label: "Events", key: "4" },
  data: { label: "Data", key: "5" },
  security: { label: "Security", key: "6" },
  tests: { label: "Tests", key: "7" },
};

// Aggregate links for a lens; mapEnd(nodeId) -> group key or null
export function lensLinks(W, O, lens, mapEnd) {
  const agg = new Map();
  if (inPR(O) && lens !== "risk") {   // in a PR, a lens draws exactly its facts
    for (const f of lensFacts(W, O, lens)) for (const [a, b, kind] of f.links) {
      const A = mapEnd(a), B = mapEnd(b); if (!A || !B || A === B) continue;
      const k = A + ">" + B + ">" + kind, o = agg.get(k) || { a: A, b: B, kind, count: 0, hot: true };
      o.count += 1; agg.set(k, o);
    }
    return [...agg.values()];
  }
  const add = (a, b, kind, hot, w = 1) => {
    if (!a || !b || a === b) return;
    const k = a + ">" + b + ">" + kind;
    const o = agg.get(k) || { a, b, kind, count: 0, hot: false };
    o.count += w; o.hot = o.hot || hot; agg.set(k, o);
  };
  const hot = (e) => O.hotEdge(e);
  if (lens === "events") {
    const subs = new Map();
    W.edges.filter((e) => e.kind === "subscribes").forEach((e) => { if (!subs.has(e.target)) subs.set(e.target, []); subs.get(e.target).push(e.source); });
    const all = W.nodes.find((n) => n.kind === "type" && n.name === "IDomainEvent");
    W.edges.filter((e) => e.kind === "publishes").forEach((e) => {
      add(mapEnd(e.source), mapEnd(e.target), "publishes", hot(e));
      (subs.get(e.target) || []).concat(all ? subs.get(all.id) || [] : []).forEach((h) => add(mapEnd(e.target), mapEnd(h), "delivers", hot(e)));
    });
    return [...agg.values()];
  }
  if (lens === "tests") {
    W.edges.filter((e) => e.kind === "calls" && W.isTest(W.node(e.source)) && !W.isTest(W.node(e.target))).forEach((e) => add(mapEnd(e.source), mapEnd(e.target), "tests", hot(e)));
    return [...agg.values()];
  }
  if (lens === "apis") {
    const seen = new Set(), q = [];
    W.nodes.filter((n) => n.kind === "endpoint").forEach((n) => { seen.add(n.id); q.push([n.id, 0]); });
    while (q.length) {
      const [id, h] = q.shift(); if (h > 4) continue;
      W.outE(id).filter((e) => ["routes", "calls", "resolves"].includes(e.kind)).forEach((e) => {
        add(mapEnd(e.source), mapEnd(e.target), e.kind, hot(e));
        if (!seen.has(e.target)) { seen.add(e.target); q.push([e.target, h + 1]); }
      });
    }
    return [...agg.values()];
  }
  if (lens === "security") return [];
  const kinds = lens === "data" ? ["reads", "writes"] : ["calls", "resolves"];
  W.edges.filter((e) => kinds.includes(e.kind)).forEach((e) => { if (!W.isTest(W.node(e.source))) add(mapEnd(e.source), mapEnd(e.target), e.kind, hot(e)); });
  return [...agg.values()];
}
