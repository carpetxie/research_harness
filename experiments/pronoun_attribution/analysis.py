"""
Pronoun Attribution Experiment — Statistical Analysis

Reads data/pronoun_attribution/responses.jsonl and produces:
  - Summary statistics by condition
  - Paired t-test (they vs. you, paired by question)
  - Per-question effect sizes and direction
  - Per-paper aggregates
  - Binary analysis (P(score >= 3), McNemar's test, odds ratio)
  - Mechanism analysis (word count, hedging/affirmation markers)
  - Multi-model breakdowns (if "model" field present)
  - Console report + saved JSON summary

Usage
-----
  uv run python -m experiments.pronoun_attribution.analysis
  uv run python -m experiments.pronoun_attribution.analysis --verbose
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from scipy import stats

RESPONSES_FILE = Path("data/pronoun_attribution/responses.jsonl")
ANALYSIS_FILE = Path("data/pronoun_attribution/analysis.json")

HEDGING_MARKERS = [
    "however", "nevertheless", "despite", "while",
    "that said", "though", "although", "but",
]

AFFIRMATION_MARKERS = [
    "clearly", "indeed", "certainly", "correct", "valid",
    "strong", "well-supported", "sound",
]


# ─────────────────────────────────────────────────────────────────────────────
# Stats helpers
# ─────────────────────────────────────────────────────────────────────────────

def mean(vals: list[float]) -> float:
    return statistics.mean(vals) if vals else float("nan")


def stdev(vals: list[float]) -> float:
    return statistics.stdev(vals) if len(vals) >= 2 else float("nan")


def sem(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return float("nan")
    return stdev(vals) / math.sqrt(n)


def ci95(vals: list[float]) -> tuple[float, float]:
    """Approximate 95% CI using t-distribution with n-1 df (for small n use 2.0)."""
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    m = mean(vals)
    s = sem(vals)
    # t-critical for 95% CI: use 2.0 as conservative approximation
    t_crit = 2.0
    return (m - t_crit * s, m + t_crit * s)


def paired_t_test(x: list[float], y: list[float]) -> tuple[float, float]:
    """Paired t-test. Returns (t_statistic, p_value)."""
    assert len(x) == len(y), "paired_t_test requires equal-length lists"
    diffs = [a - b for a, b in zip(x, y)]
    n = len(diffs)
    if n < 2:
        return (float("nan"), float("nan"))
    d_mean = mean(diffs)
    d_std = stdev(diffs)
    if d_std == 0:
        if d_mean == 0:
            return (0.0, 1.0)
        return (float("inf") if d_mean > 0 else float("-inf"), 0.0)
    t = d_mean / (d_std / math.sqrt(n))
    p = float(stats.t.sf(abs(t), df=n - 1) * 2)
    return (t, p)


def cohen_d(x: list[float], y: list[float]) -> float:
    """Cohen's d for two independent groups."""
    if len(x) < 2 or len(y) < 2:
        return float("nan")
    nx, ny = len(x), len(y)
    sx, sy = stdev(x), stdev(y)
    pooled = math.sqrt(((nx - 1) * sx**2 + (ny - 1) * sy**2) / (nx + ny - 2))
    if pooled == 0:
        return float("nan")
    return (mean(x) - mean(y)) / pooled


def cohen_d_paired(diffs: list[float]) -> float:
    """Cohen's d_z for paired design."""
    if len(diffs) < 2:
        return float("nan")
    sd = stdev(diffs)
    if sd == 0:
        m = mean(diffs)
        return float("inf") if m > 0 else (float("-inf") if m < 0 else float("nan"))
    return mean(diffs) / sd


# ─────────────────────────────────────────────────────────────────────────────
# Binary analysis
# ─────────────────────────────────────────────────────────────────────────────

