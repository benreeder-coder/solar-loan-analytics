"""
Solar Loan Portfolio: Conversational Analytics Interface

Run: python app.py [--port 5000] [--llm]
"""

import argparse
import json
import os
import sqlite3

import pandas as pd
import yaml
from flask import Flask, jsonify, request, send_file, session

from chart_generator import generate_chart_html
from query_engine import QueryEngine

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Load data
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(DATA_DIR, 'solar_loans.csv'))

# Load knowledge base
with open(os.path.join(DATA_DIR, 'knowledge_base.yaml'), 'r') as f:
    kb = yaml.safe_load(f)

# Initialize query engine
engine = QueryEngine(df, kb)

# Load into SQLite (for transparency / future LLM mode)
# Use /tmp on Vercel (read-only filesystem outside /tmp)
try:
    import tempfile
    db_path = os.path.join(tempfile.gettempdir(), 'portfolio.db')
    conn = sqlite3.connect(db_path, check_same_thread=False)
    engine.df.to_sql('loans', conn, if_exists='replace', index=False)
except Exception:
    conn = None  # SQLite optional, pandas handles all queries

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return INDEX_HTML


@app.route('/api/query', methods=['POST'])
def query():
    body = request.get_json(silent=True) or {}
    question = body.get('question', '').strip()
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    ctx = session.get('conversation_context', {})
    result = engine.query(question, session_context=ctx)

    chart_html = ''
    if result.chart_spec:
        chart_html = generate_chart_html(result.chart_spec)

    session['conversation_context'] = result.context_update

    return jsonify({
        'answer': result.answer_text,
        'table': result.data,
        'chart_html': chart_html,
        'calculation': result.calculation,
        'caveats': result.caveats,
        'followups': result.suggested_followups,
    })


@app.route('/api/reset', methods=['POST'])
def reset():
    session.pop('conversation_context', None)
    return jsonify({'ok': True})


@app.route('/dashboards/delinquency')
def dashboard_delinquency():
    return send_file(os.path.join(DATA_DIR, 'delinquency_dashboard.html'))


@app.route('/dashboards/exec')
def dashboard_exec():
    return send_file(os.path.join(DATA_DIR, 'exec_credit_mix.html'))


