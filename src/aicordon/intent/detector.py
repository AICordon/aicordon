"""Intent detector: a client for the AI Cordon API with the same interface as `picket`.

    det = intent.load()          # key: argument, AICORDON_API_KEY, `aicordon login`
    rep = det.check(letter)      # Report, as Picket returns it
    a = det.assess(letter)       # full answer: score, verdict, spans, version

`assess` is for benchmarks: they need a score for every document, and a Report holds findings only.

Error handling:
  * network failure -> `EngineUnavailable`, never an empty result (callers read silence as "nothing
    found");
  * a document the service does not judge (too short, too long) -> no findings, `judged=False`;
  * 429, 5xx and dropped connections are retried with backoff and `Retry-After`; other errors raise.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Iterable, Iterator

from aicordon.core import VERSION
from aicordon.core.engine import BaseDetector, EngineUnavailable
from aicordon.core.model import Document, Evidence, Finding, Severity

from . import credentials as cred

DEFAULT_ENDPOINT = cred.DEFAULT_BASE_URL          # kept under the name the stub exported
DEFAULT_DETECTOR = "intent"
THREAT = "IPI/Intent"
_RETRY = frozenset({429, 500, 502, 503, 504})

LIMITS = (
    "needs an API key and the network: it has no local mode",
    "the cost of a call is network latency, not the milliseconds of a local rule",
    "a text of fewer than about a dozen tokens is not judged: no finding, and that is not a verdict",
    "it finds WHERE an instruction sits, not which technique it uses: every finding is " + THREAT,
)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    p: float                         # the detector's probability for this fragment


@dataclass(frozen=True)
class Assessment:
    """The API answer for one document. `flagged` is the service's decision at its threshold."""

    doc_id: str
    judged: bool
    flagged: bool = False
    score: float | None = None
    threshold: float | None = None
    spans: tuple[Span, ...] = ()
    verdicts: dict = field(default_factory=dict)        # operating point -> decision, e.g. "1e-04"
    false_alarm_rate: float | None = None
    version: str = ""
    reason: str = ""                                    # why it was not judged, when it was not

    @classmethod
    def from_api(cls, doc_id: str, a: dict) -> "Assessment":
        if a.get("scored") is False or a.get("score") is None:
            return cls(doc_id, judged=False, reason=a.get("reason") or "not_scored",
                       threshold=a.get("threshold"), version=a.get("version") or "")
        spans = tuple(Span(int(f["span"][0]), int(f["span"][1]), float(f.get("p", a["score"])))
                      for f in a.get("flagged") or () if f.get("span"))
        return cls(doc_id, judged=True, flagged=bool(a.get("is_injection")), score=float(a["score"]),
                   threshold=a.get("threshold"), spans=spans, verdicts=a.get("verdicts") or {},
                   false_alarm_rate=a.get("false_alarm_rate"), version=a.get("version") or "")


