"""python -m prw_server [--config access.yaml] [--host 127.0.0.1] [--port 8795]
python -m prw_server user add <id> [--name N] [--roles admin,developer]   (asks for a password; never echoed)
python -m prw_server user password <id>
python -m prw_server audit verify
python -m prw_server sign-rule <name>    (signs a merge rule in the team settings with PRW_POLICY_SIGNING_KEY)"""
import argparse
import getpass
import os
import sys

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="prw_server")
    ap.add_argument("--config", default=os.path.join(HERE, "access.yaml"))
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=8795)
    u = sub.add_parser("user")
    u.add_argument("action", choices=["add", "password", "disable", "enable"])
    u.add_argument("id")
    u.add_argument("--name", default="")
    u.add_argument("--roles", default="")
    a = sub.add_parser("audit")
    a.add_argument("action", choices=["verify", "tail"])
    s = sub.add_parser("sign-rule")
    s.add_argument("name")
    args = ap.parse_args(argv)
    cmd = args.cmd or "run"

    if cmd == "run":
        import uvicorn
        from .app import build_app
        app = build_app(args.config)
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8795)
        print(f"PR World server: http://{host}:{port}  (Ctrl+C to stop)")
        uvicorn.run(app, host=host, port=port, log_level="warning")
        return 0

    from .app import Server
    srv = Server(args.config)
    st = srv.store
    if cmd == "user":
        if args.action == "add":
            if st.user(args.id):
                print("This user exists.")
                return 1
            st.upsert_user(args.id, args.name or args.id, "", "local")
            st.set_roles(args.id, [x for x in args.roles.split(",") if x], "admin")
            st.audit("cli", "user_created", args.id, {"roles": args.roles})
        if args.action in ("add", "password"):
            from .auth import hash_password
            pw = getpass.getpass("New password (10+ characters): ")
            if pw != getpass.getpass("Again: "):
                print("The two passwords differ.")
                return 1
            st.set_password(args.id, hash_password(pw))
            st.audit("cli", "password_set", args.id)
            print("Saved.")
        if args.action in ("disable", "enable"):
            st.x("UPDATE users SET disabled=? WHERE id=?", (int(args.action == "disable"), args.id))
            st.audit("cli", "user_" + args.action + "d", args.id)
            print("Saved.")
        return 0
    if cmd == "audit":
        if args.action == "verify":
            v = st.verify_audit()
            print(("Audit log intact: " if v["ok"] else "AUDIT LOG CHANGED at row %s: " % v.get("broken_at")) + f"{v['rows']} rows")
            return 0 if v["ok"] else 2
        for row in reversed(st.audit_rows(40)):
            print(row["at"], row["user"], row["action"], row["target"], row["detail"])
        return 0
    if cmd == "sign-rule":
        from .policy import sign_rule
        key = os.environ.get("PRW_POLICY_SIGNING_KEY")
        if not key:
            print("Set PRW_POLICY_SIGNING_KEY first (the server uses the same key to check the rule).")
            return 1
        if not srv.settings_path or not os.path.exists(srv.settings_path):
            print("No team settings file (settings: in access.yaml).")
            return 1
        with open(srv.settings_path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        rules = (raw.get("merge_policy") or {}).get("rules") or []
        rule = next((x for x in rules if x.get("name") == args.name), None)
        if not rule:
            print("No merge rule with this name.")
            return 1
        if not rule.get("signed_by") or not rule.get("signed_on"):
            print("Fill signed_by (the person who signs) and signed_on first.")
            return 1
        rule["signature"] = sign_rule(rule, key)
        with open(srv.settings_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(raw, fh, sort_keys=False)
        st.audit("cli", "merge_rule_signed", args.name, {"signed_by": rule["signed_by"]})
        print(f"Signed rule '{args.name}' for {rule['signed_by']}.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
