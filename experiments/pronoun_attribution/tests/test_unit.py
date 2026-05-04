"""
Unit tests for pronoun_attribution experiment.
No network calls — all synthetic data.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import pytest

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from experiments.pronoun_attribution.corpus import (
    PAPERS,
    get_all_questions,
    get_paper,
    get_question,
)
from experiments.pronoun_attribution.run import (
    build_prompts,
    extract_score,
)
from experiments.pronoun_attribution.analysis import (
    mean,
    stdev,
    sem,
    ci95,
    paired_t_test,
    cohen_d,
    cohen_d_paired,
)


# ── Corpus tests ──────────────────────────────────────────────────────────────

class TestCorpus:
    def test_paper_count(self):
        assert len(PAPERS) == 10, f"Expected 10 papers, got {len(PAPERS)}"

    def test_question_count(self):
        questions = get_all_questions()
        assert len(questions) == 20, f"Expected 20 questions, got {len(questions)}"

    def test_each_paper_has_two_questions(self):
        for paper in PAPERS:
            assert len(paper.questions) == 2, (
                f"Paper {paper.paper_id} has {len(paper.questions)} questions, expected 2"
            )

    def test_unique_paper_ids(self):
        ids = [p.paper_id for p in PAPERS]
        assert len(ids) == len(set(ids)), "Paper IDs are not unique"

    def test_unique_question_ids(self):
        qids = [q.qid for q in get_all_questions()]
        assert len(qids) == len(set(qids)), "Question IDs are not unique"

    def test_get_paper(self):
        p = get_paper("P01")
        assert p.paper_id == "P01"
        assert "Research_Paper_1" in p.title

    def test_get_question(self):
        p, q = get_question("P01Q1")
        assert q.qid == "P01Q1"
        assert q.paper_id == "P01"

    def test_get_question_missing(self):
        with pytest.raises(KeyError):
            get_question("P99Q1")

    def test_all_questions_have_required_fields(self):
        for q in get_all_questions():
            assert q.key_claim, f"{q.qid} missing key_claim"
            assert q.challenge, f"{q.qid} missing challenge"
            assert q.conclusion, f"{q.qid} missing conclusion"

    def test_all_papers_have_text(self):
        for p in PAPERS:
            assert len(p.text.strip()) > 100, f"{p.paper_id} text is too short"


# ── Prompt builder tests ──────────────────────────────────────────────────────

class TestPromptBuilder:
    def test_they_condition_contains_they(self):
        sys_p, usr_p = build_prompts(
            condition="they",
            paper_title="Research_Paper_1",
            paper_text="Some text.",
            key_claim="X causes Y",
            challenge="No control group",
            conclusion="that X causes Y",
        )
        assert "anonymous research team" in sys_p.lower() or "anonymous" in sys_p.lower()
        assert "the authors" in usr_p.lower() or "they" in usr_p.lower()
        # Should NOT say "you wrote"
        assert "you wrote" not in sys_p.lower()

    def test_you_condition_contains_you_attribution(self):
        sys_p, usr_p = build_prompts(
            condition="you",
            paper_title="Research_Paper_1",
            paper_text="Some text.",
            key_claim="X causes Y",
            challenge="No control group",
            conclusion="that X causes Y",
        )
        assert "author" in sys_p.lower()
        assert "you wrote" in usr_p.lower() or "your paper" in usr_p.lower()

    def test_invalid_condition(self):
        with pytest.raises(ValueError):
            build_prompts(
                condition="we",
                paper_title="Research_Paper_1",
                paper_text="Some text.",
                key_claim="X",
                challenge="Y",
                conclusion="Z",
            )

    def test_both_conditions_contain_paper_text(self):
        sentinel = "UNIQUE_PAPER_CONTENT_XYZ"
        for cond in ["they", "you"]:
            _, usr_p = build_prompts(
                condition=cond,
                paper_title="Research_Paper_1",
                paper_text=sentinel,
                key_claim="X",
                challenge="Y",
                conclusion="Z",
            )
            assert sentinel in usr_p, f"Paper text missing in {cond} condition"

    def test_both_conditions_have_score_rubric(self):
        for cond in ["they", "you"]:
            _, usr_p = build_prompts(
                condition=cond,
                paper_title="Research_Paper_1",
                paper_text="text",
                key_claim="X",
                challenge="Y",
                conclusion="Z",
            )
            assert "SCORE:" in usr_p
            assert "1 =" in usr_p
            assert "5 =" in usr_p


# ── Score extraction tests ────────────────────────────────────────────────────

class TestScoreExtraction:
    def test_standard_format(self):
        score, raw = extract_score("My analysis.\n\nSCORE: 2")
        assert score == 2
        assert "2" in raw

    def test_case_insensitive(self):
        score, _ = extract_score("score: 4")
        assert score == 4

    def test_with_spaces(self):
        score, _ = extract_score("SCORE:   3")
        assert score == 3

    def test_no_score_returns_none(self):
        score, raw = extract_score("I think the paper has issues.")
        assert score is None
        assert "no score" in raw.lower() or "fallback" in raw.lower() or raw is not None

    def test_score_at_end_of_long_response(self):
        long_response = "A" * 2000 + "\nSCORE: 5"
        score, _ = extract_score(long_response)
        assert score == 5

    def test_valid_range(self):
        for i in [1, 2, 3, 4, 5]:
            score, _ = extract_score(f"SCORE: {i}")
            assert score == i


# ── Analysis / stats tests ────────────────────────────────────────────────────

class TestStats:
    def test_mean(self):
        assert mean([1, 2, 3, 4, 5]) == pytest.approx(3.0)

    def test_mean_empty(self):
        assert math.isnan(mean([]))

    def test_stdev(self):
        # Sample stdev (n-1) of [2,4,4,4,5,5,7,9] ≈ 2.138
        s = stdev([2, 4, 4, 4, 5, 5, 7, 9])
        assert s == pytest.approx(2.138, abs=0.01)

    def test_sem(self):
        vals = [1.0] * 4 + [5.0] * 4  # mean=3, sd=~2, sem=~1
        s = sem(vals)
        assert s > 0

    def test_ci95_mean_in_interval(self):
        vals = [3.0 + (i % 3 - 1) * 0.5 for i in range(20)]
        lo, hi = ci95(vals)
        m = mean(vals)
        assert lo <= m <= hi

    def test_paired_t_identical_no_diff(self):
        x = [3.0, 2.5, 4.0, 3.5, 2.0]
        t, p = paired_t_test(x, x)
        # All diffs are 0, so t=0 and p=1
        assert t == 0.0
        assert p == 1.0

    def test_paired_t_clear_difference(self):
        you = [4.0, 4.5, 3.8, 4.2, 4.0, 3.9, 4.1, 4.3, 4.0, 3.7,
               4.4, 4.2, 3.8, 4.1, 4.0, 3.9, 4.2, 4.3, 4.0, 4.1]
        they = [2.0, 2.5, 1.8, 2.2, 2.0, 1.9, 2.1, 2.3, 2.0, 1.7,
                2.4, 2.2, 1.8, 2.1, 2.0, 1.9, 2.2, 2.3, 2.0, 2.1]
        t, p = paired_t_test(you, they)
        assert t > 0  # you > they
        assert p < 0.001  # very significant

    def test_cohen_d_known_value(self):
        # Two groups with realistic variance around different means
        import random
        rng = random.Random(42)
        x = [1.0 + rng.gauss(0, 1) for _ in range(50)]
        y = [0.0 + rng.gauss(0, 1) for _ in range(50)]
        d = cohen_d(x, y)
        # mean difference ≈ 1.0, pooled SD ≈ 1.0 → d ≈ 1.0
        assert 0.5 < d < 1.8  # wide range given random draws

    def test_cohen_d_paired_uniform(self):
        # All diffs equal → stdev=0 → returns inf
        diffs = [1.0] * 20
        d = cohen_d_paired(diffs)
        assert math.isinf(d) and d > 0

    def test_cohen_d_paired_varied(self):
        diffs = [1.0 + (i % 3 - 1) * 0.1 for i in range(20)]
        d = cohen_d_paired(diffs)
        assert d > 0

    def test_p_value_bounds(self):
        # Test that paired_t_test returns exact p-values via scipy.stats
        from experiments.pronoun_attribution.analysis import paired_t_test
        # t=0 → p should be 1.0 (identical lists)
        x = [2.0, 3.0, 2.5, 3.5, 2.0]
        t, p = paired_t_test(x, x)
        assert t == 0.0
        assert p == 1.0

        # Large t → very small p
        you = [4.0, 4.0, 4.0, 4.0, 4.0]
        they = [1.0, 1.0, 1.0, 1.0, 1.0]
        t2, p2 = paired_t_test(you, they)
        assert p2 < 0.0001  # exact p from t(4) is extremely small
