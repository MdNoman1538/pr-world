import { useEffect, useState } from "react";
import { displayName, LEVEL, VERDICT, range, conf, basis, REVIEWER, lensFacts, LENSES, sev, trustShow, TRUST, notCheckedAreas, shownSev, VIEW } from "./model.js";
import { CutBanner, SignOff, Coverage, TwoPartTrust, Judge, AccessCard } from "./Platform.jsx";
import { Finding, About } from "./SidePanel.jsx";

// What the active lens shows for this PR, as facts from the map and the diff (each line names real code)
const LENS_HEAD = {
  apis: ["APIs this PR changes or affects", "Each endpoint, the code it runs that this PR touched, and other modules that use the same code."],
  calls: ["Calls made by changed code", "Every call from code this PR changed, and the calls it added."],
  events: ["Events this PR touches", "Who publishes each event and who handles it."],
  data: ["Data this PR reads or writes", "Each table, and the changed or affected code that reads or writes it."],
  security: ["Security facts in this PR", "Authorization on each endpoint, access checks, personal data and the reviewer's security findings."],
  tests: ["Tests written in this PR", "Each new or changed test, its result, and the code it calls."],
};
const ST = { new: "bad", changed: "bad", affected: "warn", open: "bad", finding: "warn", failed: "bad", broken: "warn", "not run": "mute", passed: "ok" };
export function LensFacts({ W, O, lens, scope, onOpen }) {
  const [openK, setOpenK] = useState(null);
  if (!lens || lens === "risk" || !LENS_HEAD[lens]) return null;
  let facts = lensFacts(W, O, lens);
  if (scope) facts = facts.filter((f) => f.home === scope || f.links.some(([a, b]) => (W.node(a) || {}).module === scope || (W.node(b) || {}).module === scope));
  const [head, sub] = LENS_HEAD[lens];
  return (
    <section className="lensfacts">
      <h4 className="fbhead">{head}{scope ? ` · ${scope}` : ""} ({facts.length})</h4>
      <p className="note">{sub}</p>
      {!facts.length && <p className="note">Nothing for this lens {scope ? "in this module " : ""}in this PR.</p>}
      {facts.map((f, i) => {
        const k = f.id + i, on = openK === k;
        return (
          <div key={k} className={"lf" + (on ? " on" : "")}>
            <div className="lfh" onClick={() => setOpenK(on ? null : k)}>
              <span className={"sv " + (ST[f.status] || "mute")}>{f.sev ? sev(f.sev).label : f.status}</span>
              <b>{f.title}</b>
              {f.lines.length > 0 && <span className="lfn">{on ? "▾" : "▸"} {f.lines.length}</span>}
            </div>
            {f.sub && <div className="lfs">{f.sub}</div>}
            {on && <ul className="lfl">{f.lines.map((l, j) => <li key={j}>{l}</li>)}</ul>}
            {f.id && W.node(f.id) && <a className="lfo" onClick={() => onOpen(f.id)}>Show it</a>}
          </div>);
      })}
    </section>);
}


const IMPACT = { high: "bad", medium: "warn", low: "ok", none: "mute", unknown: "mute" };
const kindWord = (W, n) => (n.kind === "type" ? n.attrs.type_kind || "class" : n.kind === "ctor" ? "constructor" : n.kind);

// One bar: how much of this area has test evidence. Counts only, no invented weights.
export function TrustCard({ W, s, side, onOpen, onMethod, compact }) {
  if (!s) return null;
  const seg = [["verified", s.verified], ["contradicted", s.contradicted], ["not_run", s.not_run], ["none", s.none]].filter(([, v]) => v);
  const title = side === "changed" ? "Changed code verified by passing tests" : "Affected code with a passing test across the link";
  return (
    <div className={"trust " + (compact ? "compact" : "")}>
      <div className="th">
        <b className={s.contradicted ? "bad" : s.pct >= 80 ? "ok" : s.pct >= 40 ? "warn" : "bad"}>{s.verified}/{s.n}</b>
        <span>{title}{!compact && s.conf != null && (TRUST.view === "percent" ? <em className="rng"> · confidence {conf(s)}, 95% range {range(s)}</em> : (() => { const t = trustShow(s); return <em className="rng" title={t.title}> · trust <b className={t.cls}>{t.text}</b>: {t.why}</em>; })())}</span>
        {!compact && <button className="unc" onClick={onMethod} title="How this is computed">uncalibrated ⓘ</button>}
      </div>
      <div className="bar">{seg.map(([k, v]) => <i key={k} className={"lv-" + k} style={{ flex: v }} title={`${LEVEL[k].label}: ${v}`} />)}</div>
      <div className="lg">{seg.map(([k, v]) => <span key={k}><i className={"lv-" + k} />{v} {LEVEL[k].short}</span>)}</div>
      {!compact && s.weakest && s.weakest.length > 0 && (
        <div className="held">Held back by
          {s.weakest.map(([id, lv]) => W.node(id) && <a key={id} onClick={() => onOpen(id)}><span className={LEVEL[lv].cls}>{LEVEL[lv].icon}</span> {W.node(W.node(id).parent)?.name}.{displayName(W.node(id))}<em>{LEVEL[lv].short}</em></a>)}
        </div>)}
    </div>
  );
}

