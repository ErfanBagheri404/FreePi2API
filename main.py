"""FreePi2API — CLI entry point with interactive menu."""
import argparse
import json
import urllib.error
import urllib.request

from version import version


def banner(cfg):
    print()
    print("  FreePi2API " + version() + "  —  OpenAI-compatible proxy for free-pi")
    print(f"  upstream : {cfg.base_url}")
    print(f"  listen   : http://{cfg.bind}:{cfg.port}")
    print()


def show_status():
    from auth import status
    st = status()
    print()
    if not st.get("loggedIn"):
        print("  x not signed in — run option 5")
    else:
        me = st.get("me") or {}
        print(f"  ok signed in   user={me.get('user_id')} handle={me.get('handle')}")
        print(f"     free remaining today: {me.get('remaining_usd_today')} / cap {me.get('cap_usd_today')} USD")
        if me.get("credit_usd") is not None:
            print(f"     credit balance     : {me.get('credit_usd')} USD")
    print(f"     store          : {st.get('store')}")
    print()


def list_models(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=30) as r:
            data = json.loads(r.read())
        models = data.get("data", [])
        print(f"\n  {len(models)} models:")
        for m in models:
            print(f"    {m['id']}")
        print()
    except Exception as e:
        print(f"\n  x failed: {e}\n")


def test_chat(port):
    model = input("  model [deepseek-v4-flash]: ").strip() or "deepseek-v4-flash"
    msg = input("  message [Hello]: ").strip() or "Hello"
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": msg}],
                       "max_tokens": 200}).encode()
    print()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                     data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        content = d.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  ok {content}\n")
    except urllib.error.HTTPError as e:
        print(f"  x {e.code}: {e.read().decode('utf-8', 'replace')[:300]}\n")
    except Exception as e:
        print(f"  x {e}\n")


def run_menu(cfg):
    while True:
        print()
        print("  1. Status     2. Start server     3. List models")
        print("  4. Test chat  5. Sign in          6. Quit")
        print()
        choice = input("  > ").strip()
        if choice == "1":
            show_status()
        elif choice == "2":
            banner(cfg)
            from server import serve
            serve(cfg)
        elif choice == "3":
            list_models(cfg.port)
        elif choice == "4":
            test_chat(cfg.port)
        elif choice == "5":
            from auth import login
            try:
                login(print)
            except Exception as e:
                print(f"  x {e}")
        elif choice == "6":
            print("\n  bye\n")
            break
        else:
            print("\n  invalid choice\n")


def main():
    p = argparse.ArgumentParser(description="OpenAI-compatible proxy for free-pi")
    p.add_argument("--port", type=int, default=61040)
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--api-key", default=None, help="require this key on /v1/ routes")
    p.add_argument("--login", action="store_true", help="run GitHub device login then exit")
    p.add_argument("--no-menu", action="store_true", help="start the server directly")
    p.add_argument("--version", action="version", version=f"FreePi2API {version()}")
    args = p.parse_args()

    if args.login:
        from auth import login
        login(print)
        return

    from config import load_config
    cfg = load_config(args)
    if not args.no_menu:
        run_menu(cfg)
        return
    banner(cfg)
    from server import serve
    serve(cfg)


if __name__ == "__main__":
    main()
