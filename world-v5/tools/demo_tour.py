#!/usr/bin/env python3
"""
PR World — fast demo video ("Seeing is believing"), about 2.5 to 3 minutes.

Follows the 10-beat storyboard: triage list, the world map (with a short navigation move),
blast radius, isolate, honest abstention, the dive to line 71, sign-off vs a calm PR,
customisation, safe access and the audit log. Nothing is saved: the settings step declines.

Run from world-v5 with the app running (./run_world.sh --view):
    ../ai-reviewer/.venv/bin/python tools/demo_tour.py --record          # Retina-quality video in media/
    ../ai-reviewer/.venv/bin/python tools/demo_tour.py --record --pace 0.8   # 20% faster
    ../ai-reviewer/.venv/bin/python tools/demo_tour.py                   # just play it, no video
Options: --size WxH (default: fits your screen, same as manual_tour.py) · --no-captions · --browser chromium
"""
import argparse, asyncio, os, shutil, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manual_tour import page_size, launch_opts, pick_url, M as MID, T as TID  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

PR12 = "#/pr/PR-12?l=world"

CAPTION_JS = """([beat, text]) => {
  let el = document.getElementById('__tour');
  if (!el) { el = document.createElement('div'); el.id = '__tour'; document.body.appendChild(el); }
  el.style.cssText = 'position:fixed;left:16px;bottom:56px;z-index:99999;max-width:620px;background:rgba(10,16,26,.92);' +
    'color:#eef2f7;border:1px solid #e8a93a;border-radius:10px;padding:10px 14px;font:15px/1.4 system-ui,sans-serif;' +
    'box-shadow:0 8px 30px rgba(0,0,0,.5);pointer-events:none;transition:opacity .25s';
  el.innerHTML = '<div style="font:11px ui-monospace,monospace;color:#e8a93a;letter-spacing:.08em;text-transform:uppercase">' + beat +
    '</div><div style="margin-top:3px;font-weight:600">' + text + '</div>';
}"""


class Recorder:
    """Records the page with Chrome's screencast at device pixels (2x on Retina), then encodes an mp4."""

    def __init__(self, page, w, h, scale):
        self.page, self.w, self.h, self.scale = page, w, h, scale
        self.dir = tempfile.mkdtemp(prefix="prw-demo-")
        self.frames, self.cdp = [], None

    async def start(self):
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", lambda e: asyncio.ensure_future(self._frame(e)))
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "everyNthFrame": 1,
                                                     "maxWidth": self.w * self.scale, "maxHeight": self.h * self.scale})

    async def _frame(self, e):
        import base64
        n = len(self.frames)
        path = os.path.join(self.dir, f"f{n:06d}.jpg")
        with open(path, "wb") as f:
            f.write(base64.b64decode(e["data"]))
        self.frames.append((path, e["metadata"].get("timestamp") or time.time()))
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": e["sessionId"]})
        except Exception:
            pass

    async def stop(self, out_mp4):
        try:
            await self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        await asyncio.sleep(0.5)
        if len(self.frames) < 2:
            print("No video frames were captured.")
            return None
        end = time.time()
        lst = os.path.join(self.dir, "frames.txt")
        with open(lst, "w") as f:
            for i, (p, ts) in enumerate(self.frames):
                nxt = self.frames[i + 1][1] if i + 1 < len(self.frames) else max(ts + 0.5, min(end, ts + 2))
                f.write(f"file '{p}'\nduration {max(0.001, nxt - ts):.4f}\n")
            f.write(f"file '{self.frames[-1][0]}'\n")
        if not shutil.which("ffmpeg"):
            print("ffmpeg is needed to build the video: brew install ffmpeg. Frames are kept in", self.dir)
            return None
        W, H = self.w * self.scale // 2 * 2, self.h * self.scale // 2 * 2
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                            "-vf", f"scale={W}:{H}:flags=lanczos,fps=30,format=yuv420p",
                            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-movflags", "+faststart", out_mp4])
        if r.returncode == 0:
            shutil.rmtree(self.dir, ignore_errors=True)
            return out_mp4
        print("ffmpeg could not build the video. Frames are kept in", self.dir)
        return None


