"""The shared shell: one command parser for every product of the company.

There are two tools — Picket and Intent — and their command layer is not "similar" but literally the
same code: the umbrella calls `run()` with a different product description. Divergence is therefore
impossible by construction rather than by agreement.

The shell imports no engine. All it knows about one is the `core.engine` contract.

    aicordon letter.txt
    aicordon picket explain IPI/Exfil.Send.A
    aicordon intent scan letter.txt --api-key ...
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..core.engine import EngineUnavailable
from ..core.model import Document
from ..core.product import Product
from . import report as report_mod
from . import render

EXIT_OK, EXIT_FOUND, EXIT_USAGE, EXIT_ENGINE = 0, 1, 2, 3

PROGRESS_FROM = 100      # batch size from which progress is reported
PROGRESS_EVERY = 50

MAX_SIZE_MB = 10         # anything larger is skipped and said so; see `_walk`
BINARY_PROBE = 4096


@dataclass
class Selection:
    """How the product was chosen. Supplied by the `aicordon` command; the shell only reads it.

    It exists for one reason: **an implicit choice must be signed**. A user who forgot to export the
    key would otherwise get a check by the weaker detector and exit code 0 — formally honest, but
    not the check they were expecting.
    """

    mode: str = "explicit"                       # explicit | auto | chosen
    others: list = field(default_factory=list)   # (title, reason it is unavailable)
    why: str = ""

    @property
    def note(self) -> str:
        if self.mode == "auto":
            return f"product chosen automatically: {self.why}" if self.why else \
                "product chosen automatically"
        return ""


# --- input --------------------------------------------------------------------------------------

def _documents(a, stats: dict) -> Iterator[Document]:
    """Documents as a stream, not a list: 10 000 files must not pile up in memory."""
    if a.text is not None:
        yield Document(id="--text", text=a.text)
    if a.jsonl:
        with a.jsonl.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    print(f"line {i}: not JSON, skipped", file=sys.stderr, flush=True)
                    continue
                yield Document(id=str(r.get("id") or f"{a.jsonl.name}:{i}"),
                               text=r.get(a.field) or "", origin=str(a.jsonl))

    paths = list(a.paths)
    if not (a.text is not None or a.jsonl or paths):
        if _stdin_has_data():
            yield Document(id="stdin", text=sys.stdin.read())
            return
        # No input named at all — check the current directory, NOT recursively. Recursion by default
        # would walk into `node_modules` and `.git`, and the first impression of the product would
        # be "it hung"; `-r` is a deliberate act.
        paths = [Path(".")]
        stats["default_cwd"] = True

    for p in paths:
        if p.is_dir():
            yield from _walk(p, a, stats)
        elif p.is_file():
            # A file named explicitly is checked as it is: the traversal filters do not apply to it,
            # because the user has already said what they want.
            stats["files"] += 1
            yield Document(id=str(p), text=_read(p), origin=str(p))
        else:
            print(f"{p}: no such file", file=sys.stderr, flush=True)


def _seen(docs: Iterator[Document], sink: dict, origins: dict) -> Iterator[Document]:
    """Passes documents through, remembering their text and origin for the shell."""
    for d in docs:
        sink[d.id] = d.text
        origins[d.id] = d.origin
        yield d


def _walk(root: Path, a, stats: dict) -> Iterator[Document]:
    """Directory traversal with skips. Every skip is counted — none are silent.

    Not checking a file and then reporting "no threats found" is the same false claim as the verdict
    "clean", only quieter. That is why the counters end up in the report footer.
    """
    try:
        entries = sorted(root.rglob("*") if a.recursive else root.iterdir())
    except OSError as e:
        print(f"{root}: {e}", file=sys.stderr, flush=True)
        return
    for x in entries:
        try:
            if x.is_dir():
                # A subdirectory without `-r` is not checked. That is a skip too and must be
                # visible: otherwise "no findings" over a directory holding one file and ten folders
                # sounds like the whole tree was checked.
                if not a.recursive:
                    stats["dirs"] += 1
                continue
            if not x.is_file():
                continue
            rel = x.relative_to(root).parts
            if not a.all and any(part.startswith(".") for part in rel):
                stats["hidden"] += 1
                continue
            if x.stat().st_size > a.max_size * 1024 * 1024:
                stats["big"] += 1
                continue
            data = x.read_bytes()
        except OSError:
            stats["unreadable"] += 1
            continue
        if b"\0" in data[:BINARY_PROBE]:
            stats["binary"] += 1
            continue
        stats["files"] += 1
        yield Document(id=str(x), text=data.decode("utf-8", errors="replace"), origin=str(x))


def _stdin_has_data() -> bool:
    """Tells "data was piped in" apart from "stdin merely is not a terminal".

    The difference is practical: a CI or cron job runs with `</dev/null`, and the rule "not a
    terminal means read stdin" would hand it one empty document instead of the directory it was
    started in. A pipe (FIFO) and a redirected file are data; `/dev/null` and other character
    devices are not.
    """
    if sys.stdin is None or sys.stdin.isatty():
        return False
    try:
        mode = os.fstat(sys.stdin.fileno()).st_mode
    except (OSError, ValueError):
        return False
    return stat.S_ISFIFO(mode) or stat.S_ISREG(mode)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _new_stats() -> dict:
    return {"files": 0, "hidden": 0, "binary": 0, "big": 0, "unreadable": 0, "dirs": 0,
            "default_cwd": False}


# --- engine -------------------------------------------------------------------------------------

def _build(product: Product, a):
    """Raises the product's engine. Product flags are passed through; the shell does not read them."""
    kw = {opt.dest: getattr(a, opt.dest) for opt in product.options
          if getattr(a, opt.dest, None) is not None}
    det = product.build(**kw)
    det.available()
    return det


