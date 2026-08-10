# Changelog

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
