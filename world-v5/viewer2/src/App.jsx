import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Command } from "cmdk";
import { getJSON, World, Overlay, NO_OVERLAY, LENSES, LEVEL, VERDICT, range, conf, basis, sev, REVIEWER, lensCounts, displayName, trustShow, TRUST, VIEW, notCheckedAreas, shownSev } from "./model.js";
import { API, api, SettingsPage, PluginsPage, AdminPage, AccessCard, Inbox, TwoPartTrust, Requests, ViewAs } from "./Platform.jsx";
import WorldView from "./WorldView.jsx";
import ClassView from "./ClassView.jsx";
import MethodView from "./MethodView.jsx";
import SidePanel, { Finding } from "./SidePanel.jsx";
import PRPanel, { Method } from "./PRPanel.jsx";
import { Requirement, Calibration } from "./Platform.jsx";
import CodeBlock from "./CodeBlock.jsx";

const DEC = { BLOCKED: "#f07070", NEEDS_HUMAN: "#b39cf0", READY_FOR_SIGNOFF: "#97c459" };
const sevRank = (s) => ({ Blocker: 0, ShouldFix: 1, Nit: 2 }[s] ?? 3);
const tierRank = { high: 0, medium: 1, low: 2, none: 3 };
const store = { get: (k, d) => { try { const v = localStorage.getItem("pw3." + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem("pw3." + k, JSON.stringify(v)); } catch { /* private mode */ } } };

// #/             -> list of pull requests
// #/pr/PR-3?l=module&f=module:Loans&t=flow
// #/world?l=...  -> the whole bank, with the build timeline
function readHash() {
  const raw = location.hash.slice(1);
  if (!raw && VIEW.start === "world") return { page: "world", prId: null, nav: { level: "world", focus: null, tab: null, sel: null } };
  if (!raw && VIEW.start === "feedback") return { page: "latest", prId: null, nav: { level: "world", focus: null, tab: null, sel: null } };
  const [path, q] = (raw || "/").split("?");
  const p = new URLSearchParams(q || "");
  const m = path.match(/^\/pr\/([^/]+)/);
  return { page: m ? "pr" : path.startsWith("/world") ? "world" : "list", prId: m ? decodeURIComponent(m[1]) : null,
    nav: { level: p.get("l") || "world", focus: p.get("f") || null, tab: p.get("t") || null, sel: null } };
}

export default function App() {
  const init = useRef(readHash());
  const [index, setIndex] = useState(null);
  const [error, setError] = useState(null);
  const [meaning, setMeaning] = useState({});
  const [page, setPage] = useState(init.current.page);
  const [prId, setPrId] = useState(init.current.prId);
  const [frame, setFrame] = useState(null);
  const [W, setW] = useState(null);
  const [O0, setO0] = useState(NO_OVERLAY);
  const [mode, setMode] = useState(store.get("mode", { changed: true, affected: false }));
  const [nav, setNav] = useState(init.current.nav);
  const hist = useRef([]);
  const [lens, setLens] = useState("risk");
  const [onlyImpact, setOnlyImpact] = useState(false);
  const [tour, setTour] = useState(-1);
  const [focusF, setFocusF] = useState(null);
  const [palette, setPalette] = useState(false);
  const [modal, setModal] = useState(null);
  const tipApi = useRef(null);   // the tooltip keeps its own state, so hovering never re-renders the whole page
  const setTip = useCallback((t) => { if (tipApi.current) tipApi.current(t); }, []);
  const onHover = useCallback((info) => setTip(info.object && info.object.id ? { x: info.x, y: info.y, id: info.object.id } : null), [setTip]);
  const [playing, setPlaying] = useState(false);
  const [layout, setLayout] = useState(VIEW.start === "feedback" && !location.hash.slice(1) ? "read" : VIEW.layout || "split");
  const [unread, setUnread] = useState(API.me ? API.me.unread : 0);
  const [, setViewRev] = useState(0);
  const [sideW, setSideW] = useState(store.get("sideW", 420));

  useEffect(() => {
    getJSON("index.json").then(setIndex).catch((e) => setError(e.message));
    getJSON("meaning.json").then(setMeaning).catch(() => {});
  }, []);
  useEffect(() => store.set("mode", mode), [mode]);
  useEffect(() => store.set("sideW", sideW), [sideW]);
  useEffect(() => { // start page "Latest PR feedback": the newest PR, panel only
    if (page === "latest" && index && index.prs.length) { const last = index.prs[index.prs.length - 1]; setPage("pr"); setPrId(last.id); }
  }, [page, index]);
  const frames = useMemo(() => (index ? [{ sha: index.seed, label: "Seed" }, ...index.prs.map((p) => ({ sha: p.merged, label: p.id, title: p.title }))] : []), [index]);
  const pr = page === "pr" && index ? index.prs.find((p) => p.id === prId) || null : null;
  const O = useMemo(() => O0.view(mode), [O0, mode]);

  // load the world for the current page
  useEffect(() => {
    if (!index || page === "list") return;
    let file, diffP = null, revP = null, notesP = null;
    if (pr) {
      file = `worlds/${pr.head}.json`;
      diffP = getJSON(`diffs/${pr.id}.json`).catch(() => null);
      revP = getJSON(`reviews/${pr.id}.json`).catch(() => null);
      notesP = getJSON(`notes/${pr.id}.json`).catch(() => null);
    } else { const f = frame == null ? frames.length - 1 : frame; file = `worlds/${(frames[f] || {}).sha || index.main}.json`; }
    Promise.all([getJSON(file), diffP, revP, notesP]).then(([w, d, r, n]) => {
      const nw = new World(w);
      setW(nw);
      setO0(pr ? new Overlay(nw, d, r || { findings: [] }, n) : NO_OVERLAY);
      setNav((cur) => (cur.focus && !nw.node(cur.focus) ? { level: "world", focus: null, tab: null, sel: null } : { ...cur, sel: cur.sel && nw.node(cur.sel) ? cur.sel : null }));
    }).catch((e) => setError(e.message));
  }, [index, page, prId, frame]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setFrame((f) => { const cur = f == null ? frames.length - 1 : f; if (cur >= frames.length - 1) { setPlaying(false); return cur; } return cur + 1; }), 1300);
    return () => clearInterval(t);
  }, [playing, frames.length]);

  // URL <-> state (browser Back works between pages)
  const hashFor = (pg, id, n) => {
    if (pg === "list") return "#/";
    const q = `l=${n.level}${n.focus ? "&f=" + encodeURIComponent(n.focus) : ""}${n.tab ? "&t=" + n.tab : ""}`;
    return pg === "pr" ? `#/pr/${id}?${q}` : `#/world?${q}`;
  };
  useEffect(() => { try { history.replaceState(null, "", hashFor(page, prId, nav)); } catch { /* file:// */ } }, [page, prId, nav]);
  useEffect(() => {
    const onPop = () => { const h = readHash(); setPage(h.page); setPrId(h.prId); setNav(h.nav); };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const goPage = useCallback((pg, id = null) => {
    const n = { level: "world", focus: null, tab: null, sel: null };
    try { history.pushState(null, "", hashFor(pg, id, n)); } catch { /* file:// */ }
    setPage(pg); setPrId(id); setNav(n); hist.current = []; setTour(-1); setFocusF(null); setTip(null);
    if (pg !== "world") setPlaying(false);
  }, []);

  const go = useCallback((n) => { setNav((cur) => { hist.current.push(cur); return { level: n.level, focus: n.focus || null, tab: n.tab || null, sel: n.sel || null }; }); setTip(null); }, []);
  const open = useCallback((id) => {
    if (!W) return;
    const n = W.node(id); if (!n) return;
    if (n.attrs.locked) return setModal({ title: n.name + " — no access", body: <AccessCard name={n.name} node={n} /> });
    if (n.kind === "module") return go({ level: "module", focus: id });
    if (n.kind === "layer") return go({ level: "module", focus: n.parent });
    if (n.kind === "type" || n.kind === "table") return go({ level: "type", focus: id });
    if (n.kind === "method" || n.kind === "ctor") return go({ level: "method", focus: id });
    if (n.kind === "endpoint" && n.attrs.handler && W.node(n.attrs.handler)) return go({ level: "method", focus: n.attrs.handler });
    if (n.kind === "state") return go({ level: "type", focus: n.attrs.owner && W.node(n.attrs.owner) ? n.attrs.owner : n.parent, tab: "state", sel: id });
    const t = W.typeOf(id); if (t) go({ level: "type", focus: t, sel: id });
  }, [W, go]);
  const up = useCallback(() => {
    if (!W) return;
    const n = W.node(nav.focus);
    if (nav.level === "method") go({ level: "type", focus: W.typeOf(n.parent) || n.parent, sel: nav.focus });
    else if (nav.level === "type") go({ level: "module", focus: "module:" + n.module, sel: nav.focus });
    else if (nav.level === "module") go({ level: "world", sel: nav.focus });
  }, [W, nav, go]);
  const back = useCallback(() => { const h = hist.current.pop(); if (h) setNav(h); }, []);
  const select = useCallback((id) => setNav((n) => ({ ...n, sel: id })), []);
  const setTab = useCallback((t) => setNav((n) => ({ ...n, tab: t })), []);
  const toggle = useCallback((k) => setMode((m) => ({ ...m, [k]: !m[k] })), []);

  const tourList = useMemo(() => {
    if (!pr || !W) return [];
    const fs = [...(O.review.findings || [])].sort((a, b) => sevRank(a.severity) - sevRank(b.severity)).map((f) => ({ type: "finding", f }));
    const ch = [...O.changed].filter(([id, how]) => how !== "contains" && W.node(id) && ["method", "ctor", "endpoint", "state"].includes(W.node(id).kind) && !W.isTest(W.node(id)))
      .sort((a, b) => tierRank[W.tier(W.node(a[0]).module)] - tierRank[W.tier(W.node(b[0]).module)]).map(([id]) => ({ type: "change", id }));
    return fs.concat(ch);
  }, [pr, W, O]);
  const focusFinding = useCallback((fid) => {
    const f = (O.review.findings || []).find((x) => x.id === fid); if (!f || !W) return;
    setFocusF(fid);
    const at = f._at && W.node(f._at);
    if (at && (at.kind === "method" || at.kind === "ctor")) go({ level: "method", focus: at.id, tab: "flow" });
    else if (at) go({ level: "type", focus: W.typeOf(at.id) || at.id, sel: at.id });
  }, [O, W, go]);
  const step = useCallback((d) => {
    if (!tourList.length) return;
    const i = (tour + d + tourList.length) % tourList.length;
    setTour(i);
    const it = tourList[i];
    if (it.type === "finding") focusFinding(it.f.id); else open(it.id);
  }, [tour, tourList, focusFinding, open]);
  const showMethod = useCallback(() => setModal({ title: "How trust is computed", body: <Method /> }), []);
  const afterSettings = useCallback(() => { setLayout(VIEW.layout || "split"); setViewRev((x) => x + 1); }, []);
  const [menu, setMenu] = useState(false);
  const pick = (title, body) => { setMenu(false); setModal({ title, body }); };
  const tools = (
    <div className="menuw">
      <button className={"ghost " + (menu ? "on" : "")} onClick={() => setMenu((m) => !m)} aria-haspopup="menu" aria-expanded={menu}>
        {API.on && API.me ? (API.me.mode === "switch" ? <><small className="va">Viewing as</small> {API.me.name}</> : API.me.name) : "Menu"}{unread ? <span className="cnt">{unread}</span> : null} ▾</button>
      {menu && <div className="menu" role="menu" onMouseLeave={() => setMenu(false)}>
        {API.on && <a role="menuitem" onClick={() => pick("Inbox", <Inbox onRead={() => setUnread(0)} />)}>Inbox{unread ? ` (${unread} new)` : ""}</a>}
        <a role="menuitem" onClick={() => pick("Your view", <SettingsPage onSaved={afterSettings} />)}>Settings (your view)</a>
        <a role="menuitem" onClick={() => pick("Plugins and coverage", <PluginsPage />)}>Plugins and coverage</a>
        {API.on && <a role="menuitem" onClick={() => pick("Access requests", <Requests />)}>Access requests</a>}
        {API.on && API.me && API.me.admin && <a role="menuitem" onClick={() => pick("Admin", <AdminPage />)}>Admin</a>}
        {API.on && API.me && API.me.mode === "switch" && <ViewAs />}
        {API.on && API.me && API.me.mode !== "switch" && <div className="msep" title={`roles: ${API.me.roles.join(", ") || "none"}`}>{API.me.id} · {API.me.roles.join(", ") || "no role"}</div>}
        {API.on && API.me && API.me.mode !== "switch" && <a role="menuitem" onClick={() => api("/auth/logout", "POST", {}).finally(() => { location.href = "/login"; })}>Sign out</a>}
      </div>}
    </div>);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); return; }
      if (palette || ["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
      if (e.key === "Escape") { if (modal) return setModal(null); return up(); }
      if (page === "list") return;
      if (e.key === "/") { e.preventDefault(); return setPalette(true); }
      if (e.key === "b" || e.key === "B" || ((e.metaKey || e.ctrlKey) && e.key === "[")) return back();
      if (e.key === "Enter" && nav.sel) return open(nav.sel);
      if (e.key === "j" || e.key === "J") return step(1);
      if (e.key === "k" || e.key === "K") return step(-1);
      if (pr && (e.key === "c" || e.key === "C")) return toggle("changed");
      if (pr && (e.key === "a" || e.key === "A")) return toggle("affected");
      if ((e.key === "o" || e.key === "O") && pr) return setOnlyImpact((v) => !v);
      if (e.key === "\\") return setLayout((l) => (l === "split" ? "map" : l === "map" ? "read" : "split"));
      const l = Object.entries(LENSES).find(([, v]) => v.key === e.key);
      if (l && (nav.level === "world" || nav.level === "module")) setLens(l[0]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [palette, modal, up, back, open, step, nav, pr, page, toggle]);

  // drag the border between map and panel (like VS Code)
  const drag = (e) => {
    e.preventDefault();
    const move = (ev) => setSideW(Math.max(300, Math.min(window.innerWidth - 360, window.innerWidth - ev.clientX)));
    const stop = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); document.body.classList.remove("dragging"); };
    if (layout !== "split") setLayout("split");
    document.body.classList.add("dragging");
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", stop);
  };

  if (error) return <div className="boot">Could not load the world ({error}). <button className="ghost" onClick={() => location.reload()}>Try again</button> If it keeps failing, run <code>./run_world.sh --fresh</code>.</div>;
  if (!index) return <div className="boot">Loading…</div>;
  if (page === "list") return (
    <div className="app list">
      <header className="top">
        <div className="brand"><b>PR World</b><span>review AI-written code by travelling it</span></div>
        <div className="spacer" />
        <button className="ghost" onClick={showMethod}>How trust is computed</button>
        {tools}
      </header>
      <PRList index={index} onOpen={(id) => goPage("pr", id)} onWorld={() => goPage("world")} onPlay={() => { goPage("world"); setFrame(0); setPlaying(true); }} />
      {modal && <Modal modal={modal} close={() => setModal(null)} />}
    </div>);
  if (!W) return <div className="boot">Loading the world…</div>;

  const focusNode = nav.focus && W.node(nav.focus);
  const scene = nav.level === "world" || nav.level === "module";
  const prTests = pr && pr.tests && pr.tests.tests;
  const openCode = (file, line) => setModal({ title: file, body: <CodeBlock W={W} O={O} file={file} from={Math.max(1, line - 8)} to={line + 40} focusLine={line} /> });
  const counts = pr ? lensCounts(W, O0) : null;
  const cols = layout === "map" ? "1fr 6px 0px" : layout === "read" ? "0px 6px 1fr" : `minmax(0,1fr) 6px minmax(300px,min(${sideW}px,46vw))`;

  const crumbs = [<a key="w" onClick={() => go({ level: "world" })}>{pr ? pr.id : "Bank"}</a>];
  if (nav.level !== "world" && focusNode) {
    crumbs.push(<a key="m" onClick={() => go({ level: "module", focus: "module:" + focusNode.module })}>{focusNode.module}</a>);
    if (nav.level === "type" || nav.level === "method") {
      const t = W.node(nav.level === "type" ? nav.focus : W.typeOf(focusNode.parent) || focusNode.parent);
      if (t) { crumbs.push(<span key="l" className="note">{t.layer}</span>); crumbs.push(<a key="t" onClick={() => go({ level: "type", focus: t.id })}>{t.name}</a>); }
    }
    if (nav.level === "method") crumbs.push(<b key="me">{displayName(focusNode)}</b>);
  }

  return (
    <div className="app">
      <header className="top">
        <button className="ghost back" onClick={() => goPage("list")}>← Pull requests</button>
        {pr ? (
          <div className="prh"><b>{pr.id}</b><span className="ttl">{O.notes && O.notes.source === "ai" ? O.notes.headline : pr.title}</span>
            {O.notes && O.notes.verdict ? <span className={"vchip " + VERDICT[O.notes.verdict.label].cls}>{VERDICT[O.notes.verdict.label].label}<em><TwoPartTrust O={O} compact /></em></span>
              : <span className="dec" style={{ color: DEC[O.review.decision] }}>{REVIEWER[O.review.decision] || "no review"}</span>}</div>
        ) : <div className="prh"><b>The whole bank</b><span className="ttl">every module, as built so far</span></div>}
        <div className="spacer" />
        <button className="search" onClick={() => setPalette(true)}><span>Jump to anything</span><kbd>⌘K</kbd></button>
        <button className="ghost" aria-label="Help" onClick={() => setModal({ title: "Travel the world", help: true })}>?</button>
        {tools}
      </header>
      <div className="sub">
        <nav className="crumbs">{crumbs.flatMap((c, i) => (i ? [<span key={"s" + i} className="sep">›</span>, c] : [c]))}</nav>
        {pr && (
          <div className="seg small show" role="group" aria-label="Show">
            <button className={"t-chg " + (mode.changed ? "on" : "")} aria-pressed={mode.changed} onClick={() => toggle("changed")}><i />Changed<kbd>C</kbd></button>
            <button className={"t-aff " + (mode.affected ? "on" : "")} aria-pressed={mode.affected} onClick={() => toggle("affected")}><i />Affected<kbd>A</kbd></button>
          </div>)}
        <div className="spacer" />
        {scene ? <div className="seg small">{Object.entries(LENSES).filter(([k]) => !VIEW.lenses || VIEW.lenses.includes(k) || k === "risk" || k === lens).map(([k, l]) => (
          <button key={k} className={(lens === k ? "on " : "") + (counts && !counts[k] ? "dim" : "")} onClick={() => setLens(k)} title={counts ? `${counts[k]} in this PR` : ""}>
            {l.label}{counts ? <span className="cnt">{counts[k]}</span> : <kbd>{l.key}</kbd>}</button>))}</div>
          : <span className="note">{nav.level === "type" ? "Class view" : "Method view"} · Esc to go up</span>}
        <div className="seg small lay" role="group" aria-label="Layout">
          <button className={layout === "map" ? "on" : ""} onClick={() => setLayout("map")} title="Map only">▣</button>
          <button className={layout === "split" ? "on" : ""} onClick={() => setLayout("split")} title="Map and panel">◫</button>
          <button className={layout === "read" ? "on" : ""} onClick={() => setLayout("read")} title="Panel only (reading)">▤</button>
        </div>
      </div>
      <main style={{ gridTemplateColumns: cols }}>
        <section className="stage">
          {layout !== "read" && scene && <WorldView W={W} O={O} level={nav.level} focus={nav.focus} lens={lens} sel={nav.sel} pr={!!pr} onlyImpact={onlyImpact}
            onSelect={select} onOpen={open} onUp={up} onHover={onHover} />}
          {layout !== "read" && nav.level === "type" && focusNode && <ClassView W={W} O={O} t={focusNode} tab={nav.tab} setTab={setTab} sel={nav.sel} onSelect={select} onOpen={open} prTests={prTests} />}
          {layout !== "read" && nav.level === "method" && focusNode && <MethodView W={W} O={O} m={focusNode} tab={nav.tab} setTab={setTab} onOpen={open} onSelect={select} />}
          {scene && <div className="hud">{nav.level === "world" ? "Double-click or pinch in to open a block" : "Floors are layers · doors lead to other modules · Esc to go up"}{W.lite ? " · links are name-matched guesses (lite cartographer)" : ""}{index.mode && index.mode.mock ? " · rehearsal data" : ""}</div>}
          {scene && <Legend lens={lens} pr={!!pr} level={nav.level} mode={mode} />}
          {scene && <TipHost api={tipApi} W={W} O={O} meaning={meaning} />}
          {layout === "map" && <button className="reopen" onClick={() => setLayout("split")} title="Show the panel">◀ panel</button>}
        </section>
        <div className="splitter" onPointerDown={drag} onDoubleClick={() => setLayout((l) => (l === "map" ? "split" : "map"))} title="Drag to resize · double-click to hide or show" />
        {pr ? (
          <PRPanel W={W} O={O} pr={pr} id={nav.sel || (nav.level !== "world" ? nav.focus : null)} mode={mode} focusF={focusF} meaning={meaning} lens={nav.level === "world" || nav.level === "module" ? lens : null}
            onOpen={open} onFinding={focusFinding} onCode={openCode} onMethod={showMethod} onModal={(title, body) => setModal({ title, body })}
            onIssue={() => setModal({ title: pr.id + " — requirement", req: true, pr, review: O.review, onCode: openCode })} />
        ) : (
          <SidePanel W={W} O={O} id={nav.sel || (nav.level !== "world" ? nav.focus : null)} meaning={meaning} pr={false} prInfo={null} focusF={focusF}
            onOpen={open} onFinding={focusFinding} onCode={openCode} onIssue={() => {}} />
        )}
      </main>
      <footer className="bottom">
        {pr ? (
          <>
            <div className="seg small"><button onClick={() => step(-1)} aria-label="Previous">◀</button><button className={tour >= 0 ? "on" : ""} onClick={() => step(1)}>Guided tour {tour >= 0 ? `${tour + 1}/${tourList.length}` : `(${tourList.length})`}</button><button onClick={() => step(1)} aria-label="Next">▶</button></div>
            <button className={"ghost " + (onlyImpact ? "on" : "")} onClick={() => setOnlyImpact((v) => !v)}>Fade the rest</button>
            <div className="spacer" />
            <span className="note">findings {(O.review.findings || []).length} · {pr.tests && pr.tests.ran ? (O.notes && O.notes.verdict ? `new test failures ${O.notes.verdict.failures.new} · broken ${O.notes.verdict.failures.broken} · from earlier PRs ${O.notes.verdict.failures.inherited}` : `tests ${pr.tests.passed}✓ ${pr.tests.failed}✕`) : "tests not run"} · builder {pr.builder.source}{O.notes ? ` · notes: ${O.notes.source === "ai" ? "AI" : "facts only"}` : ""}</span>
          </>
        ) : (
          <>
            <button className="ghost" onClick={() => { if (!playing && (frame == null || frame >= frames.length - 1)) setFrame(0); setPlaying((p) => !p); go({ level: "world" }); }}>{playing ? "Pause" : "Play the build"}</button>
            <input type="range" min={0} max={frames.length - 1} step={1} value={frame == null ? frames.length - 1 : frame} onChange={(e) => { setPlaying(false); setFrame(+e.target.value); }} aria-label="Timeline" />
            <span className="frame">{(frames[frame == null ? frames.length - 1 : frame] || {}).label}{(frames[frame == null ? frames.length - 1 : frame] || {}).title ? " · " + frames[frame == null ? frames.length - 1 : frame].title : ""}</span>
            <div className="spacer" />
            <span className="note">cartographer: <b>{index.mode.cartographer}</b>{index.mode.mock ? " · rehearsal" : ""}</span>
          </>
        )}
      </footer>

      <Command.Dialog open={palette} onOpenChange={setPalette} label="Jump to anything" className="palette">
        <Command.Input placeholder="Type a module, class, method, API, table or state…" autoFocus />
        <Command.List>
          <Command.Empty>Nothing in the world matches.</Command.Empty>
          <Command.Group heading="Go">
            <Command.Item onSelect={() => { goPage("list"); setPalette(false); }}>All pull requests</Command.Item>
            <Command.Item onSelect={() => { go({ level: "world" }); setPalette(false); }}>Overview</Command.Item>
            {index.prs.map((p) => <Command.Item key={p.id} value={"review " + p.id + " " + p.title} onSelect={() => { goPage("pr", p.id); setPalette(false); }}>Review {p.id}: {p.title}</Command.Item>)}
            {Object.entries(LENSES).map(([k, l]) => <Command.Item key={k} value={"lens " + l.label} onSelect={() => { setLens(k); setPalette(false); }}>Lens: {l.label}</Command.Item>)}
          </Command.Group>
          {[["Modules", ["module"]], ["Classes and tables", ["type", "table"]], ["Methods", ["method", "ctor"]], ["APIs", ["endpoint"]], ["States", ["state"]]].map(([h, kinds]) => (
            <Command.Group key={h} heading={h}>
              {W.nodes.filter((n) => kinds.includes(n.kind) && !W.isTest(n) && !n.attrs.locked).map((n) => {
                const p = W.node(n.parent);
                return (<Command.Item key={n.id} value={`${displayName(n)} ${n.module} ${p && p.kind === "type" ? p.name : ""} ${n.id}`} onSelect={() => { open(n.id); setPalette(false); }}>
                  <span>{displayName(n)}</span><span className="pk">{n.kind === "type" ? n.attrs.type_kind : n.kind} · {n.module}{p && p.kind === "type" ? " · " + p.name : ""}</span>
                  {O.status(n.id) && <span className={"pill p-" + O.status(n.id)}>{O.status(n.id) === "impacted" ? "affected" : "changed"}</span>}
                </Command.Item>);
              })}
            </Command.Group>))}
        </Command.List>
      </Command.Dialog>
      {modal && <Modal modal={modal} close={() => setModal(null)} />}
    </div>
  );
}

