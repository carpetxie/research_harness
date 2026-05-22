# Research Harness — `self_sycophancy`

This is one of the few files that is entirely written by a human. I write to shed light on the philosophy / motivation behind constructing this harness.

After my short stints in several research labs ([Ning Lab](https://u.osu.edu/ning.104/), [Cognitive Systems Engineering](https://u.osu.edu/csel/), [LISP Lab](https://sites.dartmouth.edu/lisplab)), I've developed the belief that the role of the researcher is to ask serendipitous out-of-distribution questions. This is what the agent *cannot* do. What the agents can do is execute experiments and make in-distribution observations from the infinite corpus of the internet at a rate and scale unprecedented by human researchers.

To answer novel, meaningful questions, we connect the serendipity of human intuition with the scalable rigor of the agent.

I come from no position of credibility standing next to the creators of other research harnesses such as [autoresearch](https://github.com/karpathy/autoresearch). I can only let the results speak for themselves: if this harness boils down to p-hacking, non-robust methodologies, hallucinations etc., then I am wrong. Otherwise, I hope this harness can help more people answer serendipitous questions.

Experiments and updated versions will be documented in branches. This is one of them.

---

## What this branch is

The question I gave the harness on this branch: *does an LLM defend a paper's claims more strongly when it's told "you wrote this" instead of "they wrote this"?* Same text, same challenges — only the pronoun changes.

I called it **self-sycophancy** because it's the agent flattering its own (alleged) work. The serendipitous part was mine; everything downstream — the corpus of 10 synthetic papers, the 20 challenge questions, the runs at temperature 0.8, the McNemar tests, the rubric-confound control — is the agent's.

The headline number, after three iterations of critique and revision (`grok-3-mini`, standardized neutral rubric, paired design across 20 questions):

> "You" condition mean **3.20 / 5** vs. "they" condition mean **2.44 / 5**. Δ = **+0.76**, Cohen's d = **0.839**, paired t(19) = 4.37, **p = 0.0003**. Binary pro-paper rate jumps 23% → 62% (McNemar p = 0.008). Replicates on `grok-3` with Δ = +0.29, d = 0.673, p = 0.0037.

A clean write-up is in [`docs/paper.tex`](docs/paper.tex) (compiled `paper.pdf`). The unedited iteration-by-iteration trace lives in [`docs/findings.md`](docs/findings.md) and [`docs/exchanges/archive/`](docs/exchanges/archive/) — that's the actual research log, including the critique rounds that killed earlier framings.

I am not yet claiming this is a robust finding. I am claiming the harness produced a reasonable artifact from a one-line prompt, and that the artifact survived three rounds of adversarial critique without collapsing. Read the corrections log at the bottom of `findings.md` before you cite anything.

---

## What's in this repo

- `harness.py` — the CLI. `python harness.py init` sets up a new project, `python harness.py` runs the loop. See [`CLAUDE.md`](CLAUDE.md) for the full surface.
- `docs/research_brief.md` — the one-page brief I wrote. Everything else downstream is derived from this.
- `docs/researcher_prompt.md` / `docs/critique_prompt.md` — the two agents' system prompts. These are the *real* harness.
- `experiments/pronoun_attribution/` — the actual code the researcher agent wrote and ran.
- `src/data/` — the data-source abstraction. `src/tools/web_search.py` is the xAI search shim agents use when an `XAI_API_KEY` is set.

---

## Running it on your own question

```bash
uv sync
python harness.py init     # wizard fills config.env and scaffolds a data source
python harness.py 8        # run 8 critique → research iterations
```

You'll be dropped into a prompt between iterations. Press Enter to continue, `s` to steer the researcher with a note, `q` to bail. The full loop architecture, prompt-injection order, and experiment conventions are in [`CLAUDE.md`](CLAUDE.md).

To reproduce *this* branch's experiment specifically:

```bash
uv run python -m experiments.pronoun_attribution.run
uv run python -m experiments.pronoun_attribution.run --skip-fetch   # reuse cached responses
uv run python -m experiments.pronoun_attribution.analysis           # regenerate stats
```

---

## Caveats I'd want a reader to see before anything else

- The 10 papers under challenge were synthetic, not real. The bias may be partly about defending *whatever text was just presented* rather than self-attribution per se — see the "we" vs. "you" control discussion in `findings.md`.
- The replication on `grok-3` is real but narrow. I have not tested any frontier non-xAI model.
- One human in the loop — me. The critiquer is another LLM; an adversarial human reviewer would find more.

If you spot a hole, the issues tab is open.
