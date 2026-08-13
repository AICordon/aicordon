# Changelog

## 0.3.0 — 2026-08-13

### A new base: a third more injections caught, at the same cost

Both versions were run through the same scanner on the same documents — [Quadrat-IPI
v1.0.1](https://huggingface.co/datasets/mihailgribov/quadrat-ipi), an open corpus published with its
harness: 16 800 injections and 63 000 clean documents. The full report, with the breakdown by carrier
and by kind of attack, is in [docs/eval](docs/eval/quadrat-ipi-v1.0.1.md). Margins are ±1.96
standard errors.

| | 0.2.0 | 0.3.0 |
|---|---|---|
| **detection** | **12.46 ± 0.50%** | **16.39 ± 0.56%** |
| **false positives** | **0.086 ± 0.023%** | **0.098 ± 0.024%** |
| rules in the base | 25 | 313 |

Paired over the same documents, **detection rises by 3.93 ± 0.37 percentage points**: 821 injections
are caught only by this version, 161 only by the previous one. **False positives are level, not
lower** — the intervals overlap.

**Where it is still blind is unchanged.** The base is strongest where an injection asks for something
to be *revealed*, and weak where it swaps the task or claims authority without naming it. A bare
command and a plausible errand stay out of reach: both are defined by what is *absent* from the text,
and a signature can only assert what is present.

### Cutting the injection out takes more of it with it

The span the report hands you now starts exactly where the injected text starts (median offset 0.000
of the payload, against 0.046 before) and covers more of it — median 0.598 against 0.558, IoU 0.484
against 0.466. Slightly more of the honest text falls inside the span in exchange: precision 0.845
against 0.860.

### Speed and memory: no measurable change

Twelve times the rules cost nothing that can be measured — the time goes on reading the text, not on
checking rules. Measured through the shipped command on the same 1 999 documents: 2.46 ± 0.39 ms per
1000 characters against 2.40 ± 0.14, a median of 4.69 ms per document against 4.70, peak RSS of
47.4 ± 1.5 MB + 0.269 ± 0.007 MB per KB against 47.0 ± 1.4 MB + 0.269 ± 0.007. Every pair overlaps
inside its interval.

### Nothing to change on your side

The library and the command work exactly as before — same calls, same flags, same report. Upgrading
is `pip install -U aicordon`. Which base is running is printed by `aicordon picket version` and in
the scan banner: `lexical 20260813`.

## 0.2.0 — 2026-08-10

### Rules got more expressive

A rule can now constrain not only *what* it matches but *where* the parts of a match sit relative to
one another. Matches whose parts are scattered across a document no longer count.

**Fewer false alarms, the same catches, the same speed.** On the same evaluation half the previous
base was measured on: **26 false positives out of 101 386, down from 32**, with recall unchanged —
no detection is lost. Timing is unchanged as well: 1.591 ± 0.255 ms per 1000 characters against
1.594 ± 0.255 for 0.1.0, measured on the same documents and the same core.

If you were splitting documents into overlapping windows before handing them to Picket, you no
longer need to: the detector does the equivalent itself, in a single pass over the text.

### Base format: schema 2

The rules gained a field, so a base carrying it declares schema 2.

* A **schema 1 base loads unchanged** in this version and scans exactly as it did.
* A **schema 2 base is refused by 0.1.x** rather than read — a rule set whose working point was
  measured with the new field would behave differently in a tool that cannot see it, and the
  numbers on the box would then belong to a different detector.

### Spans are tighter

The reported span of a finding is now the tightest region covering the match, rather than one
assembled from each part independently. The old choice could anchor a span on a fragment far from
the rest of the match. Verdicts are unaffected; on our corpus 8.6% of spans narrow, some
considerably.

### The recall figure was re-derived

The previous base published recall as 32.37%. That figure came from a measurement pipeline
assembled differently from the one that ships; scanning the shipped rules directly gives the number
the base now reports. **The rules did not change — only how they were measured.** The wording in the
README stays conservative on purpose.

### Compatibility

The rules themselves are the 25 frozen on 2026-07-31, unchanged. The library and CLI surfaces are
unchanged. Verified on 12 000 documents: no verdict differs from 0.1.0.

## 0.1.0 — 2026-08-02

First release: the signature detector, the CLI, the library interface, `bench`, and the rule base as
a single binary file.
