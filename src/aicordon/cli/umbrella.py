"""The single `aicordon` command: finds the installed products and hands the work to the shell.

This is the composition root — **the only place that knows the products by name**. `core` and
`cli/main` still know none of them: they receive a product description as a parameter. Deleting a
product package therefore breaks nothing except its own line in the listing.

Grammar:

    aicordon [PRODUCT] [COMMAND] [arguments]

Both upper levels are optional and get filled in, BUT only when that can be done unambiguously:

    product omitted -> the one that is ready, if exactly one is; otherwise ask (terminal)
                       or refuse with a ready-made hint (script, pipeline)
    command omitted -> scan

A product named explicitly is **never substituted**: ask for Intent and you get Intent or a refusal.
Substitution is allowed only where there is no choice to make.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass

from ..core.engine import EngineUnavailable
from ..core.product import VENDOR
from . import render
from .main import COMMANDS, EXIT_ENGINE, EXIT_OK, EXIT_USAGE, Selection, run

# Default order: the free product first. A name absent from the environment simply never shows up.
# Products live INSIDE the distribution (`aicordon.picket`, `aicordon.intent`) rather than at
# the top level: the flat names are taken on PyPI by unrelated projects — `picket` there is a
# rules tool for AI coding agents, a close enough neighbour to end up installed side by side —
# and two different libraries answering to one import name is a failure nobody debugs quickly.
PRODUCT_MODULES = ("aicordon.picket", "aicordon.intent")

VERSION = "0.1.0"

HELP = """  aicordon — indirect prompt injection (IPI) detectors by AI Cordon

  aicordon [PRODUCT] [COMMAND] [arguments]

  The product and the command are optional: the product is filled in when exactly one is
  ready, the command defaults to scan, and the input defaults to the current directory.

    aicordon                       check the current directory
    aicordon letter.txt            check one file
    aicordon -r ./docs             check a directory including subdirectories
    cat letter.txt | aicordon      check a stream
    aicordon picket coverage       the limits of one product
    aicordon -- scan               a file named like a command goes after --

  Commands: {commands}
  Products: {products}
