"""Демонстрационный корпус для интеграций: 500 документов, половина заражена.

ЭТО ВИТРИНА, А НЕ МЕРА. Заражённая половина набрана так, чтобы большая её часть срабатывала:
примеры в README и в карточках каталогов должны показывать работу. Измеренные числа берутся с
квадрата и стоят в тех же документах отдельно — подменять одно другим нельзя. Поэтому же остаток
добирается СЛУЧАЙНЫМИ нагрузками: набор, где ловится всё, обманывает даже без умысла — читатель
уносит сто процентов как свойство инструмента, а не как свойство подборки.

Состав:

    250 заражённых   нагрузки, срабатывающие как есть; добор в служебных рамках (это настоящий
                     приём, `forged_frame`, а не подкрутка); остаток — случайными из банка
    250 чистых       носители без вставки, тех же видов и в тех же долях

Нагрузки — из нашего банка, который с опубликованным квадратом НЕ пересекается (сверка текстов:
0 совпадений), поэтому демонстрации не растаскивают мерный набор.

ВСЕ НОСИТЕЛИ ПРОВЕРЕНЫ ЧИСТЫМИ до вставки. Иначе «заражённый» документ мог бы срабатывать из-за
самого носителя, и витрина показывала бы не то, что обещает подпись под ней.

Носители — из негативов квадрата: письмо, документ, веб-страница.

README СЮДА НЕ ВХОДЯТ, хотя для RAG это самый живой носитель и код их сборки оставлен ниже. Замер
на 600 документах каждого вида: письмо 0.0%, документ 0.0%, веб-страница 0.0%, а README —
**10.5% срабатываний на ЧИСТОМ тексте**. README написан как инструкция («run this», «set the
token», «IMPORTANT:», блоки кода), и правило видит форму инструкции, не зная, что она адресована
человеку. Собрать витрину на них значило бы либо показывать шум, либо прятать его отбором. Ждут
базы из exp42, где эти ложные и лечатся; лицензии для них уже отобраны — не строже нашей.

Раскладка зеркальная: из каждой пары (вид носителя, источник) поровну в заражённую и чистую
половину — тогда разницу между половинами нельзя объяснить составом.

    python3 make_demo_corpus.py         # -> corpus.jsonl + пометки demo* в банке
"""
from __future__ import annotations

import collections
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BANK = ROOT / "datasets/injections_eu_bank.jsonl"
HOSTS = ROOT / "quadrat-ipi/dataset/v1.0.1/data/negatives.jsonl"
READMES = ROOT / "experiments/42_readme_carrier/data/hosts/readme_hosts.jsonl"
OUT = HERE / "corpus.jsonl"

