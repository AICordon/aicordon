# Framework integrations

Wrappers that put Picket inside somebody else's pipeline. **Two** places to sit, one per role the
text plays in the prompt; since 1.0.0 Picket carries a rule set for each, and they do not overlap.

**Material** (`ipi`) — what the model works on: a document, a retrieved passage, a tool result. We
sit at **ingest**, before the chunker and the embedder, so the injection is cut once and never
reaches the store. Checking after chunking is late and dearer: the cut would run per chunk, with the
boundaries stitched back together.

**The request** (`dpi`) — the turn the model answers. We sit **next to the generator**, on the
message list about to enter it. Nothing is cut here: cutting is fitted to an injection spliced into
a document as its own line, and a typed jailbreak is not spliced into anything — it *is* the turn.
The decision is for the whole exchange: it goes to the model or it does not.

The side follows from the role, NOT from who fetched the text. A passage from an internal index was
never "pulled off the internet", and plenty of architectures pull the user's turn out of a queue.
The code knows the difference either way — it puts material and request in different places when it
assembles the call.

## Layout

```
aicordon/guard/    the policy: what to read, with which rule set, what to do with a finding
  guard.py           material: six modes, where the cut ends, metadata
  dialogue.py        request: the role map, three modes, one verdict for the exchange
integrations/
  haystack/        two wrappers against the Haystack contract (@component)
  ...              llamaindex/, langchain/, crewai/ to follow — one wrapper each
```

**Everything of substance lives in `aicordon.guard`**, inside the detector distribution: it depends
on nothing but the detector, and a second published package for two hundred lines of policy costs
maintenance and buys nothing. Per framework that leaves the translation of its types into a string
and back — fifty-odd lines. Written inside a Haystack component instead, the same logic would be
rewritten for LlamaIndex.

## The order of frameworks

Haystack first: its indexing pipeline is an explicit object wired by name, so our check goes in as
its own `pipeline.connect(...)` line and shows up in the graph, and the way into their catalogue is
one PR to `deepset-ai/haystack-integrations`. The smaller ecosystem is the point: a mistake costs
less, and the core carries over.

For LlamaIndex the material slot is `IngestionPipeline(transformations=[...])` ahead of the
splitter; for LangChain, `BaseDocumentTransformer`. CrewAI has no slot at all — chunking sits inside
the knowledge source, and intercepting means subclassing `BaseKnowledgeSource` — so it goes last.

Their request slot is **not yet established from the sources**: for LangChain the candidate is a
`Runnable` link ahead of the model in LCEL, for LlamaIndex the chat engine's wrapping. Establish it
as it was for Haystack — from a clone, with the contract and the traps written into that framework's
`NOTES.md`. Check the "to the model / not to the model" branch separately in each: a component that
returns an empty list instead of taking the branch calls the model with nothing.

## How we show it works

Not "we integrated" — a number, one per side.

Material: run a poisoned corpus (Quadrat, 16 800 injections across three carriers) through an
indexing pipeline and measure how much reaches the store with our component and without it.

The request: run held-out forum jailbreaks and live WildChat turns through a chat pipeline — how
many attacks reach the generator, how many real users are left without an answer. And a third number
that outranks both: **the pipeline and the bare detector must differ zero times on the same string**.
A wrapper may neither lose text nor add its own; if that number is not zero, the rest must not be
read.

The measurement is part of releasing the package, as it is for Picket itself.
