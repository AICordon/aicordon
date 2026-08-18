"""Picket — AI Cordon's free signature detector for prompt injection. A rule; no model, no network.

The package works as a tool and as a library. The second is not a side effect: adapters for AI
frameworks will be written against THIS interface rather than against argument parsing, so importing
the package prints nothing, exits nothing and needs no configuration.

Embedding:

    from aicordon import picket

    det = picket.load()                     # raised once, then called as often as you like
    rep = det.check(letter)
    if rep.flagged:
        print(rep.severity, rep.threats, rep.span)

    for rep in det.check_all(documents):   # streamed, input order preserved
        ...

The `intent` package exposes the same set of names (the same detector behind an API). Code written
against one works with the other — that is an architectural requirement, not a coincidence.

What the package does NOT claim: no findings does not mean no injection. The rule sees on the
order of a quarter of the injections in its own bank (`aicordon picket coverage`), which is why the API has no
`is_safe` field and never will — believing such a field in reverse would be a mistake.
"""
from __future__ import annotations

from aicordon.core.engine import BaseDetector, EngineUnavailable
from aicordon.core.model import Document, Evidence, Finding, Report, Severity
from aicordon.core.product import Option, Product

__all__ = [
    "Detector", "load", "pick_base", "PRODUCT",
    "Document", "Finding", "Evidence", "Report", "Severity",
    "EngineUnavailable", "BaseDetector",
]

# The detector is imported ON FIRST USE, not on `import picket` (PEP 562). Measured: importing the
# package costs 26.8 ms eagerly against 14.8 ms lazily, and the engine is imported anyway the moment
# a detector is actually built. That matters for code that imports the package only to read
# `PRODUCT` or `VERSION` — the umbrella does exactly that when it lists the installed products.
# It also removes a RuntimeWarning: `python3 -m aicordon.picket.rule.scan` used to report the module as
# imported twice, because the package `__init__` pulled in the very module being run as `__main__`.
#
# What this does NOT save: the shell still probes every product for readiness (a product that did
# not take part must be named with a reason), and probing builds the detector.
#
# The public names are unchanged — `from aicordon.picket import Detector` and `picket.load()` work as before.

_LAZY = ("Detector", "load", "pick_base")


def __getattr__(name: str):
    if name in _LAZY:
        from . import detector
        globals().update({k: getattr(detector, k) for k in _LAZY})
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


def _mode(v: str) -> str:
    """Validated at PARSE time rather than when the detector is built: otherwise a typo in the flag
    surfaces as a traceback out of the depths of the package instead of one line naming the mode."""
    import argparse
    if v not in ("ipi", "dpi"):
        raise argparse.ArgumentTypeError(f"unknown mode {v!r}: expected 'ipi' or 'dpi'")
    return v


def _build(**kw):
    """What `PRODUCT.build` points at: the same `load`, resolved at call time.

    Naming `load` directly in the card would defeat the laziness — building the card is part of
    importing the package.
    """
    from .detector import load
    return load(**kw)

from ..core import VERSION  # noqa: F401 — one source for the version

ART = r"""
   ___   _ __        __
  / _ \ (_) /_____  / /_
 / ___// / ,< / -_)/ __/
/_/   /_/_/|_|\__/ \__/
"""

PRODUCT = Product(
    key="picket",
    title="Picket",
    # "Detector" with the qualifier always attached: Picket is the SIGNATURE detector, Intent the
    # SEMANTIC one. Same genus, different method — which is what the two products actually are, and
    # naming them asymmetrically ("prefilter" vs "detector") only hid it. The frame to stay out of
    # is the undifferentiated "one more injection detector", so the qualifier is not decoration:
    # never ship the noun without it.
    tagline="fast local signature detector for prompt injection · a rule, no model, no network",
    version=VERSION,
    build=_build,
    art=ART,
    free=True,
    options=(
        Option(flags=("--rules",), dest="rules", metavar="FILE",
               help="base file (the one shipped with the package by default)"),
        Option(flags=("--span-pad",), dest="span_pad", metavar="N", type=int,
               help="shift the span from its measured optimum: 0 is the optimum, +150 for "
                    "trimming a document, -50 for the raw hull of the matched rules"),
        # WHERE THE TEXT CAME FROM, not how hard to look. `dpi` adds the rules for the openings
        # people type by hand, and those cost 0.81% false positives on documents against 0.098%
        # for the default — eight times the noise if the mode is used as a sensitivity knob.
        Option(flags=("--mode",), dest="mode", metavar="ipi|dpi", type=_mode, default="ipi",
               help="ipi (default) for data your code fetched, dpi for a turn your user typed"),
    ),
    # The rules for these lines live in `aicordon/core/product.py`. While there is no production API
    # only the site is mentioned: promising a package and an API before they can be used is not on.
    promo=("The full AI Cordon detector sees what a rule cannot: ai-cordon.com",),
)
