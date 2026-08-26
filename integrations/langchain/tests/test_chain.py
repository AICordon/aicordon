"""The chain surface: a link between the prompt and the model that marks or raises."""
from __future__ import annotations

import pytest
from aicordon.guard import InjectionFound
from conftest import fake_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableBranch, RunnableLambda

from aicordon_langchain import PromptInjectionValidator


def prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([("system", "Be helpful."), ("user", "{q}")])


def test_a_clean_request_passes_through_as_the_same_object() -> None:
    value = ChatPromptValue(messages=[HumanMessage(content="What is the capital of France?")])
    assert PromptInjectionValidator().invoke(value) is value


def test_a_flagged_request_raises_in_fail_mode(attack: str) -> None:
    with pytest.raises(InjectionFound) as caught:
        PromptInjectionValidator().invoke(ChatPromptValue(messages=[HumanMessage(content=attack)]))
    assert caught.value.threats


def test_the_model_is_not_reached_when_the_link_raises(attack: str) -> None:
    """The control: the same chain answers when the request is clean."""
    model = fake_model(AIMessage(content="Paris."))
    chain = prompt() | PromptInjectionValidator() | model
    assert chain.invoke({"q": "What is the capital of France?"}).content == "Paris."
    assert len(model.calls) == 1
    with pytest.raises(InjectionFound):
        chain.invoke({"q": attack})
    assert len(model.calls) == 1


def test_annotate_marks_the_messages_and_keeps_the_type(attack: str) -> None:
    value = ChatPromptValue(messages=[SystemMessage(content="Be helpful."),
                                      HumanMessage(content=attack)])
    out = PromptInjectionValidator(mode="annotate").invoke(value)
    assert isinstance(out, ChatPromptValue)
    assert out.messages[0].additional_kwargs == {}          # the system turn is not read
    assert out.messages[1].additional_kwargs["picket_flagged"] is True
    assert value.messages[1].additional_kwargs == {}        # the caller's object is untouched


def test_the_branch_predicate_answers_without_the_model(attack: str) -> None:
    """The LCEL way to have `drop`: the chain, not the link, decides not to call the model."""
    model = fake_model(AIMessage(content="should never be produced"))
    guard = PromptInjectionValidator(mode="annotate")
    refusal = RunnableLambda(lambda _v: AIMessage(content="refused"))
    chain = prompt() | RunnableBranch((guard.flagged, refusal), model)
    assert chain.invoke({"q": attack}).content == "refused"
    assert model.calls == []


def test_drop_is_refused_rather_than_imitated() -> None:
    with pytest.raises(ValueError, match="mark or raise"):
        PromptInjectionValidator(mode="drop")


def test_a_bare_string_is_read_as_the_request(attack: str) -> None:
    """A string handed to a model IS the request, whoever assembled it."""
    with pytest.raises(InjectionFound):
        PromptInjectionValidator().invoke(attack)
    assert PromptInjectionValidator().invoke("hello") == "hello"


def test_a_list_of_messages_is_read_as_well(attack: str) -> None:
    with pytest.raises(InjectionFound):
        PromptInjectionValidator().invoke([("system", "Be helpful."), ("user", attack)])


@pytest.mark.asyncio
async def test_the_async_form_decides_the_same(attack: str) -> None:
    with pytest.raises(InjectionFound):
        await PromptInjectionValidator().ainvoke(ChatPromptValue(
            messages=[HumanMessage(content=attack)]))
