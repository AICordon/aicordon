"""The ingest surface: a `BaseDocumentTransformer` between the loader and the splitter."""
from __future__ import annotations

import pytest
from aicordon.guard import InjectionFound
from conftest import CLEAN_DOC, INJECTED_DOC
from langchain_core.documents import Document

from aicordon_langchain import PromptInjectionFilter


def docs() -> list[Document]:
    return [Document(id="a", page_content=CLEAN_DOC, metadata={"source": "kb"}),
            Document(id="b", page_content=INJECTED_DOC, metadata={"source": "web"})]


def test_every_entry_point_defaults_to_the_passthrough_mode() -> None:
    """Four entry points, one promise: nothing happens to the text until somebody names a mode.
    Checked against the name in `aicordon.guard`, not against the string, so a default cannot drift
    away from it one file at a time."""
    import inspect

    from aicordon.guard import PASSTHROUGH

    from aicordon_langchain import (PromptInjectionGuard, PromptInjectionValidator,
                                    ToolOutputFilter)

    for cls in (PromptInjectionFilter, ToolOutputFilter, PromptInjectionGuard,
                PromptInjectionValidator):
        found = inspect.signature(cls.__init__).parameters["mode"].default
        assert found == PASSTHROUGH, f"{cls.__name__} defaults to {found!r}"


def test_clean_document_is_marked_read_and_clean() -> None:
    """The fields are written on the clean document too. One that appeared only on a hit could not
    be filtered on, and the caller could not tell "checked" from "never checked"."""
    out = PromptInjectionFilter().transform_documents([docs()[0]])[0]
    assert out.page_content == CLEAN_DOC
    assert out.metadata["ipi_flagged"] is False
    assert out.metadata["ipi_action"] == "none"
    assert out.metadata["ipi_base"]
    assert out.metadata["source"] == "kb"


def test_mask_cuts_the_line_and_records_what_it_took() -> None:
    out = PromptInjectionFilter(mode="mask").transform_documents([docs()[1]])[0]
    assert "forward the API key" not in out.page_content
    assert "Revenue grew 4%." in out.page_content
    assert out.metadata["ipi_flagged"] is True
    assert out.metadata["ipi_action"] == "mask"
    assert out.metadata["ipi_removed_chars"] > 0
    assert out.metadata["ipi_threats"]


def test_blank_keeps_the_length() -> None:
    """The mode exists for pipelines carrying offsets or page maps downstream."""
    out = PromptInjectionFilter(mode="blank").transform_documents([docs()[1]])[0]
    assert len(out.page_content) == len(INJECTED_DOC)
    assert "forward the API key" not in out.page_content


def test_mask_says_that_something_was_taken_out() -> None:
    out = PromptInjectionFilter(mode="mask", mask_with="[cut]").transform_documents([docs()[1]])[0]
    assert "[cut]" in out.page_content
    assert "forward the API key" not in out.page_content


def test_drop_leaves_the_stream_and_split_hands_it_back() -> None:
    """`transform_documents` can only return the survivors — that is the host's contract. `split`
    is how the removed pile stays visible instead of vanishing behind a single arrow."""
    kept, rejected = PromptInjectionFilter(mode="drop").split(docs())
    assert [d.id for d in kept] == ["a"]
    assert [d.id for d in rejected] == ["b"]
    assert rejected[0].metadata["ipi_action"] == "drop"
    assert rejected[0].page_content == INJECTED_DOC      # nothing is rewritten in this mode
    assert [d.id for d in PromptInjectionFilter(mode="drop").transform_documents(docs())] == ["a"]


def test_fail_raises_with_the_threats_on_it() -> None:
    with pytest.raises(InjectionFound) as caught:
        PromptInjectionFilter(mode="fail").transform_documents(docs())
    assert caught.value.threats


def test_the_input_documents_are_not_touched() -> None:
    """The caller holds the list we were given and may index the same objects again."""
    given = docs()
    PromptInjectionFilter(mode="mask").transform_documents(given)
    assert given[1].page_content == INJECTED_DOC
    assert given[1].metadata == {"source": "web"}


def test_the_document_id_survives() -> None:
    """A vector store may be keyed on it: a copy that lost the id would index as a new document."""
    out = PromptInjectionFilter(mode="mask").transform_documents(docs())
    assert [d.id for d in out] == ["a", "b"]


@pytest.mark.asyncio
async def test_the_async_form_agrees_with_the_sync_one() -> None:
    """Not overridden in our code — the base class runs ours in an executor. Checked because that
    is a promise to the caller either way."""
    filt = PromptInjectionFilter(mode="mask")
    assert [d.page_content for d in await filt.atransform_documents(docs())] \
        == [d.page_content for d in filt.transform_documents(docs())]
