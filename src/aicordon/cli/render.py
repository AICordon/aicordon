"""Presentation: banner, report, colour. The only layer that prints.

The layer is shared by every product: Picket and Intent must look the same, otherwise knowing one
tool does not transfer to the other. Everything the products differ in arrives here as a parameter —
`render` itself does not know whether a local or a remote engine sits behind it.

About colour: enabled only on a TTY, honours `NO_COLOR` and `--no-color`. Redirected to a file or
piped into `head` the output must stay readable — a readiness criterion of the spec.
"""
from __future__ import annotations

import os
import shutil
import sys

from ..core.model import Report, Severity
from ..core.product import VENDOR_ART

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN = "\033[36m"

SEV_COLOR = {Severity.HIGH: RED, Severity.MEDIUM: YELLOW, Severity.LOW: CYAN}
SEV_MARK = {Severity.HIGH: "!!", Severity.MEDIUM: " !", Severity.LOW: " ·"}

# Words the detector has no right to describe its own result with (SPEC §2). Checked by a test over
# the whole output rather than by eye: at 32.4% recall "clean" and "safe" would be untrue.
#
# Whole words, not stems, and that is not pedantry about form. "Clean corpus" is an accepted
# technical term in this project (it names a sample without injections) and appears in the base
# metadata; banning it outright is wrong. What is banned is a claim about the CHECKED DOCUMENT.
# The check therefore runs on word boundaries.
FORBIDDEN = ("safe", "clean", "secure", "protected", "harmless", "benign", "trusted")

NOTHING_FOUND = "no threats found"


class Style:
    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def __call__(self, text: str, *codes: str) -> str:
        return f"{''.join(codes)}{text}{RESET}" if self.on and codes else text


def make_style(no_color: bool, stream=sys.stdout) -> Style:
    if no_color or os.environ.get("NO_COLOR") is not None:
        return Style(False)
    return Style(bool(getattr(stream, "isatty", lambda: False)()))


def width(default: int = 80) -> int:
    try:
        return max(60, min(shutil.get_terminal_size((default, 24)).columns, 120))
    except OSError:
        return default


def rule_line(st: Style) -> str:
    return st("─" * width(), DIM)


def wrap(text: str, w: int) -> list[str]:
    """Word wrapping. Width comes from the terminal and degrades to 80 columns."""
    out, line = [], ""
    for word in (text or "").split():
        if line and len(line) + 1 + len(word) > w:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


def banner(st: Style, product, detector, ready: bool, reason: str = "", selection=None) -> str:
    """Banner: product, tool version, base version, engine state.

    The point is not decoration: this is where the user sees ONCE what is about to check their
    files. An engine that dropped out for a missing key or a broken base must be visible here, or an
    incomplete check reads as a complete one (SPEC §2).
    """
    lines = []
    # Company first, product second — the user installed `aicordon`, and the product is what it is
    # running right now. The product keeps its own wordmark: which of the two checked the files is
    # the single most consequential fact on this screen.
    lines.append(st(VENDOR_ART.strip("\n"), CYAN, BOLD))
    if product.art:
        lines.append("")                       # the two wordmarks must not read as one drawing
        lines.append(st(product.art.strip("\n"), DIM, CYAN))
    lines.append(st(f"  {product.vendor} · {product.title} · {product.version}", DIM))
    lines.append(st(f"  {product.tagline}", DIM))
    lines.append("")
    mark = st("●", GREEN) if ready else st("○", DIM)
    base = getattr(detector, "version", "?")
    tail = "" if ready else st(f"  (unavailable: {reason})", DIM)
    note = getattr(selection, "note", "") if selection else ""
    lines.append(f"  {mark} {getattr(detector, 'name', product.key):<10} {st(base, DIM)}"
                 f"{tail}{st('   ' + note, YELLOW) if note else ''}")
    # Products that did NOT take part in the check, and why. Without this line an incomplete check
    # reads as a complete one — the same ban that applies to the verdict "clean" (SPEC §2).
    for title, why in getattr(selection, "others", []) or []:
        lines.append(st(f"  ○ {title:<10} {why}", DIM))
    return "\n".join(lines) + "\n"


