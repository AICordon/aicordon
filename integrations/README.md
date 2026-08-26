# Framework integrations

Wrappers that put Picket inside somebody else's pipeline. **Two** places to sit, one per role the
text plays in the prompt; since 1.0.0 Picket carries a rule set for each, and they do not overlap.
How many entry points a framework has follows from its own shape — a RAG pipeline offers two, an
agent library four — but every one of them is one of these two sides.

**Material** (`ipi`) — what the model works on: a document, a retrieved passage, a tool result. We
sit at **ingest**, before the chunker and the embedder, so the injection is cut once and never
reaches the store. Checking after chunking is late and dearer: the cut would run per chunk, with the
boundaries stitched back together. In an agent the ingest point of a tool result is the moment the
tool returns — same rule, same modes, a different doorway.

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
  langchain/       four against LangChain: a document transformer, two agent middlewares, a runnable
```

**Everything of substance lives in `aicordon.guard`**, inside the detector distribution: it depends
on nothing but the detector, and a second published package for two hundred lines of policy costs
maintenance and buys nothing. Per framework that leaves the translation of its types into a string
and back — fifty-odd lines. Written inside a framework component instead, the same logic would be
rewritten for the next one.

## How we show it works

Not "we integrated" — a number, one per side.

Material: run a poisoned corpus (Quadrat, 16 800 injections across three carriers) through an
indexing pipeline and measure how much reaches the store with our component and without it.

The request: run held-out forum jailbreaks and live WildChat turns through a chat pipeline — how
many attacks reach the generator, how many real users are left without an answer. And a third number
that outranks both: **the pipeline and the bare detector must differ zero times on the same string**.
A wrapper may neither lose text nor add its own; if that number is not zero, the rest must not be
read.

The measurement is part of releasing the package, as it is for Picket itself. Two wrappers over the
same policy on the same corpora must agree, and they do: the Haystack pipeline and the LangChain
agent both leave 350 of 537 held-out attacks reaching the model and cost 14 of 20 000 real turns
their answer.

## Establishing a framework's contract

The traps are never in the check — they are in the host, and each one found so far was silent. Before
writing a wrapper, clone the framework and read the sources for: how a step declines to call the
model (an absent key in Haystack, a skipped handler in LangChain, and in both a way of *appearing*
to decline that quietly does not); how a message carries its text when it is not a plain string; how
an edited message is put back without being duplicated; and whether the sync and async halves of a
hook are interchangeable. Write what you find into that framework's `NOTES.md` with the control that
proves it, and cover it with a test.
