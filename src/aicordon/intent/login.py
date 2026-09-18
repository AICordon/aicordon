"""`aicordon login` / `aicordon logout` — keep the Intent API key where the client finds it.

The flow is the one `huggingface-cli login` and `gh auth login` taught everyone:

    aicordon login                   prompts for the key without echoing it
    echo "$KEY" | aicordon login     takes it from a pipe (CI, scripts)
    aicordon login --status          which key is in use and where it came from
    aicordon logout                  removes the stored key

The key is checked against the API before it is saved — a typo is caught now, not on the first scan
an hour later. `--no-verify` skips that for offline setups.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from . import credentials as cred

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _verify(key: str, base_url: str | None) -> str | None:
    """None when the API accepts the key, otherwise why not."""
    from aicordon.core.engine import EngineUnavailable
    from .detector import Detector
    try:
        Detector(api_key=key, base_url=base_url, max_retries=1, timeout=20).assess("ok", doc_id="login")
    except EngineUnavailable as e:
        return e.reason
    return None


def login(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="aicordon login", description="Store the Intent API key for this user.")
    ap.add_argument("--status", action="store_true", help="show the key in use and its source, then exit")
    ap.add_argument("--base-url", metavar="URL", help=f"API to verify against (default {cred.DEFAULT_BASE_URL})")
    ap.add_argument("--no-verify", action="store_true", help="save without asking the API first")
    a = ap.parse_args(argv)

    if a.status:
        key = cred.find_key()
        if not key:
            print(cred.NO_KEY_HINT, file=sys.stderr)
            return EXIT_FAIL
        print(f"  key       {cred.mask(key)}")
        print(f"  source    {cred.key_source()}")
        print(f"  endpoint  {cred.base_url(a.base_url)}")
        return EXIT_OK

    if sys.stdin.isatty():
        try:
            key = getpass.getpass("  API key (input hidden): ")
        except (EOFError, KeyboardInterrupt):
            print()
            return EXIT_USAGE
    else:
        key = sys.stdin.readline()
    key = (key or "").strip()
    if not key:
        print("  no key given", file=sys.stderr)
        return EXIT_USAGE

    if not a.no_verify:
        why = _verify(key, a.base_url)
        if why:
            print(f"  not saved: {why}", file=sys.stderr)
            return EXIT_FAIL
    path = cred.save_key(key)
    print(f"  saved {cred.mask(key)} to {path}" + ("" if a.no_verify else " (verified)"))
    import os
    if os.environ.get(cred.ENV_VAR, "").strip():
        print(f"  note: {cred.ENV_VAR} is set and takes precedence over the saved key", file=sys.stderr)
    return EXIT_OK


def logout(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="aicordon logout", description="Remove the stored Intent API key.").parse_args(argv)
    if cred.delete_key():
        print(f"  removed {cred.CREDENTIALS}")
    else:
        print("  no stored key")
    return EXIT_OK