MARK_OPEN, MARK_CLOSE = ">>>", "<<<"
SPAN_BUDGET = 600          # characters of the span shown in full before the middle is elided
CONTEXT = 90               # characters of surrounding text shown on each side of the span


def span_lines(st: Style, f, text: str) -> list[str]:
    """The injection itself, marked at both ends.

    This is the line the user actually acts on: a threat name says what kind of thing was found, but
    the decision — is this an attack in my document or a quotation in an article about attacks — can
    only be made by reading the text. Hence the whole span rather than the edge fragments the rules
    matched: those are our bookkeeping and they cut the sentence into pieces.

    Marked with characters, not only with colour: the report is read through `less`, in CI logs and
    with NO_COLOR, and a highlight that survives only in a terminal is not a highlight. The markers
    are ASCII and greppable.

    A long span is elided in the MIDDLE — the beginning and the end of an injection are where its
    demand and its recipient live, and dropping the tail would hide exactly the address it wants
    things sent to.

    Surrounding text is shown too, dimmed and outside the markers. The span is measured, not
    generous: it ends where the last matched relation ends, which on a real payload cuts off a
    sentence or two — including, in the example that prompted this, the address the text asks to
    send everything to. Deciding what to do requires reading a little further than the rule looked,
    and the markers keep the two apart, so nothing is passed off as detected that was not.
    """
    if not f.span or not text:
        return []
    lo, hi = f.span
    body = " ".join(text[lo:hi].split())
    n = len(body)
    if n > SPAN_BUDGET:
        head, tail = body[: SPAN_BUDGET // 2], body[-SPAN_BUDGET // 2:]
        body = f"{head} […{n - SPAN_BUDGET} chars…] {tail}"
    # Context is cut to whole words: a line starting with "… y results" reads as damaged text and
    # makes the reader wonder whether the document is damaged too.
    before = " ".join(text[max(0, lo - CONTEXT):lo].split())
    after = " ".join(text[hi:hi + CONTEXT].split())
    if lo - CONTEXT > 0 and before:
        before = "… " + before.partition(" ")[2]
    if hi + CONTEXT < len(text) and after:
        after = after.rpartition(" ")[0] + " …"

    out = [f"       {st(f'text at {lo}–{hi} ({n} chars):', DIM)}"]
    # Assembled as one string and wrapped whole, so the markers land where the span really starts
    # and ends rather than at a line break.
    pieces = [(before + " " if before else "", DIM), (MARK_OPEN, DIM), (body, RED),
              (MARK_CLOSE, DIM), (" " + after if after else "", DIM)]
    plain = "".join(p for p, _ in pieces)
    spans: list[tuple[int, int, str]] = []
    pos = 0
    for p, code in pieces:
        spans.append((pos, pos + len(p), code))
        pos += len(p)
    at = 0
    for line in wrap(plain, max(20, width() - 14)):
        start = plain.index(line, at)
        at = start + len(line)
        # Colour each piece of the line separately: a wrapped line may cross the marker.
        rendered = ""
        for s0, s1, code in spans:
            a0, a1 = max(start, s0), min(start + len(line), s1)
            if a0 < a1:
                rendered += st(plain[a0:a1], code)
        out.append(f"       {rendered}")
    return out


def finding_block(st: Style, f, verbose: bool = False, text: str = "") -> list[str]:
    """One place — one block. The machinery behind it appears only under `-v`.

    By default the reader gets what they can act on: what was recognised, how severe it is, where it
    sits, and the text itself. Which rules fired and which constructions matched is our internal
    bookkeeping — useful when tuning the base, noise when reading a report. It used to be printed
    always, and three rules over one sentence turned into three blocks of near-identical output.
    """
    color = SEV_COLOR.get(f.severity, "")
    where = f"offset {f.span[0]}–{f.span[1]}" if f.span else "location undetermined"
    head = (f"    {st(SEV_MARK.get(f.severity, ' ·'), color)} "
            f"{st(f.threat, BOLD)}  {st(f.severity, color)}  {st(where, DIM)}")
    also = getattr(f, "also", []) or []
    if also:
        # Not a footnote: several techniques at one place is a property of the injection, and a
        # report that hides them would answer a narrower question than the one that was asked.
        head += st(f"  +{len(also)}", DIM)
    out = [head]
    out += span_lines(st, f, text)

    if not verbose:
        return out

    shown: set[str] = set()
    for e in f.evidence[:3]:
        q = " ".join((e.quote or "").split())
        # Edges of a conjunction often cut out the very same piece of text; printing it twice
        # manufactures the appearance of two pieces of evidence where there is one.
        if q and q not in shown:
            shown.add(q)
            out.append(f"       {st(chr(34) + q[:96] + ('…' if len(q) > 96 else '') + chr(34), DIM)}")

    if also:
        out.append(f"       {st('also: ' + ', '.join(also), DIM)}")
    rules = f.extra.get("rules") or []
    if rules:
        # The numbers of the rules, not what they consist of. A number is enough to say "this one
        # fired" in a bug report; the terms and distances behind it are the base itself, and the
        # base is not something the tool hands out — see the note in `threats.catalog`.
        out.append(f"       {st('rules: ' + ', '.join('#' + str(r) for r in rules), DIM)}")
    return out


def document_block(st: Style, rep: Report, verbose: bool, text: str = "") -> list[str]:
    if not rep.flagged and not verbose:
        return []
    out = [f"  {st(rep.doc_id, BOLD)}"]
    if not rep.flagged:
        out.append(f"    {st(NOTHING_FOUND, DIM)}")
    for f in sorted(rep.findings, key=lambda x: Severity.ORDER.get(x.severity, 9)):
        out += finding_block(st, f, verbose, text)
    out.append("")
    return out


SKIP_NAMES = (("hidden", "hidden"), ("binary", "binary"), ("big", "over the size limit"),
              ("unreadable", "unreadable"), ("dirs", "subdirectories (needs -r)"))


def skipped_line(stats: dict) -> str:
    """Whatever was skipped is named: silently not checking something is the same false claim as
    "clean", only quieter."""
    parts = [f"{stats[key]} {name}" for key, name in SKIP_NAMES if stats.get(key)]
    return f"Skipped: {', '.join(parts)}" if parts else ""


def footer(st: Style, product, detector, n_docs: int, n_find: int, ms: float,
           promo: bool = True, stats: dict | None = None, n_flagged: int = 0) -> str:
    """Footer: totals, coverage, and only then the link.

    The order here is substantive, not cosmetic. The coverage line is the only place that states
    what the check does NOT cover, and it must come before any mention of the company's other
    products (the rules for those lines live in `core/product.py`).

    Findings are counted IN DOCUMENTS as well as in total: over a directory "Findings: 12" leaves
    the reader guessing whether that is one poisoned page or twelve, and those are different
    situations. With a single document there is nothing to disambiguate, so the clause is dropped.
    """
    found = f"{n_find}"
    if n_docs > 1 and n_find:
        found += f" in {n_flagged} of {n_docs} documents"
    lines = [rule_line(st),
             f"  Documents: {n_docs}     Findings: {found}     Time: {ms:.0f} ms"]
    skipped = skipped_line(stats or {})
    if skipped:
        lines.append(st(f"  {skipped}", DIM))
    lines.append("")
    cover = f"Engine: {detector.name} ({detector.version}). Does not cover: {detector.coverage}."
    for line in wrap(cover, width() - 4):
        lines.append(st(f"  {line}", DIM))
    lines.append(st("  No findings does not mean no injection.", DIM))
    if promo and product.promo:
        lines.append("")
        for line in product.promo:
            lines.append(st(f"  {line}", DIM))
    return "\n".join(lines)
