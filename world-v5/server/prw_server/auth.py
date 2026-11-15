"""Login: company single sign-on (OIDC: Azure AD / Entra ID, Okta, Keycloak, Google) and local users for small teams.

Passwords: scrypt (salted). Company groups map to roles on every login, so removing someone from a group in the
company directory removes the role here at their next login. SAML-only directories: use the directory's OIDC app
(Azure AD and Okta both offer one); SAML itself is not implemented."""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Dict, List, Optional, Tuple

import requests

SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def hash_password(pw: str) -> str:
    if len(pw) < 10:
        raise ValueError("Use at least 10 characters.")
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: Optional[str]) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        hashlib.scrypt(b"x", salt=b"0" * 16, dklen=32, **SCRYPT)   # same time whether or not the user exists
        return False
    _, n, r, p, salt, h = stored.split("$")
    got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), dklen=32, n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(got.hex(), h)


class Throttle:
    """Max 5 failed logins per user name and per address in 10 minutes."""

    def __init__(self, limit: int = 5, window: int = 600):
        self.limit, self.window = limit, window
        self.fails: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def _recent(self, key: str) -> List[float]:
        t = time.time()
        return [x for x in self.fails.get(key, []) if t - x < self.window]

    def allowed(self, *keys: str) -> bool:
        with self.lock:
            return all(len(self._recent(k)) < self.limit for k in keys)

    def fail(self, *keys: str) -> None:
        with self.lock:
            for k in keys:
                self.fails[k] = self._recent(k) + [time.time()]

    def ok(self, *keys: str) -> None:
        with self.lock:
            for k in keys:
                self.fails.pop(k, None)


class OIDC:
    """Authorization code flow with PKCE; the ID token is checked against the provider's keys (JWKS)."""

    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self.issuer = cfg["issuer"].rstrip("/")
        self.client_id = cfg["client_id"]
        self.secret = os.environ.get(cfg.get("client_secret_env") or "PRW_OIDC_CLIENT_SECRET", "")
        self.redirect_uri = cfg["redirect_uri"]
        self.scopes = cfg.get("scopes", "openid profile email")
        self.groups_claim = cfg.get("groups_claim", "groups")
        self.group_roles: Dict[str, List[str]] = {k: (v if isinstance(v, list) else [v]) for k, v in (cfg.get("group_roles") or {}).items()}
        self._meta = None
        self._jwks = None

    def meta(self) -> Dict:
        if self._meta is None:
            r = requests.get(self.issuer + "/.well-known/openid-configuration", timeout=10)
            r.raise_for_status()
            self._meta = r.json()
        return self._meta

    def start(self) -> Tuple[str, Dict]:
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        q = {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri, "scope": self.scopes,
             "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
        url = self.meta()["authorization_endpoint"] + "?" + requests.compat.urlencode(q)
        return url, {"state": state, "nonce": nonce, "verifier": verifier, "t": time.time()}

    def finish(self, code: str, state: str, saved: Dict) -> Dict:
        import jwt
        if not saved or not hmac.compare_digest(state or "", saved.get("state", "")) or time.time() - saved.get("t", 0) > 600:
            raise PermissionError("The sign-in took too long or did not start here. Try again.")
        body = {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
                "client_id": self.client_id, "code_verifier": saved["verifier"]}
        if self.secret:
            body["client_secret"] = self.secret
        r = requests.post(self.meta()["token_endpoint"], data=body, timeout=15)
        if r.status_code != 200:
            raise PermissionError(f"The company sign-in refused the code ({r.status_code}).")
        tok = r.json().get("id_token")
        if self._jwks is None:
            self._jwks = jwt.PyJWKClient(self.meta()["jwks_uri"])
        key = self._jwks.get_signing_key_from_jwt(tok)
        claims = jwt.decode(tok, key.key, algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"],
                            audience=self.client_id, issuer=self.meta().get("issuer", self.issuer), leeway=60)
        if not hmac.compare_digest(claims.get("nonce", ""), saved["nonce"]):
            raise PermissionError("Sign-in check failed (nonce).")
        return claims

    def roles_for(self, claims: Dict) -> List[str]:
        groups = claims.get(self.groups_claim) or []
        if isinstance(groups, str):
            groups = [groups]
        out = []
        for g in groups:
            out += self.group_roles.get(g, [])
        return sorted(set(out))
