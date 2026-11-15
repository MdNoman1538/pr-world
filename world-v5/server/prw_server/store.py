"""SQLite store for the PR World server: users, roles, module access, requests, signatures, feedback, settings
and a hash-chained audit log. Nothing is deleted: grants are revoked, signatures are withdrawn, requests are decided."""
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

LEVELS = ["overview", "read", "review", "sign"]
RANK = {lv: i for i, lv in enumerate(LEVELS)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT, email TEXT, source TEXT, pw TEXT,
    created_at TEXT, disabled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS roles(name TEXT PRIMARY KEY, description TEXT, admin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS role_modules(role TEXT, module TEXT, level TEXT, PRIMARY KEY(role, module));
CREATE TABLE IF NOT EXISTS user_roles(user TEXT, role TEXT, source TEXT, PRIMARY KEY(user, role));
CREATE TABLE IF NOT EXISTS grants(id INTEGER PRIMARY KEY, user TEXT, module TEXT, level TEXT, until TEXT, by TEXT,
    reason TEXT, created_at TEXT, revoked_at TEXT, revoked_by TEXT, kind TEXT DEFAULT 'grant');
CREATE TABLE IF NOT EXISTS owners(module TEXT, user TEXT, PRIMARY KEY(module, user));
CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY, user TEXT, module TEXT, level TEXT, reason TEXT,
    created_at TEXT, status TEXT, decided_by TEXT, decided_at TEXT, note TEXT, grant_id INTEGER);
CREATE TABLE IF NOT EXISTS signatures(id INTEGER PRIMARY KEY, pr TEXT, module TEXT, head TEXT, user TEXT, at TEXT,
    note TEXT, mac TEXT, withdrawn_at TEXT, kind TEXT DEFAULT 'person');
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, pr TEXT, finding TEXT, user TEXT, verdict TEXT, note TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS prefs(user TEXT PRIMARY KEY, json TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS inbox(id INTEGER PRIMARY KEY, user TEXT, at TEXT, kind TEXT, text TEXT, read_at TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, user TEXT, action TEXT, target TEXT, detail TEXT,
    prev TEXT, hash TEXT);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(d: Optional[datetime] = None) -> str:
    return (d or now()).isoformat(timespec="seconds")


def parse(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _row_hash(prev: str, at: str, user: str, action: str, target: str, detail: str) -> str:
    return hashlib.sha256("\x1f".join([prev, at, user, action, target, detail]).encode()).hexdigest()


class Store:
    def __init__(self, path: str):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ------------------------------------------------------------------ low level
    def q(self, sql: str, args=()) -> List[Dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql: str, args=()) -> Optional[Dict]:
        r = self.q(sql, args)
        return r[0] if r else None

    def x(self, sql: str, args=()) -> int:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    # ------------------------------------------------------------------ audit (hash chain: any edit breaks verify())
    def audit(self, user: str, action: str, target: str = "", detail: Optional[Dict] = None) -> None:
        with self.lock:
            last = self.db.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
            prev = last["hash"] if last else "0" * 64
            at, d = iso(), json.dumps(detail or {}, sort_keys=True, separators=(",", ":"))
            h = _row_hash(prev, at, user or "", action, target or "", d)
            self.db.execute("INSERT INTO audit(at,user,action,target,detail,prev,hash) VALUES(?,?,?,?,?,?,?)",
                            (at, user or "", action, target or "", d, prev, h))
            self.db.commit()

    def verify_audit(self) -> Dict:
        prev, n = "0" * 64, 0
        for r in self.q("SELECT * FROM audit ORDER BY id"):
            n += 1
            if r["prev"] != prev or _row_hash(prev, r["at"], r["user"], r["action"], r["target"], r["detail"]) != r["hash"]:
                return {"ok": False, "rows": n, "broken_at": r["id"]}
            prev = r["hash"]
        return {"ok": True, "rows": n, "last_hash": prev}

    def audit_rows(self, limit: int = 500, user: str = "", action: str = "", target: str = "") -> List[Dict]:
        sql, args = "SELECT * FROM audit WHERE 1=1", []
        for col, val in (("user", user), ("action", action)):
            if val:
                sql += f" AND {col}=?"
                args.append(val)
        if target:
            sql += " AND target LIKE ?"
            args.append(f"%{target}%")
        rows = self.q(sql + " ORDER BY id DESC LIMIT ?", (*args, int(limit)))
        for r in rows:
            r["detail"] = json.loads(r["detail"] or "{}")
        return rows

    # ------------------------------------------------------------------ users and roles
    def user(self, uid: str) -> Optional[Dict]:
        return self.one("SELECT * FROM users WHERE id=?", (uid,))

    def upsert_user(self, uid: str, name: str = "", email: str = "", source: str = "local") -> None:
        if self.user(uid):
            self.x("UPDATE users SET name=COALESCE(NULLIF(?,''),name), email=COALESCE(NULLIF(?,''),email) WHERE id=?",
                   (name, email, uid))
        else:
            self.x("INSERT INTO users(id,name,email,source,created_at) VALUES(?,?,?,?,?)", (uid, name or uid, email, source, iso()))

    def set_password(self, uid: str, pw_hash: str) -> None:
        self.x("UPDATE users SET pw=? WHERE id=?", (pw_hash, uid))

    def roles_of(self, uid: str) -> List[str]:
        return [r["role"] for r in self.q("SELECT role FROM user_roles WHERE user=? ORDER BY role", (uid,))]

    def set_roles(self, uid: str, roles: List[str], source: str) -> None:
        """Replace the roles that came from one source (oidc login or admin) and keep the others."""
        with self.lock:
            self.db.execute("DELETE FROM user_roles WHERE user=? AND source=?", (uid, source))
            for r in roles:
                self.db.execute("INSERT OR IGNORE INTO user_roles(user,role,source) VALUES(?,?,?)", (uid, r, source))
            self.db.commit()

    def is_admin(self, uid: str) -> bool:
        return bool(self.one("SELECT 1 AS x FROM user_roles ur JOIN roles r ON r.name=ur.role WHERE ur.user=? AND r.admin=1", (uid,)))

    def owners(self, module: Optional[str] = None) -> List[Dict]:
        if module:
            return self.q("SELECT * FROM owners WHERE module=?", (module,))
        return self.q("SELECT * FROM owners ORDER BY module, user")

    def owned_by(self, uid: str) -> List[str]:
        return [r["module"] for r in self.q("SELECT module FROM owners WHERE user=?", (uid,))]

    # ------------------------------------------------------------------ module access
    def active_grants(self, uid: str) -> List[Dict]:
        t = iso()
        return self.q("SELECT * FROM grants WHERE user=? AND revoked_at IS NULL AND (until IS NULL OR until='' OR until>?)",
                      (uid, t))

    def levels_for(self, uid: str, modules: List[str], default_level: str = "overview") -> Dict[str, str]:
        """Module -> highest level from: default, roles (module or '*'), active grants, ownership (Sign)."""
        out = {m: default_level for m in modules}

        def lift(m, lv):
            if lv in RANK and (m not in out or RANK[lv] > RANK[out[m]]):
                out[m] = lv

        role_rows = self.q("SELECT rm.module, rm.level FROM role_modules rm JOIN user_roles ur ON ur.role=rm.role WHERE ur.user=?", (uid,))
        for r in role_rows:
            for m in (modules if r["module"] == "*" else [r["module"]]):
                lift(m, r["level"])
        for g in self.active_grants(uid):
            for m in (modules if g["module"] == "*" else [g["module"]]):
                lift(m, g["level"])
        for m in self.owned_by(uid):
            lift(m, "sign")
        return out

    def add_grant(self, uid: str, module: str, level: str, until: Optional[str], by: str, reason: str, kind: str = "grant") -> int:
        if level not in RANK:
            raise ValueError(f"unknown level {level}")
        return self.x("INSERT INTO grants(user,module,level,until,by,reason,created_at,kind) VALUES(?,?,?,?,?,?,?,?)",
                      (uid, module, level, until or None, by, reason, iso(), kind))

    def revoke_grant(self, gid: int, by: str) -> bool:
        return bool(self.x("UPDATE grants SET revoked_at=?, revoked_by=? WHERE id=? AND revoked_at IS NULL", (iso(), by, gid)) is not None)

    # ------------------------------------------------------------------ inbox
    def notify(self, uid: str, kind: str, text: str) -> None:
        self.x("INSERT INTO inbox(user,at,kind,text) VALUES(?,?,?,?)", (uid, iso(), kind, text))

    def inbox(self, uid: str) -> List[Dict]:
        return self.q("SELECT * FROM inbox WHERE user=? ORDER BY id DESC LIMIT 100", (uid,))

    # ------------------------------------------------------------------ personal settings
    def prefs(self, uid: str) -> Dict:
        r = self.one("SELECT json FROM prefs WHERE user=?", (uid,))
        return json.loads(r["json"]) if r else {}

    def set_prefs(self, uid: str, data: Dict) -> None:
        self.x("INSERT INTO prefs(user,json,at) VALUES(?,?,?) ON CONFLICT(user) DO UPDATE SET json=excluded.json, at=excluded.at",
               (uid, json.dumps(data, sort_keys=True), iso()))


def until_from_hours(hours: float) -> str:
    return iso(now() + timedelta(hours=float(hours)))
