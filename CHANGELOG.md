# Changelog

Two things are versioned here and they move independently.

**The package** — this file, semantic versioning. **The base** — dated instead of
numbered (`engine_v1_20260731_b1`): its version answers "how fresh", which a
sequence number cannot, and it changes on its own schedule. Which base a build
shipped with is recorded in each entry below and printed by
`aicordon picket version`.

## 0.1.0 — unreleased

First release. Base `20260731`.

### The detector

* `aicordon picket scan` — indirect prompt injection by signature: no model, no
  network, no dependencies. Working point measured on sources and payloads that
  took no part in building it: **0.03% false alarms**, **20–32%** of the
  injections caught, on one CPU core at **2.17 ± 0.07 ms per 1000 characters**.
* Findings carry offsets, so a payload can be cut out or masked rather than the
  document dropped. `--span-pad` trades how much of the payload is covered
  against how much innocent text goes with it.
* Threat names come from the base rather than from the code, so a name printed a
  year ago can still be matched to the rule that produced it.

### The shell

* One command, `aicordon`, with the product as the first argument; the product,
  the command and the input are filled in when that can be done unambiguously,
  and an implicit choice is signed in the report.
* `scan`, `check`, `explain`, `coverage`, `version`, `bench`.
* Exit codes: `0` nothing found · `1` findings · `2` usage error · `3` engine
  unavailable. There is no verdict "clean" and no `is_safe` field — at this
  recall a field you could believe in reverse would build a falsehood into the
  API.
* `bench` measures the detector on your own documents and reports the cost model
  with its intervals, a JSON report and an SVG chart — no dependencies involved.

### The library

* `picket.load()`, `check`, `check_all`, `reports`; `acheck`/`acheck_all` for
  code in an event loop; `Report.to_json`/`from_json`. Thread-safe: one detector
  serves several threads and returns what the same calls return in sequence.
* `py.typed`, and no dependencies at all — nothing to resolve against whatever
  your framework pins.

### Not in this release

* `aicordon.intent`, the semantic detector: the API behind it does not exist
  yet, and a stub in a release would read as "get a key and it works".
* SARIF output, and adapters for AI frameworks.
