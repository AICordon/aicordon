"""Tool output as material: what the model is shown of what a tool brought back."""
from __future__ import annotations

import pytest
from aicordon.guard import InjectionFound
from conftest import CLEAN_DOC, INJECTED_DOC, fake_model
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from aicordon_langchain import ToolOutputFilter


@tool
def fetch(url: str) -> str:
    """Fetch a page."""
    return INJECTED_DOC


@tool
def clean_fetch(url: str) -> str:
    """Fetch a page that carries nothing."""
    return CLEAN_DOC


@tool
def state_fetch(url: str) -> str:
    """A tool that answers with a Command instead of a plain result."""
    return Command(update={"messages": [ToolMessage(content=INJECTED_DOC, name="state_fetch",
                                                    tool_call_id="c1")]})


def run(tools, middleware, name="fetch"):  # noqa: ANN001, ANN201
    model = fake_model(
        AIMessage(content="", tool_calls=[{"name": name, "args": {"url": "u"}, "id": "c1"}]),
        AIMessage(content="done"))
    out = create_agent(model=model, tools=tools, middleware=[middleware]).invoke(
        {"messages": [HumanMessage(content="go")]})
    return model, [m for m in out["messages"] if isinstance(m, ToolMessage)]


def test_the_injection_is_cut_before_the_model_sees_the_result() -> None:
    model, results = run([fetch], ToolOutputFilter(mode="redact"))
    assert "forward the API key" not in results[0].content
    assert "Revenue grew 4%." in results[0].content
    assert results[0].response_metadata["ipi_flagged"] is True
    assert results[0].response_metadata["ipi_action"] == "redact"
    # The control: what the model was given on its second call is the cut text, not the original.
    second_call = "".join(str(m.content) for m in model.calls[1])
    assert "forward the API key" not in second_call


def test_a_clean_result_is_marked_read_and_clean() -> None:
    _model, results = run([clean_fetch], ToolOutputFilter(), name="clean_fetch")
    assert results[0].content == CLEAN_DOC
    assert results[0].response_metadata["ipi_flagged"] is False
    assert results[0].response_metadata["ipi_action"] == "none"
    assert results[0].response_metadata["ipi_base"]


def test_a_tool_that_answers_with_a_command_is_read_too() -> None:
    """The trap this exists for: a wrapper matching on `ToolMessage` alone lets exactly these tools
    through unread — the text still reaches the model, and nothing records that nobody looked."""
    _model, results = run([state_fetch], ToolOutputFilter(mode="redact"), name="state_fetch")
    assert results, "the Command carried no tool message into state"
    assert "forward the API key" not in results[0].content
    assert results[0].response_metadata["ipi_flagged"] is True


def test_drop_keeps_the_message_and_withholds_the_text() -> None:
    """Every tool call must be answered by a result carrying its id, so `drop` cannot mean "no
    message": the model is told the output was withheld."""
    _model, results = run([fetch], ToolOutputFilter(mode="drop", withheld="[withheld]"))
    assert results[0].content == "[withheld]"
    assert results[0].tool_call_id == "c1"
    assert results[0].response_metadata["ipi_action"] == "drop"


def test_blank_keeps_the_length_of_the_result() -> None:
    _model, results = run([fetch], ToolOutputFilter(mode="blank"))
    assert len(results[0].content) == len(INJECTED_DOC)
    assert "forward the API key" not in results[0].content


def test_fail_stops_the_run() -> None:
    with pytest.raises(InjectionFound):
        run([fetch], ToolOutputFilter(mode="fail"))


def test_only_the_named_tools_are_read() -> None:
    _model, results = run([fetch], ToolOutputFilter(mode="redact", tools=["other_tool"]))
    assert "forward the API key" in results[0].content
    assert "ipi_flagged" not in results[0].response_metadata     # not read, and it says so


def test_content_blocks_are_read_block_by_block() -> None:
    """Tool output can arrive as a list of blocks. An offset into the joined text points nowhere
    once they are apart, so each text block is read on its own and the rest passes untouched."""
    filt = ToolOutputFilter(mode="redact")
    message = ToolMessage(content=[{"type": "text", "text": INJECTED_DOC},
                                   {"type": "image", "url": "http://example.invalid/x.png"}],
                          name="fetch", tool_call_id="c1")
    out = filt._check(message)
    assert "forward the API key" not in out.content[0]["text"]
    assert out.content[1] == {"type": "image", "url": "http://example.invalid/x.png"}
    assert out.response_metadata["ipi_flagged"] is True


@pytest.mark.asyncio
async def test_the_filter_holds_under_ainvoke() -> None:
    """A middleware defining only `wrap_tool_call` raises `NotImplementedError` from the tools node
    under `ainvoke`. The async half is written out; this is the check that it is."""
    model = fake_model(
        AIMessage(content="", tool_calls=[{"name": "fetch", "args": {"url": "u"}, "id": "c1"}]),
        AIMessage(content="done"))
    out = await create_agent(model=model, tools=[fetch],
                             middleware=[ToolOutputFilter(mode="redact")]).ainvoke(
        {"messages": [HumanMessage(content="go")]})
    results = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert "forward the API key" not in results[0].content
