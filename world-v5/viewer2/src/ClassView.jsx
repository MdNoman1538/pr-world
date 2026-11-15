import { useEffect, useMemo, useState } from "react";
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType } from "@xyflow/react";
import ELK from "elkjs/lib/elk.bundled.js";
import { displayName, shortType, LEVEL } from "./model.js";
import CodeBlock from "./CodeBlock.jsx";

const elk = new ELK();
const VIS = { public: "+", private: "−", protected: "#", internal: "~" };

export function relations(W, O, t, dir) {
  const mine = new Set([t.id, ...W.descendants(t.id).map((n) => n.id)]);
  const groups = new Map();
  const kinds = dir === "in" ? ["calls", "resolves", "injects", "routes", "publishes", "subscribes", "maps", "reads", "writes"] : ["calls", "resolves", "injects", "publishes", "writes", "reads", "triggers", "maps", "implements", "inherits"];
  const list = [...mine].flatMap((id) => (dir === "in" ? W.inE(id) : W.outE(id)));
  const add = (key, kind, row, hot) => {
    const g = groups.get(key) || { id: key, kinds: new Set(), rows: new Set(), count: 0, hot: false };
    g.kinds.add(kind); g.count++; g.rows.add(row); g.hot = g.hot || hot; groups.set(key, g);
  };
  list.forEach((e) => {
    if (!kinds.includes(e.kind)) return;
    const other = dir === "in" ? e.source : e.target;
    if (mine.has(other)) return;
    const on = W.node(other); if (!on) return;
    const key = on.kind === "endpoint" ? other : W.typeOf(other) || other;
    add(key, e.kind, W.memberOf(dir === "in" ? e.target : e.source) || t.id, O.hotEdge(e));
  });
  if (dir === "in") {
    [...mine].forEach((id) => W.inE(id).filter((e) => e.kind === "resolves").forEach((r) => {
      W.inE(r.source).filter((c) => c.kind === "calls" && !mine.has(c.source)).forEach((c) => {
        const key = W.typeOf(c.source) || c.source;
        if (!mine.has(key)) add(key, "calls via " + (W.node(W.typeOf(r.source)) || {}).name, id, O.hotEdge(c));
      });
    }));
  }
  return [...groups.values()].sort((a, b) => (W.isTest(W.node(a.id)) - W.isTest(W.node(b.id))) || b.count - a.count);
}

