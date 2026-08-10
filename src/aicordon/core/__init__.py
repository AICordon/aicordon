"""Shared core of the AI Cordon products: the finding model, the detector contract, the CLI.

The version of the distribution lives HERE and nowhere else. It used to be written out in three
places — the umbrella and each product — and three copies of one number drift the moment one of them
is edited: a clean install of 0.2.0 announced itself as 0.1.0, because the copies were not the file
the release is cut from. Now the packaging metadata is the single source, and the literal below is
only what a source tree that was never installed can fall back on.
"""
from __future__ import annotations

_FALLBACK = "0.2.0"


def _version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:                                  # pragma: no cover — Python without it
        return _FALLBACK
    try:
        return version("aicordon")
    except PackageNotFoundError:
        # Running straight from a source tree. The fallback is right for development and cannot
        # reach a user: an installed distribution always has metadata.
        return _FALLBACK


VERSION = _version()
