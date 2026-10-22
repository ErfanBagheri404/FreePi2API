"""Upstream client for api.freepi.ai."""
import http.client
import json
import threading
import time
import urllib.parse

UA = "free-pi-cli/0.4.10"
TIMEOUT = 300
_local = threading.local()


class Upstream:
    def __init__(self, cfg):
        self.cfg = cfg
        self.host = urllib.parse.urlparse(cfg.base_url).netloc

    def _headers(self, token, extra=None, stream=False):
        h = {
            "user-agent": UA,
            "accept": "text/event-stream" if stream else "application/json",
            "accept-encoding": "identity",
            "x-session-id": self.cfg.session_id,
            "x-client-version": self.cfg.client_version,
        }
        if token:
            h["authorization"] = "Bearer " + token
        if extra:
            h.update(extra)
        return h

    def _conn(self):
        c = getattr(_local, "conn", None)
        if c is None:
            c = http.client.HTTPSConnection(self.host, timeout=TIMEOUT)
            _local.conn = c
        return c

    def _drop(self):
        c = getattr(_local, "conn", None)
        _local.conn = None
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def request(self, method, path, body=None, token=None, extra_headers=None, retries=2):
        hdrs = self._headers(token, extra_headers)
        if body is not None:
            hdrs["content-type"] = "application/json"
        last = None
        for attempt in range(retries + 1):
            try:
                c = self._conn()
                c.request(method, path, body=body, headers=hdrs)
                r = c.getresponse()
                data = r.read()
                if r.status >= 500 or r.status == 429:
                    last = (r.status, dict(r.getheaders()), data)
                    if attempt < retries:
                        self._drop()
                        time.sleep(0.8 * (attempt + 1))
                        continue
                    return last
                return r.status, dict(r.getheaders()), data
            except (http.client.HTTPException, OSError) as e:
                self._drop()
                last = (502, {}, json.dumps({"error": {"message": str(e)}}).encode())
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))
        return last

    def stream(self, path, body, token, extra_headers=None):
        hdrs = self._headers(token, extra_headers, stream=True)
        hdrs["content-type"] = "application/json"
        c = http.client.HTTPSConnection(self.host, timeout=TIMEOUT)
        c.request("POST", path, body=body, headers=hdrs)
        return c, c.getresponse()
