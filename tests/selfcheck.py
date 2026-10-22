"""Self-check: login store, model list, chat (buffered + stream)."""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("FREEPI2API_URL", "http://127.0.0.1:61040")


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(extra)) if extra else ""))
    return cond


def main():
    ok = True
    from auth import status
    st = status()
    ok &= check("auth status runs", isinstance(st, dict))
    print("     store:", st.get("store"))

    base = BASE
    try:
        with urllib.request.urlopen(base + "/health", timeout=10) as r:
            ok &= check("healthz", json.loads(r.read()).get("ok") is True)
    except Exception as e:
        print("FAIL healthz", e)
        return 1

    try:
        with urllib.request.urlopen(base + "/v1/models", timeout=30) as r:
            models = json.loads(r.read()).get("data", [])
        ok &= check("models non-empty", len(models) > 0, f"{len(models)} models")
        print("     " + ", ".join(m["id"] for m in models[:8]))
    except Exception as e:
        ok &= False
        print("FAIL models", e)

    body = json.dumps({"model": "deepseek-v4-flash", "max_tokens": 64,
                       "messages": [{"role": "user", "content": "Say exactly: PONG"}]}).encode()
    have_tok = False
    try:
        import auth as _auth
        have_tok = bool(_auth.token())
    except Exception:
        have_tok = False
    if not have_tok:
        print("SKIP chat (no JWT signed in — run `py main.py --login` first)")
    else:
        try:
            req = urllib.request.Request(base + "/v1/chat/completions", data=body,
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            text = d["choices"][0]["message"].get("content") or ""
            ok &= check("buffered chat", bool(text.strip()), text[:60])
            ok &= check("usage present", "usage" in d, d.get("usage"))
        except urllib.error.HTTPError as e:
            ok &= False
            print("FAIL chat", e.code, e.read().decode()[:300])
        except Exception as e:
            ok &= False
            print("FAIL chat", e)

    sbody = json.dumps({"model": "deepseek-v4-flash", "max_tokens": 64, "stream": True,
                        "messages": [{"role": "user", "content": "Say exactly: PONG"}]}).encode()
    if not have_tok:
        print("SKIP stream (no JWT)")
    else:
        try:
            req = urllib.request.Request(base + "/v1/chat/completions", data=sbody,
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read().decode()
            has_delta = '"delta"' in raw or "data:" in raw
            ok &= check("stream chat", has_delta, raw[:60].replace("\n", " "))
        except Exception as e:
            ok &= False
            print("FAIL stream", e)

    print("\nALL PASS" if ok else "\nFAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())