import { useEffect, useMemo, useRef, useState } from "react";
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType } from "@xyflow/react";
import ELK from "elkjs/lib/elk.bundled.js";
import { displayName, shortType, LEVEL, sev } from "./model.js";
import CodeBlock from "./CodeBlock.jsx";

const elk = new ELK();

// ---------------------------------------------------------------- flowchart from the step tree
function buildFlow(steps, name) {
  const nodes = [{ id: "start", kind: "start", text: name }], edges = [];
  let c = 0;
  const link = (entries, to) => entries.forEach((e) => edges.push({ id: `e${edges.length}`, source: e.from, target: to, label: e.label || "", back: !!e.back }));
  const build = (list, entries) => {
    for (const s of list) {
      const id = "n" + c++;
      nodes.push({ id, kind: s.kind, s });
      link(entries, id);
      if (s.kind === "if") {
        const yes = build(s.then || [], [{ from: id, label: "yes" }]);
        const no = (s.else || []).length ? build(s.else, [{ from: id, label: "no" }]) : [{ from: id, label: "no" }];
        entries = yes.concat(no);
      } else if (s.kind === "loop") {
        const body = build(s.body || [], [{ from: id, label: "each" }]);
        body.forEach((e) => edges.push({ id: `e${edges.length}`, source: e.from, target: id, label: "next", back: true }));
        entries = [{ from: id, label: "done" }];
      } else if (s.kind === "using" || s.kind === "block") {
        entries = build(s.body || [], [{ from: id }]);
      } else if (s.kind === "try") {
        const body = build(s.body || [], [{ from: id }]);
        const caught = (s.catches || []).flatMap((ct) => {
          const cid = "n" + c++;
          nodes.push({ id: cid, kind: "catch", s: { text: ct.text, line: ct.line, calls: [], publishes: [], triggers: [], tables: [] } });
          edges.push({ id: `e${edges.length}`, source: id, target: cid, label: "on error" });
          return build(ct.body || [], [{ from: cid }]);
        });
        entries = body.concat(caught);
      } else if (s.kind === "return" || s.kind === "throw") {
        entries = [];
      } else entries = [{ from: id }];
    }
    return entries;
  };
  const exits = build(steps || [], [{ from: "start" }]);
  if (exits.length) { nodes.push({ id: "end", kind: "end", text: "end" }); link(exits, "end"); }
  return { nodes, edges };
}
const width = (n) => (n.kind === "start" || n.kind === "end" ? 180 : Math.min(460, Math.max(200, 9 + (n.s.text.length + 4) * 6.6)));
const height = (n) => {
  if (n.kind === "start" || n.kind === "end") return 40;
  const lines = Math.ceil(((n.s.text.length + 4) * 6.6) / (width(n) - 20));
  const fx = (n.s.calls?.length || 0) + (n.s.publishes?.length || 0) + (n.s.triggers?.length || 0) + (n.s.tables?.length || 0);
  return 22 + lines * 17 + (fx ? 24 : 0) + (n.f ? 18 : 0);
};

