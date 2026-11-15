"""Trust level, sign-off per module (E8) and the signed merge policy (F1). All rules are fixed code."""
import hashlib
import hmac
import json
import os
from typing import Dict, List, Optional

SEV_RANK = {"none": -1, "Nit": 0, "ShouldFix": 1, "Blocker": 2}
TIER_RANK = {"low": 0, "medium": 1, "high": 2}
TRUST_RANK = {"low": 0, "medium": 1, "high": 2}


def trust_level(s: Optional[Dict], label: Optional[str] = None, not_checked: Optional[List[str]] = None) -> Optional[Dict]:
    """Same rule as the viewer (model.js trustLevel). Not checked areas cap the level at Medium."""
    if not s or not s.get("n"):
        return None
    n, v, c, lo, hi = s["n"], s.get("verified", 0), s.get("contradicted", 0), s.get("lo"), s.get("hi")
    if c > 0:
        return {"key": "low", "why": f"{c} changed method(s) contradicted by a failing test or a Critical finding"}
    if label == "fix":
        return {"key": "low", "why": "the PR is labelled Fix before merge"}
    if hi is not None and hi < 0.5:
        return {"key": "low", "why": f"only {v} of {n} changed methods are verified; even the top of the 95% range is below one half"}
    if v >= 0.75 * n and lo is not None and lo >= 0.5 and (not label or label == "ready"):   # High: at least 3 in 4 verified
        if not_checked:
            return {"key": "medium", "why": f"{v} of {n} changed methods are verified, but these areas were not checked: " + ", ".join(not_checked)}
        return {"key": "high", "why": f"{v} of {n} changed methods are verified by passing tests and nothing contradicts them"}
    if v == n:
        return {"key": "medium", "why": "every change is verified, but there is too little evidence or open items remain"}
    return {"key": "medium", "why": f"{v} of {n} changed methods are verified; {n - v} have no test evidence yet"}


def pr_trust(notes: Optional[Dict], review: Optional[Dict]) -> Optional[Dict]:
    s = ((notes or {}).get("roll") or {}).get("pr", {}).get("changed")
    label = ((notes or {}).get("verdict") or {}).get("label")
    nc = [a["area"] for a in (review or {}).get("areas", []) if a.get("status") == "not_checked"]
    return trust_level(s, label, nc)


# ------------------------------------------------------------------ sign-off per module
def parts(diff: Optional[Dict]) -> List[str]:
    """Modules that changed in this PR: each needs a signature from someone with Sign access to it."""
    return sorted(m for m, st in ((diff or {}).get("modules") or {}).items() if st == "changed")


def sign_mac(secret: bytes, pr: str, module: str, head: str, user: str, at: str, note: str) -> str:
    msg = json.dumps([pr, module, head, user, at, note], separators=(",", ":")).encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def signoff_status(pr: str, head: str, mods: List[str], sigs: List[Dict], secret: bytes) -> Dict:
    out, done = [], True
    for m in mods:
        cur = [s for s in sigs if s["module"] == m and s["head"] == head and not s.get("withdrawn_at")]
        valid = [s for s in cur if hmac.compare_digest(s["mac"], sign_mac(secret, pr, m, head, s["user"], s["at"], s.get("note") or ""))]
        old = [s for s in sigs if s["module"] == m and s["head"] != head and not s.get("withdrawn_at")]
        if not valid:
            done = False
        out.append({"module": m, "signed": bool(valid), "by": [{"user": s["user"], "at": s["at"], "note": s.get("note") or ""} for s in valid],
                    "tampered": len(cur) - len(valid), "older_commits": len(old)})
    return {"parts": out, "all_signed": done and bool(mods), "head": head}


# ------------------------------------------------------------------ signed merge policy (Option A)
def rule_payload(rule: Dict) -> bytes:
    body = {k: v for k, v in rule.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def sign_rule(rule: Dict, key: str) -> str:
    return hmac.new(key.encode(), rule_payload(rule), hashlib.sha256).hexdigest()


def evaluate_merge(rules: List[Dict], protected: List[str], review: Optional[Dict], notes: Optional[Dict], diff: Optional[Dict],
                   key: Optional[str] = None) -> Dict:
    """Which signed rule (if any) lets this PR merge without a person signing each module. Never for protected areas,
    never with a not-checked area, never when the reviewer's gate is not ready."""
    key = key if key is not None else os.environ.get("PRW_POLICY_SIGNING_KEY", "")
    review, notes, diff = review or {}, notes or {}, diff or {}
    t = review.get("tier")
    tier = (t.get("tier") if isinstance(t, dict) else t) or "high"
    findings = review.get("findings", [])
    worst = max([SEV_RANK.get(f.get("severity"), 2) for f in findings] or [-1])
    trust = pr_trust(notes, review)
    touched = set((diff.get("modules") or {}).keys())
    prot = sorted(touched & set(protected or []))
    nc = [a["area"] for a in review.get("areas", []) if a.get("status") == "not_checked"]
    checks = []
    for r in rules or []:
        why = []
        if not key:
            why.append("no policy signing key on this server (PRW_POLICY_SIGNING_KEY)")
        elif not r.get("signature") or not hmac.compare_digest(r["signature"], sign_rule(r, key)):
            why.append("the rule's signature does not match (changed after signing, or never signed)")
        if prot:
            why.append("touches protected area(s): " + ", ".join(prot))
        if nc:
            why.append("not checked: " + ", ".join(nc))
        if TIER_RANK.get(tier, 2) > TIER_RANK[r["max_tier"]]:
            why.append(f"risk tier {tier} is above {r['max_tier']}")
        if worst > SEV_RANK.get(r.get("max_severity", "none"), -1):
            why.append("has findings above " + r.get("max_severity", "none"))
        if r.get("min_trust"):
            if not trust or TRUST_RANK[trust["key"]] < TRUST_RANK[r["min_trust"]]:
                why.append(f"trust is {trust['key'] if trust else 'unknown'}, needs {r['min_trust']}")
        if review.get("decision") not in ("READY_FOR_SIGNOFF",):
            why.append("the reviewer's gate is not ready")
        checks.append({"rule": r["name"], "signed_by": r.get("signed_by"), "signed_on": r.get("signed_on"), "ok": not why, "why_not": why})
    allowed = next((c for c in checks if c["ok"]), None)
    return {"allowed": bool(allowed), "rule": allowed, "checks": checks, "tier": tier, "trust": trust,
            "protected_touched": prot, "not_checked": nc}
