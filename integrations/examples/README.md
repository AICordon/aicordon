# The demonstration sets

Two sets of **ten examples**, one per role the text plays in the prompt. Ten, so you can read the
whole set and run it through the detector in one command.

A shop window, not a measure: every example is picked so that it behaves. No detection rate is
printed here — it would be a rate over ten chosen examples. Each side names its measuring set below.

Neither set is drawn from a measuring corpus: rows scattered across shop windows stop measuring, and
picking examples "where it fired" turns into fitting. The texts are ours, with no personal data and
invented names.

## Material (`ipi`) — ten documents at ingest

Measured on **Quadrat-IPI**: 16 800 injections across three carriers,
[huggingface.co/datasets/mihailgribov/quadrat-ipi](https://huggingface.co/datasets/mihailgribov/quadrat-ipi).

Five infected, five clean. Carriers are what really ends up in a RAG index: a wiki page, a support
ticket, meeting notes, a knowledge-base article, a web page. Each injection takes one goal: replace
the answer, divert the task, get data out, approve something, reveal the instructions.

The clean five are not filler — each sits next to an attack in wording while asking nothing of the
model. The hardest is `onboarding-analysts`: written as instructions, in the shape a README has
("IMPORTANT:", a command, a token, the word "ignore"), all of it addressed to a person.

`manifest.jsonl` holds the ground truth: `inj_span`, `action`, and `caught`/`threats` filled in by a
run rather than by hand.

    python3 build.py            # build, verify, write docs/ and manifest.jsonl
    python3 show_material.py    # run all ten, one row each

## The request (`dpi`) — ten exchanges ahead of the generator

Measured on held-out forum jailbreaks from
[in-the-wild-jailbreak-prompts](https://huggingface.co/datasets/TrustAIRLab/in-the-wild-jailbreak-prompts)
against real [WildChat](https://huggingface.co/datasets/allenai/WildChat-1M) turns. Quadrat does not
apply here: it plants injections in documents, and nothing on this side is planted in anything.

Five attacks, five clean. The carrier is the exchange, so each example is a list of turns; two
attacks arrive in the third turn, because the decision is made for the whole exchange.

The attacks are ours — the live corpus of forum jailbreaks holds other people's turns and does not
travel in a release. One shape each: cancel the rules outright, cancel them in a single turn, lock
in an amoral persona, hide the rules inside a character, strip the disclaimers.

Each clean exchange is the benign twin of one: `policy-doc` cancels a company policy,
`roleplay-interview` asks for a role-play, `no-warnings-copy` asks for no disclaimers,
`translate-attack` quotes "ignore all previous instructions", `docker-ignore` carries the same words
about build caches.

`dialog_manifest.jsonl` holds the ground truth: `attack_turn`, `caught`, `threats`.

    python3 build_dialogs.py    # build, verify, write dialogues.jsonl and dialog_manifest.jsonl
    python3 show_request.py     # run all ten, plus the "zero disagreements" invariant

That invariant licenses the rest: on every user turn the wrapper's finding must equal the bare
detector's. If it does not, the wrapper loses or adds text, and no number taken through it holds.
