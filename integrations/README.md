# Framework integrations

Wrappers that put Picket inside somebody else's pipeline. There are **two** places to sit, one per
role the text plays in the prompt — since 1.0.0 Picket carries a rule set for each, and the two do
not overlap.

**Material** (`ipi`) — what the model works on: a document, a retrieved passage, the result of a
tool call. We sit at **document ingest**, before the chunker and the embedder: the injection is cut
once, on the way in, and never reaches the vector store at all. Checking after chunking is both late
and dearer — the cut would have to run per chunk, stitching the boundaries back together.

**The request** (`dpi`) — the turn the model answers. We sit **right next to the generator**, on the
message list that is about to go into it. Nothing is cut here: cutting is fitted to an injection
spliced into a document as a line of its own, and a typed jailbreak is not spliced into anything —
it *is* the turn. The decision is for the whole exchange: either it goes to the model or it does
not.

What selects the side is the role, NOT who fetched the text. Nobody "pulls a passage off the
internet" when it comes from an internal index, and in plenty of architectures the code pulls the
user's turn out of a queue; the code always knows the difference regardless, because it puts
material and request in different places when it assembles the call.

## Layout

```
aicordon/guard/    the policy: what to read, with which rule set, what to do with a finding
  guard.py           material: six modes, where the cut ends, metadata
  dialogue.py        request: the role map, three modes, one verdict for the exchange
integrations/
  haystack/        two wrappers against the Haystack contract (@component)
  ...              llamaindex/, langchain/, crewai/ to follow — one wrapper each
```

**Everything of substance lives in `aicordon.guard`**, inside the detector distribution rather than
in a package of its own: it depends on nothing but the detector, and a second published package for
two hundred lines of policy would be a maintenance cost with nothing on the other side. What is left
per framework is the translation of its types into a string and back — fifty-odd lines a wrapper.
That is not tidiness: written inside a Haystack component, the same logic would have to be rewritten
for LlamaIndex, and "start small, then go to the big ones" would lose its point.

## The order of frameworks

Haystack first: its indexing pipeline is an explicit object wired by name, so our check goes in as
its own `pipeline.connect(...)` line and shows up in the graph. The way into their catalogue is a
single PR to `deepset-ai/haystack-integrations`. The ecosystem is smaller than LlamaIndex's or
LangChain's, and that is deliberate: a mistake costs less, while the core that comes out of it
carries over.

For LlamaIndex the material slot is `IngestionPipeline(transformations=[...])` ahead of the
splitter; for LangChain it is `BaseDocumentTransformer`. CrewAI has no such slot at all: chunking
sits inside the knowledge source, so intercepting means subclassing `BaseKnowledgeSource` — which is
why it comes last rather than first.

Their request slot is **not yet established from the sources**: for LangChain the candidate is a
`Runnable` link ahead of the model in LCEL, for LlamaIndex the chat engine's wrapping. Establish it
the way it was established for Haystack — from a clone, writing the contract and the traps into that
framework's `NOTES.md`. The "to the model / not to the model" branch differs in each, and it cannot
be passed over quietly: a component that returns an empty list instead of taking the branch will
call the model with nothing.

## How we show it works

Not "we integrated", but a number, and a different one per side.

Material: build an indexing pipeline over a poisoned corpus (Quadrat, 16 800 injections across three
carriers) and measure how much reaches the store with our component and without it.

The request: run held-out forum jailbreaks and live WildChat turns through a chat pipeline — how
many attacks reach the generator, and how many real users are left without an answer. Plus a third
number that matters more than the first two: **the verdict of the pipeline and the verdict of the
bare detector on the same string must differ zero times**. A wrapper has no licence either to lose
text or to add its own; if that number is not zero, the rest must not be read.

The measurement is part of releasing the package, exactly as it is for Picket itself.
