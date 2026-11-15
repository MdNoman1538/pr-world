#!/usr/bin/env python3
"""
PR World — 1:28 documentary cut ("Seeing Is Believing"), Retina quality.

Every scene is played in a real browser, recorded once it has fully loaded, then cut to the exact
length in the cut sheet, so each cut lands on its timecode (0:00 title, 0:03 PR list, 0:17 map ...).
No caption boxes: the video is made for your voice-over. Nothing is saved in the app.

Run from world-v5 with the app running (./run_world.sh --view):
    ../ai-reviewer/.venv/bin/python tools/documentary.py
Options: --size WxH (default: fits your screen) · --scale 2 (Retina) · --browser chromium · --list (print the cut sheet)
Needs ffmpeg (brew install ffmpeg). The video is saved in media/.
"""
import argparse, asyncio, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manual_tour import page_size, launch_opts, pick_url, M as MID  # noqa: E402
from demo_tour import Recorder, Demo, PR12, _line71, _scroll, _decline  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

CARD_JS = """([title, sub]) => {
  let el = document.getElementById('__card');
  if (!el) { el = document.createElement('div'); el.id = '__card'; document.body.appendChild(el); }
  el.style.cssText = 'position:fixed;inset:0;z-index:100000;background:#0b111a;display:flex;flex-direction:column;' +
    'align-items:center;justify-content:center;gap:18px;font-family:system-ui,-apple-system,sans-serif;text-align:center';
  el.innerHTML = '<div style="width:72px;height:4px;background:#e8a93a;border-radius:2px"></div>' +
    '<div style="color:#eef2f7;font-size:46px;font-weight:700;letter-spacing:-.5px">' + title + '</div>' +
    '<div style="color:#94a4b9;font-size:22px">' + sub + '</div>';
}"""


async def ensure_toggles(d, changed=True, affected=False, fade=False):
    """Put the map toggles in a known state, whatever an earlier run left behind."""
    pg = d.pg
    async def is_on(sel):
        try:
            return "on" in ((await pg.get_attribute(sel, "class")) or "").split()
        except Exception:
            return False
    if await is_on("button.t-chg") != changed:
        await d.click("button.t-chg", 0.3)
    if await is_on("button.t-aff") != affected:
        await d.click("button.t-aff", 0.3)
    fb = "button:has-text('Fade the rest')"
    if await is_on(fb) != fade:
        await d.click(fb, 0.5)


async def card(d, title, sub):
    await d.pg.evaluate(CARD_JS, [title, sub])
    await d.pg.wait_for_timeout(200)


async def uncard(d):
    await d.pg.evaluate("document.getElementById('__card')?.remove()")


async def slow_scroll_list(d, seconds):
    """A slow pan down the PR rows, then back to the top for the badges."""
    await d.pg.mouse.move(d.w * 0.4, d.h * 0.6)
    steps = int(seconds * 10)
    for i in range(steps):
        await d.pg.mouse.wheel(0, 9)
        await d.pg.wait_for_timeout(100)


async def back_to_top(d):
    await d.pg.evaluate("window.scrollTo({top:0}); document.querySelectorAll('*').forEach(e=>{if(e.scrollTop>0) e.scrollTop=0})")


def cut_sheet(d):
    """(timecode, seconds, what, setup before the cut, motion during the shot)"""
    jussi_ready = lambda: d.pg.wait_for_selector("text=Safe version", timeout=15000)
    return [
        ("0:00", 3, "Title card",
         lambda: card(d, "Seeing Is Believing", "Earned Trust in AI Code"), None),
        ("0:03", 10, "Pull request list (slow pan, then hold on the badges)",
         lambda: _seq(uncard(d), d.hash("#/", 0.6), back_to_top(d)),
         lambda: _seq(slow_scroll_list(d, 5.0), back_to_top(d))),
        ("0:13", 4, "How trust is computed",
         lambda: d.click("text=How trust is computed", 0.6), None),
        ("0:17", 9, "PR-12 on the 2.5D bank map",
         lambda: _seq(d.esc(), d.hash(PR12, 1.5), ensure_toggles(d, True, False, False), d.pg.wait_for_timeout(1200)), None),
        ("0:26", 8, "Changed and Affected together (34 of 40 verified)",
         lambda: ensure_toggles(d, True, True, False), None),
        ("0:34", 4, "Fade the rest",
         lambda: ensure_toggles(d, True, False, True), None),
        ("0:38", 5, "What this PR does, beside the isolated Payments block",
         lambda: d.click(".side button:has-text('What this PR does')", 0.6), None),
        ("0:43", 4, "Requirement: not checked",
         lambda: _seq(d.esc(), d.click(".side button:has-text('Requirement')", 0.6)), None),
        ("0:47", 4, "Trust details: 7 of 23 verified, 13 no evidence",
         lambda: _seq(d.esc(), d.click(".side button:has-text('Trust details')", 0.6)), None),
        ("0:51", 4, "Inside the Payments module",
         lambda: _seq(d.esc(), ensure_toggles(d, True, False, False),
                      d.hash("#/pr/PR-12?l=module&f=module%3APayments", 1.5), d.pg.wait_for_timeout(1000)), None),
        ("0:55", 4, "ReleaseAsync as a flow",
         lambda: d.hash(f"#/pr/PR-12?l=method&f={MID}", 1.5), None),
        ("0:59", 4, "Line 71: three blind reviewers, verified evidence and a fix",
         lambda: _seq(d.click("button:has-text('Code') >> nth=0", 0.8), _line71(d)), None),
        ("1:03", 4, "Sign-off: named owners sign, the AI never approves",
         lambda: _seq(d.hash(PR12, 1.2), d.click(".side button:has-text('Sign-off')", 0.6)), None),
        ("1:07", 5, "A calm PR: PR-10",
         lambda: _seq(d.esc(), d.hash("#/pr/PR-10?l=world", 1.5), d.pg.wait_for_timeout(1000)), None),
        ("1:12", 5, "Eleven AI model slots",
         lambda: _seq(d.hash("#/", 0.6), d.menu("Plugins and coverage"),
                      _scroll(d, "document.querySelector('.models')?.scrollIntoView({block:'start'})", 0.6)), None),
        ("1:17", 4, "Impact and cost before saving",
         lambda: _seq(_scroll(d, "[...document.querySelectorAll('h4,h3')].find(e=>/Specialist reviewers/.test(e.textContent)&&!e.closest('.models'))?.scrollIntoView({block:'start'})", 0.3),
                      d.click(".pcard .sw >> nth=2", 0.4), d.click("text=Review and save", 0.9)), None),
        ("1:21", 2, "Jussi's safe view of PR-12",
         lambda: _seq(_decline(d), d.esc(), d.view_as("Jussi"), d.hash(PR12, 1.0), jussi_ready(), d.pg.wait_for_timeout(600)), None),
        ("1:23", 2, "The hash-chained audit log",
         lambda: _seq(d.view_as("Noman"), d.hash("#/", 0.6), d.menu("Admin"),
                      d.click(".admin .seg button:has-text('Audit log')", 0.9)), None),
        ("1:25", 3, "End card",
         lambda: card(d, "PR World", "Seeing Is Believing"), None),
    ]


