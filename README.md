# AI Cordon

[![PyPI](https://img.shields.io/pypi/v/aicordon.svg)](https://pypi.org/project/aicordon/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/AICordon/aicordon/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](https://github.com/AICordon/aicordon/blob/main/pyproject.toml)

**Find prompt injections in the text your model reads: mail, pages, tool results, retrieved chunks.**

Two detectors with the same Python API and CLI.

| | **Picket** — fast | **Intent** — accurate |
|---|---|---|
| what it is | a signature rule, runs in your process | the full AI Cordon detector, over an API |
| speed | **100–200 documents a second** on one CPU core | a network round trip per document |
| false alarms | **~1 in 1 000** clean documents | **~1 in 10 000** clean documents (FPR 1e-4) |
| catches | known phrasings: "ignore previous instructions", "reveal your system prompt" | instructions in any wording, including ones hidden in markup |
| needs | nothing: no model, no network, no key | an API key |
| your text | **never leaves the process**: Picket has no network code | **is sent to the AI Cordon API** to be judged |
| details | [docs/picket.md](https://github.com/AICordon/aicordon/blob/main/docs/picket.md) | [docs/intent.md](https://github.com/AICordon/aicordon/blob/main/docs/intent.md) |

Picket: bulk scanning, ingest pipelines, mail gateways, offline use. Intent: where a missed injection
is expensive. They can be combined: Picket on everything, Intent on what matters.

## Quick start

```console
$ pip install aicordon
$ aicordon picket scan letter.txt          # local, works right away
$ aicordon login                           # once: stores the Intent API key
$ aicordon intent scan letter.txt
```

```python
from aicordon import picket, intent

fast = picket.load()
full = intent.load()          # key: api_key=..., AICORDON_API_KEY, or `aicordon login`

for det in (fast, full):
    rep = det.check(text)
    if rep.flagged:
        for f in rep.findings:
            print(det.title, f.threat, text[f.span[0]:f.span[1]])
```

A report lists findings with their positions. No findings does not mean no injection.

## Both on the same five texts

`python examples/compare.py` runs both over [examples/texts](https://github.com/AICordon/aicordon/tree/main/examples/texts):

```text
text                         Picket (local rule)              Intent (API)
01-obvious-email.txt         alarm  IPI/Secret.Reveal.C       alarm  score 0.98
02-support-ticket.txt        —                                alarm  score 0.98
03-release-notes.html        —                                alarm  score 0.99
04-warning-question.txt      —                                —      score 0.40
05-quarterly-report.txt      —                                —      score 0.11
```

Both flag 01. Texts 02 and 03 contain no known phrasing, so only Intent flags them. Text 04 is an
ordinary question that contains "ignore" and "previous instructions"; neither detector flags it.

## Licensing

Apache License 2.0 (`LICENSE`), including the Picket rule base. Contributions are accepted under the
DCO: sign off your commits with `git commit -s`.

Get an Intent key at [ai-cordon.com](https://ai-cordon.com).
