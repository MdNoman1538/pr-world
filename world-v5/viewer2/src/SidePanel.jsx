import { displayName, sev } from "./model.js";

const OUT = { calls: "calls", resolves: "implemented by", injects: "needs (injected)", routes: "handled by", publishes: "publishes", subscribes: "listens to", reads: "reads", writes: "writes", triggers: "moves state to", transitions: "can go to", maps: "stored as", implements: "implements", inherits: "inherits", registers: "registers", uses: "uses the setting" };
const IN = { calls: "called by", resolves: "contract", injects: "injected into", routes: "reached from", publishes: "published by", subscribes: "handled by", reads: "read by", writes: "written by", triggers: "entered by", transitions: "comes from", maps: "mapped from", implements: "implemented by", inherits: "inherited by", registers: "registered by", uses: "used by" };

export function Finding({ f, on, onClick }) {
  return (
    <div className={`finding ${f.severity} ${on ? "on" : ""}`} onClick={onClick}>
      <b><span className={"sv " + sev(f.severity).cls} title={sev(f.severity).means}>{sev(f.severity).label}</span> {f.dimension ? <span className="dim">{f.dimension}</span> : null} {f.title}</b>{f.claim}
      <div className="loc">{f.id} · {f.file}:{f.line_start}{f.evidence_verified ? " · evidence verified" : ""}</div>
      {f.suggested_fix && <div className="note">Fix: {f.suggested_fix}</div>}
    </div>
  );
}

function Connections({ W, O, id, onOpen }) {
  const groups = new Map();
  const add = (label, other, e) => { if (!W.node(other)) return; if (!groups.has(label)) groups.set(label, new Map()); groups.get(label).set(other, e); };
  W.outE(id).forEach((e) => add(OUT[e.kind] || e.kind, e.target, e));
  W.inE(id).forEach((e) => add(IN[e.kind] || e.kind, e.source, e));
  return [...groups].map(([label, m]) => {
    const list = [...m], tests = list.filter(([o]) => W.isTest(W.node(o))), real = list.filter(([o]) => !W.isTest(W.node(o)));
    return (
      <div key={label}>
        <h4>{label} ({list.length})</h4>
        <div className="conn">
          {real.slice(0, 14).map(([o, e]) => {
            const n = W.node(o), st = O.status(o), p = W.node(n.parent);
            return (<a key={o} onClick={() => onOpen(o)} className={st ? "s-" + st : ""}>{e.certainty === "guess" ? "┄ " : ""}{displayName(n)}<em>{n.kind === "module" ? "" : n.module}{p && p.kind === "type" ? " · " + p.name : ""}{e.line ? " · L" + e.line : ""}</em></a>);
          })}
          {real.length > 14 && <span className="note">+{real.length - 14} more</span>}
          {tests.length > 0 && <span className="note">+ {tests.length} test(s)</span>}
        </div>
      </div>
    );
  });
}

// What the element is (not about the PR): meaning, facts, rules, access, connections
export function About({ W, O, id, meaning, onOpen }) {
  const n = W.node(id); if (!n) return null;
  const a = n.attrs, m = meaning[id];
  const stats = n.kind === "module" ? W.moduleStats(n.name) : null;
  return (
    <>
      {(m || a.summary) && <><h4>What it is for</h4><div className="meaning">{m ? m.summary : a.summary}<small>{m ? m.source : "doc comment in the code"}</small></div></>}
      {stats && <><h4>Facts</h4><div className="note">{stats.types} types · {stats.eps.length} APIs · {stats.methods} methods · {stats.tested} directly tested{stats.pii ? ` · ${stats.pii} personal-data fields` : ""}</div>{a.why && <div className="note">Rulebook: {a.why}</div>}</>}
      {n.kind === "module" && (W.w.constitutions || {})[n.name] && <><h4>Constitution</h4><pre className="const">{W.w.constitutions[n.name].replace(/\*\*/g, "")}</pre></>}
      {n.kind === "endpoint" && <><h4>Access</h4><div>{(a.auth || []).length ? a.auth.map((x) => <span key={x} className="chip c-api">{x}</span>) : <b className="bad">No authorization attribute</b>}</div></>}
      {a.signature && n.kind !== "module" && <><h4>Signature</h4><div className="mono small">{a.signature}</div></>}
      <Connections W={W} O={O} id={id} onOpen={onOpen} />
    </>
  );
}

