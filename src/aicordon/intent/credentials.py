"""Whether the user has access to the API. Part of the Intent package, not of the shared core.

It lives here deliberately: the key belongs to exactly one product, and moving it into shared code
would make the free Picket carry the notion of a key it does not have.

The key is looked for in three places, in descending priority: an explicit argument, an environment
variable, a configuration file. Nothing is validated over the network — "there is a key" and "the
key works" are different questions, and the second is answered by the first call to the API.

STUB: only the PRESENCE of a key is checked so far, the format is not parsed.
"""
from __future__ import annotations

import os
from pathlib import Path

SITE = "https://ai-cordon.com"
ENV_VAR = "AICORDON_API_KEY"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ai-cordon" / "key"

NO_KEY_HINT = (
    f"No API access key found. Get one at: {SITE}\n"
    f"    Then: export {ENV_VAR}=<key>   or put the key in {CONFIG}"
)


def find_key(explicit: str | None = None) -> str | None:
    """The key, or None. An empty string and whitespace do not count as a key."""
    for candidate in (explicit, os.environ.get(ENV_VAR)):
        if candidate and candidate.strip():
            return candidate.strip()
    try:
        if CONFIG.is_file():
            text = CONFIG.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError:
        pass                    # an unreadable config means no key, not a crash
    return None


def has_key(explicit: str | None = None) -> bool:
    return find_key(explicit) is not None