def binary_analysis(scored: list[dict]) -> dict:
    """
    Compute binary outcome statistics (score >= 3) for they vs. you conditions.

    Returns a dict with:
      - p_high_they: P(score >= 3) for 'they'
      - p_high_you:  P(score >= 3) for 'you'
      - mcnemar: McNemar's test statistic and p-value (paired by qid)
      - odds_ratio: OR with 95% CI (Woolf method)
    """
    by_cond: dict[str, list[int]] = defaultdict(list)
    for r in scored:
        binary = 1 if r["score"] >= 3 else 0
        by_cond[r["condition"]].append(binary)

    they_vals = by_cond.get("they", [])
    you_vals = by_cond.get("you", [])

    p_high_they = mean(they_vals) if they_vals else float("nan")
    p_high_you = mean(you_vals) if you_vals else float("nan")

    # Build paired 2x2 table from per-question means
    q_binary: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for r in scored:
        binary = 1 if r["score"] >= 3 else 0
        q_binary[r["qid"]][r["condition"]].append(binary)

    # McNemar's table: count discordant pairs
    # b = they=1, you=0 (they high, you not)
    # c = they=0, you=1 (you high, they not)
    b, c = 0, 0
    for qid, cond_vals in q_binary.items():
        if "they" not in cond_vals or "you" not in cond_vals:
            continue
        they_bin = 1 if mean(cond_vals["they"]) >= 0.5 else 0
        you_bin = 1 if mean(cond_vals["you"]) >= 0.5 else 0
        if they_bin == 1 and you_bin == 0:
            b += 1
        elif they_bin == 0 and you_bin == 1:
            c += 1

    # McNemar's chi-squared with continuity correction
    if b + c > 0:
        mcnemar_stat = (abs(b - c) - 1) ** 2 / (b + c)
        mcnemar_p = float(stats.chi2.sf(mcnemar_stat, df=1))
    else:
        mcnemar_stat = float("nan")
        mcnemar_p = float("nan")

    # 2x2 contingency table for OR (marginal counts across all records)
    # a = they=1, you=1 (both high) — approximate via paired question data
    a_count, d_count = 0, 0
    for qid, cond_vals in q_binary.items():
        if "they" not in cond_vals or "you" not in cond_vals:
            continue
        they_bin = 1 if mean(cond_vals["they"]) >= 0.5 else 0
        you_bin = 1 if mean(cond_vals["you"]) >= 0.5 else 0
        if they_bin == 1 and you_bin == 1:
            a_count += 1
        elif they_bin == 0 and you_bin == 0:
            d_count += 1

    # Woolf method: OR = (a*d)/(b*c)
    # Use Haldane-Anscombe correction (+0.5) when any cell is zero
    a, d = a_count, d_count
    needs_correction = (a == 0 or b == 0 or c == 0 or d == 0)
    if needs_correction:
        a_c, b_c, c_c, d_c = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    else:
        a_c, b_c, c_c, d_c = float(a), float(b), float(c), float(d)
    if a_c > 0 and b_c > 0 and c_c > 0 and d_c > 0:
        or_val = (a_c * d_c) / (b_c * c_c)
        log_or = math.log(or_val)
        log_se = math.sqrt(1 / a_c + 1 / b_c + 1 / c_c + 1 / d_c)
        or_lo = math.exp(log_or - 1.96 * log_se)
        or_hi = math.exp(log_or + 1.96 * log_se)
        or_correction_note = "Haldane-Anscombe (+0.5) applied" if needs_correction else ""
    else:
        or_val = float("nan")
        or_lo = float("nan")
        or_hi = float("nan")
        or_correction_note = "undefined"

    return {
        "p_high_they": p_high_they,
        "p_high_you": p_high_you,
        "mcnemar_table": {"b_they1_you0": b, "c_they0_you1": c,
                          "a_both1": a_count, "d_both0": d_count},
        "mcnemar_stat": mcnemar_stat,
        "mcnemar_p": mcnemar_p,
        "mcnemar_significant_p05": mcnemar_p < 0.05 if not math.isnan(mcnemar_p) else False,
        "odds_ratio": or_val,
        "odds_ratio_ci95_lo": or_lo,
        "odds_ratio_ci95_hi": or_hi,
        "odds_ratio_note": or_correction_note,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mechanism analysis
# ─────────────────────────────────────────────────────────────────────────────

def _count_markers(text: str, markers: list[str]) -> int:
    """Count occurrences of any marker phrase in text (case-insensitive)."""
    text_lower = text.lower()
    return sum(text_lower.count(m) for m in markers)


def mechanism_analysis(records: list[dict]) -> dict:
    """
    Compute per-condition linguistic mechanism stats.

    For each condition ('they', 'you'), returns:
      - mean_word_count
      - mean_hedging_count: avg occurrences of hedging markers per response
      - mean_affirmation_count: avg occurrences of affirmation markers per response
      - hedging_rate: fraction of responses containing at least one hedging marker
      - affirmation_rate: fraction of responses containing at least one affirmation marker
    """
    # Only use records that have a response text
    text_records = [r for r in records if r.get("response")]

    by_cond: dict[str, list[dict]] = defaultdict(list)
    for r in text_records:
        by_cond[r["condition"]].append(r)

    result = {}
    for cond in ["they", "you"]:
        recs = by_cond.get(cond, [])
        if not recs:
            result[cond] = {
                "n": 0,
                "mean_word_count": float("nan"),
                "mean_hedging_count": float("nan"),
                "mean_affirmation_count": float("nan"),
                "hedging_rate": float("nan"),
                "affirmation_rate": float("nan"),
            }
            continue

        word_counts = [len(r["response"].split()) for r in recs]
        hedging_counts = [_count_markers(r["response"], HEDGING_MARKERS) for r in recs]
        affirmation_counts = [_count_markers(r["response"], AFFIRMATION_MARKERS) for r in recs]

        result[cond] = {
            "n": len(recs),
            "mean_word_count": mean(word_counts),
            "mean_hedging_count": mean(hedging_counts),
            "mean_affirmation_count": mean(affirmation_counts),
            "hedging_rate": sum(1 for c in hedging_counts if c > 0) / len(recs),
            "affirmation_rate": sum(1 for c in affirmation_counts if c > 0) / len(recs),
        }

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Per-model breakdown helpers
# ─────────────────────────────────────────────────────────────────────────────

def _per_model_condition_summary(scored: list[dict]) -> dict:
    """Return per-model condition means and paired stats."""
    models = sorted({r["model"] for r in scored if "model" in r})
    if not models:
        return {}

    result = {}
    for model in models:
        model_records = [r for r in scored if r.get("model") == model]
        by_cond: dict[str, list[float]] = defaultdict(list)
        for r in model_records:
            by_cond[r["condition"]].append(r["score"])

        cond_summary = {}
        for cond in ["they", "you"]:
            vals = by_cond.get(cond, [])
            m = mean(vals)
            s = stdev(vals)
            lo, hi = ci95(vals)
            cond_summary[cond] = {"n": len(vals), "mean": m, "sd": s,
                                   "ci95_lo": lo, "ci95_hi": hi}

        # Paired by question within this model
        q_means: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for r in model_records:
            q_means[r["qid"]][r["condition"]].append(r["score"])

        q_you, q_they = [], []
        for qid, cond_vals in sorted(q_means.items()):
            if "you" in cond_vals and "they" in cond_vals:
                q_you.append(mean(cond_vals["you"]))
                q_they.append(mean(cond_vals["they"]))

        if q_you and q_they:
            t_stat, p_val = paired_t_test(q_you, q_they)
            diffs = [y - t for y, t in zip(q_you, q_they)]
            d_z = cohen_d_paired(diffs)
            d_mean = mean(diffs)
        else:
            t_stat = p_val = d_z = d_mean = float("nan")

        result[model] = {
            "n_scored": len(model_records),
            "conditions": cond_summary,
            "paired_analysis": {
                "n_questions": len(q_you),
                "mean_diff_you_minus_they": d_mean,
                "t_statistic": t_stat,
                "p_value": p_val,
                "cohen_d_z": d_z,
                "significant_p05": p_val < 0.05 if not math.isnan(p_val) else False,
            },
            "binary": binary_analysis(model_records),
            "mechanism": mechanism_analysis(model_records),
        }

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main analysis
# ─────────────────────────────────────────────────────────────────────────────

def load_responses(responses_file: Path | None = None) -> list[dict]:
    path = responses_file or RESPONSES_FILE
    if not path.exists():
        raise FileNotFoundError(f"No responses file at {path}. Run the experiment first.")
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                records.append(r)
    return records


def analyze(verbose: bool = False,
            responses_file: Path | None = None,
            analysis_file: Path | None = None) -> dict:
    records = load_responses(responses_file)
    print(f"Loaded {len(records)} response records.")

    # Filter to scored records only
    scored = [r for r in records if r.get("score") is not None]
    missing = len(records) - len(scored)
    print(f"Scored: {len(scored)} | Missing/error: {missing}")

    # ── 1. Overall condition means ──────────────────────────────────────────
    by_cond: dict[str, list[float]] = defaultdict(list)
    for r in scored:
        by_cond[r["condition"]].append(r["score"])

    print("\n── Overall Condition Summary ──────────────────────────────────────")
    cond_summary = {}
    for cond in ["they", "you"]:
        vals = by_cond.get(cond, [])
        m = mean(vals)
        s = stdev(vals)
        lo, hi = ci95(vals)
        print(f"  {cond:4s}: n={len(vals):4d}  mean={m:.3f}  SD={s:.3f}  "
              f"95%CI=[{lo:.3f},{hi:.3f}]")
        cond_summary[cond] = {"n": len(vals), "mean": m, "sd": s,
                               "ci95_lo": lo, "ci95_hi": hi}

    delta = cond_summary.get("you", {}).get("mean", 0) - \
            cond_summary.get("they", {}).get("mean", 0)
    d_indep = cohen_d(by_cond["you"], by_cond["they"])
    print(f"\n  Δ (you − they) = {delta:+.3f}  Cohen's d = {d_indep:.3f}")

    # ── 2. Paired analysis (by question) ─────────────────────────────────────
    # For each question, compute mean score per condition (averaged over runs)
    q_means: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in scored:
        q_means[r["qid"]][r["condition"]].append(r["score"])

    q_you, q_they, q_ids = [], [], []
    for qid, cond_vals in sorted(q_means.items()):
        if "you" in cond_vals and "they" in cond_vals:
            q_you.append(mean(cond_vals["you"]))
            q_they.append(mean(cond_vals["they"]))
            q_ids.append(qid)

    diffs_paired = [y - t for y, t in zip(q_you, q_they)]
    t_stat, p_val = paired_t_test(q_you, q_they)
    d_paired = cohen_d_paired(diffs_paired)
    d_mean_paired = mean(diffs_paired)
    ci_lo, ci_hi = ci95(diffs_paired)

    print("\n── Paired Analysis (by question, n={}) ─────────────────────────────".format(len(q_ids)))
    print(f"  Mean diff (you − they): {d_mean_paired:+.3f}  "
          f"95%CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
    print(f"  Paired t({len(q_ids)-1}): t={t_stat:.3f}  p={p_val:.4f}")
    print(f"  Cohen's d_z: {d_paired:.3f}")

    direction = "you > they (self-defense)" if d_mean_paired > 0 else "they > you (self-criticism)"
    print(f"  Direction: {direction}")

    sig_label = "SIGNIFICANT" if p_val < 0.05 else "not significant"
    print(f"  Result: {sig_label} at α=0.05")

    # ── 3. Per-question breakdown ─────────────────────────────────────────────
    print("\n── Per-Question Breakdown ───────────────────────────────────────────")
    print(f"  {'QID':<8} {'they_mean':>10} {'you_mean':>10} {'diff':>8} {'n_they':>7} {'n_you':>6}")
    q_details = []
    for qid in q_ids:
        cond_vals = q_means[qid]
        t_m = mean(cond_vals["they"])
        y_m = mean(cond_vals["you"])
        diff = y_m - t_m
        n_t = len(cond_vals["they"])
        n_y = len(cond_vals["you"])
        direction_q = "↑" if diff > 0.05 else ("↓" if diff < -0.05 else "~")
        print(f"  {qid:<8} {t_m:>10.3f} {y_m:>10.3f} {diff:>+7.3f} {direction_q}  "
              f"{n_t:>5} {n_y:>6}")
        q_details.append({"qid": qid, "they_mean": t_m, "you_mean": y_m,
                           "diff": diff, "n_they": n_t, "n_you": n_y})

    n_defense = sum(1 for d in diffs_paired if d > 0)
    n_critical = sum(1 for d in diffs_paired if d < 0)
    n_neutral = len(diffs_paired) - n_defense - n_critical
    print(f"\n  Questions where you > they (self-defense): {n_defense}/{len(q_ids)}")
    print(f"  Questions where you < they (self-critical): {n_critical}/{len(q_ids)}")
    print(f"  Questions where you ≈ they (neutral):      {n_neutral}/{len(q_ids)}")

    # ── 4. Per-paper aggregates ───────────────────────────────────────────────
    paper_data: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in scored:
        paper_data[r["paper_id"]][r["condition"]].append(r["score"])

    print("\n── Per-Paper Aggregates ─────────────────────────────────────────────")
    print(f"  {'PaperID':<10} {'they_mean':>10} {'you_mean':>10} {'diff':>8}")
    paper_details = []
    for pid in sorted(paper_data.keys()):
        pd = paper_data[pid]
        t_m = mean(pd.get("they", []))
        y_m = mean(pd.get("you", []))
        diff = y_m - t_m
        print(f"  {pid:<10} {t_m:>10.3f} {y_m:>10.3f} {diff:>+7.3f}")
        paper_details.append({"paper_id": pid, "they_mean": t_m,
                               "you_mean": y_m, "diff": diff})

    # ── 5. Distribution of scores ─────────────────────────────────────────────
    print("\n── Score Distribution ───────────────────────────────────────────────")
    for cond in ["they", "you"]:
        vals = by_cond.get(cond, [])
        dist = {str(k): vals.count(k) for k in [1, 2, 3, 4, 5]}
        pct = {k: f"{100*v/len(vals):.1f}%" if vals else "0%" for k, v in dist.items()}
        print(f"  {cond}: " + " | ".join(f"{k}:{dist[k]}({pct[k]})" for k in ["1","2","3","4","5"]))

    # ── 6. Binary analysis ────────────────────────────────────────────────────
    print("\n── Binary Analysis (score >= 3) ─────────────────────────────────────")
    bin_results = binary_analysis(scored)
    print(f"  P(score >= 3 | they): {bin_results['p_high_they']:.3f}")
    print(f"  P(score >= 3 | you):  {bin_results['p_high_you']:.3f}")
    tbl = bin_results["mcnemar_table"]
    print(f"  McNemar table: a(both 1)={tbl['a_both1']}  b(they=1,you=0)={tbl['b_they1_you0']}  "
          f"c(they=0,you=1)={tbl['c_they0_you1']}  d(both 0)={tbl['d_both0']}")
    print(f"  McNemar chi2={bin_results['mcnemar_stat']:.3f}  p={bin_results['mcnemar_p']:.4f}  "
          f"({'SIGNIFICANT' if bin_results['mcnemar_significant_p05'] else 'not significant'} at α=0.05)")
    or_val = bin_results["odds_ratio"]
    or_lo = bin_results["odds_ratio_ci95_lo"]
    or_hi = bin_results["odds_ratio_ci95_hi"]
    print(f"  Odds ratio (you/they): {or_val:.3f}  95%CI=[{or_lo:.3f},{or_hi:.3f}]")

    # ── 7. Mechanism analysis ─────────────────────────────────────────────────
    print("\n── Mechanism Analysis ───────────────────────────────────────────────")
    mech_results = mechanism_analysis(records)
    for cond in ["they", "you"]:
        m = mech_results.get(cond, {})
        if not m or m.get("n", 0) == 0:
            print(f"  {cond}: no response text available")
            continue
        print(f"  {cond} (n={m['n']}): "
              f"words={m['mean_word_count']:.1f}  "
              f"hedging={m['mean_hedging_count']:.2f}({100*m['hedging_rate']:.0f}%)  "
              f"affirm={m['mean_affirmation_count']:.2f}({100*m['affirmation_rate']:.0f}%)")

    # ── 8. Multi-model breakdown ──────────────────────────────────────────────
    has_model_field = any("model" in r for r in scored)
    per_model = {}
    if has_model_field:
        models = sorted({r["model"] for r in scored if "model" in r})
        print(f"\n── Per-Model Breakdown ({len(models)} models) ───────────────────────────")
        per_model = _per_model_condition_summary(scored)
        for model, mdata in per_model.items():
            pa = mdata["paired_analysis"]
            print(f"  [{model}] n={mdata['n_scored']}  "
                  f"mean_diff={pa['mean_diff_you_minus_they']:+.3f}  "
                  f"t={pa['t_statistic']:.3f}  p={pa['p_value']:.4f}  "
                  f"d_z={pa['cohen_d_z']:.3f}  "
                  f"({'SIG' if pa['significant_p05'] else 'ns'})")

    # Compile summary
    summary = {
        "n_records": len(records),
        "n_scored": len(scored),
        "conditions": cond_summary,
        "delta_you_minus_they": delta,
        "cohen_d_independent": d_indep,
        "paired_analysis": {
            "n_questions": len(q_ids),
            "mean_diff_you_minus_they": d_mean_paired,
            "ci95_lo": ci_lo,
            "ci95_hi": ci_hi,
            "t_statistic": t_stat,
            "p_value": p_val,
            "cohen_d_z": d_paired,
            "significant_p05": p_val < 0.05,
            "direction": direction,
        },
        "question_counts": {
            "self_defense_you_gt_they": n_defense,
            "self_critical_they_gt_you": n_critical,
            "neutral": n_neutral,
            "total": len(q_ids),
        },
        "binary_analysis": bin_results,
        "mechanism_analysis": mech_results,
        "per_question": q_details,
        "per_paper": paper_details,
    }

    if per_model:
        summary["per_model"] = per_model

    out_file = analysis_file or ANALYSIS_FILE
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nAnalysis saved → {out_file}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--responses-file", type=Path, default=None,
                        help="Path to responses JSONL file (default: data/pronoun_attribution/responses.jsonl)")
    parser.add_argument("--analysis-file", type=Path, default=None,
                        help="Path to write analysis JSON (default: data/pronoun_attribution/analysis.json)")
    args = parser.parse_args()
    analyze(verbose=args.verbose,
            responses_file=args.responses_file,
            analysis_file=args.analysis_file)


if __name__ == "__main__":
    main()