async def _seq(*aws):
    for a in aws:
        if a is not None:
            await a


def build(frames, shots, out, w, h, scale):
    """Cut each shot to its exact length from the continuous recording and join them."""
    lst = os.path.join(os.path.dirname(frames[0][0]), "cut.txt")
    total = 0.0
    with open(lst, "w") as f:
        for (s, dur) in shots:
            e = s + dur
            first = max((fr for fr in frames if fr[1] <= s), key=lambda fr: fr[1], default=frames[0])
            inside = [fr for fr in frames if s < fr[1] < e]
            seq = [(first[0], s)] + [(p, ts) for p, ts in inside]
            for i, (p, ts) in enumerate(seq):
                nxt = seq[i + 1][1] if i + 1 < len(seq) else e
                f.write(f"file '{p}'\nduration {max(0.001, nxt - ts):.4f}\n")
            total += dur
        f.write(f"file '{seq[-1][0]}'\n")
    W, H = w * scale // 2 * 2, h * scale // 2 * 2
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-vf", f"scale={W}:{H}:flags=lanczos,fps=30,format=yuv420p",
                        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-movflags", "+faststart",
                        "-t", f"{total:.3f}", out])
    return r.returncode == 0, total


async def main():
    ap = argparse.ArgumentParser(description="Record the 1:28 PR World documentary cut.")
    ap.add_argument("--url")
    ap.add_argument("--size", default="auto")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--browser", default="chrome", choices=["chrome", "chromium", "brave"])
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--list", action="store_true", help="print the cut sheet and stop")
    a = ap.parse_args()
    if not shutil.which("ffmpeg") and not a.list:
        sys.exit("ffmpeg is needed: brew install ffmpeg")
    if a.list:
        for tc, sec, what, *_ in cut_sheet(Demo(None, "", 1, False, 0, 0)):
            print(f"{tc}  {sec:>2}s  {what}")
        return
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
        await pg.wait_for_timeout(1000)
        rec = Recorder(pg, w, h, a.scale)
        await rec.start()
        sheet = cut_sheet(d)
        print(f"PR World documentary: {len(sheet)} shots, 1:28, in {bname}, page {w}x{h}, video {w * a.scale}x{h * a.scale}")
        shots = []
        try:
            for tc, sec, what, setup, motion in sheet:
                try:
                    await setup()
                except Exception as e:
                    print(f"   {tc} setup not complete: {str(e).splitlines()[0][:100]}")
                await pg.wait_for_timeout(350)               # let the last paint land
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
                await _decline(d)
                await d.esc()
                await uncard(d)
            except Exception:
                pass
            try:
                await rec.cdp.send("Page.stopScreencast")
            except Exception:
                pass
            await asyncio.sleep(0.6)
            await b.close()
        frames = rec.frames
        if frames:
            print(f"   ({len(frames)} frames; clock offset {frames[0][1] - shots[0][0]:+.1f} s)")
        if len(frames) < 2 or not shots:
            sys.exit("No frames were captured.")
        # the screencast timestamps and time.time() share the wall clock; align them just in case
        out_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "media"))
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, time.strftime("documentary-%Y%m%d-%H%M.mp4"))
        print("Cutting the shots to the timecodes ...")
        ok, total = build(frames, shots, out, w, h, a.scale)
        if ok:
            shutil.rmtree(rec.dir, ignore_errors=True)
            print(f"Video saved: {out}  ({total:.0f} s)")
        else:
            print("ffmpeg could not build the video. Frames are kept in", rec.dir)


if __name__ == "__main__":
    asyncio.run(main())
