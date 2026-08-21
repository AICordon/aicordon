# Changelog

## 0.1.0 — 2026-08-21

First release. Two components, one for each place a Haystack pipeline holds text a model is about to
read.

* **`PromptInjectionFilter`** — `haystack_integrations.components.preprocessors.aicordon`. Reads
  documents at ingest with Picket's `ipi` rules, before they are chunked and embedded. Six modes
  (`annotate`, `blank`, `mask`, `redact`, `drop`, `fail`); what is cut is the whole line holding the
  span, or the sentence when the line is long. Two output sockets, so a dropped document goes to
  quarantine instead of disappearing.
* **`PromptInjectionGuard`** — `haystack_integrations.components.validators.aicordon`. Reads the
  message list on its way into the generator with the `dpi` rules. The decision is for the whole
  exchange: on a flagged one the component returns `blocked` and **no** `messages` key at all, which
  is how a Haystack pipeline branches — the generator is not called with a shortened list, it is not
  called. This side never edits a turn.

Both are thin: the policy lives in `aicordon.guard`, which ships with the detector. Hence the
requirement `aicordon>=1.1.0` — 1.0.0 has no such module, and against it the install resolves while
the import fails.

What was measured, on the pipeline rather than on the detector:

| | |
|---|---|
| injected payload reaching the store, `mode="redact"` | 85.4% with the filter against 100% without |
| clean documents damaged | 0 of 1000 |
| held-out forum jailbreaks reaching the generator, `mode="drop"` | 65.2% with the guard against 100% without |
| real WildChat turns left unanswered | 0.070% (14 of 20 000), an upper bound |
| **verdicts differing from the bare detector** | **0** |
| cost added to a turn of median length | 0.39 ms; 15 ms once, to load the base |

The last row of the block is the one that licenses the others: a wrapper that loses or adds text
would make every number above it meaningless.