class _Stub:
    """Stand-in for the banner when the engine did not come up: there is a name but no base."""

    def __init__(self, product: Product) -> None:
        self.name = product.key
        self.version = "—"
        self.coverage = ""


def _unavailable(st, product: Product, e: EngineUnavailable, quiet: bool) -> int:
    """A refusal is always visible and goes to stderr: silence would read as "nothing was found"."""
    if not quiet:
        print(render.banner(st, product, _Stub(product), False, e.reason))
    # Without flushing stdout the reason would appear BEFORE the banner in a terminal: the streams
    # are buffered independently, and it would read as an error raised before the run started.
    sys.stdout.flush()
    print(f"  {st(e.reason, render.RED)}", file=sys.stderr)
    for line in (e.hint or "").splitlines():
        print(f"  {st(line, render.YELLOW)}", file=sys.stderr)
    return EXIT_ENGINE


# --- commands -----------------------------------------------------------------------------------

def cmd_scan(product: Product, a) -> int:
    st = render.make_style(a.no_color)
    quiet = a.quiet or a.json
    try:
        det = _build(product, a)
    except EngineUnavailable as e:
        return _unavailable(st, product, e, quiet)

    if not quiet:
        print(render.banner(st, product, det, True, selection=a.selection))
        # Input the user did not name must be named by us.
        if not (a.text is not None or a.jsonl or a.paths) and not _stdin_has_data():
            where = "current directory, including subdirectories" if a.recursive \
                else "current directory"
            print(f"  {st(where, render.DIM)}\n")

    if a.json:
        head = {"schema": 1, "product": product.key, "product_version": product.version,
                "engine": det.name, "engine_version": det.version,
                "product_selected": a.selection.mode}
        if getattr(a, "collect", None):
            head["collect"] = str(a.collect)
        print(json.dumps(head, ensure_ascii=False), flush=True)

    stats = _new_stats()
    t0 = time.perf_counter()
    n_docs = n_find = n_flagged = 0
    # The engine reports WHERE; showing WHAT is the shell's job, so the shell keeps the text of the
    # documents currently in flight. It holds references, not copies, and drops each one as soon as
    # its report has been rendered — at most one batch is alive, exactly what the engine holds too.
    texts: dict[str, str] = {}
    origins: dict[str, str] = {}
    collector = None
    if getattr(a, "collect", None) or getattr(a, "report", None):
        try:
            collector = report_mod.Collector(getattr(a, "collect", None), product.key, det.name,
                                             det.version, report_path=getattr(a, "report", None))
        except OSError as e:
            target = getattr(a, "collect", None) or a.report
            print(f"cannot use {target}: {e}", file=sys.stderr, flush=True)
            return EXIT_USAGE
        if collector.reused:
            print(f"--collect: {a.collect} is not empty; {report_mod.REPORT_NAME} will describe "
                  f"this run only", file=sys.stderr, flush=True)
    for rep in det.reports(_seen(_documents(a, stats), texts, origins)):
        n_docs += 1
        n_find += len(rep.findings)
        n_flagged += bool(rep.findings)
        text = texts.pop(rep.doc_id, "")
        origin = origins.pop(rep.doc_id, "")
        if collector is not None:
            collector.add(rep, text, origin)
        if a.json:
            print(json.dumps(report_mod.document_json(rep, text), ensure_ascii=False), flush=True)
        else:
            for line in render.document_block(st, rep, a.verbose, text):
                print(line)
        # Progress goes to stderr so that it never mixes with the result.
        if n_docs >= PROGRESS_FROM and n_docs % PROGRESS_EVERY == 0:
            print(f"  {n_docs}…", file=sys.stderr, flush=True)
    ms = (time.perf_counter() - t0) * 1000

    if not n_docs:
        print("nothing to check: no suitable files were found", file=sys.stderr)
        if not quiet:
            print(render.footer(st, product, det, 0, 0, ms, stats=stats))
        return EXIT_USAGE
    if collector is not None:
        where = collector.write()
        # Said out loud and on stdout: a mode that writes files must report what it wrote, or a
        # later reader cannot tell an empty collection from one that never ran.
        if not a.json:
            n = len(collector.documents)
            if a.collect:
                print(f"  Collected {n} document(s) into {a.collect}, report: {where}")
            else:
                print(f"  Report on {n} document(s) with findings: {where}")
        for problem in collector.errors:
            print(f"--collect: {problem}", file=sys.stderr, flush=True)
    if not quiet:
        print(render.footer(st, product, det, n_docs, n_find, ms, stats=stats,
                            n_flagged=n_flagged))
    return EXIT_OK if a.exit_zero else (EXIT_FOUND if n_find else EXIT_OK)


