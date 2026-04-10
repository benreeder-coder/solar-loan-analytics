"""Build a single HTML dashboard with embedded loan data and Chart.js visualizations."""

import csv
import json

# Load and transform data
data = list(csv.DictReader(open("solar_loans.csv")))
loans = []
for r in data:
    loans.append({
        "s": round(float(r["cents_per_watt_of_utility_electricity"]) - float(r["cents_per_watt_of_solar_electricity"]), 2),
        "p": round(float(r["monthly_payment"]), 2),
        "r": round(float(r["interest_rate"]), 2),
        "t": int(r["loan_term_months"]),
        "a": round(float(r["loan_amount"]), 2),
        "c": r["credit_tier"],
        "d": 1 if r["is_delinquent"] == "TRUE" else 0,
        "dpd": int(r["days_past_due"]),
    })

json_data = json.dumps(loans, separators=(",", ":"))

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Solar Loan Delinquency Analysis</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e1e4e8; padding: 24px; }}
  h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 6px; color: #fff; }}
  .subtitle {{ font-size: 13px; color: #8b949e; margin-bottom: 28px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 1400px; margin: 0 auto; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }}
  .card h2 {{ font-size: 14px; font-weight: 600; color: #c9d1d9; margin-bottom: 4px; }}
  .card .desc {{ font-size: 11px; color: #8b949e; margin-bottom: 16px; }}
  .card canvas {{ width: 100% !important; }}
  .full-width {{ grid-column: 1 / -1; }}
  .legend-row {{ display: flex; gap: 24px; justify-content: center; margin-bottom: 20px; font-size: 12px; flex-wrap: wrap; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .legend-bar {{ width: 14px; height: 10px; border-radius: 2px; opacity: 0.35; }}
  .insight {{ background: #1c2128; border-left: 3px solid #f0883e; padding: 12px 16px; margin-top: 12px; font-size: 12px; color: #c9d1d9; border-radius: 0 6px 6px 0; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; max-width: 1400px; margin: 0 auto 20px; }}
  .stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center; }}
  .stat-val {{ font-size: 28px; font-weight: 700; color: #fff; }}
  .stat-label {{ font-size: 11px; color: #8b949e; margin-top: 4px; }}
  .stat-val.red {{ color: #f85149; }}
  .stat-val.green {{ color: #3fb950; }}
  .stat-val.amber {{ color: #f0883e; }}
</style>
</head>
<body>

<div style="max-width:1400px;margin:0 auto;">
  <h1>Solar Loan Delinquency: Risk Factor Analysis</h1>
  <p class="subtitle">2,450 loans, Jan 2024 &ndash; Dec 2025 &middot; Bars = loan volume (right axis) &middot; Lines = delinquency rate (left axis) &middot; Segmented by credit tier</p>

  <div class="legend-row">
    <div class="legend-item"><div class="legend-dot" style="background:#3fb950"></div> Tier A Rate</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f0883e"></div> Tier B Rate</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f85149"></div> Tier C Rate</div>
    <div class="legend-item"><div class="legend-dot" style="background:#8b949e"></div> All Tiers Rate</div>
    <div class="legend-item"><div class="legend-bar" style="background:#3fb950"></div> Tier A Vol</div>
    <div class="legend-item"><div class="legend-bar" style="background:#f0883e"></div> Tier B Vol</div>
    <div class="legend-item"><div class="legend-bar" style="background:#f85149"></div> Tier C Vol</div>
  </div>

  <div class="summary-grid" id="summaryGrid"></div>
</div>

<div class="grid">
  <div class="card full-width">
    <h2>Delinquency Rate by Utility-Solar Savings Spread</h2>
    <p class="desc">Spread = utility cost &minus; solar cost (cents/watt). Negative = solar costs more than utility. Bars = loan count per tier, lines = delinquency rate.</p>
    <canvas id="spreadChart" height="100"></canvas>
    <div class="insight" id="spreadInsight"></div>
  </div>

  <div class="card">
    <h2>Delinquency Rate by Monthly Payment</h2>
    <p class="desc">Payment bands in USD. Bars = volume, lines = delinquency rate.</p>
    <canvas id="paymentChart" height="160"></canvas>
    <div class="insight" id="paymentInsight"></div>
  </div>

  <div class="card">
    <h2>Delinquency Rate by Interest Rate</h2>
    <p class="desc">Annual interest rate bands. Bars = volume, lines = delinquency rate.</p>
    <canvas id="rateChart" height="160"></canvas>
    <div class="insight" id="rateInsight"></div>
  </div>

  <div class="card">
    <h2>Delinquency Rate by Loan Term</h2>
    <p class="desc">Term in months. Bars = volume, lines = delinquency rate.</p>
    <canvas id="termChart" height="160"></canvas>
    <div class="insight" id="termInsight"></div>
  </div>

  <div class="card">
    <h2>Delinquency Rate by Loan Amount</h2>
    <p class="desc">Loan principal bands in USD. Bars = volume, lines = delinquency rate.</p>
    <canvas id="amountChart" height="160"></canvas>
    <div class="insight" id="amountInsight"></div>
  </div>

  <div class="card full-width">
    <h2>Heatmap: Savings Spread vs Credit Tier &mdash; Loan Volume and Delinquency</h2>
    <p class="desc">Bubble size = loan count, color intensity = delinquency rate. Hover for exact counts.</p>
    <canvas id="heatmapChart" height="80"></canvas>
  </div>
</div>

<script>
const DATA = {json_data};

const COLORS = {{
  A: '#3fb950', B: '#f0883e', C: '#f85149', All: '#8b949e'
}};
const COLORS_BG = {{
  A: 'rgba(63,185,80,0.3)', B: 'rgba(240,136,62,0.3)', C: 'rgba(248,81,73,0.3)', All: 'rgba(139,148,158,0.15)'
}};

// --- Utility functions ---
function bandData(field, bands, labelFn) {{
  const tiers = ['A','B','C','All'];
  const result = {{}};
  tiers.forEach(t => {{
    result[t] = bands.map(([lo, hi]) => {{
      const subset = DATA.filter(d => {{
        const v = d[field];
        const tierMatch = t === 'All' || d.c === t;
        return tierMatch && v >= lo && v < hi;
      }});
      const n = subset.length;
      const delinq = subset.filter(d => d.d === 1).length;
      return {{ n, delinq, rate: n > 0 ? (delinq / n * 100) : 0 }};
    }});
  }});
  return {{ labels: bands.map(([lo, hi]) => labelFn(lo, hi)), tiers: result }};
}}

function makeBands(min, max, step) {{
  const bands = [];
  for (let v = min; v < max; v += step) {{
    bands.push([v, v + step]);
  }}
  return bands;
}}

function createChart(canvasId, bandResult) {{
  const ctx = document.getElementById(canvasId).getContext('2d');
  const datasets = [];

  // Volume bars for A, B, C (stacked)
  ['A','B','C'].forEach(t => {{
    const d = bandResult.tiers[t];
    datasets.push({{
      label: 'Tier ' + t + ' Vol',
      data: d.map(x => x.n),
      type: 'bar',
      backgroundColor: COLORS_BG[t],
      borderColor: COLORS[t],
      borderWidth: 1,
      yAxisID: 'yVol',
      stack: 'volume',
      order: 2,
      barPercentage: 0.85,
      categoryPercentage: 0.8
    }});
  }});

  // Rate lines for A, B, C, All
  ['A','B','C','All'].forEach(t => {{
    const d = bandResult.tiers[t];
    datasets.push({{
      label: t === 'All' ? 'All Tiers' : 'Tier ' + t,
      data: d.map(x => x.rate),
      type: 'line',
      borderColor: COLORS[t],
      backgroundColor: 'transparent',
      borderWidth: t === 'All' ? 3 : 2,
      borderDash: t === 'All' ? [6, 3] : [],
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.3,
      fill: false,
      yAxisID: 'yRate',
      order: 1
    }});
  }});

  new Chart(ctx, {{
    type: 'bar',
    data: {{ labels: bandResult.labels, datasets }},
    options: {{
      responsive: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: function(ctx2) {{
              const ds = ctx2.dataset;
              if (ds.type === 'bar' || (!ds.type && ctx2.chart.config.type === 'bar')) {{
                // Volume bar
                const tier = ds.label.replace(' Vol','');
                const tierKey = tier.replace('Tier ','');
                const info = bandResult.tiers[tierKey][ctx2.dataIndex];
                return ds.label + ': ' + info.n + ' loans (' + info.delinq + ' delinquent)';
              }} else {{
                // Rate line
                const tierKey = ds.label.replace('Tier ','').replace('All Tiers','All');
                const info = bandResult.tiers[tierKey][ctx2.dataIndex];
                return ds.label + ': ' + info.rate.toFixed(1) + '% (' + info.delinq + '/' + info.n + ')';
              }}
            }}
          }}
        }},
        legend: {{ display: false }}
      }},
      scales: {{
        x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', font: {{ size: 10 }}, maxRotation: 45 }} }},
        yRate: {{
          position: 'left',
          grid: {{ color: '#21262d' }},
          ticks: {{ color: '#8b949e', callback: v => v + '%' }},
          title: {{ display: true, text: 'Delinquency Rate (%)', color: '#8b949e' }},
          beginAtZero: true
        }},
        yVol: {{
          position: 'right',
          grid: {{ drawOnChartArea: false }},
          ticks: {{ color: '#555' }},
          title: {{ display: true, text: 'Loan Count', color: '#555' }},
          beginAtZero: true
        }}
      }}
    }}
  }});
  return bandResult;
}}

// --- Build charts ---

// 1. Savings spread
const spreadBands = makeBands(-8, 24, 2);
const spreadData = bandData('s', spreadBands, (lo, hi) => lo + ' to ' + hi);
createChart('spreadChart', spreadData);

(function() {{
  const negLoans = DATA.filter(d => d.s < 0);
  const negDelinq = negLoans.filter(d => d.d === 1).length;
  const negRate = (negDelinq / negLoans.length * 100).toFixed(1);
  const posLoans = DATA.filter(d => d.s >= 0);
  const posDelinq = posLoans.filter(d => d.d === 1).length;
  const posRate = (posDelinq / posLoans.length * 100).toFixed(1);
  const negC = negLoans.filter(d => d.c === 'C');
  const negCrate = negC.length > 0 ? (negC.filter(d => d.d === 1).length / negC.length * 100).toFixed(1) : '0';
  document.getElementById('spreadInsight').innerHTML =
    '<strong>Key:</strong> Negative spread (solar > utility): ' + negLoans.length + ' loans, ' + negRate + '% delinquent. ' +
    'Positive spread: ' + posLoans.length + ' loans, ' + posRate + '% delinquent. ' +
    'Tier C + negative spread: ' + negC.length + ' loans, ' + negCrate + '% delinquent.';
}})();

// 2. Monthly payment
const payBands = makeBands(50, 800, 50);
const payData = bandData('p', payBands, (lo, hi) => '$' + lo + '-' + hi);
createChart('paymentChart', payData);

(function() {{
  const highPay = DATA.filter(d => d.p >= 400);
  const highDelinq = highPay.filter(d => d.d === 1).length;
  document.getElementById('paymentInsight').innerHTML =
    '<strong>Key:</strong> Payments >= $400/mo: ' + highPay.length + ' loans, ' +
    (highDelinq / highPay.length * 100).toFixed(1) + '% delinquent vs ' +
    (DATA.filter(d => d.d === 1).length / DATA.length * 100).toFixed(1) + '% overall.';
}})();

// 3. Interest rate
const rateBands = makeBands(2, 16, 1);
const rateData = bandData('r', rateBands, (lo, hi) => lo + '-' + hi + '%');
createChart('rateChart', rateData);

(function() {{
  const highRate = DATA.filter(d => d.r >= 10);
  const highDelinq = highRate.filter(d => d.d === 1).length;
  document.getElementById('rateInsight').innerHTML =
    '<strong>Key:</strong> 10%+ interest: ' + highRate.length + ' loans, ' +
    (highDelinq / highRate.length * 100).toFixed(1) + '% delinquent. ' +
    'Tier C at 10%+: ' + highRate.filter(d => d.c === 'C').length + ' loans, ' +
    (highRate.filter(d => d.c === 'C' && d.d === 1).length / highRate.filter(d => d.c === 'C').length * 100).toFixed(1) + '%.';
}})();

// 4. Loan term (discrete -- uses same createChart with synthetic bands)
const termVals = [120, 180, 240, 300];
const termBandResult = {{
  labels: termVals.map(v => v + ' mo (' + (v/12).toFixed(0) + 'yr)'),
  tiers: {{}}
}};
['A','B','C','All'].forEach(t => {{
  termBandResult.tiers[t] = termVals.map(term => {{
    const subset = DATA.filter(d => d.t === term && (t === 'All' || d.c === t));
    const n = subset.length;
    const delinq = subset.filter(d => d.d === 1).length;
    return {{ n, delinq, rate: n > 0 ? (delinq / n * 100) : 0 }};
  }});
}});
createChart('termChart', termBandResult);

(function() {{
  const lines = termVals.map(term => {{
    const sub = DATA.filter(d => d.t === term);
    const rate = (sub.filter(d => d.d === 1).length / sub.length * 100).toFixed(1);
    return term + 'mo: ' + sub.length + ' loans, ' + rate + '%';
  }});
  document.getElementById('termInsight').innerHTML = '<strong>Key:</strong> ' + lines.join(' | ');
}})();

// 5. Loan amount
const amtBands = makeBands(10000, 80000, 5000);
const amtData = bandData('a', amtBands, (lo, hi) => '$' + (lo/1000).toFixed(0) + 'k-' + (hi/1000).toFixed(0) + 'k');
createChart('amountChart', amtData);

(function() {{
  const under25 = DATA.filter(d => d.a < 25000);
  const over50 = DATA.filter(d => d.a >= 50000);
  document.getElementById('amountInsight').innerHTML =
    '<strong>Key:</strong> Under $25k: ' + under25.length + ' loans, ' +
    (under25.filter(d => d.d === 1).length / under25.length * 100).toFixed(1) + '% delinquent. ' +
    'Over $50k: ' + over50.length + ' loans, ' +
    (over50.filter(d => d.d === 1).length / over50.length * 100).toFixed(1) + '% delinquent.';
}})();

// 6. Bubble heatmap: spread band x tier
(function() {{
  const ctx = document.getElementById('heatmapChart').getContext('2d');
  const sBands = makeBands(-8, 24, 4);
  const tiers = ['A','B','C'];
  const datasets = [];
  tiers.forEach((t, ti) => {{
    const points = sBands.map(([lo, hi], bi) => {{
      const subset = DATA.filter(d => d.c === t && d.s >= lo && d.s < hi);
      const n = subset.length;
      const delinq = subset.filter(d => d.d === 1).length;
      const rate = n > 0 ? delinq / n * 100 : 0;
      return {{ x: bi, y: ti, r: Math.max(Math.sqrt(n) * 1.8, 3), n, delinq, rate }};
    }});
    const alpha = t === 'C' ? 0.8 : t === 'B' ? 0.6 : 0.4;
    datasets.push({{
      label: 'Tier ' + t,
      data: points,
      backgroundColor: points.map(p => {{
        if (p.n === 0) return 'rgba(100,100,100,0.2)';
        const intensity = Math.min(p.rate / 40, 1);
        const r = Math.round(63 + (248 - 63) * intensity);
        const g = Math.round(185 - 140 * intensity);
        const b = Math.round(80 - 7 * intensity);
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
      }}),
      borderColor: COLORS[t],
      borderWidth: 1.5
    }});
  }});

  new Chart(ctx, {{
    type: 'bubble',
    data: {{ datasets }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: function(ctx2) {{
              const p = ctx2.raw;
              return ctx2.dataset.label + ': ' + p.rate.toFixed(1) + '% (' + p.delinq + '/' + p.n + ' loans)';
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          type: 'linear',
          grid: {{ color: '#21262d' }},
          ticks: {{ color: '#8b949e', callback: function(v) {{ const lo = -8 + v * 4; return lo + ' to ' + (lo + 4); }} }},
          title: {{ display: true, text: 'Savings Spread Band (cents/watt)', color: '#8b949e' }}
        }},
        y: {{
          type: 'linear', min: -0.5, max: 2.5,
          grid: {{ color: '#21262d' }},
          ticks: {{ color: '#8b949e', stepSize: 1, callback: function(v) {{ return ['Tier A','Tier B','Tier C'][v] || ''; }} }},
          title: {{ display: true, text: 'Credit Tier', color: '#8b949e' }}
        }}
      }}
    }}
  }});
}})();

// Summary stats
(function() {{
  const total = DATA.length;
  const delinq = DATA.filter(d => d.d === 1).length;
  const overallRate = (delinq / total * 100).toFixed(1);
  const tierC = DATA.filter(d => d.c === 'C');
  const tierCrate = (tierC.filter(d => d.d === 1).length / tierC.length * 100).toFixed(1);
  const negSpread = DATA.filter(d => d.s < 0);
  const negRate = (negSpread.filter(d => d.d === 1).length / negSpread.length * 100).toFixed(1);
  const negC = negSpread.filter(d => d.c === 'C');
  const negCrate = negC.length > 0 ? (negC.filter(d => d.d === 1).length / negC.length * 100).toFixed(1) : '0.0';

  document.getElementById('summaryGrid').innerHTML =
    '<div class="stat-card"><div class="stat-val">' + overallRate + '%</div><div class="stat-label">Overall Delinquency (' + delinq + '/' + total + ')</div></div>' +
    '<div class="stat-card"><div class="stat-val red">' + tierCrate + '%</div><div class="stat-label">Tier C Delinquency (' + tierC.filter(d => d.d === 1).length + '/' + tierC.length + ')</div></div>' +
    '<div class="stat-card"><div class="stat-val amber">' + negRate + '%</div><div class="stat-label">Negative Spread Delinq (' + negSpread.length + ' loans)</div></div>' +
    '<div class="stat-card"><div class="stat-val red">' + negCrate + '%</div><div class="stat-label">Tier C + Neg Spread (' + negC.length + ' loans)</div></div>';
}})();
</script>
</body>
</html>"""

with open("delinquency_dashboard.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Done. delinquency_dashboard.html created.")
