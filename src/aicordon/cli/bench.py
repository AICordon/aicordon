"""Measuring the detector on YOUR documents: the numbers and the chart, without dependencies.

Why it is a command and not a page in the README. Every figure we publish was measured on our
machine and our corpora, and both differ from yours: the constant scales with the CPU, and how much
a document costs depends on what is written in it. A number you can reproduce where it will run is
worth more than a number you have to believe, so the tool carries the measurement with it.

What it reports is what we ourselves look at:

    per document      median, P10-P90, P99, max — the spread matters more than the average
    per 1000 chars    slope and intercept of the cost model, each with an interval
    throughput        documents and characters per second, and the whole run
    flagged share     how often it fires HERE — not an error rate, see below

The intervals are bootstrapped over documents rather than taken from a formula: the spread grows
with document size, so the constant-variance assumption behind the textbook interval is false here.
Two thousand resamples, a fixed seed, plain `random` — nothing to install.

The chart is written as SVG, which is text: no plotting library, no fonts to embed, and it opens in
any browser. That is not asceticism — a detector that must be installable inside somebody else's
dependency tree cannot bring matplotlib along for a chart.

**The flagged share is not a false-positive rate.** This code has no idea whether your documents
contain injections. It reports how often the detector fired here; calling that an error rate would
require labels, and labels are exactly what a corpus of your own documents does not come with.
"""
from __future__ import annotations

import math
import random
import sys
import time
from typing import Iterable

BOOT = 2000
SEED = 20260801


def measure(det, docs: Iterable, repeat: int = 1, progress=None) -> list[dict]:
    """One row per document: its size, the median of `repeat` timings, and whether it fired.

    The median of repeats and not the first timing: the first touch of a document pays for the file
    cache and for whatever else the machine was doing, and on short documents that noise is larger
    than the thing being measured.
    """
    rows: list[dict] = []
    for i, doc in enumerate(docs, 1):
        ts = []
        flagged = False
        for _ in range(max(1, repeat)):
            t = time.perf_counter()
            for rep in det.reports([doc]):
                flagged = rep.flagged
            ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        rows.append({"id": doc.id, "size": len(doc.text), "ms": ts[len(ts) // 2],
                     "flagged": flagged})
        if progress:
            progress(i)
    return rows


class Progress:
    """A progress line for a run that takes minutes. Standard library, no dependency.

    Two shapes for two readers. On a terminal it is ONE line, rewritten in place with `\r`, with a
    bar, a rate and a forecast — a person watching wants to know whether to wait or to leave. Piped
    into a file or a CI log there is no cursor to move, so it degrades to a line every so often;
    a bar written with `\r` into a log file produces a single unreadable line kilometres long.

    Always on stderr: the report goes to stdout and has to stay pipeable.

    The forecast is deliberately naive — elapsed per document times what is left. The alternative,
    a moving average, is worse here: document costs differ by an order of magnitude, and a rate
    computed over the last few makes the estimate jump.
    """

    WIDTH = 28

    def __init__(self, total: int | None = None, every: int = 50) -> None:
        self.total = total if total and total > 0 else None
        self.every = max(1, every)
        self.tty = bool(getattr(sys.stderr, "isatty", lambda: False)())
        self.t0 = time.perf_counter()
        self.n = 0

    def tick(self, n: int) -> None:
        self.n = n
        if not self.tty:
            if n % max(self.every, 50) == 0:
                print(f"  {n}{'/' + str(self.total) if self.total else ''}…",
                      file=sys.stderr, flush=True)
            return
        if n % self.every and n != self.total:
            return
        done = time.perf_counter() - self.t0
        rate = n / done if done else 0
        if self.total:
            filled = int(self.WIDTH * n / self.total)
            bar = "█" * filled + "·" * (self.WIDTH - filled)
            left = (self.total - n) / rate if rate else 0
            tail = f" {n}/{self.total}  {rate:.0f}/s  {_clock(left)} left"
        else:
            bar = "·" * self.WIDTH
            tail = f" {n}  {rate:.0f}/s  {_clock(done)} elapsed"
        print(f"\r  {bar}{tail}   ", end="", file=sys.stderr, flush=True)

    def done(self) -> None:
        """Clears the line so the report starts on a clean one."""
        if self.tty:
            print("\r" + " " * (self.WIDTH + 44) + "\r", end="", file=sys.stderr, flush=True)


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def _quantile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p))]