function ClassCard({ data }) {
  const { t, rows, sel, onSelect, onOpen } = data;
  return (
    <div className="uml">
      <Handle type="target" position={Position.Left} id="in-__type" style={{ top: 30 }} />
      <Handle type="source" position={Position.Right} id="out-__type" style={{ top: 30 }} />
      <div className="uh"><div className="st">«{t.kind === "table" ? "table" : t.attrs.type_kind}»</div><b>{t.name}</b><div className="st">{t.attrs.namespace || ""}</div></div>
      {rows.map((g) => (
        <div className="sec" key={g.title}>
          <div className="sh">{g.title}</div>
          {g.items.map((r) => (
            <div key={r.id} className={`row ${sel === r.id ? "sel" : ""} ${r.status === "changed" ? "chg" : r.status === "impacted" ? "imp" : ""}`}
              onClick={(e) => { e.stopPropagation(); onSelect(r.id); }} onDoubleClick={(e) => { e.stopPropagation(); onOpen(r.id); }}>
              <Handle type="target" position={Position.Left} id={"in-" + r.id} className="rowh" />
              <span className="v">{r.vis}</span><span className="nm">{r.name}</span><span className="ty">{r.sig}</span>
              <span className="fl">{r.chips.map((c, i) => <span key={i} className={"chip " + c[1]} title={c[2] || ""}>{c[0]}</span>)}</span>
              <Handle type="source" position={Position.Right} id={"out-" + r.id} className="rowh" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
function RelNode({ data }) {
  const { n, g, status, side } = data;
  return (
    <div className={`rel ${status === "changed" ? "chg" : status === "impacted" ? "imp" : ""}`}>
      {side === "right" ? <Handle type="target" position={Position.Left} /> : <Handle type="source" position={Position.Right} />}
      <b>{n.kind === "endpoint" ? n.name : n.name}</b>
      <small>{n.module} · {[...g.kinds].join(", ")}{g.count > 1 ? ` ×${g.count}` : ""}</small>
    </div>
  );
}
const nodeTypes = { card: ClassCard, rel: RelNode };

function memberRows(W, O, t) {
  const ms = W.children(t.id).filter((k) => !["type", "endpoint", "state"].includes(k.kind));
  const eps = W.children(t.id).filter((k) => k.kind === "endpoint");
  const groups = [["Fields", ms.filter((m) => m.kind === "field" || m.kind === "column")], ["Properties", ms.filter((m) => m.kind === "property")],
    ["Constructors", ms.filter((m) => m.kind === "ctor")], ["Methods", ms.filter((m) => m.kind === "method")]];
  return groups.filter(([, l]) => l.length).map(([title, list]) => ({
    title, items: list.map((m) => {
      const a = m.attrs, chips = [];
      eps.filter((e) => e.attrs.handler === m.id).forEach((e) => chips.push([`${e.attrs.verb} ${e.attrs.route}`, "c-api", (e.attrs.auth || []).join(", ")]));
      if (a.pii) chips.push(["PII", "c-pii"]);
      if (a.setter === "private" && m.kind === "property") chips.push(["private set", "c-call"]);
      if (m.kind === "method" && !W.isTest(m)) chips.push(W.tested.has(m.id) ? ["tested", "c-test"] : ["untested", "c-call", "No test calls this directly"]);
      W.outE(m.id).filter((e) => e.kind === "triggers").forEach((e) => chips.push(["→ " + W.node(e.target).name, "c-state"]));
      W.outE(m.id).filter((e) => e.kind === "publishes").forEach((e) => chips.push(["⚡ " + W.node(e.target).name, "c-ev"]));
      const st = O.status(m.id);
      if (st) chips.push([O.isNew(m.id) ? "new" : st === "changed" ? "changed" : "affected", st === "changed" ? "c-bad" : "c-state"]);
      const u = st && O.unit(m.id);
      if (u && ((u.side === "changed" && st === "changed") || (u.side === "affected" && st === "impacted"))) chips.push([LEVEL[u.level].icon + " " + LEVEL[u.level].short, "c-lv-" + u.level]);
      const fs = O.findings(m.id).length; if (fs) chips.push(["! " + fs, "c-bad"]);
      const sig = m.kind === "method" || m.kind === "ctor"
        ? `(${(a.params || []).map((p) => p.split(" ").slice(0, -1).join(" ").replace(/^[\w.]+\./, "")).join(", ")})${m.kind === "method" ? " : " + shortType(a.returns) : ""}`
        : a.type ? " : " + shortType(a.type) : "";
      return { id: m.id, vis: VIS[a.visibility] || "", name: m.kind === "ctor" ? t.name : m.name, sig, chips, status: st };
    }),
  }));
}

function Structure({ W, O, t, sel, onSelect, onOpen }) {
  const { nodes, edges } = useMemo(() => {
    const ins = relations(W, O, t, "in"), outs = relations(W, O, t, "out");
    const rows = memberRows(W, O, t);
    const nodes = [], edges = [];
    const nRows = rows.reduce((a, g) => a + g.items.length, 0);
    const cardH = 90 + rows.length * 26 + nRows * 28;
    nodes.push({ id: "card", type: "card", position: { x: 360, y: 0 }, data: { t, rows, sel, onSelect, onOpen }, draggable: false });
    const place = (list, side) => {
      const gap = Math.max(70, Math.min(96, cardH / Math.max(1, list.length)));
      list.forEach((g, i) => {
        const n = W.node(g.id); if (!n) return;
        const id = "rel:" + g.id;
        nodes.push({ id, type: "rel", position: { x: side === "left" ? 40 : 880, y: i * gap + 10 }, data: { n, g, status: O.status(g.id), side }, draggable: true });
        [...g.rows].forEach((row) => {
          const handle = row === t.id || !rows.some((gr) => gr.items.some((it) => it.id === row)) ? "__type" : row;
          const col = g.hot ? "#f07070" : "#5d7398";
          edges.push(side === "left"
            ? { id: id + ">" + row, source: id, target: "card", targetHandle: "in-" + handle, type: "smoothstep", style: { stroke: col, strokeWidth: g.hot ? 2.2 : 1.3 }, markerEnd: { type: MarkerType.ArrowClosed, color: col } }
            : { id: row + ">" + id, source: "card", sourceHandle: "out-" + handle, target: id, type: "smoothstep", style: { stroke: col, strokeWidth: g.hot ? 2.2 : 1.3 }, markerEnd: { type: MarkerType.ArrowClosed, color: col } });
        });
      });
    };
    place(ins, "left"); place(outs, "right");
    return { nodes, edges };
  }, [W, O, t, sel, onSelect, onOpen]);
  return (
    <div className="flowbox tall">
      <div className="colhead left">Used by</div><div className="colhead right">Uses</div>
      <ReactFlow panOnScroll panOnScrollSpeed={1} zoomOnScroll={false} zoomOnPinch nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.08 }} minZoom={0.2} maxZoom={1.6}
        onNodeClick={(_, n) => { if (n.id.startsWith("rel:")) onOpen(n.id.slice(4)); }} nodesConnectable={false} proOptions={{ hideAttribution: true }} colorMode="dark">
        <Background gap={24} color="#1d2940" /><Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function StateNode({ data }) {
  const { n, initial, final, status } = data;
  return (
    <div className={`statenode ${initial ? "init" : ""} ${final ? "final" : ""} ${status ? "chg" : ""}`}>
      <Handle type="target" position={Position.Left} /><b>{n.name}</b><Handle type="source" position={Position.Right} />
    </div>
  );
}
export function StateChart({ W, O, t, onSelect, onOpen }) {
  const enumId = t.attrs.states_enum || t.id;
  const [layout, setLayout] = useState(null);
  const model = useMemo(() => {
    const states = W.children(enumId).filter((n) => n.kind === "state");
    const trans = states.flatMap((s) => W.outE(s.id).filter((e) => e.kind === "transitions"));
    const trig = (sid) => [...new Set(W.inE(sid).filter((e) => e.kind === "triggers" && !W.isTest(W.node(e.source))).map((e) => e.source))];
    return { states, trans, trig };
  }, [W, enumId]);
  useEffect(() => {
    const g = { id: "root", layoutOptions: { "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.spacing.nodeNode": "40", "elk.layered.spacing.nodeNodeBetweenLayers": "90", "elk.edgeLabels.inline": "true" },
      children: model.states.map((s) => ({ id: s.id, width: 140, height: 48 })),
      edges: model.trans.map((e, i) => ({ id: "e" + i, sources: [e.source], targets: [e.target], labels: [{ text: model.trig(e.target).map((m) => W.node(m).name).join(", ") || " ", width: 120, height: 14 }] })) };
    elk.layout(g).then(setLayout).catch(() => setLayout(null));
  }, [model, W]);
  if (!model.states.length) return <p className="empty">No state machine found.</p>;
  const pos = Object.fromEntries((layout?.children || []).map((c) => [c.id, { x: c.x, y: c.y }]));
  const nodes = model.states.map((s) => ({ id: s.id, type: "state", position: pos[s.id] || { x: 0, y: 0 }, data: { n: s, initial: !!s.attrs.initial, final: !model.trans.some((e) => e.source === s.id), status: O.status(s.id) } }));
  const edges = model.trans.map((e, i) => {
    const tr = model.trig(e.target);
    const hot = tr.some((m) => O.status(m) === "changed") || O.isNew(e.target);
    const col = hot ? "#f07070" : "#8ea0bd";
    return { id: "e" + i, source: e.source, target: e.target, label: tr.map((m) => W.node(m).name + "()").join(", "), data: { tr },
      labelStyle: { fill: hot ? "#f7c1c1" : "#85b7eb", fontSize: 11.5, cursor: "pointer" }, labelBgStyle: { fill: "#0f1622" }, labelBgPadding: [4, 2],
      style: { stroke: col, strokeWidth: hot ? 2.4 : 1.6 }, markerEnd: { type: MarkerType.ArrowClosed, color: col }, type: "smoothstep" };
  });
  return (
    <>
      <div className="flowbox">
        {layout && <ReactFlow panOnScroll panOnScrollSpeed={1} zoomOnScroll={false} zoomOnPinch nodes={nodes} edges={edges} nodeTypes={{ state: StateNode }} fitView fitViewOptions={{ padding: 0.06, maxZoom: 1.3 }} nodesConnectable={false} proOptions={{ hideAttribution: true }} colorMode="dark"
          onNodeClick={(_, n) => onSelect(n.id)} onEdgeClick={(_, e) => e.data.tr[0] && onOpen(e.data.tr[0])}>
          <Background gap={24} color="#1d2940" /><Controls showInteractive={false} />
        </ReactFlow>}
      </div>
      <p className="note">Boxes are states; arrows are the allowed transitions (from <code>AllowedTransitions</code>). Labels name the methods that move the entity into that state; click an arrow to open the method.</p>
    </>
  );
}

function TestsTab({ W, t, prTests, onOpen }) {
  const mine = new Set(W.descendants(t.id).map((n) => n.id));
  const by = new Map();
  W.edges.forEach((e) => { if (e.kind === "calls" && mine.has(e.target) && W.isTest(W.node(e.source))) { if (!by.has(e.source)) by.set(e.source, new Set()); by.get(e.source).add(e.target); } });
  if (!by.size) return <p className="empty">No test calls {t.name} directly.</p>;
  const res = new Map((prTests || []).map((x) => [String(x.name).split(".").pop().replace(/\(.*$/, ""), x]));
  return (
    <>
      <table className="vars"><thead><tr><th>Test</th><th>Calls</th><th>Result in this snapshot</th></tr></thead><tbody>
        {[...by].map(([tid, targets]) => {
          const tn = W.node(tid), r = res.get(tn.name);
          return (<tr key={tid}><td><a className="lnk" onClick={() => onOpen(tid)}>{W.node(tn.parent)?.name}.{tn.name}</a></td>
            <td>{[...targets].map((x) => <span key={x} className="chip c-call click" onClick={() => onOpen(x)}>{displayName(W.node(x))}</span>)}</td>
            <td>{r ? <><span className={"chip " + (r.outcome === "Passed" ? "c-test" : "c-bad")}>{r.outcome}</span> <span className="note">{r.message}</span></> : <span className="note">not run in this snapshot</span>}</td></tr>);
        })}
      </tbody></table>
      <p className="note">Tests were written by the Test agent from the requirement only — it never saw this code.</p>
    </>
  );
}

export default function ClassView({ W, O, t, tab, setTab, sel, onSelect, onOpen, prTests }) {
  const hasState = t.attrs.states_enum || t.attrs.state_machine;
  const tabs = [["members", "Structure"], hasState && ["state", "State chart"], ["tests", "Tests"], ["code", "Code"]].filter(Boolean);
  const cur = tabs.some(([k]) => k === tab) ? tab : "members";
  const st = O.status(t.id);
  return (
    <div className="flat">
      <div className="vhead">
        <div><div className="note">{t.kind === "table" ? "table" : "«" + t.attrs.type_kind + "»"} · {t.module} / {t.layer}</div><h2>{t.name}</h2><div className="sig">{t.attrs.signature}</div></div>
        <div className="pills"><span className={"pill t-" + W.tier(t.module)}>{W.tier(t.module)} risk</span>{st && <span className={"pill p-" + st}>{st === "impacted" ? "affected" : st}</span>}{t.attrs.is_event && <span className="pill p-pii">event</span>}</div>
      </div>
      {W.lite && <div className="lite">Links here are name-matched guesses (lite cartographer). Run with .NET for proven links.</div>}
      <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={cur === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      {cur === "members" && <Structure W={W} O={O} t={t} sel={sel} onSelect={onSelect} onOpen={onOpen} />}
      {cur === "state" && <StateChart W={W} O={O} t={t} onSelect={onSelect} onOpen={onOpen} />}
      {cur === "tests" && <TestsTab W={W} t={t} prTests={prTests} onOpen={onOpen} />}
      {cur === "code" && <CodeBlock W={W} O={O} file={t.file} from={1} to={99999} focus={[t.line, t.end_line]} />}
    </div>
  );
}
