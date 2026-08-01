"""The detector contract: everything the shell and embedding code know about an engine.

One contract for every product, and that is the central architectural requirement: the `picket`
package and the `intent` package expose the same interface, so the shared CLI — and future adapters
for AI frameworks — are written once instead of once per detector.

An engine does NOT print, does NOT exit the process and does NOT know the output format. It returns
findings or raises `EngineUnavailable`; deciding what the user sees is the shell's job.
"""
from __future__ import annotations

from typing import Iterable, Iterator, Protocol, Sequence, runtime_checkable

from .model import Document, Finding, Report, report_of


class EngineUnavailable(Exception):
    """The engine exists but cannot work: no key, no network, no artifact.

    `hint` says what the user should do. It is a separate field rather than part of the text so the
    shell can present the hint differently from the reason (as a link, for instance).

    A dedicated exception rather than an empty result: silence reads to embedding code as "nothing
    found", which turns an unavailable detector into a verdict. That is exactly the mistake SPEC §2
    forbids when it bans the verdict "clean".
    """

    def __init__(self, reason: str, hint: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint


@runtime_checkable
class Detector(Protocol):
    """The minimum a product package must provide."""

    name: str            # lexical, intent — engine name; goes into findings and into JSON
    version: str         # rule_v1, aicordon/v1.1 — version of the BASE, not of the tool
    title: str           # human-readable name for the report
    coverage: str        # one line: what the engine does NOT see; goes into the report footer
    limits: Sequence[str]        # the same in detail, itemised — the `coverage` command
    measured: dict               # measured numbers with caveats; an empty dict is allowed
    requires: frozenset          # {"network", "api_key"} — what the engine depends on
    batch: int                   # how many documents to hand over at a time

    def available(self) -> None:
        """Returns nothing; raises `EngineUnavailable` if it cannot work."""

    def catalog(self) -> dict:
        """Threat name -> severity, description, what triggers it. Basis of the `explain` command."""

    def describe(self) -> dict:
        """What the engine rests on: base file, fingerprint, API address. Basis of `check`."""

    def scan(self, docs: Iterable[Document]) -> Iterable[Finding]:
        """Batched: a per-document call to a remote engine would mean thousands of round trips."""


class BaseDetector:
    """Ready-made conveniences on top of `scan`. A product package inherits it.

    This is where everything EMBEDDING code needs lives, identical for any engine: check a string,
    check a list of strings, get reports for documents. If every package wrote this itself the
    signatures would drift apart, and a framework adapter would have to be written twice.

    A subclass only has to implement `scan` and declare the contract attributes.
    """

    name = "base"
    version = "0"
    title = "detector"
    coverage = ""
    limits: Sequence[str] = ()
    measured: dict = {}
    requires: frozenset = frozenset()
    batch = 64

    def available(self) -> None:
        return None

    def catalog(self) -> dict:
        return {}

    def describe(self) -> dict:
        return {}

    def scan(self, docs: Iterable[Document]) -> Iterable[Finding]:
        raise NotImplementedError

    # --- what makes the package fit for embedding ---------------------------------------------

    def reports(self, docs: Iterable[Document]) -> Iterator[Report]:
        """One report per document, streamed, preserving input order.

        Order is mandatory: embedding code matches reports to its own documents by position, and a
        reordering would silently swap verdicts. Documents therefore go out in batches of `batch`,
        and findings within a batch are grouped by `doc_id`.
        """
        for chunk in _chunks(docs, max(1, int(self.batch))):
            by_doc: dict[str, list[Finding]] = {d.id: [] for d in chunk}
            for f in self.scan(chunk):
                by_doc.setdefault(f.doc_id, []).append(f)
            for d in chunk:
                yield report_of(d.id, self.name, self.version, by_doc.get(d.id, []))

    def check(self, text: str, doc_id: str = "text") -> Report:
        """Check a single string. The most common call from someone else's code."""
        return next(iter(self.reports([Document(id=doc_id, text=text)])))

    def check_all(self, texts: Iterable[str]) -> Iterator[Report]:
        """Check many strings; identifiers are their ordinal positions."""
        docs = (Document(id=str(i), text=t) for i, t in enumerate(texts))
        return self.reports(docs)

    # --- the same, for code that runs in an event loop ------------------------------------------
    #
    # The check is CPU work, and CPU work in a coroutine blocks the loop that awaits it. One
    # document costs a couple of milliseconds and would pass unnoticed; a batch of ten thousand
    # stalls everything else in the process for half a minute. Both frameworks this package is
    # meant to plug into are async-first, so the offload belongs HERE — written once, identical for
    # every engine — rather than in each adapter, where the versions would drift.
    #
    # `to_thread` and not a process: the detector holds no per-call state and was measured
    # thread-safe, so several checks can genuinely run at once — and for the remote engine the wait
    # is the network anyway.

    async def acheck(self, text: str, doc_id: str = "text") -> Report:
        """`check` without blocking the event loop."""
        import asyncio
        return await asyncio.to_thread(self.check, text, doc_id)

    async def acheck_all(self, texts: Iterable[str]) -> list[Report]:
        """`check_all` without blocking the event loop; the result is a list, order preserved.

        A list rather than an async iterator on purpose: the reports are produced in one offloaded
        pass, and pretending they arrive one by one would suggest a streaming guarantee the engine
        does not give.
        """
        import asyncio
        return await asyncio.to_thread(lambda: list(self.check_all(texts)))


def _chunks(items: Iterable, size: int) -> Iterator[list]:
    """Slices a stream into batches without materialising the input — readiness criterion §10.6."""
    buf: list = []
    for x in items:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


# The former name of the contract; "engine" and "detector" mean the same thing in these documents.
Engine = Detector