"""


@dataclass
class Slot:
    """A product plus whatever probing it revealed."""

    product: object
    ready: bool = False
    reason: str = ""
    hint: str = ""
    version: str = "—"


def discover() -> list[Slot]:
    """Installed products. A missing package is a legitimate state, not a failure."""
    out: list[Slot] = []
    for name in PRODUCT_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        product = getattr(mod, "PRODUCT", None)
        if product is not None:
            out.append(Slot(product=product))
    return out


def probe(slots: list[Slot]) -> None:
    """Asks each product whether it can work. Costly exactly once per run; the listing is honest."""
    for s in slots:
        try:
            det = s.product.build()
            det.available()
            s.ready, s.version = True, det.version
        except EngineUnavailable as e:
            s.reason, s.hint = e.reason, e.hint
        except Exception as e:                    # noqa: BLE001 — a broken product must not kill the listing
            s.reason = f"{type(e).__name__}: {e}"


def _interactive() -> bool:
    """Asking is possible only when there is someone to ask: both question and answer via terminal.

    A pipeline stuck on a prompt is worse than a refusal — nobody sees it and nobody interrupts it.
    """
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def menu(st, slots: list[Slot], what: str) -> Slot | None:
    """The menu picks the PRODUCT only: what to do has already been said by the arguments."""
    ready = [s for s in slots if s.ready]
    print(f"  {st('What should check ' + what + '?', render.BOLD)}")
    for i, s in enumerate(ready, 1):
        tail = st("  [default]", render.DIM) if i == 1 else ""
        print(f"    {i}) {s.product.title:<10} {st(s.product.tagline, render.DIM)}{tail}")
    for s in slots:
        if not s.ready:
            print(f"    {st('○ ' + s.product.title + ' — ' + s.reason, render.DIM)}")
    try:
        raw = input("  → ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return ready[0]
    if raw.isdigit() and 1 <= int(raw) <= len(ready):
        return ready[int(raw) - 1]
    by_name = {s.product.key: s for s in ready}
    return by_name.get(raw.lower())


def status(st, slots: list[Slot]) -> int:
    """The product listing — what is shown when there is nothing to work on."""
    print(f"  {st(VENDOR + ' ' + VERSION, render.BOLD)}")
    print()
    for s in slots:
        mark = st("●", render.GREEN) if s.ready else st("○", render.DIM)
        tail = "" if s.ready else st(f"  {s.reason}", render.DIM)
        print(f"    {mark} {s.product.title:<10} {s.product.key:<8} "
              f"{st(s.version, render.DIM)}{tail}")
    print()
    print(st("  aicordon letter.txt          check a file", render.DIM))
    print(st("  aicordon picket coverage     what the detector does not see", render.DIM))
    return EXIT_OK


def split_argv(argv: list[str], names: set[str]) -> tuple[str | None, list[str]]:
    """Separates the product name from the rest.

    Only LEADING tokens are examined, up to the first flag (global ones are skipped). Otherwise the
    value of somebody else's flag — `--field scan` — would be taken for a command.
    """
    out = list(argv)
    i = 0
    while i < len(out):
        tok = out[i]
        if tok in ("--no-color", "-q", "--quiet"):
            i += 1
            continue
        if tok == "--":
            return None, out
        if tok.startswith("-"):
            return None, out
        if tok in names:
            return out.pop(i), out
        return None, out
    return None, out


def needs_command(argv: list[str]) -> bool:
    """Is a command present at the front? If not, `scan` gets filled in."""
    for tok in argv:
        if tok in ("--no-color", "-q", "--quiet"):
            continue
        if tok == "--" or tok.startswith("-"):
            return True
        return tok not in COMMANDS
    return True


AMBIGUOUS = "ambiguous"


def pick(slots: list[Slot], interactive: bool, ask):
    """Who will do the checking when no product was named. Extracted so it can be tested.

    One rule: substitution is allowed only when there is NO choice. Exactly one ready product means
    take it and sign the choice; several mean ask, and if there is nobody to ask (a script, a
    pipeline) refuse. Guessing instead of asking would mean silently swapping detectors in CI.
    """
    ready = [s for s in slots if s.ready]
    if len(ready) == 1:
        return ready[0], "auto"
    if not interactive:
        return None, AMBIGUOUS
    return ask(), "chosen"


def _what(rest: list[str]) -> str:
    """What exactly is about to be checked — so the menu asks about the job, not in the abstract."""
    command = next((t for t in rest if not t.startswith("-")), "scan")
    if command != "scan":
        return f"\"{command}\""
    target = next((t for t in rest[1:] if not t.startswith("-")), None)
    return f"\"{target}\"" if target else "the current directory"


def _ambiguous(st, ready: list[Slot], rest: list[str]) -> int:
    """Ambiguity where nobody can be asked: refuse with a ready-made line, never guess."""
    print(f"  {len(ready)} products are ready, name one explicitly:", file=sys.stderr)
    for s in ready:
        print(f"    aicordon {s.product.key} {' '.join(rest)}", file=sys.stderr)
    return EXIT_USAGE


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    st = render.make_style("--no-color" in argv)

    slots = discover()
    if not slots:
        print("no product is installed", file=sys.stderr)
        return EXIT_ENGINE

    names = {s.product.key for s in slots}
    if argv and argv[0] in ("-h", "--help", "help"):
        print(HELP.format(commands=", ".join(COMMANDS), products=", ".join(sorted(names))))
        return EXIT_OK

    key, rest = split_argv(argv, names)
    if needs_command(rest):
        rest.insert(0, "scan")

    probe(slots)

    # A product named explicitly is the one that works. Substituting "it is unavailable, take the
    # neighbour" is forbidden: the user asked for a particular check, and a silent swap would make
    # the answer worthless.
    if key is not None:
        slot = next(s for s in slots if s.product.key == key)
        others = [(o.product.title, o.reason) for o in slots if o is not slot]
        return run(slot.product, rest, Selection("explicit", others))

    ready = [s for s in slots if s.ready]
    if not ready:
        print(f"  {st('no product is ready to work', render.RED)}", file=sys.stderr)
        for s in slots:
            print(f"    {s.product.title}: {s.reason}", file=sys.stderr)
            for line in (s.hint or "").splitlines():
                print(f"      {st(line, render.YELLOW)}", file=sys.stderr)
        return EXIT_ENGINE

    slot, mode = pick(slots, _interactive(), lambda: menu(st, slots, _what(rest)))
    if mode == AMBIGUOUS:
        return _ambiguous(st, ready, rest)
    if slot is None:
        return EXIT_USAGE                      # the choice was cancelled by the user
    others = [(o.product.title, o.reason) for o in slots if o is not slot]
    return run(slot.product, rest,
               Selection(mode, others, "only one is ready" if mode == "auto" else ""))


if __name__ == "__main__":
    raise SystemExit(main())
