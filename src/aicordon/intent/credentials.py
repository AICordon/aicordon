"""Intent API key and address. Lives in the Intent package: Picket has no key.

Key lookup order (as in the OpenAI, Anthropic and Hugging Face clients):

    1. argument              intent.load(api_key="aig_...")
    2. environment           AICORDON_API_KEY
    3. credentials file      written by `aicordon login`, mode 0600

Address: `base_url=`, then AICORDON_BASE_URL, then production.

The key is not validated here; `aicordon login` checks it with the API before saving. Output shows
the key only through `mask`.
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

SITE = "https://ai-cordon.com"
ENV_VAR = "AICORDON_API_KEY"
BASE_URL_ENV = "AICORDON_BASE_URL"
DEFAULT_BASE_URL = "https://app.ai-cordon.com"


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


# One line, owner-only, as in `huggingface-cli login`.
CREDENTIALS = _config_home() / "aicordon" / "credentials"
CONFIG = CREDENTIALS                     # former name

NO_KEY_HINT = (
    f"No API key found. Get one at {SITE}, then either:\n"
    f"    aicordon login                  (stores it in {CREDENTIALS})\n"
    f"    export {ENV_VAR}=<key>"
)


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None                  # empty or whitespace: no key


def _read_file(path: Path) -> str | None:
    try:
        return _clean(path.read_text(encoding="utf-8")) if path.is_file() else None
    except OSError:
        return None                       # unreadable file: no key


def find_key(explicit: str | None = None) -> str | None:
    """The key, or None: argument, then environment, then the credentials file."""
    return _clean(explicit) or _clean(os.environ.get(ENV_VAR)) or _read_file(CREDENTIALS)


def key_source(explicit: str | None = None) -> str | None:
    """Where `find_key` found the key — for `describe` and `aicordon login --status`."""
    if _clean(explicit):
        return "argument"
    if _clean(os.environ.get(ENV_VAR)):
        return ENV_VAR
    if _read_file(CREDENTIALS):
        return str(CREDENTIALS)
    return None


def has_key(explicit: str | None = None) -> bool:
    return find_key(explicit) is not None


def base_url(explicit: str | None = None) -> str:
    """The API root, without a trailing slash: argument, then AICORDON_BASE_URL, then production."""
    return (_clean(explicit) or _clean(os.environ.get(BASE_URL_ENV)) or DEFAULT_BASE_URL).rstrip("/")


def mask(key: str | None) -> str:
    """`aig_…Xy12`: prefix and last four characters."""
    if not key:
        return "—"
    head, _, _ = key.partition("_")
    prefix = head + "_" if "_" in key and len(head) <= 6 else ""
    return f"{prefix}…{key[-4:]}" if len(key) > 8 else "…"


def save_key(key: str) -> Path:
    """Save the key atomically: directory 0700, file 0600, written to a temp file and renamed."""
    key = _clean(key)
    if not key:
        raise ValueError("an empty key cannot be saved")
    CREDENTIALS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=CREDENTIALS.parent, prefix=".credentials.")
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key + "\n")
        os.replace(tmp, CREDENTIALS)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return CREDENTIALS


def delete_key() -> bool:
    """Remove the stored key. True if there was one."""
    try:
        CREDENTIALS.unlink()
        return True
    except FileNotFoundError:
        return False
