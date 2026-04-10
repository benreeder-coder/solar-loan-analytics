"""Build exec-facing HTML: credit mix by quarter + negative spread % by tier."""

import csv
import json

data = list(csv.DictReader(open("solar_loans.csv")))
loans = []
for r in data:
    date = r["origination_date"]
    year = date[:4]
    month = int(date[5:7])
    q = (month - 1) // 3 + 1
    loans.append({
        "q": f"{year} Q{q}",
        "s": round(float(r["cents_per_watt_of_utility_electricity"]) - float(r["cents_per_watt_of_solar_electricity"]), 2),
        "c": r["credit_tier"],
        "d": 1 if r["is_delinquent"] == "TRUE" else 0,
    })

json_data = json.dumps(loans, separators=(",", ":"))

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Credit Mix &amp; Savings Spread by Quarter</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #fff;
    color: #1a1a1a;
    padding: 48px 40px;
    max-width: 960px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 20px;
    font-weight: 700;
    color: #111;
    margin-bottom: 4px;
  }}
  .subtitle {{
    font-size: 13px;
    color: #666;
    margin-bottom: 32px;
    line-height: 1.5;
  }}
  .chart-section {{
    margin-bottom: 48px;
  }}
  .chart-section h2 {{
    font-size: 15px;
    font-weight: 600;
    color: #222;
    margin-bottom: 4px;
  }}
  .chart-section .desc {{
    font-size: 12px;
    color: #888;
    margin-bottom: 16px;
  }}
  .chart-wrap {{
    position: relative;
    height: 340px;
  }}
  .chart-wrap canvas {{
    width: 100% !important;
  }}
  .legend-row {{
    display: flex;
    gap: 24px;
    justify-content: center;
    margin-bottom: 32px;
    font-size: 12px;
    color: #555;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .legend-swatch {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
  }}
  .callout {{
    background: #f8f9fa;
    border-left: 3px solid #e67e22;
    padding: 14px 18px;
    margin-top: 16px;
    font-size: 13px;
    color: #333;
    line-height: 1.5;
    border-radius: 0 6px 6px 0;
  }}
  .callout strong {{ color: #111; }}
  .divider {{
    border: none;
    border-top: 1px solid #eee;
    margin: 8px 0 40px;
  }}
</style>
</head>
<body>

<h1>Origination Mix Shift &amp; Savings Spread Analysis</h1>
<p class="subtitle">Quarterly view, Jan 2024 &ndash; Dec 2025. Top: loan volume by credit tier. Bottom: % of loans where solar costs more than utility, by tier.</p>

<div class="legend-row">
  <div class="legend-item"><div class="legend-swatch" style="background:#2563eb"></div> Tier A (Prime)</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#f59e0b"></div> Tier B (Near-Prime)</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#ef4444"></div> Tier C (Subprime)</div>
</div>

<div class="chart-section">
  <h2>Origination Volume by Credit Tier</h2>
  <p class="desc">Each bar = one quarter. Segments show loan count per tier. Labels show tier share %.</p>
  <div class="chart-wrap">
    <canvas id="mixChart"></canvas>
  </div>
  <div class="callout" id="mixCallout"></div>
</div>

<hr class="divider">

<div class="chart-section">
  <h2>% of Loans with Negative Savings Spread</h2>
  <p class="desc">Negative spread = borrower's solar electricity costs more per watt than their local utility. Higher % = weaker value proposition for the borrower.</p>
  <div class="chart-wrap">
    <canvas id="spreadChart"></canvas>
  </div>
  <div class="callout" id="spreadCallout"></div>
</div>

<script>
const DATA = {json_data};

const TIER_COLORS = {{
  A: '#2563eb',
  B: '#f59e0b',
  C: '#ef4444'
}};
const TIER_COLORS_LIGHT = {{
  A: 'rgba(37,99,235,0.85)',
  B: 'rgba(245,158,11,0.85)',
  C: 'rgba(239,68,68,0.85)'
}};

const QUARTERS = ['2024 Q1','2024 Q2','2024 Q3','2024 Q4','2025 Q1','2025 Q2','2025 Q3','2025 Q4'];
const TIERS = ['A','B','C'];

// Compute per-quarter, per-tier stats
function getStats() {{
  const stats = {{}};
  QUARTERS.forEach(q => {{
    stats[q] = {{}};
    TIERS.forEach(t => {{
      const subset = DATA.filter(d => d.q === q && d.c === t);
      const n = subset.length;
      const negSpread = subset.filter(d => d.s < 0).length;
      const delinq = subset.filter(d => d.d === 1).length;
      stats[q][t] = {{ n, negSpread, delinq }};
    }});
    const allQ = DATA.filter(d => d.q === q);
    stats[q].total = allQ.length;
  }});
  return stats;
}}

const stats = getStats();

// --- Chart 1: Stacked bar with % labels ---
(function() {{
  const ctx = document.getElementById('mixChart').getContext('2d');

  const datasets = TIERS.map(t => ({{
    label: 'Tier ' + t,
    data: QUARTERS.map(q => stats[q][t].n),
    backgroundColor: TIER_COLORS_LIGHT[t],
    borderColor: TIER_COLORS[t],
    borderWidth: 1,
    borderRadius: 2
  }}));

  new Chart(ctx, {{
    type: 'bar',
    data: {{ labels: QUARTERS, datasets }},
    plugins: [ChartDataLabels],
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        datalabels: {{
          color: '#fff',
          font: {{ size: 11, weight: '600' }},
          formatter: function(value, context) {{
            const q = QUARTERS[context.dataIndex];
            const total = stats[q].total;
            const pct = (value / total * 100).toFixed(0);
            if (value < 30) return '';
            return value + '\\n(' + pct + '%)';
          }},
          textAlign: 'center',
          anchor: 'center',
          align: 'center'
        }},
        tooltip: {{
          callbacks: {{
            label: function(ctx2) {{
              const q = QUARTERS[ctx2.dataIndex];
              const total = stats[q].total;
              const pct = (ctx2.raw / total * 100).toFixed(1);
              return ctx2.dataset.label + ': ' + ctx2.raw + ' loans (' + pct + '%)';
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          stacked: true,
          grid: {{ display: false }},
          ticks: {{ color: '#555', font: {{ size: 12, weight: '500' }} }}
        }},
        y: {{
          stacked: true,
          grid: {{ color: '#f0f0f0' }},
          ticks: {{ color: '#888' }},
          title: {{ display: true, text: 'Loan Count', color: '#888', font: {{ size: 12 }} }}
        }}
      }}
    }}
  }});

  // Callout
  const q1 = stats['2024 Q1'];
  const q8 = stats['2025 Q4'];
  const cPctStart = (q1.C.n / q1.total * 100).toFixed(0);
  const cPctEnd = (q8.C.n / q8.total * 100).toFixed(0);
  const aPctStart = (q1.A.n / q1.total * 100).toFixed(0);
  const aPctEnd = (q8.A.n / q8.total * 100).toFixed(0);
  document.getElementById('mixCallout').innerHTML =
    '<strong>Tier C (subprime) grew from ' + cPctStart + '% to ' + cPctEnd + '% of originations.</strong> ' +
    'Tier A (prime) fell from ' + aPctStart + '% to ' + aPctEnd + '%. ' +
    'Total quarterly volume increased from ' + q1.total + ' to ' + q8.total + ' loans.';
}})();

// --- Chart 2: % negative spread by tier per quarter ---
(function() {{
  const ctx = document.getElementById('spreadChart').getContext('2d');

  const datasets = TIERS.map(t => ({{
    label: 'Tier ' + t,
    data: QUARTERS.map(q => {{
      const s = stats[q][t];
      return s.n > 0 ? (s.negSpread / s.n * 100) : 0;
    }}),
    borderColor: TIER_COLORS[t],
    backgroundColor: TIER_COLORS[t],
    borderWidth: 2.5,
    pointRadius: 5,
    pointHoverRadius: 7,
    tension: 0.3,
    fill: false
  }}));

  // Also add the delinquency rate by tier as dashed lines
  TIERS.forEach(t => {{
    datasets.push({{
      label: 'Tier ' + t + ' Delinq Rate',
      data: QUARTERS.map(q => {{
        const s = stats[q][t];
        return s.n > 0 ? (s.delinq / s.n * 100) : 0;
      }}),
      borderColor: TIER_COLORS[t],
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderDash: [6, 4],
      pointRadius: 3,
      pointStyle: 'rectRot',
      tension: 0.3,
      fill: false
    }});
  }});

  new Chart(ctx, {{
    type: 'line',
    data: {{ labels: QUARTERS, datasets }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{
          display: true,
          position: 'bottom',
          labels: {{
            color: '#555',
            font: {{ size: 11 }},
            usePointStyle: true,
            padding: 16
          }}
        }},
        datalabels: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: function(ctx2) {{
              return ctx2.dataset.label + ': ' + ctx2.raw.toFixed(1) + '%';
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          grid: {{ display: false }},
          ticks: {{ color: '#555', font: {{ size: 12, weight: '500' }} }}
        }},
        y: {{
          grid: {{ color: '#f0f0f0' }},
          ticks: {{ color: '#888', callback: v => v + '%' }},
          title: {{ display: true, text: '% of Loans', color: '#888', font: {{ size: 12 }} }},
          beginAtZero: true
        }}
      }}
    }}
  }});

  // Callout
  const cNegStart = stats['2024 Q1'].C.n > 0 ? (stats['2024 Q1'].C.negSpread / stats['2024 Q1'].C.n * 100).toFixed(0) : '0';
  const cNegEnd = (stats['2025 Q4'].C.negSpread / stats['2025 Q4'].C.n * 100).toFixed(0);
  const aNegEnd = (stats['2025 Q4'].A.negSpread / stats['2025 Q4'].A.n * 100).toFixed(0);
  document.getElementById('spreadCallout').innerHTML =
    '<strong>Solid lines = % with negative spread. Dashed lines = delinquency rate.</strong> ' +
    'Tier C consistently has the highest share of negative-spread loans (' + cNegEnd + '% in Q4 2025) and the highest delinquency. ' +
    'Tier A negative spread share: ' + aNegEnd + '% in Q4 2025. ' +
    'The correlation between weak savings and delinquency is visible across all tiers.';
}})();
</script>
</body>
</html>"""

with open("exec_credit_mix.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Done. exec_credit_mix.html created.")
