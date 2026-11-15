#!/usr/bin/env python3
"""Record a focused, real-browser PR-12 trust walkthrough."""
import argparse, asyncio, os, sys, time
from pathlib import Path

from playwright.async_api import async_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_tour import Demo, Recorder, _seq, _line71, PR12
from manual_tour import page_size, launch_opts, pick_url

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8795")
    ap.add_argument("--out", default="Deliverable/video demo/06-live-app-walkthrough.mp4")
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    base = pick_url(a.url)
    w, h = page_size("1600x810")
    async with async_playwright() as p:
        opts, _ = launch_opts("chrome", a.headless, w, h)
        try:
            browser = await p.chromium.launch(**opts)
        except Exception:
            opts.pop("channel", None)
            browser = await p.chromium.launch(**opts)
        ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        page = await ctx.new_page()
        await page.goto(base + "/#/")
        await page.wait_for_selector("text=Pull requests", timeout=45000)
        demo = Demo(page, base, 1.0, True, w, h)
        try:
            if "Noman" not in await page.inner_text(".menuw > button"):
                await demo.view_as("Noman")
        except Exception:
            pass
        recorder = Recorder(page, w, h, 1)
        await recorder.start()
        scenes = [
            ("A QUESTION OF TRUST", "The verdict and evidence are visible before opening code", lambda: demo.hash("#/", 1), 8),
            ("SEE THE SYSTEM", "PR-12: Payments changed; amber shows the affected path", lambda: demo.hash(PR12, 2), 17),
            ("CHECK THE BLAST RADIUS", "Affected modules carry their own test evidence", lambda: _seq(demo.click("button.t-chg", .3), demo.click("button.t-aff", 1.4)), 12),
            ("FINDING WITH PROOF", "Open the second finding: ReleaseAsync debits the payer again", lambda: _seq(demo.click("button.t-aff", .3), demo.click(".fb .fbh >> nth=1", 1.2)), 18),
            ("TRUST FROM TESTS", "Seven of twenty-three verified; three contradicted; thirteen unproven", lambda: _seq(demo.esc(), demo.click(".side button:has-text('Trust details')", 1)), 15),
            ("REFUSE TO GUESS", "Requirement check did not run; the app says Not checked", lambda: _seq(demo.esc(), demo.click(".side button:has-text('Requirement')", 1)), 13),
            ("HUMAN ACCOUNTABILITY", "The AI blocks; named module owners sign the exact commit", lambda: _seq(demo.esc(), demo.click(".side button:has-text('Sign-off')", 1)), 15),
        ]
        try:
            for beat, caption, action, hold in scenes:
                await demo.caption(beat, caption)
                try:
                    await action()
                except Exception as e:
                    print(f"Scene issue ({beat}): {str(e).splitlines()[0]}")
                await demo.caption(beat, caption)
                await demo.hold(hold)
        finally:
            try:
                await page.evaluate("document.getElementById('__tour')?.remove()")
            except Exception:
                pass
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            print("Saved:", await recorder.stop(os.path.abspath(a.out)))
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
