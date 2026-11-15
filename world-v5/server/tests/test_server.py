"""Server tests on real PR World data (no network). Run from world-v5/server:  python -m unittest discover -s tests
Uses PRW_TEST_DATA (a viewer/data folder) and PRW_TEST_REVIEWER (ai-reviewer/backend)."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
sys.path.insert(0, SERVER)
DATA = os.environ.get("PRW_TEST_DATA", os.path.join(SERVER, "..", "..", "world-v3", "viewer", "data"))
REVIEWER = os.environ.get("PRW_TEST_REVIEWER", os.path.join(SERVER, "..", "..", "ai-reviewer", "backend"))

from prw_server import policy as pol  # noqa: E402
from prw_server.auth import hash_password  # noqa: E402

PW = "correct horse battery"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipUnless(os.path.isdir(DATA), "no PR World data folder")
class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn
        from prw_server import app as appmod
        cls.tmp = tempfile.mkdtemp()
        cls.data = os.path.join(cls.tmp, "data")
        shutil.copytree(DATA, cls.data)
        settings = os.path.join(cls.tmp, "prworld.yaml")
        with open(settings, "w") as fh:
            yaml.safe_dump({"version": "1", "preset": "balanced", "approved_by": "Test Owner", "approved_on": "2026-11-14",
                            "access": {"hide_restricted_names": False, "restricted_names": ["Audit"], "emergency_max_hours": 4}}, fh)
        cfg = {"mode": "login", "data": cls.data, "viewer": os.path.join(cls.tmp, "dist"), "reviewer": os.path.abspath(REVIEWER), "settings": settings,
               "database": os.path.join(cls.tmp, "t.db"), "secrets_file": os.path.join(cls.tmp, "s.json"),
               "roles": {"admin": {"admin": True}, "developer": {"modules": {"*": "read"}}, "testers": {"modules": {"Tests": "read"}}},
               "owners": {"Loans": ["omar"], "Database": ["omar"], "Platform": ["omar"], "Tests": ["omar"]},
               "users": {"root": {"roles": ["admin"]}, "lena": {"roles": ["testers"]}, "omar": {"roles": ["developer"]},
                         "nina": {"roles": ["developer"]}}}
        os.makedirs(cfg["viewer"])
        open(os.path.join(cfg["viewer"], "index.html"), "w").write("<html>viewer</html>")
        cls.cfgp = os.path.join(cls.tmp, "access.yaml")
        with open(cls.cfgp, "w") as fh:
            yaml.safe_dump(cfg, fh)
        app = appmod.build_app(cls.cfgp)
        cls.S = appmod.S
        for u in ("root", "lena", "omar", "nina"):
            cls.S.store.set_password(u, hash_password(PW))
        cls.port = free_port()
        cls.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error"))
        threading.Thread(target=cls.server.run, daemon=True).start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.05)
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True

    def login(self, user, pw=PW):
        s = requests.Session()
        s.headers["X-PRW"] = "1"
        r = s.post(self.base + "/auth/local", json={"user": user, "password": pw})
        self.assertEqual(r.status_code, 200, r.text)
        return s

    def get(self, s, path):
        r = s.get(self.base + path)
        self.assertEqual(r.status_code, 200, f"{path}: {r.status_code} {r.text[:200]}")
        return r.json()

    # ------------------------------------------------------------------ login wall
    def test_01_login_wall(self):
        self.assertEqual(requests.get(self.base + "/api/me").status_code, 401)
        self.assertEqual(requests.get(self.base + "/data/index.json").status_code, 401)
        r = requests.get(self.base + "/", allow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/login")
        self.assertIn("frame-ancestors 'none'", r.headers["content-security-policy"])

    def test_02_wrong_password_and_throttle(self):
        s = requests.Session()
        s.headers["X-PRW"] = "1"
        for _ in range(5):
            self.assertEqual(s.post(self.base + "/auth/local", json={"user": "nina", "password": "nope"}).status_code, 401)
        self.assertEqual(s.post(self.base + "/auth/local", json={"user": "nina", "password": PW}).status_code, 429)
        self.S.throttle.fails.clear()

    def test_03_post_needs_header(self):
        s = self.login("nina")
        r = requests.post(self.base + "/api/inbox/read", cookies=s.cookies)
        self.assertEqual(r.status_code, 403)

    # ------------------------------------------------------------------ per-user data
    def test_10_full_reader_gets_everything(self):
        s = self.login("nina")
        idx = self.get(s, "/data/index.json")
        w = self.get(s, f"/data/worlds/{idx['main']}.json")
        raw = json.load(open(os.path.join(self.data, "worlds", idx["main"] + ".json")))
        self.assertEqual(len(w["nodes"]), len(raw["nodes"]))
        self.assertNotIn("cut", w)

    def test_11_locked_modules_are_cut(self):
        s = self.login("lena")                         # reads Tests only
        idx = self.get(s, "/data/index.json")
        w = self.get(s, f"/data/worlds/{idx['main']}.json")
        mods = {n["module"] for n in w["nodes"] if n["kind"] != "module"}
        self.assertLessEqual(mods, {"Tests"})
        blocks = {n["name"]: n for n in w["nodes"] if n["kind"] == "module"}
        self.assertIn("Loans", blocks)
        self.assertTrue(blocks["Loans"]["attrs"]["locked"])
        self.assertIn("Restricted module 1", blocks)    # Audit's name is hidden by the team setting
        self.assertNotIn("Audit", blocks)
        for f in w["files"]:
            self.assertIn("Tests", f)
        txt = json.dumps(w)
        self.assertNotIn("LoanService.cs", txt)
        self.assertNotIn("module:Audit", txt)
        for e in w["edges"]:
            self.assertNotEqual(e["source"], e["target"])

    def test_12_review_and_notes_cut(self):
        s = self.login("lena")
        r = self.get(s, "/data/reviews/PR-2.json")
        c01 = next(f for f in r["findings"] if f["id"] == "C01")
        self.assertTrue(c01["locked"])
        self.assertEqual(c01["evidence"], "")
        self.assertEqual(c01["severity"], "Blocker")         # the risk stays visible, the details do not
        n = self.get(s, "/data/notes/PR-2.json")
        self.assertTrue(n["safe_version"])
        self.assertEqual(n["verdict"]["label"], "fix")
        raw = json.load(open(os.path.join(self.data, "notes", "PR-2.json")))
        for k in n["notes"]:
            self.assertIn("Tests", k)
        self.assertEqual(len(n["verdict"]["reasons"]), len(raw["verdict"]["reasons"]))
        txt = json.dumps(n)
        self.assertNotIn("LoanService.GetForCurrentUserAsync", txt)
        self.assertNotIn("M:Bank.Modules.Loans.", txt)
        self.assertEqual(n["roll"]["pr"]["changed"]["n"], raw["roll"]["pr"]["changed"]["n"])   # counts kept
        d = self.get(s, "/data/diffs/PR-2.json")
        self.assertIn("module:Loans", d["changed"])
        self.assertTrue(all("Modules/Loans/" not in f for f in d["changed_lines"]))

    def test_13_scorecard_admin_only(self):
        self.assertEqual(self.login("nina").get(self.base + "/data/scorecard.json").status_code, 404)
        self.assertEqual(self.login("root").get(self.base + "/data/scorecard.json").status_code, 200)

    def test_14_opens_are_logged(self):
        s = self.login("lena")
        self.get(s, "/data/reviews/PR-3.json")
        rows = self.S.store.audit_rows(50, user="lena", action="open")
        self.assertTrue(any(r["target"] == "reviews/PR-3.json" and r["detail"].get("cut") for r in rows))

    # ------------------------------------------------------------------ admin wall
    def test_20_admin_only(self):
        s = self.login("nina")
        self.assertEqual(s.get(self.base + "/api/admin/users").status_code, 403)
        self.assertTrue(self.S.store.audit_rows(10, user="nina", action="admin_refused"))
        a = self.login("root")
        users = self.get(a, "/api/admin/users")["users"]
        self.assertIn("lena", [u["id"] for u in users])

    # ------------------------------------------------------------------ request access -> owner decides
    def test_30_request_and_approve(self):
        lena, omar = self.login("lena"), self.login("omar")
        r = lena.post(self.base + "/api/access-requests", json={"module": "Loans", "level": "read", "reason": "fixing a loan test"})
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        todo = self.get(omar, "/api/access-requests")["to_decide"]
        self.assertIn(rid, [x["id"] for x in todo])
        self.assertEqual(lena.post(self.base + f"/api/access-requests/{rid}/decide", json={"approve": True}).status_code, 403)
        self.assertEqual(omar.post(self.base + f"/api/access-requests/{rid}/decide", json={"approve": True, "hours": 2}).status_code, 200)
        idx = self.get(lena, "/data/index.json")
        w = self.get(lena, f"/data/worlds/{idx['main']}.json")
        self.assertIn("Loans", {n["module"] for n in w["nodes"] if n["kind"] != "module"})
        self.assertTrue(any("approved" in i["text"] for i in self.get(lena, "/api/inbox")["items"]))
        g = self.S.store.one("SELECT id FROM grants WHERE user='lena' AND module='Loans'")
        self.S.store.revoke_grant(g["id"], "test")

    def test_31_emergency_access(self):
        lena = self.login("lena")
        self.assertEqual(lena.post(self.base + "/api/emergency", json={"module": "Ledger", "reason": "x", "hours": 1}).status_code, 400)
        self.assertEqual(lena.post(self.base + "/api/emergency", json={"module": "Ledger", "reason": "production incident 4411", "hours": 9}).status_code, 400)
        r = lena.post(self.base + "/api/emergency", json={"module": "Ledger", "reason": "production incident 4411", "hours": 1})
        self.assertEqual(r.status_code, 200, r.text)
        root_inbox = [i for i in self.S.store.inbox("root") if i["kind"] == "emergency"]
        self.assertTrue(root_inbox)
        self.assertEqual(self.get(lena, "/api/me")["levels"]["Ledger"], "read")
        self.S.store.x("UPDATE grants SET until='2000-01-01T00:00:00+00:00' WHERE id=?", (r.json()["grant"],))   # time is up
        self.assertEqual(self.get(lena, "/api/me")["levels"]["Ledger"], "overview")

    # ------------------------------------------------------------------ sign-off per module
    def test_40_signoff(self):
        nina, omar = self.login("nina"), self.login("omar")
        st = self.get(omar, "/api/prs/PR-1/signoff")
        self.assertEqual({p["module"] for p in st["parts"]}, {"Database", "Tests", "Platform", "Loans"})
        self.assertFalse(st["ready"])
        self.assertEqual(nina.post(self.base + "/api/prs/PR-1/sign", json={"module": "Loans"}).status_code, 403)
        for m in ("Database", "Tests", "Platform", "Loans"):
            r = omar.post(self.base + "/api/prs/PR-1/sign", json={"module": m, "note": "read it"})
            self.assertEqual(r.status_code, 200, r.text)
        st = self.get(omar, "/api/prs/PR-1/signoff")
        self.assertTrue(st["ready"])
        # tampering with a stored signature is detected
        self.S.store.x("UPDATE signatures SET user='mallory' WHERE pr='PR-1' AND module='Loans'")
        st = self.get(omar, "/api/prs/PR-1/signoff")
        self.assertFalse(st["ready"])
        self.assertEqual(next(p for p in st["parts"] if p["module"] == "Loans")["tampered"], 1)

    def test_41_fix_label_needs_accepted_risk(self):
        omar = self.login("omar")
        r = omar.post(self.base + "/api/prs/PR-4/sign", json={"module": "Loans"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Fix before merge", r.json()["error"])
        r = omar.post(self.base + "/api/prs/PR-4/sign", json={"module": "Loans", "note": "rounding error accepted until PR-10 lands"})
        self.assertEqual(r.status_code, 200)

    # ------------------------------------------------------------------ audit chain
    def test_50_audit_chain(self):
        self.assertTrue(self.S.store.verify_audit()["ok"])
        db = self.S.store
        rid = db.one("SELECT id, detail FROM audit ORDER BY id LIMIT 1 OFFSET 3")
        db.x("UPDATE audit SET detail='{}' WHERE id=?", (rid["id"],))
        self.assertFalse(db.verify_audit()["ok"])
        db.x("UPDATE audit SET detail=? WHERE id=?", (rid["detail"], rid["id"]))
        self.assertTrue(db.verify_audit()["ok"])

    # ------------------------------------------------------------------ settings and plugins
    def test_60_personal_settings(self):
        s = self.login("nina")
        self.assertEqual(self.get(s, "/data/settings.json")["trust_view"], "level")
        self.assertEqual(s.put(self.base + "/api/settings", json={"trust_view": "sometimes"}).status_code, 400)
        r = s.put(self.base + "/api/settings", json={"trust_view": "percent", "severity_min": "Blocker"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.get(s, "/data/settings.json")["trust_view"], "percent")
        self.assertEqual(self.get(self.login("lena"), "/data/settings.json")["trust_view"], "level")

    def test_61_plugins_page(self):
        p = self.get(self.login("nina"), "/api/plugins")
        ids = {x["id"] for x in p["plugins"]}
        self.assertIn("requirement_check", ids)
        self.assertGreater(p["levels"]["full"]["estimate_calls"], p["levels"]["essential"]["estimate_calls"])
        self.assertIn("allow_ai_approve", p["locked"])

    def test_62_settings_check_refuses_locked(self):
        a = self.login("root")
        r = a.post(self.base + "/api/admin/settings/check", json={"yaml": "version: '1'\npreset: balanced\nallow_ai_approve: true\n"})
        self.assertFalse(r.json()["ok"])
        r = a.post(self.base + "/api/admin/settings/check", json={"yaml": "version: '1'\npreset: fast-team\n", "save": True})
        self.assertFalse(r.json()["ok"])        # not approved by a named person: not saved


@unittest.skipUnless(os.path.isdir(DATA), "no PR World data folder")
class SwitchMode(unittest.TestCase):
    """This version: no sign-in; start as the default person and switch to anyone else."""
    @classmethod
    def setUpClass(cls):
        import uvicorn
        from prw_server import app as appmod
        cls.tmp = tempfile.mkdtemp()
        cfg = {"mode": "switch", "default_user": "boss", "data": os.path.abspath(DATA), "viewer": os.path.join(cls.tmp, "dist"),
               "reviewer": os.path.abspath(REVIEWER), "database": os.path.join(cls.tmp, "t.db"), "secrets_file": os.path.join(cls.tmp, "s.json"),
               "roles": {"admin": {"admin": True}, "architect": {"modules": {"*": "read"}, "description": "Reads every module"},
                         "qa": {"modules": {"Tests": "read"}, "description": "Tests only"}},
               "owners": {"Loans": ["boss"]},
               "users": {"boss": {"name": "Boss", "roles": ["admin", "architect"]}, "tess": {"name": "Tess (QA)", "roles": ["qa"]}}}
        os.makedirs(cfg["viewer"])
        open(os.path.join(cfg["viewer"], "index.html"), "w").write("<html>viewer</html>")
        p = os.path.join(cls.tmp, "access.yaml")
        with open(p, "w") as fh:
            yaml.safe_dump(cfg, fh)
        app = appmod.build_app(p)
        cls.S = appmod.S
        cls.port = free_port()
        cls.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error"))
        threading.Thread(target=cls.server.run, daemon=True).start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.05)
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True

    def test_no_sign_in_and_switch(self):
        s = requests.Session()
        s.headers["X-PRW"] = "1"
        me = s.get(self.base + "/api/me").json()
        self.assertEqual((me["id"], me["mode"]), ("boss", "switch"))
        self.assertEqual(s.get(self.base + "/login", allow_redirects=False).headers["location"], "/")
        ppl = s.get(self.base + "/api/people").json()["people"]
        self.assertEqual({p["id"] for p in ppl}, {"boss", "tess"})
        self.assertEqual(s.post(self.base + "/api/switch", json={"user": "nobody"}).status_code, 404)
        self.assertEqual(s.post(self.base + "/api/switch", json={"user": "tess"}).status_code, 200)
        me = s.get(self.base + "/api/me").json()
        self.assertEqual(me["id"], "tess")
        self.assertEqual(me["levels"]["Loans"], "overview")           # the view really changes
        self.assertEqual(s.get(self.base + "/api/admin/users").status_code, 403)
        self.assertTrue(self.S.store.audit_rows(10, action="switched_user"))
        self.assertEqual(s.post(self.base + "/auth/local", json={"user": "boss", "password": "x"}).status_code, 403)


class MergePolicy(unittest.TestCase):
    review = {"decision": "READY_FOR_SIGNOFF", "tier": {"tier": "low"}, "findings": [{"severity": "ShouldFix"}], "areas": []}
    notes = {"verdict": {"label": "ready"}, "roll": {"pr": {"changed": {"n": 4, "verified": 4, "contradicted": 0, "lo": 0.55, "hi": 0.99}}}}
    diff = {"modules": {"Reports": "changed"}}

    def rule(self, key="k", **kw):
        r = {"name": "low-risk", "max_tier": "low", "max_severity": "ShouldFix", "min_trust": "high", "signed_by": "Anna Berg (CTO)",
             "signed_on": "2026-11-14", **kw}
        r["signature"] = pol.sign_rule(r, key)
        return r

    def test_allowed(self):
        ev = pol.evaluate_merge([self.rule()], [], self.review, self.notes, self.diff, key="k")
        self.assertTrue(ev["allowed"], ev)
        self.assertEqual(ev["rule"]["signed_by"], "Anna Berg (CTO)")

    def test_changed_rule_refused(self):
        r = self.rule()
        r["max_tier"] = "medium"
        self.assertFalse(pol.evaluate_merge([r], [], self.review, self.notes, self.diff, key="k")["allowed"])

    def test_protected_and_not_checked_refused(self):
        self.assertFalse(pol.evaluate_merge([self.rule()], ["Reports"], self.review, self.notes, self.diff, key="k")["allowed"])
        rv = {**self.review, "areas": [{"area": "Performance", "status": "not_checked"}]}
        ev = pol.evaluate_merge([self.rule()], [], rv, self.notes, self.diff, key="k")
        self.assertFalse(ev["allowed"])
        self.assertEqual(ev["trust"]["key"], "medium")          # not checked caps trust below High

    def test_trust_rules(self):
        self.assertEqual(pol.trust_level({"n": 3, "verified": 1, "contradicted": 1, "lo": .1, "hi": .8})["key"], "low")
        self.assertEqual(pol.trust_level({"n": 3, "verified": 3, "contradicted": 0, "lo": .5, "hi": 1}, "fix")["key"], "low")
        self.assertEqual(pol.trust_level({"n": 6, "verified": 1, "contradicted": 0, "lo": .02, "hi": .45})["key"], "low")
        self.assertEqual(pol.trust_level({"n": 1, "verified": 1, "contradicted": 0, "lo": .2, "hi": 1})["key"], "medium")
        self.assertEqual(pol.trust_level({"n": 4, "verified": 4, "contradicted": 0, "lo": .55, "hi": 1}, "ready")["key"], "high")


if __name__ == "__main__":
    unittest.main()
