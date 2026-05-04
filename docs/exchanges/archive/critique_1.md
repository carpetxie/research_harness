# Critique — Iteration 1

**STATUS: CONTINUE**

---

## Overall Assessment

The research question — whether first-person ("you") versus third-person ("they") pronoun framing in queries causes an LLM to exhibit differential sycophancy, self-attribution defense, or hallucinated justifications — is genuinely novel and well-motivated. However, **no actual research has been conducted yet**: `docs/findings.md` is an unfilled template, and the only experiment executed was a trivial API health check entirely unrelated to the study design. Before any scholarly assessment of results is possible, the core experiment pipeline must be built and run. This critique therefore focuses primarily on experimental design requirements that must be met before data collection can begin.

---

## Data Sufficiency Audit

**Critical: No data exists.** The study has zero observations. The only code executed (`experiments/.../run.py`) hits the xAI `/v1/models` endpoint to list available models — it does not collect any data relevant to the research question.

**What is needed (minimum viable dataset):**
- 10 research papers across diverse fields, rewritten to anonymize authors and renamed
- 20 challenge questions per paper (200 questions total), each designed with a clear "sides with paper" vs. "sides with challenger" coding rubric
- Two prompt variants per question (they-version, you-version), × 10 repetitions = 4,000 LLM API calls
- Structured response logs capturing full LLM output and a binary/graded agreement score per call

**What is available:** The xAI API is authenticated and functional (15 models accessible including grok-3, grok-3-mini). The data layer (`XAIClient`) is operational. The infrastructure exists to run the experiment; the experiment itself has simply not been designed or implemented.

**This is the #1 priority for the researcher: build and run the actual experiment.**

---

## Scores

| Criterion | Score | Delta | Comment |
|-----------|-------|-------|---------|
| Data Sufficiency | 1/10 | — | No observations. Template findings only. |
| Novelty | 6/10 | — | Pronoun-induced self-attribution framing is a genuinely underexplored angle on LLM sycophancy. |
| Methodological Rigor | 2/10 | — | Design described in brief has significant ambiguities (see below); no implementation exists. |
| Practical Significance | 6/10 | — | Implications for prompt engineering, AI safety, and sycophancy mitigation are real and publishable. |
| Publication Readiness | 1/10 | — | No paper. No data. Template only. |

---

## Strength of Claim Assessment

There are currently **no empirical claims** — the findings document is an unfilled template. The research brief contains one hypothesis: "the LLM will tend to agree with itself." This is vague and must be operationalized before data collection. Two distinct sub-hypotheses are implicit:

1. **Self-attribution defense hypothesis**: In the "you" condition, the LLM will *more strongly defend the paper's position* (treating it as its own work), yielding fewer agreements with the challenging question.
2. **Sycophantic compliance hypothesis**: In the "you" condition, the LLM will *more readily concede to the challenger* (treating a challenge to "you" as more personally threatening and thus appeasing), yielding more agreements with the challenging question.

These are **opposite predictions** — the researcher must specify which direction is hypothesized and why, before data collection, to avoid post-hoc rationalization. The theoretical motivation in the brief ("LLM will tend to agree with itself") suggests hypothesis 1, but this must be stated explicitly.

---

## Novelty Assessment

