# Critique — Iteration 1

STATUS: CONTINUE

## Overall Assessment

There is no research here yet. `docs/findings.md` is the unmodified skeleton template — every section is a bracketed placeholder. `config.env` is also unfilled (TOPIC = "your research topic", PAPER_TITLE = "Your Paper Title", DATA_SOURCE_NAME = "Your Data Source", PUBLICATION_VENUE = "your research blog or journal"), `experiments/` is empty (only a `.gitkeep`), `data/` is empty, and `src/data/` contains only the abstract `base.py` with no concrete `DataSource` subclass. There is nothing to evaluate on rigor, novelty, or publishability — this is a pre-iteration-zero state.

## Data Sufficiency Audit

**Dataset analyzed: zero observations. Dataset available: unknown — the data source has not been chosen, named, or implemented.**

Concretely:
- No `DataSource` subclass exists in `src/data/` beyond the abstract `base.py`. There is no `kalshi.py`, `fred.py`, `bloomberg.py`, etc.
- No cached data exists in `data/`.
- No experiment scripts exist in `experiments/` to fetch or analyze anything.
- `DATA_SOURCE_NAME` in `config.env` is the literal placeholder string "Your Data Source", so I cannot even audit which API endpoints, series, or time windows ought to be exploited.

This is not "underpowered" — it is unconstructed. Every subsequent claim about data sufficiency is moot until (a) the topic and source are committed in `config.env`, and (b) at least one `DataSource` subclass + experiment pipeline lands data on disk.

## Scores

| Criterion | Score | Delta | Comment |
|-----------|-------|-------|---------|
| Data Sufficiency | 0/10 | n/a | No data fetched, no source implemented, no source even chosen. |
| Novelty | 0/10 | n/a | No claims exist. Cannot assess contribution. |
| Methodological Rigor | 0/10 | n/a | No methods exist. The Methodology section is `[Describe the analytical approach...]`. |
| Practical Significance | 0/10 | n/a | No findings. |
| Publication Readiness | 0/10 | n/a | A blank template cannot be submitted to any venue. |

## Strength of Claim Assessment

There are no claims. Every section of `findings.md` is a square-bracketed instruction to a future author (e.g. "Frame the problem. Why does this matter?"). There is nothing to call conclusive, suggestive, or speculative.

## Novelty Assessment

Indeterminate. Without a topic, research question, or data source, no novelty argument can be made. The first iteration must commit to a research question concrete enough that "what's new about this?" has a defensible answer.

## Robustness Assessment

No code in `experiments/` or `src/data/` (beyond `base.py`) to review. `base.py` defines a reasonable `DataSource` ABC with `fetch`, `load`, `cache_path`, and `is_cached`, which is fine — but no subclass uses it yet, so there is no implementation to audit for correctness, caching behavior, error handling, or determinism.

## The One Big Thing

**Bootstrap the project.** Before any further critique cycles can be productive, the researcher must, in this exact order:

1. **Fill in `config.env`** with a real TOPIC, PAPER_TITLE, RESEARCH_QUESTION, DATA_SOURCE_NAME, and PUBLICATION_VENUE. Without these, the research-loop prompts substitute placeholder strings and every downstream agent (researcher and critiquer) is operating on `{{TOPIC}}` = "your research topic".
2. **Implement one concrete `DataSource` subclass** in `src/data/<source>.py` that actually fetches and caches data.
3. **Land at least one experiment** in `experiments/<name>/run.py` that pulls a non-trivial sample (target ≥ a few hundred observations across multiple series, not a single series of 10 points) and writes it to `data/<name>/`.
4. **Replace the skeleton in `docs/findings.md` with real prose**: a stated research question, a described sample with N and date range, a named methodology, and at least one numerical result with a confidence interval or p-value.

Until step 1 happens, nothing else I could say is actionable.

## Other Issues

### Must Fix (blocks publication)

1. `config.env` is entirely placeholder text. Fill it in.
2. `docs/findings.md` is the unmodified skeleton. It must contain real content — abstract, data description, methodology, results, discussion — by the end of iteration 2 at the latest.
3. No `DataSource` implementation exists. At least one concrete subclass must be written and tested.
4. No experiment exists. At least one runnable `experiments/<name>/run.py` must exist and produce cached output in `data/<name>/`.
5. No tests. The CLAUDE.md asks for `experiments/<name>/tests/test_unit.py` with synthetic data. None exist.

### Should Fix (strengthens paper)

1. Once the topic is chosen, write a one-paragraph **literature positioning** in the Introduction so novelty can be argued against named prior work, not in the abstract.
2. Decide upfront whether the paper will be **descriptive** (characterizing a phenomenon) or **inferential / predictive** (testing a hypothesis or forecasting). This decision drives every methodological choice that follows; deferring it produces muddled papers.
3. Pre-commit a **target sample size and time window** in iteration 2 (e.g. "≥ 500 daily observations across ≥ 20 series, 2015–2025") so future critique cycles have a concrete sufficiency yardstick.

### New Experiments / Code to Write

These are unblocked the moment `config.env` is filled in. Specific suggestions are necessarily generic until then:

- **`src/data/<source>.py`**: implement `fetch(series)`, `cache_path(series)`, and ensure idempotent caching (re-running with `--skip-fetch` must not re-hit the API).
- **`experiments/exploratory/run.py`**: a first-pass exploratory experiment that fetches a broad slice of data, prints summary statistics (N, date range, missingness, basic moments), and saves a cached parquet/JSON. This is the dataset audit that future iterations will lean on.
- **`experiments/exploratory/tests/test_unit.py`**: synthetic-data unit test with no network calls, per CLAUDE.md.
- **`docs/findings.md` Section 2 (Data)**: replace the placeholder with concrete N, date range, source URL, access method, and any inclusion/exclusion criteria, populated automatically (or by hand) from the exploratory experiment's output.

### Genuinely Unfixable Limitations

None to declare. Every weakness here is fixable by writing code and filling in `config.env`. There is no "inherent limitation" defense available at iteration 1 of a project with no committed scope.

## Reward-Hacking Watch (for future iterations)

Flagging now so the researcher and I both know the trap: in later iterations, the failure mode I will be watching for is **cosmetic compliance** — e.g., responding to a "fetch more data" critique by fetching one additional series and declaring the dataset expanded, or responding to a "add robustness checks" critique by adding a single placebo regression and calling robustness done. The bar for "addressed" is that the underlying weakness no longer holds, not that a code change was made in its general direction.

## Verdict

**REJECT** (with the strong expectation that iteration 2 will be a substantively different submission). This is not a rejection of a research idea — there is no idea on the page yet. It is a rejection of the current artifact as a paper. Iteration 2 should produce, at minimum: a filled `config.env`, one concrete `DataSource`, one experiment with cached output, and a `findings.md` that contains real prose and at least one quantitative result.