# ---------------------------------------------------------------------------
# Chat UI (single-page, inline HTML/CSS/JS)
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Solar Loan Portfolio Analytics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #f8f9fa;
    --surface: #ffffff;
    --border: #e5e7eb;
    --text: #1a1a1a;
    --text-secondary: #6b7280;
    --accent: #2563eb;
    --accent-light: #eff6ff;
    --user-bg: #2563eb;
    --user-text: #ffffff;
    --system-bg: #ffffff;
    --caveat-bg: #fffbeb;
    --caveat-border: #f59e0b;
    --code-bg: #f3f4f6;
    --radius: 12px;
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* Header */
  .header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .header h1 { font-size: 16px; font-weight: 600; color: var(--text); }
  .header-badge {
    font-size: 11px;
    color: var(--accent);
    background: var(--accent-light);
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
  }
  .header-links { display: flex; gap: 12px; }
  .header-links a {
    font-size: 12px;
    color: var(--text-secondary);
    text-decoration: none;
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid var(--border);
    transition: all 0.15s;
  }
  .header-links a:hover {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-light);
  }

  /* Chat area */
  .chat-container {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 860px;
    width: 100%;
    margin: 0 auto;
  }

  /* Messages */
  .msg { display: flex; flex-direction: column; max-width: 85%; animation: fadeIn 0.2s ease; }
  .msg.user { align-self: flex-end; }
  .msg.system { align-self: flex-start; }

  .msg-bubble {
    padding: 12px 16px;
    border-radius: var(--radius);
    line-height: 1.55;
    font-size: 14px;
    box-shadow: var(--shadow);
  }
  .msg.user .msg-bubble {
    background: var(--user-bg);
    color: var(--user-text);
    border-bottom-right-radius: 4px;
  }
  .msg.system .msg-bubble {
    background: var(--system-bg);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
  }

  .msg-bubble p { margin-bottom: 8px; }
  .msg-bubble p:last-child { margin-bottom: 0; }

  /* Collapsible sections */
  details {
    margin-top: 10px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }
  details summary {
    font-size: 12px;
    color: var(--text-secondary);
    cursor: pointer;
    user-select: none;
    font-weight: 500;
  }
  details summary:hover { color: var(--accent); }

  /* Data tables */
  .data-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 12px;
  }
  .data-table th {
    text-align: left;
    padding: 6px 10px;
    border-bottom: 2px solid var(--border);
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .data-table td {
    padding: 5px 10px;
    border-bottom: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
  }
  .data-table tr:last-child td { border-bottom: none; }

  /* Caveats */
  .caveat {
    margin-top: 10px;
    padding: 8px 12px;
    background: var(--caveat-bg);
    border-left: 3px solid var(--caveat-border);
    border-radius: 0 6px 6px 0;
    font-size: 12px;
    color: #92400e;
    line-height: 1.45;
  }

  /* Calculation code */
  .calc-code {
    margin-top: 8px;
    padding: 10px 12px;
    background: var(--code-bg);
    border-radius: 6px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    color: var(--text);
    white-space: pre-wrap;
    line-height: 1.5;
  }

  /* Follow-up chips */
  .followups {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }
  .followup-chip {
    font-size: 12px;
    color: var(--accent);
    background: var(--accent-light);
    border: 1px solid rgba(37,99,235,0.2);
    padding: 4px 12px;
    border-radius: 16px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .followup-chip:hover {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }

  /* Chart container */
  .chart-container { margin-top: 10px; }
  .chart-container > div { border: none !important; }

  /* Loading indicator */
  .loading {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    background: var(--system-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    border-bottom-left-radius: 4px;
    box-shadow: var(--shadow);
    font-size: 13px;
    color: var(--text-secondary);
  }
  .loading-dots { display: flex; gap: 4px; }
  .loading-dots span {
    width: 6px; height: 6px;
    background: var(--text-secondary);
    border-radius: 50%;
    animation: bounce 1.2s infinite;
  }
  .loading-dots span:nth-child(2) { animation-delay: 0.2s; }
  .loading-dots span:nth-child(3) { animation-delay: 0.4s; }

  /* Input area */
  .input-area {
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 16px 24px;
    flex-shrink: 0;
  }
  .input-row {
    max-width: 860px;
    margin: 0 auto;
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }
  .input-row textarea {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 14px;
    font-family: inherit;
    color: var(--text);
    background: var(--bg);
    resize: none;
    outline: none;
    transition: border-color 0.15s;
    min-height: 42px;
    max-height: 120px;
    line-height: 1.45;
  }
  .input-row textarea:focus { border-color: var(--accent); }
  .input-row textarea::placeholder { color: var(--text-secondary); }

  .send-btn {
    padding: 10px 20px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
    white-space: nowrap;
  }
  .send-btn:hover { background: #1d4ed8; }
  .send-btn:disabled { background: #93c5fd; cursor: not-allowed; }

  /* Welcome message */
  .welcome {
    text-align: center;
    padding: 48px 24px;
    color: var(--text-secondary);
    max-width: 480px;
    margin: auto;
  }
  .welcome h2 { font-size: 18px; color: var(--text); margin-bottom: 8px; font-weight: 600; }
  .welcome p { font-size: 13px; line-height: 1.6; margin-bottom: 16px; }
  .welcome-examples {
    display: flex;
    flex-direction: column;
    gap: 6px;
    text-align: left;
  }
  .welcome-example {
    padding: 8px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 13px;
    color: var(--text);
    cursor: pointer;
    transition: all 0.15s;
  }
  .welcome-example:hover {
    border-color: var(--accent);
    background: var(--accent-light);
  }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-6px); }
  }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>Solar Loan Portfolio Analytics</h1>
    <span class="header-badge">2,450 loans</span>
  </div>
  <div class="header-links">
    <a href="/dashboards/delinquency" target="_blank">Risk Dashboard</a>
    <a href="/dashboards/exec" target="_blank">Executive View</a>
  </div>
</div>

<div class="chat-container" id="chat">
  <div class="welcome" id="welcome">
    <h2>Ask about the portfolio</h2>
    <p>I can analyze delinquency rates, credit mix trends, installer performance, savings spreads, and more. Try one of these:</p>
    <div class="welcome-examples">
      <div class="welcome-example" onclick="askQuestion(this.textContent)">Why is delinquency rising?</div>
      <div class="welcome-example" onclick="askQuestion(this.textContent)">What's the overall delinquency rate?</div>
      <div class="welcome-example" onclick="askQuestion(this.textContent)">How has the credit mix changed over time?</div>
      <div class="welcome-example" onclick="askQuestion(this.textContent)">Which installer has the worst subprime performance?</div>
      <div class="welcome-example" onclick="askQuestion(this.textContent)">How severe are the delinquencies?</div>
    </div>
  </div>
</div>

<div class="input-area">
  <div class="input-row">
    <textarea id="input" rows="1" placeholder="Ask about the portfolio... e.g., 'What's driving the rise in delinquency?'"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"
      oninput="autoResize(this)"></textarea>
    <button class="send-btn" id="sendBtn" onclick="sendMessage()">Send</button>
  </div>
</div>

<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const welcome = document.getElementById('welcome');
let isProcessing = false;

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function askQuestion(text) {
  input.value = text;
  sendMessage();
}

function scrollToBottom() {
  requestAnimationFrame(() => { chat.scrollTop = chat.scrollHeight; });
}

function addUserMessage(text) {
  if (welcome) welcome.remove();
  const div = document.createElement('div');
  div.className = 'msg user';
  div.innerHTML = '<div class="msg-bubble">' + escapeHtml(text) + '</div>';
  chat.appendChild(div);
  scrollToBottom();
}

function addLoading() {
  const div = document.createElement('div');
  div.className = 'msg system';
  div.id = 'loading';
  div.innerHTML = '<div class="loading"><div class="loading-dots"><span></span><span></span><span></span></div> Analyzing...</div>';
  chat.appendChild(div);
  scrollToBottom();
  return div;
}

function removeLoading() {
  const el = document.getElementById('loading');
  if (el) el.remove();
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function buildTable(tableData) {
  if (!tableData || !tableData.columns || !tableData.rows || tableData.rows.length === 0) return '';
  let html = '<details><summary>View data table (' + tableData.rows.length + ' rows)</summary>';
  html += '<table class="data-table"><thead><tr>';
  tableData.columns.forEach(c => { html += '<th>' + escapeHtml(c) + '</th>'; });
  html += '</tr></thead><tbody>';
  tableData.rows.forEach(row => {
    html += '<tr>';
    row.forEach(cell => { html += '<td>' + escapeHtml(String(cell)) + '</td>'; });
    html += '</tr>';
  });
  html += '</tbody></table></details>';
  return html;
}

function addSystemMessage(data) {
  const div = document.createElement('div');
  div.className = 'msg system';

  let html = '<div class="msg-bubble">';

  // Answer text — convert newlines to paragraphs
  const paragraphs = data.answer.split('\\n\\n').filter(p => p.trim());
  paragraphs.forEach(p => {
    html += '<p>' + escapeHtml(p.trim()) + '</p>';
  });

  // Caveats
  if (data.caveats && data.caveats.length > 0) {
    data.caveats.forEach(c => {
      html += '<div class="caveat">' + escapeHtml(c) + '</div>';
    });
  }

  // Chart
  if (data.chart_html) {
    html += '<div class="chart-container">' + data.chart_html + '</div>';
  }

  // Data table
  if (data.table) {
    html += buildTable(data.table);
  }

  // Calculation
  if (data.calculation) {
    html += '<details><summary>Show calculation</summary>';
    html += '<div class="calc-code">' + escapeHtml(data.calculation) + '</div>';
    html += '</details>';
  }

  // Follow-ups
  if (data.followups && data.followups.length > 0) {
    html += '<div class="followups">';
    data.followups.forEach(f => {
      html += '<span class="followup-chip" onclick="askQuestion(this.textContent)">' + escapeHtml(f) + '</span>';
    });
    html += '</div>';
  }

  html += '</div>';
  div.innerHTML = html;
  chat.appendChild(div);

  // Activate Chart.js scripts
  const scripts = div.querySelectorAll('script[type="text/chart-init"]');
  scripts.forEach(oldScript => {
    const newScript = document.createElement('script');
    newScript.textContent = oldScript.textContent;
    requestAnimationFrame(() => {
      document.body.appendChild(newScript);
    });
  });

  scrollToBottom();
}

async function sendMessage() {
  const text = input.value.trim();
  if (!text || isProcessing) return;

  isProcessing = true;
  sendBtn.disabled = true;
  input.value = '';
  input.style.height = 'auto';

  addUserMessage(text);
  const loader = addLoading();

  try {
    const resp = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text }),
    });
    const data = await resp.json();
    removeLoading();
    addSystemMessage(data);
  } catch (err) {
    removeLoading();
    addSystemMessage({
      answer: 'Something went wrong. Please try again.',
      caveats: [],
      chart_html: '',
      table: null,
      calculation: '',
      followups: [],
    });
  }

  isProcessing = false;
  sendBtn.disabled = false;
  input.focus();
}

// Focus input on load
input.focus();
</script>

</body>
</html>
"""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Solar Loan Portfolio Analytics')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--llm', action='store_true', help='Enable Claude API mode (future)')
    args = parser.parse_args()

    if args.llm:
        print("LLM mode not yet implemented. Running in template mode.")

    print(f"Starting Solar Loan Analytics on http://localhost:{args.port}")
    print(f"Portfolio: {len(df):,} loans loaded")
    app.run(debug=True, port=args.port)
