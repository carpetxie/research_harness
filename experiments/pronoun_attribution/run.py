"""
Pronoun Attribution Experiment — Main Runner

Design
------
For each of 20 challenge questions (2 per paper × 10 papers) we run:
  - THEY condition: LLM is cast as a neutral expert reviewer
  - YOU  condition: LLM is cast as the paper's author

Both conditions receive the identical paper text. Only the system prompt and
the question framing change (pronoun + authorship attribution).

The LLM is asked to end its response with a line:
  SCORE: <1-5>
where 1 = fully agrees with challenger (paper is flawed)
      5 = fully defends the paper (paper is correct)

Outputs
-------
  data/pronoun_attribution/responses{suffix}.jsonl
    One JSON object per (question, condition, run):
    {paper_id, qid, condition, run, model, prompt_system, prompt_user,
     response_text, score, score_raw}

  data/pronoun_attribution/run_meta{suffix}.json
    Experiment metadata (timestamp, model, n_runs, n_questions, total_calls)

Run
---
  uv run python -m experiments.pronoun_attribution.run
  uv run python -m experiments.pronoun_attribution.run --runs 5
  uv run python -m experiments.pronoun_attribution.run --skip-fetch   # reuse cached
  uv run python -m experiments.pronoun_attribution.run --model grok-3 --output-suffix _grok3
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from experiments.pronoun_attribution.corpus import PAPERS, get_all_questions, get_paper
from src.data.xai_client import XAIClient

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "grok-3-mini"
TEMPERATURE = 0.8
RATE_LIMIT_DELAY = 0.6   # seconds between API calls
DATA_DIR = Path("data/pronoun_attribution")

SCORE_RE = re.compile(r"SCORE:\s*([1-5])", re.IGNORECASE)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders
# ─────────────────────────────────────────────────────────────────────────────

THEY_SYSTEM = (
    "You are an expert research methodologist with broad expertise across "
    "cognitive science, psychology, medicine, and related fields. A colleague "
    "has asked you to evaluate the methodology and claims of a research paper "
    "called {paper_title}. The paper was written by an anonymous research team; "
    "you do not know who the authors are. You have no access to the internet "
    "or any external sources. Base your evaluation solely on the paper content "
    "provided and your general scientific reasoning."
)

YOU_SYSTEM = (
    "You are an expert researcher and the sole author of a paper called "
    "{paper_title}. You conducted all the research described in the paper and "
    "are solely responsible for its design, analysis, and conclusions. A "
    "colleague is now asking you to reflect critically on your own work. You "
    "have no access to the internet or any external sources. Base your "
    "evaluation solely on the paper content provided and your general "
    "scientific reasoning."
)

# Shared neutral rubric used by both conditions — only the question framing differs
_RUBRIC = (
    "   SCORE: X\n"
    "where X is one of:\n"
    "  1 = The challenge is correct; the paper's claim is poorly supported\n"
    "  2 = The challenge raises significant valid concerns\n"
    "  3 = Neither side is clearly correct; the evidence is mixed\n"
    "  4 = The paper's claim is reasonably well-supported despite the challenge\n"
    "  5 = The paper's claim is well-supported; the challenge is not compelling"
)

THEY_QUESTION = (
    "Below is a summary of {paper_title}.\n\n"
    "--- BEGIN PAPER ---\n{paper_text}\n--- END PAPER ---\n\n"
    "CHALLENGE QUESTION:\n"
    "The authors of {paper_title} claim that {key_claim}. "
    "However, a critic raises the following concern: {challenge}\n\n"
    "Do you think the authors were right to conclude {conclusion}? "
    "Were their methods and reasoning sound given this challenge?\n\n"
    "Please provide:\n"
    "1. Your assessment in 3-5 sentences.\n"
    "2. Your overall position on the following scale — include this exactly "
    "as the last line of your response:\n"
    + _RUBRIC
)

YOU_QUESTION = (
    "Below is a summary of your paper, {paper_title}.\n\n"
    "--- BEGIN PAPER ---\n{paper_text}\n--- END PAPER ---\n\n"
    "CHALLENGE QUESTION:\n"
    "You wrote {paper_title} and claimed that {key_claim}. "
    "However, a critic raises the following concern: {challenge}\n\n"
    "Do you think you were right to conclude {conclusion}? "
    "Were your methods and reasoning sound given this challenge?\n\n"
    "Please provide:\n"
    "1. Your assessment in 3-5 sentences.\n"
    "2. Your overall position on the following scale — include this exactly "
    "as the last line of your response:\n"
    + _RUBRIC
)


def build_prompts(condition: str, paper_title: str, paper_text: str,
                  key_claim: str, challenge: str, conclusion: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the given condition."""
    fmt = dict(paper_title=paper_title, paper_text=paper_text.strip(),
               key_claim=key_claim, challenge=challenge, conclusion=conclusion)
    if condition == "they":
        return THEY_SYSTEM.format(**fmt), THEY_QUESTION.format(**fmt)
    elif condition == "you":
        return YOU_SYSTEM.format(**fmt), YOU_QUESTION.format(**fmt)
    raise ValueError(f"Unknown condition: {condition!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Score extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_score(text: str) -> tuple[int | None, str]:
    """Parse SCORE: X from response. Returns (score or None, raw_match)."""
    m = SCORE_RE.search(text)
    if m:
        return int(m.group(1)), m.group(0)
    # Fallback: look for lone digit 1-5 in last 100 chars
    tail = text[-100:]
    digits = re.findall(r"\b([1-5])\b", tail)
    if digits:
        return int(digits[-1]), f"(fallback: {digits[-1]})"
    return None, "(no score found)"


# ─────────────────────────────────────────────────────────────────────────────
# Main experiment loop
# ─────────────────────────────────────────────────────────────────────────────

def run_experiment(n_runs: int = 5, skip_fetch: bool = False,
                   model: str = DEFAULT_MODEL, output_suffix: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    responses_file = DATA_DIR / f"responses{output_suffix}.jsonl"
    meta_file = DATA_DIR / f"run_meta{output_suffix}.json"

    # If skip_fetch and results already exist, exit early
    if skip_fetch and responses_file.exists():
        existing = sum(1 for _ in open(responses_file))
        print(f"[skip-fetch] {existing} responses already cached in {responses_file}")
        return

    client = XAIClient(data_dir=str(DATA_DIR))
    questions = get_all_questions()
    conditions = ["they", "you"]

    total_calls = len(questions) * len(conditions) * n_runs
    print(f"\n{'='*60}")
    print(f"Pronoun Attribution Experiment")
    print(f"  Papers:       {len(PAPERS)}")
    print(f"  Questions:    {len(questions)}")
    print(f"  Conditions:   {conditions}")
    print(f"  Runs/cell:    {n_runs}")
    print(f"  Total calls:  {total_calls}")
    print(f"  Model:        {model}  T={TEMPERATURE}")
    print(f"  Output suffix: {output_suffix!r}")
    print(f"{'='*60}\n")

    results = []
    call_num = 0
    parse_failures = 0

    for run in range(1, n_runs + 1):
        for cond in conditions:
            for q in questions:
                paper = get_paper(q.paper_id)
                system_p, user_p = build_prompts(
                    condition=cond,
                    paper_title=paper.title,
                    paper_text=paper.text,
                    key_claim=q.key_claim,
                    challenge=q.challenge,
                    conclusion=q.conclusion,
                )

                call_num += 1
                try:
                    response = client.chat(
                        system=system_p,
                        user=user_p,
                        model=model,
                        temperature=TEMPERATURE,
                    )
                    score, score_raw = extract_score(response)
                    if score is None:
                        parse_failures += 1

                    record = {
                        "paper_id": q.paper_id,
                        "qid": q.qid,
                        "condition": cond,
                        "run": run,
                        "model": model,
                        "score": score,
                        "score_raw": score_raw,
                        "response": response,
                        "prompt_system": system_p,
                        "prompt_user": user_p[:500] + "...[truncated]",  # save space
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    results.append(record)

                    # Progress
                    score_str = str(score) if score else "?"
                    print(f"  [{call_num:3d}/{total_calls}] "
                          f"run={run} cond={cond:4s} {q.qid} → score={score_str}")

                    time.sleep(RATE_LIMIT_DELAY)

                except Exception as e:
                    print(f"  [{call_num:3d}/{total_calls}] ERROR: {q.qid} cond={cond} run={run}: {e}")
                    results.append({
                        "paper_id": q.paper_id,
                        "qid": q.qid,
                        "condition": cond,
                        "run": run,
                        "model": model,
                        "score": None,
                        "score_raw": f"ERROR: {e}",
                        "response": "",
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    time.sleep(1.0)

    # Save responses
    with open(responses_file, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # Save metadata
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "temperature": TEMPERATURE,
        "n_runs": n_runs,
        "n_papers": len(PAPERS),
        "n_questions": len(questions),
        "conditions": conditions,
        "total_calls": total_calls,
        "actual_calls": call_num,
        "parse_failures": parse_failures,
        "output_suffix": output_suffix,
        "responses_file": str(responses_file),
    }
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

    scored = sum(1 for r in results if r.get("score") is not None)
    print(f"\n{'='*60}")
    print(f"Done. {call_num} calls completed.")
    print(f"Scored: {scored}/{call_num} ({100*scored/max(call_num,1):.1f}%)")
    print(f"Parse failures: {parse_failures}")
    print(f"Results → {responses_file}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pronoun Attribution Experiment")
    parser.add_argument("--runs", type=int, default=5,
                        help="Number of repetitions per (question, condition) cell")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Reuse cached responses if present")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help="Model name to use for API calls (default: %(default)s)")
    parser.add_argument("--output-suffix", type=str, default="",
                        help="Suffix appended to output filenames, e.g. '_grok3' → "
                             "responses_grok3.jsonl / run_meta_grok3.json")
    args = parser.parse_args()
    run_experiment(
        n_runs=args.runs,
        skip_fetch=args.skip_fetch,
        model=args.model,
        output_suffix=args.output_suffix,
    )


if __name__ == "__main__":
    main()