function StepNode({ data }) {
  const { n, W, O, file, onOpen, onSelect } = data;
  if (n.kind === "start" || n.kind === "end") return (<div className={"fstep k-" + n.kind}><Handle type="target" position={Position.Top} /><b>{n.text}</b><Handle type="source" position={Position.Bottom} /></div>);
  const s = n.s, chg = O.changedLine(file, s.line);
  const chips = [];
  (s.calls || []).forEach((id) => { const t = W.node(id); if (t) chips.push(<span key={"c" + id} className="chip c-call click" onClick={(e) => { e.stopPropagation(); onOpen(id); }}>{(W.node(t.parent) || {}).name}.{displayName(t)}</span>); });
  (s.publishes || []).forEach((id) => { const t = W.node(id); if (t) chips.push(<span key={"p" + id} className="chip c-ev click" onClick={(e) => { e.stopPropagation(); onOpen(id); }}>⚡ {t.name}</span>); });
  (s.triggers || []).forEach((id) => { const t = W.node(id); if (t) chips.push(<span key={"t" + id} className="chip c-state click" onClick={(e) => { e.stopPropagation(); onSelect(id); }}>→ {t.name}</span>); });
  (s.tables || []).forEach((x) => { const [mode, id] = x.split(" "); const t = W.node(id); if (t) chips.push(<span key={"d" + x} className="chip c-data click" onClick={(e) => { e.stopPropagation(); onOpen(id); }}>{mode === "writes" ? "✎" : "⌕"} {t.name}</span>); });
  return (
    <div className={`fstep k-${n.kind} ${chg ? "chg" : ""}`} style={{ width: width(n) }}>
      <Handle type="target" position={Position.Top} />
      <div><span className="ln">{s.line}</span>{s.text}</div>
      {chips.length > 0 && <div className="fx">{chips}</div>}
      {n.f && <div className="fnd">! {sev(n.f.severity).label}: {n.f.title}</div>}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
function FlowTab({ W, O, m, onOpen, onSelect }) {
  const steps = (W.w.flows || {})[m.id];
  const graph = useMemo(() => {
    const g = buildFlow(steps, displayName(m));
    const fs = (O.review.findings || []).filter((f) => f.file === m.file);
    g.nodes.forEach((n) => { if (n.s) n.f = fs.find((f) => f.line_start <= n.s.line && (f.line_end || f.line_start) >= n.s.line); });
    return g;
  }, [steps, m, O]);
  const [pos, setPos] = useState(null);
  useEffect(() => {
    setPos(null);
    const g = { id: "root", layoutOptions: { "elk.algorithm": "layered", "elk.direction": "DOWN", "elk.spacing.nodeNode": "28", "elk.layered.spacing.nodeNodeBetweenLayers": "34", "elk.edgeRouting": "ORTHOGONAL", "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF" },
      children: graph.nodes.map((n) => ({ id: n.id, width: width(n), height: height(n) })),
      edges: graph.edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })) };
    elk.layout(g).then((r) => setPos(Object.fromEntries(r.children.map((c) => [c.id, { x: c.x, y: c.y }])))).catch(() => setPos({}));
  }, [graph]);
  const box = useRef(null);
  if (!steps) return <p className="empty">No body (interface member or abstract).</p>;
  if (!pos) return <p className="note">Laying out the flow…</p>;
  const gw = Math.max(...graph.nodes.map((n) => (pos[n.id]?.x || 0) + width(n)), 200);
  const onInit = (inst) => {
    const w = box.current ? box.current.clientWidth : 900;
    const zoom = Math.min(1, (w - 40) / gw);
    inst.setViewport({ x: (w - gw * zoom) / 2, y: 16, zoom });
  };
  const nodes = graph.nodes.map((n) => ({ id: n.id, type: "step", position: pos[n.id] || { x: 0, y: 0 }, data: { n, W, O, file: m.file, onOpen, onSelect }, draggable: false }));
  const edges = graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, label: e.label, type: "smoothstep",
    labelStyle: { fill: e.label === "yes" ? "#97c459" : e.label === "no" ? "#f09595" : "#8ea0bd", fontSize: 11, fontWeight: 600 }, labelBgStyle: { fill: "#0f1622" },
    style: { stroke: e.back ? "#5d7398" : "#7d90b2", strokeDasharray: e.back ? "5 4" : undefined, strokeWidth: 1.5 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#7d90b2" } }));
  return (
    <>
      <div className="flowbox tall" ref={box}>
        <ReactFlow panOnScroll panOnScrollSpeed={1} zoomOnScroll={false} zoomOnPinch nodes={nodes} edges={edges} nodeTypes={{ step: StepNode }} onInit={onInit} minZoom={0.15} nodesConnectable={false} proOptions={{ hideAttribution: true }} colorMode="dark">
          <Background gap={24} color="#1d2940" /><Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p className="note">Amber boxes are decisions, blue are loops, green ends return, red ends throw; red outline = changed in this PR. Chips show what each step touches; click to travel.</p>
    </>
  );
}

