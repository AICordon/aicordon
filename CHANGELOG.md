# Changelog

## 0.3.0 — 2026-08-13

### A rule base built from the two axes of an injection, not from whole patterns

Until now a rule matched a pattern as a whole: one conjunction had to land on the technique **and**
on the goal at once, so each rule sat on one kind of injection. The new base separates the two. One
set of parts recognises the technique — a forged frame, a revoked instruction, a poisoned retrieval
snippet — and another recognises what the injection is after: disclose, exfiltrate, escalate. A
finding requires one of each. Parts combine, so `m` techniques and `k` goals cover `m·k` kinds of
injection instead of the handful a hand-built conjunction can reach.

**Measured on an open corpus anyone can rerun.** [Quadrat-IPI
v1.0.1](https://huggingface.co/datasets/mihailgribov/quadrat-ipi) is published with its documents,
its labels and its harness: 8378 injections and 31 365 clean documents, here the half of the corpus
that took no part in building the base. Its grid is 92 cells of "technique × goal" over three
carriers — e-mail, document, web page — so a number can be read per kind of attack rather than as a
single average. Margins are ±1.96 standard errors.

| | 0.2.0 | 0.3.0 |
|---|---|---|
| **detection** | **12.52 ± 0.71%** | **16.23 ± 0.79%** |
| **false positives** | **0.086 ± 0.032%** | **0.092 ± 0.034%** |
| detection — e-mail / document / web | 13.22 / 12.00 / 12.26% | 16.20 / 16.02 / 16.54% |
| false positives — e-mail / document / web | 0.038 / 0.067 / 0.153% | 0.086 / 0.086 / 0.105% |
| cells of the grid covered at 50% or better | 6 of 92 | 8 of 92 |
| rules in the base | 25 | 313 |

Paired over the same documents, **detection rises by 3.71 ± 0.51 percentage points**: 390 injections
are caught only by this version, 79 only by the previous one.

**False positives are level, not lower** — 0.086% against 0.092%, intervals overlapping. They fall
on web pages (0.153% → 0.105%) and rise on e-mail and documents (0.038% → 0.086%, 0.067% → 0.086%).
The new rules do not yet use the aperture field that 0.2.0 introduced; that is where the next
reduction is expected to come from.

**What did not improve is breadth.** Eight cells of 92 are covered at 50% or better, against six.
The base is still strongest where an injection asks for something to be *revealed*, and weak where
it swaps the task or claims authority without naming it. Two whole families stay out of reach —
a bare command and a plausible errand — because both are defined by what is *absent* from the text,
and a signature can only assert what is present.

### Spans point at the start of the payload

The reported span now begins exactly at the start of the injected text (median offset 0.000 of the
payload length, against 0.046 before) and covers more of it (median 0.598 against 0.558; IoU 0.484
against 0.466). Precision of the span is marginally lower — 0.845 against 0.860.

### Speed

**102 documents per second against 114**, median 5.48 ms per document against 5.15. The base holds
313 rules instead of 25, but the time is spent walking the text, not checking rules. Loading the
base costs 85 ms instead of 18, once per process.

### Compatibility

The base declares schema 2 and carries no aperture fields, so it scans exactly as a schema 1 base
would. The library and CLI surfaces are unchanged. The base in use is printed by
`aicordon picket version` and in the scan banner: `lexical 20260813`.

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
