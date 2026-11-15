"""PR World server: login, per-user data, module access, requests, sign-off, merge policy, settings, audit.

Run:  python -m prw_server --config access.yaml        (see README in this folder)
"""
import json
import os
import secrets
import sys
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional

import requests
import yaml
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import policy as pol
from .access import Data, View
from .auth import OIDC, Throttle, check_password, hash_password
from .store import LEVELS, RANK, Store, iso, until_from_hours

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
PERSONAL_KEYS = ["trust_view", "severity_min", "lenses", "layout", "density", "theme", "language", "start"]


def _rel(base: str, p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def secret_file(path: str, name: str, env: str) -> bytes:
    """A server secret from the environment, else from a local file created once (mode 600). Never printed."""
    v = os.environ.get(env)
    if v:
        return v.encode()
    store = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            store = json.load(fh)
    if name not in store:
        store[name] = secrets.token_hex(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(store, fh)
    return store[name].encode()


class Server:
    def __init__(self, config_path: str):
        self.config_path = os.path.abspath(config_path)
        base = os.path.dirname(self.config_path)
        with open(self.config_path, encoding="utf-8") as fh:
            self.cfg = yaml.safe_load(fh) or {}
        c = self.cfg
        self.data = Data(_rel(base, c.get("data", "../viewer/data")))
        self.dist = _rel(base, c.get("viewer", "../viewer2/dist"))
        self.reviewer_dir = _rel(base, c.get("reviewer", "../../ai-reviewer/backend"))
        self.settings_path = _rel(base, c.get("settings")) if c.get("settings") else None
        self.store = Store(_rel(base, c.get("database", "prw-server.db")))
        secrets_path = _rel(base, c.get("secrets_file", ".prw-secrets.json"))
        self.session_secret = secret_file(secrets_path, "session", "PRW_SESSION_SECRET")
        self.sign_secret = secret_file(secrets_path, "signing", "PRW_SIGNING_SECRET")
        self.default_level = c.get("default_level", "overview")
        if self.default_level not in RANK:
            raise SystemExit("default_level must be one of " + ", ".join(LEVELS))
        self.oidc = OIDC(c["oidc"]) if c.get("oidc") else None
        # sign-in mode: "switch" (this version: no passwords; pick who you are from a list) or "login" (passwords / company sign-in)
        self.mode = c.get("mode", "switch")
        if self.mode not in ("switch", "login"):
            raise SystemExit("mode must be switch or login")
        self.default_user = c.get("default_user") or next(iter(c.get("users") or {}), None)
        self.local_login = bool(c.get("local_login", True)) and self.mode == "login"
        self.throttle = Throttle()
        self._seen: Dict = {}
        self._cache: "OrderedDict" = OrderedDict()
        self._lock = threading.Lock()
        if self.reviewer_dir and self.reviewer_dir not in sys.path:
            sys.path.insert(0, self.reviewer_dir)
        self.team = self.load_team()
        self.seed()

    # ------------------------------------------------------------------ team settings (prworld.yaml)
    def load_team(self):
        try:
            from reviewer.platform_config import load_config
            return load_config(self.settings_path) if self.settings_path and os.path.exists(self.settings_path) else load_config()
        except Exception as e:      # the server still runs; the admin page shows the problem
            self.team_error = str(e)
            return None

    def team_get(self, *keys, default=None):
        return self.team.get(*keys, default=default) if self.team else default

    def hide_names(self):
        a = self.cfg.get("access", {}) or {}
        return (bool(self.team_get("access", "hide_restricted_names", default=False)) or bool(a.get("hide_restricted_names")),
                list(self.team_get("access", "restricted_names", default=[]) or []) + list(a.get("restricted_names") or []))

    def emergency_max(self) -> int:
        return int(self.team_get("access", "emergency_max_hours", default=None) or (self.cfg.get("access") or {}).get("emergency_max_hours", 4))

    # ------------------------------------------------------------------ first start: roles, owners and users from the file
    def seed(self):
        s = self.store
        if not s.q("SELECT 1 FROM roles LIMIT 1"):
            for name, r in (self.cfg.get("roles") or {}).items():
                s.x("INSERT INTO roles(name,description,admin) VALUES(?,?,?)", (name, (r or {}).get("description", ""), int(bool((r or {}).get("admin")))))
                for m, lv in ((r or {}).get("modules") or {}).items():
                    if lv not in RANK:
                        raise SystemExit(f"role {name}: unknown level {lv} (use {', '.join(LEVELS)})")
                    s.x("INSERT INTO role_modules(role,module,level) VALUES(?,?,?)", (name, m, lv))
            for m, users in (self.cfg.get("owners") or {}).items():
                for u in users or []:
                    s.x("INSERT OR IGNORE INTO owners(module,user) VALUES(?,?)", (m, u))
            s.audit("system", "seed", self.config_path, {"roles": list((self.cfg.get("roles") or {}).keys())})
        for uid, u in (self.cfg.get("users") or {}).items():
            if not s.user(uid):
                s.upsert_user(uid, (u or {}).get("name", uid), (u or {}).get("email", ""), "local")
                s.set_roles(uid, (u or {}).get("roles", []), "file")
                s.audit("system", "user_created", uid, {"roles": (u or {}).get("roles", [])})

    # ------------------------------------------------------------------ per-user view
    def view(self, uid: str) -> View:
        mods = self.data.modules()
        lv = self.store.levels_for(uid, mods, self.default_level)
        star = self.default_level
        rows = self.store.q("SELECT rm.level FROM role_modules rm JOIN user_roles ur ON ur.role=rm.role WHERE ur.user=? AND rm.module='*'", (uid,))
        rows += [g for g in self.store.active_grants(uid) if g["module"] == "*"]
        for r in rows:
            if RANK[r["level"]] > RANK[star]:
                star = r["level"]
        hide_all, hidden = self.hide_names()
        return View(self.data, lv, hide_all, hidden, star)

    def cached(self, key, fn):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        v = fn()
        with self._lock:
            self._cache[key] = v
            while len(self._cache) > 48:
                self._cache.popitem(last=False)
        return v

    def log_open(self, uid: str, target: str, detail: Dict):
        k, t = (uid, target), time.time()
        if t - self._seen.get(k, 0) > 300:      # one line per person and file every 5 minutes
            self._seen[k] = t
            self.store.audit(uid, "open", target, detail)

    def pr(self, pr_id: str) -> Optional[Dict]:
        idx = self.data.load("index.json") or {}
        return next((p for p in idx.get("prs", []) if p.get("id") == pr_id), None)

    def notify_owners(self, module: str, text: str, kind: str):
        owners = [o["user"] for o in self.store.owners(module)]
        admins = [r["user"] for r in self.store.q("SELECT DISTINCT ur.user FROM user_roles ur JOIN roles r ON r.name=ur.role WHERE r.admin=1")]
        for u in sorted(set(owners + admins)):
            self.store.notify(u, kind, text)
        hook = os.environ.get("PRW_SLACK_WEBHOOK_URL")
        if hook:
            try:
                requests.post(hook, json={"text": f"PR World: {text}"}, timeout=10)
            except Exception:
                pass
        return owners


S: Optional[Server] = None


# ---------------------------------------------------------------------- helpers
def err(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=code)


def uid_of(req: Request) -> Optional[str]:
    uid = req.session.get("uid")
    if not uid and S.mode == "switch" and S.default_user and S.store.user(S.default_user):
        uid = S.default_user                     # switch mode: no sign-in, you start as the default person
        req.session.update({"uid": uid, "at": time.time()})
        S.store.audit(uid, "session_started", "switch mode")
    if not uid:
        return None
    u = S.store.user(uid)
    if not u or u["disabled"]:
        req.session.clear()
        return None
    if S.mode == "login" and time.time() - req.session.get("at", 0) > float(S.cfg.get("session_hours", 8)) * 3600:
        req.session.clear()
        return None
    return uid


def need_admin(req: Request) -> Optional[str]:
    uid = uid_of(req)
    return uid if uid and S.store.is_admin(uid) else None


async def body(req: Request) -> Dict:
    try:
        return await req.json()
    except Exception:
        return {}


# ---------------------------------------------------------------------- login
LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>PR World · sign in</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/login.css"></head>
<body><main><h1>PR World</h1><p class="sub">Sign in to review pull requests.</p>
{sso}{local}<p id="msg" role="alert"></p></main><script src="/login.js"></script></body></html>"""
LOGIN_CSS = """body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f1418;color:#e6edf3;font:15px system-ui,sans-serif}
main{width:320px;padding:28px;border:1px solid #2a333c;border-radius:12px;background:#151c22}h1{margin:0 0 4px;font-size:22px}
.sub{color:#9aa7b3;margin:0 0 20px}label{display:block;margin:10px 0 4px;color:#9aa7b3;font-size:13px}
input{width:100%;box-sizing:border-box;padding:9px;border-radius:8px;border:1px solid #2a333c;background:#0f1418;color:#e6edf3}
button,a.sso{display:block;width:100%;box-sizing:border-box;margin-top:16px;padding:10px;border:0;border-radius:8px;background:#3b82f6;
color:#fff;font-weight:600;text-align:center;text-decoration:none;cursor:pointer}a.sso{background:#22303c}#msg{color:#f59e0b;min-height:1em}"""
LOGIN_JS = """const f=document.getElementById('f');if(f)f.addEventListener('submit',async(e)=>{e.preventDefault();
const r=await fetch('/auth/local',{method:'POST',headers:{'Content-Type':'application/json','X-PRW':'1'},
body:JSON.stringify({user:f.user.value,password:f.password.value})});const j=await r.json().catch(()=>({}));
if(r.ok)location.href='/';else document.getElementById('msg').textContent=j.error||'Sign-in failed';});"""


async def login_page(req: Request):
    if S.mode == "switch":
        return RedirectResponse("/", status_code=302)
    sso = '<a class="sso" href="/auth/oidc">Sign in with your company account</a>' if S.oidc else ""
    local = ('<form id="f"><label for="u">User name</label><input id="u" name="user" autocomplete="username" required>'
             '<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>'
             '<button type="submit">Sign in</button></form>') if S.local_login else ""
    return HTMLResponse(LOGIN_HTML.replace("{sso}", sso).replace("{local}", local))


async def login_local(req: Request):
    if not S.local_login:
        return err("Local sign-in is off; use the company account.", 403)
    b = await body(req)
    user, pw = str(b.get("user", "")).strip(), str(b.get("password", ""))
    ip = req.client.host if req.client else "?"
    if not S.throttle.allowed("u:" + user, "ip:" + ip):
        S.store.audit(user, "login_throttled", ip)
        return err("Too many failed attempts. Wait 10 minutes.", 429)
    u = S.store.user(user)
    if not u or u["disabled"] or u["source"] != "local" or not check_password(pw, u["pw"]):
        S.throttle.fail("u:" + user, "ip:" + ip)
        S.store.audit(user, "login_failed", ip)
        return err("Wrong user name or password.", 401)
    S.throttle.ok("u:" + user, "ip:" + ip)
    req.session.clear()
    req.session.update({"uid": user, "at": time.time()})
    S.store.audit(user, "login", ip, {"method": "local"})
    return JSONResponse({"ok": True})


async def login_oidc(req: Request):
    if not S.oidc:
        return err("Company sign-in is not set up.", 404)
    url, saved = await run_in_threadpool(S.oidc.start)
    req.session["oidc"] = saved
    return RedirectResponse(url, status_code=302)


async def oidc_callback(req: Request):
    if not S.oidc:
        return err("Company sign-in is not set up.", 404)
    saved = req.session.pop("oidc", None)
    try:
        claims = await run_in_threadpool(S.oidc.finish, req.query_params.get("code", ""), req.query_params.get("state", ""), saved)
    except Exception as e:
        S.store.audit("", "login_failed", "oidc", {"reason": str(e)[:200]})
        return HTMLResponse(f"<p>Sign-in failed: {str(e)[:200]}</p><p><a href='/login'>Try again</a></p>", status_code=401)
    uid = "oidc:" + str(claims["sub"])
    S.store.upsert_user(uid, claims.get("name") or claims.get("preferred_username") or "", claims.get("email", ""), "oidc")
    if S.store.user(uid)["disabled"]:
        return HTMLResponse("<p>This account is switched off in PR World.</p>", status_code=403)
    roles = S.oidc.roles_for(claims)
    S.store.set_roles(uid, roles, "oidc")
    req.session.clear()
    req.session.update({"uid": uid, "at": time.time()})
    S.store.audit(uid, "login", "oidc", {"roles": roles})
    return RedirectResponse("/", status_code=302)


async def logout(req: Request):
    uid = req.session.get("uid")
    req.session.clear()
    if uid:
        S.store.audit(uid, "logout")
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------- data (cut per user)
async def data_file(req: Request):
    uid = uid_of(req)
    rel = req.path_params["path"]
    if rel == "settings.json":
        return JSONResponse(effective_settings(uid))
    if rel in ("scorecard.json", "calibration.json", "experiment.json"):     # built from the test tool's answer key: admins only
        if not S.store.is_admin(uid):
            return err("Not found", 404)
        return JSONResponse(S.data.load(rel) or {})
    parts = rel.split("/")
    allowed = rel in ("index.json", "meaning.json") or (len(parts) == 2 and parts[0] in ("worlds", "diffs", "reviews", "notes") and parts[1].endswith(".json"))
    if not allowed:
        return err("Not found", 404)
    raw = S.data.load(rel)
    if raw is None:
        return err("Not found", 404)
    v = S.view(uid)
    p = S.data.path(rel)
    key = (rel, os.path.getmtime(p), frozenset(v.locked), tuple(sorted(v.alias.items())))

    def make():
        if parts[0] == "worlds":
            return v.world(raw)
        if parts[0] == "diffs":
            return v.diff(raw)
        if parts[0] == "reviews":
            return v.review(raw)
        if parts[0] == "notes":
            return v.notes(raw, S.data.load("reviews/" + parts[1]))
        if rel == "meaning.json":
            return v.meaning(raw)
        return v.index(raw)
    out = await run_in_threadpool(S.cached, key, make)
    if rel != "index.json":
        S.log_open(uid, rel, {"cut": sorted(v.mname(m) for m in v.locked)} if v.locked else {})
    return JSONResponse(out)


# ---------------------------------------------------------------------- me, modules, settings
async def me(req: Request):
    uid = uid_of(req)
    u = S.store.user(uid)
    v = S.view(uid)
    return JSONResponse({"id": uid, "name": u["name"], "email": u["email"], "roles": S.store.roles_of(uid), "mode": S.mode,
                         "admin": S.store.is_admin(uid), "owns": S.store.owned_by(uid),
                         "levels": {v.mname(m): v.level(m) for m in S.data.modules()},
                         "unread": sum(1 for n in S.store.inbox(uid) if not n["read_at"]),
                         "settings_badge": S.team.badge() if S.team else "settings file has a problem"})


async def modules(req: Request):
    uid = uid_of(req)
    v = S.view(uid)
    out = []
    for m in S.data.modules():
        out.append({"module": v.mname(m), "level": v.level(m), "locked": m in v.locked, "tier": S.data.module_tier.get(m, ""),
                    "owners": [] if m in v.alias else [o["user"] for o in S.store.owners(m)],
                    "real": None if m in v.alias else m})
    return JSONResponse({"modules": out, "levels": LEVELS})


def effective_settings(uid: Optional[str]) -> Dict:
    team = dict(S.team_get("view_defaults", default={}) or {})
    env_tv = os.environ.get("PRW_TRUST_VIEW")
    if env_tv in ("level", "percent"):
        team["trust_view"] = env_tv
    personal = S.store.prefs(uid) if uid else {}
    eff = {**{"trust_view": "level"}, **team, **personal}
    return {**eff, "team": team, "personal": personal}


async def settings_get(req: Request):
    return JSONResponse(effective_settings(uid_of(req)))


async def settings_put(req: Request):
    uid = uid_of(req)
    b = await body(req)
    clean = {k: v for k, v in b.items() if k in PERSONAL_KEYS and v not in (None, "")}
    try:
        from reviewer.platform_config import SCHEMA
        import jsonschema
        jsonschema.validate(clean, SCHEMA["properties"]["view_defaults"])
    except ImportError:
        pass
    except Exception as e:
        return err("Setting refused: " + str(getattr(e, "message", e))[:200])
    S.store.set_prefs(uid, clean)
    S.store.audit(uid, "personal_settings", uid, clean)
    return JSONResponse(effective_settings(uid))


MODEL_SECTIONS = [
    {"key": "specialist", "label": "Specialist reviewers", "where": "Read the change for one concern each (security, safety, tests, and so on)."},
    {"key": "validator", "label": "Validator", "where": "Double-checks every finding against the real code."},
    {"key": "panel", "label": "Second-opinion panel", "where": "2 to 5 different models vote on Critical findings."},
    {"key": "investigator", "label": "Investigator", "where": "Follows a doubtful finding through the code, step by step."},
    {"key": "requirement_analyst", "label": "Requirement analyst", "where": "Turns the ticket into a checklist of what must be true."},
    {"key": "change_interpreter", "label": "Change interpreter", "where": "Describes what the change does, without seeing the ticket."},
    {"key": "requirement_judge", "label": "Requirement judge", "where": "Compares checklist and change; says met, not met or unclear."},
    {"key": "radar", "label": "Radar", "where": "Looks for risks the specialists were not asked about."},
    {"key": "fixer", "label": "Fix suggester", "where": "Proposes a fix for a finding."},
    {"key": "writer", "label": "Summary writer", "where": "Writes the plain-language notes on a PR."},
    {"key": "draft_policy", "label": "Policy drafter", "where": "Drafts team settings from a plain description."},
]


async def plugins(req: Request):
    if not S.team:
        return err("The team settings file has a problem: " + getattr(S, "team_error", ""), 500)
    from reviewer.plugins import Registry
    from reviewer.platform_config import LOCKED, list_presets
    reg = Registry(S.team, base_dir=os.path.dirname(S.settings_path) if S.settings_path else ".")
    cards = []
    for p in reg.catalog():
        cards.append(p)
    cov = S.team_get("coverage", default={})
    levels = {lv: {"plugins": sorted(reg.enabled_for_level(lv)), "estimate_calls": reg.estimate_calls(reg.enabled_for_level(lv))}
              for lv in ("essential", "full")}
    models = {"default": S.team_get("models", "default", default={"provider": "gemini", "model": "gemini-3.8-flash"}),
              "roles": S.team_get("models", "roles", default={}) or {}, "role_list": MODEL_SECTIONS,
              "providers": [{"id": "gemini", "label": "Gemini", "note": "connected"}, {"id": "openai", "label": "OpenAI", "note": "needs OPENAI_API_KEY in .env"},
                            {"id": "anthropic", "label": "Anthropic", "note": "needs ANTHROPIC_API_KEY in .env"},
                            {"id": "local", "label": "Local model", "note": "your own OpenAI-compatible server"},
                            {"id": "mock", "label": "Rehearsal (no AI)", "note": "fixed example answers, for tests"}],
              "suggest": {"gemini": ["gemini-3.8-flash", "gemini-4-hydrogen"]}}
    return JSONResponse({"models": models, "plugins": cards, "coverage": cov, "levels": levels, "badge": S.team.badge(), "fingerprint": S.team.fingerprint,
                         "locked": LOCKED, "presets": list_presets(), "problems": reg.problems, "warnings": S.team.warnings,
                         "wizard": {"regulated": "strict-bank", "business": "balanced", "small": "fast-team", "critical": "critical-only"}})


# ---------------------------------------------------------------------- access requests and emergency access
def module_real(v: View, name: str) -> Optional[str]:
    for m in S.data.modules():
        if v.mname(m) == name or m == name and m not in v.alias:
            return m
    return None


async def request_access(req: Request):
    uid = uid_of(req)
    b = await body(req)
    v = S.view(uid)
    m = module_real(v, str(b.get("module", "")))
    lv = b.get("level", "read")
    reason = str(b.get("reason", "")).strip()
    if not m or lv not in RANK or lv == "overview":
        return err("Choose a module and a level (read, review or sign).")
    if len(reason) < 5:
        return err("Write why you need access (the owner sees it).")
    if v.can(m, lv):
        return err("You already have this access.")
    rid = S.store.x("INSERT INTO requests(user,module,level,reason,created_at,status) VALUES(?,?,?,?,?,?)", (uid, m, lv, reason, iso(), "open"))
    S.store.audit(uid, "access_requested", m, {"level": lv, "reason": reason, "request": rid})
    S.notify_owners(m, f"{uid} asks for {lv} access to {m}: {reason}", "request")
    return JSONResponse({"ok": True, "id": rid})


async def list_requests(req: Request):
    uid = uid_of(req)
    mine = S.store.q("SELECT * FROM requests WHERE user=? ORDER BY id DESC", (uid,))
    owned = S.store.owned_by(uid)
    if S.store.is_admin(uid):
        todo = S.store.q("SELECT * FROM requests WHERE status='open' ORDER BY id")
    else:
        todo = [r for r in S.store.q("SELECT * FROM requests WHERE status='open' ORDER BY id") if r["module"] in owned]
    v = S.view(uid)
    for r in mine:
        r["module"] = v.mname(r["module"])
    return JSONResponse({"mine": mine, "to_decide": todo})


async def decide_request(req: Request):
    uid = uid_of(req)
    rid = int(req.path_params["rid"])
    b = await body(req)
    r = S.store.one("SELECT * FROM requests WHERE id=?", (rid,))
    if not r or r["status"] != "open":
        return err("No open request with this number.", 404)
    if r["module"] not in S.store.owned_by(uid) and not S.store.is_admin(uid):
        return err("Only the module owner or an admin can decide.", 403)
    if r["user"] == uid:
        return err("You cannot approve your own request.", 403)
    approve = bool(b.get("approve"))
    gid = None
    if approve:
        until = until_from_hours(b["hours"]) if b.get("hours") else (b.get("until") or None)
        gid = S.store.add_grant(r["user"], r["module"], r["level"], until, uid, f"request {rid}: {r['reason']}")
    S.store.x("UPDATE requests SET status=?, decided_by=?, decided_at=?, note=?, grant_id=? WHERE id=?",
              ("approved" if approve else "declined", uid, iso(), str(b.get("note", ""))[:500], gid, rid))
    S.store.audit(uid, "access_" + ("approved" if approve else "declined"), r["module"], {"request": rid, "user": r["user"], "level": r["level"], "grant": gid})
    S.store.notify(r["user"], "request", f"Your {r['level']} access to {r['module']} was {'approved' if approve else 'declined'} by {uid}."
                   + (f" Note: {b.get('note')}" if b.get("note") else ""))
    return JSONResponse({"ok": True, "grant": gid})


async def emergency(req: Request):
    uid = uid_of(req)
    b = await body(req)
    v = S.view(uid)
    m = module_real(v, str(b.get("module", "")))
    reason = str(b.get("reason", "")).strip()
    hours = float(b.get("hours") or 1)
    if not m:
        return err("Choose a module.")
    if len(reason) < 10:
        return err("Emergency access needs a clear reason (at least 10 characters). The owner is told at once.")
    if hours <= 0 or hours > S.emergency_max():
        return err(f"Emergency access lasts at most {S.emergency_max()} hours.")
    gid = S.store.add_grant(uid, m, "read", until_from_hours(hours), uid, reason, kind="emergency")
    S.store.audit(uid, "emergency_access", m, {"hours": hours, "reason": reason, "grant": gid})
    owners = S.notify_owners(m, f"EMERGENCY ACCESS: {uid} opened {m} for {hours:g} h. Reason: {reason}", "emergency")
    return JSONResponse({"ok": True, "grant": gid, "until": until_from_hours(hours), "told": owners})


async def inbox(req: Request):
    uid = uid_of(req)
    return JSONResponse({"items": S.store.inbox(uid)})


async def inbox_read(req: Request):
    uid = uid_of(req)
    S.store.x("UPDATE inbox SET read_at=? WHERE user=? AND read_at IS NULL", (iso(), uid))
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------- sign-off per module, merge policy, feedback
def pr_bundle(pr_id: str):
    pr = S.pr(pr_id)
    if not pr:
        return None
    return pr, S.data.load(f"diffs/{pr_id}.json"), S.data.load(f"reviews/{pr_id}.json"), S.data.load(f"notes/{pr_id}.json")


def signoff_view(pr_id: str, uid: str) -> Optional[Dict]:
    b = pr_bundle(pr_id)
    if not b:
        return None
    pr, diff, review, notes = b
    head = pr.get("head", "")
    sigs = S.store.q("SELECT * FROM signatures WHERE pr=? AND kind='person' ORDER BY id", (pr_id,))
    st = pol.signoff_status(pr_id, head, pol.parts(diff), sigs, S.sign_secret)
    v = S.view(uid)
    for p in st["parts"]:
        p["can_sign"] = v.can(p["module"], "sign")
        p["module"] = v.mname(p["module"])
    by_policy = S.store.q("SELECT * FROM signatures WHERE pr=? AND kind='policy' AND head=? AND withdrawn_at IS NULL", (pr_id, head))
    st["merge_by_policy"] = [{"rule": s["module"], "by": s["user"], "at": s["at"], "note": s["note"]} for s in by_policy]
    st["ready"] = st["all_signed"] or bool(by_policy)
    st["label"] = ((notes or {}).get("verdict") or {}).get("label")
    st["trust"] = pol.pr_trust(notes, review)
    st["note"] = "The AI never approves. A PR is ready only when every changed module is signed by a person with Sign access, or a signed merge rule allows it."
    return st


async def signoff_get(req: Request):
    st = signoff_view(req.path_params["pr"], uid_of(req))
    return JSONResponse(st) if st else err("No such PR.", 404)


async def sign(req: Request):
    uid = uid_of(req)
    pr_id = req.path_params["pr"]
    b = await body(req)
    bun = pr_bundle(pr_id)
    if not bun:
        return err("No such PR.", 404)
    pr, diff, review, notes = bun
    v = S.view(uid)
    m = module_real(v, str(b.get("module", "")))
    if not m or m not in pol.parts(diff):
        return err("This module has no change in this PR.")
    if not v.can(m, "sign"):
        S.store.audit(uid, "sign_refused", f"{pr_id}/{m}", {"reason": "no Sign access"})
        return err("You need Sign access to this module.", 403)
    note = str(b.get("note", "")).strip()[:1000]
    label = ((notes or {}).get("verdict") or {}).get("label")
    if label == "fix" and len(note) < 15:
        return err("This PR is labelled Fix before merge. To sign anyway, write the risk you accept (at least 15 characters).")
    head, at = pr.get("head", ""), iso()
    mac = pol.sign_mac(S.sign_secret, pr_id, m, head, uid, at, note)
    S.store.x("INSERT INTO signatures(pr,module,head,user,at,note,mac,kind) VALUES(?,?,?,?,?,?,?,'person')", (pr_id, m, head, uid, at, note, mac))
    S.store.audit(uid, "signed", f"{pr_id}/{m}", {"head": head, "label": label, "note": note})
    return JSONResponse(signoff_view(pr_id, uid))


async def withdraw(req: Request):
    uid = uid_of(req)
    pr_id = req.path_params["pr"]
    b = await body(req)
    v = S.view(uid)
    m = module_real(v, str(b.get("module", "")))
    n = S.store.q("SELECT id FROM signatures WHERE pr=? AND module=? AND user=? AND withdrawn_at IS NULL AND kind='person'", (pr_id, m, uid))
    if not n:
        return err("You have no signature on this part.", 404)
    S.store.x("UPDATE signatures SET withdrawn_at=? WHERE pr=? AND module=? AND user=? AND withdrawn_at IS NULL", (iso(), pr_id, m, uid))
    S.store.audit(uid, "signature_withdrawn", f"{pr_id}/{m}")
    return JSONResponse(signoff_view(pr_id, uid))


async def merge_get(req: Request):
    bun = pr_bundle(req.path_params["pr"])
    if not bun:
        return err("No such PR.", 404)
    _, diff, review, notes = bun
    mp = S.team_get("merge_policy", default={}) or {}
    ev = pol.evaluate_merge(mp.get("rules", []), mp.get("protected_areas", []), review, notes, diff)
    v = S.view(uid_of(req))
    ev["protected_touched"] = [v.mname(m) for m in ev["protected_touched"]]
    return JSONResponse(ev)


async def merge_post(req: Request):
    uid = uid_of(req)
    pr_id = req.path_params["pr"]
    bun = pr_bundle(pr_id)
    if not bun:
        return err("No such PR.", 404)
    pr, diff, review, notes = bun
    v = S.view(uid)
    if not all(v.can(m, "review") for m in pol.parts(diff)):
        return err("You need Review access to every changed module to record a merge by policy.", 403)
    mp = S.team_get("merge_policy", default={}) or {}
    ev = pol.evaluate_merge(mp.get("rules", []), mp.get("protected_areas", []), review, notes, diff)
    if not ev["allowed"]:
        S.store.audit(uid, "merge_by_policy_refused", pr_id, {"checks": ev["checks"]})
        return err("No signed rule allows this PR: " + "; ".join(f"{c['rule']}: {', '.join(c['why_not'])}" for c in ev["checks"]) if ev["checks"]
                   else "There is no signed merge rule in the team settings.", 403)
    r = ev["rule"]
    note = f"approved by policy {r['rule']}, signed by {r['signed_by']} on {r.get('signed_on') or '?'}; recorded by {uid}"
    at = iso()
    mac = pol.sign_mac(S.sign_secret, pr_id, r["rule"], pr.get("head", ""), "policy:" + r["rule"], at, note)
    S.store.x("INSERT INTO signatures(pr,module,head,user,at,note,mac,kind) VALUES(?,?,?,?,?,?,?,'policy')",
              (pr_id, r["rule"], pr.get("head", ""), "policy:" + r["rule"], at, note, mac))
    S.store.audit(uid, "merge_by_policy", pr_id, {"rule": r["rule"], "signed_by": r["signed_by"], "head": pr.get("head", "")})
    return JSONResponse({"ok": True, "note": note})


async def feedback_post(req: Request):
    uid = uid_of(req)
    pr_id = req.path_params["pr"]
    b = await body(req)
    review = S.data.load(f"reviews/{pr_id}.json") or {}
    f = next((x for x in review.get("findings", []) + review.get("dropped_findings", []) if x.get("id") == b.get("finding")), None)
    if not f:
        return err("No such finding.", 404)
    if b.get("verdict") not in ("accepted", "rejected"):
        return err("verdict must be accepted or rejected")
    m = S.data.module_of_file(f.get("file", ""))
    v = S.view(uid)
    if not (v.can(m, "review") if m else v.star in ("review", "sign")):
        return err("You need Review access to this module.", 403)
    S.store.x("INSERT INTO feedback(pr,finding,user,verdict,note,at) VALUES(?,?,?,?,?,?)", (pr_id, f["id"], uid, b["verdict"], str(b.get("note", ""))[:1000], iso()))
    S.store.audit(uid, "finding_" + b["verdict"], f"{pr_id}/{f['id']}", {"note": str(b.get("note", ""))[:300]})
    return JSONResponse({"ok": True})


async def feedback_get(req: Request):
    uid = uid_of(req)
    pr_id = req.path_params["pr"]
    review = S.data.load(f"reviews/{pr_id}.json") or {}
    v = S.view(uid)
    rows = S.store.q("SELECT finding,user,verdict,note,at FROM feedback WHERE pr=? ORDER BY id", (pr_id,))
    return JSONResponse({"items": [r for r in rows if not v.finding_locked(review, r["finding"])]})


# ---------------------------------------------------------------------- admin
async def admin_users(req: Request):
    if req.method == "POST":
        uid = need_admin(req)
        b = await body(req)
        new = str(b.get("id", "")).strip()
        if not new or ":" in new or len(new) > 64:
            return err("User name: letters, digits, dots or dashes.")
        if S.store.user(new):
            return err("This user exists.")
        S.store.upsert_user(new, b.get("name", new), b.get("email", ""), "local")
        temp = None
        if S.mode == "switch":
            pass                                  # no passwords in switch mode
        elif b.get("password"):
            S.store.set_password(new, hash_password(str(b["password"])))
        else:
            temp = secrets.token_urlsafe(12)
            S.store.set_password(new, hash_password(temp))
        S.store.set_roles(new, [r for r in b.get("roles", []) if S.store.one("SELECT 1 AS x FROM roles WHERE name=?", (r,))], "admin")
        S.store.audit(uid, "user_created", new, {"roles": b.get("roles", [])})
        return JSONResponse({"ok": True, "temporary_password": temp})
    users = S.store.q("SELECT id,name,email,source,created_at,disabled, pw IS NOT NULL AS has_password FROM users ORDER BY id")
    for u in users:
        u["roles"] = S.store.roles_of(u["id"])
        u["grants"] = S.store.active_grants(u["id"])
        u["owns"] = S.store.owned_by(u["id"])
    return JSONResponse({"users": users})


async def admin_user_roles(req: Request):
    uid = need_admin(req)
    target = req.path_params["uid"]
    b = await body(req)
    roles = [r for r in b.get("roles", []) if S.store.one("SELECT 1 AS x FROM roles WHERE name=?", (r,))]
    if target == uid and S.store.is_admin(uid) and not any(S.store.one("SELECT admin FROM roles WHERE name=?", (r,))["admin"] for r in roles):
        if len(S.store.q("SELECT DISTINCT ur.user FROM user_roles ur JOIN roles r ON r.name=ur.role WHERE r.admin=1")) <= 1:
            return err("You are the last admin; give another person the admin role first.")
    before = S.store.roles_of(target)
    for src in ("admin", "file"):
        S.store.set_roles(target, [], src)
    S.store.set_roles(target, roles, "admin")
    S.store.audit(uid, "roles_changed", target, {"before": before, "after": S.store.roles_of(target)})
    return JSONResponse({"ok": True, "roles": S.store.roles_of(target)})


async def admin_user_disable(req: Request):
    uid = need_admin(req)
    target = req.path_params["uid"]
    b = await body(req)
    off = bool(b.get("disabled", True))
    if target == uid and off:
        return err("You cannot switch yourself off.")
    S.store.x("UPDATE users SET disabled=? WHERE id=?", (int(off), target))
    S.store.audit(uid, "user_disabled" if off else "user_enabled", target)
    return JSONResponse({"ok": True})


async def admin_roles(req: Request):
    roles = S.store.q("SELECT * FROM roles ORDER BY name")
    for r in roles:
        r["modules"] = {x["module"]: x["level"] for x in S.store.q("SELECT module, level FROM role_modules WHERE role=?", (r["name"],))}
        r["members"] = [x["user"] for x in S.store.q("SELECT user FROM user_roles WHERE role=?", (r["name"],))]
    return JSONResponse({"roles": roles, "levels": LEVELS, "modules": S.data.modules()})


async def admin_role_put(req: Request):
    uid = need_admin(req)
    name = req.path_params["name"]
    b = await body(req)
    mods = b.get("modules") or {}
    for m, lv in mods.items():
        if lv not in RANK:
            return err(f"Unknown level {lv}.")
    before = {x["module"]: x["level"] for x in S.store.q("SELECT module, level FROM role_modules WHERE role=?", (name,))}
    old = S.store.one("SELECT * FROM roles WHERE name=?", (name,))
    admin_flag = int(bool(b.get("admin", old["admin"] if old else False)))
    if old and old["admin"] and not admin_flag and len(S.store.q("SELECT name FROM roles WHERE admin=1")) <= 1:
        return err("This is the last admin role.")
    S.store.x("INSERT INTO roles(name,description,admin) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET description=excluded.description, admin=excluded.admin",
              (name, b.get("description", old["description"] if old else ""), admin_flag))
    with S.store.lock:
        S.store.db.execute("DELETE FROM role_modules WHERE role=?", (name,))
        for m, lv in mods.items():
            S.store.db.execute("INSERT INTO role_modules(role,module,level) VALUES(?,?,?)", (name, m, lv))
        S.store.db.commit()
    S.store.audit(uid, "role_changed", name, {"before": before, "after": mods, "admin": admin_flag})
    return JSONResponse({"ok": True})


async def admin_grants(req: Request):
    uid = need_admin(req)
    if req.method == "POST":
        b = await body(req)
        target, m, lv = b.get("user"), b.get("module"), b.get("level")
        if not S.store.user(target or ""):
            return err("No such user.")
        if lv not in RANK or (m != "*" and m not in S.data.modules()):
            return err("Choose a module and a level.")
        until = until_from_hours(b["hours"]) if b.get("hours") else (b.get("until") or None)
        gid = S.store.add_grant(target, m, lv, until, uid, str(b.get("reason", ""))[:500])
        S.store.audit(uid, "grant_added", target, {"module": m, "level": lv, "until": until, "grant": gid})
        S.store.notify(target, "grant", f"You now have {lv} access to {m}" + (f" until {until}" if until else "") + f" (by {uid}).")
        return JSONResponse({"ok": True, "id": gid})
    rows = S.store.q("SELECT * FROM grants ORDER BY id DESC LIMIT 1000")
    return JSONResponse({"grants": rows})


async def admin_grant_revoke(req: Request):
    uid = need_admin(req)
    gid = int(req.path_params["gid"])
    g = S.store.one("SELECT * FROM grants WHERE id=?", (gid,))
    if not g or g["revoked_at"]:
        return err("No active grant with this number.", 404)
    S.store.revoke_grant(gid, uid)
    S.store.audit(uid, "grant_revoked", g["user"], {"grant": gid, "module": g["module"], "level": g["level"]})
    return JSONResponse({"ok": True})


async def admin_owners(req: Request):
    if req.method == "PUT":
        uid = need_admin(req)
        m = req.path_params.get("module")
        b = await body(req)
        before = [o["user"] for o in S.store.owners(m)]
        with S.store.lock:
            S.store.db.execute("DELETE FROM owners WHERE module=?", (m,))
            for u in b.get("users", []):
                S.store.db.execute("INSERT OR IGNORE INTO owners(module,user) VALUES(?,?)", (m, u))
            S.store.db.commit()
        S.store.audit(uid, "owners_changed", m, {"before": before, "after": b.get("users", [])})
        return JSONResponse({"ok": True})
    return JSONResponse({"owners": {m: [o["user"] for o in S.store.owners(m)] for m in S.data.modules()}})


async def admin_audit(req: Request):
    qp = req.query_params
    return JSONResponse({"rows": S.store.audit_rows(int(qp.get("limit", 500)), qp.get("user", ""), qp.get("action", ""), qp.get("target", "")),
                         "chain": S.store.verify_audit()})


async def admin_settings_check(req: Request):
    uid = need_admin(req)
    b = await body(req)
    from reviewer.platform_config import ConfigError, load_config
    try:
        raw = yaml.safe_load(b.get("yaml", "")) or {}
    except Exception as e:
        return err(f"Not valid YAML: {e}")
    tmp = os.path.join(os.path.dirname(S.config_path), ".prworld.check.yaml")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(raw, fh, sort_keys=False)
    try:
        c = load_config(tmp)
    except ConfigError as e:
        return JSONResponse({"ok": False, "problems": str(e).split("\n")})
    finally:
        os.path.exists(tmp) and os.remove(tmp)
    out = {"ok": True, "fingerprint": c.fingerprint, "badge": c.badge(), "warnings": c.warnings}
    if b.get("save"):
        if not raw.get("approved_by") or not raw.get("approved_on"):
            return JSONResponse({**out, "ok": False, "problems": ["A named person must approve the settings: fill approved_by and approved_on."]})
        if not S.settings_path:
            return err("This server has no settings file path (settings: in access.yaml).")
        if os.path.exists(S.settings_path):
            keep = S.settings_path.replace(".yaml", f".{time.strftime('%Y%m%d-%H%M%S')}.yaml")
            os.replace(S.settings_path, keep)          # the old version is kept, never deleted
            out["previous_kept_as"] = os.path.basename(keep)
        with open(S.settings_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(raw, fh, sort_keys=False)
        S.team = S.load_team()
        S.store.audit(uid, "team_settings_saved", S.settings_path, {"fingerprint": c.fingerprint, "approved_by": raw.get("approved_by")})
        out["saved"] = True
    return JSONResponse(out)


async def admin_settings_get(req: Request):
    txt = ""
    if S.settings_path and os.path.exists(S.settings_path):
        with open(S.settings_path, encoding="utf-8") as fh:
            txt = fh.read()
    try:
        raw = yaml.safe_load(txt) if txt else None
    except Exception:
        raw = None
    return JSONResponse({"path": S.settings_path, "yaml": txt, "raw": raw, "fingerprint": S.team.fingerprint if S.team else None,
                         "badge": S.team.badge() if S.team else None, "error": getattr(S, "team_error", None) if not S.team else None})


async def people(req: Request):
    """Switch mode: everyone you can view the app as, with their roles and what they own."""
    roles = {r["name"]: r for r in S.store.q("SELECT * FROM roles")}
    out = []
    for u in S.store.q("SELECT id, name, disabled FROM users ORDER BY name"):
        if u["disabled"]:
            continue
        rs = S.store.roles_of(u["id"])
        out.append({"id": u["id"], "name": u["name"], "roles": rs, "owns": S.store.owned_by(u["id"]),
                    "about": "; ".join(roles[r]["description"] for r in rs if r in roles and roles[r]["description"]),
                    "admin": S.store.is_admin(u["id"])})
    return JSONResponse({"mode": S.mode, "current": uid_of(req), "people": out})


async def switch_user(req: Request):
    if S.mode != "switch":
        return err("Switching people is off: this server uses sign-in.", 403)
    before = uid_of(req)
    b = await body(req)
    u = S.store.user(str(b.get("user", "")))
    if not u or u["disabled"]:
        return err("No such person.", 404)
    req.session.clear()
    req.session.update({"uid": u["id"], "at": time.time()})
    S.store.audit(u["id"], "switched_user", u["id"], {"from": before})
    return JSONResponse({"ok": True, "user": u["id"]})


async def health(req: Request):
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------- middleware: login wall, CSRF header, admin wall, headers
PUBLIC = ("/login", "/login.css", "/login.js", "/auth/local", "/auth/oidc", "/auth/callback", "/healthz")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


class Guard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        req = Request(scope, receive)
        path = scope["path"]
        method = scope["method"]

        async def add_headers(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                for k, v in (("content-security-policy", CSP), ("x-content-type-options", "nosniff"), ("referrer-policy", "same-origin"),
                             ("x-frame-options", "DENY"), ("cache-control", "no-store")):
                    if k == "cache-control" and path.startswith("/assets/"):
                        v = "public, max-age=31536000, immutable"   # hashed build files never change
                    h.append((k.encode(), v.encode()))
            await send(message)

        if method not in ("GET", "HEAD", "OPTIONS") and path not in ("/auth/callback",) and req.headers.get("x-prw") != "1":
            return await JSONResponse({"error": "Missing request header."}, status_code=403)(scope, receive, add_headers)
        if not path.startswith(PUBLIC):
            if not uid_of(req):
                if path.startswith(("/api/", "/data/")):
                    return await JSONResponse({"error": "Sign in first."}, status_code=401)(scope, receive, add_headers)
                return await RedirectResponse("/login", status_code=302)(scope, receive, add_headers)
            if path.startswith("/api/admin/") and not need_admin(req):
                S.store.audit(req.session.get("uid", ""), "admin_refused", path)
                return await JSONResponse({"error": "Admins only."}, status_code=403)(scope, receive, add_headers)
        return await self.app(scope, receive, add_headers)


def build_app(config_path: str) -> Starlette:
    global S
    S = Server(config_path)
    routes = [
        Route("/healthz", health), Route("/login", login_page),
        Route("/login.css", lambda r: Response(LOGIN_CSS, media_type="text/css")),
        Route("/login.js", lambda r: Response(LOGIN_JS, media_type="application/javascript")),
        Route("/auth/local", login_local, methods=["POST"]), Route("/auth/oidc", login_oidc), Route("/auth/callback", oidc_callback),
        Route("/auth/logout", logout, methods=["POST"]),
        Route("/data/{path:path}", data_file),
        Route("/api/me", me), Route("/api/people", people), Route("/api/switch", switch_user, methods=["POST"]), Route("/api/modules", modules),
        Route("/api/settings", settings_get, methods=["GET"]), Route("/api/settings", settings_put, methods=["PUT"]),
        Route("/api/plugins", plugins),
        Route("/api/access-requests", request_access, methods=["POST"]), Route("/api/access-requests", list_requests, methods=["GET"]),
        Route("/api/access-requests/{rid:int}/decide", decide_request, methods=["POST"]),
        Route("/api/emergency", emergency, methods=["POST"]),
        Route("/api/inbox", inbox), Route("/api/inbox/read", inbox_read, methods=["POST"]),
        Route("/api/prs/{pr}/signoff", signoff_get), Route("/api/prs/{pr}/sign", sign, methods=["POST"]),
        Route("/api/prs/{pr}/withdraw", withdraw, methods=["POST"]),
        Route("/api/prs/{pr}/merge", merge_get, methods=["GET"]), Route("/api/prs/{pr}/merge", merge_post, methods=["POST"]),
        Route("/api/prs/{pr}/feedback", feedback_get, methods=["GET"]), Route("/api/prs/{pr}/feedback", feedback_post, methods=["POST"]),
        Route("/api/admin/users", admin_users, methods=["GET", "POST"]),
        Route("/api/admin/users/{uid}/roles", admin_user_roles, methods=["PUT"]),
        Route("/api/admin/users/{uid}/disable", admin_user_disable, methods=["POST"]),
        Route("/api/admin/roles", admin_roles), Route("/api/admin/roles/{name}", admin_role_put, methods=["PUT"]),
        Route("/api/admin/grants", admin_grants, methods=["GET", "POST"]),
        Route("/api/admin/grants/{gid:int}/revoke", admin_grant_revoke, methods=["POST"]),
        Route("/api/admin/owners", admin_owners), Route("/api/admin/owners/{module}", admin_owners, methods=["PUT"]),
        Route("/api/admin/audit", admin_audit),
        Route("/api/admin/settings", admin_settings_get), Route("/api/admin/settings/check", admin_settings_check, methods=["POST"]),
    ]
    if S.dist and os.path.isdir(S.dist):
        routes.append(Mount("/", app=StaticFiles(directory=S.dist, html=True)))
    mw = [Middleware(SessionMiddleware, secret_key=S.session_secret.decode(), session_cookie="prw_session",
                     max_age=int(float(S.cfg.get("session_hours", 8)) * 3600), same_site="lax",
                     https_only=bool(S.cfg.get("cookie_secure", False))),
          Middleware(Guard), Middleware(GZipMiddleware, minimum_size=1024)]
    return Starlette(routes=routes, middleware=mw)
