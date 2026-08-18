"""Числа НА ДЕМОНСТРАЦИОННОМ наборе диалогов: что показывает витрина запроса, если её честно померить.

Пара к `measure_demo.py`: тот меряет материал (`ipi`), этот — запрос (`dpi`). И так же, как там,
эти числа НЕЛЬЗЯ выдавать за качество детектора: набор витринный, атаки подобраны из срабатывающих,
чистые — из молчащих. Мерные числа диалоговой стороны берутся на отложенных форумных джейлбрейках и
живом трафике и живут в README интеграции рядом.

Что здесь считается:

    заблокировано атак      — обмены, которые обёртка не пустила в модель
    чистые дошли до модели  — обмены, которые прошли нетронутыми
    расхождений с детектором — вердикт обёртки против голого TurnGuard на той же реплике; ОБЯЗАН
                               быть ноль. Обёртка не имеет права ни терять текст, ни добавлять
                               своего; если это число не ноль, остальные читать нельзя.

    python3 measure_demo_dialog.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

from aicordon.guard import DialogueGuard, TurnGuard          # noqa: E402


def main() -> int:
    rows = [json.loads(l) for l in (HERE / "dialogues.jsonl").open()]
    guard = DialogueGuard(mode="drop")
    guard.warm_up()
    bare = TurnGuard(mode="annotate")     # the same dpi rules, with no wrapper around them
    bare.warm_up()

    attacks = [r for r in rows if r["label"] == "attack"]
    cleans = [r for r in rows if r["label"] == "clean"]

    blocked = 0
    clean_through = 0
    mismatch = 0
    t0 = time.perf_counter()
    for r in rows:
        turns = [(role, text) for role, text in r["turns"]]
        verdict = guard.decide(turns)
        if r["label"] == "attack":
            blocked += verdict.flagged and not verdict.keep
        else:
            clean_through += verdict.keep and not verdict.flagged

        # The invariant: on every user turn, the wrapper's finding must equal the bare detector's.
        for role, text in turns:
            if role != "user" or not text:
                continue
            if bare.inspect(text).flagged != _turn_flagged(verdict, turns, text):
                mismatch += 1
    seconds = time.perf_counter() - t0

    n_turns = sum(len(r["turns"]) for r in rows)
    print(f"диалогов {len(rows)} ({len(attacks)} атак, {len(cleans)} чистых), "
          f"реплик {n_turns}, {seconds * 1000:.0f} мс "
          f"({seconds / len(rows) * 1000:.1f} мс на обмен), база {guard.base_version}\n")
    print(f"атак заблокировано       : {blocked}/{len(attacks)} ({blocked / len(attacks):.0%})")
    print(f"чистые дошли до модели   : {clean_through}/{len(cleans)} ({clean_through / len(cleans):.0%})")
    print(f"расхождений с детектором : {mismatch}   <- обязан быть 0")
    return 1 if mismatch else 0


def _turn_flagged(verdict, turns: list[tuple[str, str]], text: str) -> bool:
    """Whether the wrapper flagged the message carrying `text`, read off its per-message verdicts."""
    for i, (_role, t) in enumerate(turns):
        if t == text:
            found = verdict.per_message.get(i)
            return bool(found and found.flagged)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