class Demo:
    def __init__(self, pg, base, pace, captions, w, h):
        self.pg, self.base, self.pace, self.captions, self.w, self.h = pg, base.rstrip("/"), pace, captions, w, h

    async def hold(self, s):
        await self.pg.wait_for_timeout(int(s * self.pace * 1000))

    async def hash(self, h, settle=1.6):
        """Move inside the app without reloading, so there is no blank flash."""
        await self.pg.evaluate("h => { location.hash = h; }", h.lstrip("/"))
        try:
            await self.pg.wait_for_selector(".side" if "/pr/" in h else "text=Pull requests", timeout=15000)
        except Exception:
            pass
        await self.pg.wait_for_timeout(int(settle * 1000))

    async def click(self, sel, settle=0.7):
        await self.pg.click(sel, timeout=8000)
        await self.pg.wait_for_timeout(int(settle * 1000))

    async def esc(self):
        await self.pg.keyboard.press("Escape")
        await self.pg.wait_for_timeout(250)

    async def caption(self, beat, text):
        if not self.captions:
            return
        await self.pg.evaluate(CAPTION_JS, [beat, text])

    async def menu(self, item):
        await self.click(".menuw > button", 0.35)
        await self.click(f".menu >> text={item}", 0.9)

    async def view_as(self, who):
        await self.click(".menuw > button", 0.35)
        await self.click(f".menu a.person:has-text('{who}'), .menu button:has-text('{who}')", 0.3)
        try:
            await self.pg.wait_for_load_state("networkidle", timeout=10000)
            await self.pg.wait_for_selector(".menuw > button", timeout=15000)
        except Exception:
            pass
        await self.pg.wait_for_timeout(600)

    async def navigate_map(self):
        """A 2-second show of moving around the 2.5D map: pan, zoom in, zoom out."""
        m = self.pg.mouse
        cx, cy = int(self.w * 0.36), int(self.h * 0.55)
        await m.move(cx, cy)
        await m.down()
        for i in range(12):
            await m.move(cx + 9 * i, cy + 3 * i)
            await self.pg.wait_for_timeout(25)
        await m.up()
        for _ in range(5):
            await m.wheel(0, -120)
            await self.pg.wait_for_timeout(70)
        await self.pg.wait_for_timeout(250)
        for _ in range(5):
            await m.wheel(0, 120)
            await self.pg.wait_for_timeout(70)
        await m.move(cx + 99, cy + 33)
        await m.down()
        for i in range(12):
            await m.move(cx + 99 - 9 * i, cy + 33 - 3 * i)
            await self.pg.wait_for_timeout(25)
        await m.up()


async def scenes(d):
    S = [
        # Beat 1 · The triage hook
        ("The triage hook", "Every AI-written PR arrives with a verdict computed by code", lambda: d.hash("#/", 1.2), 4),
        ("The triage hook", "How trust is computed: a rule anyone can read",
         lambda: d.click("text=How trust is computed", 0.8), 4),
        # Beat 2 · Single-glance architecture (+ navigation move)
        ("Seeing is believing", "PR-12 on the whole bank: Payments changed, arcs show where it reaches",
         lambda: _seq(d.esc(), d.hash(PR12, 2.2), d.navigate_map()), 5),
        # Beat 3 · Blast radius and test proof
        ("Blast radius", "One click on Affected: every module the change reaches, with its test proof",
         lambda: _seq(d.click("button.t-chg", 0.2), d.click("button.t-aff", 1.6)), 5),
        ("Blast radius", "Changed and affected together: 34 of 40 affected parts verified",
         lambda: d.click("button.t-chg", 1.4), 6),
        # Beat 4 · Isolate and read side by side
        ("Isolate", "Fade the rest: only the change stays on screen",
         lambda: _seq(d.click("button.t-aff", 0.3), d.click("button:has-text('Fade the rest')", 1.6)), 6),
        ("Isolate", "What this PR does, and what it means for the business",
         lambda: d.click(".side button:has-text('What this PR does')", 0.8), 4),
        # Beat 5 · Honest abstention
        ("Refusing to guess", "Requirement: not checked, shown as a gap, never as a pass",
         lambda: _seq(d.esc(), d.click(".side button:has-text('Requirement')", 0.8)), 4),
        ("Refusing to guess", "Trust details: 7 of 23 verified, 13 with no evidence, trust Low",
         lambda: _seq(d.esc(), d.click(".side button:has-text('Trust details')", 0.8)), 5),
        # Beat 6 · Travel deep without reading diffs
        ("Travel deep", "Inside Payments: layers, changed classes, the path of the change",
         lambda: _seq(d.esc(), d.click("button:has-text('Fade the rest')", 0.2),
                      d.hash("#/pr/PR-12?l=module&f=module%3APayments", 2.2)), 5),
        ("Travel deep", "ReleaseAsync as a flow: read the logic, not the diff",
         lambda: d.hash(f"#/pr/PR-12?l=method&f={MID}", 1.8), 4),
        # Beat 7 · The smoking gun at line 71
        ("The smoking gun", "Line 71: three blind reviewers found the same double debit",
         lambda: _seq(d.click("button:has-text('Code') >> nth=0", 1.0), _line71(d)), 7),
        ("The smoking gun", "Every finding cites its line, verified evidence and a fix",
         lambda: _seq(d.hash(PR12, 1.8), d.click(".fb .fbh >> nth=1", 0.8)), 5),
        # Beat 8 · Human sign-off vs calm approval
        ("A human decides", "Sign-off: a named owner signs each module. The AI never approves",
         lambda: d.click(".side button:has-text('Sign-off')", 0.8), 4),
        ("A human decides", "A calm PR: PR-10, the overview is enough to sign",
         lambda: _seq(d.esc(), d.hash("#/pr/PR-10?l=world", 2.2)), 4),
        # Beat 9 · Use your own thing
        ("You are in control", "Start from a preset for your kind of project",
         lambda: _seq(d.hash("#/", 0.8), d.menu("Plugins and coverage"), d.click("summary:has-text('Set-up wizard')", 0.6)), 4),
        ("You are in control", "Choose the model for each of the 11 places AI is used, your own included",
         lambda: _seq(d.click("summary:has-text('Set-up wizard')", 0.2), _scroll(d, "document.querySelector('.models')?.scrollIntoView({block:'start'})")), 4),
        ("You are in control", "See the cost and impact before you accept",
         lambda: _seq(_scroll(d, "[...document.querySelectorAll('h4,h3')].find(e=>/Specialist reviewers/.test(e.textContent)&&!e.closest('.models'))?.scrollIntoView({block:'start'})", 0.3),
                      d.click(".pcard .sw >> nth=2", 0.5), d.click("text=Review and save", 1.0)), 5),
        # Beat 10 · Safe access and audit
        ("Safe access", "Viewed as Jussi: severity visible, Payments code withheld",
         lambda: _seq(_decline(d), d.esc(), d.view_as("Jussi"), d.hash(PR12, 1.8)), 5),
        ("Every action audited", "The hash-chained audit log records every view, grant and signature",
         lambda: _seq(d.view_as("Noman"), d.hash("#/", 0.8), d.menu("Admin"), d.click(".admin .seg button:has-text('Audit log')", 1.0)), 5),
    ]
    return S


