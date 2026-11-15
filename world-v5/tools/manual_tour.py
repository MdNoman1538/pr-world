#!/usr/bin/env python3
"""
PR World — manual tour.
Opens the screens from the user manual one after another in a real browser window,
with a caption showing which manual section you are looking at. Nothing is saved:
the settings steps decline and discard every change they make.

Setup (once):
    python3 -m pip install playwright
    python3 -m playwright install chromium

Run (with the app already running, for example ./run_world.sh --view):
    python3 tools/manual_tour.py                  # auto-advance, 6 seconds a step
    python3 tools/manual_tour.py --wait 9         # slower
    python3 tools/manual_tour.py --step           # press Enter in the terminal for each step
    python3 tools/manual_tour.py --from 20        # start at step 20
    python3 tools/manual_tour.py --url http://127.0.0.1:8792
    python3 tools/manual_tour.py --browser chromium   # Playwright's own Chromium instead of Brave
    python3 tools/manual_tour.py --record         # also saves the tour as a video in media/ (mp4 if ffmpeg is installed)
"""
import argparse, asyncio, os, shutil, subprocess, sys, time, urllib.request
from playwright.async_api import async_playwright

M = "M%3ABank.Modules.Payments.Application.PaymentReviewService.ReleaseAsync(System.Guid%2CSystem.Threading.CancellationToken)"
T = "T%3ABank.Modules.Payments.Application.PaymentReviewService"

CAPTION_JS = """([sec, title, n, total]) => {
  let el = document.getElementById('__tour');
  if (!el) { el = document.createElement('div'); el.id = '__tour'; document.body.appendChild(el); }
  el.style.cssText = 'position:fixed;left:16px;bottom:56px;z-index:99999;max-width:560px;background:rgba(10,16,26,.92);' +
    'color:#eef2f7;border:1px solid #e8a93a;border-radius:10px;padding:10px 14px;font:14px/1.4 system-ui,sans-serif;' +
    'box-shadow:0 8px 30px rgba(0,0,0,.5);pointer-events:none';
  el.innerHTML = '<div style="font:11px ui-monospace,monospace;color:#e8a93a;letter-spacing:.06em">MANUAL ' + sec +
    ' &middot; STEP ' + n + ' OF ' + total + '</div><div style="margin-top:3px;font-weight:600">' + title + '</div>';
}"""


class Tour:
    def __init__(self, pg, base):
        self.pg, self.base = pg, base.rstrip("/")

    async def go(self, h, sel=".side", wait=3500):
        await self.pg.goto("about:blank")
        await self.pg.goto(self.base + "/" + h)
        await self.pg.wait_for_selector(sel, timeout=45000)
        await self.pg.wait_for_timeout(wait)

    async def click(self, sel, wait=900):
        await self.pg.click(sel)
        await self.pg.wait_for_timeout(wait)

    async def esc(self):
        await self.pg.keyboard.press("Escape")
        await self.pg.wait_for_timeout(300)

    async def menu(self, item):
        await self.click(".menuw > button", 400)
        await self.click(f".menu >> text={item}", 1200)

    async def plugins(self):
        await self.go("#/", "text=Pull requests", 2000)
        await self.menu("Plugins and coverage")
        await self.pg.wait_for_selector(".models")

    async def view_as(self, who):
        await self.click(".menuw > button", 400)
        await self.click(f".menu a.person:has-text('{who}'), .menu button:has-text('{who}')", 2500)


