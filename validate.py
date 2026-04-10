"""
Validation test harness for the solar loan query engine.

Runs known questions against the engine and checks expected answers.
Run: python validate.py
"""

import os
import sys

import pandas as pd
import yaml

from query_engine import QueryEngine

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# Load data and engine
df = pd.read_csv(os.path.join(DATA_DIR, 'solar_loans.csv'))
with open(os.path.join(DATA_DIR, 'knowledge_base.yaml'), 'r') as f:
    kb = yaml.safe_load(f)
engine = QueryEngine(df, kb)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [
    # --- Basic metrics ---
    {
        'question': "What's the overall delinquency rate?",
        'expected_contains': ['10.9%'],
        'expect_intent': 'overall_delinquency',
        'expect_chart': False,
        'category': 'basic_metric',
    },
    {
        'question': "How many loans are delinquent?",
        'expected_contains': ['267', '2,450'],
        'expect_intent': 'overall_delinquency',
        'expect_chart': False,
        'category': 'basic_metric',
    },

    # --- Tier comparison ---
    {
        'question': "What's the delinquency rate by credit tier?",
        'expected_contains': ['3.0%', '7.2%', '26.7%'],
        'expect_intent': 'delinquency_by_tier',
        'expect_chart': True,
        'category': 'comparison',
    },
    {
        'question': "Which credit tier has the highest delinquency?",
        'expected_contains': ['Tier C', '26.7%'],
        'expect_intent': 'delinquency_by_tier',
        'expect_chart': True,
        'category': 'comparison',
    },

    # --- Trends ---
    {
        'question': "How has delinquency changed over time?",
        'expected_contains': ['2024 Q1', '2025 Q4'],
        'expect_intent': 'delinquency_trend',
        'expect_chart': True,
        'category': 'trend',
    },

    # --- Credit mix ---
    {
        'question': "How has the credit mix changed?",
        'expected_contains': ['Tier C', 'Tier A'],
        'expect_intent': 'credit_mix_trend',
        'expect_chart': True,
        'category': 'trend',
    },

    # --- Mix-adjusted ---
    {
        'question': "What would delinquency be if we kept the same credit mix as Q1 2024?",
        'expected_contains': ['mix', 'Q1 2024', '%'],
        'expect_intent': 'mix_adjusted_delinquency',
        'expect_chart': True,
        'category': 'calculation',
    },

    # --- Installer ---
    {
        'question': "Show me delinquency by installer",
        'expected_contains': ['installer'],
        'expect_intent': None,  # routed through delinquency_by_tier with groupby override
        'expect_chart': True,
        'category': 'comparison',
    },

    # --- State ---
    {
        'question': "What's the delinquency rate by state?",
        'expected_contains': [],
        'expect_intent': None,  # routed through dimension redirect
        'expect_chart': True,
        'category': 'comparison',
    },

    # --- DPD severity ---
    {
        'question': "How severe are the delinquencies?",
        'expected_contains': ['30-59', '120+'],
        'expect_intent': 'dpd_severity',
        'expect_chart': True,
        'category': 'distribution',
    },

    # --- Savings spread ---
    {
        'question': "What's the relationship between savings spread and delinquency?",
        'expected_contains': ['negative', 'spread'],
        'expect_intent': 'savings_spread',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- Portfolio summary ---
    {
        'question': "Give me a portfolio overview",
        'expected_contains': ['2,450', 'delinquency'],
        'expect_intent': 'portfolio_summary',
        'expect_chart': False,
        'category': 'summary',
    },

    # --- Specific cohort ---
    {
        'question': "What's the delinquency rate for Tier C loans in Q4 2025?",
        'expected_contains': ['Tier C', '%'],
        'expect_intent': 'specific_cohort',
        'expect_chart': False,
        'category': 'filtered',
    },

    # --- Installer x tier cross ---
    {
        'question': "Which installers are worst for subprime loans?",
        'expected_contains': ['installer', 'tier'],
        'expect_intent': 'installer_tier_cross',
        'expect_chart': True,
        'category': 'cross_tab',
    },

    # --- Why rising ---
    {
        'question': "Why is delinquency rising?",
        'expected_contains': ['credit mix', 'Tier C'],
        'expect_intent': 'why_rising',
        'expect_chart': True,
        'category': 'narrative',
    },
    {
        'question': "What's driving the increase in delinquency?",
        'expected_contains': ['mix', 'Tier C'],
        'expect_intent': 'why_rising',
        'expect_chart': True,
        'category': 'narrative',
    },

    # --- Negative spread ---
    {
        'question': "How many loans have negative savings spread?",
        'expected_contains': ['negative', 'spread'],
        'expect_intent': 'negative_spread',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- Edge cases ---
    {
        'question': "What's the weather like today?",
        'expected_contains': ["can't answer"],
        'expect_intent': 'cant_answer',
        'expect_chart': False,
        'category': 'edge_case',
    },
    {
        'question': "",
        'expected_contains': ["can't answer"],
        'expect_intent': 'cant_answer',
        'expect_chart': False,
        'category': 'edge_case',
    },

    # --- Metric trend ---
    {
        'question': "How has the interest rate changed over time?",
        'expected_contains': ['interest', 'rate'],
        'expect_intent': 'metric_trend',
        'expect_chart': True,
        'category': 'metric_trend',
    },
    {
        'question': "Monthly payment trend by quarter",
        'expected_contains': ['payment'],
        'expect_intent': 'metric_trend',
        'expect_chart': True,
        'category': 'metric_trend',
    },

    # --- Tier × quarter cross ---
    {
        'question': "Show delinquency by tier for each quarter",
        'expected_contains': ['tier', 'stable'],
        'expect_intent': 'tier_quarter_cross',
        'expect_chart': True,
        'category': 'cross_tab',
    },

    # --- Savings band × tier ---
    {
        'question': "Delinquency by savings spread band and tier",
        'expected_contains': ['spread', 'tier'],
        'expect_intent': 'savings_band_analysis',
        'expect_chart': True,
        'category': 'cross_tab',
    },

    # --- Payment analysis ---
    {
        'question': "What's the average monthly payment by tier?",
        'expected_contains': ['Tier A', 'Tier B', 'Tier C'],
        'expect_intent': 'payment_analysis',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- Interest rate analysis ---
    {
        'question': "What's the average interest rate by tier?",
        'expected_contains': ['Tier A', 'Tier C'],
        'expect_intent': 'interest_rate_analysis',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- System size ---
    {
        'question': "Does system size affect delinquency?",
        'expected_contains': ['system size', 'no meaningful'],
        'expect_intent': 'system_size_analysis',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- Loan term ---
    {
        'question': "Does loan term affect delinquency?",
        'expected_contains': ['term', '%'],
        'expect_intent': 'loan_term_analysis',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- Concentration risk ---
    {
        'question': "How concentrated is the portfolio geographically?",
        'expected_contains': ['top', '%'],
        'expect_intent': 'concentration_risk',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- Correlation ---
    {
        'question': "What factors correlate with delinquency?",
        'expected_contains': ['interest rate', 'savings'],
        'expect_intent': 'correlation_analysis',
        'expect_chart': True,
        'category': 'analysis',
    },

    # --- Recommendations ---
    {
        'question': "What should we do about rising delinquency?",
        'expected_contains': ['tier c', 'cap', 'spread'],
        'expect_intent': 'recommendations',
        'expect_chart': False,
        'category': 'recommendations',
    },

    # --- State × tier cross ---
    {
        'question': "Which states are worst for Tier C loans?",
        'expected_contains': ['state', 'tier'],
        'expect_intent': 'state_tier_cross',
        'expect_chart': True,
        'category': 'cross_tab',
    },

    # --- Questions from the interview ---
    {
        'question': "What's the average number of days late by loan originated quarter?",
        'expected_contains': ['days past due'],
        'expect_intent': 'avg_dpd',
        'expect_chart': True,
        'category': 'interview_question',
    },
    {
        'question': "Show the distribution of loan originations by state for each loan origination quarter",
        'expected_contains': ['volume', 'state'],
        'expect_intent': 'origination_volume',
        'expect_chart': True,
        'category': 'interview_question',
    },

    # --- Follow-up simulation ---
    # (follow-ups tested separately below)
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests():
    passed = 0
    failed = 0
    errors = []

    print("=" * 70)
    print("SOLAR LOAN QUERY ENGINE VALIDATION")
    print("=" * 70)
    print()

    for i, tc in enumerate(TEST_CASES):
        q = tc['question']
        label = f"[{tc['category']}] {q[:60]}{'...' if len(q) > 60 else ''}"

        try:
            result = engine.query(q)
            issues = []

            # Check intent
            if tc.get('expect_intent') and result.intent != tc['expect_intent']:
                issues.append(f"intent: expected '{tc['expect_intent']}', got '{result.intent}'")

            # Check expected substrings
            answer_lower = result.answer_text.lower()
            for expected in tc.get('expected_contains', []):
                if expected.lower() not in answer_lower:
                    issues.append(f"missing '{expected}' in answer")

            # Check chart presence
            if tc.get('expect_chart') is True and result.chart_spec is None:
                issues.append("expected chart but got none")
            elif tc.get('expect_chart') is False and result.chart_spec is not None:
                issues.append("got chart but expected none")

            if issues:
                failed += 1
                errors.append((label, issues, result.answer_text[:200]))
                print(f"  FAIL  {label}")
                for issue in issues:
                    print(f"        -> {issue}")
            else:
                passed += 1
                print(f"  PASS  {label}")

        except Exception as e:
            failed += 1
            errors.append((label, [f"exception: {e}"], ""))
            print(f"  ERROR {label}")
            print(f"        -> {e}")

    # --- Follow-up tests ---
    print()
    print("-" * 70)
    print("FOLLOW-UP CONTEXT TESTS")
    print("-" * 70)

    followup_tests = [
        {
            'turns': [
                ("What's the delinquency rate?", 'overall_delinquency'),
                ("Break that down by tier", 'delinquency_by_tier'),
            ]
        },
        {
            'turns': [
                ("Delinquency by credit tier", 'delinquency_by_tier'),
                ("By state", 'delinquency_by_tier'),  # follow-up changes groupby
            ]
        },
    ]

    for ft in followup_tests:
        ctx = {}
        all_ok = True
        turn_labels = []
        for q, expected_intent in ft['turns']:
            result = engine.query(q, session_context=ctx)
            ctx = result.context_update
            ok = result.intent == expected_intent
            status = "ok" if ok else f"got {result.intent}"
            turn_labels.append(f"'{q}' -> {status}")
            if not ok:
                all_ok = False
                failed += 1
            else:
                passed += 1

        icon = "PASS" if all_ok else "FAIL"
        print(f"  {icon}  {' | '.join(turn_labels)}")

    # --- Summary ---
    print()
    print("=" * 70)
    total = passed + failed
    print(f"RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    print("=" * 70)

    if errors:
        print()
        print("FAILURES:")
        for label, issues, answer in errors:
            print(f"\n  {label}")
            for issue in issues:
                print(f"    - {issue}")
            if answer:
                print(f"    Answer: {answer}")

    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
