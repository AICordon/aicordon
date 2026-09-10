# LangChain: the contract, established from the sources

Checked 2026-08-26. The clone is `langchain-ai/langchain` at `502b2b4`, which carries
`langchain-core` 1.6.1 and `langchain` 1.3.17 in development; the wrapper is written against the
released `langchain-core` 1.6.0, `langchain` 1.3.17 and `langgraph` 1.2.11, which is what the venv
here has. Repository MIT, the framework's own.

**The framework moved under the name.** `langchain` 1.x is an agent library: `create_agent` plus
middleware. What used to be `langchain` — chains, retrievers, the whole 0.3 surface — was renamed
`langchain-classic` (1.0.8) and left where it was. So an integration written for "LangChain" today
has to answer for two shapes, the agent and the chain, and this package carries one entry per shape.

## Where we sit

Four slots, because a string reaches a model by four routes and the role it plays differs.

| slot | host contract | ours | rules |
|---|---|---|---|
| documents at ingest | `BaseDocumentTransformer.transform_documents` | `PromptInjectionFilter` | `ipi` |
| a tool's answer | `AgentMiddleware.wrap_tool_call` | `ToolOutputFilter` | `ipi` |
| the turn an agent will answer | `AgentMiddleware.wrap_model_call` | `PromptInjectionGuard` | `dpi` |
| the request in a chain | `Runnable` between prompt and model | `PromptInjectionValidator` | `dpi` |

The ingest slot is a line of the caller's own code, not a pipeline object: LangChain has no
`IngestionPipeline`, the loader hands you a list and you pass it on. That makes the transformer the
plainest of the four and the only one with no host lifecycle to respect.

## What a middleware is obliged to do

Source of truth: `langchain/agents/middleware/types.py` and `langchain/agents/factory.py`, plus
`middleware/pii.py`, which is the closest thing in the tree to what we are doing.

* Subclass `AgentMiddleware`, implement the hooks you need, pass the instance in
  `create_agent(middleware=[...])`. First in the list is the outermost layer.
* `before_model` / `after_model` are nodes: they return state updates or `None`.
* `wrap_model_call(request, handler)` and `wrap_tool_call(request, handler)` are wrappers: they may
  call the handler more than once, or not at all.
* Every hook has an async twin (`awrap_tool_call`, `abefore_model`, …). See trap 4 — the asymmetry
  there is sharp.
* State that goes through a checkpointer must be JSON-serialisable. Our metadata is bools, strings
  and lists.

There is **no serialisation of the middleware object itself** — a middleware is constructed in the
caller's code and never rebuilt from a dict, so the trap that cost the Haystack wrapper a whole
mechanism (`to_dict`/`from_dict`, settings silently restored to their defaults) does not exist here.
The `BaseDocumentTransformer` is not `Serializable` either.

## Traps the mock-ups caught (2026-08-26)

Each was run against a control on `langchain` 1.3.17; the probes are in the session scratchpad and
the behaviour each describes is covered by a test in `tests/`.

1. **`jump_to` is ignored unless the hook is decorated.** A `before_model` may end a run by
   returning `{"jump_to": "end"}` — but only if it also carries `@hook_config(can_jump_to=["end"])`.
   The decorator is what makes `_add_middleware_edge` build a conditional edge; without it the
   builder emits `graph.add_edge(name, default_destination)`, the value sits in state unread, and
   the model is called with the attack. Nothing is raised, nothing is logged. Measured: undecorated,
   the model was called once; decorated, zero times. **We use `wrap_model_call` instead**, where
   refusing means not calling the handler — there is no edge to forget.

2. **A tool may answer with a `Command`, and then its text is not in a `ToolMessage`.** A tool that
   writes agent state returns `Command(update={"messages": [ToolMessage(...)]})`, and a wrapper
   matching on `ToolMessage` alone passes it through unread — the text still reaches the model, and
   the metadata does not even record that nobody looked. Measured with one tool of each kind in the
   same run: the plain one was rewritten, the `Command` one was not. We walk `update["messages"]`.

3. **A message copy without the original `id` is appended, not replaced.** The `messages` channel
   reduces by id. Annotating a turn by building a fresh `HumanMessage` leaves BOTH in the list, so
   the model is sent the turn twice — and in a design that edited the turn it would be sent the clean copy and
   the original side by side. Measured: with the id, two messages in the final state; without it,
   three. `model_copy(update=...)` keeps the id, so that is what we use everywhere.

