"""The Intent detector: the full detector over the AI Cordon API. A STUB — there is no network call.

Exactly as much is written as it takes for the package interface to match `picket` already: the same
names, the same finding model, the same contract. Everything specific to it is the key and the API
address.

What has to appear when it is implemented:

    * the host address: from the map self-announcement mechanism (`feature host discovery`) or from
      a config — undecided, see CLI_SPEC;
    * sending in batches (`batch` is declared already — that is what the contract is batched for);
    * retries and timeouts. A network failure is `EngineUnavailable` and NOT an empty result:
      embedding code reads silence as "no injections", so a broken link would become a verdict;
    * no numeric confidence goes out: the detector output is nearly binary, and percentages would
      be invented precision (`detector-threshold-degenerate`).
"""
from __future__ import annotations

from typing import Iterable, Iterator

from aicordon.core.engine import BaseDetector, EngineUnavailable
from aicordon.core.model import Document, Finding

from .credentials import NO_KEY_HINT, SITE, find_key

DEFAULT_ENDPOINT = "https://api.ai-cordon.com/v1/scan"

LIMITS = (
    "works only with a key and a network: it has no local mode",
    "the cost of a call is network latency, not the milliseconds of a local rule",
    "the engine is not implemented in this build: a STUB",
)


class Detector(BaseDetector):
    """The same public interface as `picket.Detector`, on top of a remote detector."""

    name = "intent"
    title = "AI Cordon Intent (API)"
    version = "stub"
    requires = frozenset({"api_key", "network"})
    batch = 32
    limits = LIMITS
    coverage = "anything without a key and without a network"

    def __init__(self, api_key: str | None = None, endpoint: str | None = None) -> None:
        self._key = find_key(api_key)
        self._endpoint = endpoint or DEFAULT_ENDPOINT

    @property
    def measured(self) -> dict:
        # Empty on purpose: the numbers will come from a production run, not from expectations.
        return {}

    def available(self) -> None:
        if not self._key:
            raise EngineUnavailable("no API access key", hint=NO_KEY_HINT)
        raise EngineUnavailable("the intent engine is not implemented yet (a stub)",
                                hint=f"Watch for updates: {SITE}")

    def describe(self) -> dict:
        return {"endpoint": self._endpoint, "key": "found" if self._key else "not found"}

    def scan(self, docs: Iterable[Document]) -> Iterator[Finding]:
        self.available()             # always raises: a stub
        return iter(())              # unreachable; kept to satisfy the contract


def load(api_key: str | None = None, endpoint: str | None = None) -> Detector:
    return Detector(api_key=api_key, endpoint=endpoint)
