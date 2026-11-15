import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import DeckGL from "@deck.gl/react";
import { OrbitView, LinearInterpolator } from "@deck.gl/core";
import { SolidPolygonLayer, ArcLayer, TextLayer, LineLayer } from "@deck.gl/layers";
import { lensLinks, displayName } from "./model.js";

const GRID = { Auth: [0, 0], Accounts: [1, 0], Ledger: [2, 0], Platform: [0, 1], Loans: [1, 1], Database: [2, 1], Notifications: [0, 2], Audit: [1, 2], Tests: [2, 2] };
const LAYER_ORDER = ["Api", "Application", "Domain", "Data", "Tables", "Wiring", "Shared", "Host"];
export const C = {
  bg: [15, 22, 34], ground: [20, 29, 44], grid: [30, 42, 63],
  tier: { high: [168, 78, 66], medium: [172, 132, 58], low: [66, 132, 92], none: [52, 66, 92] },
  changed: [150, 50, 52], changedLine: [244, 150, 150],
  affected: [112, 84, 38], affectedLine: [250, 199, 117],
  calm: [38, 53, 80], calmLine: [72, 98, 140],
  sel: [133, 183, 235],
  lens: { risk: [120, 140, 170], calls: [150, 170, 200], apis: [94, 150, 235], events: [178, 150, 245], data: [93, 202, 165], tests: [151, 196, 89] },
  hot: [240, 110, 110],
  text: [228, 236, 248], textDim: [140, 158, 189],
};
const TYPE_COL = (n) => {
  if (n.kind === "table") return [40, 120, 110];
  const a = n.attrs;
  if (a.is_controller) return [52, 92, 170];
  if (a.is_event) return [110, 82, 170];
  if (a.type_kind === "interface") return [58, 72, 98];
  if (a.type_kind === "enum") return [150, 112, 48];
  if (a.type_kind === "record") return [44, 118, 102];
  return [70, 86, 116];
};
const VIEWS = new OrbitView({ orbitAxis: "Z", orthographic: true });
// Drag = pan with a short glide. Wheel and trackpad are handled by WorldView itself (scroll pans, pinch zooms).
const CONTROLLER = { dragMode: "pan", dragPan: true, dragRotate: false, touchRotate: false, touchZoom: true, doubleClickZoom: false, scrollZoom: false, keyboard: true, inertia: 300 };
const rect = (x, y, w, d, z = 0) => [[x, y, z], [x + w, y, z], [x + w, y + d, z], [x, y + d, z]];
const fade = (c, a) => [...c.slice(0, 3), a];

function useSize(ref) {
  const [s, setS] = useState({ w: 800, h: 600 });
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setS({ w: e.contentRect.width, h: e.contentRect.height }));
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref]);
  return s;
}

