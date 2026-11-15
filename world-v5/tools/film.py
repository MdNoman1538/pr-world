#!/usr/bin/env python3
"""
PR World — the 1:59 film ("Seeing Is Believing"), Retina quality.

Act 1 (0:00-0:24)  three research cards and the title
Act 2 (0:24-1:44)  the app, recorded live, each shot cut to its exact length
Act 3 (1:44-1:59)  the architecture with the benchmark result, and the closing card

Run from world-v5 with the app running (./run_world.sh --view):
    ../ai-reviewer/.venv/bin/python tools/film.py
Options: --size WxH (default: fits your screen) · --scale 2 · --list · --diagram path/to/diagram-architecture.png
Needs ffmpeg (brew install ffmpeg). Saved in media/film-<date>.mp4. Nothing is saved in the app.
"""
import argparse, asyncio, base64, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manual_tour import page_size, launch_opts, pick_url, M as MID  # noqa: E402
from demo_tour import Recorder, Demo, PR12, _line71, _scroll, _decline  # noqa: E402
from documentary import ensure_toggles, back_to_top, slow_scroll_list, build, _seq  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIAGRAM = os.path.abspath(os.path.join(HERE, "..", "..", "user-manual", "images", "diagram-architecture.png"))

STYLE = """
#__card, #__card *{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;letter-spacing:normal;text-transform:none;box-sizing:border-box}
#__card{position:fixed;inset:0;z-index:100000;background:#0b0f17;color:#eef2f7;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
  display:flex;flex-direction:column;justify-content:center;padding:0 7vw;box-sizing:border-box}
#__card .pw-ey{font-family:ui-monospace,Menlo,monospace !important;font-size:13px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:#e8a93a}
#__card .pw-big{font-weight:800;letter-spacing:-.02em;line-height:1}
#__card .pw-mute{color:#94a4b9}
#__card .pw-src{position:absolute;left:7vw;bottom:4.5vh;font-size:13px;color:#6f7f95}
#__card .pw-in{opacity:0;animation:up .7s cubic-bezier(.2,.7,.2,1) forwards}
@keyframes up{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
#__card .pw-row{display:grid;gap:4vw}
#__card .pw-stat{border-left:3px solid #e8a93a;padding-left:18px}
#__card .pw-bar{width:72px;height:4px;background:#e8a93a;border-radius:2px}
"""


