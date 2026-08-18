# What a check costs: time and memory, in full

The README states the two figures and moves on. This page is where they come from, how they were
fitted, and how far they can be trusted.

Every figure here was measured on one core of an Intel Core i9-12900KF, Python 3.12 on Linux. The
constant is a property of that machine — it drifts by a tenth of a millisecond or so with whatever
else the machine is doing — and yours will differ; what carries over is the shape: linear in the
size of the document, no GPU, no network. Every figure on this page comes from the release run of
the version it describes, measured by the commands quoted here.

## Time

**The cost is linear in the size of the document** — 1.85 ± 0.07 ms per 1000 characters through
`check()`, the call you actually make, with a per-document constant consistent with zero, and it
does not care what the document contains. The two panels are measured separately, on 4 800 real
documents: **1.69 ± 0.10** ms per 1000 characters without an injection, **1.88 ± 0.08** with one
(95%). The difference is **0.19 ± 0.12**, and it is the corpora rather than the verdict: the cost
follows the number of dictionary hits, and the injected half is mail and news while the clean half
is a different pair of pools.

**The mode does not change it.** Both were timed on the same documents in the same run: the
difference is **−0.5%** (95% interval −0.7 to −0.4) — nothing you would ever budget for. One
figure covers both.

**Nothing degrades in TIME on a long page**: the most expensive document in the run below is 96 KB
and costs 1.84 ms per 1000 characters, the same as a one-kilobyte letter.

The spread at any given size comes from the text itself: prose full of the ordinary words the tool
must look at costs more than the same length of text with none. That is why the per-document figure
is a range rather than a single number.

## The tool carries the measurement

So you do not have to believe the numbers above on this machine — run them on yours, with the same
statistics and the same intervals:

```console
$ aicordon picket bench ./docs --repeat 3 --report bench.json --chart bench.svg
  documents 1999, median length 1907 characters (P10-P90 646-5677)
  per document   median 3.625 ms   P10-P90 1.353-10.108   P99 31.158   max 186.64
  cost model     1.9 ± 0.077 ms per 1000 characters, plus -0.087 ± 0.199 ms per document (95%)
  throughput     177.3 documents/s, 534508 characters/s
  base load      14.9 ms, once per process (the whole command costs more: interpreter and imports on top)
  fired on       152 of 1999 documents (7.60%) — not an error rate, these documents carry no labels
```

That last line is a property of the corpus, not of the detector: those 2 000 documents are an
INJECTED pool, so a fraction of them firing is recall showing through rather than a false-alarm
rate. On your own traffic the same line means something else again — which is exactly why the tool
declines to name it.

The same figure comes out of that command on a different corpus — **1.90 ± 0.08** ms per 1000
characters over 1 999 documents — and that agreement, between two corpora and two ways of timing,
is what the number rests on.

The chart is SVG, drawn without a plotting library — a package with no dependencies has none to draw
with.

## Memory

Memory is the exception, and it is the one figure that is not flat. It has the same shape as the
time — a base plus a slope — and it was fitted the same way, over 12 sizes and 36 runs:

**peak RSS = 48.5 ± 1.4 MB + 0.269 ± 0.006 MB per KB of the document** (95%)

which is about 270 times the size of the text on top of the base, because the normalised copy, the
offset map, the token list and the hit list are all alive at once:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/AICordon/aicordon/main/docs/memory-dark.png">
  <img alt="Memory to check one document: peak RSS grows linearly with document size, 48 MB plus 0.27 MB per KB" src="https://raw.githubusercontent.com/AICordon/aicordon/main/docs/memory.png">
</picture>

The peak is set by the LARGEST document, not by their number: documents are checked one at a time,
so a million small files cost what one of them costs. A megabyte-long page is what to watch: about
275 MB for the text on TOP of the 48.5 MB base, so a peak around 325 MB — roughly seven times the
base, and that is the figure a container limit has to be set against. A second detector for the
other mode adds about 22 MB on top: the modes cost the same to RUN, but each `load()` builds its
own engine.

## Where the floor is

Picket pays its floor per PROCESS, not per call:

| | floor | per document |
|---|---|---|
| **as a library** | none — the detector is raised once and then called | ~1.9 ms for a 1 KB letter |
| **as the `aicordon` command** | **105 ms** to start | the same ~1.9 ms |

So an agent loop, a server or a queue pays nothing per check beyond the text itself. That is what
makes the typed end affordable at all: a check on the way in, on every turn, that costs a couple of
milliseconds of the CPU you already have and adds nothing to the latency the user feels.

A pre-commit hook or a CI step pays the start once and then scans as fast as it reads — worth doing,
with one caveat that is about the CONTENT and not the cost: a repository of security writing is the
corpus this tool argues with, see Limits in the README.

The arithmetic: 500 documents of 2.6 KB on average take 2.78 s in one run, which is 5.3 ms each on
top of the start — the same 1.9 ms per 1000 characters, at that size.

Both figures come from `experiments/40_prefilter/floorbench.py`, the same run as the rest of this
page. What you must not do is spawn the command per file — that pays the floor 500 times
over.
