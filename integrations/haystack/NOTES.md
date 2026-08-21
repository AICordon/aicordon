# Haystack: the contract, established from the sources

Checked 2026-08-13. The clone in `upstream/` at `ba92ec9` is **3.1.0-rc0**, i.e. the development
branch; the last RELEASED version is **v3.0.0** (2026-07-20). The wrapper is written against 3.0.x,
and the clone is what tells us whether the contract is drifting by 3.1.

Repository: `deepset-ai/haystack`, Apache-2.0, 26 201 stars. The catalogue of third-party
integrations is a separate repository, `deepset-ai/haystack-integrations` (a card via PR); what
deepset maintains itself lives in `haystack-core-integrations`.

## What a component is obliged to do

The source of truth is the docstring of `haystack/core/component/component.py`, where this is said
outright.

* The class is marked `@component`.
* **`run()`** is mandatory; output types are declared with `@component.output_types(...)`, and a
  `dict` with those same keys is returned.
* **`__init__` must be cheap** — it is called when the pipeline is assembled and validated. Heavy
  initialisation goes into the optional `warm_up()`, which the pipeline calls before a run.
* **`__init__` parameters must be primitives** (strings, numbers, and lists and dicts of them).
  Objects and functions are forbidden: the parameters have to be JSON-serialisable, or the pipeline
  can be neither saved nor loaded. If an object is needed, take a string with its import path and
  resolve it inside.
* **Do not modify the input in place**: work on a copy and return that (`dataclasses.replace` for a
  single field, `deepcopy` for anything richer). Otherwise the edit leaks into other branches of the
  pipeline.

## What follows for us

1. The detector is heavy state (a 376 KB base, ~17 ms to load): raise it in `warm_up()`, not in
   `__init__`. Otherwise the cost is paid on every pipeline assembly, validation included.
2. Pass only strings into `__init__`: the mode (`redact` / `drop` / `annotate`), the metadata
   prefix. No "hand the detector object in here" — that breaks saving the pipeline.
3. Copy documents before editing their text: in an indexing pipeline the same list may go into a
   second branch.
4. Give the component two outputs — the clean stream and what was rejected. Haystack's connections
   are named, so the rejected pile can be sent to a store of its own with one `connect` line instead
   of vanishing quietly.

## Where we sit

Two places, one per role the text plays in the prompt.

**Material** — the indexing pipeline: `converter → (our component) → cleaner → splitter → embedder →
writer`. We go BEFORE the splitter: the injection that is cut then reaches neither the embeddings
nor the store, and no chunk boundaries have to be stitched together.

**The request** — the chat pipeline: `prompt builder → (our component) → chat generator`, with a
second wire `blocked → whoever answers instead of the model`. We go RIGHT NEXT to the generator, on
the message list that is about to enter it: everything between the check and the call is one more
place where the text could change.

## Traps the mock-up caught (2026-08-13)

1. **Settings are lost silently when a pipeline is saved.** Without a `to_dict` of its own, Haystack
   restores parameters through `getattr(obj, "<parameter name>")`, and where the attribute is
   missing it **substitutes the default from the signature** and says nothing. A component built
   with `mode="annotate"` came back out of YAML as `redact`. The cure: keep the parameters on the
   object under those same names AND declare `to_dict`/`from_dict` via
   `default_to_dict`/`default_from_dict`. Covered by a YAML round trip in the tests.
2. **The order of chunks out of a store is not guaranteed**, and `split_overlap` repeats the tail of
   the previous chunk. A measurement that glued chunks back together reported 92.5% where the answer
   is 100% because of it. The acceptance measurement now has no splitter in it at all: it stands
   AFTER us and cannot affect the result.
3. **Logging is not a mode.** It is wanted under `drop` as much as under `annotate`, so it goes
   through `haystack.logging` at `warning` level rather than being a value of the parameter.

## What carries over to LlamaIndex or LangChain

The policy (`aicordon.guard`) carries over as it is: the modes, where the cut ends and the metadata
are all in there. A wrapper is the translation of the host's document type into a string and back,
plus the host's contract. For LlamaIndex that is `TransformComponent.__call__(nodes)`, for LangChain
`BaseDocumentTransformer.transform_documents`. Check their equivalent of serialisation separately:
Haystack is not the only framework that can lose a mode without a word.

## The request side: contract and traps (2026-08-18)

The second component is `PromptInjectionGuard`, in
`haystack_integrations.components.validators.aicordon`. Category `validators` rather than
`preprocessors`: it prepares nothing, it decides whether to call the model.

1. **A branch in Haystack is an ABSENT key in the returned dict, not an empty list.** The receiver
   gets `_NoOutputProduced` (`core/pipeline/component_checks.py`) and does not run at all. Returning
   `{"messages": [], "blocked": [...]}` means calling the generator with an empty list. So `run`
   returns exactly one of the two keys. Covered by a test with a control: on a clean turn the next
   component IS in the pipeline output, on a flagged one it is not.
2. **`ChatMessage.text` is the FIRST text part, not the whole message.** In a message with an image
   the parts come as a list, and an attack in the second text part is invisible to `text` — with no
   error of any kind. We read `texts` and join them. Covered by a test.
3. **The text of a tool result is NOT in `texts`.** For a message with role `tool` the content sits
   in `tool_call_result.result` while `texts` is empty. A wrapper reading `texts` alone would check
   the `tool` role against an empty string and write "read, clean" into the metadata — the quiet
   kind of wrong. We read `texts` plus the call results; the calls themselves (`tool_calls`) we do
   not read, as they are the model's output rather than what was given to it. Covered by a test.
4. **Edit a message only through a copy**: `ChatMessage` carries `@_warn_on_inplace_mutation`, and
   the same list may go into a second branch of the pipeline. The copy is
   `dataclasses.replace(msg, _meta=...)` (the underscored dataclass fields are their real names in
   `__init__`).
5. **The same serialisation trap as in the filter**, now with a dict parameter: `roles` has to sit
   on the object under its own name and be listed in `to_dict`. Covered by a YAML round trip.
6. **The decision is for the exchange, not for a message.** Dropping the flagged turn and calling
   the model with the rest is not allowed: the model answers the message before it, and whoever drew
   the single arrow never finds out.
