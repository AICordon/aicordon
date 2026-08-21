<!--
STAGING COPY of the integration card for the Haystack catalogue.

When submitting: copy this file to `integrations/aicordon-haystack.md` in a fork of
`deepset-ai/haystack-integrations` and open a PR. Schema confirmed 2026-08-19 from that repo's
README:
  - required frontmatter: layout, name, description, authors (>=1 with a name), type
  - at least one of `pypi` or `repo` must be present for a merge
  - allowed `type`: Document Store | Model Provider | Data Ingestion | Monitoring Tool |
    Evaluation Framework | Custom Component | Tool Integration | Other
  - one card per PACKAGE, not per component: `aicordon-haystack` ships two components under one card.

SUBMIT ONLY AFTER `aicordon-haystack` IS ON PyPI: at least one of `pypi`/`repo` must resolve for a
merge, and a card pointing at a package that is not there yet is a rejection asking to happen. The
order is: merge the integration branch into `main` and push (the `repo` link and the README links
inside this card resolve off `main`), publish `aicordon` >= 1.1.0, publish `aicordon-haystack`, then
open this PR.

`logo` is optional and is deliberately not set: a logo lives in the catalogue repository, not ours,
and adding one is a separate PR that can follow at any time.
-->
---
layout: integration
name: AI Cordon Picket
description: Detect prompt injection in what an LLM is given - documents at ingest and the turn it answers - with a local rule base, no GPU or network.
authors:
    - name: Mike Gribov
      socials:
        github: mihail-gribov
pypi: https://pypi.org/project/aicordon-haystack
repo: https://github.com/AICordon/aicordon
report_issue: https://github.com/AICordon/aicordon/issues
type: Custom Component
version: Haystack 3.0
toc: true
---

# AI Cordon Picket for Haystack

Check what an LLM is given for prompt injection - in both places it can arrive.

| component | reads | with |
|---|---|---|
| `PromptInjectionFilter` | **material**: documents at ingest, before they are chunked and embedded | Picket's `ipi` rules |
| `PromptInjectionGuard` | **the request**: the turn the model is about to answer | Picket's `dpi` rules |

The two rule sets are disjoint and neither is a stricter version of the other, so the choice is not
a sensitivity knob. It follows from the role the text plays in the prompt: material is what the
model works on, a request is what it answers. Your code always knows which is which, because it puts
them in different places when it assembles the call.

The check is a rule, not a model: no GPU, no network, no key, a few hundred kilobytes of base, and a
fraction of a millisecond on one core for a turn of ordinary length.

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

The component sits **before the splitter**: cutting an injection here removes it from the chunks,
the embeddings and the store at once, and no offsets have to be reconciled across chunk boundaries.
Modes: `annotate`, `blank` (keeps the length), `mask`, `redact` (default), `drop`, `fail`. What is
cut is the whole line that holds the span, not the matched characters alone.

## The turn the model answers

```python
from haystack_integrations.components.validators.aicordon import PromptInjectionGuard

pipe.add_component("guard", PromptInjectionGuard())          # mode="drop" is the default
pipe.connect("prompt.messages", "guard.messages")
pipe.connect("guard.messages", "llm.messages")               # the model is called on this path
pipe.connect("guard.blocked", "refusal.messages")            # and not on this one
```

**Two sockets, and only one of them ever carries a value.** On a flagged exchange the component
returns `blocked` and no `messages` key at all, so the generator is not called with a shortened
message list - it is not called. Connect `blocked` to whatever should answer the user instead. The
decision is for the exchange, not for one message. This side never edits a turn: a typed jailbreak
is not spliced into anything - it *is* the turn - so there is nothing to cut out of it.

## Measured

The question is never the detector's recall - that is published with the detector - but what the
pipeline delivers with the component in it and without.

**Material** - [Quadrat-IPI v1.0.1](https://huggingface.co/datasets/mihailgribov/quadrat-ipi),
1000 injected + 1000 clean documents, `mode="redact"`:

| | whole corpus | injections that ask the model to reveal something |
|---|---|---|
| payload reaches the store intact, without the filter | 100% | 100% |
| payload reaches the store intact, with it | **85.4%** | **42.8%** |
| payload gone without a trace | 13.1% | **52.3%** |
| clean documents dropped or trimmed | 0 of 1000 | 0 of 1000 |

**The request** - held-out forum jailbreaks from
[TrustAIRLab in-the-wild](https://huggingface.co/datasets/TrustAIRLab/in-the-wild-jailbreak-prompts)
(537) against 20 000 real [WildChat](https://huggingface.co/datasets/allenai/WildChat-1M) turns,
`mode="drop"`:

| | |
|---|---|
| attacks reaching the model, without the guard | 100% (537 of 537) |
| attacks reaching the model, with it | **65.2%** |
| turns not answered, out of 20 000 real ones | 0.070% (14) |
| verdicts differing from the bare detector | **0** |

Adding the component costs **0.39 ms for a turn of median length**; loading the base costs 15 ms,
once per process. No findings does not mean no injection.

## License

Apache-2.0, the same as the detector it wraps.