def _fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least squares with an intercept, written out because there is no numpy here."""
    n = len(xs)
    if n < 2:
        return (ys[0] if ys else 0.0), 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - slope * mx, slope


def _boot_fit(xs: list[float], ys: list[float], n: int = BOOT) -> dict:
    """Intercept and slope, each with half the 95% interval — resampling documents, not residuals."""
    a0, b0 = _fit(xs, ys)
    rnd = random.Random(SEED)
    N = len(xs)
    if N < 8:
        return {"intercept": a0, "intercept_pm": None, "slope": b0, "slope_pm": None}
    A, B = [], []
    for _ in range(n):
        idx = [rnd.randrange(N) for _ in range(N)]
        a, b = _fit([xs[i] for i in idx], [ys[i] for i in idx])
        A.append(a)
        B.append(b)
    A.sort()
    B.sort()

    def pm(vals: list[float], point: float) -> float:
        lo = vals[int(0.025 * len(vals))]
        hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
        return max(point - lo, hi - point)

    return {"intercept": a0, "intercept_pm": pm(A, a0), "slope": b0, "slope_pm": pm(B, b0)}


def summarize(rows: list[dict], load_ms: float, engine: str, version: str) -> dict:
    """Every number the report carries. Sizes are in characters, times in milliseconds."""
    times = sorted(r["ms"] for r in rows)
    sizes = [float(r["size"]) for r in rows]
    total_ms = sum(times)
    total_chars = sum(sizes)
    fit = _boot_fit(sizes, [r["ms"] for r in rows])
    return {
        "engine": engine,
        "engine_version": version,
        "documents": len(rows),
        "startup_ms": round(load_ms, 1),
        "total_s": round(total_ms / 1000, 3),
        "chars_total": int(total_chars),
        "size": {
            "median": int(_quantile(sorted(sizes), 0.5)),
            "p10": int(_quantile(sorted(sizes), 0.10)),
            "p90": int(_quantile(sorted(sizes), 0.90)),
            "max": int(max(sizes)) if sizes else 0,
        },
        "ms_per_doc": {
            "median": round(_quantile(times, 0.5), 3),
            "p10": round(_quantile(times, 0.10), 3),
            "p90": round(_quantile(times, 0.90), 3),
            "p99": round(_quantile(times, 0.99), 3),
            "max": round(times[-1], 3) if times else 0.0,
        },
        # The model everything else is derived from: cost = intercept + slope * characters.
        "cost_model": {
            "per_1000_chars_ms": round(fit["slope"] * 1000, 3),
            "per_1000_chars_pm": None if fit["slope_pm"] is None else round(fit["slope_pm"] * 1000, 3),
            "per_document_ms": round(fit["intercept"], 3),
            "per_document_pm": None if fit["intercept_pm"] is None else round(fit["intercept_pm"], 3),
            "confidence": "95%",
            "method": "bootstrap over documents, 2000 resamples, fixed seed",
        },
        "throughput": {
            "documents_per_s": round(len(rows) / (total_ms / 1000), 1) if total_ms else None,
            "chars_per_s": int(total_chars / (total_ms / 1000)) if total_ms else None,
        },
        # The documents that cost the most PER CHARACTER, not the longest ones. This is a diagnostic
        # and it has earned its place: a rule that hits one slot thousands of times in a signature
        # line once cost 688 ms per 1000 characters where the rest of the corpus cost 2, and the
        # only way that was ever going to be noticed is a list like this one.
        "slowest_per_char": [
            {"id": r["id"], "size": r["size"], "ms": round(r["ms"], 2),
             "ms_per_1000": round(r["ms"] / max(1, r["size"]) * 1000, 2)}
            for r in sorted(rows, key=lambda r: -(r["ms"] / max(1, r["size"])))[:5]
        ],
        # NOT an error rate: this code does not know what is in your documents. See the module note.
        "flagged": {
            "documents": sum(1 for r in rows if r["flagged"]),
            "share": round(sum(1 for r in rows if r["flagged"]) / len(rows), 6) if rows else 0.0,
            "note": "share of documents that fired here; not a false-positive rate — "
                    "these documents carry no labels",
        },
    }


def lines(s: dict) -> list[str]:
    """The same numbers for a terminal, in the order they answer questions."""
    cm = s["cost_model"]
    fitted = cm["per_1000_chars_pm"] is not None
    d = s["ms_per_doc"]
    out = [
        f"  documents {s['documents']}, median length {s['size']['median']} characters "
        f"(P10-P90 {s['size']['p10']}-{s['size']['p90']})",
        f"  per document   median {d['median']} ms   P10-P90 {d['p10']}-{d['p90']}   "
        f"P99 {d['p99']}   max {d['max']}",
        # The model is printed only when it was actually fitted. On a handful of documents the
        # numbers still come out, and printing them with a "(95%)" beside them would dress a guess
        # up as a measurement — the one thing this command exists not to do.
        (f"  cost model     {cm['per_1000_chars_ms']} ± {cm['per_1000_chars_pm']} ms per 1000 "
         f"characters, plus {cm['per_document_ms']} ± {cm['per_document_pm']} ms per document "
         f"({cm['confidence']})") if fitted else
        f"  cost model     not fitted: {s['documents']} document(s) is too few to separate the "
        f"per-character cost from the per-document one",
        f"  throughput     {s['throughput']['documents_per_s']} documents/s, "
        f"{s['throughput']['chars_per_s']} characters/s",
        f"  startup        {s['startup_ms']} ms, once per process",
        f"  whole run      {s['total_s']} s",
        f"  dearest doc    {s['slowest_per_char'][0]['ms_per_1000']} ms per 1000 characters "
        f"({s['slowest_per_char'][0]['size']} chars) — against a median of "
        f"{s['ms_per_doc']['median']} ms per document" if s.get("slowest_per_char") else "",
        f"  fired on       {s['flagged']['documents']} of {s['documents']} documents "
        f"({s['flagged']['share']:.2%}) — not an error rate, these documents carry no labels",
    ]
    return [x for x in out if x]


# --- the chart -----------------------------------------------------------------------------------
#
# Hand-written SVG, and it has to stay hand-written: the package declares no dependencies, and a
# chart is not a reason to break that. Everything here is arithmetic and string formatting.

W, H, PAD_L, PAD_B, PAD_T, PAD_R = 760, 420, 64, 48, 56, 20


def _nice(v: float) -> float:
    """A round number at or above `v`, for an axis a human can read."""
    if v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    base = 10 ** exp
    for m in (1, 2, 2.5, 5, 10):
        if m * base >= v:
            return m * base
    return 10 * base


def svg(rows: list[dict], s: dict, title: str = "Time to check one document") -> str:
    xs = [r["size"] for r in rows] or [1]
    ys = [r["ms"] for r in rows] or [0.0]
    xmax = _nice(max(xs))
    ymax = _nice(max(ys))
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B

    def px(x: float) -> float:
        return PAD_L + plot_w * (x / xmax)

    def py(y: float) -> float:
        return PAD_T + plot_h * (1 - y / ymax)

    cm = s["cost_model"]
    a = cm["per_document_ms"]
    b = cm["per_1000_chars_ms"] / 1000.0

    dots = "".join(
        f'<circle cx="{px(r["size"]):.1f}" cy="{py(r["ms"]):.1f}" r="2.6" '
        f'class="{"hit" if r["flagged"] else "dot"}"/>'
        for r in rows)
    grid = "".join(
        f'<line x1="{PAD_L}" y1="{py(ymax * k / 4):.1f}" x2="{W - PAD_R}" y2="{py(ymax * k / 4):.1f}"'
        f' class="grid"/><text x="{PAD_L - 8}" y="{py(ymax * k / 4) + 4:.1f}" class="tick" '
        f'text-anchor="end">{ymax * k / 4:g}</text>'
        for k in range(5))
    xticks = "".join(
        f'<text x="{px(xmax * k / 4):.1f}" y="{H - PAD_B + 20}" class="tick" '
        f'text-anchor="middle">{int(xmax * k / 4)}</text>'
        for k in range(5))
    pm = f" ± {cm['per_1000_chars_pm']}" if cm["per_1000_chars_pm"] is not None else ""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" \
height="{H}" font-family="system-ui, sans-serif">
<style>
  .bg {{ fill: #fbfbf9; }} .ink {{ fill: #1a1a19; }} .muted {{ fill: #6b6a66; }}
  .grid {{ stroke: #e6e4de; stroke-width: 1; }} .tick {{ fill: #8a8880; font-size: 11px; }}
  .dot {{ fill: #3f7fd0; fill-opacity: .45; }} .hit {{ fill: #d9663f; fill-opacity: .55; }}
  .fit {{ stroke: #6b6a66; stroke-width: 1.6; stroke-dasharray: 6 4; fill: none; }}
  @media (prefers-color-scheme: dark) {{
    .bg {{ fill: #1a1a19; }} .ink {{ fill: #ffffff; }} .muted {{ fill: #898781; }}
    .grid {{ stroke: #333230; }} .tick {{ fill: #6b6a66; }}
  }}
</style>
<rect class="bg" width="{W}" height="{H}"/>
<text x="16" y="26" class="ink" font-size="15" font-weight="600">{title}</text>
<text x="16" y="44" class="muted" font-size="11.5">{s['documents']} documents · \
{cm['per_1000_chars_ms']}{pm} ms per 1000 characters ({cm['confidence']}) · \
{s['engine']} {s['engine_version']}</text>
{grid}{xticks}
<line class="fit" x1="{px(0):.1f}" y1="{py(a):.1f}" x2="{px(xmax):.1f}" \
y2="{py(min(ymax, a + b * xmax)):.1f}"/>
{dots}
<text x="{PAD_L + plot_w / 2:.0f}" y="{H - 8}" class="muted" font-size="11" \
text-anchor="middle">document size, characters</text>
<text x="14" y="{PAD_T + plot_h / 2:.0f}" class="muted" font-size="11" \
transform="rotate(-90 14 {PAD_T + plot_h / 2:.0f})" text-anchor="middle">milliseconds</text>
</svg>
"""
