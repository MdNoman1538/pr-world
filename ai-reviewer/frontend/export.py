#!/usr/bin/env python3
"""Make one self-contained, read-only dashboard HTML from a run's bundle.json (no server needed).

    python frontend/export.py backend/runs/<run_id>            → backend/runs/<run_id>/dashboard.html
    python frontend/export.py path/to/bundle.json --out x.html

Reads only the bundle file the backend wrote; imports no backend code.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()


def export(bundle_path: str, out_path: str) -> str:
    with open(bundle_path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != "ai-reviewer-bundle/1":
        raise SystemExit(f"{bundle_path} is not an ai-reviewer bundle")
    html = _read("index.html")
    html = html.replace('<link rel="stylesheet" href="style.css">', "").replace(
        "<!--INLINE_STYLE-->", "<style>" + _read("style.css") + "</style>")
    html = html.replace('<script src="config.js"></script>', "")
    html = html.replace('<script src="d3.min.js"></script>', "<script>" + _read("d3.min.js").replace("</script", "<\\/script") + "</script>")
    html = html.replace('<script src="app.js"></script>', "<script>" + _read("app.js").replace("</script", "<\\/script") + "</script>")
    html = html.replace("<!--BUNDLE-->", "<script>window.__BUNDLE__ = " + json.dumps(data).replace("</", "<\\/") + ";</script>")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="run folder or bundle.json")
    p.add_argument("--out")
    a = p.parse_args()
    bundle = os.path.join(a.source, "bundle.json") if os.path.isdir(a.source) else a.source
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(bundle)), "dashboard.html")
    print("[frontend] wrote", export(bundle, out))


if __name__ == "__main__":
    main()