def card_html(kind, diagram_uri=""):
    d = lambda s: f"style='animation-delay:{s}s'"
    if kind == "crisis":
        return f"""
<div class='pw-ey pw-in' {d(0)}>The problem</div>
<div class='pw-row' style='grid-template-columns:1fr 1fr;margin-top:5vh'>
  <div class='pw-stat pw-in' {d(.3)}><div class='pw-big' style='font-size:84px'>7.3 trillion</div>
    <div style='font-size:22px;margin-top:14px'>tokens a week used by AI agents on OpenRouter,<br>about five times what people use <span class='pw-mute'>(Aug 2026)</span></div></div>
  <div class='pw-stat pw-in' {d(2.2)}><div class='pw-big' style='font-size:84px'>200–400</div>
    <div style='font-size:22px;margin-top:14px'>lines: past this, human reviewers<br>stop finding defects <span class='pw-mute'>(Cisco study)</span></div></div>
</div>
<div class='pw-src'>Sources: OpenRouter data via a16z, reported Oct 2026 · SmartBear study of 2,500 reviews at Cisco</div>"""
    if kind == "reviewers":
        return f"""
<div class='pw-ey pw-in' {d(0)}>And first-generation AI reviewers do not earn trust</div>
<div class='pw-row' style='grid-template-columns:1fr 1fr 1fr;margin-top:5vh'>
  <div class='pw-stat pw-in' {d(.3)}><div class='pw-big' style='font-size:64px'>45.2%</div>
    <div style='font-size:19px;margin-top:12px'>merge rate when only an AI review agent reviewed, against <b>68.4%</b> for human review</div></div>
  <div class='pw-stat pw-in' {d(1.6)}><div class='pw-big' style='font-size:64px'>60.2%</div>
    <div style='font-size:19px;margin-top:12px'>of closed AI-only-reviewed PRs got mostly noise: 0–30% useful signal</div></div>
  <div class='pw-stat pw-in' {d(2.9)}><div class='pw-big' style='font-size:64px'>45%</div>
    <div style='font-size:19px;margin-top:12px'>of AI-written code samples failed security tests (OWASP Top 10)</div></div>
</div>
<div class='pw-src'>Sources: Chowdhury et al., MSR 2026, “From Industry Claims to Empirical Reality” · Veracode 2025 GenAI Code Security Report</div>"""
    if kind == "thesis":
        return f"""
<div class='pw-big pw-in' style='animation-delay:0s;font-size:46px;font-weight:700;max-width:1000px;line-height:1.2'>Trust is not given to an AI that sounds confident.<br><span style='color:#e8a93a'>It is earned.</span></div>
<div class='pw-row' style='grid-template-columns:1fr 1fr 1fr;margin-top:6vh;max-width:1100px'>
  <div class='pw-stat pw-in' style='animation-delay:1.2s;font-size:24px'>See the whole system<br><span class='pw-mute' style='font-size:17px'>in one glance</span></div>
  <div class='pw-stat pw-in' style='animation-delay:2.0s;font-size:24px'>Verify every claim<br><span class='pw-mute' style='font-size:17px'>side by side with its proof</span></div>
  <div class='pw-stat pw-in' style='animation-delay:2.8s;font-size:24px'>Control the rules<br><span class='pw-mute' style='font-size:17px'>yourself</span></div>
</div>"""
    if kind == "title":
        return f"""
<div style='display:flex;flex-direction:column;align-items:center;text-align:center;gap:20px'>
  <div class='pw-bar pw-in' {d(0)}></div>
  <div class='pw-big pw-in' style='animation-delay:.2s;font-size:64px'>PR World: Seeing Is Believing</div>
  <div class='pw-in pw-mute' style='animation-delay:.7s;font-size:26px'>Earned Trust in AI Code Review</div>
</div>"""
    if kind == "architecture":
        img = (f"<img src='{diagram_uri}' style='height:78vh;border-radius:12px;background:#fff;padding:10px;box-sizing:border-box'>"
               if diagram_uri else "<div class='pw-mute'>(architecture diagram not found)</div>")
        return f"""
<div style='display:grid;grid-template-columns:auto 1fr;gap:5vw;align-items:center'>
  <div class='pw-in' {d(0)}>{img}</div>
  <div>
    <div class='pw-ey pw-in' {d(.4)}>Built to be checked</div>
    <div class='pw-in' style='animation-delay:.9s;font-size:34px;font-weight:700;margin-top:14px;line-height:1.25'>Two tracks: the code<br>and the requirement</div>
    <div class='pw-in pw-mute' style='animation-delay:1.6s;font-size:22px;margin-top:10px'>Verdict computed by code · 8 locked rules</div>
    <div class='pw-stat pw-in' style='animation-delay:3.0s;margin-top:5vh'>
      <div class='pw-ey' style='color:#94a4b9'>Nordbank benchmark</div>
      <div style='font-size:26px;margin-top:8px'><b>12</b> AI-written pull requests</div>
      <div style='font-size:26px'><b>3 of 3</b> planted defects caught</div>
      <div style='font-size:26px'><b>0</b> PRs approved by the AI: a named person signs</div>
    </div>
  </div>
</div>"""
    if kind == "end":
        return f"""
<div style='display:flex;flex-direction:column;align-items:center;text-align:center;gap:18px'>
  <div class='pw-bar pw-in' {d(0)}></div>
  <div class='pw-big pw-in' style='animation-delay:.2s;font-size:72px'>PR World</div>
  <div class='pw-in pw-mute' style='animation-delay:.6s;font-size:26px'>Seeing Is Believing</div>
  <div class='pw-in' style='animation-delay:1.4s;font-size:30px;font-weight:600;margin-top:3vh'>Don’t just trust AI code review. <span style='color:#e8a93a'>See it.</span></div>
</div>"""
    raise ValueError(kind)