export default function SidePanel({ W, O, id, meaning, pr, prInfo, focusF, onOpen, onFinding, onIssue, onCode }) {
  const n = id ? W.node(id) : null;
  if (!n) {
    if (!pr) return (
      <aside className="side">
        <h3>The bank, as a world</h3><div className="kind">Each block is a module</div>
        <p className="note">Height = how much is inside. Colour = risk from the team's rulebook. Arcs = connections in the chosen lens.</p>
        <p className="note"><b>Travel:</b> double-click or pinch in to open, Esc to go up, ⌘K to jump anywhere. Pick a PR at the top to see what it changed and what it touches. Drag the timeline at the bottom to watch the bank being built.</p>
      </aside>);
    const d = O.diff || {}, r = O.review || {};
    const ch = Object.entries(d.changed || {}).filter(([, v]) => v !== "contains");
    return (
      <aside className="side">
        <h3>{prInfo.id}: {prInfo.title}</h3>
        <div className="kind">Pull request · reviewer: <span className={"dec dec-" + r.decision}>{(r.decision || "n/a").replace(/_/g, " ")}</span> · tier {r.tier || "?"}</div>
        {r.ai_error && <div className="finding"><b>AI review did not run</b>{r.ai_error}</div>}
        <h4>At a glance</h4>
        <div className="glance"><div><b>{ch.length}</b>changed</div><div><b>{Object.keys(d.upstream || {}).length}</b>depend on it</div><div><b>{Object.keys(d.downstream || {}).length}</b>reached</div><div><b>{(d.untested_changed || []).length}</b>untested</div></div>
        <h4>Modules</h4>
        <div>{Object.entries(d.modules || {}).map(([m, s]) => <span key={m} className={"pill p-" + s} style={{ cursor: "pointer" }} onClick={() => onOpen("module:" + m)}>{m}: {s === "impacted" ? "affected" : s}</span>)}</div>
        <h4>Findings ({(r.findings || []).length})</h4>
        {(r.findings || []).map((f) => <Finding key={f.id} f={f} on={focusF === f.id} onClick={() => onFinding(f.id)} />)}
        {!(r.findings || []).length && <p className="note">No findings.</p>}
        <h4>Untested changes</h4>
        <div className="conn">{(d.untested_changed || []).map((x) => W.node(x) && <a key={x} onClick={() => onOpen(x)}>{displayName(W.node(x))}<em>{W.node(x).module}</em></a>)}</div>
        <h4>Builder</h4><div className="note">{prInfo.builder.source} · {prInfo.builder.attempts || 0} attempt(s){prInfo.builder.fallback ? " · fell back to reference code" : ""}</div>
        <h4>Tests (Test agent, blind to the code)</h4>
        <div className="note">{prInfo.tests && prInfo.tests.ran ? <>{prInfo.tests.passed} passed · <b className={prInfo.tests.failed ? "bad" : ""}>{prInfo.tests.failed} failed</b>{(prInfo.tests.failed_tests || []).map((t) => <div key={t}>✕ {t}</div>)}</> : (prInfo.tests && prInfo.tests.reason) || "not run"}</div>
        <h4>Requirement</h4><button className="ghost" onClick={onIssue}>Open the issue</button>
      </aside>);
  }
  const a = n.attrs, st = O.status(id), m = meaning[id];
  const fs = O.findings(id);
  const via = O.up.has(id) ? (O.diff.up_via || {})[id] : O.down.has(id) ? (O.diff.down_via || {})[id] : null;
  const stats = n.kind === "module" ? W.moduleStats(n.name) : null;
  return (
    <aside className="side">
      <h3>{displayName(n)}</h3>
      <div className="kind">{n.kind === "type" ? a.type_kind : n.kind}{n.kind !== "module" && n.module ? ` · ${n.module} / ${n.layer || ""}` : ""}</div>
      <div>
        <span className={"pill t-" + W.tier(n.module)}>{W.tier(n.module)} risk</span>
        {st && <span className={"pill p-" + st}>{O.isNew(id) ? "new" : st === "impacted" ? "affected" : st}</span>}
        {a.pii && <span className="pill p-pii">personal data</span>}
        {n.kind === "endpoint" && <span className={"pill " + (a.protected ? "p-ok" : "p-bad")}>{a.protected ? "protected" : "NOT protected"}</span>}
      </div>
      {(m || a.summary) && <><h4>What it is for</h4><div className="meaning">{m ? m.summary : a.summary}<small>{m ? m.source : "doc comment in the code"}</small></div></>}
      {stats && <><h4>Facts</h4><div className="note">{stats.types} types · {stats.eps.length} APIs · {stats.methods} methods · {stats.tested} directly tested{stats.pii ? ` · ${stats.pii} personal-data fields` : ""}{a.guarded ? " · guarded area" : ""}</div>{a.why && <div className="note">Rulebook: {a.why}</div>}</>}
      {n.kind === "module" && (W.w.constitutions || {})[n.name] && <><h4>Constitution</h4><pre className="const">{W.w.constitutions[n.name].replace(/\*\*/g, "")}</pre></>}
      {n.file && <><h4>Proof</h4><span className="proof" onClick={() => onCode(n.file, n.line)}>{n.file}:{n.line}</span></>}
      {n.kind === "endpoint" && <><h4>Access</h4><div>{(a.auth || []).length ? a.auth.map((x) => <span key={x} className="chip c-api">{x}</span>) : <b className="bad">No authorization attribute</b>}</div></>}
      {a.signature && n.kind !== "module" && <><h4>Signature</h4><div className="mono small">{a.signature}</div></>}
      {via && <><h4>Why it is affected</h4><div className="note">{O.up.has(id) ? "Depends on the change" : "Reached by the change"} — {O.up.get(id) || O.down.get(id)} hop(s), via <a className="lnk" onClick={() => onOpen(via[0])}>{displayName(W.node(via[0]))}</a> ({via[1]})</div></>}
      {fs.length > 0 && <><h4>Review findings ({fs.length})</h4>{fs.map((f) => <Finding key={f.id} f={f} on={focusF === f.id} onClick={() => onFinding(f.id)} />)}</>}
      <Connections W={W} O={O} id={id} onOpen={onOpen} />
    </aside>
  );
}
