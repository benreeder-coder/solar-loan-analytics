"""
Chart generator for the solar loan conversational analytics interface.

Takes a chart_spec dict from QueryResult and produces a self-contained HTML snippet
with a <canvas> element and a <script type="text/chart-init"> block for Chart.js.
"""

import uuid

# ---------------------------------------------------------------------------
# Theme definitions (extracted from existing dashboards)
# ---------------------------------------------------------------------------

THEMES = {
    'detailed': {
        'bg': '#0f1117',
        'card_bg': '#161b22',
        'card_border': '#30363d',
        'text': '#e1e4e8',
        'text_secondary': '#8b949e',
        'grid': '#21262d',
        'tier_colors': {'A': '#3fb950', 'B': '#f0883e', 'C': '#f85149'},
        'tier_bg': {'A': 'rgba(63,185,80,0.3)', 'B': 'rgba(240,136,62,0.3)', 'C': 'rgba(248,81,73,0.3)'},
        'default_color': '#8b949e',
        'default_bg': 'rgba(139,148,158,0.3)',
    },
    'exec': {
        'bg': '#ffffff',
        'card_bg': '#ffffff',
        'card_border': '#e5e7eb',
        'text': '#1a1a1a',
        'text_secondary': '#666666',
        'grid': '#f0f0f0',
        'tier_colors': {'A': '#2563eb', 'B': '#f59e0b', 'C': '#ef4444'},
        'tier_bg': {'A': 'rgba(37,99,235,0.85)', 'B': 'rgba(245,158,11,0.85)', 'C': 'rgba(239,68,68,0.85)'},
        'default_color': '#6366f1',
        'default_bg': 'rgba(99,102,241,0.7)',
    },
}

# Severity colors for DPD bands
SEVERITY_COLORS = ['#f59e0b', '#f97316', '#ef4444', '#991b1b']

# Generic palette for non-tier categorical data
PALETTE = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ef4444',
           '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#64748b']


def generate_chart_html(chart_spec: dict, chart_id: str = None) -> str:
    """Generate a self-contained HTML snippet with Chart.js visualization.

    Args:
        chart_spec: Dict with keys: type, title, labels, datasets, axes, theme, etc.
        chart_id: Unique ID for the canvas element. Auto-generated if None.

    Returns:
        HTML string with <div>, <canvas>, and <script type="text/chart-init">.
    """
    if not chart_spec:
        return ''

    chart_id = chart_id or f"chart-{uuid.uuid4().hex[:8]}"
    theme_name = chart_spec.get('theme', 'exec')
    theme = THEMES.get(theme_name, THEMES['exec'])
    chart_type = chart_spec.get('type', 'bar')

    if chart_type == 'stacked_bar':
        return _build_stacked_bar(chart_spec, chart_id, theme)
    elif chart_type == 'line':
        return _build_line(chart_spec, chart_id, theme)
    elif chart_type == 'bar':
        if chart_spec.get('grouped') or len(chart_spec.get('datasets', [])) > 1:
            # Check if it's a mixed bar+line chart (has datasets with different types)
            has_line = any(ds.get('type') == 'line' for ds in chart_spec.get('datasets', []))
            if has_line:
                return _build_mixed(chart_spec, chart_id, theme)
            return _build_grouped_bar(chart_spec, chart_id, theme)
        return _build_bar(chart_spec, chart_id, theme)
    elif chart_type == 'mixed':
        return _build_mixed(chart_spec, chart_id, theme)
    else:
        return _build_bar(chart_spec, chart_id, theme)


def _wrap_html(chart_id: str, js_code: str, title: str = '', theme: dict = None) -> str:
    """Wrap chart JS in the standard HTML container."""
    theme = theme or THEMES['exec']
    title_html = f'<div style="font-size:14px;font-weight:600;color:{theme["text"]};margin-bottom:8px;">{title}</div>' if title else ''
    return (
        f'<div style="background:{theme["card_bg"]};border:1px solid {theme["card_border"]};'
        f'border-radius:8px;padding:16px;margin:8px 0;">\n'
        f'{title_html}'
        f'<canvas id="{chart_id}" style="width:100%;max-height:320px;"></canvas>\n'
        f'<script type="text/chart-init">\n{js_code}\n</script>\n'
        f'</div>'
    )


