# Solar Loan Portfolio: Conversational Analytics Layer

## What this project is

A working prototype of a conversational analytics interface for a residential solar loan portfolio. Non-technical stakeholders (capital markets, operations) type plain-English questions and get answers with data, charts, and explanations -- no SQL, no dashboards to navigate, no waiting on the data team.

This is a proof-of-concept for the exact initiative Palmetto's data team is building. The dataset is synthetic but structurally realistic: 2,450 funded solar loans, Jan 2024 - Dec 2025.

## Why it exists

Palmetto's data team identified two blockers to scaling analytics:
1. Tribal knowledge is scattered -- definitions, business rules, and context live in people's heads, Slack threads, and undocumented SQL.
2. Every ad-hoc question requires a human analyst to write a query, which creates a bottleneck.

This prototype solves both: it encodes domain knowledge into a structured context layer, then uses that context to translate natural language into accurate, self-serve answers.

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────┐
│  Web UI (chat)   │────▶│  Query Engine (Python) │────▶│  solar_loans │
│  Ask a question  │◀────│  NL → pandas/SQL       │◀────│  .csv / .db  │
└─────────────────┘     │  + domain context      │     └─────────────┘
                        │  + chart generation    │
                        └──────────────────────┘
```

### Components to build

1. **`knowledge_base.yaml`** -- Structured domain context file. This is the tribal knowledge layer. Contains:
   - Column definitions with business meaning (not just data types)
   - Derived metrics and how to calculate them (e.g., savings spread = utility cpw - solar cpw)
   - Business rules (e.g., delinquent = 30+ days past due, credit tiers A/B/C map to prime/near-prime/subprime)
   - Known caveats (e.g., cents_per_watt unit ambiguity, is_delinquent is point-in-time not time-series)
   - Common question patterns mapped to analytical approaches
   - Stakeholder glossary (terms capital markets people use vs. operations people)

2. **`query_engine.py`** -- The core logic. Takes a natural language question + the knowledge base context, translates to a pandas operation (or raw SQL if using SQLite), executes, and returns structured results. Must:
   - Parse intent: is this a metric lookup, trend question, comparison, or root cause investigation?
   - Select relevant knowledge base entries to inject as context
   - Generate the analytical code (pandas or SQL)
   - Execute and validate output (row counts, null checks, sanity bounds)
   - Format the answer in plain English with supporting numbers
   - Flag when a question can't be answered with available data

3. **`chart_generator.py`** -- Produces visualizations based on query results. Rules:
   - Default to the simplest chart that answers the question
   - Bar charts for comparisons, line charts for trends, stacked bars for composition
   - Always label axes, include data labels on key points
   - Two style modes: "detailed" (dark theme, analyst-facing) and "exec" (clean white, presentation-ready)
   - Return chart as base64 PNG or embedded HTML (Chart.js) depending on output target
   - Never generate a chart when a single number answers the question

4. **`app.py`** -- Web interface. A single-page chat UI where:
   - User types a question in plain English
   - System shows the interpreted query (so user can verify intent)
   - System returns: plain-English answer, supporting data table (collapsible), chart (if appropriate)
   - Conversation history persists in the session so follow-up questions work ("break that down by state")
   - A "show me how this was calculated" toggle that reveals the generated pandas/SQL

5. **`validate.py`** -- Test harness. A set of known questions with expected answers to verify accuracy:
   - "What's the overall delinquency rate?" → ~9.8% (exact number TBD from data)
   - "How has delinquency changed over time?" → Rising, driven by credit mix shift
   - "Which credit tier has the highest delinquency?" → Tier C
   - "What's the delinquency rate for Tier C loans originated in Q4 2025?" → Should return a specific %
   - "Are any installers worse than others for subprime loans?" → Should break down by installer × tier
   - "What would the delinquency rate be if we kept the same credit mix as Q1 2024?" → Mix-adjusted calculation
   - Edge cases: questions the data can't answer, ambiguous questions, questions requiring external data

## Data

- **Source**: `solar_loans.csv` -- 2,450 rows, 14 columns, no nulls, no duplicates
- **Dictionary**: `data_dictionary.txt`
- **Load into SQLite** (`portfolio.db`) at startup for SQL-based queries. Also keep pandas DataFrame in memory for fast aggregations.

### Column reference

| Column | Type | Business meaning |
|--------|------|-----------------|
| loan_id | string | Unique identifier (L0001-L2450) |
| origination_date | date | When the loan was funded. Use for vintage/cohort analysis. Derive quarter as YYYY-QN. |
| state | string | 2-letter code. 10 states in dataset. Solar production and utility costs vary by state. |
| credit_tier | string | A (prime), B (near-prime), C (subprime). Primary risk stratification. |
| loan_amount | float | Principal in USD. Highly correlated with system_size_kw. |
| system_size_kw | float | Installed solar capacity in kilowatts. |
| loan_term_months | int | Repayment term. Discrete values: 120, 180, 240, 300 months. |
| interest_rate | float | Annual rate as percentage (e.g., 5.25 = 5.25%). Higher for riskier tiers. |
| monthly_payment | float | USD. What the borrower pays us each month. |
| installer_partner | string | 5 partners in dataset. Construction company that did the install. |
| cents_per_watt_of_solar_electricity | float | Proxy for what borrower pays us per unit of energy. |
| cents_per_watt_of_utility_electricity | float | What borrower would pay the utility instead. |
| is_delinquent | bool | TRUE if 30+ days past due. Point-in-time snapshot, NOT time series. |
| days_past_due | int | 0 if current, 30+ if delinquent. Use for severity analysis. |

### Derived metrics (must be encoded in knowledge_base.yaml)

- **Savings spread**: `cents_per_watt_of_utility_electricity - cents_per_watt_of_solar_electricity`. Positive = borrower saves money with solar. Negative = solar costs more than utility.
- **Savings rate (%)**: `savings_spread / cents_per_watt_of_utility_electricity * 100`
- **Origination quarter**: Derived from origination_date. Format: "2024 Q1"
- **Delinquency rate**: `count(is_delinquent=TRUE) / count(all)` for any group
- **Mix-adjusted delinquency**: What the overall rate would be if credit tier proportions matched a reference quarter (default: Q1 2024). Formula: sum of (reference_quarter_tier_share × current_quarter_tier_delinquency_rate).
- **Negative spread flag**: `savings_spread < 0` (borrower is paying more for solar than utility)

### Key findings already established (encode these as "known insights" in the knowledge base)

1. Overall delinquency rose from 4.8% (Q1 2024) to 15.3% (Q4 2025)
2. Root cause: credit mix shifted toward subprime. Tier C went from 6% to 44% of originations.
3. Within-tier rates are relatively stable -- this is a mix problem, not a performance problem.
4. Cohort age bias: newer cohorts have had less time to go delinquent, so Q4 2025's rate is likely understated.
5. Savings spread correlates with delinquency but doesn't fully explain the Q4 spike.

## Existing assets (don't rebuild these, integrate them)

- `delinquency_dashboard.html` -- Detailed risk factor dashboard (dark theme, Chart.js). Dual-axis charts across 5 dimensions + bubble heatmap.
- `exec_credit_mix.html` -- Exec-facing credit mix view (white theme). Stacked quarterly bars + spread overlay.
- `build_dashboard.py` and `build_exec_view.py` -- The scripts that generated the above.

These should be linkable from the chat interface: "Would you like to see the full dashboard?" → opens the relevant HTML.

## Tech stack

- **Python 3.10+**
- **Flask or FastAPI** for the web server (pick whichever is faster to prototype)
- **pandas** for data manipulation
- **SQLite** as the query backend (so we can demonstrate actual SQL generation)
- **Chart.js** (via embedded HTML) for interactive charts in responses
- **matplotlib** as fallback for static chart generation
- No external AI API calls in the base version. The query engine uses pattern matching + template SQL/pandas generation from the knowledge base. This keeps it runnable offline and avoids API key dependencies.
  - OPTIONAL: Add a `--llm` flag that enables Claude API integration for true natural language → SQL translation. If enabled, the knowledge_base.yaml is injected as system context and Claude generates the pandas/SQL. This is the "production" path but the template path should work standalone.

## UI requirements

- Single-page app. Clean, minimal. White background.
- Chat interface: user messages on right, system responses on left.
- Each response contains: plain-English answer (always), data table (collapsible, default collapsed), chart (if applicable), calculation transparency toggle.
- Input box at bottom with placeholder text: "Ask about the portfolio... e.g., 'What's driving the rise in delinquency?'"
- Conversation context carries forward (follow-up questions work).
- No login, no auth. This is a demo.

## Build order

1. `knowledge_base.yaml` first. This is the foundation. Get the domain encoding right before writing any query logic.
2. `query_engine.py` with at least 10 question patterns working against pandas.
3. `chart_generator.py` with bar, line, and stacked bar support.
4. `app.py` web interface.
5. `validate.py` test suite to verify accuracy.
6. Wire in existing dashboards as linked assets.
7. (Optional) Add `--llm` mode with Claude API.

## Constraints

- Every number the system returns must be verifiable against the raw data. No hallucinated stats.
- When the system can't answer a question, it must say so explicitly and suggest what data would be needed.
- Flag the cents_per_watt unit ambiguity on any savings-related answer.
- Don't assume external data (economic conditions, utility rate changes) unless the user provides it.
- Keep the prototype runnable with `python app.py` and no environment variables required (unless --llm mode).

## What success looks like

A capital markets stakeholder can open this in a browser, type "Why are delinquency rates going up?", and get back:

> Delinquency rates rose from 4.8% in Q1 2024 to 15.3% in Q4 2025. The primary driver is a shift in credit mix: Tier C (subprime) loans grew from 6% to 44% of originations over that period. Within each credit tier, delinquency rates have remained relatively stable -- Tier A stays in the 1-4% range, Tier B in 6-10%. This suggests the portfolio isn't deteriorating; we're originating riskier loans.
>
> [Chart: Stacked bar showing credit tier mix by quarter]
>
> If we held the credit mix constant at Q1 2024 levels, the projected Q4 2025 delinquency rate would have been approximately X% instead of 15.3%.

That's the bar. A non-technical person gets a clear answer, a supporting visual, and a concrete counterfactual -- without writing a query or waiting for an analyst.