def steps(t: Tour):
    pr12 = "#/pr/PR-12?l=world"
    return [
        # (manual section, caption, action)
        ("2.2", "Choose who you are: the Viewing as menu",
         lambda: _seq(t.go(pr12), t.click(".menuw > button", 600))),
        ("2.3", "The pull request list: verdict, trust and top findings for every PR",
         lambda: _seq(t.esc(), t.go("#/", "text=Pull requests", 2000))),
        ("7", "How trust is computed",
         lambda: t.click("text=How trust is computed", 900)),
        ("3", "PR-12 on the world map: Payments changed, arcs show where the change reaches",
         lambda: _seq(t.esc(), t.go(pr12, wait=4500))),
        ("3.2", "One click on Affected: every module the change reaches turns amber",
         lambda: _seq(t.click("button.t-chg", 300), t.click("button.t-aff", 2500))),
        ("3.2", "Changed and Affected together",
         lambda: t.click("button.t-chg", 2500)),
        ("3.3", "Lenses: the APIs lens lists new endpoints and their policy",
         lambda: _seq(t.click("button.t-aff", 600), t.click("button:has-text('APIs')", 2000))),
        ("3.4", "Fade the rest: only the change stays on screen",
         lambda: _seq(t.click("button:has-text('Risk')", 600), t.click("button:has-text('Fade the rest')", 2500))),
        ("4.1", "What this PR does, and its business impact",
         lambda: _seq(t.click("button:has-text('Fade the rest')", 800), t.click(".side button:has-text('What this PR does')", 900))),
        ("4.2", "An open finding: file and line, verified evidence, proposed fix",
         lambda: _seq(t.esc(), t.click(".fb .fbh >> nth=1", 900))),
        ("4.3", "Trust details: 7 of 23 verified, trust Low, and what holds it back",
         lambda: t.click(".side button:has-text('Trust details')", 900)),
        ("4.4", "The requirement next to the change",
         lambda: _seq(t.esc(), t.click(".side button:has-text('Requirement')", 900))),
        ("5.1", "Inside the Payments module: layers, changed classes, path of the change",
         lambda: _seq(t.esc(), t.go("#/pr/PR-12?l=module&f=module%3APayments", wait=4500))),
        ("5.2", "An affected module: Ledger, every reached part verified",
         lambda: t.go("#/pr/PR-12?l=module&f=module%3ALedger", wait=4500)),
        ("5.3", "Class view: PaymentReviewService, Structure",
         lambda: t.go(f"#/pr/PR-12?l=type&f={T}")),
        ("5.3", "Class view: Tests",
         lambda: t.click("button:has-text('Tests') >> nth=0", 1500)),
        ("5.3", "Class view: Code",
         lambda: t.click("button:has-text('Code') >> nth=0", 1500)),
        ("5.4", "Method view: ReleaseAsync as a flow",
         lambda: t.go(f"#/pr/PR-12?l=method&f={M}")),
        ("5.4", "Method view: who it calls, in order",
         lambda: t.click("button:has-text('Sequence') >> nth=0", 1800)),
        ("5.4", "Method view: every value, where it is written and read",
         lambda: t.click("button:has-text('Data flow') >> nth=0", 1800)),
        ("5.5", "The exact line: line 71, flagged by three reviewers on their own",
         lambda: _seq(t.click("button:has-text('Code') >> nth=0", 1500), _scroll_to_line(t))),
        ("6.1", "Jump to anything",
         lambda: _seq(t.click("button.search", 400), t.pg.keyboard.type("Release"), t.pg.wait_for_timeout(900))),
        ("6.2", "Guided tour through the change",
         lambda: _seq(t.esc(), t.go(pr12, wait=4000), t.click("button:has-text('Guided tour')", 2500))),
        ("6.3", "How to move around: the help card",
         lambda: t.click("button[aria-label=Help]", 900)),
        ("8.1", "Sign-off: a named person signs each module part; the AI never approves",
         lambda: _seq(t.esc(), t.go(pr12, wait=4000), t.click(".side button:has-text('Sign-off')", 900))),
        ("8.3", "A calm PR: PR-10, the overview is enough",
         lambda: _seq(t.esc(), t.go("#/pr/PR-10?l=world", wait=4500))),
        ("9", "Your view: personal settings",
         lambda: _seq(t.go("#/", "text=Pull requests", 2000), t.menu("Settings (your view)"))),
        ("10.1", "Start from a preset: the set-up wizard",
         lambda: _seq(t.esc(), t.plugins(), t.click("summary:has-text('Set-up wizard')", 800))),
        ("10.3", "AI models: a model for each place",
         lambda: _seq(t.click("summary:has-text('Set-up wizard')", 300),
                      t.pg.locator(".models").scroll_into_view_if_needed(), t.pg.wait_for_timeout(800))),
        ("10.3", "AI models: one model for everything (not saved)",
         lambda: t.click("text=One model for everything", 1200)),
        ("10.2", "Capabilities you can add or remove",
         lambda: _seq(t.plugins(), _scroll_cards(t))),
        ("10.4", "Nothing changes until you review it",
         lambda: t.click(".pcard .sw >> nth=2", 1200)),
        ("10.4", "See the impact before you accept (this tour declines)",
         lambda: t.click("text=Review and save", 1500)),
        ("10.4", "Declined and discarded: nothing was saved",
         lambda: _seq(t.click(".confirm button:has-text('Decline')", 600), _discard(t))),
        ("11.3", "Viewed as Jussi (Lending lead): the safe version of PR-12",
         lambda: _seq(t.esc(), t.go(pr12, wait=3000), t.view_as("Jussi"), t.go(pr12, wait=4000))),
        ("11.3", "The PR list as Jussi",
         lambda: t.go("#/", "text=Pull requests", 2500)),
        ("11.3", "Viewed as Eero (Auditor): reads everything, signs nothing",
         lambda: _seq(t.view_as("Eero"), t.go(pr12, wait=4000))),
        ("11.4", "Inbox",
         lambda: _seq(t.view_as("Noman"), t.go("#/", "text=Pull requests", 2000), t.menu("Inbox"))),
        ("11.4", "Access requests",
         lambda: _seq(t.esc(), t.menu("Access requests"))),
        ("11.5", "Admin: People",
         lambda: _seq(t.esc(), t.menu("Admin"))),
        ("11.5", "Admin: Roles", lambda: t.click(".admin .seg button:has-text('Roles')", 1200)),
        ("11.5", "Admin: Grants", lambda: t.click(".admin .seg button:has-text('Grants')", 1200)),
        ("11.5", "Admin: Owners", lambda: t.click(".admin .seg button:has-text('Owners')", 1200)),
        ("11.5", "Admin: Audit log", lambda: t.click(".admin .seg button:has-text('Audit log')", 1200)),
        ("11.5", "Admin: Team settings", lambda: t.click(".admin .seg button:has-text('Team settings')", 1200)),
        ("End", "End of the tour", lambda: _seq(t.esc(), t.go("#/", "text=Pull requests", 1500))),
    ]