def cmd_bench(product: Product, a) -> int:
    """Timing only. Meaningful for a local rule and for an API alike — there it also measures the
    network."""
    st = render.make_style(a.no_color)
    try:
        det = _build(product, a)
    except EngineUnavailable as e:
        return _unavailable(st, product, e, True)

    stats = _new_stats()
    times: list[float] = []
    chars = 0
    for doc in _documents(a, stats):
        chars += len(doc.text)
        t = time.perf_counter()
        for _rep in det.reports([doc]):
            pass
        times.append((time.perf_counter() - t) * 1000)
        if len(times) >= PROGRESS_FROM and len(times) % PROGRESS_EVERY == 0:
            print(f"  {len(times)}…", file=sys.stderr, flush=True)
    if not times:
        print("nothing to measure: the input is empty", file=sys.stderr)
        return EXIT_USAGE

    times.sort()
    n = len(times)

    def q(p: float) -> float:
        return times[min(n - 1, int(n * p))]

    print(f"  documents {n}, average length {chars // n} characters")
    print(f"  ms/doc: median {q(0.5):.2f}   p90 {q(0.9):.2f}   p99 {q(0.99):.2f}   "
          f"max {times[-1]:.2f}")
    print(f"  total {sum(times) / 1000:.2f} s; engine {det.name} ({det.version})")
    return EXIT_OK


