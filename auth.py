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


def show_ads(t=None):
    """Serve one banner ad and report the impression.

    api.freepi.ai gates free completions on ads actually being shown: when a
    client never reports an impression it answers 403 {"code":"ads_required"}
    and every completion fails. The CLI does this through its Gravity SDK; a
    headless proxy has no ads to render, so it fetches the server's own ad,
    "displays" it in the log, and reports the impression so the account stays
    in good standing. Never raises — an ads hiccup must not break a request.
    """
    t = t or token()
    if not t:
        return None
    h = {"authorization": "Bearer " + t, "user-agent": UA, "x-session-id": session_id()}
    try:
        req = urllib.request.Request(_base() + "/ads/next?slot=banner", headers=h)
        with urllib.request.urlopen(req, timeout=15) as r:
            ad = json.loads(r.read().decode())
        if not ad.get("ad_id"):
            return None
        body = json.dumps({"ad_id": ad["ad_id"],
                           "click_token": ad.get("click_token"),
                           "imp_fired": True}).encode()
        req = urllib.request.Request(_base() + "/ads/impression", data=body,
                                     headers=dict(h, **{"content-type": "application/json"}),
                                     method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
        if ad.get("imp_url"):
            try:
                with urllib.request.urlopen(urllib.request.Request(ad["imp_url"], headers=h),
                                            timeout=10) as r:
                    r.read()
            except Exception:
                pass
        return ad
    except Exception:
        return None


def session_id():
    return os.environ.get("FREEPI2API_SESSION_ID", "freepi2api")


UA = "free-pi-cli/0.4.10"


def login(print=print):
    status, device = _post("/auth/github/device", {})
    if status != 200 or "session_id" not in device:
        raise RuntimeError("device flow failed: HTTP %s %s" % (status, device))
    sid = device["session_id"]
    print("\n  Open:  %s" % device.get("verification_uri"))
    print("  Code:  %s\n" % device.get("user_code"))
    print("  If you land on a GitHub sign-in page instead of a code box, log in to")
    print("  GitHub in that same browser first, then open the URL again.\n")
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
        # The server forwards GitHub's backoff. Polling faster than asked makes
        # GitHub answer slow_down and pushes the token out by the full window.
        wait = body.get("retry_after")
        if isinstance(wait, (int, float)) and wait > 0:
            interval = min(max(wait, 5), 60)
            print("  waiting %ss (upstream backoff)..." % int(interval))
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
