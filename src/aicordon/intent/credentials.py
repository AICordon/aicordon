"""Where the Intent API key and address come from. Part of the Intent package, not of the shared core.

It lives here deliberately: the key belongs to exactly one product, and moving it into shared code
would make the free Picket carry the notion of a key it does not have.

The lookup follows the convention of the common API clients (OpenAI, Anthropic, Hugging Face), so
nothing about it has to be learned:

    1. an explicit argument           intent.load(api_key="aig_...")
    2. an environment variable        AICORDON_API_KEY
    3. the credentials file           written by `aicordon login`, readable by its owner only

The address works the same way: `base_url=` or AICORDON_BASE_URL, and production otherwise.

Nothing is validated here. "There is a key" and "the key works" are different questions, and the
second is answered by the API — `aicordon login` asks it once before saving, every call asks it again.
The key is never printed whole: `mask` is what logs, reports and `describe` show.
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


# One file, one line, owner-only — the shape `huggingface-cli login` and `gh auth` settled on. Not
# JSON: a key is the only thing it holds, and a format with room for more invites putting more there.
CREDENTIALS = _config_home() / "aicordon" / "credentials"
CONFIG = CREDENTIALS                     # the name the package exported before the file had a format

NO_KEY_HINT = (
    f"No API key found. Get one at {SITE}, then either:\n"
    f"    aicordon login                  (stores it in {CREDENTIALS})\n"
    f"    export {ENV_VAR}=<key>"
)


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None                  # an empty string and whitespace do not count as a key


def _read_file(path: Path) -> str | None:
    try:
        return _clean(path.read_text(encoding="utf-8")) if path.is_file() else None
    except OSError:
        return None                       # an unreadable file means no key, not a crash


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
    """`aig_…Xy12` — enough to tell two keys apart, not enough to use one."""
    if not key:
        return "—"
    head, _, _ = key.partition("_")
    prefix = head + "_" if "_" in key and len(head) <= 6 else ""
    return f"{prefix}…{key[-4:]}" if len(key) > 8 else "…"


def save_key(key: str) -> Path:
    """Write the key for this user, owner read/write only, atomically.

    The directory is created 0700 and the file is written to a temporary name and renamed, so a
    crash never leaves a half-written key and there is no moment when the file is world-readable.
    """
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
