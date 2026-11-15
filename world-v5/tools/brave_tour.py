#!/usr/bin/env python3
"""
PR World — manual tour in the Brave window you already have open (macOS).

It drives the active tab of your front Brave window (the PR World app) step by step,
following the user manual, with a caption for each step. Nothing is saved: the
settings steps decline and discard every change.

One-time setup in Brave:  View > Developer > Allow JavaScript from Apple Events  (tick it)
For --record, the first run asks to let Terminal record the screen:
  System Settings > Privacy & Security > Screen & System Audio Recording > Terminal (on), then run again.

Run from world-v5, with PR World open in the front Brave window:
    python3 tools/brave_tour.py                    # 6 seconds a step
    python3 tools/brave_tour.py --wait 8 --record  # record the Brave window to media/*.mov (and .mp4 with ffmpeg)
    python3 tools/brave_tour.py --step             # press Enter for each step
    python3 tools/brave_tour.py --from 13
"""
import argparse, json, os, shutil, signal, subprocess, sys, time

MID = "M%3ABank.Modules.Payments.Application.PaymentReviewService.ReleaseAsync(System.Guid%2CSystem.Threading.CancellationToken)"
TID = "T%3ABank.Modules.Payments.Application.PaymentReviewService"

# Small helpers that run inside the page. Each step sends this, then its own lines.
HELPERS = r"""
window.__t = window.__t || {};
__t.find = (sel, text, nth) => { const all=[...document.querySelectorAll(sel)].filter(e => !text || (e.innerText||e.textContent||'').trim().includes(text));
  return all[nth||0] || null; };
__t.click = (sel, text, nth) => { const e=__t.find(sel,text,nth); if(!e) return 'missing '+sel+' '+(text||''); e.scrollIntoView({block:'nearest'}); e.click(); return 'ok'; };
__t.esc = () => { const x=document.querySelector('.modal .x'); if(x){x.click();} const m=document.querySelector('.menu'); if(m && m.offsetParent){ const b=document.querySelector('.menuw > button'); if(b) b.click(); }
  for (const t of [document.activeElement, document, window]) { try { t.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true})); } catch(e){} } return 'ok'; };
__t.type = (sel, value) => { const e=document.querySelector(sel); if(!e) return 'missing '+sel; e.focus();
  const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; set.call(e,value); e.dispatchEvent(new Event('input',{bubbles:true})); return 'ok'; };
__t.caption = (sec, title, n, total) => { let el=document.getElementById('__tour'); if(!el){el=document.createElement('div'); el.id='__tour'; document.body.appendChild(el);}
  el.style.cssText='position:fixed;left:16px;bottom:56px;z-index:99999;max-width:560px;background:rgba(10,16,26,.92);color:#eef2f7;border:1px solid #e8a93a;border-radius:10px;padding:10px 14px;font:14px/1.4 system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.5);pointer-events:none';
  el.innerHTML='<div style="font:11px ui-monospace,monospace;color:#e8a93a;letter-spacing:.06em">MANUAL '+sec+' &middot; STEP '+n+' OF '+total+'</div><div style="margin-top:3px;font-weight:600">'+title+'</div>'; return 'ok'; };
'ready';
"""


def js(s):
    return json.dumps(s)


