"""Intent — the full AI Cordon indirect prompt injection detector, over an API. A STUB in this build.

The public names are the same as in the `picket` package, and that is the chief requirement on both:
code written against one detector works with the other unchanged — embedding code as much as the
future adapters for AI frameworks.

    from aicordon import intent

    det = intent.load(api_key="...")       # key: argument, AICORDON_API_KEY or ~/.config
    rep = det.check(letter)

There are exactly two differences from Picket, and both are unavoidable: it needs a key and it needs
the network. Everything else is the same finding model, the same contract, the same command shell.
"""
from __future__ import annotations

from aicordon.core.engine import BaseDetector, EngineUnavailable
from aicordon.core.model import Document, Evidence, Finding, Report, Severity
from aicordon.core.product import Option, Product

from .credentials import CONFIG, ENV_VAR, find_key, has_key

__all__ = [
    "Detector", "load", "DEFAULT_ENDPOINT", "PRODUCT",
    "find_key", "has_key", "ENV_VAR", "CONFIG",
    "Document", "Finding", "Evidence", "Report", "Severity",
    "EngineUnavailable", "BaseDetector",
]

# Lazy, exactly as in `picket`: importing the package must not drag the engine in, and the two
# products have to behave the same way down to this. The key lookup stays eager — `credentials` is
# what decides whether this product is available at all, and it reads at most one small file.

_LAZY = ("Detector", "load", "DEFAULT_ENDPOINT")


def __getattr__(name: str):
    if name in _LAZY:
        from . import detector
        globals().update({k: getattr(detector, k) for k in _LAZY})
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


def _build(**kw):
    """What `PRODUCT.build` points at: the same `load`, resolved at call time."""
    from .detector import load
    return load(**kw)


VERSION = "0.1.0"

ART = r"""
   ____     __            __
  /  _/__  / /____ ___   / /_
 _/ // _ \/ __/ -_) _ \ / __/
/___/_//_/\__/\__/_//_/ \__/
"""

PRODUCT = Product(
    key="intent",
    title="Intent",
    tagline="full indirect prompt injection detector · over an API",
    version=VERSION,
    build=_build,
    art=ART,
    free=False,
    options=(
        Option(flags=("--api-key",), dest="api_key", metavar="KEY",
               help=f"API access key (otherwise {ENV_VAR} or {CONFIG})"),
        Option(flags=("--endpoint",), dest="endpoint", metavar="URL",
               help="API address (production by default)"),
    ),
)
