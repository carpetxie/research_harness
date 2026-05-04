"""
Pronoun Attribution Experiment — Statistical Analysis

Reads data/pronoun_attribution/responses.jsonl and produces:
  - Summary statistics by condition
  - Paired t-test (they vs. you, paired by question)
  - Per-question effect sizes and direction
  - Per-paper aggregates
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

RESPONSES_FILE = Path("data/pronoun_attribution/responses.jsonl")
ANALYSIS_FILE = Path("data/pronoun_attribution/analysis.json")


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
    """Paired t-test. Returns (t_statistic, approximate_p_value)."""
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
    # Approximate p-value from t with n-1 df using normal approximation for n≥20
    # For smaller n, use a rough look-up
    p = approx_p_from_t(t, df=n - 1)
    return (t, p)


def approx_p_from_t(t: float, df: int) -> float:
    """Rough two-tailed p-value approximation for t-statistic."""
    # Use simple approximation: for df >= 20 use normal; else use crude table
    import math
    abs_t = abs(t)
    if math.isnan(abs_t) or math.isinf(abs_t):
        return 0.0 if math.isinf(abs_t) else float("nan")

    # Normal approximation (good for df >= 30)
    # P(|Z| > z) ≈ 2 * (1 - Φ(z))
    # Use rational approximation for Φ
    z = abs_t * math.sqrt(df / (df + abs_t ** 2))  # better approx
    p_one = _phi_upper(abs(z))
    return min(2 * p_one, 1.0)


def _phi_upper(z: float) -> float:
    """Upper tail probability of standard normal (1 - Φ(z)) using Abramowitz & Stegun."""
    if z < 0:
        return 1.0 - _phi_upper(-z)
    t = 1.0 / (1.0 + 0.2316419 * z)
    poly = t * (0.319381530
                + t * (-0.356563782
                       + t * (1.781477937
                              + t * (-1.821255978
                                     + t * 1.330274429))))
    return poly * math.exp(-0.5 * z ** 2) / math.sqrt(2 * math.pi)


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
# Main analysis
# ─────────────────────────────────────────────────────────────────────────────

def load_responses() -> list[dict]:
    if not RESPONSES_FILE.exists():
        raise FileNotFoundError(f"No responses file at {RESPONSES_FILE}. Run the experiment first.")
    records = []
    with open(RESPONSES_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                records.append(r)
    return records


def analyze(verbose: bool = False) -> dict:
    records = load_responses()
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
    print(f"  Paired t({len(q_ids)-1}): t={t_stat:.3f}  p≈{p_val:.4f}")
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
        "per_question": q_details,
        "per_paper": paper_details,
    }

    ANALYSIS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ANALYSIS_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nAnalysis saved → {ANALYSIS_FILE}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    analyze(verbose=args.verbose)


if __name__ == "__main__":
    main()
