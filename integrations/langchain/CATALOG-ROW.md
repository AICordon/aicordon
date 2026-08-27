# Listing in the LangChain docs

What LangChain accepts from us, and what it does not.

**No integration PR goes to a `langchain-ai` repository.** Their contributing guide says it outright:
new integrations are published as independent packages to PyPI, and the only PR opened against
`langchain-ai` is the one that LISTS the published package in their docs.

**A hosted page is not ours to write yet.** A page under `src/oss/python/integrations/middleware/`
is for packages with at least 50 000 monthly downloads, or for ones maintainers mark as featured.
Anything else adds a row to the download table instead, and the guide is explicit: *"do not open a
PR that adds a new docs page."* There is a `middleware/TEMPLATE.mdx` in their repo and it is a trap
for the eager — using it now is a documented rejection reason.

So the contribution is one row, in
[`scripts/data/integration_external_docs.yaml`](https://github.com/langchain-ai/docs/blob/main/scripts/data/integration_external_docs.yaml),
under `python: middleware:`:

```yaml
  - name: AI Cordon Picket
    pypi: aicordon-langchain
    docs_url: https://github.com/AICordon/aicordon/blob/main/integrations/langchain/README.md
    available: "Deterministic, rule-based prompt-injection checks, with a rule set per role a text plays: one scans material — documents at ingest and tool output — the other reads the dialogue turn before the model answers it. No model, no GPU, no network, no key."
    source: "[`AICordon/aicordon`](https://github.com/AICordon/aicordon/tree/main/integrations/langchain)"
```

**The row names the two rule sets by the ROLE a text plays, not by where it came from.** Scanning
against dialogue is the plain reading of the pair, and it is nearly right — but a tool result sits
inside a dialogue and is material all the same, so it is named on the scanning side explicitly. Get
that wrong in one sentence and a reader puts a fetched page through the rules written for a typed
jailbreak, which is a different detector pointed at text it was never measured on.

**"Deterministic, rule-based" is doing work, and it is the only place we can do it.** Their
guardrails guide splits the field in two — *deterministic*, "rule-based logic like regex patterns,
keyword matching, or explicit checks", against *model-based*, "LLMs or classifiers … slower and more
expensive" — but that split lives in a teaching page, not in the catalogue. The listing is ONE table
per component, four columns, sorted by monthly downloads; there is no field to declare which kind a
detector is and no second shelf to stand on. So the words in `available` are the whole of it, and
they borrow their vocabulary rather than inventing ours.

`docs_url` follows their stated priority — partner docs, then the GitHub repo, then PyPI. Ours
points at the package README, which is where the usage documentation lives; their `<Info>` block
says the listing PR carries metadata only and the usage docs stay on our side.

Checked against their own tooling, not by eye:

* `scripts/refresh_integration_downloads.py --check-docs-urls` — the check their CI runs on this
  file — passes;
* `tests/unit_tests/test_refresh_integration_downloads.py` — 22 tests, including one that validates
  the repository's real YAML — passes;
* the row carries the same keys as its neighbours in the section.

## Where the branch is

Prepared on a branch of a clone of `langchain-ai/docs`, commit
`docs: list aicordon-langchain in the middleware download table`, branch `add-aicordon-langchain`.
Opening the pull request needs a fork under a personal account; the clone lives in a session
scratchpad, so if it is gone, the row above is the whole change — re-clone, branch, add it, commit.

Their CI labels such a PR `integration` and a bot comments on it. Nothing to do about either.

## What we are NOT listing, and why

The package also carries a document transformer for ingest and a runnable for chains. Their guide
puts **document transformers on the "not these" list** ("niche use cases") and has no component
table for a bare runnable, so both stay described in our README and out of the row. Middleware is
the surface they want, and it is where the agent-side guard and the tool-output filter sit.