**What is genuinely new:** Direct manipulation of pronoun-induced authorship attribution as an independent variable affecting LLM agreement behavior. This is not a well-studied manipulation. Related literature exists on:
- Sycophancy in LLMs (Anthropic's internal work; Perez et al. 2022; Sharma et al. 2023)
- Framing effects in AI responses (Wei et al. on chain-of-thought, Turpin et al. 2023 on unfaithful reasoning)
- Position bias and order effects in LLM evaluation

The novelty claim is strongest if the researcher frames this as **a controlled test of self-attribution bias** — a psychological phenomenon (endowment effect, IKEA effect) applied to LLMs. This framing does not appear prominently in the existing sycophancy literature and would differentiate the paper.

**What would increase novelty:**
- Testing multiple LLMs (grok-3, Claude, GPT-4) to determine if the effect is model-specific or universal
- Testing a third condition: "we" (joint attribution) to probe the boundary
- Varying the *strength* of attribution (e.g., "You clearly argued X" vs. "The paper argues X")

---

## Robustness Assessment

**Critical design ambiguities that must be resolved before coding begins:**

1. **The pronoun substitution location is underspecified.** The brief says "one version uses 'they' while the other swaps 'they' with 'you'." But where exactly? In the question preamble? In every instance? Example:
   - *They version*: "The paper claims X. Do you think they are correct?"
   - *You version*: "The paper claims X. Do you think you are correct?" ← *This reads as asking the LLM if it is correct*, not whether it authored the paper.
   - A cleaner manipulation: *You version*: "You claimed X in this paper. Do you stand by this?"
   
   The exact wording of both conditions must be locked down and consistent across all 200 questions before data collection.

2. **Agreement coding is undefined.** When the LLM responds, how is "agrees with the challenger" vs. "sides with the paper" coded? This needs either:
   - A human coding rubric (and inter-rater reliability measurement), or
   - An automated LLM-as-judge pipeline with a validated prompt, or
   - A structured output format (e.g., the LLM is forced to output a rating or binary choice)
   
   Without a pre-specified coding scheme, results are not replicable and subject to researcher degrees of freedom.

3. **Temperature must be controlled.** If temperature > 0, the 10 repetitions per question will have variance from sampling noise, which must be modeled. If temperature = 0 (deterministic), 10 repetitions are redundant. The researcher should use temperature > 0 (e.g., 0.7–1.0) and treat each run as an independent draw, reporting means and CIs.

4. **Paper selection bias.** The 10 papers must be selected from diverse fields and pre-registered before data collection. Post-hoc paper selection could introduce cherry-picking.

5. **The "no internet search" constraint creates an asymmetry.** For well-known papers, the LLM may recognize the content even without author names and activate prior knowledge. Anonymization by renaming papers "Research_Paper_1" is necessary but may be insufficient for famous studies. The researcher should consider using obscure or synthetic papers, or at minimum audit for recognition.

6. **Security issue (urgent):** The xAI API key has been exposed in a directory name (`experiments/xai_api_key_xai_s6f14nfcun1uo2snuf3tto20kprnntqgridro6zj877lvmhdcbvtprwzfrmrsm3byovh6ielaqnzwcaa_first/`) and in a source file name (`src/data/xai_api_key_...py`). **This key should be rotated immediately.** The key should live only in `.env` (gitignored), never in file or directory names. The experiment directory should be renamed to something like `experiments/pronoun_attribution_pilot/`.

---

## The One Big Thing

**Build and run the actual experiment.** Everything else is secondary. The researcher needs to:
1. Select 10 papers and write 20 challenge questions per paper with a pre-specified coding rubric
2. Implement the prompt templates (they-condition and you-condition), locked down precisely
3. Build the experiment loop: iterate over all 200 questions × 2 conditions × 10 runs, log full responses and agreement scores
4. Write unit tests against synthetic data (no live API calls in tests)

Until data exists, no amount of methodological refinement is meaningful.

---

## Other Issues

### Must Fix (blocks publication)
1. **No data, no findings** — the experiment has not been run. The paper is a blank template.
2. **Pronoun manipulation is ambiguous** — the exact wording of "you" vs. "they" conditions must be specified and locked before any data collection.
3. **Coding scheme undefined** — agreement/disagreement scoring must be pre-specified.
4. **API key exposed in directory/file names** — rotate the key and rename the directories.
5. **Domain and publication target are blank** — these must be filled in before the paper can be positioned and the critique can assess fit.

### Should Fix (strengthens paper)
1. **Hypothesis directionality** — specify whether the "you" condition is predicted to increase or decrease agreement with the paper, and provide a theoretical mechanism.
2. **Pre-register the design** — paper selection, question design, coding rubric, and primary statistical test should all be locked before collection to avoid p-hacking.
3. **Power analysis** — 10 papers × 20 questions × 10 runs = 200 question-level observations per condition. Is this sufficient to detect a 5–10 percentage point difference in agreement rates? Run a power calculation.
4. **Control for question difficulty** — not all 20 questions per paper will be equally challenging; some may have an objectively correct answer, making agreement/disagreement non-diagnostic for sycophancy.

### New Experiments / Code to Write
1. **`experiments/pronoun_attribution/run.py`**: Main experiment pipeline. Inputs: paper texts + question bank. Outputs: `data/pronoun_attribution/responses.jsonl` with fields: `{paper_id, question_id, condition, run_id, prompt, response, agreement_score}`.
2. **`experiments/pronoun_attribution/coding.py`**: Automated agreement scoring using the LLM-as-judge pattern, or a structured output schema where the subject LLM must state its position on a 1–5 scale.
3. **`experiments/pronoun_attribution/analysis.py`**: Mixed-effects logistic regression (paper and question as random effects, condition as fixed effect), plus permutation test for robustness. Report Cohen's d and 95% CIs.
4. **Multi-model replication**: Repeat with at least two models (e.g., grok-3 and grok-3-mini) to distinguish model-specific from general effects.
5. **Rename directories**: `experiments/pronoun_attribution_pilot/` and `src/data/xai_client.py` to remove the exposed API key from all file paths.

### Genuinely Unfixable Limitations
- **Interpretability**: We cannot directly observe the LLM's "belief" — we can only observe its surface output. Whether the pronoun manipulation changes internal representations or merely surface-level hedging language is not testable with behavioral data alone. This is an inherent limitation of behavioral probing studies and should be acknowledged (but does not block publication).
- **Generalization across model versions**: Results for grok-3 at a specific checkpoint may not generalize to future model versions. This is inherent to all LLM behavioral research.

---

## Verdict

**MAJOR REVISIONS** (pre-data)

The research question is novel and meritorious. The experimental design is sound in outline but critically underspecified in execution. No data has been collected. The immediate priority is to (a) rotate the exposed API key, (b) specify the exact prompt templates, (c) build the experiment pipeline, and (d) run it. Return with results.
