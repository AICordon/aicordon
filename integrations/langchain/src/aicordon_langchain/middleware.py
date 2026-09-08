"""Check what an agent is given, in the two places it arrives.

    agent = create_agent(
        model="openai:gpt-5.5",
        tools=[fetch_page],
        middleware=[PromptInjectionGuard(), ToolOutputFilter()],   # passthrough, both of them
    )

`PromptInjectionGuard` reads the REQUEST — the turns about to be sent — with Picket's `dpi` rules,
and either lets the call happen or answers in the model's place. `ToolOutputFilter` reads MATERIAL —
what a tool handed back — with the `ipi` rules, and may rewrite it. They are not variants of each
other and neither is a stricter setting of the other: which one applies follows from the role the
text plays, and `aicordon.guard` sets out why.

WHERE EACH ONE SITS, AND WHY THERE. The request guard is a `wrap_model_call`, the last point before
the call: it reads the message list the model is actually about to be sent, after summarisation,
context editing and every other middleware have had their turn. The tool filter is a
`wrap_tool_call`, the point the material enters the conversation — the same ingest point a document
has, and the only place where cutting is what `aicordon.guard` measured.

WHY NOT `before_model` AND `jump_to`. A hook can end a run by returning `{"jump_to": "end"}`, but
only if it is ALSO decorated `@hook_config(can_jump_to=["end"])`: the decorator is what makes the
graph build a conditional edge. Without it the value is written into state and ignored, the edge
runs to the model, and the attack is sent — no error, no warning. Measured against a control on
langchain 1.3.17: undecorated hook, model called once; decorated, model called zero times. Skipping
the handler in `wrap_model_call` needs no edge and cannot fail that way, so that is what this uses.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from aicordon.guard import DEFAULT_ROLES, PASSTHROUGH, DialogueGuard, InjectionGuard
from langchain.agents.middleware import AgentMiddleware, ExtendedModelResponse, ModelResponse
from langchain_core.messages import AIMessage, RemoveMessage, ToolMessage
from langgraph.types import Command

from ._common import ROLE_OF, message_text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


def _new_since_model_spoke(messages: list[Any]) -> list[int]:
    """Indices of the messages that arrived since the model last answered.

    A `wrap_model_call` runs once per model call, so a five-step agent would read the same opening
    turn five times — same verdict, five times the cost. What is new on each of those calls is the
    tail after the last `AIMessage`; on the first call there is no such message and the tail is the
    whole list, which is right for a run resumed with a history nobody has read yet.
    """
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], AIMessage):
            return list(range(i + 1, len(messages)))
    return list(range(len(messages)))


class PromptInjectionGuard(AgentMiddleware):
    """The request side: decide whether the model is called at all.

    :param mode: `passthrough`, the default, calls the model and records the finding on the answer;
        `drop` answers in the model's place and does not call it; `fail` raises `InjectionFound`.
        The default does not decide for you: a middleware that stops answering users the moment it
        is added is as much of a surprise as one that silently edits a document.
    :param roles: role name to rule set — `dpi` for a typed request, `ipi` for material. Defaults to
        `{"user": "dpi"}`. `tool` is left out on purpose: a tool result is material, but it reads
        like agent prompts and code, where the `ipi` rules raise eight times the alarms they raise
        on documents. `ToolOutputFilter` is the measured place for it.
    :param meta_prefix: prefix for the keys written into the answer's `response_metadata`.
    :param refusal: what the agent answers instead of calling the model, in `drop` mode.
    :param forget: in `drop` mode, take the refused turn out of the conversation as well as out of
        this call. See below for why the default is to forget it.
    """

    def __init__(self, mode: str = PASSTHROUGH, roles: dict[str, str] | None = None,
                 meta_prefix: str = "picket",
                 refusal: str = "This request was not sent to the model: it carries a prompt "
                                "injection.",
                 forget: bool = True) -> None:
        super().__init__()
        self.mode = mode
        self.roles = dict(DEFAULT_ROLES if roles is None else roles)
        self.meta_prefix = meta_prefix
        self.refusal = refusal
        self.forget = forget
        self._guard = DialogueGuard(mode=mode, roles=roles, meta_prefix=meta_prefix)

    @property
    def name(self) -> str:
        return f"{type(self).__name__}[{','.join(sorted(self.roles))}]"

    def _decide(self, request: Any) -> tuple[Any, dict[str, Any], list[str]]:
        """The verdict, the metadata to record, and the ids of the messages that were flagged.

        `None` verdict means nothing was read.

        `request.messages` is what is about to be sent, minus the system message the host keeps
        beside it. The system message is not read: it is the operator's own text, and an operator
        who wants to steer their own model does not need an injection to do it.
        """
        messages = list(request.messages)
        indices = _new_since_model_spoke(messages)
        pairs = [(ROLE_OF.get(messages[i].type, messages[i].type), message_text(messages[i]))
                 for i in indices]
        if not any(self._guard.reads(role) for role, _ in pairs):
            # Nothing here plays a role the policy reads. Not "read and clean" — not read, and no
            # metadata is written anywhere, which is the only way the caller can tell them apart.
            return None, {}, []
        verdict = self._guard.decide(pairs)
        meta: dict[str, Any] = {}
        flagged: list[str] = []
        for position, index in enumerate(indices):
            found = self._guard.meta(verdict, position)
            if not found:
                continue
            # Keyed by the message id rather than by position: the caller reading the answer's
            # metadata has the message objects, not our slice of them.
            message_id = messages[index].id
            meta[str(message_id)] = found
            if found.get(f"{self.meta_prefix}_flagged") and message_id:
                flagged.append(str(message_id))
        return verdict, meta, flagged

    def _refuse(self, verdict: Any, meta: dict[str, Any],
                flagged: list[str]) -> ExtendedModelResponse:
        """The answer the caller gets instead of the model's, and an explicit end to the run.

        NOT a bare `AIMessage`. Skipping the model call is enough to end an ordinary agent, whose
        loop stops at a message carrying no tool calls — but an agent built with `response_format`
        has a different exit: the model node runs again unless a structured response appeared this
        turn, on the reasoning that the model may simply have failed to produce one. A refusal never
        will, so that agent spins for ever, quietly, at the speed of the model. Measured on
        langchain 1.3.17: the same refusal that ends a plain agent in under a second did not return
        in four minutes.

        `jump_to` in a state update is read by both edges out of the model node before anything
        else, so this ends the run in every shape of agent — plain, with tools, with a schema.

        AND THE REFUSED TURN LEAVES THE CONVERSATION. Not calling the model with it is only half the
        job: an agent keeps the exchange in its state, and the NEXT turn is assembled from that
        state — so the attack that was refused on Tuesday is in the context on Wednesday, and the
        model reads it there. Measured on three corpus attacks with a local model: with the turn
        left in the thread, the answer to the following innocuous question came back in the
        attacker's persona ("JailBreak: …", "[CLASSIC] … [JESTER] …") every time; with the turn
        removed, it came back as an ordinary answer every time. So `drop` removes it, and what
        remains in the thread is our refusal, which carries the threats and the finding.

        `forget=False` keeps it, for a caller who would rather hold the whole transcript and knows
        that the next turn goes to the model with the attack inside it.
        """
        logger.warning("prompt injection in the request: %s, action %s",
                       ", ".join(verdict.threats), self.mode)
        message = AIMessage(content=self.refusal, response_metadata={
            f"{self.meta_prefix}_blocked": True,
            f"{self.meta_prefix}_threats": list(verdict.threats),
            f"{self.meta_prefix}_messages": meta,
        })
        update: dict[str, Any] = {"jump_to": "end"}
        if self.forget and flagged:
            update["messages"] = [RemoveMessage(id=i) for i in flagged]
        return ExtendedModelResponse(model_response=ModelResponse(result=[message]),
                                     command=Command(update=update))

    def _mark(self, response: Any, verdict: Any, meta: dict[str, Any]) -> Any:
        """Record what was found on the answer the model gave.

        `passthrough` does not touch the request — nothing on this side ever does — so the only place
        left to write is the answer. `response_metadata` under our prefix, on a copy: the fields say
        what was found in the REQUEST, which is why they are named for it.
        """
        if not meta:
            return response
        if verdict.flagged:
            logger.warning("prompt injection in the request: %s, action %s",
                           ", ".join(verdict.threats), self.mode)
        fields = {f"{self.meta_prefix}_request_flagged": verdict.flagged,
                  f"{self.meta_prefix}_request_threats": list(verdict.threats),
                  f"{self.meta_prefix}_messages": meta}

        def stamp(message: Any) -> Any:
            return message.model_copy(update={
                "response_metadata": {**message.response_metadata, **fields}})

        if isinstance(response, AIMessage):
            return stamp(response)
        result = getattr(response, "result", None)
        if result:
            # A copy, not an edit in place: the response object belongs to the host, and another
            # middleware layer outside this one may still be holding the one it passed in.
            return replace(response,
                           result=[stamp(m) if isinstance(m, AIMessage) else m for m in result])
        return response

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        verdict, meta, flagged = self._decide(request)
        if verdict is None:
            return handler(request)
        if verdict.flagged and not verdict.keep:
            # The handler is never called, so the model is never sent the turn. The run ends here
            # because the message we return carries no tool calls, and the caller gets an answer
            # rather than their own message reflected back at them.
            return self._refuse(verdict, meta, flagged)
        return self._mark(handler(request), verdict, meta)

    async def awrap_model_call(self, request: Any,
                               handler: Callable[[Any], Awaitable[Any]]) -> Any:
        """The same decision for an agent driven by `ainvoke`/`astream`.

        Written out rather than inherited: a middleware that defines only the sync hook raises
        `NotImplementedError` the moment the agent is run asynchronously. The check itself has no
        I/O to await — it is a rule over a string — so this is the sync body with the handler
        awaited.
        """
        verdict, meta, flagged = self._decide(request)
        if verdict is None:
            return await handler(request)
        if verdict.flagged and not verdict.keep:
            return self._refuse(verdict, meta, flagged)
        return self._mark(await handler(request), verdict, meta)


class ToolOutputFilter(AgentMiddleware):
    """The material side: read what a tool handed back, with the `ipi` rules, before the model does.

    :param mode: `passthrough` (the default, which edits nothing), `blank`, `mask`, `drop` or `fail`;
        `mask_with=""` cuts the block out with nothing in its place. See `withheld` for what
        `drop` means where a tool result cannot simply go missing.
    :param tools: names of the tools to read. `None` reads every one of them.
    :param meta_prefix: prefix for the keys written into the tool message's `response_metadata`.
    :param blank_char: the character `blank` mode fills the block with.
    :param mask_with: what `mask` mode puts in place of the block.
    :param withheld: what the model is given in `drop` mode.
    """

    def __init__(self, mode: str = PASSTHROUGH, tools: list[str] | None = None,
                 meta_prefix: str = "ipi", blank_char: str = "*",
                 mask_with: str = "[prompt injection removed]",
                 withheld: str = "[tool output withheld: prompt injection]") -> None:
        super().__init__()
        self.mode = mode
        self.read_tools = tools
        self.meta_prefix = meta_prefix
        self.blank_char = blank_char
        self.mask_with = mask_with
        self.withheld = withheld
        self._guard = InjectionGuard(mode=mode, meta_prefix=meta_prefix, blank_char=blank_char,
                                     mask_with=mask_with)

    @property
    def name(self) -> str:
        return f"{type(self).__name__}[{self.mode}]"

    def _reads(self, tool_name: str) -> bool:
        return self.read_tools is None or tool_name in self.read_tools

    def _check(self, message: ToolMessage) -> ToolMessage:
        """One tool result, read and handled. The message comes back as a copy, always.

        A `ToolMessage` carries its text either as a string or as a list of content blocks. String
        content is read and edited whole. Block content is read and edited BLOCK BY BLOCK: an offset
        into the joined text does not point anywhere in particular once the blocks are back apart,
        and the joins are not text anybody sent. The cost is that an injection split across two
        blocks is seen as two halves; tool output is one block in every case we have met.
        """
        content = message.content
        new_content: Any
        threats: tuple[str, ...]
        if isinstance(content, str):
            verdict = self._guard.inspect(content)
            flagged, keep, threats = verdict.flagged, verdict.keep, verdict.threats
            new_content = verdict.text
        else:
            blocks: list[Any] = []
            flagged, keep = False, True
            seen: dict[str, None] = {}
            for block in content:
                if isinstance(block, str):
                    verdict = self._guard.inspect(block)
                    blocks.append(verdict.text)
                elif isinstance(block, dict) and block.get("type") == "text" \
                        and isinstance(block.get("text"), str):
                    verdict = self._guard.inspect(block["text"])
                    blocks.append({**block, "text": verdict.text})
                else:
                    # Not text: an image, a file, a citation. Picket is a rule over text and has
                    # nothing to say about these, so they pass through untouched and unread.
                    blocks.append(block)
                    continue
                flagged = flagged or verdict.flagged
                keep = keep and verdict.keep
                seen.update(dict.fromkeys(verdict.threats))
            threats = tuple(seen)
            new_content = blocks

        if flagged:
            logger.warning("prompt injection in the output of tool %s: %s, action %s",
                           message.name, ", ".join(threats), self.mode)
        if flagged and not keep:
            # `drop` cannot mean "no message". Every tool call the model made must be answered by a
            # result carrying its `tool_call_id`, and a provider handed a call with no answer either
            # errors or re-asks. So the MESSAGE stays and the TEXT goes: the model is told the
            # output was withheld, which is also the honest thing to tell it.
            new_content = self.withheld
        meta = {f"{self.meta_prefix}_flagged": flagged,
                f"{self.meta_prefix}_action": self.mode if flagged else "none",
                f"{self.meta_prefix}_base": self._guard.base_version}
        if flagged:
            meta[f"{self.meta_prefix}_threats"] = list(threats)
        return message.model_copy(update={
            "content": new_content,
            "response_metadata": {**message.response_metadata, **meta},
        })

    def _handle(self, request: Any, result: Any) -> Any:
        """Whatever the tool returned, with every tool result in it read.

        A tool may answer with a `Command` instead of a `ToolMessage` — to write agent state, or to
        hand control elsewhere — and its text then sits in `update["messages"]`. A filter that
        matched on `ToolMessage` alone would let exactly those tools through unread, silently: the
        text still reaches the model, and the metadata would not even record that it had not been
        looked at. Measured on langchain 1.3.17 with a tool of each kind.
        """
        if not self._reads(request.tool_call["name"]):
            return result
        if isinstance(result, ToolMessage):
            return self._check(result)
        update = getattr(result, "update", None)
        if isinstance(update, dict) and isinstance(update.get("messages"), list):
            checked = [self._check(m) if isinstance(m, ToolMessage) else m
                       for m in update["messages"]]
            # A copy, like everywhere else here: `Command` is a dataclass, and the one we were
            # handed may be the tool's own module-level constant.
            return replace(result, update={**update, "messages": checked})
        return result

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return self._handle(request, handler(request))

    async def awrap_tool_call(self, request: Any,
                              handler: Callable[[Any], Awaitable[Any]]) -> Any:
        """The same for an agent driven by `ainvoke`/`astream`.

        Not optional, and not symmetrical with the model hook: a middleware defining only
        `wrap_tool_call` raises `NotImplementedError` from the tools node under `ainvoke`, where a
        sync `before_model` or `wrap_model_call` would have been run in an executor for us.
        """
        return self._handle(request, await handler(request))