async def _seq(*aws):
    for a in aws:
        await a


async def _discard(t):
    b = t.pg.locator("button:has-text('Discard')")
    if await b.count():
        await b.first.click()
    await t.pg.wait_for_timeout(1200)


async def _scroll_to_line(t):
    try:
        await t.pg.locator("text=payment.FromAccountId,").first.evaluate("e => e.scrollIntoView({block:'center'})")
    except Exception:
        pass
    await t.pg.wait_for_timeout(800)


async def _scroll_cards(t):
    await t.pg.evaluate("[...document.querySelectorAll('h4,h3')].find(e=>/Specialist reviewers/.test(e.textContent) && !e.closest('.models'))?.scrollIntoView({block:'start'})")
    await t.pg.wait_for_timeout(800)


BRAVE = ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
         os.path.expanduser("~/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
         "/usr/bin/brave-browser", "/usr/bin/brave"]


def screen_size():
    """The usable desktop size in points (macOS), else a laptop-sized default."""
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["osascript", "-e", 'tell application "Finder" to get bounds of window of desktop'],
                               capture_output=True, text=True, timeout=5)
            x1, y1, x2, y2 = [int(v) for v in r.stdout.strip().split(", ")]
            return x2 - x1, y2 - y1
        except Exception:
            pass
    return 1470, 956


def page_size(arg):
    if arg != "auto":
        w, h = arg.lower().split("x")
        return int(w), int(h)
    sw, sh = screen_size()
    # leave room for the menu bar, the browser's tab and address bars and its "controlled by" notice
    return max(1100, min(sw - 16, 1600)), max(640, min(sh - 190, 1000))


def launch_opts(name, headless, w, h):
    """Google Chrome (default), Brave, or Playwright's Chromium, in a window that fits the page."""
    o = {"headless": headless, "args": ["--window-position=0,0", f"--window-size={w},{h + 150}",
                                        "--disable-features=Translate", "--no-first-run", "--no-default-browser-check"]}
    if name == "brave":
        path = next((x for x in BRAVE if os.path.exists(x)), None)
        if path:
            o["executable_path"] = path
            return o, "Brave"
        sys.exit("Brave was not found in /Applications. Use --browser chrome or --browser chromium.")
    if name == "chrome":
        o["channel"] = "chrome"
        return o, "Google Chrome"
    return o, "Chromium"


def pick_url(given):
    for u in ([given] if given else ["http://127.0.0.1:8795", "http://127.0.0.1:8792"]):
        try:
            urllib.request.urlopen(u + "/", timeout=3)
            return u
        except Exception:
            continue
    sys.exit("The app is not answering. Start it first:  ./run_world.sh --view")


