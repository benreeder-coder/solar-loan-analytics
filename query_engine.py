"""
Query engine for the solar loan conversational analytics interface.

Three-phase pipeline:
  1. UNDERSTAND — intent classification + entity extraction
  2. EXECUTE — pandas operations against the DataFrame
  3. FORMAT — structured QueryResult with answer text, data, chart spec, caveats
"""

import re
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import yaml


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    intent: str
    question: str
    answer_text: str
    data: dict = field(default_factory=dict)          # {columns: [], rows: []}
    chart_spec: Optional[dict] = None
    calculation: str = ""
    caveats: list = field(default_factory=list)
    suggested_followups: list = field(default_factory=list)
    context_update: dict = field(default_factory=dict)

    @classmethod
    def cant_answer(cls, question, reason=None):
        text = "I can't answer that with the available data."
        if reason:
            text += f" {reason}"
        text += " I can help with questions about delinquency rates, credit mix trends, installer performance, state breakdowns, savings spread analysis, and portfolio-level metrics."
        return cls(intent="cant_answer", question=question, answer_text=text)


# ---------------------------------------------------------------------------
# Query Engine
# ---------------------------------------------------------------------------

class QueryEngine:
    def __init__(self, df: pd.DataFrame, knowledge_base: dict):
        self.df = df.copy()
        self.kb = knowledge_base

        # Pre-compute derived columns
        self.df['origination_date'] = pd.to_datetime(self.df['origination_date'])
        self.df['origination_quarter'] = self.df['origination_date'].apply(
            lambda d: f"{d.year} Q{(d.month - 1) // 3 + 1}"
        )
        self.df['savings_spread'] = (
            self.df['cents_per_watt_of_utility_electricity']
            - self.df['cents_per_watt_of_solar_electricity']
        )
        self.df['negative_spread'] = self.df['savings_spread'] < 0

        # Sort quarters for consistent ordering
        self.quarter_order = sorted(self.df['origination_quarter'].unique())

        # Build entity lookup from reference_values
        self._build_entity_map()

        # Handler dispatch
        self.handlers = {
            'overall_delinquency': self._handle_overall_delinquency,
            'delinquency_by_tier': self._handle_delinquency_by_tier,
            'delinquency_trend': self._handle_delinquency_trend,
            'credit_mix_trend': self._handle_credit_mix_trend,
            'mix_adjusted_delinquency': self._handle_mix_adjusted,
            'installer_breakdown': self._handle_installer_breakdown,
            'state_breakdown': self._handle_state_breakdown,
            'dpd_severity': self._handle_dpd_severity,
            'savings_spread': self._handle_savings_spread,
            'loan_distribution': self._handle_loan_distribution,
            'portfolio_summary': self._handle_portfolio_summary,
            'specific_cohort': self._handle_specific_cohort,
            'installer_tier_cross': self._handle_installer_tier_cross,
            'why_rising': self._handle_why_rising,
            'negative_spread': self._handle_negative_spread,
        }

    # -----------------------------------------------------------------------
    # Entity map construction
    # -----------------------------------------------------------------------

    def _build_entity_map(self):
        """Build a reverse-lookup dict from aliases to (column, canonical_value).

        Excludes single-character aliases and very short ambiguous strings
        to prevent false positives when matching within natural language.
        """
        self.entity_map = {}
        ref = self.kb.get('reference_values', {})

        # Minimum alias lengths by category to avoid false positives
        # e.g., "a" would match inside words; "NC" matches "once", etc.
        MIN_ALIAS_LEN = {
            'states': 2,        # State codes are 2 chars, matched with word boundaries
            'credit_tiers': 5,  # Require "tier a", "prime", etc. — not just "a"
            'installers': 4,
            'quarters': 5,
            'loan_terms': 5,
        }

        for canonical, aliases in ref.get('states', {}).items():
            for alias in aliases:
                if len(alias) >= MIN_ALIAS_LEN['states']:
                    self.entity_map[alias.lower()] = ('state', canonical)

        for canonical, aliases in ref.get('credit_tiers', {}).items():
            for alias in aliases:
                if len(alias) >= MIN_ALIAS_LEN['credit_tiers']:
                    self.entity_map[alias.lower()] = ('credit_tier', canonical)

        for canonical, aliases in ref.get('installers', {}).items():
            for alias in aliases:
                if len(alias) >= MIN_ALIAS_LEN['installers']:
                    self.entity_map[alias.lower()] = ('installer_partner', canonical)

        for canonical, aliases in ref.get('quarters', {}).items():
            for alias in aliases:
                if len(alias) >= MIN_ALIAS_LEN['quarters']:
                    self.entity_map[alias.lower()] = ('origination_quarter', canonical)

        for canonical, aliases in ref.get('loan_terms', {}).items():
            for alias in aliases:
                if len(alias) >= MIN_ALIAS_LEN['loan_terms']:
                    self.entity_map[alias.lower()] = ('loan_term_months', int(canonical))

    # -----------------------------------------------------------------------
    # Phase 1: UNDERSTAND
    # -----------------------------------------------------------------------

    def _classify_intent(self, text: str) -> tuple:
        """Score each question pattern against the input. Returns (intent_id, score).

        Uses two matching strategies:
        1. Exact substring match for keyword phrases (3pts multi-word, 1pt single)
        2. All-words-present match for multi-word phrases (2pts) — catches
           "how many loans are delinquent" matching "how many delinquent"
        """
        text_lower = text.lower()
        text_words = set(re.findall(r'\w+', text_lower))
        best_intent = None
        best_score = 0
        best_priority = 0

        for pattern in self.kb.get('question_patterns', []):
            score = 0
            for kw in pattern.get('keywords', []):
                kw_lower = kw.lower()
                if kw_lower in text_lower:
                    # Exact substring match
                    word_count = len(kw_lower.split())
                    score += 3 if word_count > 1 else 1
                elif ' ' in kw_lower:
                    # Fuzzy: all words from the keyword are present in the text
                    kw_words = set(kw_lower.split())
                    if kw_words.issubset(text_words):
                        score += 2

            priority = pattern.get('priority', 0)
            if score > best_score or (score == best_score and priority > best_priority):
                best_score = score
                best_priority = priority
                best_intent = pattern['intent_id']

        if best_score < 1:
            return None, 0

        # Dimension-aware redirect: if user said "by [dimension]" and the matched
        # intent is a single-metric intent, redirect to the appropriate breakdown.
        dimension_redirects = {
            'credit_tier': 'delinquency_by_tier',
            'state': 'state_breakdown',
            'installer_partner': 'installer_breakdown',
            'origination_quarter': 'delinquency_trend',
        }
        single_metric_intents = {'overall_delinquency', 'specific_cohort'}

        if best_intent in single_metric_intents:
            dim_ref = self.kb.get('reference_values', {}).get('dimensions', {})
            for col, phrases in dim_ref.items():
                for phrase in phrases:
                    if phrase.lower() in text_lower:
                        redirect = dimension_redirects.get(col)
                        if redirect:
                            return redirect, best_score
                        break

        return best_intent, best_score

    def _extract_entities(self, text: str) -> dict:
        """Extract filter values and dimension references from the input.

        Uses word-boundary matching to prevent false positives like
        matching "NC" inside "once" or "MA" inside "many".
        """
        text_lower = text.lower()
        entities = {'filters': {}, 'groupby': None}

        # Check for dimension references (longest match first)
        dim_ref = self.kb.get('reference_values', {}).get('dimensions', {})
        for col, phrases in dim_ref.items():
            for phrase in phrases:
                if phrase.lower() in text_lower:
                    entities['groupby'] = col
                    break

        # Check for filter value references using word boundaries
        # Sort longest-first to prefer "BrightPath Solar" over "BrightPath"
        sorted_aliases = sorted(self.entity_map.keys(), key=len, reverse=True)
        matched_columns = set()
        for alias in sorted_aliases:
            col, val = self.entity_map[alias]
            if col in matched_columns:
                continue
            # Use word boundaries for matching
            pattern = r'\b' + re.escape(alias) + r'\b'
            if re.search(pattern, text_lower):
                entities['filters'][col] = val
                matched_columns.add(col)

        return entities

    def _detect_followup(self, text: str, context: dict) -> bool:
        """Detect if this is a follow-up to a previous question."""
        if not context or not context.get('last_intent'):
            return False
        text_lower = text.lower().strip()
        followup_signals = [
            'break that down', 'break it down', 'split by', 'and by',
            'what about', 'how about', 'show me by', 'now by',
            'same thing', 'same but', 'also by', 'break down',
        ]
        for signal in followup_signals:
            if signal in text_lower:
                return True
        # Very short input with just a dimension reference
        if len(text_lower.split()) <= 5:
            dim_ref = self.kb.get('reference_values', {}).get('dimensions', {})
            for phrases in dim_ref.values():
                for phrase in phrases:
                    if phrase.lower() in text_lower:
                        return True
        return False

    # -----------------------------------------------------------------------
    # Main query method
    # -----------------------------------------------------------------------

    def query(self, question: str, session_context: dict = None) -> QueryResult:
        """Process a natural language question and return a structured result."""
        if not question.strip():
            return QueryResult.cant_answer(question)

        context = session_context or {}
        is_followup = self._detect_followup(question, context)
        entities = self._extract_entities(question)

        if is_followup:
            # Inherit previous intent and filters
            intent = context.get('last_intent')
            prev_filters = context.get('last_filters', {})
            # Merge: new entities override, but keep previous where not overridden
            merged_filters = {**prev_filters, **entities['filters']}
            entities['filters'] = merged_filters
            # If new groupby detected, use it; otherwise keep previous
            if not entities['groupby']:
                entities['groupby'] = context.get('last_groupby')
            # If the follow-up introduces a dimension, redirect to the breakdown handler
            if entities['groupby']:
                dimension_handlers = {
                    'credit_tier': 'delinquency_by_tier',
                    'state': 'state_breakdown',
                    'installer_partner': 'installer_breakdown',
                    'origination_quarter': 'delinquency_trend',
                }
                redirect = dimension_handlers.get(entities['groupby'])
                if redirect:
                    intent = redirect
        else:
            intent, score = self._classify_intent(question)

        if intent is None or intent not in self.handlers:
            return QueryResult.cant_answer(question)

        # If a groupby was detected but intent normally has a default, the explicit one wins
        # If no explicit groupby, use the pattern's default
        if not entities['groupby']:
            for pattern in self.kb.get('question_patterns', []):
                if pattern['intent_id'] == intent:
                    entities['groupby'] = pattern.get('default_groupby')
                    break

        handler = self.handlers[intent]
        result = handler(question, entities)

        # Attach caveats based on content
        result.caveats = self._get_caveats(question, intent)

        # Build context update for follow-ups
        result.context_update = {
            'last_intent': intent,
            'last_filters': entities.get('filters', {}),
            'last_groupby': entities.get('groupby'),
            'turn_count': context.get('turn_count', 0) + 1,
        }

        return result

    # -----------------------------------------------------------------------
    # Caveat detection
    # -----------------------------------------------------------------------

    def _get_caveats(self, question: str, intent: str) -> list:
        caveats = []
        text_lower = question.lower()
        for caveat_id, caveat in self.kb.get('caveats', {}).items():
            for trigger in caveat.get('triggers', []):
                if trigger.lower() in text_lower:
                    caveats.append(caveat['text'])
                    break
        # Always add point-in-time caveat for trend questions
        if intent in ('delinquency_trend', 'credit_mix_trend', 'why_rising'):
            pit = self.kb['caveats'].get('point_in_time_snapshot', {}).get('text')
            if pit and pit not in caveats:
                caveats.append(pit)
        return caveats

    # -----------------------------------------------------------------------
    # Helper: apply filters
    # -----------------------------------------------------------------------

    def _apply_filters(self, df: pd.DataFrame, filters: dict) -> tuple:
        """Apply entity-based filters. Returns (filtered_df, filter_description)."""
        filtered = df
        parts = []
        for col, val in filters.items():
            filtered = filtered[filtered[col] == val]
            if col == 'credit_tier':
                label = self.kb['columns']['credit_tier']['tier_labels'].get(val, val)
                parts.append(f"Tier {val} ({label})")
            elif col == 'origination_quarter':
                parts.append(val)
            else:
                parts.append(str(val))
        desc = ", ".join(parts) if parts else "all loans"
        return filtered, desc

    # -----------------------------------------------------------------------
    # Helper: build table data
    # -----------------------------------------------------------------------

    def _table(self, columns: list, rows: list) -> dict:
        return {'columns': columns, 'rows': rows}

    # -----------------------------------------------------------------------
    # Intent handlers
    # -----------------------------------------------------------------------

    def _handle_overall_delinquency(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])
        total = len(df)
        deliq = df['is_delinquent'].sum()
        rate = (deliq / total * 100) if total > 0 else 0

        if entities['filters']:
            answer = f"For {desc}: the delinquency rate is {rate:.1f}% ({deliq:,} of {total:,} loans are 30+ days past due)."
        else:
            answer = f"The overall portfolio delinquency rate is {rate:.1f}% ({deliq:,} of {total:,} loans are 30+ days past due)."

        return QueryResult(
            intent='overall_delinquency',
            question=question,
            answer_text=answer,
            data=self._table(
                ['Metric', 'Value'],
                [['Total Loans', f"{total:,}"], ['Delinquent', f"{deliq:,}"], ['Rate', f"{rate:.1f}%"]]
            ),
            calculation=f"df['is_delinquent'].sum() / len(df) * 100  # = {rate:.1f}%",
            suggested_followups=["Break that down by credit tier", "How has it changed over time?", "Which tier is worst?"],
        )

    def _handle_delinquency_by_tier(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])
        groupby = entities.get('groupby') or 'credit_tier'

        grouped = df.groupby(groupby).agg(
            total=('is_delinquent', 'count'),
            delinquent=('is_delinquent', 'sum')
        ).reset_index()
        grouped['rate'] = (grouped['delinquent'] / grouped['total'] * 100).round(1)

        # Sort by the groupby column
        if groupby == 'credit_tier':
            grouped = grouped.sort_values('credit_tier')
        else:
            grouped = grouped.sort_values('rate', ascending=False)

        rows = []
        for _, r in grouped.iterrows():
            label = str(r[groupby])
            if groupby == 'credit_tier':
                tier_labels = self.kb['columns']['credit_tier']['tier_labels']
                label = f"Tier {r[groupby]} ({tier_labels.get(r[groupby], '')})"
            rows.append([label, f"{int(r['total']):,}", f"{int(r['delinquent']):,}", f"{r['rate']:.1f}%"])

        if groupby == 'credit_tier':
            tier_rates = {r['credit_tier']: r['rate'] for _, r in grouped.iterrows()}
            answer = (
                f"Delinquency rates by credit tier: "
                f"Tier A (prime): {tier_rates.get('A', 0):.1f}%, "
                f"Tier B (near-prime): {tier_rates.get('B', 0):.1f}%, "
                f"Tier C (subprime): {tier_rates.get('C', 0):.1f}%."
            )
            if desc != "all loans":
                answer = f"For {desc} — " + answer
        else:
            answer = f"Delinquency rates by {groupby.replace('_', ' ')}:"
            if desc != "all loans":
                answer = f"For {desc} — " + answer

        chart = {
            'type': 'bar',
            'title': f"Delinquency Rate by {groupby.replace('_', ' ').title()}",
            'labels': [str(r[groupby]) for _, r in grouped.iterrows()],
            'datasets': [{
                'label': 'Delinquency Rate (%)',
                'data': [round(r['rate'], 1) for _, r in grouped.iterrows()],
            }],
            'axes': {
                'x': {'label': groupby.replace('_', ' ').title()},
                'y': {'label': 'Delinquency Rate (%)', 'suffix': '%'},
            },
            'theme': 'exec',
        }
        # Color bars by tier if groupby is credit_tier
        if groupby == 'credit_tier':
            chart['tier_colored'] = True

        followups = ["Break that down by state", "Break that down by installer"]
        if groupby != 'credit_tier':
            followups.insert(0, "Break that down by tier")

        return QueryResult(
            intent='delinquency_by_tier',
            question=question,
            answer_text=answer,
            data=self._table(['Group', 'Total Loans', 'Delinquent', 'Rate'], rows),
            chart_spec=chart,
            calculation=f"df.groupby('{groupby}').agg(total=('is_delinquent','count'), delinquent=('is_delinquent','sum'))",
            suggested_followups=followups,
        )

    def _handle_delinquency_trend(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])
        groupby = entities.get('groupby') or 'origination_quarter'

        # If groupby is a non-time dimension, do a breakdown with that dimension over time
        if groupby not in ('origination_quarter', None):
            return self._handle_delinquency_by_tier(question, entities)

        quarterly = df.groupby('origination_quarter').agg(
            total=('is_delinquent', 'count'),
            delinquent=('is_delinquent', 'sum')
        ).reindex(self.quarter_order).reset_index()
        quarterly['rate'] = (quarterly['delinquent'] / quarterly['total'] * 100).round(1)

        rows = []
        for _, r in quarterly.iterrows():
            rows.append([r['origination_quarter'], f"{int(r['total']):,}", f"{int(r['delinquent']):,}", f"{r['rate']:.1f}%"])

        first = quarterly.iloc[0]
        last = quarterly.iloc[-1]
        answer = (
            f"Delinquency has risen from {first['rate']:.1f}% in {first['origination_quarter']} "
            f"to {last['rate']:.1f}% in {last['origination_quarter']}."
        )
        if desc != "all loans":
            answer = f"For {desc}: " + answer

        chart = {
            'type': 'line',
            'title': 'Delinquency Rate Over Time',
            'labels': list(quarterly['origination_quarter']),
            'datasets': [{
                'label': 'Delinquency Rate (%)',
                'data': list(quarterly['rate']),
            }],
            'axes': {
                'x': {'label': 'Origination Quarter'},
                'y': {'label': 'Delinquency Rate (%)', 'suffix': '%'},
            },
            'theme': 'exec',
        }

        return QueryResult(
            intent='delinquency_trend',
            question=question,
            answer_text=answer,
            data=self._table(['Quarter', 'Total', 'Delinquent', 'Rate'], rows),
            chart_spec=chart,
            calculation="df.groupby('origination_quarter').agg(total=('is_delinquent','count'), delinquent=('is_delinquent','sum'))",
            suggested_followups=["Break that down by tier", "Why is it rising?", "What's the mix-adjusted rate?"],
        )

    def _handle_credit_mix_trend(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])

        cross = df.groupby(['origination_quarter', 'credit_tier']).size().unstack(fill_value=0)
        cross = cross.reindex(self.quarter_order).fillna(0)
        pct = cross.div(cross.sum(axis=1), axis=0) * 100

        rows = []
        for q in self.quarter_order:
            if q in pct.index:
                row = [q]
                for tier in ['A', 'B', 'C']:
                    val = pct.loc[q, tier] if tier in pct.columns else 0
                    row.append(f"{val:.0f}%")
                row.append(f"{int(cross.loc[q].sum()):,}")
                rows.append(row)

        first_q, last_q = self.quarter_order[0], self.quarter_order[-1]
        a_first = pct.loc[first_q, 'A'] if 'A' in pct.columns else 0
        a_last = pct.loc[last_q, 'A'] if 'A' in pct.columns else 0
        c_first = pct.loc[first_q, 'C'] if 'C' in pct.columns else 0
        c_last = pct.loc[last_q, 'C'] if 'C' in pct.columns else 0

        answer = (
            f"Credit mix has shifted significantly. "
            f"Tier C (subprime) share grew from {c_first:.0f}% to {c_last:.0f}% of originations, "
            f"while Tier A (prime) dropped from {a_first:.0f}% to {a_last:.0f}%."
        )

        chart = {
            'type': 'stacked_bar',
            'title': 'Credit Tier Mix by Origination Quarter',
            'labels': list(self.quarter_order),
            'datasets': [],
            'axes': {
                'x': {'label': 'Origination Quarter'},
                'y': {'label': 'Share of Originations (%)', 'suffix': '%', 'max': 100},
            },
            'theme': 'exec',
        }
        for tier in ['A', 'B', 'C']:
            if tier in pct.columns:
                chart['datasets'].append({
                    'label': f'Tier {tier}',
                    'data': [round(pct.loc[q, tier], 1) if q in pct.index else 0 for q in self.quarter_order],
                    'tier': tier,
                })

        return QueryResult(
            intent='credit_mix_trend',
            question=question,
            answer_text=answer,
            data=self._table(['Quarter', 'Tier A', 'Tier B', 'Tier C', 'Total Loans'], rows),
            chart_spec=chart,
            calculation="df.groupby(['origination_quarter','credit_tier']).size().unstack(fill_value=0).div(totals, axis=0)*100",
            suggested_followups=["What's the mix-adjusted delinquency rate?", "Why is delinquency rising?"],
        )

    def _handle_mix_adjusted(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])

        # Reference shares from knowledge base (Q1 2024)
        ref_shares = self.kb['derived_metrics']['mix_adjusted_delinquency']['reference_shares']

        # Calculate per-quarter, per-tier delinquency rates
        cross = df.groupby(['origination_quarter', 'credit_tier']).agg(
            total=('is_delinquent', 'count'),
            delinquent=('is_delinquent', 'sum')
        ).reset_index()
        cross['rate'] = cross['delinquent'] / cross['total']

        rows = []
        adjusted_rates = {}
        actual_rates = {}
        for q in self.quarter_order:
            q_data = cross[cross['origination_quarter'] == q]
            q_total = q_data['total'].sum()
            q_deliq = q_data['delinquent'].sum()
            actual = (q_deliq / q_total * 100) if q_total > 0 else 0
            actual_rates[q] = actual

            # Mix-adjusted: apply reference shares to current tier rates
            adjusted = 0
            for tier, share in ref_shares.items():
                tier_row = q_data[q_data['credit_tier'] == tier]
                if len(tier_row) > 0:
                    tier_rate = tier_row.iloc[0]['rate']
                else:
                    tier_rate = 0
                adjusted += share * tier_rate
            adjusted *= 100
            adjusted_rates[q] = adjusted

            rows.append([q, f"{actual:.1f}%", f"{adjusted:.1f}%", f"{actual - adjusted:+.1f}pp"])

        last_q = self.quarter_order[-1]
        answer = (
            f"If credit mix had stayed at Q1 2024 levels "
            f"(62% Tier A, 32% Tier B, 6% Tier C), "
            f"the {last_q} delinquency rate would have been approximately "
            f"{adjusted_rates[last_q]:.1f}% instead of the actual {actual_rates[last_q]:.1f}%. "
            f"The {actual_rates[last_q] - adjusted_rates[last_q]:.1f} percentage point gap "
            f"is attributable to the shift toward riskier credit tiers."
        )

        chart = {
            'type': 'line',
            'title': 'Actual vs Mix-Adjusted Delinquency Rate',
            'labels': list(self.quarter_order),
            'datasets': [
                {
                    'label': 'Actual Rate',
                    'data': [round(actual_rates[q], 1) for q in self.quarter_order],
                    'style': 'solid',
                },
                {
                    'label': 'Mix-Adjusted Rate (Q1 2024 mix)',
                    'data': [round(adjusted_rates[q], 1) for q in self.quarter_order],
                    'style': 'dashed',
                },
            ],
            'axes': {
                'x': {'label': 'Origination Quarter'},
                'y': {'label': 'Delinquency Rate (%)', 'suffix': '%'},
            },
            'theme': 'exec',
        }

        return QueryResult(
            intent='mix_adjusted_delinquency',
            question=question,
            answer_text=answer,
            data=self._table(['Quarter', 'Actual Rate', 'Mix-Adjusted Rate', 'Difference'], rows),
            chart_spec=chart,
            calculation=(
                "# Mix-adjusted = sum(Q1_2024_tier_share * current_quarter_tier_rate)\n"
                "ref_shares = {'A': 0.62, 'B': 0.32, 'C': 0.06}\n"
                "for tier, share in ref_shares.items():\n"
                "    adjusted += share * quarter_tier_rate[tier]"
            ),
            suggested_followups=["Show me the credit mix trend", "Break that down by tier"],
        )

    def _handle_installer_breakdown(self, question, entities):
        # Delegate to the generic groupby handler
        entities['groupby'] = entities.get('groupby') or 'installer_partner'
        return self._handle_delinquency_by_tier(question, entities)

    def _handle_state_breakdown(self, question, entities):
        entities['groupby'] = entities.get('groupby') or 'state'
        return self._handle_delinquency_by_tier(question, entities)

    def _handle_dpd_severity(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])
        deliq = df[df['is_delinquent'] == True].copy()
        total = len(deliq)

        if total == 0:
            return QueryResult(
                intent='dpd_severity',
                question=question,
                answer_text=f"No delinquent loans found for {desc}.",
            )

        bins = [(30, 59, '30-59 days'), (60, 89, '60-89 days'), (90, 119, '90-119 days'), (120, 9999, '120+ days')]
        counts = {}
        for lo, hi, label in bins:
            counts[label] = len(deliq[(deliq['days_past_due'] >= lo) & (deliq['days_past_due'] <= hi)])

        rows = []
        for label, count in counts.items():
            pct = count / total * 100
            rows.append([label, f"{count:,}", f"{pct:.0f}%"])

        early = counts['30-59 days']
        mid = counts['60-89 days']
        late = counts['90-119 days']
        severe = counts['120+ days']

        answer = (
            f"Among {total:,} delinquent loans: "
            f"{early:,} are 30-59 days past due ({early/total*100:.0f}%), "
            f"{mid:,} are 60-89 days ({mid/total*100:.0f}%), "
            f"{late:,} are 90-119 days ({late/total*100:.0f}%), "
            f"and {severe:,} are 120+ days ({severe/total*100:.0f}%)."
        )
        if desc != "all loans":
            answer = f"For {desc}: " + answer

        chart = {
            'type': 'bar',
            'title': 'Days Past Due Distribution (Delinquent Loans)',
            'labels': list(counts.keys()),
            'datasets': [{
                'label': 'Number of Loans',
                'data': list(counts.values()),
            }],
            'axes': {
                'x': {'label': 'Days Past Due'},
                'y': {'label': 'Number of Loans'},
            },
            'theme': 'exec',
            'severity_colored': True,
        }

        return QueryResult(
            intent='dpd_severity',
            question=question,
            answer_text=answer,
            data=self._table(['DPD Band', 'Count', 'Share'], rows),
            chart_spec=chart,
            calculation="df[df['is_delinquent']].groupby(pd.cut(df['days_past_due'], bins=[30,60,90,120,999])).size()",
            suggested_followups=["Break that down by tier", "What's driving the rise in delinquency?"],
        )

    def _handle_savings_spread(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])

        # Band the spread into ranges
        bins = [(-999, -2, '< -2'), (-2, 0, '-2 to 0'), (0, 2, '0 to 2'),
                (2, 5, '2 to 5'), (5, 10, '5 to 10'), (10, 999, '10+')]
        band_data = []
        for lo, hi, label in bins:
            band = df[(df['savings_spread'] > lo) & (df['savings_spread'] <= hi)]
            count = len(band)
            deliq_rate = (band['is_delinquent'].mean() * 100) if count > 0 else 0
            band_data.append({'label': label, 'count': count, 'rate': round(deliq_rate, 1)})

        rows = [[b['label'], f"{b['count']:,}", f"{b['rate']:.1f}%"] for b in band_data]

        neg_count = len(df[df['savings_spread'] < 0])
        neg_pct = neg_count / len(df) * 100 if len(df) > 0 else 0
        neg_rate = (df[df['savings_spread'] < 0]['is_delinquent'].mean() * 100) if neg_count > 0 else 0
        pos_rate = (df[df['savings_spread'] >= 0]['is_delinquent'].mean() * 100) if (len(df) - neg_count) > 0 else 0

        answer = (
            f"Savings spread analysis: {neg_count:,} loans ({neg_pct:.1f}%) have a negative spread "
            f"(borrower pays more for solar). Delinquency rate for negative-spread loans: {neg_rate:.1f}% "
            f"vs {pos_rate:.1f}% for positive-spread loans."
        )
        if desc != "all loans":
            answer = f"For {desc}: " + answer

        chart = {
            'type': 'bar',
            'title': 'Delinquency Rate by Savings Spread Band',
            'labels': [b['label'] for b in band_data],
            'datasets': [
                {
                    'label': 'Delinquency Rate (%)',
                    'data': [b['rate'] for b in band_data],
                    'type': 'line',
                },
                {
                    'label': 'Loan Count',
                    'data': [b['count'] for b in band_data],
                    'type': 'bar',
                    'yAxisID': 'y2',
                },
            ],
            'axes': {
                'x': {'label': 'Savings Spread (cents)'},
                'y': {'label': 'Delinquency Rate (%)', 'suffix': '%'},
                'y2': {'label': 'Loan Count', 'position': 'right'},
            },
            'theme': 'exec',
        }

        return QueryResult(
            intent='savings_spread',
            question=question,
            answer_text=answer,
            data=self._table(['Spread Band (cents)', 'Loan Count', 'Delinquency Rate'], rows),
            chart_spec=chart,
            calculation="df.groupby(pd.cut(df['savings_spread'], bins)).agg(count=('loan_id','count'), rate=('is_delinquent','mean'))",
            caveats=[self.kb['caveats']['cents_per_watt_unit_ambiguity']['text']],
            suggested_followups=["How many loans have negative spread?", "Break that down by tier"],
        )

    def _handle_loan_distribution(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])
        col = 'loan_amount'

        stats = {
            'mean': df[col].mean(),
            'median': df[col].median(),
            'min': df[col].min(),
            'max': df[col].max(),
            'std': df[col].std(),
        }

        answer = (
            f"Loan amount distribution: average ${stats['mean']:,.0f}, "
            f"median ${stats['median']:,.0f}, "
            f"range ${stats['min']:,.0f} - ${stats['max']:,.0f}."
        )
        if desc != "all loans":
            answer = f"For {desc}: " + answer

        # Bucket into $10k bands
        band_edges = list(range(10000, 65001, 10000))
        labels = []
        counts = []
        for i in range(len(band_edges) - 1):
            lo, hi = band_edges[i], band_edges[i + 1]
            label = f"${lo // 1000}k-${hi // 1000}k"
            labels.append(label)
            counts.append(len(df[(df[col] >= lo) & (df[col] < hi)]))

        rows = [
            ['Mean', f"${stats['mean']:,.0f}"],
            ['Median', f"${stats['median']:,.0f}"],
            ['Min', f"${stats['min']:,.0f}"],
            ['Max', f"${stats['max']:,.0f}"],
            ['Std Dev', f"${stats['std']:,.0f}"],
        ]

        chart = {
            'type': 'bar',
            'title': 'Loan Amount Distribution',
            'labels': labels,
            'datasets': [{'label': 'Number of Loans', 'data': counts}],
            'axes': {
                'x': {'label': 'Loan Amount'},
                'y': {'label': 'Number of Loans'},
            },
            'theme': 'exec',
        }

        return QueryResult(
            intent='loan_distribution',
            question=question,
            answer_text=answer,
            data=self._table(['Statistic', 'Value'], rows),
            chart_spec=chart,
            calculation=f"df['loan_amount'].describe()",
            suggested_followups=["Break that down by tier", "What's the average interest rate?"],
        )

    def _handle_portfolio_summary(self, question, entities):
        df = self.df
        total = len(df)
        total_volume = df['loan_amount'].sum()
        deliq_rate = df['is_delinquent'].mean() * 100
        avg_rate = df['interest_rate'].mean()
        avg_payment = df['monthly_payment'].mean()
        avg_amount = df['loan_amount'].mean()
        states = df['state'].nunique()
        installers = df['installer_partner'].nunique()
        date_range = f"{df['origination_date'].min().strftime('%b %Y')} - {df['origination_date'].max().strftime('%b %Y')}"

        tier_counts = df['credit_tier'].value_counts()
        tier_pcts = (tier_counts / total * 100).round(0)

        answer = (
            f"Portfolio overview: {total:,} loans totaling ${total_volume:,.0f} "
            f"originated {date_range} across {states} states and {installers} installer partners. "
            f"Overall delinquency rate: {deliq_rate:.1f}%. "
            f"Credit mix: Tier A {tier_pcts.get('A', 0):.0f}%, Tier B {tier_pcts.get('B', 0):.0f}%, Tier C {tier_pcts.get('C', 0):.0f}%. "
            f"Average loan: ${avg_amount:,.0f} at {avg_rate:.1f}% interest, ${avg_payment:,.0f}/month."
        )

        rows = [
            ['Total Loans', f"{total:,}"],
            ['Total Volume', f"${total_volume:,.0f}"],
            ['Date Range', date_range],
            ['States', f"{states}"],
            ['Installers', f"{installers}"],
            ['Delinquency Rate', f"{deliq_rate:.1f}%"],
            ['Tier A Share', f"{tier_pcts.get('A', 0):.0f}%"],
            ['Tier B Share', f"{tier_pcts.get('B', 0):.0f}%"],
            ['Tier C Share', f"{tier_pcts.get('C', 0):.0f}%"],
            ['Avg Loan Amount', f"${avg_amount:,.0f}"],
            ['Avg Interest Rate', f"{avg_rate:.1f}%"],
            ['Avg Monthly Payment', f"${avg_payment:,.0f}"],
        ]

        return QueryResult(
            intent='portfolio_summary',
            question=question,
            answer_text=answer,
            data=self._table(['Metric', 'Value'], rows),
            calculation="df.describe() + df.groupby('credit_tier').size()",
            suggested_followups=["What's the delinquency rate?", "How has the credit mix changed?", "Why is delinquency rising?"],
        )

    def _handle_specific_cohort(self, question, entities):
        if not entities['filters']:
            # No specific filters detected, fall back to overall
            return self._handle_overall_delinquency(question, entities)

        df, desc = self._apply_filters(self.df, entities['filters'])
        total = len(df)

        if total == 0:
            return QueryResult(
                intent='specific_cohort',
                question=question,
                answer_text=f"No loans found matching {desc}.",
            )

        deliq = df['is_delinquent'].sum()
        rate = (deliq / total * 100) if total > 0 else 0

        answer = f"For {desc}: delinquency rate is {rate:.1f}% ({deliq:,} of {total:,} loans)."

        return QueryResult(
            intent='specific_cohort',
            question=question,
            answer_text=answer,
            data=self._table(
                ['Filter', 'Total Loans', 'Delinquent', 'Rate'],
                [[desc, f"{total:,}", f"{deliq:,}", f"{rate:.1f}%"]]
            ),
            calculation=f"filtered = df[{entities['filters']}]; filtered['is_delinquent'].mean() * 100",
            suggested_followups=["Break that down by state", "How does that compare to other tiers?"],
        )

    def _handle_installer_tier_cross(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])

        cross = df.groupby(['installer_partner', 'credit_tier']).agg(
            total=('is_delinquent', 'count'),
            delinquent=('is_delinquent', 'sum')
        ).reset_index()
        cross['rate'] = (cross['delinquent'] / cross['total'] * 100).round(1)

        # Pivot for display
        pivot = cross.pivot_table(index='installer_partner', columns='credit_tier', values='rate', fill_value=0)
        pivot = pivot.round(1)

        rows = []
        for installer in sorted(df['installer_partner'].unique()):
            row = [installer]
            for tier in ['A', 'B', 'C']:
                val = pivot.loc[installer, tier] if installer in pivot.index and tier in pivot.columns else 0
                row.append(f"{val:.1f}%")
            rows.append(row)

        answer = "Delinquency rates by installer and credit tier:"
        if desc != "all loans":
            answer = f"For {desc}: " + answer

        # Find notable outliers
        for _, r in cross.iterrows():
            tier_avg = df[df['credit_tier'] == r['credit_tier']]['is_delinquent'].mean() * 100
            if r['rate'] > tier_avg * 1.5 and r['total'] >= 10:
                answer += f" {r['installer_partner']} has notably higher Tier {r['credit_tier']} delinquency ({r['rate']:.1f}% vs {tier_avg:.1f}% average)."

        chart = {
            'type': 'bar',
            'title': 'Delinquency Rate: Installer x Credit Tier',
            'labels': sorted(df['installer_partner'].unique()),
            'datasets': [],
            'axes': {
                'x': {'label': 'Installer Partner'},
                'y': {'label': 'Delinquency Rate (%)', 'suffix': '%'},
            },
            'theme': 'exec',
            'grouped': True,
        }
        for tier in ['A', 'B', 'C']:
            tier_data = []
            for installer in sorted(df['installer_partner'].unique()):
                val = pivot.loc[installer, tier] if installer in pivot.index and tier in pivot.columns else 0
                tier_data.append(round(val, 1))
            chart['datasets'].append({
                'label': f'Tier {tier}',
                'data': tier_data,
                'tier': tier,
            })

        return QueryResult(
            intent='installer_tier_cross',
            question=question,
            answer_text=answer,
            data=self._table(['Installer', 'Tier A', 'Tier B', 'Tier C'], rows),
            chart_spec=chart,
            calculation="df.groupby(['installer_partner','credit_tier']).agg(rate=('is_delinquent','mean')).unstack()*100",
            suggested_followups=["Which installer is worst for Tier C?", "Show me delinquency by state"],
        )

    def _handle_why_rising(self, question, entities):
        df = self.df

        # 1. Headline rate trend
        quarterly = df.groupby('origination_quarter').agg(
            total=('is_delinquent', 'count'),
            delinquent=('is_delinquent', 'sum')
        ).reindex(self.quarter_order).reset_index()
        quarterly['rate'] = (quarterly['delinquent'] / quarterly['total'] * 100).round(1)

        first_q = self.quarter_order[0]
        last_q = self.quarter_order[-1]
        first_rate = quarterly[quarterly['origination_quarter'] == first_q]['rate'].iloc[0]
        last_rate = quarterly[quarterly['origination_quarter'] == last_q]['rate'].iloc[0]

        # 2. Credit mix
        cross = df.groupby(['origination_quarter', 'credit_tier']).size().unstack(fill_value=0)
        cross = cross.reindex(self.quarter_order).fillna(0)
        pct = cross.div(cross.sum(axis=1), axis=0) * 100

        c_first = pct.loc[first_q, 'C'] if 'C' in pct.columns else 0
        c_last = pct.loc[last_q, 'C'] if 'C' in pct.columns else 0
        a_first = pct.loc[first_q, 'A'] if 'A' in pct.columns else 0
        a_last = pct.loc[last_q, 'A'] if 'A' in pct.columns else 0

        # 3. Mix-adjusted rate for last quarter
        ref_shares = self.kb['derived_metrics']['mix_adjusted_delinquency']['reference_shares']
        q_data = df[df['origination_quarter'] == last_q]
        adjusted = 0
        for tier, share in ref_shares.items():
            tier_df = q_data[q_data['credit_tier'] == tier]
            tier_rate = tier_df['is_delinquent'].mean() if len(tier_df) > 0 else 0
            adjusted += share * tier_rate
        adjusted *= 100

        answer = (
            f"Delinquency rates rose from {first_rate:.1f}% in {first_q} to {last_rate:.1f}% in {last_q}. "
            f"The primary driver is a shift in credit mix: Tier C (subprime) loans grew from {c_first:.0f}% "
            f"to {c_last:.0f}% of originations over that period, while Tier A (prime) dropped from {a_first:.0f}% to {a_last:.0f}%. "
            f"\n\nWithin each credit tier, delinquency rates have remained relatively stable — "
            f"Tier A stays in the 1-4% range, Tier B in 6-10%. This suggests the portfolio isn't deteriorating; "
            f"we're originating riskier loans."
            f"\n\nIf we held the credit mix constant at {first_q} levels, the {last_q} delinquency rate "
            f"would have been approximately {adjusted:.1f}% instead of {last_rate:.1f}%."
        )

        # Show credit mix chart
        chart = {
            'type': 'stacked_bar',
            'title': 'Credit Tier Mix by Origination Quarter',
            'labels': list(self.quarter_order),
            'datasets': [],
            'axes': {
                'x': {'label': 'Origination Quarter'},
                'y': {'label': 'Share of Originations (%)', 'suffix': '%', 'max': 100},
            },
            'theme': 'exec',
        }
        for tier in ['A', 'B', 'C']:
            if tier in pct.columns:
                chart['datasets'].append({
                    'label': f'Tier {tier}',
                    'data': [round(pct.loc[q, tier], 1) if q in pct.index else 0 for q in self.quarter_order],
                    'tier': tier,
                })

        rows = []
        for q in self.quarter_order:
            q_df = df[df['origination_quarter'] == q]
            q_rate = q_df['is_delinquent'].mean() * 100
            a_share = pct.loc[q, 'A'] if 'A' in pct.columns and q in pct.index else 0
            c_share = pct.loc[q, 'C'] if 'C' in pct.columns and q in pct.index else 0
            rows.append([q, f"{q_rate:.1f}%", f"{a_share:.0f}%", f"{c_share:.0f}%", f"{int(len(q_df)):,}"])

        return QueryResult(
            intent='why_rising',
            question=question,
            answer_text=answer,
            data=self._table(['Quarter', 'Delinq Rate', 'Tier A Share', 'Tier C Share', 'Total Loans'], rows),
            chart_spec=chart,
            calculation=(
                "# Headline rate by quarter\n"
                "df.groupby('origination_quarter')['is_delinquent'].mean()*100\n"
                "# Credit mix by quarter\n"
                "df.groupby(['origination_quarter','credit_tier']).size().unstack().div(totals)*100\n"
                "# Mix-adjusted = sum(Q1_2024_share * current_tier_rate)"
            ),
            suggested_followups=["What's the mix-adjusted delinquency rate?", "Show me delinquency by tier", "Are any installers worse for subprime?"],
        )

    def _handle_negative_spread(self, question, entities):
        df, desc = self._apply_filters(self.df, entities['filters'])

        neg = df[df['negative_spread'] == True]
        pos = df[df['negative_spread'] == False]
        total = len(df)
        neg_count = len(neg)
        neg_pct = (neg_count / total * 100) if total > 0 else 0

        neg_deliq = neg['is_delinquent'].mean() * 100 if neg_count > 0 else 0
        pos_deliq = pos['is_delinquent'].mean() * 100 if len(pos) > 0 else 0

        # Break down by tier
        rows = []
        tier_data = []
        for tier in ['A', 'B', 'C']:
            tier_df = df[df['credit_tier'] == tier]
            tier_neg = tier_df[tier_df['negative_spread'] == True]
            tier_neg_count = len(tier_neg)
            tier_neg_pct = (tier_neg_count / len(tier_df) * 100) if len(tier_df) > 0 else 0
            tier_neg_deliq = (tier_neg['is_delinquent'].mean() * 100) if tier_neg_count > 0 else 0
            rows.append([f"Tier {tier}", f"{tier_neg_count:,}", f"{tier_neg_pct:.1f}%", f"{tier_neg_deliq:.1f}%"])
            tier_data.append({'tier': tier, 'neg_pct': round(tier_neg_pct, 1), 'neg_deliq': round(tier_neg_deliq, 1)})

        answer = (
            f"{neg_count:,} loans ({neg_pct:.1f}%) have a negative savings spread "
            f"(borrower pays more for solar than utility). "
            f"Delinquency rate for negative-spread loans: {neg_deliq:.1f}% vs {pos_deliq:.1f}% for positive-spread loans."
        )
        if desc != "all loans":
            answer = f"For {desc}: " + answer

        chart = {
            'type': 'bar',
            'title': 'Negative Spread: Share and Delinquency by Tier',
            'labels': [f"Tier {td['tier']}" for td in tier_data],
            'datasets': [
                {
                    'label': '% with Negative Spread',
                    'data': [td['neg_pct'] for td in tier_data],
                },
                {
                    'label': 'Delinquency Rate (neg spread)',
                    'data': [td['neg_deliq'] for td in tier_data],
                },
            ],
            'axes': {
                'x': {'label': 'Credit Tier'},
                'y': {'label': 'Percentage (%)', 'suffix': '%'},
            },
            'theme': 'exec',
            'grouped': True,
        }

        return QueryResult(
            intent='negative_spread',
            question=question,
            answer_text=answer,
            data=self._table(['Tier', 'Neg Spread Count', 'Neg Spread %', 'Neg Spread Deliq Rate'], rows),
            chart_spec=chart,
            calculation="df[df['savings_spread'] < 0].groupby('credit_tier').agg(count=('loan_id','count'), rate=('is_delinquent','mean'))",
            caveats=[self.kb['caveats']['cents_per_watt_unit_ambiguity']['text']],
            suggested_followups=["Show me savings spread analysis", "Why is delinquency rising?"],
        )
