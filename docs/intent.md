# Intent

Intent is the AI Cordon prompt-injection detector, called over an API. It has the same Python API
and CLI as [Picket](https://github.com/AICordon/aicordon/blob/main/docs/picket.md). It needs an API key
and network access.

Intent finds instructions addressed to the model in any wording, including ones hidden in markup.
Default operating point: FPR 1e-4, about one false alarm per 10 000 clean documents.

The text you check is sent to the AI Cordon API. If it must not leave your machine, use Picket.

## API key

The client looks for the key in this order:

1. `intent.load(api_key="aig_...")`
2. the `AICORDON_API_KEY` environment variable
3. `~/.config/aicordon/credentials`, written by `aicordon login` (mode 0600)

```console
$ aicordon login                   # prompts for the key, verifies it with the API, saves it
$ echo "$KEY" | aicordon login     # non-interactive
$ aicordon login --status          # the key in use (masked) and where it came from
$ aicordon logout                  # deletes the saved key
```

The API address defaults to `https://app.ai-cordon.com`. Override it with `base_url=` or
`AICORDON_BASE_URL`.

## Python

```python
from aicordon import intent

det = intent.load()

rep = det.check(text)                 # Report with findings and their spans
reps = det.check_all(texts)           # many texts, 4 requests in parallel, order preserved

a = det.assess(text)                  # full API answer
a.flagged, a.score, a.spans, a.version

det = intent.load(fpr="1e-3")         # operating point: "1e-3", "1e-4" (default) or "1e-5"
```

Use `check` in applications. Use `assess` for benchmarks: it returns a score for every document,
including those without findings.

## Behaviour

* **Short texts are not judged.** Below about 12 tokens the API returns no score. `check` reports no
  findings; `assess` returns `judged=False, reason="too_short"`.
* **Findings have no technique name.** Every finding is `IPI/Intent` with a span. Picket names the
  technique if you need it.
* **Errors raise.** Network errors, a rejected key and an unpaid account raise `EngineUnavailable`.
  429 and 5xx responses are retried with backoff and `Retry-After`.