function Modal({ modal, close }) {
  return (
    <div className="ovl" onClick={close}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="mh"><b>{modal.title}</b><button className="x" onClick={close} aria-label="Close">✕</button></div>
        <div className="mbody">{modal.help ? <Help /> : modal.req ? <Requirement pr={modal.pr} review={modal.review} onCode={(f, l) => { close(); modal.onCode(f, l); }} /> : modal.body}</div>
      </div>
    </div>);
}

// GitHub-like list: pick a PR, then travel only what it touches
function PRList({ index, onOpen, onWorld, onPlay }) {
  const [notes, setNotes] = useState({});
  useEffect(() => { index.prs.forEach((p) => getJSON(`notes/${p.id}.json`).then((n) => setNotes((s) => ({ ...s, [p.id]: n }))).catch(() => {})); }, [index]);
  return (
    <div className="prlist">
      <div className="plh">
        <div><h2>Pull requests</h2><div className="note">Written by the agent team · tested by a blind Test agent · reviewed by the AI reviewer · signed by a named human</div></div>
        <div className="spacer" />
        <button className="ghost" onClick={onWorld}>Explore the whole bank</button>
        <button className="ghost" onClick={onPlay}>▶ Play the build</button>
      </div>
      <div className="prt">
        <div className="prrow head"><span>Pull request</span><span>Verdict and why</span><span>{TRUST.view === "percent" ? "Confidence" : "Trust (changed code)"}</span><span>Reviewer findings</span><span>New test failures</span><span>Business impact</span></div>
        {index.prs.slice().reverse().map((p) => {
          const n = notes[p.id], s = n && n.roll.pr && n.roll.pr.changed, rv = p.review || {};
          const t = s ? trustShow(s, n.verdict && n.verdict.label) : null;
          const fs = n ? n.findings.filter((f) => shownSev(f.severity)) : [], folded = n ? n.findings.length - fs.length : 0;
          const mods = n ? [...new Set(Object.keys(n.roll).filter((k) => k.startsWith("module:") && n.roll[k].changed).map((k) => k.slice(7)))] : [];
          return (
            <a key={p.id} className="prrow" onClick={() => onOpen(p.id)}>
              <span className="pt"><b><i className={"dot " + (n && n.verdict ? VERDICT[n.verdict.label].cls : "")} style={n && n.verdict ? {} : { background: DEC[rv.decision] || "#5d7398" }} />{p.id}</b> {p.title}
                <small>{n && n.source === "ai" ? n.headline : mods.length ? "Changes: " + mods.join(", ") : ""}</small></span>
              <span>{n && n.verdict ? <><span className={"vchip " + VERDICT[n.verdict.label].cls}>{VERDICT[n.verdict.label].label}</span><small className="why">{(n.verdict.reasons[0] || {}).text || ""}</small></>
                : <><b style={{ color: DEC[rv.decision] }}>{REVIEWER[rv.decision] || "—"}</b><small>tier {rv.tier || "?"}</small></>}</span>
              <span>{s ? <><b className={"big " + (TRUST.view === "percent" ? "" : t.cls)} title={t.title}>{t.text}</b><small>{basis(s)}</small>
                <span className="bar mini">{[["verified", s.verified], ["contradicted", s.contradicted], ["not_run", s.not_run], ["none", s.none]].filter(([, v]) => v).map(([k, v]) => <i key={k} className={"lv-" + k} style={{ flex: v }} />)}</span>
                </> : <small>no notes yet</small>}</span>
              <span className="fcol">{n ? (fs.length ? <>{[...fs].sort((x, y) => sev(x.severity).rank - sev(y.severity).rank).slice(0, 2).map((f) => (
                  <span key={f.id} className="fl"><span className={"sv " + sev(f.severity).cls}>{sev(f.severity).label}</span> {f.title}</span>))}
                  {fs.length > 2 && <small>+{fs.length - 2} more ({["Blocker", "ShouldFix", "Nit"].map((k) => { const c = [...fs].sort((x, y) => sev(x.severity).rank - sev(y.severity).rank).slice(2).filter((f) => f.severity === k).length; return c ? `${c} ${sev(k).label}` : ""; }).filter(Boolean).join(", ")})</small>}
                  {folded > 0 && <small className="mute">{folded} hidden by your filter</small>}</>
                : folded ? <small className="mute">{folded} hidden by your filter</small> : <span className="ok">None</span>) : <b>{rv.findings ?? "—"}</b>}</span>
              <span>{p.tests && p.tests.ran ? (n && n.verdict ? <><b className={n.verdict.failures.new ? "bad" : "ok"}>{n.verdict.failures.new}</b>
                <small>{[n.verdict.failures.broken && `${n.verdict.failures.broken} broken`, n.verdict.failures.inherited && `${n.verdict.failures.inherited} from earlier PRs`].filter(Boolean).join(" · ") || `${p.tests.passed} cases pass`}</small></>
                : <><b className="ok">{p.tests.passed}✓</b> <b className={p.tests.failed ? "bad" : "mute"}>{p.tests.failed}✕</b></>) : <small>not run</small>}</span>
              <span>{n && n.source === "ai" ? <b className={{ high: "bad", medium: "warn", low: "ok" }[n.business_impact] || "mute"}>{n.business_impact}</b> : <small>—</small>}</span>
            </a>);
        })}
      </div>
      {(index.not_merged || []).length > 0 && (
        <div className="nm"><b>Not merged ({index.not_merged.length})</b>
          {index.not_merged.map((x) => <div key={x.id} className="nmr"><b>{x.id}</b> {x.title} <span className="sv warn">{x.status}</span> <small>{x.reason}</small></div>)}
        </div>)}
      <p className="note foot">{TRUST.view === "percent" ? "" : "Trust level (Low / Medium / High) comes from the same counts as the percentage; see How trust is computed. "}Confidence = how much of the changed code is verified by passing tests, as one number: (verified + ½) / (methods + 1), the Jeffreys estimate, so a PR with 1 method is not called 100%. The label is a rule; the number never overrides it. Both stay labelled uncalibrated until checked against PRs with known outcomes.
        {index.prs.some((p) => /review-policy\.yaml is not approved/.test((p.review || {}).reason || "")) ? " The reviewer's rulebook (review-policy.yaml) is not yet approved by a named human." : ""}
        {index.mode && index.mode.mock ? " Rehearsal data." : ` Models: ${Object.values(index.mode.models || {})[0] || "?"} for every agent.`}</p>
    </div>
  );
}