4. **Sync-only hooks are not symmetrical under `ainvoke`.** A sync `before_model` or
   `wrap_model_call` is run in an executor and works. A sync `wrap_tool_call` raises
   `NotImplementedError` from the tools node, mid-run. Both halves of every hook are written out
   here, and both are tested.

5. **`str(message.content)` is not the message text.** Content is either a string or a list of
   blocks; `str()` of the list is a Python repr, so a check over it reads punctuation and dictionary
   keys that nobody sent, and an edit to it destroys the message. `langchain-core` 1.x has
   `message.text`, which joins the text blocks and ignores images and files — that is what we read.
   (`middleware/pii.py` in the framework itself does the `str(content)` thing.)

6. **The two vocabularies disagree about role names.** `HumanMessage.type` is `human` where the
   policy says `user`, `AIMessage.type` is `ai` where it says `assistant`. A role map keyed on the
   host's word matches nothing in the default policy: the guard reads no message at all while
   reporting each one read and clean. `ROLE_OF` in `_common.py` translates; the test that would fail
   without it is `test_the_human_message_is_read_as_the_user_role`.

## Decisions that are ours, not the host's

**`drop` on a tool result withholds the text, not the message.** Every tool call must be answered by
a result carrying its `tool_call_id`; a call left unanswered makes the provider error or re-ask. So
the message stays and the model is told the output was withheld — which is also the honest thing to
tell it.

**A chain link may not `drop`.** A `Runnable` returns a value and the next link is the model; there
is no arrangement in which it declines the call and answers instead. `PromptInjectionValidator`
raises on the mode rather than imitating it, and points at the two real ways to have it: `fail`, or
a `RunnableBranch` on `.flagged`. In an agent the decision has a proper home.

**A refused turn is removed from the agent's state, not only from the call.** `drop` skips the model
call — and `create_agent` keeps the exchange, assembling the NEXT call from it, so a turn left in
the thread reaches the model one turn late. Measured on three corpus attacks with a local model: the
answer to an innocuous follow-up came back in the attacker's persona every time while the turn
stayed, and as an ordinary answer every time once it was removed. Only the flagged message goes; the
refusal stays and carries the finding.

**A history the caller assembles elsewhere is not re-read.** The guard reads what arrived since the
model last spoke, so a transcript handed in wholesale — from the caller's own store, ending in an
assistant message — is checked only from its newest turn on. That is deliberate: re-reading the
whole transcript on every call bills the same turns again and again. It also means a conversation
restored from somewhere that never had a guard in it carries whatever is in it. Guard the turns as
they arrive, and what is in the thread will have been read once each.

**The request guard reads what arrived since the model last spoke.** `wrap_model_call` runs once per
model call, so reading the whole history each time would re-bill the opening turn on every step of
a loop. The tail after the last `AIMessage` is what is new; on the first call there is none, and the
tail is the whole list — right for a run resumed with a history nobody has read yet.

## Saving a chain: the trap Haystack has, and LangChain does not (2026-09-09)

A Haystack pipeline saved to YAML without a `mode:` line comes back up in whatever the CURRENT
default is — `to_dict` fills the gap from the signature — so an upgrade can quietly change what a
saved pipeline does. That is written down on the Haystack side; the question of whether it repeats
here had to be asked of LangChain rather than assumed.

It does not. `PromptInjectionValidator` is a plain `Runnable`, not a `Serializable`, so `dumpd` puts
`{"type": "not_implemented"}` where the node was and `loads` raises `NotImplementedError` on the way
back. A chain carrying the validator still dumps — nothing crashes at save time — but it refuses to
come back rather than coming back in a mode nobody chose. Loud is the right failure here, and it
costs a round trip we do not currently need.

The two middlewares and the document filter are not serialised by LangChain at all: an agent is
assembled in code, so there is no saved form to drift.

Checked by an end-to-end stand kept outside this package.

## What carries over to another framework

The policy (`aicordon.guard`) carried over from Haystack unchanged: modes, cut boundaries, metadata,
the role map, the refusal of editing modes on the request side. What had to be written here is the
translation and the host's contract — and one surface Haystack has no equivalent of, the tool
result, which is where an agent takes in material.
