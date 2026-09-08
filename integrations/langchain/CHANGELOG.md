# Changelog

## 0.2.0 — 2026-09-08

Requires `aicordon>=1.2.0`. **Every entry point now defaults to `mode="passthrough"`** —
`PromptInjectionFilter`, `ToolOutputFilter`, `PromptInjectionGuard` and `PromptInjectionValidator`.
They read the text and record what they found; they edit, refuse and raise only when a mode says so.
All four used to act by default.

Breaking for code that named no mode, and for nobody else: documents and tool results are no longer
edited, a flagged turn now reaches the model with the finding on the answer, and a chain link no
longer raises. Each of those is one argument away:

    PromptInjectionFilter(mode="mask")
    ToolOutputFilter(mode="mask")
    PromptInjectionGuard(mode="drop")
    PromptInjectionValidator(mode="fail")

The reasoning is in the detector's own changelog under 1.2.0, along with the modes and what each
does. Nothing about detection changed: the base, the rules and the published numbers are the same.

## 0.1.1 — 2026-08-27

### A refused turn now leaves the conversation

`PromptInjectionGuard` in `drop` mode did not send the flagged turn to the model — and left it in
the agent's state, where the NEXT turn was assembled from. So the attack refused on one turn was in
the context on the following one, and the model read it there.

Measured end to end on three corpus attacks with a local model, asking an innocuous question after
the refusal:

| | refused | left in the thread | the answer to the next, clean question |
|---|---|---|---|
| no guard | — | yes | `JailBreak: …`, `[CLASSIC] … [JESTER] …` |
| 0.1.0 | yes | yes | `JailBreak: …`, `[CLASSIC] … [JESTER] …` |
| 0.1.1 | yes | **no** | an ordinary support answer, all three times |

The refusal itself stays in the thread and carries the threats, so what happened is still on the
record. Only what was flagged is removed — a clean turn beside it in the same batch is kept.
`PromptInjectionGuard(forget=False)` restores the old behaviour for a caller who would rather hold
the whole transcript and knows the next turn carries the attack into the model.

This is a wrapper-side fix; nothing in the detector or the shared policy changed. Haystack is not
affected: a pipeline is handed its message list by the caller and keeps no thread of its own.

## 0.1.0 — 2026-08-26

First release. AI Cordon Picket for LangChain, in four places a string reaches a model.

| entry point | host contract | reads | with |
|---|---|---|---|
| `PromptInjectionFilter` | `BaseDocumentTransformer` | documents at ingest | `ipi` |
| `ToolOutputFilter` | `AgentMiddleware.wrap_tool_call` | what a tool handed back | `ipi` |
| `PromptInjectionGuard` | `AgentMiddleware.wrap_model_call` | the turn an agent will answer | `dpi` |
| `PromptInjectionValidator` | `Runnable` | the request in a chain | `dpi` |

The policy is `aicordon.guard`, shipped inside the detector: modes, cut boundaries and metadata are
the same here as in `aicordon-haystack`, and the acceptance measurements reproduce that package's
numbers on the same corpora.

**The tool result is the surface a RAG pipeline has no equivalent of.** A page a tool fetches enters
the conversation with nothing between it and the model, and it is material by any reading — so it is
read with the `ipi` rules at the point the tool returns, where cutting is what the policy was
measured on. `drop` there withholds the text and keeps the message: every tool call must be answered
by a result carrying its id.

**Nothing rewrites a request.** `PromptInjectionGuard` and `PromptInjectionValidator` take
`annotate`, `drop` and `fail` only, and a chain link takes no `drop` at all — a `Runnable` returns a
value and the next link is the model, so it raises or marks and lets a `RunnableBranch` decide.

Against `langchain-core` 1.6, `langchain` 1.3 and `langgraph` 1.2. The contract each entry point
stands on, and the four traps behind these choices, are in `NOTES.md`.
