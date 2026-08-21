# AI Cordon Picket for Haystack

Check what an LLM is given for prompt injection — in both places it can arrive:

| component | reads | with |
|---|---|---|
| `PromptInjectionFilter` | **material**: documents at ingest, before they are chunked and embedded | Picket's `ipi` rules |
| `PromptInjectionGuard` | **the request**: the turn the model is about to answer | Picket's `dpi` rules |

The two rule sets are disjoint, and neither is a stricter version of the other — this is not a
sensitivity knob. Pick by role: material is what the model works on, the request is what it answers.
Your code knows which is which; it puts them in different places when it assembles the call.

The check is a rule, not a model: no GPU, no network, no key, a few hundred kilobytes of base, and a
fraction of a millisecond per turn on one core — see [what it costs](#what-it-costs).

## Installation

```bash
pip install aicordon-haystack
```

## Material at ingest

```python
from haystack import Pipeline
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.writers import DocumentWriter
from haystack_integrations.components.preprocessors.aicordon import PromptInjectionFilter

pipe = Pipeline()
pipe.add_component("ipi_filter", PromptInjectionFilter(mode="redact"))
pipe.add_component("splitter", DocumentSplitter(split_by="word", split_length=200))
pipe.add_component("writer", DocumentWriter(document_store=store))

pipe.connect("converter.documents", "ipi_filter.documents")
pipe.connect("ipi_filter.documents", "splitter.documents")
pipe.connect("splitter.documents", "writer.documents")
pipe.connect("ipi_filter.rejected", "quarantine.documents")   # optional; nothing disappears quietly
```

The component sits **before the splitter**: a cut here takes the injection out of the chunks, the
embeddings and the store at once, with no offsets to reconcile across chunk boundaries.

### What it does with a finding

| `mode` | the document | the length |
|---|---|---|
| `annotate` | indexed unchanged, the finding recorded in metadata | unchanged |
| `blank` | every character of the block becomes `blank_char` (default `*`) | **preserved** |
| `mask` | the block is replaced by `mask_with` | changes |
| `redact` *(default)* | the block is cut out | changes |
| `drop` | not indexed; it comes out of the `rejected` socket | — |
| `fail` | the run stops on the first finding | — |

`blank` is for pipelines that carry offsets, page maps or diffs downstream and cannot have a
document change length under them.

The cut takes **the line holding the span**, or the sentence when that line runs past 1500
characters: the span points at the injection, but what must leave the index is the whole utterance.
Measured on 1200 documents: the payload is gone entirely in 91% of catches, at a median 11.6% of the
document removed.

## The turn the model answers

```python
from haystack_integrations.components.validators.aicordon import PromptInjectionGuard

pipe.add_component("guard", PromptInjectionGuard())          # mode="drop" is the default
pipe.connect("prompt.messages", "guard.messages")
pipe.connect("guard.messages", "llm.messages")               # the model is called on this path
pipe.connect("guard.blocked", "refusal.messages")            # and not on this one
```

**Two sockets, one value.** On a flagged exchange `run` returns `blocked` and no `messages` key, so
the generator is not called at all. Connect `blocked` to whatever answers the user instead.

The decision is for the **exchange**, not for one message: drop the offending turn and the model
answers the one before it.

### What it reads, and what it does with a finding

`roles` maps a role to a rule set, default `{"user": "dpi"}`. `assistant` is the model's own text,
`system` the operator's. `tool` carries material and switches on with
`roles={"user": "dpi", "tool": "ipi"}` — measure your own tool output first: over live chat text the
`ipi` rules raise eight times as many alarms as over documents, and they fire on command lists and
code, which is what a tool result looks like.

| `mode` | the exchange |
|---|---|
| `drop` *(default)* | routed to the `blocked` socket; the model is not called |
| `annotate` | passed through, with the finding in each read message's metadata |
| `fail` | the run stops with `InjectionFound` |

No mode edits a turn, and asking for one raises. The cut above is fitted to an instruction spliced
into a document; a typed jailbreak is not spliced into anything — it *is* the turn, and cutting it
leaves the rest of the attack in place.

## What lands in the metadata

Written on **every** document and every message whose role is read, so "checked and clean" is
distinguishable from "never checked". A role outside the map gets no fields — a third, distinct
fact.

```python
{"ipi_flagged": False, "ipi_action": "none", "ipi_base": "20260817"}
{"ipi_flagged": True,  "ipi_action": "redact", "ipi_base": "20260817",
 "ipi_threats": ["IPI/Secret.Reveal.B"], "ipi_spans": [[812, 947]], "ipi_removed_chars": 163}

{"picket_flagged": True, "picket_action": "drop", "picket_base": "20260817",
 "picket_threats": ["DPI/Policy.Cancel.M"], "picket_spans": [[0, 41]]}
```

Findings are also logged through Haystack's own logger at `warning`, so the level is yours to set.

## Measured

Not the detector's recall — that ships with the detector — but what the pipeline delivers with the
component and without.

**Material.** [Quadrat-IPI v1.0.1](https://huggingface.co/datasets/mihailgribov/quadrat-ipi),
1000 injected and 1000 clean documents, `mode="redact"`; how much of a planted payload still reaches
the store:

| | whole corpus | injections that ask the model to **reveal** something |
|---|---|---|
| payload reaches the store intact, without the filter | 100% | 100% |
| payload reaches the store intact, with it | **85.4%** | **42.8%** |
| payload gone without a trace | 13.1% | **52.3%** |
| clean documents dropped or trimmed | 0 of 1000 | 0 of 1000 |

Both columns matter: the first is an arbitrary stream, the second is where the rule is strong. A
document cost 8.3 ms in that run — documents are long, and cost follows length.

**The request.** Held-out forum jailbreaks from
[TrustAIRLab in-the-wild](https://huggingface.co/datasets/TrustAIRLab/in-the-wild-jailbreak-prompts)
(537, near-duplicates of the fitting half removed) against 20 000 real user turns from
[WildChat](https://huggingface.co/datasets/allenai/WildChat-1M), `mode="drop"`:

| | |
|---|---|
| attacks reaching the model, without the guard | 100% (537 of 537) |
| attacks reaching the model, with it | **65.2%** |
| turns not answered, out of 20 000 real ones | 0.070% (14) |
| verdicts differing from the bare detector | **0** |

WildChat carries no attack labels and real jailbreaks sit inside it, so "turns not answered" is an
upper bound on the cost to a real user, not a false-alarm rate. The detector's working point, on a
labelled pool, is in its report.

Reproduce both with `eval/measure.py` and `eval/measure_dialog.py`.

## What it costs

Adding the component to a pipeline costs **0.39 ms for a turn of median length**, and 1.65 ± 0.03 ms
averaged over ordinary traffic — 3000 real WildChat turns, each timed five times
(`eval/costturn.py`). Loading the base costs 15 ms, once per process.

The average is four times the median: cost follows turn length, and a chat pool has a long tail.
Find your row:

| turn length | turns in the pool | cost |
|---|---|---|
| under 200 characters | 1943 | 0.30 ms |
| 200–500 | 411 | 0.74 ms |
| 500–1500 | 321 | 1.62 ms |
| 1500–4000 | 182 | 4.09 ms |
| over 4000 | 143 | 13.20 ms |

Cost drifts with machine load. These were taken in one run by one procedure — the only way two
figures compare.

No findings does not mean no injection.

## License

Apache-2.0, the same as the detector it wraps.