function TipHost({ api, W, O, meaning }) {
  const [tip, setTip] = useState(null);
  useEffect(() => {
    api.current = (t) => setTip((cur) => (!t && !cur ? cur : t && cur && t.id === cur.id && Math.abs(t.x - cur.x) < 2 && Math.abs(t.y - cur.y) < 2 ? cur : t));
    return () => { api.current = null; };
  }, [api]);
  return tip ? <Tip W={W} O={O} tip={tip} meaning={meaning} /> : null;
}

function Tip({ W, O, tip, meaning }) {
  const id = tip.id.startsWith("door:") ? "module:" + tip.id.slice(5) : tip.id;
  const n = W.node(id); if (!n) return null;
  const m = meaning[id] || (n.attrs.summary ? { summary: n.attrs.summary } : null);
  const st = O.status(id);
  return (
    <div className="tip" style={{ left: tip.x + 16, top: tip.y + 16 }}>
      <b>{tip.id.startsWith("door:") ? "Door to " + n.name : displayName(n)}</b>
      <em>{n.kind === "module" ? `${n.attrs.area || n.name} · ${n.attrs.tier || "?"} risk` : `${n.kind === "type" ? n.attrs.type_kind : n.kind} · ${n.module}/${n.layer || ""}`}</em>
      {m && <div>{m.summary}</div>}
      {st && <em>PR: {st === "impacted" ? "affected" : "changed"}{O.roll(id) && O.roll(id)[st === "impacted" ? "affected" : "changed"] ? ` · ${O.roll(id)[st === "impacted" ? "affected" : "changed"].verified}/${O.roll(id)[st === "impacted" ? "affected" : "changed"].n} verified` : ""}</em>}
      <em>{tip.id.startsWith("door:") ? "Click to travel there" : "Double-click to open"}</em>
    </div>
  );
}
function Legend({ lens, pr, level, mode }) {
  const L = {
    risk: [["sw", "#a84e42", "high risk"], ["sw", "#ac843a", "medium"], ["sw", "#42845c", "low"], ["t", "", "height = amount inside"]],
    calls: [["ln", "#96aac8", "calls (thicker = more)"]], apis: [["sw", "#345caa", "has HTTP APIs"], ["ln", "#5e96eb", "where a request travels"]],
    events: [["ln", "#b296f5", "event published → delivered"]], data: [["ln", "#5dcaa5", "reads / writes"], ["t", "", "PII = personal-data fields"]],
    security: [["sw", "#42845c", "all APIs protected"], ["sw", "#a84e42", "an API is open"], ["ln", "#96aac8", "Auth guards it"]],
    tests: [["sw", "#42845c", "≥60% tested"], ["sw", "#ac843a", "some"], ["sw", "#a84e42", "none"], ["ln", "#97c459", "tests call it"]],
  }[lens];
  const mod = [["sw", "#345caa", "controller"], ["sw", "#46567a", "class"], ["sw", "#3a4862", "interface"], ["sw", "#2c7666", "record"], ["sw", "#6e52aa", "event"], ["sw", "#967030", "enum / states"], ["t", "", "⇄ door to another module"]];
  const items = (level === "module" ? mod : L).concat(pr && mode.changed ? [["sw", "#963234", "changed"]] : []).concat(pr && mode.affected ? [["sw", "#705426", "affected"]] : []).concat(pr ? [["ln", "#f07070", "path of the change"], ["t", "", "n/m ✓ = verified by tests"]] : []);
  return <div className="legend">{items.map(([k, c, t], i) => <span key={i}>{k === "sw" && <i style={{ background: c }} />}{k === "ln" && <s style={{ borderColor: c }} />}{t}</span>)}</div>;
}
function Help() {
  return (
    <table className="vars"><thead><tr><th>Do</th><th>Mouse</th><th>Trackpad</th><th>Touch</th><th>Keys</th></tr></thead><tbody>
      <tr><td>Open a block / class / method</td><td>double-click</td><td>pinch out over it</td><td>double-tap</td><td>Enter</td></tr>
      <tr><td>Go up a level</td><td>↑ button</td><td>pinch in</td><td>↑ button</td><td>Esc</td></tr>
      <tr><td>Back to where you were</td><td colSpan={3}>—</td><td>B</td></tr>
      <tr><td>Pan / zoom</td><td>drag / wheel</td><td>two fingers / pinch</td><td>drag / pinch</td><td>+ −</td></tr>
      <tr><td>Jump to anything</td><td colSpan={3}>search button</td><td>⌘K or /</td></tr>
      <tr><td>Change lens</td><td colSpan={3}>lens bar</td><td>1–7</td></tr>
      <tr><td>Guided tour of a PR</td><td colSpan={3}>◀ ▶ at the bottom</td><td>J / K</td></tr>
      <tr><td>Show changed / affected</td><td colSpan={3}>toggles in the top bar</td><td>C / A</td></tr>
      <tr><td>Fade everything else</td><td colSpan={3}>button at the bottom</td><td>O</td></tr>
      <tr><td>Map only / split / panel only</td><td colSpan={3}>▣ ◫ ▤, drag or double-click the border</td><td>\\</td></tr>
    </tbody></table>
  );
}