def cmd_check(product: Product, a) -> int:
    """Readiness: the base file for a local engine, the key and the API for a remote one."""
    st = render.make_style(a.no_color)
    try:
        det = _build(product, a)
    except EngineUnavailable as e:
        return _unavailable(st, product, e, a.quiet)
    print(f"  {st('●', render.GREEN)} {det.title}")
    print(f"    engine       {det.name} ({det.version})")
    print(f"    requires     {', '.join(sorted(det.requires)) or 'nothing'}")
    for k, v in (det.describe() or {}).items():
        print(f"    {k:<12} {v}")
    return EXIT_OK


def cmd_explain(product: Product, a) -> int:
    """The threat catalogue is read from the base, not from code — otherwise `explain` and `scan`
    drift apart."""
    st = render.make_style(a.no_color)
    try:
        det = _build(product, a)
    except EngineUnavailable as e:
        return _unavailable(st, product, e, True)
    cat = det.catalog()
    if not cat:
        print("the base declares no threat catalogue", file=sys.stderr)
        return EXIT_ENGINE

    if not a.threat:
        for name, entry in cat.items():
            color = render.SEV_COLOR.get(entry["severity"], "")
            pad = " " * max(0, 32 - len(name))
            print(f"  {st(name, render.BOLD)}{pad} {st(entry['severity'], color)}")
        print()
        print(st(f"  {len(cat)} in total; details: aicordon {product.key} explain NAME", render.DIM))
        return EXIT_OK

    entry = cat.get(a.threat)
    if entry is None:
        print(f"no such threat: {a.threat}", file=sys.stderr)
        for n in [x for x in cat if a.threat.lower() in x.lower()][:10]:
            print(f"  did you mean {n}", file=sys.stderr)
        return EXIT_USAGE

    color = render.SEV_COLOR.get(entry["severity"], "")
    print(f"  {st(entry['threat'], render.BOLD)}   {st(entry['severity'], color)}")
    print()
    for line in render.wrap(entry["description"], render.width() - 4):
        print(f"  {line}")
    print()
    n = len(entry["rules"])
    print(st(f"  {n} rule{'s' if n != 1 else ''} in the base "
             f"{'carry' if n != 1 else 'carries'} this name.", render.DIM))
    print(st("  What the report shows is the place in YOUR document that fired: "
             "scan -v prints it.", render.DIM))
    return EXIT_OK


def cmd_coverage(product: Product, a) -> int:
    """A command of its own rather than a footer line: the detector's limits are one of its
    characteristics."""
    st = render.make_style(a.no_color)
    try:
        det = _build(product, a)
    except EngineUnavailable as e:
        return _unavailable(st, product, e, True)

    print(f"  {st(det.title, render.BOLD)}  ({det.name} {det.version})")
    print()
    if det.measured:
        print(st("  measured:", render.DIM))
        for k, v in det.measured.items():
            print(f"    {k:<24} {v}")
        print()
    print(st("  does not cover:", render.DIM))
    for lim in det.limits:
        for i, line in enumerate(render.wrap(lim, render.width() - 8)):
            print(f"    {'· ' if i == 0 else '  '}{line}")
    print()
    print(st("  No findings does not mean no injection.", render.DIM))
    return EXIT_OK


def cmd_version(product: Product, a) -> int:
    """Always works, even when the engine did not come up: the tool version does not depend on the
    base."""
    st = render.make_style(a.no_color)
    print(f"  {product.title} {product.version} · {product.vendor}")
    try:
        det = _build(product, a)
        # The schema is printed next to the version because the two answer different questions: the
        # version says which base this is, the schema says whether this tool can read it at all —
        # and that is the first thing worth knowing when a base does not come up.
        schema = getattr(det, "spec", {}).get("schema")
        print(f"  base: {det.name} {det.version}" + (f" (schema {schema})" if schema else ""))
    except EngineUnavailable as e:
        print(f"  base: unavailable ({e.reason})")
    print(f"  {st(product.site, render.DIM)}")
    for line in product.promo:
        print(f"  {st(line, render.DIM)}")
    return EXIT_OK


