#!/usr/bin/env python3
"""Calibration check (D5): does the confidence number match what really happened?

Known outcome per PR = whether the Bug planter put a defect into it (plan/answer_key.yaml; the clean PRs have none).
Reads  viewer/data/scorecard.json, notes/, reviews/      Writes viewer/data/calibration.json
Honest limits: 12 PRs are far too few to calibrate anything; this shows the method and the first points.
"Correct" means only "no planted defect": the Builder can add defects of its own that nobody planted."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import VIEW, say, write_json  # noqa: E402
from pr_notes import trust_level  # noqa: E402  (same fixed rule as the viewer)

BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001)]


def main() -> int:
    sc_p = VIEW / "scorecard.json"
    if not sc_p.exists():
        say("No scorecard yet: run the world first.")
        return 1
    sc = json.loads(sc_p.read_text())
    bugged = {b["pr"] for b in sc.get("bugs", []) if b.get("applied")}
    rows = []
    for p in sc.get("prs", []):
        n_p = VIEW / "notes" / f"{p['id']}.json"
        if not n_p.exists():
            continue
        n = json.loads(n_p.read_text())
        s = (n.get("roll", {}).get("pr") or {}).get("changed") or {}
        rv_p = VIEW / "reviews" / f"{p['id']}.json"
        rv = json.loads(rv_p.read_text()) if rv_p.exists() else {}
        rc = rv.get("requirement_check") or {}
        trust = (n.get("trust") or trust_level(s, (n.get("verdict") or {}).get("label"),
                                                [a["area"] for a in rv.get("areas") or [] if a.get("status") == "not_checked"]) or {}).get("level")
        rows.append({"pr": p["id"], "conf": s.get("conf"), "lo": s.get("lo"), "hi": s.get("hi"), "trust": trust,
                     "label": (n.get("verdict") or {}).get("label"), "decision": rv.get("decision"),
                     "requirement": (rc.get("counts") if rc.get("ran") else None),
                     "correct": 0 if p["id"] in bugged else 1, "planted": p["id"] in bugged})
    scored = [r for r in rows if r["conf"] is not None]
    brier = round(sum((r["conf"] - r["correct"]) ** 2 for r in scored) / len(scored), 3) if scored else None
    bins = []
    for lo, hi in BINS:
        inb = [r for r in scored if lo <= r["conf"] < hi]
        bins.append({"from": lo, "to": min(hi, 1.0), "n": len(inb),
                     "mean_conf": round(sum(r["conf"] for r in inb) / len(inb), 3) if inb else None,
                     "share_correct": round(sum(r["correct"] for r in inb) / len(inb), 3) if inb else None})
    by = {}
    for key in ("trust", "label"):
        g = {}
        for r in rows:
            k = r[key] or "none"
            g.setdefault(k, {"n": 0, "correct": 0})
            g[k]["n"] += 1
            g[k]["correct"] += r["correct"]
        by[key] = g
    # requirement check against outcomes: did a contradicted / missing item point at the planted PRs?
    req = [r for r in rows if r["requirement"]]
    req_flag = {"pr_with_contradicted_or_missing": sum(1 for r in req if (r["requirement"]["contradicted"] or r["requirement"]["missing"])),
                "of_which_planted": sum(1 for r in req if (r["requirement"]["contradicted"] or r["requirement"]["missing"]) and r["planted"]),
                "planted_with_check": sum(1 for r in req if r["planted"]), "clean_with_check": sum(1 for r in req if not r["planted"])}
    out = {"rows": rows, "brier": brier, "bins": bins, "by": by, "requirement": req_flag,
           "note": ("Outcome = no planted defect (answer key). Confidence is read as the chance the PR is correct. "
                    f"{len(scored)} PRs: far too few to calibrate; the points show the method, not a result. "
                    "Brier score: 0 is perfect, 0.25 is what always saying 50% scores.")}
    write_json(VIEW / "calibration.json", out)
    say(f"Calibration: {len(scored)} PRs, Brier {brier}; written to viewer/data/calibration.json")
    for b in bins:
        if b["n"]:
            say(f"  confidence {b['from']:.1f}-{b['to']:.1f}: {b['n']} PR(s), mean {b['mean_conf']}, correct {b['share_correct']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