// ---------------------------------------------------------------- scene builders
// The box around the changed and affected parts, so "Fade the rest" can move the camera onto them.
function focusBox(items) {
  const pts = items.flatMap((it) => it.polygon);
  if (!pts.length) return null;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]), PAD = 50;
  const z0 = Math.min(...pts.map((p) => p[2] || 0)), z1 = Math.max(...items.map((it) => (it.polygon[0][2] || 0) + (it.h || 0)));
  return { bounds: [[Math.min(...xs) - PAD, Math.min(...ys) - PAD], [Math.max(...xs) + PAD, Math.max(...ys) + PAD]], z0, z1 };
}
const quiet = (labels, opts) => (opts.pr && opts.onlyImpact ? labels.filter((l) => l.floor || l.status) : labels);
function worldScene(W, O, lens, opts) {
  const mods = W.modules().map((n) => n.name).filter((m) => m !== "Tests" || lens === "tests");
  let extra = 0;
  const pos = {};
  mods.forEach((m) => { pos[m] = GRID[m] ? GRID[m] : [extra % 3, 3 + Math.floor(extra++ / 3)]; });
  const CELL = 200, FOOT = 110;
  const blocks = mods.map((m) => {
    const st = W.moduleStats(m);
    const h = Math.max(24, Math.min(170, 12 + 16 * Math.sqrt(st.members / 3 + st.types)));
    const [gx, gy] = pos[m];
    const x = gx * CELL, y = -gy * CELL;
    const status = O.status("module:" + m);
    let fill = C.tier[W.tier(m)] || C.tier.none, line = [255, 255, 255, 40];
    if (lens === "security") fill = st.eps.length ? (st.unprotected.length ? C.tier.high : C.tier.low) : C.tier.none;
    if (lens === "tests") { const r = st.methods ? st.tested / st.methods : 1; fill = m === "Tests" ? C.tier.low : !st.methods ? C.tier.none : r >= 0.6 ? C.tier.low : r >= 0.3 ? C.tier.medium : C.tier.high; }
    if (lens === "apis") fill = st.eps.length ? [52, 92, 170] : C.tier.none;
    if (lens === "data" && m === "Database") fill = [40, 130, 116];
    if (opts.pr) {
      if (status === "changed") { fill = C.changed; line = C.changedLine; }
      else if (status === "impacted") { fill = C.affected; line = C.affectedLine; }
      else { fill = opts.onlyImpact ? fade(C.calm, 45) : C.calm; line = opts.onlyImpact ? fade(C.calmLine, 50) : C.calmLine; }
    }
    if (st.locked) fill = fade(fill, 150);   // a module you cannot open: same colour, dimmer
    if (opts.sel === "module:" + m) line = C.sel;
    return { id: "module:" + m, m, polygon: rect(x, y - FOOT, FOOT, FOOT), h, fill, line, top: [x + FOOT / 2, y - FOOT / 2, h], st, status };
  });
  const byM = Object.fromEntries(blocks.map((b) => [b.m, b]));
  const links = lensLinks(W, O, lens === "risk" ? "calls" : lens, (id) => { const n = W.node(id); return n && byM[n.module] ? n.module : null; })
    .map((l) => ({ ...l, s: byM[l.a].top, t: byM[l.b].top }));
  if (lens === "security" && byM.Auth && !opts.pr) blocks.filter((b) => b.st.eps.length && b.m !== "Auth").forEach((b) => links.push({ a: "Auth", b: b.m, kind: "guards", count: b.st.eps.length, s: byM.Auth.top, t: b.top }));
  const labels = blocks.map((b) => {
    const badges = [];
    if (b.st.eps.length && (!b.status || lens === "apis")) badges.push(`${b.st.eps.length} API`);
    if ((lens === "security" || lens === "data") && b.st.pii) badges.push(`${b.st.pii} PII`);
    if (lens === "security" && b.st.unprotected.length) badges.push(`${b.st.unprotected.length} OPEN`);
    if (lens === "tests" && b.st.methods) badges.push(`${Math.round(100 * b.st.tested / b.st.methods)}% tested`);
    if (b.st.locked) badges.push("no access");
    if (b.status && !b.st.locked) badges.push(trustBadge(O, b.id, b.status));
    if (b.status && b.st.locked) badges.push(b.status === "changed" ? "changed" : "affected");
    return { id: b.id, pos: [b.top[0], b.top[1], b.top[2] + 6], text: b.m, sub: badges.join(" · "), status: b.status, findings: O.findings(b.id).length };
  });
  const ground = { polygon: rect(-90, 90 - 3 * CELL - 90 * 0, 3 * CELL + 90, 3 * CELL + 90, 0) };
  ground.polygon = [[-80, 80, 0], [3 * CELL - 10, 80, 0], [3 * CELL - 10, -Math.max(3, Math.ceil(mods.length / 3)) * CELL + 10, 0], [-80, -Math.max(3, Math.ceil(mods.length / 3)) * CELL + 10, 0]];
  return { blocks, links, labels: quiet(labels, opts), ground, bounds: [[-80, -3 * CELL], [3 * CELL, 80]], focus: focusBox(blocks.filter((b) => b.status)) };
}