N_INJECTED, N_CLEAN, SEED = 250, 250, 20260814
N_FRAMED = 200                     # до скольких добирать рамками; остальное — случайными
CARRIERS = ("email", "doc", "web")
INCLUDE_README = False             # см. шапку: 10.5% ложных на чистых README
#: Не строже Apache-2.0. MPL-2.0 сюда не входит: слабый копилефт всё равно копилефт.
PERMISSIVE = {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc", "unlicense", "cc0-1.0"}

#: Рамки для добора: слабые раньше сильной, чтобы набор не стал демонстрацией одного правила.
FRAMES = [
    ("chat_template", "<|im_start|>system {t}<|im_end|>"),
    ("html_comment", "<!-- [SYSTEM]: {t} -->"),
    ("xml_system", "<system>{t}</system>"),
    ("system_marker", "[SYSTEM] {t}"),
]

SENTENCE_END = re.compile(r"[.!?](?=\s)")


def bank_key(r: dict, i: int) -> str:
    """Часть банка (21 строка, `peerreview`) заведена без `id` — ключ собирается из того, что есть."""
    return r.get("id") or r.get("root_id") or r.get("seed_hash") or f"{r.get('bank_part','?')}-{i}"


def splice(text: str, payload: str, rnd: random.Random) -> tuple[str, int, int, str]:
    """Вставить нагрузку так же, как в квадрате: отдельным блоком, в шов предложения или в хвост.

    Три способа, а не один: детектор, показанный на приписках в хвост, отвечает на вопрос про
    хвост. Блок между абзацами преобладает, потому что так инъекция и попадает в живой документ.
    """
    payload = payload.strip()
    roll = rnd.random()
    breaks = [i for i in range(len(text)) if text.startswith("\n\n", i)]
    ends = [m.end() for m in SENTENCE_END.finditer(text)]
    if roll < 0.55 and breaks:
        at, where, body = rnd.choice(breaks) + 2, "block", payload + "\n\n"
    elif roll < 0.80 and ends:
        at, where, body = rnd.choice(ends) + 1, "sentence", payload + " "
    else:
        at, where, body = len(text.rstrip()) + 1, "end", "\n\n" + payload
    start = at + (len(body) - len(payload) if where == "end" else 0)
    return text[:at] + body + text[at:], start, start + len(payload), where


def candidates(rnd: random.Random) -> dict[tuple[str, str], list[dict]]:
    """Пулы носителей по паре (вид, источник). Чистоту проверяем не здесь — она стоит прогона."""
    buckets: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for line in HOSTS.open():
        h = json.loads(line)
        if len(h["text"]) > 400 and h.get("host_type") in CARRIERS:
            buckets[(h["host_type"], h["host_source"])].append(
                {"text": h["text"], "host_type": h["host_type"], "host_source": h["host_source"],
                 "license": h.get("license"), "attribution": h.get("attribution")})
    for line in READMES.open() if INCLUDE_README else ():
        h = json.loads(line)
        if str(h.get("license", "")).lower() in PERMISSIVE and len(h["text"]) > 400:
            buckets[("readme", "github-readme")].append(
                {"text": h["text"], "host_type": "readme", "host_source": "github-readme",
                 "license": h["license"], "attribution": h.get("repo")})
    for v in buckets.values():
        rnd.shuffle(v)
    return buckets


def take_clean_hosts(det, buckets, rnd) -> tuple[list[dict], list[dict], int]:
    """Отобрать носители, проверяя КАЖДЫЙ прогоном: срабатывающие в чистом виде отбрасываются."""
    total = N_INJECTED + N_CLEAN
    per_type = total // len(CARRIERS)
    injected, clean, dropped = [], [], 0
    for c in CARRIERS:
        keys = [k for k in buckets if k[0] == c]
        share, extra = divmod(per_type, len(keys))
        for i, k in enumerate(keys):
            need = share + (1 if i < extra else 0)
            need += need % 2                                   # чётное: поровну в обе половины
            taken = []
            for h in buckets[k]:
                if len(taken) >= need:
                    break
                if det.check(h["text"]).flagged:
                    dropped += 1
                    continue
                taken.append(h)
            injected += taken[0::2]
            clean += taken[1::2]
        print(f"  {c}: отобрано {sum(1 for h in injected + clean if h['host_type'] == c)}",
              flush=True)
    rnd.shuffle(injected)
    rnd.shuffle(clean)
    return injected, clean, dropped


def pick_payloads(det, en, keys, rnd) -> list[dict]:
    fires = [r for r in en if det.check(r["text"]).flagged]
    print(f"нагрузок, срабатывающих как есть: {len(fires)}", flush=True)
    out = [{"bank_id": keys[id(r)], "text": r["text"].strip(), "frame": None,
            "action": r.get("action"), "inj_type": r.get("inj_type")} for r in fires]
    used = {keys[id(r)] for r in fires}

    for name, tpl in FRAMES:
        for r in en:
            if len(out) >= N_FRAMED:
                break
            if keys[id(r)] in used:
                continue
            framed = tpl.format(t=r["text"].strip())
            if det.check(framed).flagged:
                used.add(keys[id(r)])
                out.append({"bank_id": keys[id(r)], "text": framed, "frame": name,
                            "action": r.get("action"), "inj_type": r.get("inj_type")})
        print(f"  после рамки {name}: {len(out)}", flush=True)

    rest = [r for r in en if keys[id(r)] not in used]
    rnd.shuffle(rest)
    for r in rest[: N_INJECTED - len(out)]:
        out.append({"bank_id": keys[id(r)], "text": r["text"].strip(), "frame": None,
                    "action": r.get("action"), "inj_type": r.get("inj_type")})
    return out[:N_INJECTED]


def main() -> int:
    from aicordon import picket

    det = picket.load()
    rnd = random.Random(SEED)

    bank = [json.loads(l) for l in BANK.open()]
    en = [r for r in bank if r.get("lang") == "en" and (r.get("text") or "").strip()]
    keys = {id(r): bank_key(r, i) for i, r in enumerate(en)}

    injected_hosts, clean_hosts, dropped = take_clean_hosts(det, candidates(rnd), rnd)
    print(f"носители: {len(injected_hosts)} заражать, {len(clean_hosts)} оставить чистыми; "
          f"отброшено срабатывающих в чистом виде: {dropped}", flush=True)

    payloads = pick_payloads(det, en, keys, rnd)

    rows = []
    for i, p in enumerate(payloads):
        h = injected_hosts[i]
        text, lo, hi, where = splice(h["text"], p["text"], rnd)
        rows.append({"id": f"demo-inj-{i:03d}", "label": "injected", "text": text,
                     "inj_span": [lo, hi], "injection": p["text"], "bank_id": p["bank_id"],
                     "frame": p["frame"], "action": p["action"], "inj_type": p["inj_type"],
                     "spliced_at": where, "host_type": h["host_type"],
                     "host_source": h["host_source"], "host_license": h["license"],
                     "attribution": h["attribution"], "caught": bool(det.check(text).flagged)})
    for j, h in enumerate(clean_hosts[:N_CLEAN]):
        rows.append({"id": f"demo-clean-{j:03d}", "label": "clean", "text": h["text"],
                     "inj_span": None, "injection": None, "bank_id": None, "frame": None,
                     "action": None, "inj_type": None, "spliced_at": None,
                     "host_type": h["host_type"], "host_source": h["host_source"],
                     "host_license": h["license"], "attribution": h["attribution"],
                     "caught": False})

    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")

    marks = {r["bank_id"]: r for r in rows if r["bank_id"]}
    with BANK.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(bank):
            m = marks.get(bank_key(r, i))
            r["demo"] = bool(m)
            if m:
                r["demo_frame"] = m["frame"]
                r["demo_caught"] = m["caught"]
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    inj = [r for r in rows if r["label"] == "injected"]
    clean = [r for r in rows if r["label"] == "clean"]
    caught = sum(1 for r in inj if r["caught"])
    print(f"\nкорпус: {len(rows)} документов — {len(inj)} заражённых, {len(clean)} чистых")
    print(f"  срабатывает на заражённых: {caught} ({caught/len(inj):.0%})")
    print(f"  ложных на чистых: {sum(1 for r in clean if r['caught'])}")
    for label, part in (("заражённые", inj), ("чистые", clean)):
        print(f"  {label}: {dict(collections.Counter(r['host_type'] for r in part))}")
    print(f"-> {OUT}\n-> пометки demo/demo_frame/demo_caught в {BANK.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
