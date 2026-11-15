# PR World server (v5)

Sends each person only what they may see. Replaces the plain file server (`viewer2/serve.py`) when more than one
person uses PR World.

## Start
```
cd ~/Projects/junction-ai-review/world-v5
./run_world.sh --view            # starts this server on http://127.0.0.1:8795 and opens it
```
The first time, `server/access.yaml` is copied from `access.example.yaml` (example Nordbank people, roles and owners).

## Two modes
- **switch** (this version, the default): no sign-in and no passwords. You start as `default_user`; Menu → **View as**
  switches to any person, and the app shows exactly what that person's access allows. Every switch is in the audit log.
  For one machine (it binds to 127.0.0.1): anyone who can reach it can be anyone.
- **login** (later): `mode: login` turns on passwords (`python -m prw_server user password <id>`) and company sign-in (oidc).

## Access levels (per module)
| Level | What the person can do |
|---|---|
| Overview | See the module block, its name and risk colour, that it changed or is affected, and how many findings it has. Nothing inside. |
| Read | Open classes, methods, code, flows and the full AI feedback. |
| Review | Read, plus mark findings right or wrong. |
| Sign | Review, plus sign the module's part of a PR. Module owners have Sign on their module. |

Access comes from roles (a role lists modules or `*`), personal grants (optional end date) and ownership.
Admins assign roles, grants and owners; being an admin does not by itself open any code.

## What a locked module looks like
Block, name (or "Restricted module N" when hidden by setting) and colour. No classes, code, routes, flows, finding text
or quoted code. Links into it end at the block. AI text is cleaned of its file paths and class names (the "safe
version"). Finding severity stays visible, so the risk is never hidden; only the details are.
Honest limit: a name that appears inside code you *can* read (for example a test that calls `LoanService`) stays
visible in that code.

## Other parts
- **Request access**: the person writes why; module owners (and admins) approve with an end date, or decline.
- **Emergency access**: Read for at most N hours (team setting), a reason is required, owners and admins are told at once
  (in the app, and on Slack when `PRW_SLACK_WEBHOOK_URL` is set).
- **Sign-off per module**: a PR is ready when every changed module is signed by someone with Sign access, for the
  current commit. Signatures are sealed with a server key, so a changed record shows as tampered. A PR labelled
  "Fix before merge" can only be signed with a written accepted risk.
- **Signed merge policy**: a rule in the team settings (`merge_policy.rules`) signed with
  `python -m prw_server sign-rule <name>` (key `PRW_POLICY_SIGNING_KEY`). Never for protected areas, never with a
  "Not checked" area, never when the reviewer's gate is not ready.
- **Audit log**: logins, opens, access changes, requests, emergency access, signatures, settings changes. Each row holds
  the hash of the row before it; `python -m prw_server audit verify` finds any edit.
- **Company sign-in** (mode: login): OIDC (Azure AD / Entra ID, Okta, Keycloak, Google). Groups in the token become roles at every
  login. SAML-only directories: use the directory's OIDC app; SAML itself is not built.

## Security notes
- Binds to 127.0.0.1 by default. Put it behind https (and set `cookie_secure: true`) before others use it.
- Session and signing keys come from `PRW_SESSION_SECRET` / `PRW_SIGNING_SECRET`, else from `.prw-secrets.json`
  (created once, mode 600). Never commit that file.
- Every POST needs the header `X-PRW: 1` (blocks cross-site form posts); strict Content-Security-Policy.
- Passwords: scrypt, at least 10 characters; 5 failed tries in 10 minutes pauses that name and address.
