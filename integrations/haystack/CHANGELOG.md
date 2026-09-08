# Changelog

## 0.2.0 — 2026-09-08

Requires `aicordon>=1.2.0`. **Both components now default to `mode="passthrough"`**: they read the text,
record what they found beside it, and pass it on untouched. They used to act by default — the filter
edited the document, the guard held a flagged exchange back.

Breaking for a pipeline that named no mode, and for nobody else: documents are no longer edited, and
a flagged exchange now reaches the generator with the finding in its metadata instead of coming out
of `blocked`. Both behaviours are one argument away:

    PromptInjectionFilter(mode="mask")
    PromptInjectionGuard(mode="drop")

The reasoning is in the detector's own changelog under 1.2.0, along with the modes and what each
does. Nothing about detection changed: the base, the rules and the numbers below are the same.

Watch the serialisation when you change a mode — a pipeline saved to YAML carries the mode
explicitly, but a component built before this release and reloaded after it reads back the new
default. See `NOTES.md`.

## 0.1.1 — 2026-08-26

Requires `aicordon>=1.1.1`, and that is the whole release: the wrapper is unchanged, the policy it
calls was fixed.

`aicordon.guard` grew a finding to the LINE holding it before cutting. That assumes the payload
occupies one line — true of a corpus, false of a page that arrived hard wrapped, where the cut took
the first line and left the rest of the same sentence in the document. What stays behind is a
working instruction, not debris: on a document whose payload told the model to print a token, a
model printed the token WITH `mode="redact"` in place. Since 1.1.1 the cut follows the whole
utterance across the lines a wrapper broke it over.

Nothing here changes what is detected. The base, the rules and the published numbers are the same:
recall 16.4%, FPR 0.098% on the same corpus build, reproduced under 1.1.1 to the digit.

## 0.1.0 — 2026-08-21

First release. Two components, one per place a pipeline holds text a model is about to read.

* **`PromptInjectionFilter`** — `haystack_integrations.components.preprocessors.aicordon`. Reads
  documents at ingest with the `ipi` rules, before chunking and embedding. Six modes (`annotate`,
  `blank`, `mask`, `redact`, `drop`, `fail`); the cut takes the whole line holding the span, or the
  sentence when the line is long. (Since 0.1.1 it takes the whole utterance instead — see above.) Two output sockets, so a dropped document goes to quarantine
  instead of disappearing.
* **`PromptInjectionGuard`** — `haystack_integrations.components.validators.aicordon`. Reads the
  message list on its way into the generator with the `dpi` rules. The decision is for the whole
  exchange: when it fires, `run` returns `blocked` and **no** `messages` key, which is how a
  pipeline branches — the generator is not called at all. This side never edits a turn.

Both are thin; the policy lives in `aicordon.guard`, which ships with the detector. Hence
`aicordon>=1.1.0`: against 1.0.0 the install resolves and the import fails.

Measured on the pipeline, not on the detector:

| | |
|---|---|
| injected payload reaching the store, `mode="redact"` | 85.4% with the filter, 100% without |
| clean documents damaged | 0 of 1000 |
| held-out forum jailbreaks reaching the generator, `mode="drop"` | 65.2% with the guard, 100% without |
| real WildChat turns left unanswered | 0.070% (14 of 20 000), an upper bound |
| **verdicts differing from the bare detector** | **0** |
| cost per turn of median length | 0.39 ms; 15 ms once, to load the base |

The last row licenses the others: a wrapper that loses or adds text makes every number above it
meaningless.
