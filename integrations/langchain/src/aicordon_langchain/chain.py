"""Check the request on its way to the model in a chain that is not an agent.

    guard = PromptInjectionValidator(mode="fail")   # the default, `passthrough`, only marks
    chain = prompt | guard | model

The validator is a `Runnable` that passes its input on with its text untouched and records what
Picket's `dpi` rules found on it; in `fail` mode it raises `InjectionFound` instead of returning. It
accepts what a chat model accepts — a string, a `PromptValue`, or a list of messages — and gives
back the same shape it was handed, so it can be dropped into a chain anywhere ahead of the model
without changing its types.

WHY IT ONLY MARKS OR RAISES. A `Runnable` in a chain has one way out: it returns a value, and the
next link is the model. There is no arrangement in which it declines to call the model and answers
instead — that decision belongs to whoever built the chain. So `drop` is refused here rather than
imitated, and the two ways to have it are named:

    # raise, and handle it where you handle errors
    chain = prompt | PromptInjectionValidator(mode="fail") | model

    # or branch, and answer for yourself
    guard = PromptInjectionValidator(mode="passthrough")
    chain = prompt | RunnableBranch((guard.flagged, refusal), model)

In an AGENT the same decision has a proper home — `PromptInjectionGuard` skips the model call and
answers in its place. Prefer that one when there is an agent to put it in.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aicordon.guard import DEFAULT_ROLES, NON_EDITING_MODES, PASSTHROUGH, DialogueGuard
from langchain_core.messages import BaseMessage, convert_to_messages
from langchain_core.prompt_values import ChatPromptValue, PromptValue
from langchain_core.runnables import Runnable

from ._common import ROLE_OF, message_text

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

#: The modes a chain can honour: what a dialogue takes, less `drop`, which is missing on purpose —
#: see the module docstring. Derived rather than spelled out, so that a mode added to the policy
#: arrives here too instead of being quietly refused by a list nobody remembered to widen.
CHAIN_MODES = tuple(mode for mode in NON_EDITING_MODES if mode != "drop")


class PromptInjectionValidator(Runnable[Any, Any]):
    """Read the request with Picket's `dpi` rules; pass it on or raise.

    :param mode: `passthrough`, the default, records the finding on each message it read and lets
        everything through, for a `RunnableBranch` or a later link to act on; `fail` raises
        `InjectionFound`.
    :param roles: role name to rule set — `dpi` for a typed request, `ipi` for material. Defaults to
        `{"user": "dpi"}`.
    :param meta_prefix: prefix for the keys written into `additional_kwargs` in `passthrough` mode.
    """

    def __init__(self, mode: str = PASSTHROUGH, roles: dict[str, str] | None = None,
                 meta_prefix: str = "picket") -> None:
        super().__init__()
        if mode not in CHAIN_MODES:
            raise ValueError(
                f"a chain link can only mark or raise, so mode is one of {CHAIN_MODES}, got "
                f"{mode!r}. To answer instead of calling the model, branch on `.flagged` or use "
                f"PromptInjectionGuard inside an agent.")
        self.mode = mode
        self.roles = dict(DEFAULT_ROLES if roles is None else roles)
        self.meta_prefix = meta_prefix
        self._guard = DialogueGuard(mode=mode, roles=roles, meta_prefix=meta_prefix)

    def warm_up(self) -> None:
        """Load the rule base now rather than on the first request."""
        self._guard.warm_up()

    def _messages(self, value: Any) -> list[BaseMessage]:
        """Whatever a chat model would have been given, as messages.

        A bare string becomes a `HumanMessage`, which is the same reading the model gets — and the
        right one: a string handed to a model IS the request, whoever assembled it.
        """
        if isinstance(value, PromptValue):
            return value.to_messages()
        if isinstance(value, str):
            return convert_to_messages([value])
        if isinstance(value, BaseMessage):
            return [value]
        if isinstance(value, (list, tuple)):
            return convert_to_messages(list(value))
        return []

    def _decide(self, value: Any) -> tuple[Any, list[BaseMessage]]:
        messages = self._messages(value)
        pairs = [(ROLE_OF.get(m.type, m.type), message_text(m)) for m in messages]
        return self._guard.decide(pairs), messages

    def flagged(self, value: Any) -> bool:
        """Whether Picket fires on this request. The predicate for a `RunnableBranch`.

        Reads the request a second time when used beside `invoke` in the same chain, which is a
        rule over a string and costs a fraction of a millisecond — the alternative would be state
        shared between two links of a chain that may be running for two different users at once.
        """
        verdict, _ = self._decide(value)
        return bool(verdict.flagged)

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        """Pass the request on. In `fail` mode `InjectionFound` comes out of here instead.

        The text is the text that came in, character for character, and the type is the type that
        came in. The OBJECT is not always the same object: in `passthrough` mode the finding goes
        into the messages' `additional_kwargs`, and a message is copied to carry it, so an input
        carrying messages comes back rebuilt around copies — flagged or clean, since "read and
        found nothing" is a finding too. Copying rather than writing in place is deliberate: the
        caller's own messages may be connected to a second branch, and a `BaseMessage` is a pydantic
        model, so editing one in place would edit theirs.

        The SHAPE is the shape that came in, in every mode. Where the request arrived as something
        with no room for a finding — a bare string, or a list of the tuples and dicts a chat model
        also accepts — it goes on exactly as it came and gets a log line only, rather than being
        handed on as the messages we built to read it. That is why `flagged` exists.
        """
        verdict, messages = self._decide(input)
        if verdict.flagged:
            logger.warning("prompt injection in the request: %s, action %s",
                           ", ".join(verdict.threats), self.mode)
        if self.mode == PASSTHROUGH and messages and not isinstance(input, str):
            return self._annotated(input, verdict, messages)
        return input

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None,
                      **kwargs: Any) -> Any:
        """The check has no I/O to await; this is `invoke` under an async name so that a chain
        driven by `ainvoke` does not fall back to a thread for a rule over a string."""
        return self.invoke(input, config, **kwargs)

    def _annotated(self, value: Any, verdict: Any, messages: list[BaseMessage]) -> Any:
        """The same input with our metadata on the messages that were read.

        Copies throughout: the caller's prompt object may be reused for the next request, and a
        finding from this one written into it would then belong to nobody.
        """
        marked: list[BaseMessage] = []
        for i, message in enumerate(messages):
            found = self._guard.meta(verdict, i)
            marked.append(message.model_copy(update={
                "additional_kwargs": {**message.additional_kwargs, **found}}) if found else message)
        if isinstance(value, ChatPromptValue):
            return ChatPromptValue(messages=marked)
        if isinstance(value, PromptValue):
            # A `StringPromptValue` is a string with a class around it: there are no messages in it
            # to write on, so it goes on as it came, the same as a bare string.
            return value
        if isinstance(value, BaseMessage):
            return marked[0]
        if isinstance(value, list) and all(isinstance(item, BaseMessage) for item in value):
            return marked
        # A list of tuples or of dicts is a RECIPE for messages, not messages: `convert_to_messages`
        # built the ones we read, and handing those back would change the shape the caller passed in
        # — under `passthrough` only, since `fail` returns the input untouched. There is nothing on a
        # tuple to carry a finding, so it goes on as it came, the same as a bare string.
        return value
