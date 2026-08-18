# The library interface

The interface an adapter is written against — not the argument parsing. The README shows the three
calls you need to start; this page is the rest of the contract.

```python
from aicordon import picket
from aicordon.picket import EngineUnavailable, Report, Severity

det = picket.load()                    # raised once, then called as often as you like
det = picket.load(mode="dpi")          # the same call for the other end
rep = det.check(text)
if rep.flagged:
    print(rep.severity, rep.threats, rep.span)

for rep in det.check_all(documents):   # streamed, input order preserved
    ...
```

A detector is fixed to its mode at `load()` and says so in `describe()`. That is deliberate: the
mode is a property of the channel you are guarding, so it belongs to the object you hand to that
part of the code, not to every call site inside it. An unknown mode is a `ValueError` at load, not
a silent fallback to the default.

`rep.severity` is `"high"`, `"medium"` or `"low"` — the worst of the findings — and `None` when
nothing fired, which is the only thing that ever distinguishes a quiet report. It grades the
TECHNIQUE, not the confidence: sending content outside is high whatever else is true, and there is
no score behind it to threshold. Compare it, do not do arithmetic on it; `Severity.HIGH` and the
rest are importable from `aicordon.picket`.

Four properties that decide whether this can sit inside somebody else's runtime:

* **one instance, many callers.** `load()` is paid once, and every `check` after it costs the text
  alone. One detector per process and per mode, not per request.
* **thread-safe.** Measured, not assumed: one instance called from eight threads over 400 documents
  returns exactly what the same calls return in sequence. Safe under a thread pool or a parallel
  runnable.
* **streaming.** `check_all` yields as it goes and preserves input order, so a batch of 10 000
  documents does not have to be held in memory to be matched up afterwards.
* **failure is an exception, never an empty result.** If the base cannot be loaded you get
  `EngineUnavailable`, because embedding code reads silence as "no injections", and a broken
  detector would then quietly become a verdict.

Three more things an integration usually has to build itself, and here does not:

```python
rep = await det.acheck(text)            # CPU work off the event loop; acheck_all for batches
d = rep.to_json()                       # plain JSON, no library types
same = Report.from_json(d)              # and back — a report survives a queue or a file
```

The package ships `py.typed`, so your type checker sees the same signatures we do, and it declares
no dependencies at all — nothing to resolve against whatever pydantic or aiohttp your framework
pins.

## Spans

Spans are offsets into the original text, and every finding carries the evidence that produced it.
`finding.span` is one place; **`rep.span` is the hull of them all** — the answer to "whereabouts in
this document", not a region to excise. Cut by findings, not by the hull.

The strictness is yours to set, with one knob: `span_pad=` in `picket.load()`, spelled `--span-pad`
on the command line. Zero — the default — is the measured optimum. Negative values tighten the span
towards the bare anchor: less of the surrounding text, less of the payload. Positive values widen
it: the whole payload with room to spare, useful when the span is fed to something more expensive to
read, at the cost of carrying more innocent text along.

The full detector, when it ships, answers to the same names, so code written against this interface
does not change.
