# Solar Loan Delinquency Analysis

## Project context

Client asked us to investigate rising delinquency rates in their residential solar loan portfolio and determine whether underwriting standards need tightening. Output is a presentation-ready analysis with visuals and recommendations for a leadership meeting.

## Data

- **File**: `solar_loans.csv` — 2,450 funded residential solar loans, Jan 2024 through Dec 2025
- **Dictionary**: `data_dictionary.txt` — column definitions
- 10 states, 5 installer partners, 3 credit tiers (A/prime, B/near-prime, C/subprime)
- No missing data. All columns clean.
- `is_delinquent` is a point-in-time snapshot (TRUE/FALSE), not a time series. No monthly status history exists.
- `days_past_due` = 0 if current, 30+ if delinquent.
- `cents_per_watt` columns: labeled "cents per watt" but likely cents per kWh. Unit ambiguity unresolved with client. Don't make strong claims about utility savings without flagging this.

## Key findings so far

### The trend is real but it's a mix problem, not a performance problem.

1. **Overall delinquency rate rose from 4.8% (Q1 2024) to 15.3% (Q4 2025).**

2. **Root cause: credit mix shift toward subprime.**
   - Tier C share of originations: 6% (Q1 2024) → 44% (Q4 2025)
   - Tier A share dropped from 62% to 30% over the same period

3. **Within-tier delinquency rates are stable.**
   - Tier A: 1-4% across all quarters
   - Tier B: 6-10% across all quarters
   - Tier C: 19-34% (volatile but no clear worsening trend)

4. **Secondary factors:**
   - Avg interest rate climbed 6.3% → 8.3% (consistent with riskier mix)
   - Monthly payments crept up ~$238 → ~$285
   - Installer mix and state mix stayed relatively stable — no concentration issues

5. **Cohort age bias works in favor of the finding.** Newer cohorts have had less time to go delinquent, yet Q4 2025 (youngest) has the highest rate. The signal is likely understated, not overstated.

## Analysis still needed

- **Mix-adjusted delinquency**: Calculate what the rate would have been each quarter if credit mix stayed at Q1 2024 levels. Isolates mix effect vs true performance deterioration.
- **Installer-level delinquency by tier**: Check if any installer has notably worse Tier C performance.
- **State-level breakdown**: See if geographic concentration within Tier C is a factor.
- **Days past due distribution**: Among delinquent loans, how severe? 30-60 vs 90+ matters for loss provisioning.
- **Recommendations**: Frame underwriting tightening options — Tier C volume caps, state restrictions, installer requirements, or spread minimums.

## Dashboards built

- `build_dashboard.py` → `delinquency_dashboard.html`: Dark-themed detailed dashboard. Dual-axis charts (volume bars right axis, delinquency rate lines left axis) for: savings spread, monthly payment, interest rate, loan term, loan amount. All segmented by credit tier. Includes bubble heatmap (spread x tier). Summary stat cards at top.
- `build_exec_view.py` → `exec_credit_mix.html`: White-background exec-facing view. Two charts: (1) stacked bar showing credit tier volume by quarter with % labels, (2) line chart showing % of loans with negative savings spread by tier (solid) overlaid with delinquency rate by tier (dashed). Callout boxes with key takeaways.
- `loan_data_temp.json`: Temp file, safe to delete.

## Output format

Client wants visuals and explanations for a meeting. Build charts (matplotlib, plotly, or similar) and a summary document or slide deck. Keep it executive-friendly — lead with the punchline, support with data.

## Constraints

- Don't assume anything not in the data. No external economic data unless sourced.
- Flag assumptions explicitly.
- The `cents_per_watt` unit issue is unresolved. Use the columns for relative comparisons but caveat any absolute claims.
