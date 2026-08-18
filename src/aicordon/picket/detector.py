"""Picket's detector: the frozen rule base. No model, no network.

The parsing lives in `aicordon.picket.rule` (`scan`, `frag`, `l2`, `norm`, `ac`, `ent`). This file only maps it
onto the shared `aicordon.core.engine` contract — the very same contract the `intent` package
implements.

Threat names and severities come FROM THE BASE (the `threat`/`severity` fields written by
`threats.py`), they are not reconstructed here by heuristics. Otherwise `explain` and `scan` would
drift apart at the first change of base, and a threat name from yesterday's report could not be
matched against today's rule.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Iterator

from aicordon.core.engine import BaseDetector, EngineUnavailable
from aicordon.core.model import Document, Evidence, Finding, Severity

from .rule.scan import DATA, Scanner, pick_base     # noqa: F401 — DATA is used by consumers
from .rule.threats import catalog, rank, signature   # noqa: F401 — signature is used by consumers


class Detector(BaseDetector):
    """The local detector. Raised once, then called as often as needed.

    Embedding code needs no more than:

        from aicordon.picket import Detector
        det = Detector()
        rep = det.check(text)
        if rep.flagged:
            ...
    """

    name = "lexical"
    title = "Picket"
    requires = frozenset()
    batch = 64

    def __init__(self, rules: Path | str | None = None, span_pad: int = 0,
                 mode: str = "ipi") -> None:
        """`mode` says where the text came from: `ipi` — data the agent read, `dpi` — a turn the
        user typed. It is a property of the CALL SITE, not of the document, which is why it is set
        once at construction: a gateway knows which field a string arrived in and cannot mistake
        one for the other. See `Scanner.scan` for what the modes change."""
        if mode not in ("ipi", "dpi"):
            raise ValueError(f"unknown mode {mode!r}: expected 'ipi' or 'dpi'")
        self._mode = mode
        self._pad = int(span_pad)
        try:
            # No base, a base from a newer schema, a damaged file — all of it comes out here as
            # "the engine is unavailable", which the shell turns into exit code 3 and a message.
            # The one thing that must never happen is a run continuing on some other base.
            self._path = Path(rules) if rules else pick_base()
            self._sc = Scanner(self._path)
        except SystemExit as e:                   # Scanner exits when it disagrees with the base
            raise EngineUnavailable(str(e)) from e
        except OSError as e:
            raise EngineUnavailable(f"cannot read the base file: {e}") from e
        self.spec = self._sc.spec
        self.version = self.spec["version"]
        # A rule without a name would mean a finding without a threat name in the report — better to
        # refuse to start than to print a verdict that `explain` cannot account for.
        if any(not r.get("threat") for r in self.spec["rules"]):
            raise EngineUnavailable(
                "the base contains rules with no threat name",
                hint="annotate the base: python3 -m aicordon.picket.rule.threats --annotate <base>")

    # --- contract ------------------------------------------------------------------------------

    @property
    def measured(self) -> dict:
        # The numbers belong to the MODE, not to the base: `measured` is the core on the indirect
        # corpus, `measured_dpi` the direct group on typed turns. Reporting one under the other's
        # name would be the quiet kind of wrong the caveat below warns about, so a mode with no
        # numbers of its own reports none rather than borrowing.
        m = self.spec.get("measured" if self._mode == "ipi" else f"measured_{self._mode}", {})
        out = {}
        if "eval_recall" in m:
            a, b = m.get("eval_recall_abs", ("?", "?"))
            # What the denominator counts is part of the number: recall by distinct payload and
            # recall by document differ by several points on the same run, and a base that reports
            # one under the other's label is the quiet kind of wrong. The basis travels with the
            # base rather than being fixed here, because it is a property of how that base was
            # measured.
            out[f"recall ({m.get('recall_basis', 'by seed')})"] = \
                f"{m['eval_recall']:.1%}  ({a} of {b})"
        if "eval_fpr" in m:
            a, b = m.get("eval_fpr_abs", ("?", "?"))
            out["false positives (FPR)"] = f"{m['eval_fpr']:.4%}  ({a} of {b})"
        if m.get("cross_check"):
            out["cross-check"] = m["cross_check"]
        if out:
            # Which mode these are is part of the numbers. Two modes, two corpora, two working
            # points: a reader who cannot see which one is on screen cannot use either.
            out = {"mode": self._mode, **out}
        if m.get("corpus"):
            out["corpus"] = m["corpus"]
        # The base still carries its frozen caveats — the report quotes them and `spec` keeps them —
        # but the command prints the working point, not an essay on it: what the check is worth is
        # the measurement above, and the standing warning underneath says an empty report is not a
        # clean bill. That is the whole caveat a run needs.
        return out

    def available(self) -> None:
        return None                               # a local engine is always available

    def describe(self) -> dict:
        raw = self._path.read_bytes()
        n_conj = sum(1 for r in self.spec["rules"] if r["kind"] == "conjunction")
        return {
            "base file": self._path.name,
            "formed": self.spec.get("frozen", "—"),
            # The digest is of the RULES, the fingerprint is of the FILE. Two builds of one base can
            # differ in bytes and agree in rules; a report should be able to say which it means.
            "rules digest": self.spec.get("digest", "—"),
            "fingerprint": hashlib.sha256(raw).hexdigest()[:16],
            "size": f"{len(raw) / 1024:.0f} KB",
            "rules": f"{len(self.spec['rules'])} ({n_conj} conjunctions)",
            "scope": self.spec.get("scope", ""),
            "span": f"base padding 50 chars, shift {self._pad:+d}",
            "mode": self._mode,
        }

    def catalog(self) -> dict:
        return catalog(self.spec)                  # the same code that annotated the base

    def scan(self, docs: Iterable[Document]) -> Iterator[Finding]:
        for d in docs:
            res = self._sc.scan(d.text, pad=self._pad, mode=self._mode)
            if not res["flagged"]:
                continue
            doc_span = tuple(res["span"]) if res["span"][0] >= 0 else None
            for fired in res["rules"]:
                # The threat name comes from the base by rule index, it is not derived from edges.
                rule = self.spec["rules"][fired["index"]]
                yield Finding(
                    doc_id=d.id,
                    engine=self.name,
                    engine_version=self.version,
                    threat=rule.get("threat", "IPI/Generic.Relation.A"),
                    severity=rule.get("severity", Severity.MEDIUM),
                    span=tuple(fired["span"]) if fired["span"][0] >= 0 else doc_span,
                    # The label is the THREAT NAME, not the pair of slots that matched: the slots
                    # are the base, and the base does not travel through the API any more than it
                    # travels through `explain`.
                    evidence=[Evidence(label=rule.get("threat", "IPI/Generic.Relation.A"),
                                       span=tuple(e["span"]) if e["span"][0] >= 0 else None,
                                       quote=e["text"]) for e in fired["edges"]],
                    # `rank` lets the shared merging pick the headline technique, `rules` carries
                    # the number of the rule in the base — what the verbose mode prints.
                    extra={"rank": rank(rule.get("threat", "")),
                           "refs": [fired["index"]],
                           "doc_span": list(doc_span) if doc_span else None},
                )


def load(rules: Path | str | None = None, span_pad: int = 0, mode: str = "ipi") -> Detector:
    """A ready detector. A separate function so embedding code need not know the class name.

    `mode` is `ipi` for text the agent read and `dpi` for a turn the user typed; see `Detector`."""
    return Detector(rules=rules, span_pad=span_pad, mode=mode)