async def show_card(d, kind, diagram_uri=""):
    html = card_html(kind, diagram_uri)
    await d.pg.evaluate("""([css, html]) => {
        let s = document.getElementById('__cardcss'); if (!s) { s = document.createElement('style'); s.id='__cardcss'; document.head.appendChild(s); }
        s.textContent = css;
        let el = document.getElementById('__card'); if (el) el.remove();
        el = document.createElement('div'); el.id = '__card'; el.innerHTML = html; document.body.appendChild(el);
    }""", [STYLE, html])
    await d.pg.wait_for_timeout(120)


async def hide_card(d):
    await d.pg.evaluate("document.getElementById('__card')?.remove()")


def sheet(d, diagram_uri):
    jussi_ready = lambda: d.pg.wait_for_selector("text=Safe version", timeout=15000)
    card = lambda k: (lambda: show_card(d, k, diagram_uri))
    return [
        # Act 1 · the crisis and the thesis
        ("0:00", 8, "Card: 7.3 trillion agent tokens · 200–400 lines", card("crisis"), None),
        ("0:08", 8, "Card: 45.2% vs 68.4% · 60.2% noise · 45% insecure", card("reviewers"), None),
        ("0:16", 4, "Card: trust is earned", card("thesis"), None),
        ("0:20", 4, "Title: PR World, Seeing Is Believing", card("title"), None),
        # Act 2 · the app
        ("0:24", 8, "Pull request list (slow pan)",
         lambda: _seq(hide_card(d), d.hash("#/", 0.6), back_to_top(d)),
         lambda: _seq(slow_scroll_list(d, 4.5), back_to_top(d))),
        ("0:32", 4, "How trust is computed", lambda: d.click("text=How trust is computed", 0.6), None),
        ("0:36", 9, "PR-12 on the 2.5D bank map",
         lambda: _seq(d.esc(), d.hash(PR12, 1.5), ensure_toggles(d, True, False, False), d.pg.wait_for_timeout(1200)), None),
        ("0:45", 8, "Changed and Affected together", lambda: ensure_toggles(d, True, True, False), None),
        ("0:53", 4, "Fade the rest", lambda: ensure_toggles(d, True, False, True), None),
        ("0:57", 5, "What this PR does", lambda: d.click(".side button:has-text('What this PR does')", 0.6), None),
        ("1:02", 4, "Requirement: not checked",
         lambda: _seq(d.esc(), d.click(".side button:has-text('Requirement')", 0.6)), None),
        ("1:06", 4, "Trust details", lambda: _seq(d.esc(), d.click(".side button:has-text('Trust details')", 0.6)), None),
        ("1:10", 4, "Inside the Payments module",
         lambda: _seq(d.esc(), ensure_toggles(d, True, False, False),
                      d.hash("#/pr/PR-12?l=module&f=module%3APayments", 1.5), d.pg.wait_for_timeout(1000)), None),
        ("1:14", 4, "ReleaseAsync: call sequence",
         lambda: _seq(d.hash(f"#/pr/PR-12?l=method&f={MID}", 1.3), d.click("button:has-text('Sequence') >> nth=0", 1.2)), None),
        ("1:18", 4, "Line 71: three blind reviewers and a fix",
         lambda: _seq(d.click("button:has-text('Code') >> nth=0", 0.8), _line71(d)), None),
        ("1:22", 4, "Sign-off: named owners sign",
         lambda: _seq(d.hash(PR12, 1.2), d.click(".side button:has-text('Sign-off')", 0.6)), None),
        ("1:26", 5, "A calm PR: PR-10",
         lambda: _seq(d.esc(), d.hash("#/pr/PR-10?l=world", 1.5), d.pg.wait_for_timeout(1000)), None),
        ("1:31", 4, "Eleven AI model slots",
         lambda: _seq(d.hash("#/", 0.6), d.menu("Plugins and coverage"),
                      _scroll(d, "document.querySelector('.models')?.scrollIntoView({block:'start'})", 0.6)), None),
        ("1:35", 3, "Impact and cost before saving",
         lambda: _seq(_scroll(d, "[...document.querySelectorAll('h4,h3')].find(e=>/Specialist reviewers/.test(e.textContent)&&!e.closest('.models'))?.scrollIntoView({block:'start'})", 0.3),
                      d.click(".pcard .sw >> nth=2", 0.4), d.click("text=Review and save", 0.9)), None),
        ("1:38", 3, "Jussi's safe view",
         lambda: _seq(_decline(d), d.esc(), d.view_as("Jussi"), d.hash(PR12, 1.0), jussi_ready(), d.pg.wait_for_timeout(600)), None),
        ("1:41", 3, "Hash-chained audit log",
         lambda: _seq(d.view_as("Noman"), d.hash("#/", 0.6), d.menu("Admin"),
                      d.click(".admin .seg button:has-text('Audit log')", 0.9)), None),
        # Act 3 · proof and close
        ("1:44", 10, "Architecture, locked rules, benchmark", lambda: _seq(d.esc(), card("architecture")()), None),
        ("1:54", 5, "End card: Don't just trust AI code review. See it.", card("end"), None),
    ]