// The answer first: label, confidence range, and the reasons, each one clickable
export function VerdictCard({ W, O, onOpen, onFinding, onMethod }) {
  const v = O.notes && O.notes.verdict;
  if (!v) return null;
  const V = VERDICT[v.label], s = (O.roll("pr") || {}).changed;
  const groups = [["fix", "Must be fixed"], ["check", "To check"], ["info", "Good to know"]];
  const go = (r) => (r.finding ? onFinding(r.finding) : r.node ? onOpen(r.node) : r.nodes && r.nodes[0] ? onOpen(r.nodes[0]) : null);
  return (
    <div className={"verdict " + V.cls}>
      <div className="vt"><b>{V.label}</b>{s && (() => { const t = trustShow(s, v.label, notCheckedAreas(O.review)); return <span className="conf" title={t.title}><b className={TRUST.view === "percent" ? "" : t.cls}>{t.text}</b> <small>{t.word} · {basis(s)}</small></span>; })()}</div>
      <div className="who">{V.who}</div>
      {groups.map(([lv, h]) => {
        const rs = v.reasons.filter((r) => r.level === lv);
        if (!rs.length) return null;
        return (<div key={lv} className={"rg " + lv}><h4>{h} ({rs.length})</h4>
          {rs.map((r, i) => (
            <div key={i} className={"rsn " + ((r.finding || r.node || r.nodes) ? "click" : "")} onClick={() => go(r)}>
              <span className="rk">{r.kind === "critical" ? "Critical" : r.kind === "major" ? "Major" : r.kind === "tests_fail" ? "Tests" : r.kind === "broken" ? "Broken tests" : r.kind === "untested" ? "No evidence" : r.kind === "reviewer" ? "Reviewer" : r.kind === "inherited" ? "Earlier PR" : ""}</span>
              <span className="rt">{r.text}{r.detail && <small>{r.detail}</small>}</span>
            </div>))}
        </div>);
      })}
      <div className="vf">Reviewer engine: {REVIEWER[v.reviewer_gate] || "no review"} · <a onClick={onMethod}>how this is decided</a> · uncalibrated</div>
    </div>
  );
}

