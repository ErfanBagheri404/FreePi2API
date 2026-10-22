"""FreePi2API — OpenAI-compatible proxy for the free-pi backend."""
import os
import sys

VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
_FALLBACK = "0.1.0"


def version():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for path in (VERSION_FILE, os.path.join(base, "VERSION")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                v = f.read().strip()
            if v:
                return v
        except OSError:
            continue
    return _FALLBACK