async def main():
    ap = argparse.ArgumentParser(description="Walk through the screens of the PR World user manual.")
    ap.add_argument("--url", help="app address (default: try 8795, then 8792)")
    ap.add_argument("--wait", type=float, default=6, help="seconds per step when auto-advancing")
    ap.add_argument("--step", action="store_true", help="press Enter in the terminal to go to the next step")
    ap.add_argument("--from", dest="start", type=int, default=1, help="start at this step number")
    ap.add_argument("--headless", action="store_true", help="no window (for testing the script)")
    ap.add_argument("--record", action="store_true", help="save a video of the tour in media/")
    ap.add_argument("--browser", default="chrome", choices=["chrome", "chromium", "brave"],
                    help="which browser to drive (default: Google Chrome; chromium = Playwright's own)")
    ap.add_argument("--size", default="auto",
                    help="page size WIDTHxHEIGHT, e.g. 1280x760 (default: fit your screen so the map and panel are both in view)")
    a = ap.parse_args()
    base = pick_url(a.url)
    async with async_playwright() as p:
        w, h = page_size(a.size)
        lo, bname = launch_opts(a.browser, a.headless, w, h)
        try:
            b = await p.chromium.launch(**lo)
        except Exception as e:
            if a.browser == "chrome":
                print("Google Chrome could not be started (", str(e).splitlines()[0][:80], "); using Playwright's Chromium.")
                lo.pop("channel", None); bname = "Chromium"
                b = await p.chromium.launch(**lo)
            else:
                raise
        rec_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "media", "tour-raw")
        opts = {"viewport": {"width": w, "height": h}}
        if a.record:
            os.makedirs(rec_dir, exist_ok=True)
            opts.update(record_video_dir=rec_dir, record_video_size={"width": w // 2 * 2, "height": h // 2 * 2})
        ctx = await b.new_context(**opts)
        pg = await ctx.new_page()
        t = Tour(pg, base)
        todo = steps(t)
        print(f"PR World manual tour: {len(todo)} steps on {base}, in {bname}, page {w}x{h}" + (f", video {w // 2 * 2}x{h // 2 * 2}" if a.record else ""))
        try:
            await run_steps(a, pg, todo)
        except Exception as e:
            print("The browser window closed or stopped answering:", str(e).splitlines()[0][:120])
        await finish(a, b, ctx, pg, rec_dir)


async def run_steps(a, pg, todo):
        for i, (sec, title, act) in enumerate(todo, 1):
            if i < a.start:
                continue
            try:
                await act()
            except Exception as e:
                print(f"  step {i} could not run fully ({str(e).splitlines()[0][:120]}); going on")
            try:
                await pg.evaluate(CAPTION_JS, [sec, title, i, len(todo)])
            except Exception:
                pass
            print(f"{i:2d}/{len(todo)}  [{sec}] {title}")
            if a.step:
                await asyncio.get_event_loop().run_in_executor(None, input, "      Enter for the next step ")
            else:
                await pg.wait_for_timeout(int(a.wait * 1000))


async def finish(a, b, ctx, pg, rec_dir):
        if a.record:
            video = pg.video
            try:
                await ctx.close()                   # the video file is finished when the page closes
            except Exception:
                pass
            try:
                src = await video.path()
            except Exception:
                print("No video was written."); await b.close(); return
            stamp = time.strftime("%Y%m%d-%H%M")
            out_dir = os.path.abspath(os.path.join(rec_dir, ".."))
            webm = os.path.join(out_dir, f"manual-tour-{stamp}.webm")
            shutil.move(src, webm)
            if shutil.which("ffmpeg"):
                mp4 = webm[:-5] + ".mp4"
                r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", webm, "-c:v", "libx264", "-preset", "veryfast",
                                    "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", mp4])
                if r.returncode == 0:
                    os.remove(webm)
                print("Video saved:", mp4 if r.returncode == 0 else webm)
            else:
                print("Video saved:", webm, "(install ffmpeg for an mp4: brew install ffmpeg)")
        elif not a.headless and not a.step:
            print("Tour finished. Close the browser window to end.")
            try:
                await pg.wait_for_event("close", timeout=0)
            except Exception:
                pass
        try:
            await b.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