function UnitCard({ u }) {
  if (!u) return null;
  const L = LEVEL[u.level];
  return (
    <div className="unit">
      <div className={"lvl " + L.cls}>{L.icon} {L.label}</div>
      {u.side === "affected" && u.via && <div className="note">{u.direction === "depends on the change" ? "Depends on the change" : "Reached by the change"}, {u.hops} hop(s).</div>}
      {u.tests.failed_n > 0 && <><h4>Tests that disagree with this code ({u.tests.failed_n})</h4>{u.tests.failed.map((t) => <div key={t.name} className="tst bad">✕ {t.name}{t.cases > 1 ? ` (${t.cases} cases)` : ""}{t.message && <small>{t.message}</small>}</div>)}</>}
      {u.tests.broken_n > 0 && <><h4>Broken tests ({u.tests.broken_n}): crash in the test's own code, prove nothing</h4>{u.tests.broken.map((t) => <div key={t.name} className="tst warn">⚠ {t.name}{t.cases > 1 ? ` (${t.cases} cases)` : ""}{t.message && <small>{t.message}</small>}</div>)}</>}
      {u.tests.inherited_n > 0 && <><h4>Failing before this PR ({u.tests.inherited_n}): not counted</h4>{u.tests.inherited.map((t) => <div key={t.name} className="tst mute">↺ {t.name}</div>)}</>}
      {u.tests.passed_n > 0 && <><h4>Passing tests ({u.tests.passed_n})</h4>{u.tests.passed.map((t) => <div key={t} className="tst ok">✓ {t}</div>)}{u.tests.passed_n > u.tests.passed.length && <div className="note">+{u.tests.passed_n - u.tests.passed.length} more</div>}</>}
      {u.tests.failed_n === 0 && u.tests.passed_n === 0 && !u.tests.broken_n && <div className="note">{u.side === "changed" ? "No test from the Test agent reaches this code." : "No test runs through both the change and this code."}</div>}
    </div>
  );
}

function Note({ O, id, side }) {
  const n = O.note(id);
  const txt = n && n[side];
  if (!txt) return null;
  const ai = n[side + "_src"] === "ai";
  const nk = (O.W.node(id) || {}).kind;
  if (!ai && (nk === "module" || nk === "type")) return null; // the list below already says it
  return <div className="meaning">{txt}<small>{ai ? "written from the diff" : "facts from the diff"}</small></div>;
}

// the changed / affected children of an area, one line each, with their own evidence
function Children({ W, O, id, side, onOpen }) {
  const n = W.node(id);
  const set = side === "changed" ? O.rollC : O.rollA;
  let kids = W.children(id).filter((k) => set.has(k.id) && !W.isTest(k));
  if (n.kind === "module") kids = kids.flatMap((l) => (l.kind === "layer" ? W.children(l.id).filter((k) => set.has(k.id)) : [l]));
  if (!kids.length) return null;
  const word = n.kind === "module" ? "Classes" : n.kind === "type" ? "Members" : "Parts";
  return (
    <>
      <h4>{word} {side === "changed" ? "changed" : "affected"} ({kids.length})</h4>
      <div className="kids">
        {kids.map((k) => {
          const u = O.unit(k.id), r = O.roll(k.id), s = r && r[side];
          const nt = O.note(k.id);
          return (
            <a key={k.id} onClick={() => onOpen(k.id)}>
              <span className="kn">{u && u.side === side ? <span className={LEVEL[u.level].cls}>{LEVEL[u.level].icon}</span> : s ? <span className={s.contradicted ? "bad" : s.verified === s.n ? "ok" : "warn"}>{s.verified}/{s.n}</span> : <span className="mute">·</span>}
                {" "}{displayName(k)}{O.isNew(k.id) && side === "changed" ? <em className="new">new</em> : null}{O.findings(k.id).length ? <em className="bad">! {O.findings(k.id).length}</em> : null}</span>
              {nt && nt[side] && <small>{nt[side]}</small>}
            </a>);
        })}
      </div>
    </>
  );
}

function Section({ W, O, id, side, onOpen, onMethod }) {
  const n = W.node(id);
  const r = O.roll(id), u = O.unit(id);
  const name = n.kind === "module" ? n.name : displayName(n);
  return (
    <section className={"psec " + side}>
      <h3 className="sh">{side === "changed" ? "What changed in " : "How "}<b>{name}</b>{side === "affected" ? " is affected" : ""}</h3>
      <Note O={O} id={id} side={side} />
      {u && u.side === side ? <UnitCard u={u} /> : r && r[side] ? <TrustCard W={W} s={r[side]} side={side} onOpen={onOpen} onMethod={onMethod} /> :
        (n.kind === "method" || n.kind === "ctor" || n.kind === "property" || n.kind === "field") && side === "changed" ? <div className="note">{n.kind === "property" || n.kind === "field" ? "Data, no behaviour of its own: counted with the code that uses it." : "A contract only: the implementation carries the evidence."}</div> : null}
      <Children W={W} O={O} id={id} side={side} onOpen={onOpen} />
    </section>
  );
}

// One feedback item: a plain sentence for the human; click to open the facts behind it
function FeedbackItem({ W, r, open, onToggle, onOpen, onCode, pr }) {
  const tag = { critical: ["Critical", "bad"], major: ["Major", "warn"], tests_fail: ["Tests disagree", "bad"], broken: ["Broken tests", "warn"],
    untested: ["Not tested", "warn"], reviewer: ["Please check", "warn"], no_tests: ["Not tested", "warn"],
    setting: ["Business decision", "warn"], business: ["Business impact", "warn"],
    requirement: ["Requirement", r.level === "fix" ? "bad" : "warn"], not_checked: ["Not checked", "mute"] }[r.kind] || ["Note", "mute"];
  return (
    <div className={"fb " + (open ? "open" : "")}>
      <div className="fbh" onClick={onToggle}>
        <span className={"sv " + tag[1]}>{tag[0]}</span>
        <span className="fbt">{r.say || r.text}</span>
        <span className="chev">{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <div className="fbd">
          {r.finding && <><div className="fbk">Reviewer's finding</div><div className="fbv"><b>{r.text}</b>{r.claim && <p>{r.claim}</p>}</div></>}
          {r.suggested_fix && <><div className="fbk">Suggested fix</div><div className="fbv">{r.suggested_fix}</div></>}
          {r.kind === "requirement" && r.detail && <><div className="fbk">Items</div><div className="fbv">{r.detail}</div></>}
          {r.file && <div className="fbv"><a onClick={() => onCode(r.file, r.line_start)}>Open the code ({r.file.split("/").pop()}:{r.line_start})</a>{r.node && W.node(r.node) && <> · <a onClick={() => onOpen(r.node)}>Show in the map</a></>}</div>}
          {r.kind === "setting" && r.node && W.node(r.node) && <div className="fbv"><a onClick={() => onOpen(r.node)}>Show who uses it in the map</a></div>}
          {!r.finding && r.detail && r.kind !== "untested" && r.kind !== "requirement" && <><div className="fbk">Details</div><div className="fbv mono small">{r.detail}</div></>}
          {r.nodes && <><div className="fbk">Where</div><div className="fbv">{r.nodes.map((id) => W.node(id) && <a key={id} className="blk" onClick={() => onOpen(id)}>{(W.node(W.node(id).parent) || {}).name}.{displayName(W.node(id))}</a>)}</div></>}
          {r.tests && r.tests.length > 0 && <><div className="fbk">{r.kind === "critical" ? "Tests that agree with the finding" : "Tests"}</div><div className="fbv">{r.tests.map((t) => <div key={t} className="tst">{t.replace(/_/g, " ")}</div>)}</div></>}
          {r.say_src === "ai" && r.say_facts && <div className="fbsrc">Worded by the notes agent from the reviewer's facts.</div>}
          {r.locked && <div className="fbv note">This item is in a module you cannot open: its details are hidden.</div>}
          {r.finding && !r.locked && pr && <Judge pr={pr} fid={r.finding} />}
        </div>)}
    </div>
  );
}

// Trust details: everything about evidence, on demand (one button, not many lines)
export function TrustDetails({ W, O, pr, id, onOpen, onMethod }) {
  const r = O.roll(id || "pr") || {}, u = id ? O.unit(id) : null, v = O.notes && O.notes.verdict;
  return (
    <div className="trustd">
      {u ? <UnitCard u={u} /> : null}
      {!u && r.changed && <><h4>Changed code</h4><TrustCard W={W} s={r.changed} side="changed" onOpen={onOpen} onMethod={onMethod} /></>}
      {!u && r.affected && <><h4>Affected code</h4><TrustCard W={W} s={r.affected} side="affected" onOpen={onOpen} onMethod={onMethod} /></>}
      {!id && pr.tests && pr.tests.ran && v && <><h4>Tests (written blind, from the requirement)</h4>
        <div className="note">{pr.tests.passed} cases pass · {v.failures.new} test(s) disagree with this PR's code · {v.failures.broken} broken · {v.failures.inherited} were failing before this PR (not counted)</div></>}
      {!id && <><h4>Two parts</h4><p><TwoPartTrust O={O} /></p></>}
      {!id && <Coverage review={O.review} />}
      <p className="note"><a onClick={onMethod}>How the trust level, the confidence and the label are decided</a></p>
    </div>
  );
}

// What the PR does, in words: summary, business impact, requirement
export function AboutPR({ O, pr, onIssue }) {
  const n = O.notes;
  return (
    <div className="aboutpr">
      {n && n.summary ? <p className="lead">{n.summary}</p> : <p className="note">No written summary yet. Run <code>./run_world.sh --notes</code>.</p>}
      {n && n.business && <div className={"biz " + IMPACT[n.business_impact]}><b>Business impact: {n.business_impact}</b>{n.business}</div>}
      <p><button className="ghost" onClick={onIssue}>Read the requirement</button></p>
    </div>
  );
}

const oneLine = (u) => {
  if (!u) return null;
  const t = u.tests;
  if (u.level === "verified") return ["ok", `Verified by ${t.passed_n} passing test${t.passed_n > 1 ? "s" : ""}`];
  if (u.level === "contradicted") return ["bad", t.failed_n ? `${t.failed_n} test${t.failed_n > 1 ? "s" : ""} disagree with this code` : "The reviewer found a problem here"];
  if (u.level === "not_run") return ["mute", "Tests reach it but were not run"];
  return ["warn", "No working test covers this"];
};

export default function PRPanel({ W, O, pr, id, mode, focusF, onOpen, onFinding, onCode, onIssue, onMethod, onModal, meaning, lens }) {
  const notes = O.notes;
  const n = id ? W.node(id) : null;
  const [openI, setOpenI] = useState(null);
  useEffect(() => setOpenI(null), [pr.id, id]);
  useEffect(() => { // a finding picked on the map or in the tour opens its feedback item
    if (!focusF || !notes || !notes.verdict) return;
    const i = notes.verdict.reasons.findIndex((r) => r.finding === focusF);
    if (i >= 0) setOpenI(i);
  }, [focusF]); // eslint-disable-line react-hooks/exhaustive-deps
  const trustBtn = (nid) => <button className="ghost small" onClick={() => onModal("Trust details" + (nid && W.node(nid) ? " — " + (W.node(nid).kind === "module" ? W.node(nid).name : displayName(W.node(nid))) : ""), <TrustDetails W={W} O={O} pr={pr} id={nid} onOpen={onOpen} onMethod={onMethod} />)}>Trust details</button>;

  if (!n) {
    const v = notes && notes.verdict;
    const RSEV = { critical: "Blocker", major: "ShouldFix" };
    const all = v ? v.reasons.map((r, i) => [r, i]).filter(([r]) => r.level !== "info") : [];
    const items = all.filter(([r]) => !RSEV[r.kind] || shownSev(RSEV[r.kind]));
    const hidden = all.filter(([r]) => RSEV[r.kind] && !shownSev(RSEV[r.kind]));
    const info = v ? v.reasons.filter((r) => r.level === "info") : [];
    const minor = (O.review.findings || []).filter((f) => f.severity === "Nit");
    return (
      <aside className="side clean">
        <div className="kind">{pr.id}{v && v.risk_areas.length ? ` · high-risk area: ${v.risk_areas.map((a) => a.module).join(", ")}` : ""}</div>
        <h3>{pr.title}</h3>
        <CutBanner O={O} />
        <div className="two-line"><TwoPartTrust O={O} /></div>
        <div className="acts">
          <button className="ghost small" onClick={() => onModal(pr.id + " — what this PR does", <AboutPR O={O} pr={pr} onIssue={onIssue} />)}>What this PR does</button>
          {trustBtn(null)}
          <button className="ghost small" onClick={onIssue}>Requirement</button>
          <button className="ghost small" onClick={() => onModal(pr.id + " — sign-off", <SignOff pr={pr} O={O} />)}>Sign-off</button>
        </div>
        <LensFacts W={W} O={O} lens={lens} onOpen={onOpen} />
        <h4 className="fbhead">Reviewer feedback {items.length ? `(${items.length})` : ""}</h4>
        {!v && <p className="note">No feedback yet. Run <code>./run_world.sh --notes</code>.</p>}
        {v && !items.length && <p className="note ok">Nothing to check. The named human can sign.</p>}
        {items.map(([r, i]) => <FeedbackItem key={i} W={W} r={r} pr={pr} open={openI === i} onToggle={() => setOpenI(openI === i ? null : i)} onOpen={onOpen} onCode={onCode} />)}
        {hidden.length > 0 && (
          <details className="more"><summary>Hidden by your filter ({hidden.length}, {sev(VIEW.severity_min).label} and above shown)</summary>
            {hidden.map(([r, i]) => <FeedbackItem key={i} W={W} r={r} pr={pr} open={openI === i} onToggle={() => setOpenI(openI === i ? null : i)} onOpen={onOpen} onCode={onCode} />)}
          </details>)}
        {(info.length > 0 || minor.length > 0) && (
          <details className="more"><summary>Also noted ({info.length + minor.length})</summary>
            {info.map((r, i) => <p key={i} className="note">{r.say || r.text}</p>)}
            {minor.map((f) => <Finding key={f.id} f={f} on={focusF === f.id} onClick={() => onFinding(f.id)} />)}
          </details>)}
        <Coverage review={O.review} />
      </aside>);
  }

  if (n.attrs.locked) {
    const st = O.status(id), nf = O.findings(id).length;
    return (
      <aside className="side clean">
        <div className="kind">module · no access{st ? ` · ${st === "impacted" ? "affected" : "changed"} by this PR` : ""}</div>
        <h3>{n.name}</h3>
        {nf > 0 && <p className="warn">{nf} finding{nf === 1 ? "" : "s"} here ({O.findings(id).map((f) => sev(f.severity).label).join(", ")}); details hidden.</p>}
        <AccessCard name={n.name} node={n} />
      </aside>);
  }
  const showC = mode.changed && O.rollC.has(id), showA = mode.affected && O.rollA.has(id);
  const fs = O.findings(id);
  const nm = n.kind === "module" ? n.name : displayName(n);
  const line = oneLine(O.unit(id));
  const sub = (side) => { const r = O.roll(id); return r && r[side] ? r[side] : null; };
  return (
    <aside className="side clean">
      <div className="kind">{kindWord(W, n)}{n.kind !== "module" && n.module ? ` · ${n.module}` : ""}{W.tier(n.module) === "high" ? " · high-risk area" : ""}</div>
      <h3>{nm}{O.isNew(id) ? <em className="newtag">new</em> : null}</h3>
      {n.kind === "module" && <LensFacts W={W} O={O} lens={lens} scope={n.name} onOpen={onOpen} />}
      {showC && <section className="psec changed"><h4 className="sh">What changed</h4><Note O={O} id={id} side="changed" /><Children W={W} O={O} id={id} side="changed" onOpen={onOpen} /></section>}
      {showA && <section className="psec affected"><h4 className="sh">How it is affected</h4><Note O={O} id={id} side="affected" /><Children W={W} O={O} id={id} side="affected" onOpen={onOpen} /></section>}
      {!showC && !showA && <p className="note">{O.touched(id) ? "Switch on Changed or Affected (top bar) to see what this PR does here." : "This PR does not touch this part."}</p>}
      {(showC || showA) && (
        <div className="evid">
          {line ? <span className={line[0]}>{line[1]}</span> : (sub(showC ? "changed" : "affected") ? <span>{sub(showC ? "changed" : "affected").verified} of {sub(showC ? "changed" : "affected").n} {showC ? "changed" : "affected"} parts verified by tests</span> : null)}
          {trustBtn(id)}
        </div>)}
      {fs.length > 0 && <><h4>Reviewer findings here ({fs.length})</h4>{fs.map((f) => <Finding key={f.id} f={f} on={focusF === f.id} onClick={() => onFinding(f.id)} />)}</>}
      {n.file && <p className="note"><a onClick={() => onCode(n.file, n.line)}>Open the code</a></p>}
      <details className="about"><summary>About this {kindWord(W, n)}</summary><About W={W} O={O} id={id} meaning={meaning} onOpen={onOpen} /></details>
    </aside>
  );
}

export function Method() {
  return (
    <div className="method">
      <p>Each changed method or constructor (outside the tests) is one <b>unit</b>. Each unit gets one evidence level:</p>
      <table className="vars"><tbody>
        <tr><td className="ok">✓ verified</td><td>Every test from the blind Test agent that reaches it ran and passed.</td><td>rubric E4</td></tr>
        <tr><td className="bad">✕ contradicted</td><td>A test that reaches it now fails, or the reviewer raised a Critical finding (or a Major one about correctness or security) on it. The test or the code may be wrong: a human decides.</td><td>rubric E0</td></tr>
        <tr><td className="mute">○ not run</td><td>Tests reach it but were not run.</td><td></td></tr>
        <tr><td className="warn">– no evidence</td><td>No test reaches it. Only the AI reviewer looked, and "the AI said it was fine" is not evidence.</td><td>rubric E1</td></tr>
      </tbody></table>
      <p><b>Only new failures count.</b> Each PR runs the whole test suite. A failure that already happened in the PR's base is shown as "failing before this PR" and not counted. A failure whose error points into the test's own code (the message names a test class, e.g. a database query the test wrote that cannot run) is a <b>broken test</b>: it proves nothing about the code. An assertion failure means the code and the test disagree: one of them must change.</p>
      <p><b>Score = verified units / all units</b>, per method, class, module and PR. This is the ratio form of the ISO/IEC 25023 functional correctness measure (share of functions shown to give correct results). No weights are invented.</p>
      <p><b>Confidence (one number):</b> the Jeffreys estimate, (verified + ½) / (units + 1). It is the Bayesian estimate under the Jeffreys prior, whose interval Brown, Cai &amp; DasGupta (2001) recommend for small numbers. It pulls small samples toward the middle, so a PR with 1 verified method gets 75%, not 100%; 6 of 9 gives 65%; 0 of 10 gives 5%. The 95% Jeffreys interval is shown in the details for anyone who wants the uncertainty.</p>
      <p>The confidence describes the <b>test evidence for the changed code</b>. It is not yet the probability that the PR is right: requirement coverage joins it next, and it stays labelled uncalibrated until checked against PRs with known outcomes.</p>
      <p><b>Label</b> (a rule, never overridden by the number): <b className="bad">Fix before merge</b> = a Critical finding, or a test now disagrees with the code. <b className="warn">Check needed</b> = anything open (Major findings, broken tests, changes without test evidence, the reviewer asks a human). <b className="ok">Ready to sign</b> = nothing open and every changed method verified. A named human signs in every case.</p>
      <p><b>Trust level (shown by default):</b> <b className="bad">Low</b> when a failing test or a Critical finding contradicts a changed method (or the PR is labelled Fix before merge), or when even the top of the 95% range says fewer than half of the changed methods are verified. <b className="ok">High</b> when every changed method is verified, nothing contradicts them, the 95% range stays above one half (so at least 3 verified methods), for a whole PR nothing is left to check, and no area is “Not checked”. <b className="warn">Medium</b> is everything in between. The level uses the same counts as the percentage; nothing is weighted. Choose Low / Medium / High or the percentage in Settings (or <code>PRW_TRUST_VIEW</code> in <code>ai-reviewer/.env</code> as the default).</p>
      <p><b>Two parts:</b> “Changed code” is the test evidence above. “Requirement” comes from three blind agents: the analyst reads only the requirement and splits it into checkable items, the interpreter reads only the code and lists what it does, and the judge matches them (met, partly met, missing, contradicted). A “met” without code that the evidence check finds at the cited line becomes “no proof”. A contradicted item stops the merge until the code or the requirement changes.</p>
      <p><b>Not checked:</b> a check that was switched off by the team's coverage level, or did not run (budget reached, model error), is listed as Not checked. It never counts as passed, and it keeps the PR below High.</p>
      <p>Showing a confidence score helps people calibrate their trust in an AI, but it is not enough alone (Zhang, Liao &amp; Bellamy, FAT* 2020), so the reasons are always shown with it.</p>
      <p><b>Affected code</b> uses the same rule, but a test only counts if it also reaches a changed unit, so it actually crosses the link from the change into that code.</p>
      <p><b>"Reaches"</b> means the test's call graph (calls and interface implementations, up to 6 steps) on the world map from the Roslyn Cartographer.</p>
      <p><b>Uncalibrated:</b> following the assurance-case research (Bloomfield &amp; Littlewood; Bloomfield &amp; Rushby), confidence must be checked against known outcomes before it is read as a probability. The planted-bug PRs give us those outcomes.</p>
      <p><b>Finding severity</b> uses the common defect scale: <b className="bad">Critical</b> (must be fixed before merge), <b className="warn">Major</b> (a real problem; a human decides), Minor (optional polish). The reviewer engine names them Blocker / ShouldFix / Nit; they map one-to-one to Conventional Comments: blocking, non-blocking issue, nitpick.</p>
      <p className="note">Next: requirement coverage (ISO/IEC 25023 completeness) and mutation score as the weight of a passing test (Just et al. 2014; Papadakis et al. 2018).</p>
    </div>
  );
}
