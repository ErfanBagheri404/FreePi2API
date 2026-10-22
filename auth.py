"""Auth for api.freepi.ai — GitHub device flow.

The server requires consent to be recorded for the session BEFORE a token
will be issued (it answers 403 {"code":"consent_required"} otherwise), so
login() submits consent, then polls /auth/token until the user finishes the
GitHub device page. The JWT is stored in %APPDATA%/FreePi2API/auth.json.

Environment overrides: FREEPI2API_BASE_URL, FREEPI2API_SESSION_ID.
"""
import json
import os
import time
import urllib.error
import urllib.request

CONSENT_VERSION = "0.4.10"
STORE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "FreePi2API", "auth.json")
# Fallback bare-token file (written by the background poller during login)
TOKEN_FALLBACK = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Temp", "freepi_token.txt")


def _base():
    return os.environ.get("FREEPI2API_BASE_URL", "https://api.freepi.ai").rstrip("/")


def _post(path, body):
    req = urllib.request.Request(_base() + path, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except ValueError:
            return e.code, {}


def load():
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(tok):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(tok, f)


def token():
    d = load()
    if d.get("token"):
        return d["token"]
    # Fallback: bare JWT written by the background login poller
    try:
        with open(TOKEN_FALLBACK, "r", encoding="utf-8") as f:
            t = f.read().strip()
            return t or None
    except OSError:
        return None


def login(print=print):
    status, device = _post("/auth/github/device", {})
    if status != 200 or "session_id" not in device:
        raise RuntimeError("device flow failed: HTTP %s %s" % (status, device))
    sid = device["session_id"]
    print("\nOpen %s and enter code: %s\n" % (device.get("verification_uri"), device.get("user_code")))
    _post("/auth/consent", {"session_id": sid, "consent_version": CONSENT_VERSION})
    interval = device.get("interval") or 5
    deadline = time.time() + 900
    while time.time() < deadline:
        status, body = _post("/auth/token", {"session_id": sid})
        if status == 200 and body.get("token"):
            save(body)
            print("signed in -> %s" % STORE)
            return body["token"]
        if status == 403 and body.get("code") == "consent_required":
            raise RuntimeError("server did not record consent; rerun login")
        time.sleep(interval)
    raise RuntimeError("login timed out")


def me():
    """GET /me with the stored JWT -> (status, dict) or (None, None)."""
    t = token()
    if not t:
        return None, None
    req = urllib.request.Request(_base() + "/me", headers={"authorization": "Bearer " + t})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except ValueError:
            return e.code, None


def status():
    t = token()
    if not t:
        return {"loggedIn": False, "store": STORE}
    st, body = me()
    return {"loggedIn": bool(st == 200), "tokenOk": st == 200, "me": body, "store": STORE,
            "error": (body or {}).get("message")}