async def main():
    ap = argparse.ArgumentParser(description="Record the 1:59 PR World film.")
    ap.add_argument("--url")
    ap.add_argument("--size", default="auto")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--browser", default="chrome", choices=["chrome", "chromium", "brave"])
    ap.add_argument("--diagram", default=DEFAULT_DIAGRAM)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for tc, sec, what, *_ in sheet(Demo(None, "", 1, False, 0, 0), ""):
            print(f"{tc}  {sec:>2}s  {what}")
        return
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed: brew install ffmpeg")
    uri = ""
    if os.path.exists(a.diagram):
        uri = "data:image/png;base64," + base64.b64encode(open(a.diagram, "rb").read()).decode()
    else:
        print("Architecture diagram not found at", a.diagram, "(use --diagram path). The card will show without it.")
    base = pick_url(a.url)
    w, h = page_size(a.size)
    async with async_playwright() as p:
        lo, bname = launch_opts(a.browser, a.headless, w, h)
        try:
            b = await p.chromium.launch(**lo)
        except Exception:
            lo.pop("channel", None); bname = "Chromium"
            b = await p.chromium.launch(**lo)
        ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=a.scale)
        pg = await ctx.new_page()
        await pg.goto(base + "/#/")
        await pg.wait_for_selector("text=Pull requests", timeout=45000)
        d = Demo(pg, base, 1.0, False, w, h)
        try:
            if "Noman" not in (await pg.inner_text(".menuw > button")):
                await d.view_as("Noman")
        except Exception:
            pass
        await pg.wait_for_timeout(800)
        rec = Recorder(pg, w, h, a.scale)
        await rec.start()
        shots_def = sheet(d, uri)
        total = sum(s[1] for s in shots_def)
        print(f"PR World film: {len(shots_def)} shots, {total // 60}:{total % 60:02d}, in {bname}, page {w}x{h}, video {w * a.scale}x{h * a.scale}")
        shots = []
        try:
            for tc, sec, what, setup, motion in shots_def:
                try:
                    await setup()
                except Exception as e:
                    print(f"   {tc} setup not complete: {str(e).splitlines()[0][:100]}")
                await pg.wait_for_timeout(250)
                start = time.time()
                shots.append((start, sec))
                print(f"{tc}  {sec:>2}s  {what}")
                if motion:
                    try:
                        await motion()
                    except Exception:
                        pass
                left = sec + 0.3 - (time.time() - start)
                if left > 0:
                    await pg.wait_for_timeout(int(left * 1000))
        finally:
            try:
                await hide_card(d)
                await _decline(d)
                await d.esc()
            except Exception:
                pass
            try:
                await rec.cdp.send("Page.stopScreencast")
            except Exception:
                pass
            await asyncio.sleep(0.6)
            await b.close()
        if len(rec.frames) < 2:
            sys.exit("No frames were captured.")
        out_dir = os.path.abspath(os.path.join(HERE, "..", "media"))
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, time.strftime("film-%Y%m%d-%H%M.mp4"))
        print("Cutting the shots to the timecodes ...")
        ok, secs = build(rec.frames, shots, out, w, h, a.scale)
        if ok:
            shutil.rmtree(rec.dir, ignore_errors=True)
            print(f"Video saved: {out}  ({secs:.0f} s)")
        else:
            print("ffmpeg could not build the video. Frames are kept in", rec.dir)


if __name__ == "__main__":
    asyncio.run(main())
