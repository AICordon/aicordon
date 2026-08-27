"""The request side of an agent: whether the model is called at all, and with what."""
from __future__ import annotations

import pytest
from aicordon.guard import InjectionFound
from conftest import fake_model
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from aicordon_langchain import PromptInjectionGuard


@tool
def fetch(url: str) -> str:
    """Fetch a page."""
    return "an ordinary page about quarterly revenue"


def agent(model, **kw):  # noqa: ANN001, ANN003, ANN201
    return create_agent(model=model, tools=[], middleware=[PromptInjectionGuard(**kw)])


def test_a_clean_request_reaches_the_model() -> None:
    """The control for every test below. Without it, "the model was not called" proves nothing."""
    model = fake_model(AIMessage(content="Paris."))
    out = agent(model).invoke({"messages": [HumanMessage(content="What is the capital of France?")]})
    assert len(model.calls) == 1
    assert out["messages"][-1].content == "Paris."
    assert out["messages"][-1].response_metadata.get("picket_blocked") is None


def test_a_flagged_request_is_not_sent_and_the_caller_gets_an_answer(attack: str) -> None:
    """Two facts, and the second is not decoration. Ending the run without an answer would hand the
    caller their own attack text back as the last message."""
    model = fake_model(AIMessage(content="should never be produced"))
    out = agent(model).invoke({"messages": [HumanMessage(content=attack)]})
    assert model.calls == []
    last = out["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.response_metadata["picket_blocked"] is True
    assert last.response_metadata["picket_threats"]


def test_annotate_calls_the_model_and_records_the_finding_on_the_answer(attack: str) -> None:
    model = fake_model(AIMessage(content="answered anyway"))
    out = agent(model, mode="annotate").invoke({"messages": [HumanMessage(content=attack)]})
    assert len(model.calls) == 1
    meta = out["messages"][-1].response_metadata
    assert meta["picket_request_flagged"] is True
    assert meta["picket_request_threats"]
    assert meta["picket_messages"]                       # keyed by the message id that carried it


def test_annotate_on_a_clean_request_still_says_it_was_read() -> None:
    model = fake_model(AIMessage(content="Paris."))
    out = agent(model, mode="annotate").invoke({"messages": [HumanMessage(content="Capital?")]})
    meta = out["messages"][-1].response_metadata
    assert meta["picket_request_flagged"] is False
    assert list(meta["picket_messages"].values())[0]["picket_action"] == "none"


def test_fail_raises_before_the_model_is_called(attack: str) -> None:
    model = fake_model(AIMessage(content="should never be produced"))
    with pytest.raises(InjectionFound):
        agent(model, mode="fail").invoke({"messages": [HumanMessage(content=attack)]})
    assert model.calls == []


def test_the_human_message_is_read_as_the_user_role(attack: str) -> None:
    """The two vocabularies disagree: LangChain calls it `human`, the policy calls it `user`. A role
    map keyed on the host's word would read nothing and report every turn clean."""
    model = fake_model(AIMessage(content="x"))
    out = agent(model, roles={"user": "dpi"}).invoke({"messages": [HumanMessage(content=attack)]})
    assert model.calls == []
    assert out["messages"][-1].response_metadata["picket_blocked"] is True


def test_a_role_the_map_leaves_out_is_not_read_at_all(attack: str) -> None:
    """"Not read" is a different fact from "read and clean", and the metadata has to show it."""
    model = fake_model(AIMessage(content="through"))
    out = agent(model, mode="annotate", roles={"tool": "ipi"}).invoke(
        {"messages": [HumanMessage(content=attack)]})
    assert len(model.calls) == 1
    assert "picket_request_flagged" not in out["messages"][-1].response_metadata


def test_the_opening_turn_is_read_once_however_long_the_loop_runs() -> None:
    """A `wrap_model_call` runs per model call. Reading the whole history each time would re-bill
    the same turn on every step of the agent; what is new is the tail after the model last spoke."""
    read: list[str] = []

    class Counting(PromptInjectionGuard):
        def _decide(self, request):  # noqa: ANN001, ANN202
            verdict, meta, flagged = super()._decide(request)
            read.append("read" if verdict is not None else "skipped")
            return verdict, meta, flagged

    model = fake_model(
        AIMessage(content="", tool_calls=[{"name": "fetch", "args": {"url": "u"}, "id": "c1"}]),
        AIMessage(content="", tool_calls=[{"name": "fetch", "args": {"url": "v"}, "id": "c2"}]),
        AIMessage(content="done"))
    create_agent(model=model, tools=[fetch], middleware=[Counting()]).invoke(
        {"messages": [HumanMessage(content="go")]})
    assert len(model.calls) == 3
    assert read == ["read", "skipped", "skipped"]


def test_a_refusal_ends_an_agent_asked_for_structured_output(attack: str) -> None:
    """The exit condition of such an agent is a structured response, not a message without tool
    calls: without an explicit end it runs the model again, for ever, because a refusal will never
    produce one. Four minutes and still going, before the fix."""
    from pydantic import BaseModel

    class Answer(BaseModel):
        city: str

    model = fake_model(AIMessage(content="should never be produced"))
    out = create_agent(model=model, tools=[], middleware=[PromptInjectionGuard()],
                       response_format=Answer).invoke(
        {"messages": [HumanMessage(content=attack)]})
    assert model.calls == []
    assert out["messages"][-1].response_metadata["picket_blocked"] is True
    assert out.get("structured_response") is None


def test_a_refusal_ends_an_agent_that_has_tools(attack: str) -> None:
    """The same, with the other edge out of the model node."""
    model = fake_model(AIMessage(content="should never be produced"))
    out = create_agent(model=model, tools=[fetch], middleware=[PromptInjectionGuard()]).invoke(
        {"messages": [HumanMessage(content=attack)]})
    assert model.calls == []
    assert out["messages"][-1].response_metadata["picket_blocked"] is True


def test_the_refused_turn_leaves_the_conversation(attack: str) -> None:
    """Not calling the model with it is half the job. An agent keeps the exchange in its state and
    assembles the NEXT call from that state, so a refused turn left in the thread is in the context
    one turn later — measured with a local model, the answer to the following innocuous question
    came back in the attacker's persona."""
    saver = InMemorySaver()
    agent = create_agent(model=fake_model(AIMessage(content="ordinary answer")), tools=[],
                         middleware=[PromptInjectionGuard()], checkpointer=saver)
    config = {"configurable": {"thread_id": "t"}}
    agent.invoke({"messages": [HumanMessage(content=attack)]}, config)
    left = agent.get_state(config).values["messages"]
    assert not any(attack[:60] in str(m.content) for m in left), \
        "the refused turn is still in the thread and will be sent with the next one"
    assert any(m.response_metadata.get("picket_blocked") for m in left), \
        "the refusal itself did not stay, so nothing records what happened"


def test_forget_false_keeps_the_turn_for_a_caller_who_asked_for_it(attack: str) -> None:
    saver = InMemorySaver()
    agent = create_agent(model=fake_model(AIMessage(content="ordinary answer")), tools=[],
                         middleware=[PromptInjectionGuard(forget=False)], checkpointer=saver)
    config = {"configurable": {"thread_id": "t"}}
    agent.invoke({"messages": [HumanMessage(content=attack)]}, config)
    left = agent.get_state(config).values["messages"]
    assert any(attack[:60] in str(m.content) for m in left)


def test_a_clean_turn_beside_a_flagged_one_is_not_forgotten(attack: str) -> None:
    """Only what was flagged goes. A tail can hold more than one message, and removing the innocent
    ones with it would rewrite the conversation on the caller."""
    saver = InMemorySaver()
    agent = create_agent(model=fake_model(AIMessage(content="ordinary answer")), tools=[],
                         middleware=[PromptInjectionGuard(roles={"user": "dpi"})],
                         checkpointer=saver)
    config = {"configurable": {"thread_id": "t"}}
    agent.invoke({"messages": [HumanMessage(content="What plans do you offer?"),
                               HumanMessage(content=attack)]}, config)
    left = [str(m.content) for m in agent.get_state(config).values["messages"]]
    assert any("What plans do you offer?" in m for m in left), "a clean turn was removed too"
    assert not any(attack[:60] in m for m in left)


@pytest.mark.asyncio
async def test_the_guard_holds_under_ainvoke(attack: str) -> None:
    """A middleware with only the sync hook raises `NotImplementedError` here for tool calls, and
    the model hook is run in an executor. Both halves are written out, so both are checked."""
    model = fake_model(AIMessage(content="should never be produced"))
    out = await agent(model).ainvoke({"messages": [HumanMessage(content=attack)]})
    assert model.calls == []
    assert out["messages"][-1].response_metadata["picket_blocked"] is True
