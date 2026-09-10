# AI Cordon Picket for LangChain

Check what an LLM is given for prompt injection, in each place it can arrive:

| entry point | reads | with |
|---|---|---|
| `PromptInjectionFilter` | **material**: documents at ingest, before they are chunked and embedded | Picket's `ipi` rules |
| `ToolOutputFilter` | **material**: what a tool handed back, before the model reads it | `ipi` |
| `PromptInjectionGuard` | **the request**: the turn an agent is about to answer | Picket's `dpi` rules |
| `PromptInjectionValidator` | **the request**: the same, in a chain that is not an agent | `dpi` |

The two rule sets are disjoint, and neither is a stricter version of the other — this is not a
sensitivity knob. Pick by role: material is what the model works on, the request is what it answers.
Your code knows which is which; it puts them in different places when it assembles the call.

The check is a rule, not a model: no GPU, no network, no key, a few hundred kilobytes of base, and a
fraction of a millisecond per turn on one core — see [what it costs](#what-it-costs).

## Installation

```bash
pip install aicordon-langchain
```

## Material at ingest

```python
from aicordon_langchain import PromptInjectionFilter
from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

docs = DirectoryLoader("kb/").load()
docs = PromptInjectionFilter(mode="mask").transform_documents(docs)     # <- here
chunks = RecursiveCharacterTextSplitter().split_documents(docs)
store.add_documents(chunks)
```

The filter sits **before the splitter**: a cut here takes the injection out of the chunks, the
embeddings and the store at once, with no offsets to reconcile across chunk boundaries.

### What it does with a finding

| `mode` | the document | the length |
|---|---|---|
| `passthrough` *(default)* | indexed unchanged, the finding recorded in metadata | unchanged |
| `blank` | every character of the block becomes `blank_char` (default `*`) | **preserved** |
| `mask` | the block is replaced by `mask_with` | changes |
| `drop` | not indexed | — |
| `fail` | the run stops on the first finding | — |

**Why the default edits nothing.** Installing a package should not start rewriting your documents,
and it should not start refusing to answer people either. The two failures are not symmetric: a
missed injection is what the layer behind this one is for, while a sentence taken out of a clean
document is gone without a trace and the answer built on what is left still reads fine. Measured,
that costs one clean document in 2000 touched and a median 12.7% of the length of a flagged one.

Say it plainly: **in the default mode nothing is prevented.** The entry points read and report, and
the injection still reaches the model. Protection starts when you name a mode. Look at what fires on
your own material, then choose: `mode="mask"` at ingest, `mode="drop"` on the request side.

No mode shortens a document silently: `blank` keeps the length and `mask` leaves its marker where
the block was. To cut a block out with nothing in its place, say so - `mask_with=""`.

`blank` is for pipelines that carry offsets, page maps or diffs downstream and cannot have a
document change length under them.

The cut takes **the whole utterance the span sits in** — the sentence, across the lines a
wrapper broke it over: the span points at the injection, but what must leave the index is
everything it was saying. A short line that ends without punctuation is a bullet or a table
row and is left alone, so a list is not eaten item by item.

In `drop` mode the host's contract lets `transform_documents` return the survivors and nothing else,
so use `split` when the removed pile should stay visible:

```python
kept, rejected = PromptInjectionFilter(mode="drop").split(docs)
```

## Tool output in an agent

```python
from aicordon_langchain import ToolOutputFilter
from langchain.agents import create_agent

agent = create_agent(
    model="openai:gpt-5.5",
    tools=[fetch_page, read_ticket],
    middleware=[ToolOutputFilter(mode="mask")],             # every tool, or tools=["fetch_page"]
)
```

A page a tool brings back is material by any reading — the model is to work on it, not answer it —
and it enters the conversation with nothing between it and the model. The filter reads it at the
point the tool returns, which is the same ingest point a document has and the only place where
cutting is what the policy was measured on.

**`drop` here withholds the text, not the message.** Every tool call must be answered by a result
carrying its id, so the message stays and the model is told the output was withheld — which is also
the honest thing to tell it.

## The request in an agent

```python
from aicordon_langchain import PromptInjectionGuard

agent = create_agent(
    model="openai:gpt-5.5",
    tools=[fetch_page],
    middleware=[PromptInjectionGuard(mode="drop")],         # without it the turn goes on, marked
)
```

In `drop` mode a flagged turn does **not** reach the model, the refused turn is taken out of the
conversation so that the next turn is not assembled with it, and the agent answers with the guard's
own message instead. The default, `mode="passthrough"`, calls the model and records the finding on the
answer; `mode="fail"` raises `InjectionFound`. What is read is the request: by default the user's turns, and nothing else.
The system message is the operator's own text, and an operator who wants to steer their own model
does not need an injection to do it.

The refusal stays in the thread and carries the finding; only the flagged turn goes. Pass
`forget=False` to keep it, knowing that the next call to the model then carries the attack in its
history.

Both middlewares in one agent, each on its own side:

```python
middleware=[PromptInjectionGuard(mode="drop"), ToolOutputFilter(mode="mask")]
```

## The request in a chain

```python
from aicordon_langchain import PromptInjectionValidator

chain = prompt | PromptInjectionValidator(mode="fail") | model   # raises InjectionFound
```

A link in a chain returns a value and the next link is the model; there is no arrangement in which
it declines the call and answers instead. So it raises, or — in `passthrough`, the default — it
marks and lets the chain decide:

```python
guard = PromptInjectionValidator(mode="passthrough")
chain = prompt | RunnableBranch((guard.flagged, refusal), model)
```

Inside an agent the same decision has a proper home — prefer `PromptInjectionGuard` when there is
an agent to put it in.

Turns are read as they arrive — what came in since the model last spoke. A transcript you assemble
yourself and hand over whole is read from its newest turn on, not re-read end to end, so keep the
guard in the loop that appends to it rather than passing it an unchecked history.

## Nothing is rewritten on the request side

`PromptInjectionGuard` and `PromptInjectionValidator` accept `passthrough`, `drop` and `fail` only; ask
either for an editing mode and it raises. Material can lose a paragraph and stay usable. Take a clause out
of what somebody asked for and the model answers a question nobody put, with the user seeing an
answer rather than a notice — and the cut itself is fitted to the wrong shape, because a typed
attack is not spliced into a turn, it *is* the turn.

## What is written where

Metadata is written on every text that was read, including the clean ones: "read, clean" and "not
read" are different facts, and a field that appeared only on a finding could not be filtered on.

| surface | where it lands | keys |
|---|---|---|
| documents | `Document.metadata` | `ipi_flagged`, `ipi_action`, `ipi_base`, and on a finding `ipi_threats`, `ipi_spans`, `ipi_removed_chars` |
| tool output | `ToolMessage.response_metadata` | `ipi_flagged`, `ipi_action`, `ipi_base`, `ipi_threats` |
| the agent's request | the answer's `response_metadata` | `picket_blocked` or `picket_request_flagged`, `picket_request_threats`, `picket_messages` (keyed by message id) |
| the chain's request | each read message's `additional_kwargs` | `picket_flagged`, `picket_action`, `picket_base`, `picket_threats`, `picket_spans` |

Findings are also logged through the standard library logger under `aicordon_langchain.*` at
`warning` level, in every mode. Writing it down is not a policy choice.

## Measured

Not the detector's recall — that ships with the detector — but what your line delivers with this
package in it and without.

**Material at ingest.** [Quadrat-IPI v1.0.1](https://huggingface.co/datasets/mihailgribov/quadrat-ipi),
2000 injected and 2000 clean documents, `mode="mask"`; how much of a planted payload still reaches
the splitter:

| | whole corpus | injections that ask the model to **reveal** something |
|---|---|---|
| payload gets through intact, without the filter | 100% | 100% |
| payload gets through intact, with it | **85.2%** | **43.4%** |
| payload gone without a trace | 13.5% | **51.3%** |
| clean documents dropped or trimmed | 1 of 2000 | 1 of 2000 |

Both columns matter: the first is an arbitrary stream, the second is where the rule is strong.

**Material through a tool.** The same corpus, 1000 injected and 1000 clean pages, fetched by a tool
inside a real agent loop — and read off the message list the MODEL was handed, not off the filter's
own return value:

| | |
|---|---|
| payload reaching the model intact, without the filter | 100% (1000 of 1000) |
| payload reaching the model intact, with it | **85.4%** |
| payload gone without a trace | 13.1% |
| clean pages withheld or trimmed | 0 of 1000 |

**The request.** Held-out forum jailbreaks from
[TrustAIRLab in-the-wild](https://huggingface.co/datasets/TrustAIRLab/in-the-wild-jailbreak-prompts)
(537, near-duplicates of the fitting half removed) against 20 000 real user turns from
[WildChat](https://huggingface.co/datasets/allenai/WildChat-1M), an agent in `mode="drop"`:

| | |
|---|---|
| attacks reaching the model, without the guard | 100% (537 of 537) |
| attacks reaching the model, with it | **65.2%** |
| turns not answered, out of 20 000 real ones | 0.070% (14) |
| verdicts differing from the bare detector | **0** |

WildChat carries no attack labels and real jailbreaks sit inside it, so "turns not answered" is an
upper bound on the cost to a real user, not a false-alarm rate. The detector's working point, on a
labelled pool, is in its report.

The last row outranks the other two: a wrapper may neither lose text nor add its own, and a figure
taken while it does would be describing a different string than the one the user sent.

Reproduce all three with `eval/measure_ingest.py`, `eval/measure_tools.py` and
`eval/measure_agent.py`.

## What it costs

Checking a turn costs **0.32 ms at the median length**, and 1.78 ± 0.06 ms averaged over ordinary
traffic — 3000 real WildChat turns, each timed five times (`eval/costturn.py`). Loading the base
costs 21 ms, once per process. Of that 1.78 ms, 1.75 is the rule engine itself and 0.03 is
everything this package adds.

The average is five times the median: cost follows length, and a chat pool has a long tail. Find
your row:

| turn length | turns in the pool | cost |
|---|---|---|
| under 200 characters | 1943 | 0.21 ms |
| 200–500 | 411 | 0.71 ms |
| 500–1500 | 321 | 1.72 ms |
| 1500–4000 | 182 | 4.62 ms |
| over 4000 | 143 | 15.63 ms |

For scale, an agent step through LangGraph costs 0.57 ms before any middleware is installed. A
document at ingest costs 11 ms — documents are long, and cost follows length there too.

Cost drifts with machine load. These were taken in one run by one procedure — the only way two
figures compare.

No GPU, no network call, no key. The rule base is a few hundred kilobytes and loads once.

## Not a prefilter

Silence from a rule is not a verdict. Picket reports what it recognises; what it does not recognise
it says nothing about, and no finding does not mean no injection. It belongs where a cheap, local,
deterministic check is worth having on everything you ingest — not as the only thing between a model
and the web.

## Licence

Apache-2.0. The detector itself is [`aicordon`](https://pypi.org/project/aicordon/); the policy the
wrappers share lives there as `aicordon.guard`.
