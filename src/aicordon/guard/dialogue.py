"""What to do with the exchange the model is about to be sent.

This is the request side of the pair described in `guard.py`. Two things live here: a guard for one
typed turn, and the policy for a whole exchange in which more than one role may need checking.

THE TURN IS READ WITH `dpi`. Picket's 67 `dpi` conjunctions are written for a jailbreak somebody
typed, disjoint from the 313 that look for an instruction planted in material. The working point is
in the package's own report, `docs/eval/direct-jailbreaks-2026-08.md`: one alarm per thousand real
user turns.

NOT EVERY MESSAGE IN AN EXCHANGE IS A REQUEST. A tool result sitting in the message list is material
by any reading — the model is to work on it, not answer it — and so it is read with `ipi` if the
caller asks for it to be read at all. That is the whole of the role map: a role name to the rule set
that fits what that role carries.

It is off by default for `tool`, and the reason is a number rather than caution. The `ipi` rules
raise eight times as many alarms over live chat text as over documents — 0.800% against 0.101% on
43 489 turns — and what they fire on there is agent prompts, command lists and code, which is what a
tool result looks like. Switch the role on and measure your own tool outputs before believing it.

NOTHING HERE REWRITES A TEXT, and the editing modes are refused rather than discouraged.

Three separate reasons, and each on its own is enough:

* The cut is fitted to the wrong shape. `guard.py` grows a span to the line that holds it because a
  planted instruction is spliced into a document as its own line. A typed jailbreak is not spliced
  into anything — it IS the turn, commonly a page of role-play with the demand distributed through
  it, so "the line around the span" is a fragment of an attack and what is left is the rest of it.
* A request with a hole in it is still a request, and now a corrupted one. Material can lose a
  paragraph and remain usable; take a clause out of what somebody asked for and the model answers a
  question nobody put. The failure is silent — the user sees an answer, not a notice.
* Nothing measures it. Every number for the cut in `guard.py` was taken on documents with a known
  planted span. There is no such ground truth for a typed attack, so an editing mode here would be
  shipping an unmeasured policy behind a familiar name.

Redacting a tool result IS measured, and it belongs at the point the tool returns — the same ingest
point as any other material — not in a component that decides whether to answer a turn.

THE DEFAULT ANSWERS THE TURN. `passthrough` here too: the exchange is read, what was found is written
into the metadata, and it goes to the model. `drop` was the default up to 1.1.1 and it is the mode
to move to once the alarm rate is known on your own traffic — but a component that silently stops
answering users the moment it is wired in is the same surprise as one that silently edits a
document, and in a pipeline whose `blocked` output was never connected it is a turn that disappears
with nothing said anywhere. The reasoning is one for both sides; it is written out in `guard.py`.

THE UNIT IS THE EXCHANGE, NOT THE MESSAGE. `DialogueGuard.decide` returns one verdict for the list
it was given. Dropping the offending message and calling the model with what is left is not a
defence: the model then answers the message before it, and the caller who wired a single arrow never
learns the turn went missing. The wrapper routes the whole exchange one way or the other.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .guard import NON_EDITING_MODES, PASSTHROUGH, InjectionGuard, Verdict, _Guard

__all__ = ["TurnGuard", "DialogueGuard", "ExchangeVerdict", "DEFAULT_ROLES"]

#: Which rule set reads which role, by default. `user` is the request. `assistant` is the model's
#: own text and checking it would be measuring ourselves; `system` is the operator's, and an
#: operator who wants to attack their own model does not need an injection to do it. `tool` is
#: material and is left to the caller to switch on — see the module docstring.
DEFAULT_ROLES = {"user": "dpi"}


@dataclass(frozen=True)
class ExchangeVerdict:
    """One decision for the exchange, plus what was found in each message that was checked.

    `per_message` is keyed by the caller's own index into the list it passed in, so a wrapper can
    put a finding back on the message it came from without matching texts.
    """

    keep: bool                          #: False when the exchange must not reach the model
    flagged: bool
    threats: tuple[str, ...]            #: union over the messages, in order of first appearance
    per_message: dict[int, Verdict] = field(default_factory=dict)


class TurnGuard(_Guard):
    """One typed turn, read with Picket's `dpi` rules. Marks or rejects; never rewrites.

    By default it only marks: the turn is passed on with the finding attached to it."""

    detector_mode = "dpi"
    allowed_modes = NON_EDITING_MODES

    def __init__(self, mode: str = PASSTHROUGH, meta_prefix: str = "dpi") -> None:
        super().__init__(mode=mode, meta_prefix=meta_prefix)


class DialogueGuard:
    """The policy a chat wrapper holds: which roles to read with which rules, and what to do then.

    :param mode: `passthrough` (the default), `drop` or `fail`, applied to the exchange as a whole.
    :param roles: role name to rule set, `ipi` or `dpi`. Defaults to `DEFAULT_ROLES`.
    :param meta_prefix: prefix for the metadata keys the wrapper attaches.
    """

    def __init__(self, mode: str = PASSTHROUGH, roles: dict[str, str] | None = None,
                 meta_prefix: str = "picket") -> None:
        if mode not in NON_EDITING_MODES:
            raise ValueError(f"a dialogue is guarded in mode {NON_EDITING_MODES}, got {mode!r}")
        roles = dict(DEFAULT_ROLES if roles is None else roles)
        self.mode = mode
        self.roles = roles
        self.meta_prefix = meta_prefix
        self._guards: dict[str, _Guard] = {}
        for role, rules in roles.items():
            if rules == "dpi":
                self._guards[role] = TurnGuard(mode=mode, meta_prefix=meta_prefix)
            elif rules == "ipi":
                # The same detector the ingest filter uses, held to this side's policy: material
                # inside an exchange is still read with `ipi`, but a component that decides whether
                # to answer does not get to rewrite what it was given.
                self._guards[role] = InjectionGuard(mode=mode, meta_prefix=meta_prefix)
            else:
                raise ValueError(f"role {role!r}: rules must be 'ipi' or 'dpi', got {rules!r}")

    def warm_up(self) -> None:
        for guard in self._guards.values():
            guard.warm_up()

    @property
    def base_version(self) -> str:
        """The rule base behind every mode — one artefact, so one version for the whole map."""
        for guard in self._guards.values():
            return guard.base_version
        return "none"

    def reads(self, role: str) -> bool:
        return role in self._guards

    def decide(self, messages: list[tuple[str, str]]) -> ExchangeVerdict:
        """Answer for the exchange. `messages` is `(role, text)` in the order they will be sent.

        Roles outside the map are not read at all — not "read and found clean". In `fail` mode
        `InjectionFound` comes out of the first flagged message, which is the mode's point.
        """
        found: dict[int, Verdict] = {}
        threats: dict[str, None] = {}
        for i, (role, text) in enumerate(messages):
            guard = self._guards.get(role)
            if guard is None or not text:
                continue
            verdict = guard.inspect(text)
            found[i] = verdict
            if verdict.flagged:
                threats.update(dict.fromkeys(verdict.threats))
        flagged = bool(threats)
        return ExchangeVerdict(keep=not (flagged and self.mode == "drop"), flagged=flagged,
                               threats=tuple(threats), per_message=found)

    def meta(self, verdict: ExchangeVerdict, index: int) -> dict[str, Any]:
        """Metadata for the message at `index`, written whether or not anything was found in it.

        A message whose role is not in the map gets NOTHING, and that is the point: an empty
        metadata block means "not read", which is a different fact from "read and clean" and the
        caller has no other way to tell them apart. For a message that was read, the fields are
        always present, because one that appears only on a hit cannot be filtered on.
        """
        found = verdict.per_message.get(index)
        if found is None:
            return {}
        p = self.meta_prefix
        out: dict[str, Any] = {
            f"{p}_flagged": found.flagged,
            f"{p}_action": self.mode if found.flagged else "none",
            f"{p}_base": self.base_version,
        }
        if found.flagged:
            out[f"{p}_threats"] = list(found.threats)
            out[f"{p}_spans"] = [list(sp) for sp in found.spans]
        return out
