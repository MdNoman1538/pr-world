/* AI Review Dashboard — 4 zones from the research specification:
   A architecture & call-graph map (the "world")   B PR-issue requirement radar
   C verifiable evidence                           D line-anchored actionable findings  + sign-off
   Data: window.__BUNDLE__ (exported file) or the backend JSON API (window.REVIEW_API, see config.js). */
(function () {
  "use strict";
  const S = { b: null, mode: "static", runs: [], filter: { sev: "all", file: null, area: null }, feedback: {} };
  // The frontend only talks to the backend over HTTP (or reads an embedded bundle). Override with ?api=http://host:port
  const API = (new URLSearchParams(location.search).get("api") || window.REVIEW_API || "http://127.0.0.1:8765").replace(/\/$/, "");
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const TIER_FILL = { high: "#efc7bf", medium: "#efdcae", low: "#c9e3cf" };
  const TIER_STROKE = { high: "#b83a2e", medium: "#a8701c", low: "#2f7d55" };
  const SEV_LABEL = { Blocker: "[Blocker]", ShouldFix: "[Should Fix]", Nit: "[Nit]" };
  const AREA_FOR_DIM = { correctness: "Correctness", architecture: "Architecture", safety: "Security", tests: "Tests", maintainability: "Maintainability", performance: "Performance" };

  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.style.display = "block"; clearTimeout(t._h); t._h = setTimeout(() => (t.style.display = "none"), 2200); }
  function modal(title, body) { $("#mtitle").textContent = title; $("#mbody").textContent = body; $("#modal").classList.add("on"); $("#ovl").classList.add("on"); }
  function closeModal() { $("#modal").classList.remove("on"); $("#ovl").classList.remove("on"); }
  $("#mclose").onclick = closeModal; $("#ovl").onclick = closeModal;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast("Copied"); }
    catch (e) { modal("Copy this text", text); }
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    if (window.__BUNDLE__) { S.mode = "static"; load(window.__BUNDLE__); return; }
    S.mode = "live";
    try {
      S.runs = await (await fetch(API + "/api/runs")).json();
    } catch (e) { document.querySelector("main").innerHTML = `<p class='empty' style='padding:20px'>Could not reach the backend API at ${esc(API)}. Start it with <code>python backend/review.py api</code>, or open a run's exported dashboard file.</p>`; return; }
    if (!S.runs.length) { document.querySelector("main").innerHTML = "<p class='empty' style='padding:20px'>No reviews yet. Run <code>python review.py review ...</code> first.</p>"; return; }
    const sel = $("#runsel"); sel.hidden = false;
    sel.innerHTML = S.runs.map((r) => `<option value="${esc(r.run_id)}">${esc(r.head)} · ${esc(r.decision)} · ${esc(r.run_id.slice(0, 15))}</option>`).join("");
    sel.onchange = () => { location.hash = sel.value; };
    window.addEventListener("hashchange", () => openRun(location.hash.slice(1)));
    const want = location.hash.slice(1);
    await openRun(S.runs.some((r) => r.run_id === want) ? want : S.runs[0].run_id);
  }
  async function openRun(id) {
    if (!id) return;
    $("#runsel").value = id;
    const b = await (await fetch(API + "/api/runs/" + encodeURIComponent(id))).json();
    load(b);
  }
  function load(b) {
    S.b = b; S.filter = { sev: "all", file: null, area: null }; S.feedback = b.feedback || {};
    const mock = (b.review.models || {}).specialists === "mock";
    $("#modetag").textContent = (S.mode === "live" ? "Live · feedback is recorded" : "Static export · read only") + (mock ? " · MOCK model answers" : "");
    renderHeader(); renderAreas(); renderApi(); renderMap(); renderRadar(); renderEvidence(); renderFilters(); renderStream(); renderSignoff();
  }
  document.querySelectorAll(".tab").forEach((t) => t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === t));
    const map = t.dataset.tab === "map";
    $("#apiview").hidden = map; $("#mapbox").hidden = !map; $("#maplegend").hidden = !map;
  });

  // ------------------------------------------------------------------ header + areas
  function renderHeader() {
    const r = S.b.review;
    const t = r.tier.tier;
    $("#decision").innerHTML = `
      <span class="dbadge d-${esc(r.decision)}">${esc(r.decision.replace(/_/g, " "))}</span>
      <div class="meta"><span class="pill t-${t}">Tier ${t.toUpperCase()}</span>
        <span>${r.tier.signoffs_required} sign-off(s)</span><span>·</span>
        <span>Requirement <b>${esc(r.requirement_id)}</b> (alignment: <b>${esc(r.requirement_alignment)}</b>)</span><span>·</span>
        <span>PR <b>${esc(r.head)}</b> → ${esc(r.base)}</span><span>·</span><span>Owner <b>${esc(r.owner)}</b></span>
        ${r.optimization_context ? '<span class="pill t-high">Optimization trap check</span>' : ""}
        ${r.delta && r.delta.previous_run ? `<span class="pill" style="background:#dfe8fb;color:#2b5fd9">${esc(r.delta.summary)}</span>` : ""}
      </div>
      ${r.ai_error ? `<div class="aierr">⚠ AI REVIEW DID NOT RUN — only code checks are shown. ${esc(r.ai_error)}</div>` : ""}
      <div class="reason">${esc(r.orientation || "")}</div>
      <div class="reason small">${esc(r.decision_reason)}</div>
      ${r.policy_approved_by ? "" : '<div class="warnline">The rulebook (review-policy.yaml) is not approved by a named human yet. Tiers below are a draft.</div>'}`;
  }
  function renderAreas() {
    const el = $("#areas");
    el.innerHTML = S.b.review.areas.map((a) => `<button class="chip s-${a.status} ${S.filter.area === a.area ? "on" : ""}" data-area="${esc(a.area)}" title="${esc(a.reason)}"><span class="dot"></span>${esc(a.area)}</button>`).join("")
      + `<span class="small" style="align-self:center;margin-left:6px">green = verified with evidence · purple = needs a human · red = blocked</span>`;
    el.querySelectorAll(".chip").forEach((c) => c.onclick = () => {
      const a = c.dataset.area; S.filter.area = S.filter.area === a ? null : a; S.filter.file = null;
      renderAreas(); renderFilters(); renderStream();
      const area = S.b.review.areas.find((x) => x.area === a);
      if (area && S.filter.area) toast(`${area.area}: ${area.reason}`);
    });
  }


  // ------------------------------------------------------------------ Zone A: API call flow
  const CHANGE_LABEL = { signature: "SIGNATURE CHANGED", body: "BEHAVIOUR CHANGED", new: "NEW", removed: "REMOVED" };
  const IMPACT_TEXT = {
    signature: "The contract changed: every caller must be checked and may need updating.",
    removed: "The API is gone: callers will fail to compile or break at runtime.",
    body: "Same contract, new behaviour: callers keep compiling but may now get different results.",
    new: "New API: nothing depended on it before; check it is used as intended and tested.",
  };
  let apiSel = null;
  function renderApi() {
    const api = (S.b.graph || {}).api;
    const el = $("#apiview");
    if (!api || !api.apis || !api.apis.length) {
      el.innerHTML = `<div class="body" style="grid-column:1/-1"><p class="empty">No changed C# APIs detected in this PR${api && api.test_members && api.test_members.length ? ` (only test code changed: ${api.test_members.length} test member(s))` : ""}.</p></div>`;
      return;
    }
    const s = api.summary;
    const chip = (n, cls, label) => n ? `<span class="b ${cls}">${n} ${label}</span>` : "";
    el.innerHTML = `<div class="apilist"><div class="apisum">${chip(s.breaking, "b-break", "BREAKING")}${chip(s.removed, "b-removed", "removed")}${chip(s.signature, "b-signature", "signature")}${chip(s.body, "b-body", "behaviour")}${chip(s.new, "b-new", "new")}<span class="small" style="flex-basis:100%">${s.apis} changed API(s) · ${s.untested_callers} caller(s) not reached by tests${api.test_members && api.test_members.length ? ` · ${api.test_members.length} test member(s) changed` : ""}</span></div>`
      + api.apis.map((x, i) => `<div class="apicard" data-i="${i}">
          <div>${x.breaking ? '<span class="b b-break">BREAKING</span>' : ""}<span class="b b-${x.change}">${CHANGE_LABEL[x.change] || x.change}</span><span class="b b-vis">${esc(x.visibility)} ${esc(x.kind)}</span></div>
          <div class="nm">${esc(x.name)}${x.kind === "property" ? "" : "()"}</div>
          <div class="fl">${esc(x.file)} · ${esc(x.area)}</div>
          <div class="st">${x.callers.length} caller(s)${x.caller_areas.length ? " in " + esc(x.caller_areas.join(", ")) : ""} · <b style="color:${x.untested_callers.length ? "var(--bad)" : "var(--ok)"}">${x.untested_callers.length} untested</b> · ${x.tests.length} test(s)</div></div>`).join("")
      + `</div><div class="flowpane"><div class="flowhead" id="flowhead"></div><div class="flowsvg" id="flowsvg"></div>
        <div class="flowlegend"><span>→ arrows = calls</span><span>left stripe = risk tier of the area</span><span>dashed box = no test reaches it</span><span>green = test</span><span>red arrow = contract changed · orange = behaviour changed</span><span class="small">${esc(api.method || "")}</span></div></div>`;
    el.querySelectorAll(".apicard").forEach((c) => c.onclick = () => selectApi(+c.dataset.i));
    selectApi(0);
  }
  function selectApi(i) {
    const api = S.b.graph.api, x = api.apis[i]; apiSel = i;
    document.querySelectorAll(".apicard").forEach((c) => c.classList.toggle("on", +c.dataset.i === i));
    const N = api.nodes;
    const sig = x.change === "signature" ? `<div class="sigdiff"><div class="o">- ${esc(x.sig_before)}</div><div class="n">+ ${esc(x.sig_after)}</div></div>`
      : x.change === "removed" ? `<div class="sigdiff"><div class="o">- ${esc(x.sig_before)}</div></div>`
      : x.change === "new" ? `<div class="sigdiff"><div class="n">+ ${esc(x.sig_after)}</div></div>`
      : `<div class="sigdiff"><div class="s">  ${esc(x.sig_after)}   (signature unchanged)</div></div>`;
    const untested = x.untested_callers.length;
    $("#flowhead").innerHTML = `<h3>${esc(x.name)}${x.kind === "property" ? "" : "()"} <span class="b b-${x.change}">${CHANGE_LABEL[x.change]}</span>${x.breaking ? '<span class="b b-break">BREAKING</span>' : ""}</h3>
      <div class="small">${esc(x.visibility)} ${esc(x.kind)} · ${esc(x.file)}:${x.line} · area ${esc(x.area)} (${esc(x.tier)} risk)</div>${sig}
      <div class="impactline"><b>Impact:</b> ${IMPACT_TEXT[x.change] || ""} ${x.callers.length ? `It has <b>${x.callers.length}</b> direct caller(s) in ${esc(x.caller_areas.join(", "))}; <b style="color:${untested ? "var(--bad)" : "var(--ok)"}">${untested} of them are not reached by any test</b>.` : "No callers were found."} ${x.tests.length ? `${x.tests.length} test(s) call it directly.` : "No test calls it directly."}</div>`;
    drawFlow(x, N, api.edges);
  }
  function drawFlow(x, N, edges) {
    const MAXR = 14;
    const hop1 = x.callers.slice(0, MAXR);
    const hop1Set = new Set(hop1);
    const h2 = []; const seen = new Set();
    edges.forEach((e) => { if (hop1Set.has(e.target) && N[e.source] && N[e.source].hop === 2 && !N[e.source].is_test && !seen.has(e.source)) { seen.add(e.source); h2.push(e.source); } });
    const hop2 = h2.slice(0, MAXR);
    const tests = x.tests.slice(0, MAXR);
    const cols = [{ title: "Callers of callers", ids: hop2, x: 16 }, { title: "Direct callers", ids: hop1, x: 296 }, { title: "Changed API", ids: [x.id], x: 576 }, { title: "Tests calling it", ids: tests, x: 856 }];
    const BW = 248, BH = 46, GAP = 12, TOP = 44;
    const rows = Math.max(1, ...cols.map((c) => c.ids.length));
    const H = TOP + rows * (BH + GAP) + 30, W = 1120;
    const pos = new Map();
    cols.forEach((c) => { const off = TOP + ((rows - c.ids.length) * (BH + GAP)) / 2; c.ids.forEach((id, k) => pos.set(c.title + "|" + id, { x: c.x, y: off + k * (BH + GAP) })); });
    const P = (col, id) => pos.get(col + "|" + id);
    const svg = d3.select("#flowsvg").html("").append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%").attr("style", `min-width:760px;height:auto`);
    const defs = svg.append("defs");
    const mk = (id, c) => defs.append("marker").attr("id", id).attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5).attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto-start-reverse").append("path").attr("d", "M0 0L10 5L0 10z").attr("fill", c);
    const cc = x.change === "signature" || x.change === "removed" ? "#b83a2e" : x.change === "body" ? "#d9480f" : "#2b5fd9";
    mk("fa-main", cc); mk("fa-grey", "#8f99a5"); mk("fa-test", "#2f7d55");
    cols.forEach((c) => svg.append("text").attr("x", c.x + BW / 2).attr("y", 20).attr("text-anchor", "middle").attr("font-size", 12).attr("font-weight", 700).attr("fill", "#667180").text(`${c.title}${c.ids.length ? ` (${c.ids.length}${c.title === "Direct callers" && x.callers.length > MAXR ? ` of ${x.callers.length}` : ""})` : ""}`));
    const link = (a, b, color, marker, dash, w) => {
      const x1 = a.x + BW, y1 = a.y + BH / 2, x2 = b.x, y2 = b.y + BH / 2, mx = (x1 + x2) / 2;
      svg.insert("path", ":first-child").attr("d", `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`).attr("fill", "none").attr("stroke", color).attr("stroke-width", w).attr("stroke-dasharray", dash).attr("marker-end", `url(#${marker})`).attr("opacity", 0.85);
    };
    const count = (s, t) => (edges.find((e) => e.source === s && e.target === t) || {}).count || 1;
    hop2.forEach((id) => edges.filter((e) => e.source === id && hop1Set.has(e.target)).forEach((e) => link(P("Callers of callers", id), P("Direct callers", e.target), "#8f99a5", "fa-grey", "", 1.4)));
    hop1.forEach((id) => link(P("Direct callers", id), P("Changed API", x.id), cc, "fa-main", N[id] && !N[id].tested ? "6 4" : "", 1.2 + Math.min(4, count(id, x.id) * 0.8)));
    tests.forEach((id) => { const a = P("Tests calling it", id), b = P("Changed API", x.id); const x1 = a.x, y1 = a.y + BH / 2, x2 = b.x + BW, y2 = b.y + BH / 2, mx = (x1 + x2) / 2;
      svg.insert("path", ":first-child").attr("d", `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`).attr("fill", "none").attr("stroke", "#2f7d55").attr("stroke-width", 1.4).attr("stroke-dasharray", "5 4").attr("marker-end", "url(#fa-test)"); });
    const tip = $("#tip");
    const box = (col, id, main) => {
      const n = N[id] || { member: id, file: "", area: "", tier: "medium" }; const p = P(col, id);
      const g = svg.append("g").attr("class", "fnode").attr("transform", `translate(${p.x},${p.y})`);
      const testy = n.is_test, dashed = !main && !testy && !n.tested;
      g.append("rect").attr("class", "box").attr("width", BW).attr("height", BH).attr("rx", 8).attr("fill", main ? "#eef3fe" : testy ? "#eaf6ee" : "#fff")
        .attr("stroke", main ? cc : testy ? "#2f7d55" : "#aab3bf").attr("stroke-width", main ? 2 : 1.2).attr("stroke-dasharray", dashed ? "5 3" : "");
      g.append("rect").attr("width", 5).attr("height", BH - 8).attr("x", 4).attr("y", 4).attr("rx", 2).attr("fill", TIER_STROKE[n.tier] || "#888");
      const name = (n.member || "") + (n.member === "(top level)" ? "" : "()");
      g.append("text").attr("x", 16).attr("y", 19).attr("font-family", "var(--mono)").attr("font-size", 12).attr("font-weight", 700).attr("fill", "#18212d").text(name.length > 30 ? name.slice(0, 29) + "…" : name);
      const sub = `${(n.file || "").split("/").pop()} · ${n.area}`;
      g.append("text").attr("x", 16).attr("y", 35).attr("font-size", 10.5).attr("fill", "#667180").text(sub.length > 40 ? sub.slice(0, 39) + "…" : sub);
      const lines = (edges.find((e) => e.source === id) || {}).lines || [];
      const how = main ? IMPACT_TEXT[x.change] : testy ? "Test that exercises this path." : x.change === "signature" ? "Calls a changed contract: check the call still compiles and passes the right arguments."
        : x.change === "removed" ? "Calls an API that no longer exists." : x.change === "body" ? "Gets the new behaviour: check its assumptions still hold." : "Calls the new API.";
      g.on("mousemove", (e) => { tip.innerHTML = `<b>${esc(name)}</b><br>${esc(n.file)}<br>area: ${esc(n.area)} (${esc(n.tier)} risk)${!main && !testy ? `<br>${n.tested ? "reached by a test" : "<b>not reached by any test</b>"}` : ""}<br>${esc(how)}${lines.length ? "<br>call sites: " + esc(lines.join(", ")) : ""}`; tip.style.display = "block"; tip.style.left = Math.min(window.innerWidth - 350, e.clientX + 14) + "px"; tip.style.top = e.clientY + 14 + "px"; })
        .on("mouseleave", () => (tip.style.display = "none"))
        .on("click", () => { S.filter.file = n.file; S.filter.area = null; S.filter.country = null; renderFilters(); renderStream(); toast(`Findings filtered to ${(n.file || "").split("/").pop()}`); });
    };
    hop2.forEach((id) => box("Callers of callers", id));
    hop1.forEach((id) => box("Direct callers", id));
    box("Changed API", x.id, true);
    tests.forEach((id) => box("Tests calling it", id));
    if (!hop1.length && !tests.length) svg.append("text").attr("x", 576 + BW / 2).attr("y", TOP + BH + 30).attr("text-anchor", "middle").attr("font-size", 12).attr("fill", "#667180").text("No callers or tests found in the repository.");
  }

  // ------------------------------------------------------------------ Zone A: world map
  let zoom, svgSel, focusIds = [];
  function renderMap() {
    const g = S.b.graph || { countries: [], cities: [], roads: [] };
    const W = 1200, H = 760;
    svgSel = d3.select("#map").attr("viewBox", `0 0 ${W} ${H}`).attr("preserveAspectRatio", "xMidYMid meet");
    svgSel.selectAll("*").remove();
    if (!g.cities.length) { $("#mapsum").textContent = "No graph data."; return; }

    const countries = g.countries.map((c) => ({ ...c }));
    const cmap = new Map(countries.map((c) => [c.id, c]));
    const allCities = g.cities.map((c) => ({ ...c }));
    const countryOf = new Map(allCities.map((c) => [c.id, c.country]));

    // country roads come from ALL city roads (nothing hidden at the area level)
    const croadMap = new Map();
    g.roads.forEach((r) => {
      const a = countryOf.get(r.source), b = countryOf.get(r.target);
      if (!a || !b || a === b) return;
      const k = a + "→" + b;
      const o = croadMap.get(k) || { source: a, target: b, calls: 0, fog: false, guarded: false, test: true };
      o.calls += r.calls; o.fog = o.fog || r.fog; o.guarded = o.guarded || !!r.guarded_crossing; o.test = o.test && r.kind === "test";
      croadMap.set(k, o);
    });
    const croads = [...croadMap.values()];

    // big PRs: show the most important cities per country, count the rest (they stay in graph.json and the findings)
    const MAXC = 24;
    const prio = (c) => (Object.keys(c.findings || {}).length ? 0 : c.changed && c.members.length ? 1 : c.changed ? 2 : c.role === "caller" ? 3 : 4) * 1000 - (c.churn || 0);
    const cities = [];
    countries.forEach((c) => {
      const mine = allCities.filter((x) => x.country === c.id).sort((p, q) => prio(p) - prio(q));
      c.allChanged = mine.filter((x) => x.changed).length;
      c.cities = mine.slice(0, MAXC);
      c.more = Math.max(0, mine.length - MAXC);
      cities.push(...c.cities);
      c.r = c.touched ? 70 + 24 * Math.sqrt(c.cities.length) : 30 + 9 * Math.log2(1 + c.files);
    });
    const cityById = new Map(cities.map((c) => [c.id, c]));
    const roads = g.roads.filter((r) => cityById.has(r.source) && cityById.has(r.target)).map((r) => ({ ...r, s: cityById.get(r.source), t: cityById.get(r.target) }));

    // place countries: touched near the centre, the rest of the world around them
    const touched = countries.filter((c) => c.touched), other = countries.filter((c) => !c.touched);
    touched.forEach((c, i) => { const a = (i / Math.max(1, touched.length)) * 2 * Math.PI; c.x = W / 2 + Math.cos(a) * 140; c.y = H / 2 + Math.sin(a) * 100; });
    other.forEach((c, i) => { const a = (i / Math.max(1, other.length)) * 2 * Math.PI + 0.4; c.x = W / 2 + Math.cos(a) * 460; c.y = H / 2 + Math.sin(a) * 300; });
    const links = croads.map((r) => ({ source: r.source, target: r.target }));
    const sim = d3.forceSimulation(countries)
      .force("collide", d3.forceCollide((d) => d.r + 16).iterations(3))
      .force("x", d3.forceX(W / 2).strength((d) => (d.touched ? 0.07 : 0.025)))
      .force("y", d3.forceY(H / 2).strength((d) => (d.touched ? 0.1 : 0.04)))
      .force("link", d3.forceLink(links).id((d) => d.id).distance((d) => d.source.r + d.target.r + 40).strength(0.35))
      .stop();
    for (let i = 0; i < 420; i++) sim.tick();
    countries.forEach((c) => { c.x = Math.max(c.r + 24, Math.min(W - c.r - 24, c.x)); c.y = Math.max(c.r + 24, Math.min(H - c.r - 24, c.y)); });

    // place cities inside their country
    cities.forEach((c, i) => { const k = cmap.get(c.country); const a = i * 2.39996; c.x = k.x + Math.cos(a) * k.r * 0.3; c.y = k.y + Math.sin(a) * k.r * 0.3; });
    const csim = d3.forceSimulation(cities)
      .force("collide", d3.forceCollide(34))
      .force("x", d3.forceX((d) => cmap.get(d.country).x).strength(0.3))
      .force("y", d3.forceY((d) => cmap.get(d.country).y + 10).strength(0.3))
      .stop();
    for (let i = 0; i < 300; i++) csim.tick();
    cities.forEach((c) => { const k = cmap.get(c.country); const dx = c.x - k.x, dy = c.y - k.y, d = Math.hypot(dx, dy) || 1, lim = k.r * 0.6; if (d > lim) { c.x = k.x + (dx / d) * lim; c.y = k.y + (dy / d) * lim; } });

    // country shapes: smooth contour of a field around the country centre and its cities
    const STEP = 6, GW = Math.ceil(W / STEP) + 1, GH = Math.ceil(H / STEP) + 1;
    const noise = (x, y) => Math.sin(x * 0.021 + 1.3) * Math.cos(y * 0.017 - 0.4) * 0.6 + Math.sin(x * 0.043 + y * 0.037) * 0.4;
    const fields = countries.map(() => new Float64Array(GW * GH));
    const vals = new Float64Array(countries.length);
    for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) {
      const x = i * STEP, y = j * STEP;
      countries.forEach((c, ci) => {
        let best = 1 - (Math.hypot(x - c.x, (y - c.y) * 1.1) / c.r) * (1 + 0.13 * noise(x + ci * 91, y - ci * 37));
        for (const p of c.cities) best = Math.max(best, 1 - Math.hypot(x - p.x, y - p.y) / 52);
        vals[ci] = best;
      });
      for (let k = 0; k < countries.length; k++) {
        let m = vals[k];
        for (let q = 0; q < countries.length; q++) if (q !== k) m = Math.min(m, (vals[k] - vals[q]) * 1.2);
        fields[k][j * GW + i] = m;
      }
    }
    const smooth = d3.line().curve(d3.curveBasisClosed);
    countries.forEach((c, k) => {
      const ct = d3.contours().size([GW, GH]).thresholds([0])(fields[k])[0];
      c.d = ct.coordinates.map((poly) => poly.map((ring) => smooth(ring.slice(0, -1).map(([x, y]) => [x * STEP, y * STEP]))).join("")).join("");
    });

    // ---- draw
    const defs = svgSel.append("defs");
    const sg = defs.append("radialGradient").attr("id", "sea").attr("cx", "50%").attr("cy", "45%").attr("r", "75%");
    sg.append("stop").attr("offset", "0%").attr("stop-color", "#dbe8f2"); sg.append("stop").attr("offset", "100%").attr("stop-color", "#b9cfe2");
    defs.append("filter").attr("id", "relief").attr("x", "-5%").attr("y", "-5%").attr("width", "110%").attr("height", "115%")
      .append("feDropShadow").attr("dx", 0).attr("dy", 3).attr("stdDeviation", 4).attr("flood-color", "#2a4058").attr("flood-opacity", 0.28);
    const mk = (id, color) => defs.append("marker").attr("id", id).attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5).attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto-start-reverse").append("path").attr("d", "M0 0L10 5L0 10z").attr("fill", color);
    mk("ar-impact", "#d9480f"); mk("ar-test", "#2f7d55"); mk("ar-fog", "#8f99a5"); mk("ar-guard", "#b83a2e");
    svgSel.append("rect").attr("x", -3000).attr("y", -3000).attr("width", 7000).attr("height", 7000).attr("fill", "#b9cfe2");
    const world = svgSel.append("g");
    world.append("rect").attr("x", -80).attr("y", -80).attr("width", W + 160).attr("height", H + 160).attr("fill", "url(#sea)");
    const grat = world.append("g");
    for (let x = 0; x <= W; x += 100) grat.append("line").attr("x1", x).attr("x2", x).attr("y1", -80).attr("y2", H + 80).attr("stroke", "#fff").attr("stroke-opacity", 0.4).attr("vector-effect", "non-scaling-stroke");
    for (let y = 0; y <= H; y += 100) grat.append("line").attr("y1", y).attr("y2", y).attr("x1", -80).attr("x2", W + 80).attr("stroke", "#fff").attr("stroke-opacity", 0.4).attr("vector-effect", "non-scaling-stroke");

    const scaled = [];
    const tip = $("#tip");
    const showTip = (e, html) => { tip.innerHTML = html; tip.style.display = "block"; tip.style.left = Math.min(window.innerWidth - 350, e.clientX + 14) + "px"; tip.style.top = e.clientY + 14 + "px"; };
    const hideTip = () => (tip.style.display = "none");

    const landG = world.append("g").attr("filter", "url(#relief)");
    countries.forEach((c) => {
      landG.append("path").attr("d", c.d).attr("class", "land" + (c.touched ? "" : " dim")).attr("fill-rule", "evenodd").attr("fill", TIER_FILL[c.tier] || TIER_FILL.medium)
        .on("mousemove", (e) => showTip(e, `<b>${esc(c.name)}</b> · risk tier ${esc(c.tier)}${c.guarded ? " · guarded" : ""}<br>${esc(c.why)}<br>${c.files} file(s) in repo · ${c.changed} changed in this PR`))
        .on("mouseleave", hideTip)
        .on("click", () => { S.filter.file = null; S.filter.area = null; S.filter.country = c.id; renderFilters(); renderStream(); });
    });
    const outG = world.append("g").style("pointer-events", "none");
    countries.forEach((c) => {
      if (c.guarded) {
        outG.append("path").attr("d", c.d).attr("fill", "none").attr("stroke", "#fff").attr("stroke-width", 4.5).attr("vector-effect", "non-scaling-stroke");
        outG.append("path").attr("d", c.d).attr("fill", "none").attr("stroke", "#b83a2e").attr("stroke-width", 2.2).attr("stroke-dasharray", "7 4").attr("vector-effect", "non-scaling-stroke");
      } else outG.append("path").attr("d", c.d).attr("fill", "none").attr("stroke", TIER_STROKE[c.tier] || "#888").attr("stroke-opacity", c.touched ? 0.6 : 0.3).attr("stroke-width", 1.3).attr("vector-effect", "non-scaling-stroke");
    });

    const style = (r) => r.guarded ? ["#b83a2e", "7 5", "ar-guard"] : r.fog ? ["#8f99a5", "2 6", "ar-fog"] : r.test || r.kind === "test" ? ["#2f7d55", "6 5", "ar-test"] : ["#d9480f", "", "ar-impact"];
    const curve = (a, b, bend = 0.12) => { const mx = (a.x + b.x) / 2 + (a.y - b.y) * bend, my = (a.y + b.y) / 2 + (b.x - a.x) * bend; return [`M${a.x},${a.y}Q${mx},${my} ${b.x},${b.y}`, mx, my]; };
    // country roads (zoomed out)
    const roadG = world.append("g").attr("class", "L1");
    croads.forEach((r) => {
      const a = cmap.get(r.source), b = cmap.get(r.target); if (!a || !b) return;
      const [d, mx, my] = curve({ x: a.x, y: a.y }, { x: b.x, y: b.y }); const s = style(r);
      roadG.append("path").attr("d", d).attr("fill", "none").attr("stroke", s[0]).attr("stroke-width", 2 + Math.min(4, r.calls)).attr("stroke-dasharray", s[1]).attr("stroke-linecap", "round").attr("vector-effect", "non-scaling-stroke").attr("marker-end", `url(#${s[2]})`).attr("opacity", 0.9);
      if (r.fog || r.guarded) { const t = roadG.append("text").attr("x", (a.x + b.x) / 4 + mx / 2).attr("y", (a.y + b.y) / 4 + my / 2).attr("text-anchor", "middle").attr("dominant-baseline", "middle").text(r.guarded ? "⛔" : "☁️"); scaled.push([t, "font-size", 20]); }
    });
    // city roads (zoomed in)
    const edgeG = world.append("g").attr("class", "L2");
    roads.forEach((r) => {
      const [d, mx, my] = curve(r.s, r.t, 0.1); const s = style(r);
      edgeG.append("path").attr("d", d).attr("fill", "none").attr("stroke", s[0]).attr("stroke-width", 1.6 + Math.min(3, r.calls * 0.6)).attr("stroke-dasharray", s[1]).attr("vector-effect", "non-scaling-stroke").attr("marker-end", `url(#${s[2]})`).attr("opacity", 0.95)
        .on("mousemove", (e) => showTip(e, `<b>${esc(r.s.name)}</b> → <b>${esc(r.t.name)}</b><br>${r.calls} call(s) to ${esc(r.members.join(", "))}${r.fog ? "<br>☁ no test references this member" : ""}${r.kind === "test" ? "<br>test reference" : ""}`))
        .on("mouseleave", hideTip);
    });
    // labels
    const labelG = world.append("g");
    countries.forEach((c) => {
      const t = labelG.append("text").attr("class", "cname").attr("x", c.x).attr("y", c.y - c.r * 0.62).attr("text-anchor", "middle").text((c.guarded ? "🛂 " : "") + c.name);
      scaled.push([t, "font-size", c.touched ? 17 : 13]);
      if (c.touched) {
        const s = labelG.append("text").attr("class", "csub").attr("x", c.x).attr("y", c.y - c.r * 0.62).attr("text-anchor", "middle").attr("fill", TIER_STROKE[c.tier]).text(`risk ${c.tier}${c.changed ? ` · ${c.allChanged} changed` : " · reached"}`);
        scaled.push([s, "font-size", 12], [s, "dy", 17]);
        if (c.allChanged) {   // one pin per country when zoomed out
          const pg = labelG.append("g").attr("class", "L1");
          pg.append("path").attr("d", "M0,0 C-6,-9 -11,-14 -11,-21 A11,11 0 1 1 11,-21 C11,-14 6,-9 0,0Z").attr("fill", "#b83a2e").attr("stroke", "#fff").attr("stroke-width", 2);
          pg.append("text").attr("y", -17).attr("text-anchor", "middle").attr("fill", "#fff").attr("font-size", 10).attr("font-weight", 700).text(c.allChanged > 99 ? "99+" : c.allChanged);
          scaled.push([pg, "pin", [c.x, c.y + 14]]);
        }
        if (c.more) {
          const m = labelG.append("text").attr("class", "nsub L2").attr("x", c.x).attr("y", c.y + c.r * 0.72).attr("text-anchor", "middle").text(`+${c.more} more file(s) not drawn`);
          scaled.push([m, "font-size", 10.5]);
        }
      }
    });
    // cities
    const maxChurn = d3.max(cities, (c) => c.churn) || 1;
    const nodeG = world.append("g");
    cities.forEach((c) => {
      const g2 = nodeG.append("g").style("cursor", "pointer")
        .on("mousemove", (e) => showTip(e, `<b>${esc(c.path)}</b><br>${c.changed ? `changed (+${c.n_added}/−${c.n_removed})` : c.role === "test" ? "test that references the change" : "calls the changed code"}<br>churn: ${c.churn} commit(s) in history${c.members.length ? "<br>changed members: " + c.members.map((m) => `${esc(m.name)} (${m.callers} callers, ${m.tests} test refs)`).join(", ") : ""}${Object.keys(c.findings).length ? "<br>findings: " + Object.entries(c.findings).map(([k, v]) => `${v} ${k}`).join(", ") : ""}`))
        .on("mouseleave", hideTip)
        .on("click", () => { S.filter.file = c.path; S.filter.area = null; S.filter.country = null; renderFilters(); renderStream(); $("#stream").scrollTop = 0; });
      const heat = g2.append("circle").attr("class", "L2").attr("cx", c.x).attr("cy", c.y).attr("fill", "none").attr("stroke", "#e8590c").attr("stroke-opacity", 0.12 + 0.6 * (c.churn / maxChurn)).attr("vector-effect", "non-scaling-stroke");
      scaled.push([heat, "r", 14], [heat, "stroke-width", 5]);
      const fill = c.changed ? "#b83a2e" : c.role === "test" ? "#2f7d55" : "#f08c5a";
      const dot = g2.append("circle").attr("class", "L2").attr("cx", c.x).attr("cy", c.y).attr("fill", fill).attr("stroke", "#fff").attr("stroke-width", 1.5).attr("vector-effect", "non-scaling-stroke");
      scaled.push([dot, "r", 6.5]);
      const lab = g2.append("text").attr("class", "nlabel L2").attr("x", c.x).attr("y", c.y).text(c.name);
      scaled.push([lab, "font-size", 11.5], [lab, "dx", 11], [lab, "dy", 4]);
      const fcount = Object.entries(c.findings).map(([k, v]) => `${v} ${k}`).join(" · ");
      const sub = g2.append("text").attr("class", "nsub L3").attr("x", c.x).attr("y", c.y)
        .text(`${c.churn} commits` + (c.changed ? ` · +${c.n_added}/−${c.n_removed}` : "") + (fcount ? ` · ${fcount}` : ""));
      scaled.push([sub, "font-size", 9.5], [sub, "dx", 11], [sub, "dy", 16]);
      c.members.forEach((m, i) => {
        const mt = g2.append("text").attr("class", "nsub L3").attr("x", c.x).attr("y", c.y).attr("fill", m.untested ? "#b83a2e" : "#4f5b69")
          .text(`${m.untested ? "☁ " : ""}${m.name}() · ${m.callers} callers · ${m.tests} test refs`);
        scaled.push([mt, "font-size", 9.5], [mt, "dx", 11], [mt, "dy", 28 + i * 11]);
      });
      if (c.changed) {
        const pin = g2.append("g").attr("class", "L2");
        pin.append("path").attr("d", "M0,0 C-6,-9 -11,-14 -11,-21 A11,11 0 1 1 11,-21 C11,-14 6,-9 0,0Z").attr("fill", "#b83a2e").attr("stroke", "#fff").attr("stroke-width", 2);
        pin.append("circle").attr("cy", -21).attr("r", 4.2).attr("fill", "#fff");
        scaled.push([pin, "pin", [c.x, c.y]]);
      }
    });
    focusIds = cities.filter((c) => c.changed).map((c) => [c.x, c.y]);

    // zoom
    let K = 1;
    const rescale = () => scaled.forEach(([sel, attr, base]) => {
      if (attr === "pin") sel.attr("transform", `translate(${base[0]},${base[1]}) scale(${1 / Math.max(1, K * 0.75)})`);
      else sel.attr(attr, base / Math.max(1, K * 0.75));
    });
    const lvl = (k) => (k < 1.45 ? 1 : k < 2.9 ? 2 : 3);
    zoom = d3.zoom().scaleExtent([0.6, 9]).translateExtent([[-400, -400], [W + 400, H + 400]]).on("zoom", (e) => {
      world.attr("transform", e.transform); K = e.transform.k; rescale();
      const L = lvl(K), el = $("#map"); el.classList.remove("lvl1", "lvl2", "lvl3"); el.classList.add("lvl" + L);
      [1, 2, 3].forEach((i) => $("#lv" + i).classList.toggle("on", i === L));
    });
    svgSel.call(zoom).on("dblclick.zoom", null);
    const home = d3.zoomIdentity.translate(W / 2, H / 2).scale(0.95).translate(-W / 2, -H / 2);
    svgSel.call(zoom.transform, home);
    $("#zin").onclick = () => svgSel.transition().duration(250).call(zoom.scaleBy, 1.6);
    $("#zout").onclick = () => svgSel.transition().duration(250).call(zoom.scaleBy, 1 / 1.6);
    $("#zfit").onclick = () => svgSel.transition().duration(400).call(zoom.transform, home);
    $("#zfocus").onclick = () => {
      const pts = cities.filter((c) => c.changed || c.hop === 1).map((c) => [c.x, c.y]);
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const k = Math.max(1.6, Math.min(4, W / (x1 - x0 + 300), H / (y1 - y0 + 260)));
      svgSel.transition().duration(600).call(zoom.transform, d3.zoomIdentity.translate(W / 2, H / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
    };

    const ch = countries.filter((c) => c.changed).map((c) => c.name), reached = countries.filter((c) => c.touched && !c.changed).map((c) => c.name);
    const fogN = roads.filter((r) => r.fog).length, guardN = roads.filter((r) => r.guarded_crossing).length;
    $("#mapsum").innerHTML = `📍 Changed in <b>${esc(ch.join(", ") || "—")}</b>. ` + (reached.length ? `The change reaches <b>${esc(reached.join(", "))}</b>. ` : "")
      + (fogN ? `☁ ${fogN} road(s) carry untested members. ` : "") + (guardN ? `⛔ ${guardN} road(s) cross a guarded border. ` : "")
      + `<span class="small">Zoom in to see files and members.</span>`;
  }

  // ------------------------------------------------------------------ Zone B: radar
  function renderRadar() {
    const r = S.b.review.radar;
    const el = $("#radar");
    if (!r) { el.innerHTML = '<p class="empty">Radar not built for this run.</p>'; return; }
    const c = r.counts || {};
    const hunks = r.hunks || [], items = r.items || [];
    let h = `<div class="counts">
      ${["aligned", "supporting", "tangled", "unclear"].map((k) => `<span class="pill c-${k}">${c[k] || 0} ${k}</span>`).join("")}
      <span style="width:10px"></span>
      ${["covered", "partial", "missing"].map((k) => `<span class="pill st-${k}">${c["item_" + k] || 0} ${k}</span>`).join("")}
    </div>`;
    if (r.note) h += `<p class="small">${esc(r.note)}</p>`;
    if (items.length) {
      h += `<div class="items">` + items.map((it) => `<div class="item"><span class="id">${esc(it.id)}</span>
        <div><div>${esc(it.text)}</div><div class="small">${esc(it.reason)}</div>
        <div>${it.hunk_ids.map((x) => `<span class="hchip" data-h="${esc(x)}">${esc(x)}</span>`).join("")}</div></div>
        <span class="pill st-${esc(it.status)}">${esc(it.status.toUpperCase())}</span></div>`).join("") + `</div>`;
    }
    // matrix: rows = requirement items + tangled + unclear, columns = hunks
    const rows = items.map((it) => ({ label: `${it.id} ${it.text}`, test: (hk) => (hk.item_ids || []).includes(it.id) }))
      .concat([{ label: "Not requested (tangled)", test: (hk) => hk.classification === "tangled" }, { label: "Unclear", test: (hk) => hk.classification === "unclear" }]);
    const color = { aligned: "#2b5fd9", supporting: "#1d9a8f", tangled: "#b83a2e", unclear: "#9aa3ad" };
    h += `<div class="matrix"><table><thead><tr><th class="rowh">Requirement ↓ · Hunk →</th>${hunks.map((hk) => `<th data-h="${esc(hk.id)}" title="${esc(hk.file)}:${hk.start}-${hk.end}">${esc(hk.id)}<span class="f">${esc(hk.file.split("/").pop())}</span></th>`).join("")}</tr></thead><tbody>`
      + rows.map((row) => `<tr><th class="rowh" title="${esc(row.label)}">${esc(row.label)}</th>${hunks.map((hk) => row.test(hk) ? `<td><span class="cell" style="background:${color[hk.classification] || "#9aa3ad"}" title="${esc(hk.classification)}: ${esc(hk.reason)}"></span></td>` : "<td></td>").join("")}</tr>`).join("")
      + `</tbody></table></div><div class="small" style="margin-top:6px">Blue = implements · teal = supports (tests, plumbing) · red = not requested · grey = unclear. Click a hunk to see its code.</div>
      <div class="hunkview" id="hunkview"></div>`;
    el.innerHTML = h;
    el.querySelectorAll("[data-h]").forEach((n) => n.onclick = () => showHunk(n.dataset.h));
  }
  function showHunk(id) {
    const hk = (S.b.review.radar.hunks || []).find((x) => x.id === id); if (!hk) return;
    const v = $("#hunkview");
    v.innerHTML = `<div class="h"><b>${esc(hk.id)}</b> · ${esc(hk.file)}:${hk.start}-${hk.end} · <span class="pill c-${esc(hk.classification)}">${esc(hk.classification)}</span> ${esc(hk.reason || "")}</div>
      <pre class="diff" style="margin:0;border-radius:0 0 8px 8px">${hk.removed.map((l) => `<span class="d">- ${esc(l)}</span>`).join("\n")}${hk.removed.length && hk.added.length ? "\n" : ""}${hk.added.map((l) => `<span class="a">+ ${esc(l)}</span>`).join("\n")}</pre>`;
    v.classList.add("on");
  }

  // ------------------------------------------------------------------ Zone C: evidence
  function renderEvidence() {
    const r = S.b.review, f = r.funnel || {};
    const kept = (f.evidence_verified || 0) - (f.dropped_by_validator || 0);
    const rows = [["Proposed by specialists", f.proposed_by_specialists || 0, "#9aa3ad"],
      ["Evidence found in the code", f.evidence_verified || 0, "#6b8fd6"],
      ["Kept by validator (Q1–Q3)", Math.max(0, kept), "#2b5fd9"],
      ["Deterministic sensor findings", f.sensor_findings || 0, "#1d9a8f"],
      ["Shown to you", f.shown || 0, "#18212d"],
      ["Ready-to-apply patches", f.patches || 0, "#2f7d55"]];
    const max = Math.max(1, ...rows.map((x) => x[1]));
    let h = `<div class="sub2" style="margin-top:0">Noise funnel</div><div class="funnel">` + rows.map(([l, n, c]) => `<div class="frow"><span>${esc(l)}</span><div class="ftrack"><div class="fbar" style="width:${(n / max) * 100}%;background:${c}"></div></div><b>${n}</b></div>`).join("")
      + `</div><div class="small">${f.dropped_hallucinated_evidence || 0} finding(s) dropped because their quoted code was not at the cited lines; ${f.dropped_by_validator || 0} removed as hallucination, nitpick or duplicate.</div>`;
    h += `<div class="sub2">Deterministic sensors &amp; execution logs</div><table class="t"><tr><th>Sensor</th><th>Result</th><th>Summary</th><th></th></tr>`
      + r.sensors.map((s, i) => { const res = !s.ran ? ["not run", "r-na"] : s.passed === false ? ["FAIL", "r-fail"] : ["pass", "r-pass"];
        return `<tr><td class="mono">${esc(s.name)}</td><td><span class="pill ${res[1]}">${res[0]}</span></td><td>${esc(s.summary)}</td><td>${s.log_file ? `<button class="linkbtn" data-log="${i}">log</button>` : ""}</td></tr>`; }).join("") + `</table>`;
    const d = r.delta || {};
    h += `<div class="sub2">Since the last review of this branch</div>`;
    if (!d.previous_run) h += `<p class="empty">${esc(d.summary || "First review of this branch")}</p>`;
    else h += `<p style="margin:0 0 4px">${esc(d.summary)} <span class="small">(previous: ${esc(d.previous_run)}, ${esc(d.previous_decision)})</span></p><ul class="plain">`
      + (d.fixed || []).map((x) => `<li>✅ Fixed: [${esc(x.severity)}] ${esc(x.title)}</li>`).join("")
      + (d.still_open || []).map((x) => `<li>⏳ Still open: [${esc(x.severity)}] ${esc(x.title)} (now ${esc(x.now_id)})</li>`).join("")
      + (d.new || []).map((x) => `<li>🆕 New: [${esc(x.severity)}] ${esc(x.title)}</li>`).join("") + `</ul>`;
    const tr = r.track_record || {};
    h += `<div class="sub2">Reviewer track record (from human feedback)</div>`;
    h += Object.keys(tr).length ? `<table class="t"><tr><th>Dimension</th><th>Accepted</th><th>Rejected</th><th>Escapes</th><th>Precision</th><th>Trust</th></tr>`
      + Object.entries(tr).map(([k, t]) => `<tr><td>${esc(k)}</td><td>${t.accepted}</td><td>${t.rejected}</td><td>${t.escapes}</td><td>${t.precision ?? "—"}</td><td>${esc(t.trust)}</td></tr>`).join("") + `</table>` : `<p class="empty">No feedback yet.</p>`;
    h += `<div class="sub2">What the AI refused to decide, and why</div><ul class="plain">` + (r.refusals.length ? r.refusals.map((x) => `<li><b>${esc(x.topic)}</b> <span class="small">(${esc(x.source)})</span>: ${esc(x.reason)}</li>`).join("") : "<li>Nothing.</li>") + `</ul>`;
    h += `<div class="sub2">Not checked</div><ul class="plain">` + (r.not_checked.length ? r.not_checked.map((x) => `<li>${esc(x)}</li>`).join("") : "<li>Everything in scope was checked.</li>") + `</ul>`;
    h += `<div class="small" style="margin-top:10px">Run ${esc(r.run_id)} · head ${esc((r.head_sha || "").slice(0, 10))} · policy ${esc(r.policy_version)} (approved by ${esc(r.policy_approved_by || "nobody yet")}) · models ${esc(JSON.stringify(r.models))}</div>`;
    $("#evidence").innerHTML = h;
    $("#evidence").querySelectorAll("[data-log]").forEach((b) => b.onclick = () => {
      const s = r.sensors[+b.dataset.log]; const text = (S.b.evidence || {})[s.log_file];
      modal(`${s.name} · ${s.log_file}`, text || `${s.summary}\n\n${(s.details || []).join("\n")}\n\n(full log is in the run folder: ${s.log_file})`);
    });
  }

  // ------------------------------------------------------------------ Zone D: findings
  function visibleFindings() {
    let fs = S.b.review.findings.slice();
    const f = S.filter;
    if (f.sev !== "all") fs = fs.filter((x) => x.severity === f.sev);
    if (f.file) fs = fs.filter((x) => x.file === f.file);
    if (f.country) { const files = new Set((S.b.graph.cities || []).filter((c) => c.country === f.country).map((c) => c.path)); fs = fs.filter((x) => files.has(x.file)); }
    if (f.area) {
      const area = S.b.review.areas.find((a) => a.area === f.area);
      const ids = new Set(((area && area.evidence) || []).map((e) => e.split(" ")[0]));
      fs = fs.filter((x) => ids.has(x.id) || AREA_FOR_DIM[x.dimension] === f.area);
    }
    return fs;
  }
  function renderFilters() {
    const f = S.filter, all = S.b.review.findings;
    const n = (s) => all.filter((x) => x.severity === s).length;
    const opts = [["all", `All ${all.length}`], ["Blocker", `Blocker ${n("Blocker")}`], ["ShouldFix", `Should fix ${n("ShouldFix")}`], ["Nit", `Nit ${n("Nit")}`]];
    let h = opts.map(([k, l]) => `<button class="fbtn ${f.sev === k ? "on" : ""}" data-sev="${k}">${esc(l)}</button>`).join("");
    const active = f.file ? `file: ${f.file.split("/").pop()}` : f.country ? `country: ${f.country}` : f.area ? `area: ${f.area}` : "";
    if (active) h += `<button class="fbtn on" id="clearf">${esc(active)} ✕</button>`;
    $("#filters").innerHTML = h;
    $("#filters").querySelectorAll("[data-sev]").forEach((b) => b.onclick = () => { S.filter.sev = b.dataset.sev; renderFilters(); renderStream(); });
    const c = $("#clearf"); if (c) c.onclick = () => { S.filter.file = S.filter.country = S.filter.area = null; renderAreas(); renderFilters(); renderStream(); };
  }
  function diffHtml(p) {
    return p.split("\n").map((l) => `<span class="${l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@") ? "h" : l.startsWith("+") ? "a" : l.startsWith("-") ? "d" : ""}">${esc(l)}</span>`).join("\n");
  }
  function findingHtml(x) {
    const cite = new Set(); for (let n = Math.min(x.line_start, x.line_end); n <= Math.max(x.line_start, x.line_end); n++) cite.add(n);
    const code = (x.anchor || []).length ? `<div class="code"><table>${x.anchor.map(([n, t, chg]) => `<tr class="${cite.has(n) ? "cite" : chg ? "ch" : ""}"><td class="n">${chg ? "+" : " "}${n}</td><td>${esc(t)}</td></tr>`).join("")}</table></div>`
      : x.evidence ? `<div class="code"><table><tr class="cite"><td class="n">−</td><td>${esc(x.evidence)}</td></tr></table></div><div class="small">Quoted from removed code.</div>` : "";
    const v = x.validator || {};
    const q = v.q3_severity ? `<div class="qchips"><span class="q">Q1 nitpick: ${v.q1_nitpick ? "yes" : "no"}</span><span class="q">Q2 hallucination: ${v.q2_hallucination ? "yes" : "no"}</span><span class="q">Q3 severity: ${esc(v.q3_severity)}</span><span class="q">${esc(v.reason || "")}</span></div>` : "";
    const fb = S.feedback[x.id];
    const live = S.mode === "live";
    return `<div class="finding" data-id="${esc(x.id)}">
      <div class="fhead"><span class="sev sev-${esc(x.severity)}">${SEV_LABEL[x.severity] || x.severity}</span><span class="mono small">${esc(x.id)}</span><span class="ftitle">${esc(x.title)}</span>${x.delta ? `<span class="delta delta-${esc(x.delta)}">${esc(x.delta)}</span>` : ""}</div>
      <div class="fmeta"><span class="mono">${esc(x.file)}:${x.line_start}</span> · ${esc(x.dimension)} · ${esc(x.source)}${x.source.startsWith("specialist") ? ` · confidence ${(+x.confidence).toFixed(2)}` : " · deterministic"}${x.evidence_verified ? " · evidence verified" : ""}</div>
      <div class="fclaim">${esc(x.claim)}</div>${code}
      ${x.requirement_link && x.requirement_link !== "none" ? `<div class="small" style="margin-top:6px">Requirement: ${esc(x.requirement_link)}</div>` : ""}
      ${x.suggested_fix ? `<div class="small" style="margin-top:4px">Fix: ${esc(x.suggested_fix)}</div>` : ""}${q}
      ${x.patch ? `<details class="patch"><summary>Ready-to-apply patch · ${esc(x.patch_explanation)}</summary><pre class="diff">${diffHtml(x.patch)}</pre></details>` : ""}
      <div class="actions">
        ${x.patch ? `<button class="btn" data-copy="${esc(x.id)}">Copy patch</button>` : ""}
        <button class="btn acc ${fb === "accepted" ? "on" : ""}" data-fb="accepted" ${live ? "" : "disabled title='Static file: open the live dashboard to record feedback'"}>✓ Real issue</button>
        <button class="btn rej ${fb === "rejected" ? "on" : ""}" data-fb="rejected" ${live ? "" : "disabled title='Static file: open the live dashboard to record feedback'"}>✕ Noise</button>
      </div></div>`;
  }
  function renderStream() {
    const fs = visibleFindings(), all = S.b.review;
    $("#streamhint").textContent = `${fs.length} shown · ${all.dropped_findings.length} filtered`;
    let h = fs.length ? fs.map(findingHtml).join("") : `<div class="finding empty">No findings for this filter.</div>`;
    if (all.dropped_findings.length) {
      h += `<details class="finding"><summary class="small" style="cursor:pointer">Filtered out before you saw them (${all.dropped_findings.length}) · audit</summary><table class="t" style="margin-top:6px"><tr><th>ID</th><th>Title</th><th>Why filtered</th></tr>`
        + all.dropped_findings.map((x) => `<tr><td class="mono">${esc(x.id)}</td><td>${esc(x.title)}</td><td>${esc(x.drop_reason)}</td></tr>`).join("") + `</table></details>`;
    }
    const el = $("#stream"); el.innerHTML = h;
    el.querySelectorAll("[data-copy]").forEach((b) => b.onclick = () => { const x = all.findings.find((f) => f.id === b.dataset.copy); copy(x.patch); });
    el.querySelectorAll("[data-fb]").forEach((b) => b.onclick = () => sendFeedback(b.closest(".finding").dataset.id, b.dataset.fb));
  }
  async function sendFeedback(id, verdict) {
    const by = (localStorageGet("reviewer") || S.b.review.owner || "").trim();
    try {
      const res = await fetch(API + "/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: S.b.review.run_id, finding_id: id, verdict, by }) });
      const j = await res.json(); if (!j.ok) throw new Error(j.error || "failed");
      S.feedback[id] = verdict; S.b.review.track_record = j.track_record; renderStream(); renderEvidence(); toast(`Recorded: ${id} ${verdict}`);
    } catch (e) { toast("Could not record feedback: " + e.message); }
  }
  function localStorageGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function localStorageSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } }

  // ------------------------------------------------------------------ sign-off
  function renderSignoff() {
    const r = S.b.review, el = $("#signoff");
    const human = r.areas.filter((a) => a.status === "human"), blocked = r.areas.filter((a) => a.status === "blocked");
    if (S.b.signoff) { el.innerHTML = `<div class="record">${esc(S.b.signoff.record)}</div>`; return; }
    if (blocked.length) {
      el.innerHTML = `<div class="locked">🔒 Merge locked. The reviewer can lock but never unlock.</div><ul class="plain" style="margin-top:8px">${blocked.map((a) => `<li><b>${esc(a.area)}</b>: ${esc(a.reason)}</li>`).join("")}</ul>
        <p class="small">To unlock: fix the blocking findings (patches are ready where possible) and review again, or amend the requirement/rulebook through its owner.</p>`;
      return;
    }
    const two = r.tier.signoffs_required > 1;
    el.innerHTML = `${human.length ? '<div class="small">Only these need you. Everything else is verified with evidence.</div>' : '<div class="small">Every area is verified with evidence. You still own the decision.</div>'}
      ${human.map((a, i) => `<label><input type="checkbox" class="ck"> <span><b>${esc(a.area)}</b>: ${esc(a.reason)}</span></label>`).join("")}
      <div style="margin-top:8px"><b>Residual risk I accept</b></div><textarea id="risk" placeholder="e.g. Report layout checked manually; follow-up ticket for the error text."></textarea>
      <div style="margin-top:8px"><b>Owner</b></div><input type="text" id="owner" value="${esc(localStorageGet("reviewer") || (r.owner !== "UNASSIGNED" ? r.owner : ""))}">
      ${two ? `<label style="margin-top:6px"><input type="checkbox" id="second"> <span>A second signer has reviewed (four eyes):</span></label><input type="text" id="second_name" placeholder="Second signer name">` : ""}
      <div class="actions"><button class="btn primary" id="signbtn" disabled>Sign</button></div>`;
    const upd = () => {
      const ok = [...el.querySelectorAll(".ck")].every((x) => x.checked) && $("#risk").value.trim().length > 3 && $("#owner").value.trim().length > 1
        && (!two || ($("#second").checked && $("#second_name").value.trim().length > 1));
      $("#signbtn").disabled = !ok;
    };
    el.querySelectorAll("input,textarea").forEach((x) => x.addEventListener("input", upd));
    $("#signbtn").onclick = async () => {
      const owner = $("#owner").value.trim(); localStorageSet("reviewer", owner);
      const verified = r.areas.filter((a) => a.status === "verified").map((a) => a.area);
      const record = [`SIGN-OFF · ${r.head} → ${r.base} · ${r.requirement_id}`, `Signed by: ${owner}${two ? " and " + $("#second_name").value.trim() : ""}`, `Date: ${new Date().toISOString()}`,
        `Decision before sign-off: ${r.decision}`, `Checked by AI and tools: ${verified.join(", ") || "none"}`, `Checked by human: ${human.map((a) => a.area).join(", ") || "none needed"}`,
        `Not checked: ${r.not_checked.join("; ") || "none"}`, `Refused by AI: ${r.refusals.map((x) => x.topic).join("; ") || "none"}`, `Residual risk accepted: ${$("#risk").value.trim()}`,
        `Evidence: run ${r.run_id}, head ${r.head_sha}, policy ${r.policy_version}, models ${JSON.stringify(r.models)}`].join("\n");
      if (S.mode === "live") {
        try { await fetch(API + "/api/signoff", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ run_id: r.run_id, record, owner }) }); toast("Sign-off saved to the run folder"); }
        catch (e) { toast("Could not save; copy the record instead"); }
      }
      S.b.signoff = { record };
      el.innerHTML = `<div class="record">${esc(record)}</div><div class="actions"><button class="btn" id="copyrec">Copy record</button></div>`;
      $("#copyrec").onclick = () => copy(record);
    };
  }

  boot();
})();