def _dataset_color(ds: dict, index: int, theme: dict) -> tuple:
    """Determine border and background colors for a dataset."""
    tier = ds.get('tier')
    if tier and tier in theme['tier_colors']:
        return theme['tier_colors'][tier], theme['tier_bg'][tier]

    if index < len(PALETTE):
        color = PALETTE[index]
    else:
        color = theme['default_color']
    # Make bg semi-transparent
    bg = color.replace(')', ',0.7)').replace('rgb', 'rgba') if color.startswith('rgb') else color
    return color, bg


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _build_bar(spec: dict, chart_id: str, theme: dict) -> str:
    ds = spec['datasets'][0]
    labels = spec['labels']
    data = ds['data']

    # Color selection
    if spec.get('tier_colored'):
        colors = [theme['tier_bg'].get(l, theme['default_bg']) for l in labels]
        borders = [theme['tier_colors'].get(l, theme['default_color']) for l in labels]
    elif spec.get('severity_colored'):
        colors = SEVERITY_COLORS[:len(data)]
        borders = SEVERITY_COLORS[:len(data)]
    else:
        colors = [theme['default_bg']] * len(data)
        borders = [theme['default_color']] * len(data)

    axes = spec.get('axes', {})
    y_config = axes.get('y', {})
    suffix = y_config.get('suffix', '')

    js = f"""(function() {{
  const ctx = document.getElementById('{chart_id}').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels},
      datasets: [{{
        label: '{ds.get("label", "")}',
        data: {data},
        backgroundColor: {colors},
        borderColor: {borders},
        borderWidth: 1,
        borderRadius: 4,
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{ return ctx.parsed.y + '{suffix}'; }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ color: '{theme["text_secondary"]}', font: {{ size: 11 }} }},
          grid: {{ display: false }},
        }},
        y: {{
          ticks: {{
            color: '{theme["text_secondary"]}',
            font: {{ size: 11 }},
            callback: function(v) {{ return v + '{suffix}'; }}
          }},
          grid: {{ color: '{theme["grid"]}' }},
          title: {{ display: true, text: '{y_config.get("label", "")}', color: '{theme["text_secondary"]}' }},
        }}
      }}
    }}
  }});
}})();"""

    return _wrap_html(chart_id, js, spec.get('title', ''), theme)


def _build_grouped_bar(spec: dict, chart_id: str, theme: dict) -> str:
    labels = spec['labels']
    datasets_js = []
    for i, ds in enumerate(spec['datasets']):
        color, bg = _dataset_color(ds, i, theme)
        datasets_js.append(
            f"{{ label: '{ds.get('label','')}', data: {ds['data']}, "
            f"backgroundColor: '{bg}', borderColor: '{color}', borderWidth: 1, borderRadius: 4 }}"
        )

    axes = spec.get('axes', {})
    y_config = axes.get('y', {})
    suffix = y_config.get('suffix', '')

    js = f"""(function() {{
  const ctx = document.getElementById('{chart_id}').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels},
      datasets: [{', '.join(datasets_js)}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: true,
      plugins: {{
        legend: {{ display: true, labels: {{ color: '{theme["text"]}', font: {{ size: 11 }} }} }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{ return ctx.dataset.label + ': ' + ctx.parsed.y + '{suffix}'; }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ color: '{theme["text_secondary"]}', font: {{ size: 11 }} }},
          grid: {{ display: false }},
        }},
        y: {{
          ticks: {{
            color: '{theme["text_secondary"]}',
            font: {{ size: 11 }},
            callback: function(v) {{ return v + '{suffix}'; }}
          }},
          grid: {{ color: '{theme["grid"]}' }},
          title: {{ display: true, text: '{y_config.get("label", "")}', color: '{theme["text_secondary"]}' }},
        }}
      }}
    }}
  }});
}})();"""

    return _wrap_html(chart_id, js, spec.get('title', ''), theme)


def _build_line(spec: dict, chart_id: str, theme: dict) -> str:
    labels = spec['labels']
    datasets_js = []
    line_colors = [theme['default_color'], '#ef4444', '#10b981', '#f59e0b']

    for i, ds in enumerate(spec['datasets']):
        tier = ds.get('tier')
        if tier and tier in theme['tier_colors']:
            color = theme['tier_colors'][tier]
        elif i < len(line_colors):
            color = line_colors[i]
        else:
            color = theme['default_color']

        style = ds.get('style', 'solid')
        dash = '[6, 3]' if style == 'dashed' else '[]'

        datasets_js.append(
            f"{{ label: '{ds.get('label','')}', data: {ds['data']}, "
            f"borderColor: '{color}', backgroundColor: '{color}', "
            f"borderDash: {dash}, borderWidth: 2, "
            f"pointRadius: 4, pointHoverRadius: 6, tension: 0.1, fill: false }}"
        )

    axes = spec.get('axes', {})
    y_config = axes.get('y', {})
    suffix = y_config.get('suffix', '')

    js = f"""(function() {{
  const ctx = document.getElementById('{chart_id}').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: {labels},
      datasets: [{', '.join(datasets_js)}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: {str(len(spec['datasets']) > 1).lower()}, labels: {{ color: '{theme["text"]}', font: {{ size: 11 }} }} }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{ return ctx.dataset.label + ': ' + ctx.parsed.y + '{suffix}'; }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ color: '{theme["text_secondary"]}', font: {{ size: 11 }} }},
          grid: {{ display: false }},
        }},
        y: {{
          ticks: {{
            color: '{theme["text_secondary"]}',
            font: {{ size: 11 }},
            callback: function(v) {{ return v + '{suffix}'; }}
          }},
          grid: {{ color: '{theme["grid"]}' }},
          title: {{ display: true, text: '{y_config.get("label", "")}', color: '{theme["text_secondary"]}' }},
        }}
      }}
    }}
  }});
}})();"""

    return _wrap_html(chart_id, js, spec.get('title', ''), theme)


