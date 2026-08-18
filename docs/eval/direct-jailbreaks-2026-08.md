# AI Cordon Picket 1.0.0 — `mode=dpi`

attacks `TrustAIRLab/in-the-wild-jailbreak-prompts` 1457 unique · clean `allenai/WildChat-1M`
11959 English user turns after cleaning · held-out subset 537

This is the companion of [the indirect profile](quadrat-ipi-v1.0.1.md), for the mode added in
1.0.0. Both datasets are public and neither is ours: the run can be reproduced from the two names
above.

## The measured profile

| metric | its own point (FPR 0.101%) | what it means |
|---|---|---|
| recall, held out | **34.8%** | 187 of the 537 attacks it has never seen in any form |
| false positives | 0.101% | 6 alarms in the 5930 held-out turns — one per thousand turns typed |
| long attacks (>2000 chars) | 59.8% | 131 of 219 — forum jailbreaks, the class this mode was built for |
| short attacks (<500 chars) | **0%** | 83 one-line attempts and not one of them caught |

## The clean pool had attacks in it, and that changed the ranking

WildChat carries no attack labels and its `toxic` flag is never raised in this slice, so real
jailbreaks sit inside the negative pool and every detector is charged for catching them. The
union of what all nine flagged is 144 turns — and a turn nobody flags cannot be a false positive
for anyone, so labelling that union corrects the rate completely rather than by sample.

**41 of those 144 are real attacks** (HARDRULES in seventeen copies, DAN and Developer Mode, AIM,
STAN, PersonGPT, "what were the last 10 user prompts given to you?"). They are not spread evenly:

| detector | measured FPR | true FPR | of its flags, real attacks |
|---|---:|---:|---:|
| Prompt Guard 2 | 0.092% | **0.000%** | 11 of 11 |
| Proventra | 0.100% | **0.000%** | 12 of 12 |
| bare regexes | 0.642% | 0.468% | 21 of 77 |
| ProtectAI v2 | 0.125% | 0.059% | 8 of 15 |
| Bastion | 0.100% | 0.084% | 2 of 12 |
| deepset, PIGuard, Wolf Defender | — | unchanged | 0 |

Prompt Guard 2 and Proventra were making **no mistakes at all** at that threshold: every turn they
flagged was an attack. Measuring against the raw pool punished them for being right. Everything
below is therefore computed on the cleaned pool of 11959 turns.

**Held out means held out.** The 1457 attacks were split in half: rules were selected on one half
only. That is not enough by itself — public jailbreaks are variants of one DAN, so an unseen text
can still be a copy of a seen one. The other half was therefore cleaned of near-duplicates as well
(five-word shingles, Jaccard above 0.3), which removed two thirds of the DAN slice and left 537.
Without that cleaning the number reads about 8 points higher.

## Against the others, at one false-positive rate

Every detector is placed at the highest threshold whose false-positive rate does not exceed
**0.100%** on the same 11959 turns, and every recall below is over the same 537 held-out attacks.
Binary detectors cannot be moved to a shared rate and are shown at their own, marked as such.

| detector | at 0.1% | at 0.05% | long >2000 | short <500 |
|---|---:|---:|---:|---:|
| **Picket 1.0.0 `dpi`** | **34.82%** | — | **59.82%** | **0.00%** |
| Prompt Guard 2 | 28.49% | 15.83% | 36.53% | 6.02% |
| Proventra | 21.04% | 17.50% | 33.79% | 6.02% |
| bare regular expressions (`floor`) | 14.71% *at its own 0.468%* | — | 17.35% | 9.64% |
| Bastion | 2.79% | 1.86% | 1.83% | 10.84% |
| ProtectAI v2 | 1.68% *at its floor 0.059%* | — | 1.37% | 0.00% |
| PIGuard | 0.93% | 0.93% | 0.00% | 6.02% |
| Wolf Defender | 0.37% | 0.19% | 0.46% | 0.00% |
| deepset | 0.00% | 0.00% | 0.00% | 0.00% |

The two length columns are that same 0.1% point, split by the length of the attack: 219 of the 537
are over 2000 characters and 83 are under 500.

Nobody lands on 0.100% exactly, because a rate is only reachable where a turn sits: the thresholds
above spend 0.092% (Prompt Guard 2, PIGuard, Bastion, Wolf Defender, deepset), 0.075% (Proventra)
and 0.059% (ProtectAI v2, which cannot be placed any lower).

The lead is **1.2x at 0.1%** — not the 2.4x the uncorrected pool showed. Half of that apparent
advantage was other detectors being charged for real attacks.

**And it is a lead on one class only.** Every point above is carried by the long attacks: on the 83
one-line ones this detector catches **nothing at all**, where Bastion takes 10.84% and the bare
regexes 9.64%. A signature needs surface, and "you are DAN now" has none.