class Brave:
    """Runs JavaScript in the active tab of the front Brave window through AppleScript."""
    APP = "Brave Browser"

    def run(self, code):
        script = ['-e', 'on run argv', '-e',
                  f'tell application "{self.APP}" to execute active tab of front window javascript (item 1 of argv)',
                  '-e', 'end run']
        r = subprocess.run(["osascript", *script, HELPERS + "\n" + code], capture_output=True, text=True)
        if r.returncode != 0:
            err = r.stderr.strip()
            if "Apple Events" in err or "JavaScript" in err or "-1743" in err or "not allowed" in err.lower():
                sys.exit("Brave refused the script. In Brave: View > Developer > Allow JavaScript from Apple Events, then run again.\n" + err)
            raise RuntimeError(err)
        return r.stdout.strip()

    def url(self):
        r = subprocess.run(["osascript", "-e", f'tell application "{self.APP}" to get URL of active tab of front window'],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("Could not reach Brave. Open PR World in Brave first, and keep that window in front.\n" + r.stderr.strip())
        return r.stdout.strip()

    def bounds(self):
        r = subprocess.run(["osascript", "-e", f'tell application "{self.APP}" to get bounds of front window'],
                           capture_output=True, text=True)
        x1, y1, x2, y2 = [int(v) for v in r.stdout.strip().split(", ")]
        return x1, y1, x2 - x1, y2 - y1

    def front(self):
        subprocess.run(["osascript", "-e", f'tell application "{self.APP}" to activate'], capture_output=True)


class Tour:
    def __init__(self, page, base):
        self.p, self.base = page, base

    def go(self, h, wait=4.0):
        self.p.run(f"location.href = {js(self.base + '/' + h)}; 'ok';")
        time.sleep(wait)

    def reload(self, h, wait=5.0):
        self.p.run(f"location.href = {js(self.base + '/' + h)}; location.reload(); 'ok';")
        time.sleep(wait)

    def click(self, sel, text=None, nth=0, wait=1.0):
        out = self.p.run(f"__t.click({js(sel)}, {js(text)}, {nth});")
        time.sleep(wait)
        return out

    def esc(self, wait=0.4):
        self.p.run("__t.esc();")
        time.sleep(wait)

    def menu(self, item):
        self.esc(0.3)
        self.click(".menuw > button", wait=0.5)
        return self.click(".menu button, .menu a", item, wait=1.2)

    def view_as(self, who):
        self.esc(0.3)
        self.click(".menuw > button", wait=0.5)
        return self.click(".menu a.person, .menu button", who, wait=2.5)

    def scroll(self, code, wait=0.8):
        self.p.run(code + "; 'ok';")
        time.sleep(wait)


def steps(t):
    pr12 = "#/pr/PR-12?l=world"
    S = []
    add = lambda sec, title, *acts: S.append((sec, title, acts))
    add("2.2", "Choose who you are: the Viewing as menu", lambda: t.reload(pr12), lambda: t.click(".menuw > button", wait=0.6))
    add("2.3", "The pull request list: verdict, trust and top findings for every PR", t.esc, lambda: t.go("#/", 2.5))
    add("7", "How trust is computed", lambda: t.click("button", "How trust is computed"))
    add("3", "PR-12 on the world map: Payments changed, arcs show where the change reaches", t.esc, lambda: t.go(pr12, 4.5))
    add("3.2", "One click on Affected: every module the change reaches turns amber",
        lambda: t.click("button.t-chg", wait=0.3), lambda: t.click("button.t-aff", wait=2.5))
    add("3.2", "Changed and Affected together", lambda: t.click("button.t-chg", wait=2.5))
    add("3.3", "Lenses: the APIs lens lists new endpoints and their policy",
        lambda: t.click("button.t-aff", wait=0.6), lambda: t.click("button", "APIs", wait=2))
    add("3.4", "Fade the rest: only the change stays on screen",
        lambda: t.click("button", "Risk", wait=0.6), lambda: t.click("button", "Fade the rest", wait=2.5))
    add("4.1", "What this PR does, and its business impact",
        lambda: t.click("button", "Fade the rest", wait=0.8), lambda: t.click(".side button", "What this PR does"))
    add("4.2", "An open finding: file and line, verified evidence, proposed fix", t.esc, lambda: t.click(".fb .fbh", nth=1))
    add("4.3", "Trust details: 7 of 23 verified, trust Low, and what holds it back", lambda: t.click(".side button", "Trust details"))
    add("4.4", "The requirement next to the change", t.esc, lambda: t.click(".side button", "Requirement"))
    add("5.1", "Inside the Payments module: layers, changed classes, path of the change",
        t.esc, lambda: t.go("#/pr/PR-12?l=module&f=module%3APayments", 4.5))
    add("5.2", "An affected module: Ledger, every reached part verified", lambda: t.go("#/pr/PR-12?l=module&f=module%3ALedger", 4.5))
    add("5.3", "Class view: PaymentReviewService, Structure", lambda: t.go(f"#/pr/PR-12?l=type&f={TID}", 4))
    add("5.3", "Class view: Tests", lambda: t.click("button", "Tests", wait=1.5))
    add("5.3", "Class view: Code", lambda: t.click("button", "Code", wait=1.5))
    add("5.4", "Method view: ReleaseAsync as a flow", lambda: t.go(f"#/pr/PR-12?l=method&f={MID}", 4))
    add("5.4", "Method view: who it calls, in order", lambda: t.click("button", "Sequence", wait=1.8))
    add("5.4", "Method view: every value, where it is written and read", lambda: t.click("button", "Data flow", wait=1.8))
    add("5.5", "The exact line: line 71, flagged by three reviewers on their own",
        lambda: t.click("button", "Code", wait=1.5),
        lambda: t.scroll("const e=[...document.querySelectorAll('*')].find(x=>x.children.length===0&&/payment\\.FromAccountId,/.test(x.textContent||'')); if(e) e.scrollIntoView({block:'center'})"))
    add("6.1", "Jump to anything", lambda: t.click("button.search", wait=0.5),
        lambda: t.p.run("__t.type('[cmdk-input], .palette input', 'Release');"), lambda: time.sleep(0.9))
    add("6.2", "Guided tour through the change", t.esc, lambda: t.go(pr12, 4), lambda: t.click("button", "Guided tour", wait=2.5))
    add("6.3", "How to move around: the help card", lambda: t.click("button[aria-label=Help]"))
    add("8.1", "Sign-off: a named person signs each module part; the AI never approves",
        t.esc, lambda: t.reload(pr12), lambda: t.click(".side button", "Sign-off"))
    add("8.3", "A calm PR: PR-10, the overview is enough", t.esc, lambda: t.go("#/pr/PR-10?l=world", 4.5))
    add("9", "Your view: personal settings", lambda: t.go("#/", 2), lambda: t.menu("Settings (your view)"))
    add("10.1", "Start from a preset: the set-up wizard",
        t.esc, lambda: t.menu("Plugins and coverage"), lambda: t.click("summary", "Set-up wizard", wait=0.8))
    add("10.3", "AI models: a model for each place",
        lambda: t.click("summary", "Set-up wizard", wait=0.3), lambda: t.scroll("document.querySelector('.models')?.scrollIntoView({block:'start'})"))
    add("10.3", "AI models: one model for everything (not saved)", lambda: t.click("button", "One model for everything", wait=1.2))
    add("10.2", "Capabilities you can add or remove",
        lambda: t.click("button", "Discard", wait=0.8),
        lambda: t.scroll("[...document.querySelectorAll('h4,h3')].find(e=>/Specialist reviewers/.test(e.textContent)&&!e.closest('.models'))?.scrollIntoView({block:'start'})"))
    add("10.4", "Nothing changes until you review it", lambda: t.click(".pcard .sw", nth=2, wait=1.2))
    add("10.4", "See the impact before you accept (this tour declines)", lambda: t.click("button", "Review and save", wait=1.5))
    add("10.4", "Declined and discarded: nothing was saved",
        lambda: t.click(".confirm button", "Decline", wait=0.6), lambda: t.click("button", "Discard", wait=1.2))
    add("11.3", "Viewed as Jussi (Lending lead): the safe version of PR-12",
        t.esc, lambda: t.go(pr12, 3), lambda: t.view_as("Jussi"), lambda: t.reload(pr12))
    add("11.3", "The PR list as Jussi", lambda: t.go("#/", 2.5))
    add("11.3", "Viewed as Eero (Auditor): reads everything, signs nothing", lambda: t.view_as("Eero"), lambda: t.reload(pr12))
    add("11.4", "Inbox", lambda: t.view_as("Noman"), lambda: t.go("#/", 2), lambda: t.menu("Inbox"))
    add("11.4", "Access requests", t.esc, lambda: t.menu("Access requests"))
    add("11.5", "Admin: People", t.esc, lambda: t.menu("Admin"))
    for tab in ("Roles", "Grants", "Owners", "Audit log", "Team settings"):
        add("11.5", f"Admin: {tab}", (lambda tab=tab: t.click(".admin .seg button", tab, wait=1.2)))
    add("End", "End of the tour", t.esc, lambda: t.go("#/", 1.5))
    return S


def main():
    ap = argparse.ArgumentParser(description="Walk through the PR World user manual in your open Brave window.")
    ap.add_argument("--wait", type=float, default=6, help="seconds per step")
    ap.add_argument("--step", action="store_true", help="press Enter in the terminal for each step")
    ap.add_argument("--from", dest="start", type=int, default=1, help="start at this step")
    ap.add_argument("--record", action="store_true", help="record the Brave window to media/ with the Mac's screen recorder")
    a = ap.parse_args()
    if sys.platform != "darwin":
        sys.exit("This script drives Brave on macOS. Elsewhere use tools/manual_tour.py.")

    page = Brave()
    url = page.url()
    if "127.0.0.1" not in url and "localhost" not in url:
        sys.exit(f"The front Brave tab is {url}. Switch to the PR World tab (http://127.0.0.1:8795 or :8792) and run again.")
    base = url.split("#")[0].rstrip("/")
    page.front()
    print(page.run("'connected';"), "to", base)
    t = Tour(page, base)
    todo = steps(t)

    rec, mov = None, None
    if a.record:
        here = os.path.dirname(os.path.abspath(__file__))
        out = os.path.abspath(os.path.join(here, "..", "media"))
        os.makedirs(out, exist_ok=True)
        mov = os.path.join(out, time.strftime("manual-tour-%Y%m%d-%H%M.mov"))
        x, y, w, h = page.bounds()
        rec = subprocess.Popen(["screencapture", "-v", "-x", f"-R{x},{y},{w},{h}", mov])
        time.sleep(1.5)
        print(f"Recording the Brave window ({w}x{h}) to {mov}")

    try:
        for i, (sec, title, acts) in enumerate(todo, 1):
            if i < a.start:
                continue
            for act in acts:
                try:
                    r = act()
                    if isinstance(r, str) and r.startswith("missing"):
                        print(f"   (step {i}: {r})")
                except Exception as e:
                    print(f"   (step {i} could not run fully: {str(e).splitlines()[0][:120]})")
            try:
                page.run(f"__t.caption({js(sec)}, {js(title)}, {i}, {len(todo)});")
            except Exception:
                pass
            print(f"{i:2d}/{len(todo)}  [{sec}] {title}")
            if a.step:
                input("      Enter for the next step ")
            else:
                time.sleep(a.wait)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            page.run("document.getElementById('__tour')?.remove(); 'ok';")
        except Exception:
            pass
        if rec:
            rec.send_signal(signal.SIGINT)
            try:
                rec.wait(timeout=30)
            except subprocess.TimeoutExpired:
                rec.terminate()
            time.sleep(1)
            if os.path.exists(mov) and shutil.which("ffmpeg"):
                mp4 = mov[:-4] + ".mp4"
                r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mov, "-c:v", "libx264", "-preset", "veryfast",
                                    "-crf", "20", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", mp4])
                print("Video saved:", mp4 if r.returncode == 0 else mov)
            elif os.path.exists(mov):
                print("Video saved:", mov)
            else:
                print("No video was written. Allow Terminal under System Settings > Privacy & Security > Screen Recording, then run again.")


if __name__ == "__main__":
    main()