function moduleScene(W, O, lens, focus, opts) {
  const mod = W.node(focus);
  if (!mod) return null;
  const layers = W.children(focus).filter((n) => n.kind === "layer" && n.name !== "Docs")
    .sort((a, b) => ((LAYER_ORDER.indexOf(a.name) + 1) || 99) - ((LAYER_ORDER.indexOf(b.name) + 1) || 99) || a.name.localeCompare(b.name));
  const floors = layers.map((l) => ({ l, items: W.children(l.id).filter((n) => n.kind === "type" || n.kind === "table").sort(sortTypes) }));
  const maxItems = Math.max(1, ...floors.map((f) => f.items.length));
  const cols = Math.max(2, Math.ceil(Math.sqrt(maxItems * 2.2))), rows = Math.ceil(maxItems / cols);
  const CELL = 170, FOOT = 84, PAD = 30;
  const PW = cols * CELL + PAD * 2, PD = rows * CELL + PAD * 2, GAP = 70, STEP = PD + 70;
  const nF = floors.length;
  const plates = [], tiles = [], labels = [], centre = {};
  floors.forEach((f, i) => {
    const z = (nF - 1 - i) * GAP, yo = -i * STEP;
    plates.push({ id: f.l.id, polygon: rect(0, yo - PD, PW, PD, z), z, name: f.l.name });
    labels.push({ id: f.l.id, pos: [-20, yo - PD / 2, z + 4], text: f.l.name, sub: hint(f.l.name), floor: true });
    f.items.forEach((n, j) => {
      const x = PAD + (j % cols) * CELL + (CELL - FOOT) / 2, y = yo - (PAD + Math.floor(j / cols) * CELL + (CELL - FOOT) / 2) - FOOT;
      const mem = W.children(n.id).filter((k) => k.kind !== "type").length;
      const h = Math.min(60, 10 + 7 * Math.sqrt(mem));
      const status = O.status(n.id);
      let fill = TYPE_COL(n), line = [255, 255, 255, 50];
      if (lens === "tests") fill = testCol(W, n);
      if (lens === "security") fill = secCol(W, n);
      if (opts.pr) { if (status === "changed") line = C.changedLine; else if (status === "impacted") line = C.affectedLine; else if (opts.onlyImpact) { fill = fade(fill, 40); line = [255, 255, 255, 25]; } }
      if (opts.sel === n.id) line = C.sel;
      const top = [x + FOOT / 2, y + FOOT / 2, z + 4 + h];
      centre[n.id] = top;
      tiles.push({ id: n.id, n, polygon: rect(x, y, FOOT, FOOT, z + 4), h, fill, line, top, status, dashed: n.attrs.type_kind === "interface" });
      const eps = W.children(n.id).filter((k) => k.kind === "endpoint").length;
      const sub = (n.kind === "table" ? `${W.children(n.id).length} columns` : n.attrs.is_event ? "event" : n.attrs.is_controller ? "controller" : n.attrs.type_kind) + (eps ? ` · ${eps} API` : "") + (n.attrs.state_machine || n.attrs.states_enum ? " · states" : "");
      labels.push({ id: n.id, pos: [top[0], top[1], top[2] + 4], text: n.name, sub: status ? trustBadge(O, n.id, status) : sub, status, findings: O.findings(n.id).length });
    });
  });
  const L = lens === "risk" ? "calls" : lens;
  const raw = lensLinks(W, O, L, (id) => {
    const n = W.node(id); if (!n) return null;
    if (n.module === mod.name) { const t = W.typeOf(id); return t && centre[t] ? t : null; }
    if (n.module === "Tests" && L !== "tests") return null;
    return "door:" + n.module;
  }).filter((l) => !(l.a.startsWith("door:") && l.b.startsWith("door:")));
  const doorIO = new Map();
  raw.forEach((l) => [l.a, l.b].forEach((x, k) => { if (x.startsWith("door:")) { const d = doorIO.get(x) || { in: 0, out: 0 }; if (k === 0) d.out += l.count; else d.in += l.count; doorIO.set(x, d); } }));
  const doorList = [...doorIO.keys()].sort();
  const zMid = ((nF - 1) * GAP) / 2, depth = nF * STEP;
  const doors = doorList.map((d, i) => {
    const m = d.slice(5), x = PW + 220, y = -depth / 2 + (i - (doorList.length - 1) / 2) * 120;
    const status = O.status("module:" + m);
    const top = [x + 18, y, zMid + 70];
    centre[d] = top;
    const io = doorIO.get(d);
    labels.push({ id: d, pos: [top[0], top[1], top[2] + 6], text: "⇄ " + m, sub: [io.in ? `in ${io.in}` : "", io.out ? `out ${io.out}` : ""].filter(Boolean).join(" · "), status, door: true });
    const calmDoor = opts.pr && opts.onlyImpact && !status;   // "Fade the rest" fades doors to untouched modules too
    return { id: d, m, status, polygon: rect(x, y - 30, 36, 60, zMid), h: 70, fill: calmDoor ? fade(C.tier[W.tier(m)] || C.tier.none, 40) : C.tier[W.tier(m)] || C.tier.none,
      line: status === "changed" ? C.changedLine : status === "impacted" ? C.affectedLine : calmDoor ? [255, 255, 255, 25] : [255, 255, 255, 60], top };
  });
  const links = raw.map((l) => ({ ...l, s: centre[l.a], t: centre[l.b] })).filter((l) => l.s && l.t);
  return { plates, tiles, doors, links, labels: quiet(labels, opts), bounds: [[-80, -depth - 40], [PW + 300, 60]], height: (nF - 1) * GAP + 120,
    focus: focusBox([...tiles.filter((t) => t.status), ...doors.filter((d) => d.status)]) };
}
// "changed · 2/5 verified ✕1" -- the trust evidence for this block, on the map
function trustBadge(O, id, status) {
  const side = status === "changed" ? "changed" : "affected";
  const r = O.roll(id), s = r && r[side];
  const word = status === "changed" ? "changed" : "affected";
  if (!s) return word;
  return `${word} · ${s.verified}/${s.n} ✓${s.contradicted ? "  ✕" + s.contradicted : ""}`;
}
function sortTypes(a, b) {
  const r = (n) => (n.attrs.is_controller ? 0 : n.attrs.type_kind === "interface" ? 2 : n.attrs.is_event ? 4 : n.attrs.type_kind === "enum" ? 5 : n.attrs.type_kind === "record" ? 3 : 1);
  return r(a) - r(b) || a.name.localeCompare(b.name);
}
const hint = (l) => ({ Api: "HTTP endpoints", Application: "use cases", Domain: "business rules", Data: "database access", Tables: "tables", Wiring: "registration", Shared: "shared contracts", Host: "startup" }[l] || "");
function testCol(W, n) {
  const ms = W.children(n.id).filter((k) => k.kind === "method" && !W.isTest(k));
  if (!ms.length) return C.tier.none;
  const r = ms.filter((k) => W.tested.has(k.id)).length / ms.length;
  return r >= 0.6 ? C.tier.low : r > 0 ? C.tier.medium : C.tier.high;
}
function secCol(W, n) {
  const eps = W.children(n.id).filter((k) => k.kind === "endpoint");
  if (eps.length) return eps.every((e) => e.attrs.protected) ? C.tier.low : C.tier.high;
  return W.children(n.id).some((k) => k.attrs.pii) ? [110, 82, 170] : C.tier.none;
}

