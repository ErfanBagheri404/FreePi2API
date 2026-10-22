"""HTTP server: OpenAI-compatible /v1/chat/completions proxy."""
import http.server
import json
import os
import threading
import time
import urllib.parse

from auth import token
from client import Upstream
from config import load_config

# Used when both the on-disk cache and the upstream catalog are unavailable, so
# GET /v1/models always answers 200 instead of failing a client's startup.
FALLBACK_MODELS = [
    "deepseek-v4-flash", "deepseek-v4.1-flash", "deepseek-v4-pro",
    "claude-haiku-5.5", "claude-sonnet-5.5",
    "gemini-4-argon", "gemini-4-argon-flex",
    "glm-5.3-flash", "gpt-6.1-sol", "gpt-6.1-sol-flex", "gpt-6-luna", "gpt-6-luna-flex",
    "gpt-oss-120b-speed", "laguna-s-2.1", "mimo-v2.6-flash",
    "muse-spark-1.3-contributor", "muse-spark-open",
    "qwen3.5-35b-darkbloom", "solar-pro-4",
]

CATALOG_CACHE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "FreePi2API", "models.json")


def _load_catalog():
    try:
        with open(CATALOG_CACHE, "r", encoding="utf-8") as f:
            return json.load(f) or None
    except (OSError, ValueError):
        return None


def _save_catalog(body):
    try:
        os.makedirs(os.path.dirname(CATALOG_CACHE), exist_ok=True)
        with open(CATALOG_CACHE, "w", encoding="utf-8") as f:
            json.dump(body, f)
    except OSError:
        pass


def _json(w, status, obj):
    data = json.dumps(obj).encode()
    w.send_response(status)
    w.send_header("content-type", "application/json")
    w.send_header("content-length", str(len(data)))
    w.end_headers()
    w.wfile.write(data)


def _cors(w):
    w.send_header("access-control-allow-origin", "*")
    w.send_header("access-control-allow-headers", "authorization, content-type")
    w.send_header("access-control-allow-methods", "GET, POST, OPTIONS")


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cfg(self):
        return self.server.cfg

    def _authorized(self):
        want = self._cfg().api_key
        if not want:
            return True
        got = self.headers.get("authorization", "").replace("Bearer ", "").strip()
        return got == want

    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/health", "/healthz", "/"):
            _json(self, 200, {"ok": True})
            return
        if not self._authorized():
            _json(self, 401, {"error": {"message": "unauthorized"}})
            return
        if u.path == "/v1/models":
            self._models()
            return
        _json(self, 404, {"error": {"message": "not found"}})

    def _models(self):
        """Always 200: upstream catalog -> on-disk cache -> static fallback."""
        body = None
        st, _, data = self.server.upstream.request("GET", "/client-version", token=token())
        if st == 200:
            try:
                body = json.loads(data or b"{}")
                _save_catalog(body)
            except ValueError:
                body = None
        if not body:
            body = _load_catalog()
        if not body:
            body = {"models": [{"id": m} for m in FALLBACK_MODELS]}
        models = body.get("models") or []
        if not models:
            mid = body.get("model") or FALLBACK_MODELS[0]
            models = [{"id": mid, "name": mid}]
        _json(self, 200, {"object": "list",
                          "data": [{"id": m.get("id"), "object": "model", "owned_by": "freepi"}
                                   for m in models if m.get("id")]})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path not in ("/v1/chat/completions", "/chat/completions"):
            _json(self, 404, {"error": {"message": "not found"}})
            return
        if not self._authorized():
            _json(self, 401, {"error": {"message": "unauthorized"}})
            return
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            _json(self, 400, {"error": {"message": "invalid json"}})
            return
        stream = bool(body.get("stream"))
        mdl = body.get("model")
        if not mdl:
            body["model"] = "deepseek-v4-flash"
        elif isinstance(mdl, str) and "/" in mdl:
            # routers often prefix with freepi/<model>; upstream wants the raw id
            body["model"] = mdl.split("/", 1)[1]
        t = token()
        up = self.server.upstream
        path = "/v1/chat/completions"
        data = json.dumps(body).encode()
        extra = {"x-session-id": self.server.cfg.session_id,
                 "x-client-version": self.server.cfg.client_version}
        if stream:
            conn, resp = up.stream(path, data, t, extra_headers=extra)
            self.send_response(resp.status)
            self.send_header("content-type", resp.getheader("content-type", "text/event-stream"))
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            finally:
                resp.close()
                conn.close()
            return
        st, headers, data = up.request("POST", path, body=data, token=t, extra_headers=extra)
        self.send_response(st)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


def serve(cfg):
    server = http.server.ThreadingHTTPServer((cfg.bind, cfg.port), Handler)
    server.cfg = cfg
    server.upstream = Upstream(cfg)
    print("FreePi2API listening on http://%s:%s" % (cfg.bind, cfg.port))
    server.serve_forever()
