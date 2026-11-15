// PR World v5: everything that talks to the server — personal settings, plugins and setup wizard, access,
// sign-off per module, merge policy, requirement check, inbox and the admin pages.
// Without the server (plain file viewer) the app still works: settings are kept in this browser only.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { VIEW, setView, LENSES, sev, VERDICT, trustShow, notCheckedAreas, reqSummary, LEVELS } from "./model.js";

export const API = { on: false, me: null };

export async function api(path, method = "GET", body) {
  const r = await fetch(path, { method, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-PRW": "1" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = "/login"; throw new Error("Sign in first."); }
  if (!r.ok) throw new Error(j.error || `${r.status}`);
  return j;
}

const local = { get: () => { try { return JSON.parse(localStorage.getItem("pw5.view") || "{}"); } catch { return {}; } },
  set: (v) => { try { localStorage.setItem("pw5.view", JSON.stringify(v)); } catch { /* private mode */ } } };

// Before the first screen: is there a server? Load the person's view settings either way.
export async function bootPlatform() {
  try {
    const r = await fetch("/api/me", { credentials: "same-origin" });
    if (r.status === 401) { location.href = "/login"; return; }
    if (r.ok) {
      API.on = true;
      API.me = await r.json();
      setView(await api("/api/settings"));
    }
  } catch { /* no server */ }
  if (!API.on) {
    let st = {};
    try { st = await (await fetch("data/settings.json")).json(); } catch { /* none */ }
    setView({ ...st, ...local.get() });
  }
  applyLook();
}

export function applyLook() {
  document.body.classList.toggle("light", VIEW.theme === "light");
  document.body.classList.toggle("compact", VIEW.density === "compact");
}

// ---------------------------------------------------------------------- A4 settings page
const SEVS = [["Blocker", "Critical only"], ["ShouldFix", "Critical and Major"], ["Nit", "Everything (Critical, Major, Minor)"]];
export function SettingsPage({ onSaved }) {
  const [v, setV] = useState({ ...VIEW, lenses: VIEW.lenses || Object.keys(LENSES) });
  const [msg, setMsg] = useState("");
  const set = (k, x) => setV((o) => ({ ...o, [k]: x }));
  const save = async () => {
    const out = { trust_view: v.trust_view, severity_min: v.severity_min, lenses: v.lenses, layout: v.layout, density: v.density, theme: v.theme, language: "en", start: v.start };
    try {
      if (API.on) setView(await api("/api/settings", "PUT", out));
      else { local.set(out); setView(out); }
      applyLook();
      setMsg("Saved.");
      onSaved && onSaved();
    } catch (e) { setMsg(e.message); }
  };
  const Row = ({ label, children, hint }) => <div className="setrow"><label>{label}</label><div>{children}{hint && <small className="note">{hint}</small>}</div></div>;
  const Pick = ({ k, opts }) => <div className="seg small">{opts.map(([val, lab]) => <button key={val} className={v[k] === val ? "on" : ""} onClick={() => set(k, val)}>{lab}</button>)}</div>;
  return (
    <div className="settings">
      <p className="note">Your own view. It changes what you see first, never what the reviewer checks: hidden items are folded, not deleted.
        {API.on ? " Saved for your account." : " Saved in this browser (no server)."}</p>
      <Row label="Trust shown as" hint="The level uses the same counts as the percentage. Trust details always show both.">
        <Pick k="trust_view" opts={[["level", "Low / Medium / High"], ["percent", "Percentage"]]} /></Row>
      <Row label="Findings shown" hint="The rest is folded under “Hidden by your filter”, with a count.">
        <Pick k="severity_min" opts={SEVS} /></Row>
      <Row label="Lenses in the bar">
        <div className="chips">{Object.entries(LENSES).map(([k, l]) => (
          <label key={k} className="chk"><input type="checkbox" checked={v.lenses.includes(k)} disabled={k === "risk"}
            onChange={(e) => set("lenses", e.target.checked ? [...v.lenses, k] : v.lenses.filter((x) => x !== k))} />{l.label}</label>))}</div></Row>
      <Row label="Layout"><Pick k="layout" opts={[["split", "Map and panel"], ["map", "Map only"], ["read", "Panel only"]]} /></Row>
      <Row label="Panel density"><Pick k="density" opts={[["comfortable", "Comfortable"], ["compact", "Compact"]]} /></Row>
      <Row label="Theme" hint="Light changes the panels and lists; the map keeps its dark ground so colours stay readable.">
        <Pick k="theme" opts={[["dark", "Dark"], ["light", "Light"]]} /></Row>
      <Row label="Start page"><Pick k="start" opts={[["list", "Pull requests"], ["world", "The whole bank"], ["feedback", "Latest PR feedback"]]} /></Row>
      <Row label="Language" hint="English only for now."><span>English</span></Row>
      <div className="acts"><button className="ghost on" onClick={save}>Save</button><span className="note">{msg}</span></div>
    </div>);
}

// ---------------------------------------------------------------------- C6 plugin page and setup wizard
const KIND = { specialist: "Specialist reviewers", agent: "Agents", sensor: "Code sensors (no AI)", lens: "Lenses", provider: "Model providers", integration: "Integrations" };
export function PluginsPage() {
  const [p, setP] = useState(null);
  const [err, setErr] = useState("");
  const [draft, setDraft] = useState(null);
  const [res, setRes] = useState(null);
  const [mdraft, setMdraft] = useState(null);
  const load = () => api("/api/plugins").then(setP).catch((e) => setErr(e.message));
  useEffect(() => { if (API.on) load(); }, []);
  const discard = () => { setDraft(null); setMdraft(null); setRes(null); };
  const [note, setNote] = useState(null);
  const saved = (r) => { setDraft(null); setMdraft(null); setRes(null); setNote(`Saved for the team and in use now. Fingerprint ${r.fingerprint}.${r.previous_kept_as ? ` Old file kept as ${r.previous_kept_as}.` : ""}`); load(); setTimeout(() => setNote(null), 8000); };
  if (!API.on) return <p className="note">The plugin page needs the PR World server (python -m prw_server). The coverage of each review is still shown on its PR.</p>;
  if (err) return <p className="bad">{err}</p>;
  if (!p) return <p className="note">Loading…</p>;
  const isAdmin = API.me && API.me.admin;
  const def = (p.coverage && p.coverage.default) || "essential";
  const onAt = new Set((p.levels[def] || p.levels.essential).plugins);
  const custom = (p.coverage && p.coverage.custom) || {};
  if (def === "custom") { (custom.enable || []).forEach((x) => onAt.add(x)); (custom.disable || []).forEach((x) => onAt.delete(x)); }
  const toggle = (id) => {
    const base = def === "custom" ? custom.base || "essential" : def;
    const baseOn = new Set(p.levels[base].plugins);
    const cur = new Set(draft ? draft.on : onAt);
    cur.has(id) ? cur.delete(id) : cur.add(id);
    const enable = [...cur].filter((x) => !baseOn.has(x)), disable = [...baseOn].filter((x) => !cur.has(x));
    const same = def === "custom" ? JSON.stringify([enable.sort(), disable.sort()]) === JSON.stringify([[...(custom.enable || [])].sort(), [...(custom.disable || [])].sort()]) : !enable.length && !disable.length;
    setDraft(same ? null : { base, on: [...cur], enable, disable });   // back to what is saved: nothing to save, the bar goes away
    setRes(null);
  };
  const shown = new Set(draft ? draft.on : onAt);
  const groups = {};
  p.plugins.forEach((x) => { (groups[x.kind] = groups[x.kind] || []).push(x); });
  const est = [...shown].reduce((a, id) => a + ((p.plugins.find((x) => x.id === id) || {}).cost_calls || 0), 0);
  return (
    <div className="plugins">
      <div className="glance big"><div><b>{p.levels.essential.estimate_calls}</b>calls per PR at Essential</div><div><b>{p.levels.full.estimate_calls}</b>calls per PR at Full</div>
        <div><b>{def}</b>team default</div><div><b>{Math.round(est * 10) / 10}</b>calls with the switches below</div></div>
      <p className="note">Team settings: {p.badge}</p>
      {p.problems.length > 0 && <p className="warn">{p.problems.join(" · ")}</p>}
      {p.warnings.length > 0 && <p className="warn">{p.warnings.join(" · ")}</p>}
      {note && <p className="okbar">✓ {note} <button className="ghost x" onClick={() => setNote(null)}>✕</button></p>}
      <Wizard p={p} isAdmin={isAdmin} />
      <ModelsSection p={p} isAdmin={isAdmin} m={mdraft} setM={(x) => { setMdraft(x); setRes(null); }} />
      {Object.entries(groups).map(([k, list]) => (
        <section key={k}><h4>{KIND[k] || k}</h4>
          <div className="cards">{list.map((x) => (
            <div key={x.id} className={"pcard " + (shown.has(x.id) ? "on" : "off")}>
              <div className="pch"><b>{x.name}</b>
                <label className="sw" title={isAdmin ? "Switch for the team (needs a named approver to save)" : "Only an admin can change team plugins"}>
                  <input type="checkbox" checked={shown.has(x.id)} disabled={!isAdmin} onChange={() => toggle(x.id)} /><i /></label></div>
              <div className="note">{x.checks}</div>
              <div className="pcm"><span>{x.cost_calls ? `${x.cost_calls} call${x.cost_calls === 1 ? "" : "s"} / PR` : "no AI calls"}</span>
                <span>{(x.levels || []).join(" · ") || "add-on"}</span><span>{x.source}{x.source === "company" ? (x.signed ? " · signed" : " · NOT signed") : ""}</span></div>
              {!shown.has(x.id) && x.loses && <div className="loses">Off: {x.loses}</div>}
            </div>))}</div>
        </section>))}
      {(draft || mdraft) && isAdmin && <SaveCoverage p={p} draft={draft} mdraft={mdraft} onDiscard={discard} onSaved={saved} />}
      <h4>Locked core (never a switch)</h4>
      <ul className="locked">{Object.entries(p.locked).map(([k, why]) => <li key={k}>{why}</li>)}</ul>
    </div>);
}

// ---------------------------------------------------------------------- models: one for everything, or one per section
const same = (a, b) => a && b && a.provider === b.provider && a.model === b.model;
function ModelPick({ v, onChange, providers, suggest, disabled }) {
  const sug = suggest[v.provider] || [];
  const custom = sug.length > 0 && !sug.includes(v.model);
  return (
    <span className="mpick">
      <select value={v.provider} disabled={disabled} onChange={(e) => { const pr = e.target.value; const s = suggest[pr] || []; onChange({ provider: pr, model: s[0] || (pr === "mock" ? "mock" : "") }); }}>
        {providers.map((x) => <option key={x.id} value={x.id}>{x.label}{x.note && x.id !== "gemini" ? ` · ${x.note}` : ""}</option>)}
      </select>
      {sug.length > 0 && v.provider !== "mock" ? (
        <select value={custom ? "__other" : v.model} disabled={disabled} onChange={(e) => onChange({ ...v, model: e.target.value === "__other" ? "" : e.target.value })}>
          {sug.map((x) => <option key={x} value={x}>{x}</option>)}<option value="__other">Other (type a name)…</option>
        </select>
      ) : v.provider === "mock" ? null : null}
      {(custom || sug.length === 0) && v.provider !== "mock" && <input placeholder="model name" value={v.model} disabled={disabled} onChange={(e) => onChange({ ...v, model: e.target.value })} />}
    </span>);
}

function modelInitial(p) {
  const M = p.models, list = M.role_list.filter((r) => r.key !== "panel");
  const eff = (k) => (M.roles[k] && k !== "panel" ? M.roles[k] : M.default);
  return { mode: list.every((r) => same(eff(r.key), eff(list[0].key))) ? "one" : "each", one: eff(list[0].key),
    each: Object.fromEntries(list.map((r) => [r.key, eff(r.key)])), panel: M.roles.panel || [], def: M.default };
}
const mname = (v) => (v ? `${v.provider} / ${v.model || "?"}` : "none");
function ModelsSection({ p, isAdmin, m, setM }) {
  const M = p.models, list = M.role_list.filter((r) => r.key !== "panel");
  const initial = modelInitial(p);
  const cur = m || initial;
  const upd = (patch) => { const n = { ...cur, ...patch }; setM(JSON.stringify(n) === JSON.stringify(initial) ? null : n); };
  const mp = (v, f, extra = {}) => <ModelPick v={v} onChange={f} providers={M.providers} suggest={M.suggest} disabled={!isAdmin} {...extra} />;
  const panel = cur.panel;
  return (
    <section className="models"><h4>AI models</h4>
      <p className="note">The AI is used in {list.length + 1} places only. Pick one model for all of them, or a different one for each place. Only Gemini is connected for now; the other providers are listed so the choice is ready when their key is added.</p>
      <div className="seg small">
        <button className={cur.mode === "one" ? "on" : ""} disabled={!isAdmin} onClick={() => upd({ mode: "one" })}>One model for everything</button>
        <button className={cur.mode === "each" ? "on" : ""} disabled={!isAdmin} onClick={() => upd({ mode: "each", each: Object.fromEntries(list.map((r) => [r.key, cur.mode === "one" ? cur.one : cur.each[r.key]])) })}>A model for each place</button>
      </div>
      {cur.mode === "one" ? (
        <div className="mrow"><div><b>Every place below</b><small className="note">Specialists, validator, investigator, requirement check, radar, fixes, summaries and policy drafts.</small></div>{mp(cur.one, (v) => upd({ one: v }))}</div>
      ) : list.map((r) => (
        <div className="mrow" key={r.key}><div><b>{r.label}</b><small className="note">{r.where}</small></div>{mp(cur.each[r.key], (v) => upd({ each: { ...cur.each, [r.key]: v } }))}</div>))}
      <div className="mrow"><div><b>Second-opinion panel</b><small className="note">{M.role_list.find((r) => r.key === "panel").where} Several different models on purpose, so it is kept apart from the choice above.</small></div>
        <div className="mpanel">{panel.map((v, i) => (
          <div key={i} className="mpi">{mp(v, (x) => upd({ panel: panel.map((y, j) => (j === i ? x : y)) }))}
            {isAdmin && panel.length > 2 && <button className="ghost x" aria-label="Remove this model" onClick={() => upd({ panel: panel.filter((_, j) => j !== i) })}>✕</button>}</div>))}
          {isAdmin && panel.length < 5 && panel.length >= 2 && <button className="ghost" onClick={() => upd({ panel: [...panel, panel[panel.length - 1] || M.default] })}>+ Add a model</button>}
          {panel.length < 2 && <small className="note">No panel set: validator only.</small>}</div></div>
      {!isAdmin && <small className="note">Only an admin can change models for the team.</small>}
    </section>);
}

function SaveCoverage({ p, draft, mdraft, onDiscard, onSaved }) {
  const [open, setOpen] = useState(false);
  const [res, setRes] = useState(null);       // the automatic check of the change
  const [busy, setBusy] = useState(false);
  const me = ((API.me && API.me.name) || "admin").replace(/\s*\(.*\)\s*$/, "");
  const name = (id) => (p.plugins.find((x) => x.id === id) || {}).name || id;
  const calls = (ids) => Math.round([...ids].reduce((a, id) => a + ((p.plugins.find((x) => x.id === id) || {}).cost_calls || 0), 0) * 10) / 10;
  // what the person is changing, in plain words
  const changes = [];
  let before = null, after = null;
  if (draft) {
    const def = (p.coverage && p.coverage.default) || "essential", custom = (p.coverage && p.coverage.custom) || {};
    const onAt = new Set((p.levels[def] || p.levels.essential).plugins);
    if (def === "custom") { (custom.enable || []).forEach((x) => onAt.add(x)); (custom.disable || []).forEach((x) => onAt.delete(x)); }
    const now = new Set(draft.on);
    [...now].filter((x) => !onAt.has(x)).forEach((x) => changes.push(["on", name(x)]));
    [...onAt].filter((x) => !now.has(x)).forEach((x) => changes.push(["off", name(x)]));
    before = calls(onAt); after = calls(now);
  }
  if (mdraft) {
    const ini = modelInitial(p), lab = Object.fromEntries(p.models.role_list.map((r) => [r.key, r.label]));
    Object.keys(mdraft.each).forEach((k) => {
      const a = ini.each[k], b = mdraft.mode === "one" ? mdraft.one : mdraft.each[k];
      if (!same(a, b)) changes.push(["model", `${lab[k]}: ${mname(a)} → ${mname(b)}`]);
    });
    if (JSON.stringify(ini.panel) !== JSON.stringify(mdraft.panel)) changes.push(["model", `Second-opinion panel: ${ini.panel.map(mname).join(", ") || "none"} → ${mdraft.panel.map(mname).join(", ") || "none"}`]);
  }
  const build = (save) => {
    const raw = JSON.parse(JSON.stringify(base.current));
    if (draft) raw.coverage = { ...(raw.coverage || {}), default: "custom", custom: { base: draft.base, enable: draft.enable, disable: draft.disable } };
    if (mdraft) {
      const one = mdraft.mode === "one", roles = {};
      Object.keys(mdraft.each).forEach((k) => { roles[k] = one ? mdraft.one : mdraft.each[k]; });   // written out in full, so a preset cannot override a choice
      if (mdraft.panel.length >= 2) roles.panel = mdraft.panel;
      raw.models = { ...(raw.models || {}), default: one ? mdraft.one : mdraft.def, roles };
    }
    if (save) { raw.approved_by = me; raw.approved_on = new Date().toISOString().slice(0, 10); }
    return raw;
  };
  const base = useRef(null);
  const review = async () => {
    setOpen(true); setRes(null);
    try {
      const cur = await api("/api/admin/settings");
      base.current = cur.raw || { version: "1", preset: "balanced" };
      setRes(await api("/api/admin/settings/check", "POST", { yaml: JSON.stringify(build(false)), save: false }));
    } catch (e) { setRes({ ok: false, problems: [e.message] }); }
  };
  const accept = async () => {
    setBusy(true);
    try {
      const r = await api("/api/admin/settings/check", "POST", { yaml: JSON.stringify(build(true)), save: true });
      if (r.ok) { setOpen(false); onSaved(r); } else setRes(r);
    } catch (e) { setRes({ ok: false, problems: [e.message] }); }
    setBusy(false);
  };
  const decline = () => { setOpen(false); onDiscard(); };
  const sum = changes.length ? `${changes.length} change${changes.length === 1 ? "" : "s"} not saved yet` : "Changes not saved yet";
  return (
    <>
      <div className="savebar">
        <b>{sum}</b>
        <div className="acts"><button className="ghost on" onClick={review}>Review and save</button><button className="ghost" onClick={onDiscard}>Discard</button></div>
      </div>
      {open && createPortal(
        <div className="confirm-back" onClick={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div className="confirm" role="dialog" aria-label="Review your changes">
            <h3>Save these changes for the team?</h3>
            <h4>What changes</h4>
            <ul className="chg">{changes.map(([k, t], i) => <li key={i}><span className={"tag " + k}>{k === "on" ? "Switched on" : k === "off" ? "Switched off" : "Model"}</span> {t}</li>)}</ul>
            <h4>What it means</h4>
            <ul className="chg">
              {before != null && <li>Calls per PR with these switches: <b>{before}</b> → <b>{after}</b>{after > before ? " (more checks, slower and dearer)" : after < before ? " (fewer checks, faster and cheaper)" : ""}.</li>}
              {changes.filter((c) => c[0] === "off").map(([, t], i) => { const x = p.plugins.find((y) => y.name === t); return x && x.loses ? <li key={i} className="warn">Without {t}: {x.loses}</li> : null; })}
              {mdraft && <li>Applies to the next review that runs. Reviews already done are not changed.</li>}
              {!res && <li className="note">Checking…</li>}
              {res && res.ok && (res.warnings || []).filter((w) => !/not approved|builder/.test(w)).map((w, i) => <li key={i} className="warn">{w}</li>)}
              {res && !res.ok && (res.problems || []).map((w, i) => <li key={i} className="bad">{w}</li>)}
            </ul>
            <p className="note">Saved as {me}. The old settings file is kept, and the change goes in the audit log.</p>
            <div className="acts end"><button className="ghost" onClick={decline}>Decline</button>
              <button className="ghost on" disabled={busy || !res || !res.ok} onClick={accept}>{busy ? "Saving…" : "Accept"}</button></div>
          </div>
        </div>, document.body)}
    </>);
}

const WIZ = [["regulated", "Regulated (bank, health, insurance)", "Full coverage on high and medium risk, a panel of different models on Critical findings, signed plugins only, names of restricted modules hidden."],
  ["business", "Business app", "Essential coverage, Full on high-risk areas. The Plugins page shows the calls per PR."],
  ["small", "Small project", "Fewest calls: correctness and security reviewers, the validator, build and tests."]];
function Wizard({ p, isAdmin }) {
  const [pick, setPick] = useState(null);
  const [who, setWho] = useState("");
  const [res, setRes] = useState(null);
  const preset = pick && p.wizard[pick];
  const info = preset && p.presets.find((x) => x.name === preset);
  const save = async () => {
    try { setRes(await api("/api/admin/settings/check", "POST", { yaml: JSON.stringify({ version: "1", preset, approved_by: who, approved_on: new Date().toISOString().slice(0, 10) }), save: true })); }
    catch (e) { setRes({ ok: false, problems: [e.message] }); }
  };
  return (
    <details className="wizard"><summary>Set-up wizard: what kind of project is this?</summary>
      <div className="cards">{WIZ.map(([k, t, d]) => <div key={k} className={"pcard click " + (pick === k ? "on" : "")} onClick={() => { setPick(k); setRes(null); }}><b>{t}</b><div className="note">{d}</div></div>)}</div>
      {info && <div className="note">Preset <b>{info.name}</b>: {info.about} · coverage default {info.coverage.default}, high risk {(info.coverage.by_tier || {}).high || info.coverage.default} · budget {info.budget.max_calls} calls / {info.budget.max_cost_eur} EUR per PR.</div>}
      {info && isAdmin && <div className="acts"><input placeholder="Approved by (full name)" value={who} onChange={(e) => setWho(e.target.value)} />
        <button className="ghost on" disabled={who.trim().length < 3} onClick={save}>Use this preset for the team</button></div>}
      {info && !isAdmin && <p className="note">Ask an admin to apply it.</p>}
      {res && (res.ok ? <p className="ok">Saved (fingerprint {res.fingerprint}).</p> : <p className="bad">{(res.problems || []).join(" · ")}</p>)}
    </details>);
}

// ---------------------------------------------------------------------- E4/E5/E10 a module you cannot open
export function AccessCard({ name, node, onDone }) {
  const [lv, setLv] = useState("read");
  const [why, setWhy] = useState("");
  const [hours, setHours] = useState(1);
  const [msg, setMsg] = useState("");
  const [emerg, setEmerg] = useState(false);
  const req = async () => { try { await api("/api/access-requests", "POST", { module: name, level: lv, reason: why }); setMsg("Request sent. The module owner decides; you will see the answer in your inbox."); onDone && onDone(); } catch (e) { setMsg(e.message); } };
  const em = async () => { try { const r = await api("/api/emergency", "POST", { module: name, reason: why, hours }); setMsg(`Open until ${r.until.slice(11, 16)} UTC. ${r.told.length ? "Told: " + r.told.join(", ") : "Admins were told."} Reload the page to see inside.`); } catch (e) { setMsg(e.message); } };
  return (
    <div className="access">
      <p className="lead">You can see that <b>{name}</b> exists, its risk colour, and whether this PR changes or affects it. You cannot open it.</p>
      <p className="note">Your access: {(node && node.attrs.level) || "overview"}. Findings in it are counted, without their text.</p>
      {API.on ? (<>
        <div className="seg small">{[["read", "Read"], ["review", "Review"], ["sign", "Sign"]].map(([k, l]) => <button key={k} className={lv === k ? "on" : ""} onClick={() => setLv(k)}>{l}</button>)}</div>
        <textarea placeholder="Why you need it (the owner reads this)" value={why} onChange={(e) => setWhy(e.target.value)} />
        <div className="acts"><button className="ghost on" onClick={req} disabled={why.trim().length < 5}>Request access</button>
          <button className="ghost" onClick={() => setEmerg((x) => !x)}>Emergency access…</button></div>
        {emerg && <div className="emerg"><p className="warn">Opens Read access at once, for a few hours. The owner and the admins are told immediately and it is logged.</p>
          <label>Hours <input type="number" min={1} max={24} value={hours} onChange={(e) => setHours(+e.target.value)} /></label>
          <button className="ghost" onClick={em} disabled={why.trim().length < 10}>Open now, with this reason</button></div>}
        {msg && <p className="note">{msg}</p>}
      </>) : <p className="note">Ask the module owner for access.</p>}
    </div>);
}

// ---------------------------------------------------------------------- E7 safe version banner
export function CutBanner({ O }) {
  const cut = (O.notes && O.notes.cut) || (O.review && O.review.cut) || (O.diff && O.diff.cut);
  if (!cut || !cut.locked_modules || !cut.locked_modules.length) return null;
  const n = (O.review.findings || []).filter((f) => f.locked).length;
  return <div className="cut">Safe version: you cannot open {cut.locked_modules.join(", ")}. {n ? `${n} finding${n === 1 ? " is" : "s are"} in those modules (severity shown, details hidden). ` : ""}Ask the owner for access.</div>;
}

// ---------------------------------------------------------------------- D2 requirement check
const RQ = { met: ["Met", "ok"], partly: ["Partly met", "warn"], missing: ["Missing", "bad"], contradicted: ["Contradicted", "bad"], unclear: ["Unclear", "mute"], no_evidence: ["No proof", "warn"] };
export function Requirement({ pr, review, onCode }) {
  const rc = review && review.requirement_check;
  const s = reqSummary(review);
  return (
    <div className="reqc">
      {s ? <>
        <div className={"rqhead " + s.cls}><b>Requirement met: {s.text}</b>
          <small>{["partly", "missing", "contradicted", "no_evidence", "unclear"].filter((k) => s.counts[k]).map((k) => `${s.counts[k]} ${RQ[k][0].toLowerCase()}`).join(" · ")}</small></div>
        <p className="note">Three agents, blind to each other: the analyst read only the requirement, the interpreter read only the code, the judge matched them. A “met” needs code that the evidence check found at the cited line.</p>
        {rc.items.map((it) => (
          <div key={it.id} className="rqi">
            <div className="rqt"><span className={"sv " + RQ[it.status][1]}>{RQ[it.status][0]}</span><b>{it.id}</b> {it.text}</div>
            {it.reason && <div className="note">{it.reason}</div>}
            {(it.proof || []).map((p) => <div key={p.id} className="rqp">{p.locked ? <span className="mute">{p.text}</span> :
              <a onClick={() => onCode(p.file, p.line)}>{p.file.split("/").pop()}:{p.line}</a>}{!p.locked && <span className={p.grounded ? "ok" : "warn"}> {p.grounded ? "proof found in the code" : "quote not found in the code"}</span>}{p.text && !p.locked && <small> · {p.text}</small>}</div>)}
          </div>))}
        {(rc.extra_behaviours || []).length > 0 && <><h4>Changes no requirement asked for</h4>{rc.extra_behaviours.map((b, i) => <div key={i} className="note">{typeof b === "string" ? b : b.text}</div>)}</>}
      </> : <p className="note">{rc && !rc.ran ? `Requirement check not run: ${rc.reason || "switched off"}.` : "This review has no requirement check (older review, or the plugin is off). The requirement text is below."}</p>}
      <h4>Requirement text</h4>
      <pre className="const">{pr.issue}</pre>
    </div>);
}

// ---------------------------------------------------------------------- trust in two parts (D2)
export function TwoPartTrust({ O, compact }) {
  const v = O.notes && O.notes.verdict, s = O.notes && O.notes.roll && (O.notes.roll.pr || {}).changed;
  const t = s ? trustShow(s, v && v.label, notCheckedAreas(O.review)) : null;
  const rq = reqSummary(O.review);
  if (!t && !rq) return null;
  return (
    <span className={"two " + (compact ? "compact" : "")}>
      {t && <span title={t.title}>Changed code: <b className={t.cls}>{t.text}</b></span>}
      <span title="From the requirement analyst, change interpreter and judge">Requirement: {rq ? <b className={rq.cls}>{rq.text}</b> : <b className="mute">not checked</b>}</span>
    </span>);
}

// ---------------------------------------------------------------------- C5 / B7 not checked and settings badge
export function Coverage({ review }) {
  const nc = (review && review.not_checked_plugins) || [];
  const areas = notCheckedAreas(review);
  const st = review && review.settings;
  return (
    <div className="covg">
      {(areas.length > 0 || nc.length > 0) && <details className="more"><summary className="warn">Not checked: {areas.join(", ") || `${nc.length} check(s)`}</summary>
        <p className="note">Switched off or not run. Never counted as passed; a PR with a not-checked area cannot reach High trust.</p>
        {nc.map((x, i) => <div key={i} className="note">{x.plugin} · {x.area} · {x.reason}</div>)}</details>}
      <div className="badge" title={st ? `Settings fingerprint ${st.fingerprint}` : ""}>Review settings: {st ? st.badge : "not recorded (review made before v5)"}
        {review && review.cost && review.cost.calls != null ? ` · ${review.cost.calls} model calls${review.cost.cost_eur ? `, ${review.cost.cost_eur} EUR` : ""}` : ""}
        {` · your view: ${VIEW.severity_min === "Nit" ? "all findings" : sev(VIEW.severity_min).label + " and above"}, trust as ${VIEW.trust_view === "percent" ? "percentage" : "level"}`}</div>
    </div>);
}

// ---------------------------------------------------------------------- E8 sign-off per module + F1 merge policy
export function SignOff({ pr, O, onChange }) {
  const [st, setSt] = useState(null);
  const [mp, setMp] = useState(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => { api(`/api/prs/${pr.id}/signoff`).then(setSt).catch((e) => setMsg(e.message)); api(`/api/prs/${pr.id}/merge`).then(setMp).catch(() => {}); };
  useEffect(() => { if (API.on) load(); }, [pr.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!API.on) return <p className="note">A named human signs. With the PR World server, each module owner signs their part here.</p>;
  if (!st) return <p className="note">{msg || "Loading sign-off…"}</p>;
  const label = O.notes && O.notes.verdict && O.notes.verdict.label;
  const act = async (path, body) => { setMsg(""); try { setSt(await api(path, "POST", body)); setNote(""); onChange && onChange(); } catch (e) { setMsg(e.message); } };
  const byPolicy = async () => { try { const r = await api(`/api/prs/${pr.id}/merge`, "POST", {}); setMsg(r.note); load(); } catch (e) { setMsg(e.message); } };
  return (
    <div className="signoff">
      <div className={"sohead " + (st.ready ? "ok" : "warn")}><b>{st.ready ? "Ready: every changed module is signed" : `Signed ${st.parts.filter((p) => p.signed).length} of ${st.parts.length} module parts`}</b>
        <small>for commit {st.head.slice(0, 8)} · the AI never approves</small></div>
      {st.parts.some((p) => p.can_sign && !p.signed) && <textarea placeholder={label === "fix" ? "This PR is labelled Fix before merge: write the risk you accept (required to sign)" : "Note with your signature (optional)"} value={note} onChange={(e) => setNote(e.target.value)} />}
      {st.parts.map((p) => (
        <div key={p.module} className="sop">
          <span className={p.signed ? "ok" : "mute"}>{p.signed ? "✓" : "○"}</span><b>{p.module}</b>
          <span className="note">{p.signed ? p.by.map((b) => `${b.user} ${b.at.slice(0, 16).replace("T", " ")}${b.note ? ` — “${b.note}”` : ""}`).join("; ") : p.can_sign ? "you can sign" : "waiting for the owner"}
            {p.tampered ? <b className="bad"> · {p.tampered} signature record changed after signing</b> : ""}{p.older_commits ? ` · ${p.older_commits} signature(s) on an older commit` : ""}</span>
          {p.can_sign && !p.signed && <button className="ghost small" onClick={() => act(`/api/prs/${pr.id}/sign`, { module: p.module, note })}>Sign</button>}
          {p.signed && p.by.some((b) => b.user === (API.me || {}).id) && <button className="ghost small" onClick={() => act(`/api/prs/${pr.id}/withdraw`, { module: p.module })}>Withdraw</button>}
        </div>))}
      {st.merge_by_policy.length > 0 && st.merge_by_policy.map((m, i) => <p key={i} className="ok">Merge allowed by policy: {m.note}</p>)}
      {mp && mp.checks.length > 0 && (
        <details className="more"><summary>Merge by signed policy: {mp.allowed ? <b className="ok">allowed by “{mp.rule.rule}” (signed by {mp.rule.signed_by})</b> : <b className="mute">not allowed for this PR</b>}</summary>
          {mp.checks.map((c) => <div key={c.rule} className="note"><b>{c.rule}</b> (signed by {c.signed_by}): {c.ok ? "all conditions met" : c.why_not.join("; ")}</div>)}
          {mp.allowed && !st.merge_by_policy.length && <button className="ghost small" onClick={byPolicy}>Record merge by this policy</button>}
        </details>)}
      {msg && <p className="note">{msg}</p>}
    </div>);
}

// ---------------------------------------------------------------------- finding feedback (Review level)
export function Judge({ pr, fid }) {
  const [done, setDone] = useState("");
  if (!API.on || !fid) return null;
  const send = async (verdict) => { try { await api(`/api/prs/${pr.id}/feedback`, "POST", { finding: fid, verdict }); setDone(verdict === "accepted" ? "Marked right" : "Marked wrong"); } catch (e) { setDone(e.message); } };
  return <div className="judge">{done ? <span className="note">{done}</span> : <>Is this finding right? <button className="ghost small" onClick={() => send("accepted")}>Right</button><button className="ghost small" onClick={() => send("rejected")}>Wrong</button></>}</div>;
}

// ---------------------------------------------------------------------- inbox
export function Inbox({ onRead }) {
  const [items, setItems] = useState(null);
  useEffect(() => { api("/api/inbox").then((r) => { setItems(r.items); api("/api/inbox/read", "POST", {}).then(() => onRead && onRead()); }).catch(() => setItems([])); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!items) return <p className="note">Loading…</p>;
  if (!items.length) return <p className="note">Nothing yet.</p>;
  return <div className="inbox">{items.map((i) => <div key={i.id} className={"ibx " + (i.read_at ? "" : "new") + " " + i.kind}><small>{i.at.slice(0, 16).replace("T", " ")} · {i.kind}</small>{i.text}</div>)}</div>;
}

// ---------------------------------------------------------------------- E6 admin pages
const LV = ["", "overview", "read", "review", "sign"];
export function AdminPage() {
  const [tab, setTab] = useState("people");
  const tabs = [["people", "People"], ["roles", "Roles"], ["grants", "Grants"], ["owners", "Owners"], ["requests", "Requests"], ["audit", "Audit log"], ["team", "Team settings"]];
  return (
    <div className="admin">
      <div className="seg small">{tabs.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === "people" && <People />}{tab === "roles" && <Roles />}{tab === "grants" && <Grants />}{tab === "owners" && <Owners />}
      {tab === "requests" && <Requests />}{tab === "audit" && <Audit />}{tab === "team" && <Team />}
    </div>);
}
function useLoad(path) {
  const [d, setD] = useState(null), [e, setE] = useState("");
  const load = () => api(path).then(setD).catch((x) => setE(x.message));
  useEffect(() => { load(); }, [path]); // eslint-disable-line react-hooks/exhaustive-deps
  return [d, e, load];
}
function People() {
  const [d, e, load] = useLoad("/api/admin/users");
  const [r] = useLoad("/api/admin/roles");
  const [nu, setNu] = useState({ id: "", name: "", roles: [] });
  const [msg, setMsg] = useState("");
  if (e) return <p className="bad">{e}</p>;
  if (!d || !r) return <p className="note">Loading…</p>;
  const roles = r.roles.map((x) => x.name);
  const setRoles = async (u, list) => { try { await api(`/api/admin/users/${encodeURIComponent(u)}/roles`, "PUT", { roles: list }); load(); } catch (x) { setMsg(x.message); } };
  const add = async () => { try { const x = await api("/api/admin/users", "POST", nu); setMsg(x.temporary_password ? `Created. Temporary password (shown once): ${x.temporary_password}` : "Created."); setNu({ id: "", name: "", roles: [] }); load(); } catch (x) { setMsg(x.message); } };
  const off = async (u, v) => { try { await api(`/api/admin/users/${encodeURIComponent(u)}/disable`, "POST", { disabled: v }); load(); } catch (x) { setMsg(x.message); } };
  return (<>
    <table className="vars"><thead><tr><th>Person</th><th>Roles</th><th>Owns</th><th>Grants</th><th></th></tr></thead><tbody>
      {d.users.map((u) => (<tr key={u.id} className={u.disabled ? "mute" : ""}><td><b>{u.name}</b><br /><small className="note">{u.id} · {u.source}</small></td>
        <td>{roles.map((x) => <label key={x} className="chk"><input type="checkbox" checked={u.roles.includes(x)} onChange={(ev) => setRoles(u.id, ev.target.checked ? [...u.roles, x] : u.roles.filter((y) => y !== x))} />{x}</label>)}</td>
        <td>{u.owns.join(", ") || "—"}</td><td>{u.grants.map((g) => <div key={g.id} className="note">{g.module}: {g.level}{g.until ? ` until ${g.until.slice(0, 16).replace("T", " ")}` : ""}{g.kind === "emergency" ? " (emergency)" : ""}</div>)}</td>
        <td><button className="ghost small" onClick={() => off(u.id, !u.disabled)}>{u.disabled ? "Switch on" : "Switch off"}</button></td></tr>))}
    </tbody></table>
    <h4>Add a local user</h4>
    <div className="acts"><input placeholder="user name" value={nu.id} onChange={(ev) => setNu({ ...nu, id: ev.target.value })} /><input placeholder="full name" value={nu.name} onChange={(ev) => setNu({ ...nu, name: ev.target.value })} />
      {roles.map((x) => <label key={x} className="chk"><input type="checkbox" checked={nu.roles.includes(x)} onChange={(ev) => setNu({ ...nu, roles: ev.target.checked ? [...nu.roles, x] : nu.roles.filter((y) => y !== x) })} />{x}</label>)}
      <button className="ghost on" onClick={add} disabled={!nu.id}>Add</button></div>
    {msg && <p className="note">{msg}</p>}
  </>);
}
function Roles() {
  const [d, e, load] = useLoad("/api/admin/roles");
  const [edit, setEdit] = useState(null);
  const [msg, setMsg] = useState("");
  if (e) return <p className="bad">{e}</p>;
  if (!d) return <p className="note">Loading…</p>;
  const mods = ["*", ...d.modules];
  const save = async () => { try { const m = Object.fromEntries(Object.entries(edit.modules).filter(([, v]) => v)); await api(`/api/admin/roles/${encodeURIComponent(edit.name)}`, "PUT", { ...edit, modules: m }); setEdit(null); setMsg("Saved."); load(); } catch (x) { setMsg(x.message); } };
  return (<>
    <p className="note">A role gives a level per module (* = every module). Admin manages access; it opens no code by itself.</p>
    <table className="vars"><thead><tr><th>Role</th>{mods.map((m) => <th key={m}>{m}</th>)}<th>People</th><th></th></tr></thead><tbody>
      {d.roles.map((r) => (<tr key={r.name}><td><b>{r.name}</b>{r.admin ? <em className="pill p-api">admin</em> : null}<br /><small className="note">{r.description}</small></td>
        {mods.map((m) => <td key={m}>{r.modules[m] || ""}</td>)}<td>{r.members.join(", ")}</td>
        <td><button className="ghost small" onClick={() => setEdit({ name: r.name, description: r.description, admin: !!r.admin, modules: { ...r.modules } })}>Edit</button></td></tr>))}
    </tbody></table>
    <button className="ghost small" onClick={() => setEdit({ name: "", description: "", admin: false, modules: {} })}>New role</button>
    {edit && <div className="editbox">
      <div className="acts"><input placeholder="role name" value={edit.name} onChange={(ev) => setEdit({ ...edit, name: ev.target.value })} /><input placeholder="description" value={edit.description} onChange={(ev) => setEdit({ ...edit, description: ev.target.value })} />
        <label className="chk"><input type="checkbox" checked={edit.admin} onChange={(ev) => setEdit({ ...edit, admin: ev.target.checked })} />admin</label></div>
      <div className="grid4">{mods.map((m) => <label key={m}>{m}<select value={edit.modules[m] || ""} onChange={(ev) => setEdit({ ...edit, modules: { ...edit.modules, [m]: ev.target.value } })}>{LV.map((l) => <option key={l} value={l}>{l || "—"}</option>)}</select></label>)}</div>
      <div className="acts"><button className="ghost on" onClick={save} disabled={!edit.name}>Save role</button><button className="ghost" onClick={() => setEdit(null)}>Cancel</button></div></div>}
    {msg && <p className="note">{msg}</p>}
  </>);
}
function Grants() {
  const [d, e, load] = useLoad("/api/admin/grants");
  const [r] = useLoad("/api/admin/roles");
  const [g, setG] = useState({ user: "", module: "", level: "read", hours: "", reason: "" });
  const [msg, setMsg] = useState("");
  if (e) return <p className="bad">{e}</p>;
  if (!d || !r) return <p className="note">Loading…</p>;
  const add = async () => { try { await api("/api/admin/grants", "POST", { ...g, hours: g.hours ? +g.hours : null }); setMsg("Granted."); load(); } catch (x) { setMsg(x.message); } };
  const revoke = async (id) => { try { await api(`/api/admin/grants/${id}/revoke`, "POST", {}); load(); } catch (x) { setMsg(x.message); } };
  const live = (x) => !x.revoked_at && (!x.until || new Date(x.until) > new Date());
  return (<>
    <div className="acts"><input placeholder="user" value={g.user} onChange={(ev) => setG({ ...g, user: ev.target.value })} />
      <select value={g.module} onChange={(ev) => setG({ ...g, module: ev.target.value })}><option value="">module…</option><option value="*">* (all)</option>{r.modules.map((m) => <option key={m}>{m}</option>)}</select>
      <select value={g.level} onChange={(ev) => setG({ ...g, level: ev.target.value })}>{LV.slice(1).map((l) => <option key={l}>{l}</option>)}</select>
      <input placeholder="hours (empty = no end)" value={g.hours} onChange={(ev) => setG({ ...g, hours: ev.target.value })} />
      <input placeholder="reason" value={g.reason} onChange={(ev) => setG({ ...g, reason: ev.target.value })} />
      <button className="ghost on" onClick={add} disabled={!g.user || !g.module}>Grant</button></div>
    {msg && <p className="note">{msg}</p>}
    <table className="vars"><thead><tr><th>#</th><th>Person</th><th>Module</th><th>Level</th><th>Until</th><th>By · why</th><th></th></tr></thead><tbody>
      {d.grants.map((x) => (<tr key={x.id} className={live(x) ? "" : "mute"}><td>{x.id}</td><td>{x.user}</td><td>{x.module}</td><td>{x.level}{x.kind === "emergency" ? " (emergency)" : ""}</td>
        <td>{x.until ? x.until.slice(0, 16).replace("T", " ") : "no end"}</td><td>{x.by} · {x.reason}</td>
        <td>{live(x) ? <button className="ghost small" onClick={() => revoke(x.id)}>Revoke</button> : <small>{x.revoked_at ? `revoked by ${x.revoked_by}` : "ended"}</small>}</td></tr>))}
    </tbody></table>
  </>);
}
function Owners() {
  const [d, e, load] = useLoad("/api/admin/owners");
  const [ed, setEd] = useState({});
  const [msg, setMsg] = useState("");
  if (e) return <p className="bad">{e}</p>;
  if (!d) return <p className="note">Loading…</p>;
  const save = async (m) => { try { await api(`/api/admin/owners/${encodeURIComponent(m)}`, "PUT", { users: ed[m].split(",").map((x) => x.trim()).filter(Boolean) }); setMsg("Saved."); load(); } catch (x) { setMsg(x.message); } };
  return (<>
    <p className="note">Owners have Sign access to their module and decide access requests for it.</p>
    <table className="vars"><tbody>{Object.entries(d.owners).map(([m, us]) => (<tr key={m}><td><b>{m}</b></td>
      <td><input value={ed[m] ?? us.join(", ")} onChange={(ev) => setEd({ ...ed, [m]: ev.target.value })} /></td>
      <td>{ed[m] !== undefined && <button className="ghost small" onClick={() => save(m)}>Save</button>}</td></tr>))}</tbody></table>
    {msg && <p className="note">{msg}</p>}
  </>);
}
export function Requests() {
  const [d, e, load] = useLoad("/api/access-requests");
  const [hours, setHours] = useState(72);
  const [msg, setMsg] = useState("");
  if (e) return <p className="bad">{e}</p>;
  if (!d) return <p className="note">Loading…</p>;
  const decide = async (id, approve) => { try { await api(`/api/access-requests/${id}/decide`, "POST", { approve, hours: hours || null }); load(); } catch (x) { setMsg(x.message); } };
  return (<>
    <h4>To decide ({d.to_decide.length})</h4>
    {d.to_decide.length > 0 && <label className="note">Approve for <input type="number" value={hours} onChange={(ev) => setHours(+ev.target.value)} style={{ width: 70 }} /> hours (0 = no end)</label>}
    {d.to_decide.map((r) => <div key={r.id} className="rqi"><b>{r.user}</b> asks for <b>{r.level}</b> on <b>{r.module}</b>: “{r.reason}” <small className="note">{r.created_at.slice(0, 16).replace("T", " ")}</small>
      <div className="acts"><button className="ghost small" onClick={() => decide(r.id, true)}>Approve</button><button className="ghost small" onClick={() => decide(r.id, false)}>Decline</button></div></div>)}
    <h4>My requests</h4>
    {d.mine.map((r) => <div key={r.id} className="note">{r.module}: {r.level} — {r.status}{r.decided_by ? ` by ${r.decided_by}` : ""}</div>)}
    {msg && <p className="note">{msg}</p>}
  </>);
}
function Audit() {
  const [f, setF] = useState({ user: "", action: "", target: "" });
  const q = new URLSearchParams({ ...f, limit: 300 }).toString();
  const [d, e] = useLoad("/api/admin/audit?" + q);
  if (e) return <p className="bad">{e}</p>;
  if (!d) return <p className="note">Loading…</p>;
  return (<>
    <p className={d.chain.ok ? "ok" : "bad"}>{d.chain.ok ? `Audit chain intact (${d.chain.rows} rows).` : `The audit log was changed at row ${d.chain.broken_at}.`}</p>
    <div className="acts">{["user", "action", "target"].map((k) => <input key={k} placeholder={k} defaultValue={f[k]} onKeyDown={(ev) => ev.key === "Enter" && setF({ ...f, [k]: ev.target.value })} />)}</div>
    <table className="vars"><thead><tr><th>When</th><th>Who</th><th>What</th><th>On</th><th>Details</th></tr></thead><tbody>
      {d.rows.map((r) => <tr key={r.id}><td className="mono">{r.at.replace("T", " ").slice(0, 19)}</td><td>{r.user}</td><td>{r.action}</td><td>{r.target}</td><td className="mono small">{JSON.stringify(r.detail)}</td></tr>)}
    </tbody></table>
  </>);
}
function Team() {
  const [d, e, load] = useLoad("/api/admin/settings");
  const [txt, setTxt] = useState(null);
  const [res, setRes] = useState(null);
  if (e) return <p className="bad">{e}</p>;
  if (!d) return <p className="note">Loading…</p>;
  const go = async (save) => { try { setRes(await api("/api/admin/settings/check", "POST", { yaml: txt ?? d.yaml, save })); if (save) load(); } catch (x) { setRes({ ok: false, problems: [x.message] }); } };
  return (<>
    <p className="note">{d.path || "No settings file path (settings: in access.yaml)."} {d.fingerprint && `· fingerprint ${d.fingerprint}`} {d.badge && `· ${d.badge}`}</p>
    {d.error && <p className="bad">{d.error}</p>}
    <textarea className="yaml" value={txt ?? d.yaml} onChange={(ev) => setTxt(ev.target.value)} spellCheck={false} />
    <div className="acts"><button className="ghost" onClick={() => go(false)}>Check</button><button className="ghost on" onClick={() => go(true)}>Save (needs approved_by and approved_on)</button></div>
    {res && (res.ok ? <p className="ok">{res.saved ? "Saved." : "Valid."} Fingerprint {res.fingerprint}. {(res.warnings || []).join(" · ")}{res.previous_kept_as ? ` Old file kept as ${res.previous_kept_as}.` : ""}</p>
      : <ul className="bad">{(res.problems || []).map((p, i) => <li key={i}>{p}</li>)}</ul>)}
  </>);
}

export { VERDICT, LEVELS };

// ---------------------------------------------------------------------- D5 calibration + G1 experiment (test tool, admins)
export function Calibration() {
  const [c, setC] = useState(null), [x, setX] = useState(null);
  useEffect(() => {
    fetch("data/calibration.json", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : false)).then(setC).catch(() => setC(false));
    fetch("data/experiment.json", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : false)).then(setX).catch(() => setX(false));
  }, []);
  const W = 220, H = 220, P = 28;
  const sx = (v) => P + v * (W - 2 * P), sy = (v) => H - P - v * (H - 2 * P);
  return (
    <div className="calib">
      <h4>Calibration: confidence against known outcomes</h4>
      {c === null ? <p className="note">Loading…</p> : !c ? <p className="note">Not computed yet: <code>./run_world.sh --calibrate</code>.</p> : (<>
        <div className="calrow">
          <svg width={W} height={H} role="img" aria-label="Reliability diagram">
            <rect x={P} y={P} width={W - 2 * P} height={H - 2 * P} fill="none" stroke="var(--line2)" />
            <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--faint)" strokeDasharray="4 4" />
            {c.rows.filter((r) => r.conf != null).map((r) => <circle key={r.pr} cx={sx(r.conf)} cy={sy(r.correct)} r={4} fill={r.planted ? "var(--bad)" : "var(--ok)"} opacity={0.55}><title>{r.pr}: confidence {Math.round(r.conf * 100)}%, {r.planted ? "planted defect" : "clean"}</title></circle>)}
            {c.bins.filter((b) => b.n).map((b, i) => <rect key={i} x={sx(b.mean_conf) - 5} y={sy(b.share_correct) - 5} width={10} height={10} fill="var(--acc)"><title>{`${b.n} PR(s): mean confidence ${Math.round(b.mean_conf * 100)}%, correct ${Math.round(b.share_correct * 100)}%`}</title></rect>)}
            <text x={W / 2} y={H - 6} textAnchor="middle" fontSize="10" fill="var(--mute)">confidence</text>
            <text x={10} y={H / 2} fontSize="10" fill="var(--mute)" transform={`rotate(-90 10 ${H / 2})`} textAnchor="middle">share correct</text>
          </svg>
          <div>
            <p><b>Brier score {c.brier ?? "–"}</b> <span className="note">(0 is perfect; always saying 50% scores 0.25)</span></p>
            <p className="note">Squares: groups of PRs (mean confidence, share without a planted defect). Dots: single PRs, red = planted defect. On the dashed line the number would mean what it says.</p>
            <table className="vars"><thead><tr><th>Trust level</th><th>PRs</th><th>Without planted defect</th></tr></thead><tbody>
              {Object.entries(c.by.trust).map(([k, v]) => <tr key={k}><td>{(LEVELS[k] || { label: k }).label}</td><td>{v.n}</td><td>{v.correct}</td></tr>)}</tbody></table>
          </div>
        </div>
        <p className="note">{c.note}</p></>)}
      <h4>Experiment: reviewer set-ups compared</h4>
      {x === null ? <p className="note">Loading…</p> : !x ? <p className="note">Not run yet: <code>./run_world.sh --experiment</code>.</p> : (<>
        <table className="vars"><thead><tr><th>Set-up</th><th>Planted defects caught</th><th>Critical on clean PRs</th><th>Requirement flags (planted / clean)</th><th>Model calls</th><th>Cost</th></tr></thead><tbody>
          {Object.entries(x.variants).map(([k, v]) => v.skipped ? <tr key={k}><td>{k}: {v.title}</td><td colSpan={5} className="note">{v.skipped}</td></tr> :
            <tr key={k}><td>{k}: {v.title}</td><td>{v.summary.caught} of {v.summary.planted}</td><td>{v.summary.clean_with_critical} of {v.summary.clean}</td>
              <td>{v.summary.requirement_flags_on_planted} / {v.summary.requirement_flags_on_clean}</td><td>{v.summary.calls}</td><td>{v.summary.cost_eur} EUR</td></tr>)}
        </tbody></table>
        <p className="note">{x.note} Run {x.generated_at}.</p></>)}
    </div>);
}

// ---------------------------------------------------------------------- switch mode: view the app as another person
export function ViewAs({ onPick }) {
  const [ppl, setPpl] = useState(null);
  useEffect(() => { api("/api/people").then((r) => setPpl(r.people)).catch(() => setPpl([])); }, []);
  if (!ppl) return <div className="msep">Loading people…</div>;
  const go = async (id) => { try { await api("/api/switch", "POST", { user: id }); onPick && onPick(); location.reload(); } catch (e) { alert(e.message); } };
  return (
    <>
      <div className="msep">View as</div>
      {ppl.map((p) => (
        <a key={p.id} role="menuitemradio" aria-checked={API.me && API.me.id === p.id} className={"person" + (API.me && API.me.id === p.id ? " cur" : "")} onClick={() => go(p.id)}
          title={p.about || p.roles.join(", ")}>
          <span>{API.me && API.me.id === p.id ? "● " : ""}{p.name}</span>
          <small>{p.owns.length ? `owns ${p.owns.join(", ")}` : p.roles.join(", ") || "no role"}</small>
        </a>))}
    </>);
}