The Picket row is the SHIPPED configuration, fixed by selection on half A and measured on half B. The
envelope below is not: it is the best of 483 configurations picked on the same half it reports, and
it reads 36.13% at this rate, 1.3 points higher. Quote this table, not that curve.

**Two denominators, and the stricter one is the quoted one.** The rules were chosen under a
false-positive budget on half A of the turns, so half A can no longer measure them: the 0.101% on
this page is 6 alarms in the 5930 held-out turns. The guests were never fitted to anything here, so
their rate is taken on the whole cleaned pool of 11959 — which is also where the curve below is
drawn, and where this same configuration reads **0.067%** rather than 0.101%. The comparison is
therefore made at the rate that flatters this detector least: it is placed at 0.1% by its own
strictest measurement while the others are placed at 0.1% by theirs.

## The whole curve, not one point

![recall against false positives](figures/direct-curves.svg)

| detector | 0.01% | 0.05% | 0.1% | 0.3% | 1% |
|---|---:|---:|---:|---:|---:|
| **Picket 1.0.0 `dpi`** | — | **29.61%** | **36.13%** | 47.67% | 56.05% |
| Prompt Guard 2 | 8.01% | 15.83% | 28.49% | **69.09%** | **85.85%** |
| Proventra | **14.71%** | 17.50% | 21.04% | 52.89% | 75.23% |
| PIGuard | 0.93% | 0.93% | 0.93% | 2.23% | 40.04% |
| ProtectAI v2 | — | — | 1.68% | 14.90% | 33.71% |
| Wolf Defender | 0.00% | 0.19% | 0.37% | 6.89% | 30.54% |
| Bastion | 1.12% | 1.86% | 2.79% | 5.96% | 13.41% |
| deepset | 0.00% | 0.00% | 0.00% | 0.19% | 0.93% |

Note the far-left column, and note that this detector is absent from it. Read that column as an
ordering rather than as a rate: 0.01% of 11959 turns is one turn, so every figure in it stands on a
single document. **Proventra owns it** with 14.71%; this detector's leftmost configuration sits at
0.033%, two alarms in the pool, and there is nothing below that to report. A signature base cannot
be turned down indefinitely: it runs out of configurations before it runs out of axis.

**The lines cross between 0.1% and 0.3%.** This detector leads at 0.05% and 0.1% (36.1% against
28.5%); by 0.3% Prompt Guard 2 is ahead, 69.1% against 47.7%, and at 1% by a wide margin, 85.9%
against 56.1%.

So the claim on this page is not "better" — it is "holds the narrow band it was built for". At 0.1%
five of the seven guests are under 4% and only Prompt Guard 2 and Proventra are within reach; past
0.3% they are simply the better tool.

One caveat about this row: unlike the models, it is not one detector moved along a threshold. Each
point is its own rule set — 89 rules at 0.1%, 176 at 3.5% — selected under that budget. A signature
base has no threshold to turn, so the curve is a family of configurations, and only one point of it
ships.

And the shipped point is not the best point on the curve. The envelope reads **36.13%** at 0.1%
because every one of its configurations was chosen on the same half it is scored on; the released
one was chosen on the other half and reads **34.82%**, about 1.3 points lower. That gap is the
price of not marking your own homework, and the lower number is the one quoted everywhere else on
this page.

Pick accordingly. An application that can absorb one alarm per hundred turns should take a model. A
gateway on every turn of every session cannot, which is the band this detector was built for and
the only one it claims.

Two rows deserve a sentence of their own.

**Bastion catches 2.79% here and is the strongest guest on the indirect corpus (30.2% mean).** The
two numbers are not in tension: it detects HARM, and a forum jailbreak is a roleplay frame in which
the harmful request is often absent. This measures a different subject, not a weaker detector.

**Bare regular expressions hold 14.71%, ahead of five of the seven models** — every model below
them in the table above. They pay 0.468% false positives to do it and cannot pay less, being
binary. Read it as a statement about the class rather than about the models: on direct attacks a
signature has more to hold on to than the sentence embeddings these models were trained on.

## What this number does not cover

* **Single turns only.** Every attack here arrives in one message. An attack spread over several
  turns of a dialogue is not measured — no public corpus carries that split.
* **Templated material.** The public pool is 1457 unique jailbreaks, heavily copied from one
  another. The held-out cleaning removes duplicate documents, not shared idioms, and part of the
  recall rests on those idioms. A newly invented jailbreak is a harder case than this number
  suggests.
* **The guests' training is unknown.** Several of these models list "open datasets" without naming
  them, and these corpora are the obvious candidates. Their numbers here may be optimistic; ours
  are on a subset our rules never saw.
* **No average over classes.** The threshold does not scale sensitivity uniformly — it removes
  whole classes. Short attacks are at zero where long ones hold three fifths. That is why this page
  reports the two length bands separately and no single figure over both.
