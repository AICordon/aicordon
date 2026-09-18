# Intent — the accurate detector

The API half of [`aicordon`](https://github.com/AICordon/aicordon): the full AI Cordon detector,
called over the network. Same interface as [Picket](https://github.com/AICordon/aicordon/blob/main/docs/picket.md);
what differs is that it needs a key and a network.

It reads the text the way a model does and finds instructions addressed to that model — whatever
their wording, in any language it was trained on, hidden in markup or phrased as a polite note. The
default operating point is **FPR 1e-4**: about one false alarm in ten thousand clean documents.

## The key

Looked up in the order the common API clients use:

1. `intent.load(api_key="aig_...")`
2. the `AICORDON_API_KEY` environment variable
3. the file written by `aicordon login` — `~/.config/aicordon/credentials`, readable by you only

```console
$ aicordon login                   # prompts, input hidden; checks the key with the API, then saves it
$ echo "$KEY" | aicordon login     # the same from a script or CI
$ aicordon login --status          # which key is in use, and where it came from
$ aicordon logout
```

The key is never printed whole. The address is `https://app.ai-cordon.com`; `base_url=` or
`AICORDON_BASE_URL` points the client elsewhere.

## Python

```python
from aicordon import intent

det = intent.load()

rep = det.check(text)                 # a Report: findings with spans, as Picket returns it
reps = det.check_all(texts)           # many texts; requests go out 4 at a time, order kept

a = det.assess(text)                  # the service's full answer
a.flagged, a.score, a.spans, a.version

det = intent.load(fpr="1e-3")         # another operating point: 1e-3, 1e-4 (default) or 1e-5
```

`check` is for applications. `assess` is for measurement: it returns the score of every document,
including those with no finding, which a benchmark rule needs.

## What it will not do

* **Judge a very short text.** Below about a dozen tokens the detector has nothing to measure. Such a
  text gets no finding, and `assess` says `judged=False, reason="too_short"`. That is not a clean
  verdict.
* **Name the technique.** A finding says where the instruction is (`IPI/Intent` plus its span), not
  what kind it is. Picket's findings name techniques; run both if you need that.
* **Fail quietly.** A network error, a rejected key or an unpaid account raises
  `EngineUnavailable`. It never turns into an empty report. Busy answers (429, 5xx) are retried with
  backoff first.

The text you check is sent to the AI Cordon API. If it must not leave your machine, use Picket.
