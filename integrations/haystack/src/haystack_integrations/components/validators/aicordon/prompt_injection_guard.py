"""Check the exchange for a jailbreak before the model is called.

The component sits between whatever assembles the messages and the chat generator. Everything it
decides comes from `aicordon.guard.DialogueGuard`; what lives here is the translation into
Haystack's types and its contract — nothing else, so the same policy serves the other frameworks
unchanged.

    pipe.add_component("guard", PromptInjectionGuard())          # passthrough: the turn goes through
    pipe.add_component("guard", PromptInjectionGuard(mode="drop"))   # or route it to `blocked`
    pipe.connect("prompt.messages", "guard.messages")
    pipe.connect("guard.messages", "llm.messages")               # the model is called on this path
    pipe.connect("guard.blocked", "refusal.messages")            # and not on this one

TWO SOCKETS, AND ONLY ONE OF THEM CARRIES A VALUE. On a flagged exchange `run` returns `blocked` and
no `messages` key at all, which is how a Haystack component branches: a receiver whose socket got
nothing does not run. So the generator is not called with a mutilated message list — it is not
called. Whoever wants a reply for the user connects `blocked` to something that produces one.

THE COMPANION IS `PromptInjectionFilter`, and they are not variants of each other. That one reads
material at ingest with the `ipi` rules and may rewrite it; this one reads the request with the
`dpi` rules and never does. Which applies is decided by the role a string plays in the prompt — the
module docstrings in `aicordon.guard` set out why, and why nothing here cuts a hole in a turn.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from aicordon.guard import DEFAULT_ROLES, PASSTHROUGH, DialogueGuard
from haystack import component, default_from_dict, default_to_dict, logging
from haystack.dataclasses import ChatMessage

logger = logging.getLogger(__name__)

#: What the guard reads of a message. A message can carry several text parts alongside images and
#: files; the parts are joined because that is what the model is given, and the non-text content is
#: not read at all — Picket is a rule over text.
PART_SEPARATOR = "\n\n"


@component
class PromptInjectionGuard:
    """Decides for the exchange as a whole, not message by message.

    :param mode: `passthrough`, the default, lets everything through with the finding in each read
        message's metadata, for a prompt or a downstream router to act on; `drop` routes a flagged
        exchange to `blocked` instead of to the model; `fail` raises `InjectionFound`. The default
        does not decide for you: a component that stops answering users the moment it is wired in
        is as much of a surprise as one that silently edits a document.
    :param roles: role name to rule set — `dpi` for a typed request, `ipi` for material. Defaults to
        `{"user": "dpi"}`. `tool` is left out on purpose: a tool result is material, but it reads
        like agent prompts and code, where the `ipi` rules raise eight times the alarms they raise
        on documents. Switch it on and measure your own tool outputs first.
    :param meta_prefix: prefix for the metadata keys written on each message that was read.
    """

    def __init__(self, mode: str = PASSTHROUGH, roles: dict[str, str] | None = None,
                 meta_prefix: str = "picket") -> None:
        # Only strings and plain dicts here: Haystack requires init parameters to be
        # JSON-serialisable so that a pipeline can be saved and loaded. The detector is built in
        # `warm_up()` instead, which is the hook the framework offers for state too heavy to raise
        # during pipeline validation.
        #
        # KEPT ON THE INSTANCE UNDER THE PARAMETER NAMES, and serialised explicitly below. Without
        # both, saving a pipeline loses the settings SILENTLY: with no `to_dict` the framework reads
        # each init parameter back with `getattr(self, name)`, and when that fails it falls back to
        # the default in the signature.
        self.mode = mode
        self.roles = dict(DEFAULT_ROLES if roles is None else roles)
        self.meta_prefix = meta_prefix
        self._guard = DialogueGuard(mode=mode, roles=self.roles, meta_prefix=meta_prefix)

    def to_dict(self) -> dict[str, Any]:
        return default_to_dict(self, mode=self.mode, roles=self.roles,
                               meta_prefix=self.meta_prefix)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptInjectionGuard":
        return default_from_dict(cls, data)

    def warm_up(self) -> None:
        self._guard.warm_up()

    @component.output_types(messages=list[ChatMessage], blocked=list[ChatMessage])
    def run(self, messages: list[ChatMessage]) -> dict[str, Any]:
        verdict = self._guard.decide([(m.role.value, self._text(m)) for m in messages])
        if verdict.flagged:
            # Logged through the host's logger, at a level the host controls: "write it to the log"
            # is not a mode — it is wanted under `drop` and under `passthrough` alike.
            logger.warning("prompt injection in a turn: {threats}, action {mode}",
                           threats=", ".join(verdict.threats), mode=self.mode)
        # Copies, never the inputs: the same list can be connected to a second branch of the
        # pipeline, and editing in place would rewrite that branch's messages too. Haystack warns
        # on in-place mutation of a ChatMessage for exactly this reason.
        out = [self._with_meta(m, self._guard.meta(verdict, i)) for i, m in enumerate(messages)]
        # One key, not two. The socket that is absent is the branch that does not run.
        return {"messages": out} if verdict.keep else {"blocked": out}

    @staticmethod
    def _text(message: ChatMessage) -> str:
        """Everything of the message that is text the model will read.

        `texts` alone is not that. A tool message carries its content in `tool_call_result.result`
        and its `texts` is EMPTY, so a guard reading only `texts` would check tool results by
        returning "nothing found" on an empty string — the quiet kind of wrong, since the role is in
        the map and the metadata says it was read. Tool CALLS are left out on purpose: those are the
        model's own output, not something handed to it.
        """
        parts = list(message.texts)
        parts += [r.result for r in message.tool_call_results if r.result]
        return PART_SEPARATOR.join(parts)

    @staticmethod
    def _with_meta(message: ChatMessage, extra: dict[str, Any]) -> ChatMessage:
        if not extra:
            return message
        return replace(message, _meta={**message.meta, **extra})
