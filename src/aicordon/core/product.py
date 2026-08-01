"""Product description: everything that makes one product differ from another.

There are two products — Picket (a local rule) and Intent (a detector behind an API) — and one
requirement on both: **their command layer is shared**. Not "similar", literally the same code,
because similar shells drift apart at the first edit and a user who knows one has to relearn the
other.

So the differences are collected into a single description object. A product package fills it in and
hands it to the shell; the shell imports no engine and does not know whether it is local or remote.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .engine import Engine

VENDOR = "AI Cordon"
SITE = "https://ai-cordon.com"

# The company comes FIRST on the splash and the product second: what a user installs is `aicordon`,
# and the products are what it can run. The wordmark lives in the shared core rather than in a
# product package for the same reason — it belongs to neither product and must not drift between
# them.
VENDOR_ART = r"""
   ___   ____  _____            __
  / _ | /  _/ / ___/__  _______/ /__  ___
 / __ |_/ /  / /__/ _ \/ __/ _  / _ \/ _ \
/_/ |_/___/  \___/\___/_/  \_,_/\___/_//_/
"""


@dataclass
class Option:
    """An extra command-line flag belonging to one product.

    It exists for the one legitimate divergence between the tools: Intent needs a key and an API
    address, Picket does not. The flag is declared here rather than in the shell so the shell never
    grows arguments that half of the products do not have.
    """

    flags: tuple[str, ...]
    dest: str
    help: str
    metavar: str = ""
    type: Callable[[str], object] = str
    default: object = None
    action: str = ""              # non-empty means a flag without an argument (`store_true`)


@dataclass
class Product:
    key: str                                  # picket, intent — the sub-command name
    title: str                                # Picket, Intent — for the banner and the report
    tagline: str                              # one line under the banner
    version: str                              # version of the TOOL, not of the base
    build: Callable[..., Engine]              # engine factory; raised once per run
    art: str = ""                             # banner art; an empty string is fine
    options: tuple[Option, ...] = ()
    vendor: str = VENDOR
    site: str = SITE
    free: bool = True
    promo: tuple[str, ...] = ()               # see below — the rules for these lines are strict


# About `promo`. A free tool pointing at the company's main resource is legitimate, but this is
# exactly where a product gets spoiled: an advertisement inside a detector's output competes for
# attention with the warning that the check is incomplete, and that warning matters more than any
# link.
#
# Hence rules that must not be broken while extending this:
#
#   * one line, two at most, printed ONCE per run, in the footer;
#   * it comes AFTER the coverage line, never instead of it and never before it;
#   * it is absent from `--json` and under `-q`: machine output and pipelines do not read ads;
#   * it promises nothing that does not exist. While there is no production API only the site is
#     mentioned; the package and the API join these lines when they can actually be used;
#   * it does not frighten and does not push: "we see less than a third" is already stated honestly
#     by the coverage line, and repeating it as an argument for the paid product is not needed.