// ---------------------------------------------------------------- component
export default function WorldView({ W, O, level, focus, lens, sel, pr, onlyImpact, onSelect, onOpen, onUp, onHover }) {
  const ref = useRef(null);
  const size = useSize(ref);
  const scene = useMemo(() => (level === "module" ? moduleScene(W, O, lens, focus, { pr, onlyImpact, sel }) : worldScene(W, O, lens, { pr, onlyImpact, sel })),
    [W, O, level, focus, lens, pr, onlyImpact, sel]);
  const PITCH = 35;
  const [view, setView] = useState({ target: [300, -300, 0], zoom: -0.5, rotationX: 35, rotationOrbit: -40, minZoom: -4, maxZoom: 4 });
  const fitZoom = useRef(0);
  const hovered = useRef(null);
  const lastClick = useRef({ id: null, t: 0 });
  const deckRef = useRef(null);

  const fit = useCallback((animate) => {
    if (!scene || size.w < 60 || size.h < 60) return;
    const fb = pr && onlyImpact && scene.focus ? scene.focus : null;   // "Fade the rest": frame only what changed or is affected
    const zoomFor = ([[x0, y0], [x1, y1]], zH) => {
      const bw = (x1 - x0) * 1.15 + (y1 - y0) * 0.5, bh = (y1 - y0) * 0.62 + zH * 0.9 + 80;
      return Math.log2(Math.min(size.w / bw, size.h / bh)) + (level === "world" ? 0.45 : 0.3);
    };
    const full = zoomFor(scene.bounds, scene.height || 120);
    const [[x0, y0], [x1, y1]] = fb ? fb.bounds : scene.bounds;
    const zH = fb ? Math.max(40, fb.z1 - fb.z0) : (scene.height || 120);
    let target = [(x0 + x1) / 2, (y0 + y1) / 2, fb ? (fb.z0 + fb.z1) / 2 : zH / 2.4], z = full;
    if (fb) {
      // project the box (with room for the labels on top) as the camera sees it, then frame it exactly
      const vp = VIEWS.makeViewport({ width: size.w, height: size.h, viewState: { target, zoom: 0, rotationX: PITCH, rotationOrbit: -40 } });
      const pts = [];
      for (const x of [x0, x1]) for (const y of [y0, y1]) for (const zz of [fb.z0, fb.z1 + 40]) pts.push(vp.project([x, y, zz]));
      const px = pts.map((p) => p[0]), py = pts.map((p) => p[1]);
      const bw = Math.max(...px) - Math.min(...px), bh = Math.max(...py) - Math.min(...py);
      const fitZ = Math.log2(Math.min((size.w - 140) / bw, (size.h - 230) / bh));
      z = Math.min(fitZ, full + 0.7);   // close in on the change, but not further than a little past the whole map
      target = vp.unproject([(Math.min(...px) + Math.max(...px)) / 2, (Math.min(...py) + Math.max(...py)) / 2 + 28], { targetZ: target[2] });
      target = [target[0], target[1], (fb.z0 + fb.z1) / 2];
    }
    fitZoom.current = full;
    setView((v) => ({ ...v, target, zoom: z, rotationX: PITCH, rotationOrbit: -40,
      ...(animate ? { transitionDuration: 650, transitionInterpolator: new LinearInterpolator(["target", "zoom"]) } : { transitionDuration: 0 }) }));
  }, [scene, size.w, size.h, PITCH, pr, onlyImpact, level]);
  const moved = useRef(false);      // true once the person pans or zooms: a resize then keeps their view
  useEffect(() => { moved.current = false; fit(true); }, [level, focus]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!moved.current) fit(false); }, [size.w, size.h]); // eslint-disable-line react-hooks/exhaustive-deps
  const lastOI = useRef(onlyImpact);   // toggling "Fade the rest" moves the camera onto the change, or back to the whole map
  useEffect(() => { if (lastOI.current === onlyImpact) return; lastOI.current = onlyImpact; moved.current = false; fit(true); }, [onlyImpact]); // eslint-disable-line react-hooks/exhaustive-deps
  const viewRef = useRef(view); viewRef.current = view;
  const P = useRef({}); P.current = { level, onOpen, onUp, onHover };

  const click = (info) => {
    const id = info.object && (info.object.id || (info.object.door && info.object.id));
    if (!id) { onSelect(null); return; }
    const now = Date.now();
    const dbl = lastClick.current.id === id && now - lastClick.current.t < 380;
    lastClick.current = { id, t: now };
    if (id.startsWith("door:")) { onOpen("module:" + id.slice(5)); return; }
    if (dbl) onOpen(id); else onSelect(id);
  };
  const autoLevel = (z) => {     // zoom far in over a block opens it; zoom far out goes up a level
    const { level: lv, onOpen: op, onUp: upf } = P.current;
    if (lv === "world" && z > fitZoom.current + 2.4 && hovered.current) { const h = hovered.current; hovered.current = null; op(h); return true; }
    if (lv === "module" && z < fitZoom.current - 1.8) { upf(); return true; }
    return false;
  };
  const onViewStateChange = useCallback(({ viewState, interactionState }) => {
    if (interactionState && (interactionState.isDragging || interactionState.isPanning || interactionState.isZooming)) moved.current = true;
    setView({ ...viewState, rotationX: PITCH, rotationOrbit: -40 });
  }, []);

  // Trackpad first: two-finger scroll pans, pinch zooms at the cursor; a mouse wheel zooms. Applied at once, no easing.
  useEffect(() => {
    const el = ref.current; if (!el) return;
    let raf = 0, acc = { dx: 0, dy: 0, dz: 0, x: 0, y: 0 };
    const flush = () => {
      raf = 0;
      const deck = deckRef.current && deckRef.current.deck;
      const vp = deck && deck.getViewports && deck.getViewports()[0];
      const v = viewRef.current; const { dx, dy, dz, x, y } = acc; acc = { dx: 0, dy: 0, dz: 0, x, y };
      if (!vp) return;
      let target = v.target, zoom = v.zoom;
      if (dx || dy) {
        const tz = target[2] || 0, cx = vp.width / 2, cy = vp.height / 2;
        const a = vp.unproject([cx, cy], { targetZ: tz }), b = vp.unproject([cx + dx, cy + dy], { targetZ: tz });
        target = [target[0] + (b[0] - a[0]), target[1] + (b[1] - a[1]), tz];
      }
      if (dz) {
        const nz = Math.max(v.minZoom ?? -6, Math.min(v.maxZoom ?? 6, zoom + dz));
        const p = vp.unproject([x, y], { targetZ: target[2] || 0 });
        const k = Math.pow(2, zoom - nz);
        target = [p[0] + (target[0] - p[0]) * k, p[1] + (target[1] - p[1]) * k, target[2] || 0];
        zoom = nz;
      }
      moved.current = true;
      setView({ ...v, target, zoom, transitionDuration: 0 });
      if (dz) autoLevel(zoom);
    };
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      acc.x = e.clientX - r.left; acc.y = e.clientY - r.top;
      const px = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? r.height : 1;
      const mouseWheel = e.deltaMode !== 0 || (e.deltaX === 0 && Math.abs(e.deltaY) >= 50 && Number.isInteger(e.deltaY));
      if (e.ctrlKey) acc.dz += -e.deltaY * px * 0.012;            // trackpad pinch (and ctrl + wheel)
      else if (mouseWheel) acc.dz += -e.deltaY * px * 0.0022;     // classic mouse wheel
      else { acc.dx += e.deltaX * px; acc.dy += e.deltaY * px; }   // two-finger scroll = pan
      if (!raf) raf = requestAnimationFrame(flush);
    };
    // Safari trackpad pinch arrives as gesture events
    let g0 = 1;
    const gs = (e) => { e.preventDefault(); g0 = e.scale; };
    const gc = (e) => { e.preventDefault(); const r = el.getBoundingClientRect(); acc.x = e.clientX - r.left; acc.y = e.clientY - r.top; acc.dz += Math.log2(e.scale / g0); g0 = e.scale; if (!raf) raf = requestAnimationFrame(flush); };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("gesturestart", gs); el.addEventListener("gesturechange", gc);
    return () => { el.removeEventListener("wheel", onWheel); el.removeEventListener("gesturestart", gs); el.removeEventListener("gesturechange", gc); if (raf) cancelAnimationFrame(raf); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const zoomBy = (d) => setView((v) => ({ ...v, zoom: Math.max(v.minZoom ?? -6, Math.min(v.maxZoom ?? 6, v.zoom + d)), transitionDuration: 160, transitionInterpolator: new LinearInterpolator(["zoom"]) }));

  const layers = useMemo(() => {
  const layers = [];
  if (scene && level === "world") {
    layers.push(new SolidPolygonLayer({ id: "ground", data: [scene.ground], getPolygon: (d) => d.polygon, getFillColor: C.ground, extruded: false }));
    const lines = [];
    for (let i = 0; i <= 12; i++) { lines.push({ s: [-80 + i * 50, 80, 0], t: [-80 + i * 50, -600 + 10, 0] }); lines.push({ s: [-80, 80 - i * 56, 0], t: [590, 80 - i * 56, 0] }); }
    layers.push(new LineLayer({ id: "grid", data: lines, getSourcePosition: (d) => d.s, getTargetPosition: (d) => d.t, getColor: C.grid, getWidth: 1 }));
    layers.push(new SolidPolygonLayer({
      id: "blocks", data: scene.blocks, getPolygon: (d) => d.polygon, extruded: true, wireframe: true, pickable: true, autoHighlight: true, highlightColor: [133, 183, 235, 70],
      getElevation: (d) => d.h, getFillColor: (d) => d.fill, getLineColor: (d) => d.line, material: { ambient: 0.55, diffuse: 0.55, shininess: 12 },
      transitions: { getElevation: { duration: 700 }, getFillColor: { duration: 400 } }, updateTriggers: { getFillColor: [lens, pr, onlyImpact, sel, O], getLineColor: [lens, pr, sel, O] },
    }));
  }
  if (scene && level === "module") {
    layers.push(new SolidPolygonLayer({ id: "plates", data: scene.plates, getPolygon: (d) => d.polygon, extruded: true, getElevation: 4, getFillColor: [34, 48, 72, 170], getLineColor: [90, 115, 160, 160], wireframe: true, parameters: { depthMask: false } }));
    layers.push(new SolidPolygonLayer({
      id: "tiles", data: scene.tiles, getPolygon: (d) => d.polygon, extruded: true, wireframe: true, pickable: true, autoHighlight: true, highlightColor: [133, 183, 235, 80],
      getElevation: (d) => d.h, getFillColor: (d) => d.fill, getLineColor: (d) => d.line, material: { ambient: 0.6, diffuse: 0.5 },
      updateTriggers: { getFillColor: [lens, pr, onlyImpact, sel, O], getLineColor: [lens, pr, sel, O] },
    }));
    layers.push(new SolidPolygonLayer({ id: "doors", data: scene.doors, getPolygon: (d) => d.polygon, extruded: true, wireframe: true, pickable: true, getElevation: (d) => d.h, getFillColor: (d) => d.fill, getLineColor: (d) => d.line }));
  }
  if (scene) {
    const lensCol = C.lens[lens] || C.lens.calls;
    layers.push(new ArcLayer({
      id: "arcs", data: scene.links.filter((l) => !(pr && onlyImpact && !l.hot)), getSourcePosition: (d) => d.s, getTargetPosition: (d) => d.t,
      getSourceColor: (d) => (pr ? (d.hot ? C.hot : [90, 110, 150, 110]) : [...lensCol, 230]), getTargetColor: (d) => (pr ? (d.hot ? [250, 199, 117] : [90, 110, 150, 110]) : [...lensCol.map((v) => Math.min(255, v + 40)), 230]),
      getWidth: (d) => (pr && d.hot ? 3.5 : Math.min(4, 1.2 + Math.log2(1 + d.count))), getHeight: level === "module" ? 0.25 : 0.45, greatCircle: false, pickable: true,
      updateTriggers: { getSourceColor: [lens, pr, O], getTargetColor: [lens, pr, O], getWidth: [pr, O] },
    }));
    const lab = scene.labels;
    layers.push(new TextLayer({
      id: "labels", data: lab, getPosition: (d) => d.pos, getText: (d) => d.text, getSize: (d) => (d.floor ? 16 : level === "world" ? 15 : 13.5), sizeUnits: "pixels",
      getColor: (d) => (d.status === "changed" ? [247, 193, 193] : d.status === "impacted" ? [250, 214, 150] : d.floor ? [160, 178, 205] : C.text),
      getPixelOffset: (d) => (d.floor ? [-10, 0] : [0, -22]), getTextAnchor: (d) => (d.floor ? "end" : "middle"), getAlignmentBaseline: "center",
      background: true, getBackgroundColor: (d) => (d.floor ? [0, 0, 0, 0] : [15, 22, 34, 225]), backgroundPadding: [7, 3],
      getBorderColor: (d) => (d.floor ? [0, 0, 0, 0] : d.status === "changed" ? C.changedLine : d.status === "impacted" ? C.affectedLine : [72, 98, 140]), getBorderWidth: 1,
      fontFamily: "Inter, -apple-system, Segoe UI, sans-serif", fontWeight: 600, characterSet: "auto", billboard: true, pickable: false, parameters: { depthTest: false },
      updateTriggers: { getColor: [pr, O], getBorderColor: [pr, O] },
    }));
    layers.push(new TextLayer({
      id: "subs", data: lab.filter((d) => d.sub), getPosition: (d) => d.pos, getText: (d) => d.sub, getSize: 11, getColor: C.textDim,
      getPixelOffset: (d) => (d.floor ? [-10, 16] : [0, -4]), getTextAnchor: (d) => (d.floor ? "end" : "middle"), getAlignmentBaseline: "center",
      fontFamily: "Inter, -apple-system, Segoe UI, sans-serif", characterSet: "auto", billboard: true, parameters: { depthTest: false },
    }));
    const fl = lab.filter((d) => d.findings);
        const fOff = (d) => [Math.round(d.text.length * (level === "world" ? 4.6 : 4.1)) + 12, -22];
    layers.push(new TextLayer({ id: "fnum", data: fl, getPosition: (d) => d.pos, getText: (d) => "! " + d.findings, getSize: 12, getColor: [255, 255, 255], fontWeight: 700, getPixelOffset: fOff,
      background: true, getBackgroundColor: [210, 64, 64, 255], backgroundPadding: [5, 2], backgroundBorderRadius: 8, getTextAnchor: "start", getAlignmentBaseline: "center",
      fontFamily: "Inter, -apple-system, Segoe UI, sans-serif", billboard: true, characterSet: "auto", parameters: { depthTest: false } }));
  }
  return layers;
  }, [scene, level, lens, pr, onlyImpact, sel, O]); // eslint-disable-line react-hooks/exhaustive-deps

  const hover = useCallback((info) => {
    hovered.current = info.object && info.object.id && !String(info.object.id).startsWith("door:") && info.layer && ["blocks", "tiles"].includes(info.layer.id) ? info.object.id : null;
    P.current.onHover(info);
  }, []);

  return (
    <div ref={ref} className="deck-wrap">
      <DeckGL
        ref={deckRef}
        views={VIEWS}
        viewState={view}
        onViewStateChange={onViewStateChange}
        controller={CONTROLLER}
        layers={layers}
        onClick={click}
        onHover={hover}
        getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
        parameters={{ clearColor: [C.bg[0] / 255, C.bg[1] / 255, C.bg[2] / 255, 1] }}
        style={{ background: `rgb(${C.bg.join(",")})` }}
      />
      <div className="zoomctl">
        <button aria-label="Zoom in" onClick={() => { moved.current = true; zoomBy(0.5); }}>+</button>
        <button aria-label="Zoom out" onClick={() => { moved.current = true; zoomBy(-0.5); }}>−</button>
        <button aria-label="Fit" onClick={() => { moved.current = false; fit(true); }}>⤢</button>
        {level !== "world" && <button aria-label="Up one level" onClick={onUp}>↑</button>}
      </div>
    </div>
  );
}
export { displayName };
