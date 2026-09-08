"""Check documents for indirect prompt injection before they are chunked and embedded.

The transformer sits between the loader and the splitter of an ingest, which in LangChain is a line
of your own code rather than a pipeline object:

    docs = TextLoader("kb.md").load()
    docs = PromptInjectionFilter().transform_documents(docs)   # or (mode="mask") to take it out
    chunks = RecursiveCharacterTextSplitter().split_documents(docs)

Everything it decides comes from `aicordon.guard.InjectionGuard`; what lives here is the translation
into LangChain's `Document` and its contract — nothing else, so the same policy serves the other
frameworks unchanged.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aicordon.guard import PASSTHROUGH, InjectionGuard
from langchain_core.documents import BaseDocumentTransformer, Document

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class PromptInjectionFilter(BaseDocumentTransformer):
    """Read documents with Picket's `ipi` rules and act on what is found.

    `transform_documents` returns the documents that go on to be indexed, which is what the host's
    contract allows it to return and nothing more. In `drop` mode that means documents leave the
    stream with only a log line to show for it — so `split()` is here as well, returning the two
    piles separately for a caller who wants to keep what was removed:

        kept, rejected = filt.split(docs)

    In every other mode the two calls are the same thing, `rejected` being empty.
    """

    def __init__(self, mode: str = PASSTHROUGH, meta_prefix: str = "ipi", blank_char: str = "*",
                 mask_with: str = "[prompt injection removed]") -> None:
        """Build the filter. The detector itself is not loaded until `warm_up()` or the first call.

        :param mode: `passthrough` (the default, which edits nothing), `blank`, `mask`, `drop` or
            `fail`. `mask_with=""` is how a block is cut out with nothing in its place.
        :param meta_prefix: prefix for the keys written into `Document.metadata`.
        :param blank_char: the character `blank` mode fills the block with.
        :param mask_with: what `mask` mode puts in place of the block.
        """
        self.mode = mode
        self.meta_prefix = meta_prefix
        self.blank_char = blank_char
        self.mask_with = mask_with
        self._guard = InjectionGuard(mode=mode, meta_prefix=meta_prefix, blank_char=blank_char,
                                     mask_with=mask_with)

    def warm_up(self) -> None:
        """Load the rule base now rather than on the first document. Optional; ingests are batches,
        so the 17 ms shows up once either way — this is for callers who time the first call."""
        self._guard.warm_up()

    def split(self, documents: Sequence[Document]) -> tuple[list[Document], list[Document]]:
        """The kept documents and the rejected ones, in the order they arrived."""
        kept: list[Document] = []
        rejected: list[Document] = []
        for doc in documents:
            verdict = self._guard.inspect(doc.page_content or "")
            if verdict.flagged:
                # Through the standard library logger under this module's name, at a level the host
                # controls: "write it to the log" is not a mode — it is wanted under `drop` and
                # under `passthrough` alike.
                logger.warning("prompt injection in a document at ingest: %s, action %s",
                               ", ".join(verdict.threats), self.mode)
            # A copy, never the input. The caller holds the list we were given and may well index
            # the same objects a second time; a `Document` is a pydantic model, so editing
            # `page_content` in place would rewrite theirs. `model_copy` also carries `id` over,
            # which a vector store may be using as its key.
            out = doc.model_copy(update={
                "page_content": verdict.text,
                "metadata": {**doc.metadata, **self._guard.meta(verdict)},
            })
            (kept if verdict.keep else rejected).append(out)
        return kept, rejected

    def transform_documents(self, documents: Sequence[Document], **kwargs: Any) -> list[Document]:
        """The host's contract: documents in, documents on. See `split()` for the rejected pile."""
        kept, _rejected = self.split(documents)
        return kept

    # `atransform_documents` is deliberately not overridden. The base class runs this one in an
    # executor, which is right for work that is CPU-bound and has no I/O to await: a coroutine of
    # our own would only be the same call with `async` written on it.