// ---------------------------------------------------------------- sequence diagram
function SequenceTab({ W, O, m, onOpen, onSelect }) {
  const { lanes, msgs } = useMemo(() => {
    const lanes = [], idx = new Map(), msgs = [];
    const lane = (key, label, kind) => { if (!idx.has(key)) { idx.set(key, lanes.length); lanes.push({ key, label, kind }); } return idx.get(key); };
    const typeLane = (id) => { const t = W.typeOf(id), n = W.node(t); return lane(t, n ? n.name : "?", n && n.kind === "table" ? "db" : n && n.attrs.is_event ? "event" : "type"); };
    const seen = new Set();
    const all = W.nodes.find((n) => n.kind === "type" && n.name === "IDomainEvent");
    const subs = (ev) => W.edges.filter((e) => e.kind === "subscribes" && (e.target === ev || (all && e.target === all.id))).map((e) => e.source).filter((x) => !W.isTest(W.node(x)));
    const visit = (mid, depth) => {
      if (msgs.length > 70 || depth > 4 || seen.has(mid)) return;
      seen.add(mid);
      const from = typeLane(mid);
      W.outE(mid).filter((e) => ["calls", "publishes", "writes", "reads", "triggers"].includes(e.kind)).sort((a, b) => (a.line || 0) - (b.line || 0)).forEach((e) => {
        if (e.kind === "calls") {
          const tgt = W.implOf(e.target), tn = W.node(tgt);
          if (!tn || W.isTest(tn) || (["PublishAsync", "TransitionTo"].includes(tn.name) && tn.module === "Platform")) return;
          msgs.push({ from, to: typeLane(tgt), label: displayName(tn), id: tgt, depth, kind: "call", hot: O.hotEdge(e) || O.status(tgt) === "changed" });
          visit(tgt, depth + 1);
        } else if (e.kind === "publishes") {
          const to = typeLane(e.target);
          msgs.push({ from, to, label: "publish " + W.node(e.target).name, id: e.target, depth, kind: "event", hot: O.hotEdge(e) });
          subs(e.target).forEach((h) => { msgs.push({ from: to, to: typeLane(h), label: "deliver → " + displayName(W.node(h)), id: h, depth, kind: "deliver" }); visit(h, depth + 1); });
        } else if (e.kind === "triggers") {
          msgs.push({ from, to: from, label: "state → " + W.node(e.target).name, id: e.target, depth, kind: "state" });
        } else {
          msgs.push({ from, to: lane("db:" + e.target, "▦ " + W.node(e.target).name, "db"), label: e.kind === "writes" ? "write" : "read", id: e.target, depth, kind: "data", hot: O.hotEdge(e) });
        }
      });
    };
    lane(W.typeOf(m.id), W.node(W.typeOf(m.id)).name, "type");
    visit(m.id, 0);
    return { lanes, msgs };
  }, [W, O, m]);
  const LW = 160, top = 50, RH = 32, Wd = Math.max(640, lanes.length * LW + 40), Hd = top + msgs.length * RH + 40;
  const x = (i) => 20 + i * LW + LW / 2;
  const COL = { call: "#9fb3d6", event: "#b39cf0", deliver: "#b39cf0", data: "#5dcaa5", state: "#fac775" };
  return (
    <>
      <div className="seqbox">
        <svg width={Wd} height={Hd}>
          <defs>{["#9fb3d6", "#b39cf0", "#5dcaa5", "#fac775", "#f07070"].map((c) => <marker key={c} id={"q" + c.slice(1)} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M1 1L9 5L1 9z" fill={c} /></marker>)}</defs>
          {lanes.map((l, i) => (
            <g key={l.key}>
              <rect x={x(i) - LW / 2 + 6} y={8} width={LW - 12} height={30} rx={8} fill={l.kind === "db" ? "#123a35" : l.kind === "event" ? "#2c2450" : "#1b2840"} stroke="#3a4f75" />
              <text x={x(i)} y={28} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="#e4ecf8">{l.label.length > 20 ? l.label.slice(0, 19) + "…" : l.label}</text>
              <line x1={x(i)} y1={38} x2={x(i)} y2={Hd - 10} stroke="#2c3b57" strokeDasharray="4 4" />
            </g>))}
          {msgs.map((g, i) => {
            const y = top + i * RH + 14, x1 = x(g.from), x2 = x(g.to), c = g.hot ? "#f07070" : COL[g.kind];
            return (
              <g key={i} style={{ cursor: "pointer" }} onClick={() => onSelect(g.id)} onDoubleClick={() => onOpen(g.id)}>
                {g.from === g.to ? <path d={`M${x1} ${y - 6} h28 v12 h-26`} fill="none" stroke={c} strokeWidth={1.5} markerEnd={`url(#q${c.slice(1)})`} />
                  : <line x1={x1} y1={y} x2={x2 + (x2 > x1 ? -3 : 3)} y2={y} stroke={c} strokeWidth={g.hot ? 2.6 : 1.5} strokeDasharray={g.kind === "deliver" ? "5 4" : undefined} markerEnd={`url(#q${c.slice(1)})`} />}
                <text x={g.from === g.to ? x1 + 34 : (x1 + x2) / 2} y={y - 6} textAnchor={g.from === g.to ? "start" : "middle"} fontSize={12} fill={c}>{"· ".repeat(Math.min(g.depth, 3))}{g.label}</text>
              </g>);
          })}
        </svg>
        {!msgs.length && <p className="empty">This method calls nothing else in the world.</p>}
      </div>
      <p className="note">Who talks to whom, in order. Calls through interfaces are followed to the real class; events are delivered to their handlers. Click to select, double-click to open.</p>
    </>
  );
}

function DataTab({ W, m, goLine }) {
  const vars = (W.w.dataflow || {})[m.id] || [];
  if (!vars.length) return <p className="empty">No variables.</p>;
  return (
    <table className="vars"><thead><tr><th>Name</th><th>Kind</th><th>Type</th><th>Written at line</th><th>Read at line</th></tr></thead><tbody>
      {vars.map((v) => (<tr key={v.name + v.kind}><td className="mono"><b>{v.name}</b></td><td>{v.kind}</td><td className="mono">{shortType(v.type)}</td>
        <td>{v.writes.length ? v.writes.map((l) => <span key={l} className="lnk" onClick={() => goLine(l)}>{l}</span>) : "—"}</td>
        <td>{v.reads.length ? v.reads.map((l) => <span key={l} className="lnk" onClick={() => goLine(l)}>{l}</span>) : "—"}</td></tr>))}
    </tbody></table>
  );
}

export default function MethodView({ W, O, m, tab, setTab, onOpen, onSelect }) {
  const owner = W.node(m.parent);
  const [line, setLine] = useState(null);
  const tabs = [["flow", "Flow"], ["sequence", "Sequence"], ["data", "Data flow"], ["code", "Code"]];
  const cur = tabs.some(([k]) => k === tab) ? tab : "flow";
  const eps = W.children(owner.id).filter((e) => e.kind === "endpoint" && e.attrs.handler === m.id);
  const testers = W.inE(m.id).filter((e) => e.kind === "calls" && W.isTest(W.node(e.source)));
  const st = O.status(m.id);
  return (
    <div className="flat">
      <div className="vhead">
        <div><div className="note"><a className="lnk" onClick={() => onOpen(owner.id)}>{owner.name}</a> · {m.module} / {m.layer}</div><h2>{displayName(m)}</h2><div className="sig">{m.attrs.signature}</div></div>
        <div className="pills">
          <span className={"pill t-" + W.tier(m.module)}>{W.tier(m.module)} risk</span>
          {eps.map((e) => <span key={e.id} className="pill p-api" title={(e.attrs.auth || []).join(", ")}>{e.name}</span>)}
          {O.unit(m.id) ? <span className={"pill c-lv-" + O.unit(m.id).level}>{LEVEL[O.unit(m.id).level].icon} {LEVEL[O.unit(m.id).level].short}{O.unit(m.id).tests.passed_n + O.unit(m.id).tests.failed_n ? ` · ${O.unit(m.id).tests.passed_n}✓ ${O.unit(m.id).tests.failed_n}✕` : ""}</span>
            : W.tested.has(m.id) ? <span className="pill p-ok">tested{testers.length ? ` by ${testers.length}` : " via interface"}</span> : !W.isTest(m) && <span className="pill p-grey">no direct test</span>}
          {st && <span className={"pill p-" + st}>{O.isNew(m.id) ? "new" : st === "impacted" ? "affected" : st}</span>}
        </div>
      </div>
      {W.lite && <div className="lite">Links here are name-matched guesses (lite cartographer). Run with .NET for proven links.</div>}
      <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={cur === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      {cur === "flow" && <FlowTab W={W} O={O} m={m} onOpen={onOpen} onSelect={onSelect} />}
      {cur === "sequence" && <SequenceTab W={W} O={O} m={m} onOpen={onOpen} onSelect={onSelect} />}
      {cur === "data" && <DataTab W={W} m={m} goLine={(l) => { setLine(l); setTab("code"); }} />}
      {cur === "code" && <CodeBlock W={W} O={O} file={m.file} from={Math.max(1, m.line - 3)} to={m.end_line + 2} focusLine={line} />}
    </div>
  );
}