async def _seq(*aws):
    for a in aws:
        await a


async def _scroll(d, code, settle=0.6):
    await d.pg.evaluate(code)
    await d.pg.wait_for_timeout(int(settle * 1000))


async def _line71(d):
    try:
        await d.pg.locator("text=payment.FromAccountId,").first.evaluate("e => e.scrollIntoView({block:'center', behavior:'smooth'})")
    except Exception:
        pass
    await d.pg.wait_for_timeout(700)


async def _decline(d):
    for sel in (".confirm button:has-text('Decline')", "button:has-text('Discard')"):
        b = d.pg.locator(sel)
        if await b.count():
            await b.first.click()
            await d.pg.wait_for_timeout(300)


async def main():
    ap = argparse.ArgumentParser(description="Record the fast PR World demo.")
    ap.add_argument("--url")
    ap.add_argument("--record", action="store_true", help="save a high-quality mp4 in media/")
    ap.add_argument("--pace", type=float, default=1.0, help="multiply every hold (0.8 = faster, 1.2 = slower)")
    ap.add_argument("--size", default="auto", help="page size WIDTHxHEIGHT (default: fits your screen)")
    ap.add_argument("--scale", type=int, default=2, help="pixel density of the video (2 = Retina)")
    ap.add_argument("--no-captions", action="store_true", help="no caption box on screen")
    ap.add_argument("--browser", default="chrome", choices=["chrome", "chromium", "brave"])
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
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
        # start in a known state: Noman, PR list, no toggles left from earlier runs
        d = Demo(pg, base, a.pace, not a.no_captions, w, h)
        try:
            if "Noman" not in (await pg.inner_text(".menuw > button")):
                await d.view_as("Noman")
        except Exception:
            pass
        await pg.wait_for_timeout(1500)
        rec = None
        if a.record:
            rec = Recorder(pg, w, h, a.scale)
            await rec.start()
        todo = await scenes(d)
        print(f"PR World demo: {len(todo)} scenes in {bname}, page {w}x{h}" + (f", video {w * a.scale}x{h * a.scale}" if a.record else ""))
        t0 = time.time()
        try:
            for i, (beat, text, act, hold) in enumerate(todo, 1):
                try:
                    await d.caption(beat, text)
                except Exception:
                    pass
                try:
                    await act()
                except Exception as e:
                    print(f"   scene {i} not complete: {str(e).splitlines()[0][:100]}")
                try:
                    await d.caption(beat, text)      # again, in case the page was reloaded
                except Exception:
                    pass
                print(f"{i:2d}/{len(todo)}  {beat}: {text}")
                await d.hold(hold)
        except Exception as e:
            print("The browser stopped:", str(e).splitlines()[0][:120])
        finally:
            try:
                await _decline(d)
                await d.esc()
                await pg.evaluate("document.getElementById('__tour')?.remove()")
            except Exception:
                pass
            print(f"Played in {time.time() - t0:.0f} s")
            if rec:
                out_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "media"))
                os.makedirs(out_dir, exist_ok=True)
                out = os.path.join(out_dir, time.strftime("demo-%Y%m%d-%H%M.mp4"))
                print("Building the video ...")
                done = await rec.stop(out)
                if done:
                    print("Video saved:", done)
            try:
                await b.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