COMMANDS = {
    "scan": (cmd_scan, "check documents"),
    "check": (cmd_check, "whether the detector is ready to work"),
    "explain": (cmd_explain, "what a threat name means"),
    "coverage": (cmd_coverage, "the detector's limits: what it does not see"),
    "version": (cmd_version, "tool version and base version"),
    "bench": (cmd_bench, "timing only: ms per document"),
}


# --- argument parsing ---------------------------------------------------------------------------

def build_parser(product: Product) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=f"aicordon {product.key}",
                                 description=f"{product.title} — {product.tagline}")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("-q", "--quiet", action="store_true", help="no banner and no footer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def product_options(p):
        """The one legitimate divergence between the tools: Intent's key and API address."""
        for opt in product.options:
            kw = {"help": opt.help, "dest": opt.dest}
            if opt.action:
                kw["action"] = opt.action
            else:
                kw["type"] = opt.type
                kw["default"] = opt.default
                if opt.metavar:
                    kw["metavar"] = opt.metavar
            p.add_argument(*opt.flags, **kw)

    def inputs(p):
        p.add_argument("paths", nargs="*", type=Path,
                       help="files and directories; without them the current directory or stdin")
        p.add_argument("-r", "--recursive", action="store_true",
                       help="descend into subdirectories (top level only by default)")
        p.add_argument("-a", "--all", action="store_true",
                       help="do not skip hidden files and directories")
        p.add_argument("--max-size", type=float, default=MAX_SIZE_MB, metavar="MB",
                       help=f"skip files larger than this (default {MAX_SIZE_MB} MB)")
        p.add_argument("--text", help="check a string given on the command line")
        p.add_argument("--jsonl", type=Path, help="batch mode: a JSONL file")
        p.add_argument("--field", default="text", help="which JSONL field holds the text")

    s = sub.add_parser("scan", help=COMMANDS["scan"][1])
    inputs(s)
    s.add_argument("--json", action="store_true",
                   help="machine output: a header line, then one line per document (NDJSON)")
    s.add_argument("-v", "--verbose", action="store_true",
                   help="print documents without findings too")
    s.add_argument("--collect", type=Path, metavar="DIR",
                   help="put a copy of every document with findings into DIR, together with "
                        f"{report_mod.REPORT_NAME} (originals are not touched or moved)")
    s.add_argument("--report", type=Path, metavar="FILE",
                   help="write the findings report to FILE as JSON; without it the report goes to "
                        "the console (--json) and nowhere else")
    s.add_argument("--exit-zero", action="store_true", help="return 0 even when there are findings")
    product_options(s)

    b = sub.add_parser("bench", help=COMMANDS["bench"][1])
    inputs(b)
    product_options(b)

    e = sub.add_parser("explain", help=COMMANDS["explain"][1])
    e.add_argument("threat", nargs="?", help="threat name; without it, the full list")
    product_options(e)

    for name in ("check", "coverage", "version"):
        p = sub.add_parser(name, help=COMMANDS[name][1])
        product_options(p)
    return ap


def run(product: Product, argv=None, selection: Selection | None = None) -> int:
    """The single entry into the shell. Both products come through here — nothing can drift."""
    a = build_parser(product).parse_args(argv)
    a.selection = selection or Selection()
    try:
        return COMMANDS[a.cmd][0](product, a)
    except EngineUnavailable as e:
        # A refusal that happened MID-RUN (the network dropped, say). Staying silent is not an
        # option: an incomplete result would read as a complete one.
        print(f"the engine failed during the run: {e.reason}", file=sys.stderr)
        return EXIT_ENGINE
    except KeyboardInterrupt:
        return EXIT_USAGE
    except BrokenPipeError:
        return EXIT_OK
    except OSError as e:
        # Unreadable input is a usage error, not a crash: a traceback explains nothing here, while
        # exit code 2 is something a pipeline can act on.
        print(f"cannot read the input: {e}", file=sys.stderr)
        return EXIT_USAGE
