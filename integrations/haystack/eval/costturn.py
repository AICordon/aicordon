"""Цена проверки ОДНОЙ реплики — то число, которое читатель README прикидывает на свой трафик.

Почему отдельным замером, а не разностью плеч в `measure_dialog.py`. Там пул смешанный: 537
форумных джейлбрейков в тысячи символов рядом с двадцатью тысячами живых реплик. Средняя по такой
смеси — свойство состава замера, а не трафика, и на чужом трафике не воспроизведётся. Здесь пул —
только живые реплики WildChat, а длина, от которой цена и зависит, показана рядом.

ЧЕТЫРЕ УРОВНЯ, ЧТОБЫ ВИДЕТЬ, КОМУ ИДЁТ КАЖДАЯ ДОЛЯ:

    detector    голый `picket.check` — цена самой проверки, это Пикет
    policy      + карта ролей и сборка вердикта на обмен (`DialogueGuard`) — наше ядро
    component   + `run()`: чтение частей сообщения, копии, метаданные — наша обёртка
    pipeline    + `Pipeline.run()` — диспетчер Haystack, чужой код

Сообщения строятся ДО таймера, а не внутри: их в настоящем конвейере собирает prompt builder, и
записывать их сборку в цену проверки значило бы приписать себе чужой расход. Ровно так же
`pipeline` показан отдельной строкой: это цена шага конвейера у хоста, её платят все компоненты
подряд, и наша она только в том смысле, что мы попросили ещё один шаг.

ПРОЦЕДУРА — как в `experiments/40_prefilter/`: R повторов всего пула, по реплике берётся МЕДИАНА
повторов (снимает шум планировщика), и уже по репликам считается распределение. Погрешность
headline-числа — стандартное отклонение средних по повторам. Числа стоимости плавают с загрузкой
машины: сравнивать можно только снятые одной процедурой в одном прогоне.

    python eval/costturn.py --turns 3000 --repeat 5
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import logging as _logging

from haystack import Pipeline
from haystack.dataclasses import ChatMessage
from haystack_integrations.components.validators.aicordon import PromptInjectionGuard

DIRECT = Path("/home/mike/Projects/ai-safity/experiments/45_picket_direct/data/direct.jsonl")
HERE = Path(__file__).resolve().parent
CLEAN_SLICE = "wildchat_user"
SYSTEM = "You are a helpful assistant."
BUCKETS = [(0, 200), (200, 500), (500, 1500), (1500, 4000), (4000, 10 ** 9)]


def pool(n: int) -> list[str]:
    rows = [json.loads(l) for l in DIRECT.open() if f'"{CLEAN_SLICE}"' in l]
    rows = [r for r in rows if r["slice"] == CLEAN_SLICE and (r["text"] or "").strip()]
    return [r["text"] for r in rows[::max(1, len(rows) // n)][:n]]


def warm_up_cost(repeat: int) -> list[float]:
    """Разовая цена: поднять базу. Платится один раз за процесс, а не за реплику."""
    out = []
    for _ in range(repeat):
        guard = PromptInjectionGuard()
        t0 = time.perf_counter()
        guard.warm_up()
        out.append((time.perf_counter() - t0) * 1000)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=3000)
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--json", default="result-costturn.json")
    a = ap.parse_args()

    # Компонент пишет предупреждение на каждую находку — здесь они только мешают читать прогресс.
    _logging.getLogger("haystack_integrations.components.validators.aicordon"
                       ".prompt_injection_guard").setLevel(_logging.ERROR)
    turns = pool(a.turns)
    lengths = sorted(len(t) for t in turns)
    print(f"реплик {len(turns)}, символов: медиана {lengths[len(lengths) // 2]}, "
          f"p90 {lengths[int(len(lengths) * 0.9)]}, максимум {lengths[-1]}", flush=True)

    from aicordon import picket
    det = picket.load(mode="dpi")
    component = PromptInjectionGuard()
    component.warm_up()
    guard = component._guard

    pipe = Pipeline()
    pipe.add_component("guard", PromptInjectionGuard())
    pipe.get_component("guard").warm_up()

    def bare(text: str) -> None:
        det.check(text)

    def policy(text: str) -> None:
        guard.decide([("system", SYSTEM), ("user", text)])

    # Готовые сообщения: их сборка — расход prompt builder'а, а не проверки.
    built = {t: [ChatMessage.from_system(SYSTEM), ChatMessage.from_user(t)] for t in set(turns)}

    def wrapper(text: str) -> None:
        component.run(built[text])

    def wired(text: str) -> None:
        pipe.run({"guard": {"messages": built[text]}})

    levels = {"detector": bare, "policy": policy, "component": wrapper, "pipeline": wired}
    # По реплике на уровень: список времён по повторам.
    samples = {name: [[] for _ in turns] for name in levels}
    for r in range(1, a.repeat + 1):
        for name, fn in levels.items():
            for i, text in enumerate(turns):
                t0 = time.perf_counter()
                fn(text)
                samples[name][i].append((time.perf_counter() - t0) * 1000)
        print(f"  повтор {r}/{a.repeat}", flush=True)

    out: dict = {"turns": len(turns), "repeats": a.repeat,
                 "chars_median": lengths[len(lengths) // 2],
                 "chars_p90": lengths[int(len(lengths) * 0.9)],
                 "base": guard.base_version, "levels": {}}
    for name in levels:
        per_turn = sorted(statistics.median(v) for v in samples[name])
        # Погрешность headline-числа — разброс СРЕДНИХ по повторам, не по репликам: реплики разной
        # длины, и их разброс — это разброс трафика, а не неопределённость замера.
        per_repeat_mean = [statistics.fmean(samples[name][i][r] for i in range(len(turns)))
                           for r in range(a.repeat)]
        out["levels"][name] = {
            "mean": statistics.fmean(per_turn),
            "sd_of_repeat_means": statistics.stdev(per_repeat_mean) if a.repeat > 1 else 0.0,
            "median": per_turn[len(per_turn) // 2],
            "p90": per_turn[int(len(per_turn) * 0.9)],
            "p99": per_turn[int(len(per_turn) * 0.99)],
            "max": per_turn[-1],
        }

    # Разбивка по длине — на верхнем уровне, то есть то, что платит пользователь.
    med = {i: statistics.median(v) for i, v in enumerate(samples["pipeline"])}
    out["by_length"] = []
    for lo, hi in BUCKETS:
        idx = [i for i, t in enumerate(turns) if lo <= len(t) < hi]
        if idx:
            out["by_length"].append({"from": lo, "to": None if hi > 10 ** 8 else hi,
                                     "turns": len(idx),
                                     "median_ms": statistics.median(med[i] for i in idx)})

    warm = warm_up_cost(a.repeat)
    out["warm_up_ms_median"] = statistics.median(warm)
    (HERE / a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print()
    print(f"{'уровень':11s} {'среднее':>16s} {'медиана':>9s} {'p90':>7s} {'p99':>7s} {'макс':>8s}")
    for name, v in out["levels"].items():
        print(f"{name:11s} {v['mean']:8.2f} ± {v['sd_of_repeat_means']:.2f} мс "
              f"{v['median']:8.2f} {v['p90']:7.2f} {v['p99']:7.2f} {v['max']:8.1f}")
    lv = out["levels"]
    top = lv["pipeline"]["mean"]
    print(f"\nиз {top:.2f} мс: детектор {lv['detector']['mean']:.2f}, "
          f"ядро {lv['policy']['mean'] - lv['detector']['mean']:+.2f}, "
          f"обёртка {lv['component']['mean'] - lv['policy']['mean']:+.2f}, "
          f"конвейер Haystack {top - lv['component']['mean']:+.2f}")
    print("\nпо длине реплики (медиана, весь путь):")
    for b in out["by_length"]:
        rng = f"{b['from']}–{b['to']}" if b["to"] else f"{b['from']}+"
        print(f"  {rng:>12s} символов  {b['turns']:5d} реплик  {b['median_ms']:6.2f} мс")
    print(f"\nразовая загрузка базы: {out['warm_up_ms_median']:.0f} мс")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