def _build_stacked_bar(spec: dict, chart_id: str, theme: dict) -> str:
    labels = spec['labels']
    datasets_js = []
    for i, ds in enumerate(spec['datasets']):
        color, bg = _dataset_color(ds, i, theme)
        datasets_js.append(
            f"{{ label: '{ds.get('label','')}', data: {ds['data']}, "
            f"backgroundColor: '{bg}', borderColor: '{color}', borderWidth: 1 }}"
        )

    axes = spec.get('axes', {})
    y_config = axes.get('y', {})
    suffix = y_config.get('suffix', '')
    y_max = y_config.get('max', '')
    y_max_js = f"max: {y_max}," if y_max else ''

    js = f"""(function() {{
  const ctx = document.getElementById('{chart_id}').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels},
      datasets: [{', '.join(datasets_js)}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: true,
      plugins: {{
        legend: {{ display: true, labels: {{ color: '{theme["text"]}', font: {{ size: 11 }} }} }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{ return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '{suffix}'; }}
          }}
        }}
      }},
      scales: {{
        x: {{
          stacked: true,
          ticks: {{ color: '{theme["text_secondary"]}', font: {{ size: 11 }} }},
          grid: {{ display: false }},
        }},
        y: {{
          stacked: true,
          {y_max_js}
          ticks: {{
            color: '{theme["text_secondary"]}',
            font: {{ size: 11 }},
            callback: function(v) {{ return v + '{suffix}'; }}
          }},
          grid: {{ color: '{theme["grid"]}' }},
          title: {{ display: true, text: '{y_config.get("label", "")}', color: '{theme["text_secondary"]}' }},
        }}
      }}
    }}
  }});
}})();"""

    return _wrap_html(chart_id, js, spec.get('title', ''), theme)


def _build_mixed(spec: dict, chart_id: str, theme: dict) -> str:
    """Mixed bar + line chart (dual axis)."""
    labels = spec['labels']
    datasets_js = []
    axes = spec.get('axes', {})

    for i, ds in enumerate(spec['datasets']):
        ds_type = ds.get('type', 'bar')
        color, bg = _dataset_color(ds, i, theme)
        y_axis = ds.get('yAxisID', 'y' if ds_type == 'line' else 'y2')

        if ds_type == 'line':
            datasets_js.append(
                f"{{ label: '{ds.get('label','')}', data: {ds['data']}, type: 'line', "
                f"borderColor: '{color}', backgroundColor: '{color}', "
                f"borderWidth: 2, pointRadius: 4, tension: 0.1, fill: false, yAxisID: '{y_axis}', order: 0 }}"
            )
        else:
            datasets_js.append(
                f"{{ label: '{ds.get('label','')}', data: {ds['data']}, type: 'bar', "
                f"backgroundColor: '{bg}', borderColor: '{color}', borderWidth: 1, "
                f"borderRadius: 4, yAxisID: '{y_axis}', order: 1 }}"
            )

    y1 = axes.get('y', {})
    y2 = axes.get('y2', {})
    y1_suffix = y1.get('suffix', '')
    y2_suffix = y2.get('suffix', '')

    js = f"""(function() {{
  const ctx = document.getElementById('{chart_id}').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels},
      datasets: [{', '.join(datasets_js)}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: true, labels: {{ color: '{theme["text"]}', font: {{ size: 11 }} }} }},
      }},
      scales: {{
        x: {{
          ticks: {{ color: '{theme["text_secondary"]}', font: {{ size: 11 }} }},
          grid: {{ display: false }},
        }},
        y: {{
          position: 'left',
          ticks: {{
            color: '{theme["text_secondary"]}',
            font: {{ size: 11 }},
            callback: function(v) {{ return v + '{y1_suffix}'; }}
          }},
          grid: {{ color: '{theme["grid"]}' }},
          title: {{ display: true, text: '{y1.get("label", "")}', color: '{theme["text_secondary"]}' }},
        }},
        y2: {{
          position: 'right',
          ticks: {{
            color: '{theme["text_secondary"]}',
            font: {{ size: 11 }},
            callback: function(v) {{ return v + '{y2_suffix}'; }}
          }},
          grid: {{ display: false }},
          title: {{ display: true, text: '{y2.get("label", "")}', color: '{theme["text_secondary"]}' }},
        }}
      }}
    }}
  }});
}})();"""

    return _wrap_html(chart_id, js, spec.get('title', ''), theme)
