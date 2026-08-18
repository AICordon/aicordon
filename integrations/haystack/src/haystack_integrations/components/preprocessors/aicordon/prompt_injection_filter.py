"""Check documents for indirect prompt injection before they are chunked and embedded.

The component sits between the converter and the splitter of an indexing pipeline. Everything it
decides comes from `aicordon.guard.InjectionGuard`; what lives here is the translation into
Haystack's types and its contract — nothing else, so the same policy serves the other frameworks
unchanged.

    pipe.add_component("ipi_filter", PromptInjectionFilter(mode="redact"))
    pipe.connect("converter.documents", "ipi_filter.documents")
    pipe.connect("ipi_filter.documents", "splitter.documents")
    pipe.connect("ipi_filter.rejected", "quarantine.documents")   # optional, nothing is lost silently
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from aicordon.guard import InjectionGuard
from haystack import Document, component, default_from_dict, default_to_dict, logging

logger = logging.getLogger(__name__)


@component
class PromptInjectionFilter:
    """Two outputs on purpose: what goes on to be indexed, and what was taken out of the stream.

    A component that only returned the survivors would drop documents where the pipeline diagram
    shows a single arrow, and a reader of that diagram would never learn it. With `rejected` as its
    own socket, removal is a connection someone chose to make — to a quarantine store, to a log, or
    to nothing at all, but visibly.
    """

    def __init__(self, mode: str = "redact", meta_prefix: str = "ipi", blank_char: str = "*",
                 mask_with: str = "[prompt injection removed]") -> None:
        # Only strings here: Haystack requires init parameters to be JSON-serialisable so that a
        # pipeline can be saved and loaded. The detector is built in `warm_up()` instead, which is
        # the hook the framework offers for state too heavy to raise during pipeline validation.
        #
        # KEPT ON THE INSTANCE UNDER THE PARAMETER NAMES, and serialised explicitly below. Without
        # both, saving a pipeline loses the settings SILENTLY: with no `to_dict` the framework reads
        # each init parameter back with `getattr(self, name)`, and when that fails it falls back to
        # the default in the signature. A pipeline built with mode="annotate" came back out of YAML
        # as "redact", with nothing raised anywhere.
        self.mode = mode
        self.meta_prefix = meta_prefix
        self.blank_char = blank_char
        self.mask_with = mask_with
        self._guard = InjectionGuard(mode=mode, meta_prefix=meta_prefix, blank_char=blank_char,
                                     mask_with=mask_with)

    def to_dict(self) -> dict[str, Any]:
        return default_to_dict(self, mode=self.mode, meta_prefix=self.meta_prefix,
                               blank_char=self.blank_char, mask_with=self.mask_with)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptInjectionFilter":
        return default_from_dict(cls, data)

    def warm_up(self) -> None:
        self._guard.warm_up()

    @component.output_types(documents=list[Document], rejected=list[Document])
    def run(self, documents: list[Document]) -> dict[str, Any]:
        kept: list[Document] = []
        rejected: list[Document] = []
        for doc in documents:
            verdict = self._guard.inspect(doc.content or "")
            if verdict.flagged:
                # Logged through the host's logger, at a level the host controls: "write it to the
                # log" is not a mode — it is wanted under `drop` and under `annotate` alike.
                logger.warning("prompt injection in a document at ingest: {threats}, action {mode}",
                               threats=", ".join(verdict.threats), mode=self.mode)
            # A copy, never the input: the same list can be connected to a second branch of the
            # pipeline, and editing in place would rewrite that branch's documents too.
            out = replace(doc, content=verdict.text, meta={**doc.meta, **self._guard.meta(verdict)})
            (kept if verdict.keep else rejected).append(out)
        return {"documents": kept, "rejected": rejected}