class Detector(BaseDetector):
    """Same public interface as `picket.Detector`. Thread-safe.

    The API takes one document per request; a batch is sent as `workers` parallel requests.
    """

    name = "intent"
    title = "AI Cordon Intent"
    version = "api"                  # replaced by the version the service reports on its first answer
    requires = frozenset({"api_key", "network"})
    batch = 32
    limits = LIMITS
    coverage = "anything without a key and a network; texts too short to judge"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, *,
                 detector: str = DEFAULT_DETECTOR, timeout: float = 60.0, max_retries: int = 5,
                 workers: int = 4, fpr: str | float | None = None, endpoint: str | None = None) -> None:
        self._key = cred.find_key(api_key)
        self._key_source = cred.key_source(api_key)
        self._base = cred.base_url(base_url or endpoint)
        self._detector = detector
        self._timeout = timeout
        self._retries = max(0, int(max_retries))
        self._workers = max(1, int(workers))
        # None: the service's decision (default 1e-4). "1e-3" / "1e-4" / "1e-5": the verdict the
        # service returns for that operating point.
        self._fpr = None if fpr is None else f"{float(fpr):.0e}"

    def __repr__(self) -> str:
        return f"intent.Detector(base_url={self._base!r}, detector={self._detector!r}, key={cred.mask(self._key)})"

    # --- contract ------------------------------------------------------------------------------

    @property
    def measured(self) -> dict:
        # Published numbers live in the benchmark reports, not in the client.
        return {}

    def available(self) -> None:
        # No network call: the CLI probes every product on start. A bad key fails on the first request.
        if not self._key:
            raise EngineUnavailable("no API key", hint=cred.NO_KEY_HINT)

    def describe(self) -> dict:
        return {"endpoint": self._base, "detector": self._detector,
                "operating point": f"FPR {self._fpr}" if self._fpr else "the service default",
                "key": f"{cred.mask(self._key)} ({self._key_source})" if self._key else "not found",
                "version": self.version}

    def catalog(self) -> dict:
        return {THREAT: {
            "threat": THREAT, "severity": Severity.HIGH, "family": "Intent", "technique": "Intent",
            "description": "An instruction addressed to the model that reads this text, found by the "
                           "full detector: the span is where it sits, the technique is not named.",
            "rules": []}}

    def scan(self, docs: Iterable[Document]) -> Iterator[Finding]:
        docs = list(docs)
        for doc, a in zip(docs, self.assess_all(docs)):
            if not a.flagged:
                continue
            # Flagged without spans: report the whole document.
            for s in a.spans or (Span(0, len(doc.text), a.score or 0.0),):
                quote = doc.text[s.start:s.end]
                yield Finding(doc_id=doc.id, engine=self.name, engine_version=a.version or self.version,
                              threat=THREAT, severity=Severity.HIGH, span=(s.start, s.end),
                              evidence=[Evidence(label=THREAT, span=(s.start, s.end), quote=quote.strip())],
                              extra={"p": round(s.p, 4)})

    # --- the raw answer ------------------------------------------------------------------------

    def assess(self, text: str, doc_id: str = "text") -> Assessment:
        """Judge one text; the service's full answer, including score and version."""
        return self._assess(Document(id=doc_id, text=text))

    def assess_all(self, docs: Iterable[Document]) -> list[Assessment]:
        """Judge many documents, `workers` at a time; results in input order."""
        docs = list(docs)
        self.available()
        if len(docs) <= 1 or self._workers == 1:
            return [self._assess(d) for d in docs]
        with ThreadPoolExecutor(min(self._workers, len(docs))) as pool:
            return list(pool.map(self._assess, docs))

    def _assess(self, doc: Document) -> Assessment:
        answer = self._post("/api/v1/detect", {"text": doc.text, "detector": self._detector})
        if answer is None:                                  # 413: the service will not take it at all
            return Assessment(doc.id, judged=False, reason="too_large")
        a = Assessment.from_api(doc.id, answer)
        if self._fpr and a.judged:
            if self._fpr not in a.verdicts:
                raise EngineUnavailable(f"the service offers no operating point {self._fpr}: "
                                        f"{sorted(a.verdicts) or 'none'}")
            a = replace(a, flagged=bool(a.verdicts[self._fpr]))
        if a.version and self.version != a.version:
            self.version = a.version
        return a

    def _post(self, path: str, body: dict) -> dict | None:
        self.available()
        data = json.dumps(body, ensure_ascii=False).encode()
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
                   "Accept": "application/json", "User-Agent": f"aicordon/{VERSION}"}
        last = ""
        for attempt in range(self._retries + 1):
            req = urllib.request.Request(self._base + path, data=data, headers=headers, method="POST")
            wait = None
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                err = _error_body(e)
                if e.code == 413:
                    return None
                if e.code in (401, 403):
                    raise EngineUnavailable(f"the API key was rejected ({err or e.code})",
                                            hint=cred.NO_KEY_HINT) from None
                if e.code == 402:
                    raise EngineUnavailable(f"the account cannot pay for the request ({err})",
                                            hint=f"Top up at {cred.SITE}") from None
                if e.code not in _RETRY:
                    raise EngineUnavailable(f"the API refused the request: HTTP {e.code} {err}") from None
                last = f"HTTP {e.code} {err}".strip()
                wait = _retry_after(e)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = str(getattr(e, "reason", e))
            if attempt < self._retries:
                time.sleep(wait if wait is not None else min(30.0, 2 ** attempt) * (0.5 + random.random()))
        raise EngineUnavailable(f"no answer from {self._base} after {self._retries + 1} attempts: {last}",
                                hint="Check the network and the service status, then retry.")


def _error_body(e: urllib.error.HTTPError) -> str:
    try:
        raw = e.read()[:500].decode("utf-8", "replace")
    except Exception:                                       # noqa: BLE001 — the body is best effort
        return ""
    try:
        d = json.loads(raw)
        return str(d.get("message") or d.get("error") or d.get("detail") or raw)
    except ValueError:
        return raw.strip()


def _retry_after(e: urllib.error.HTTPError) -> float | None:
    try:
        return min(60.0, max(0.0, float(e.headers.get("Retry-After", ""))))
    except (TypeError, ValueError):
        return None


def load(api_key: str | None = None, base_url: str | None = None, **kw) -> Detector:
    """A ready detector. The key and the address are looked up as `credentials` describes."""
    return Detector(api_key=api_key, base_url=base_url, **kw)
