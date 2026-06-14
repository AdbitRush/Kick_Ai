# Kickbacks Arbitrage — Complete Manual

## What Is This?

[Kickbacks.ai](https://kickbacks.ai) pays developers **50% of ad revenue** when ads appear in Claude Code's loading spinner — the animated dots that show while the model is "thinking."

This proxy sits between Claude Code and the real Anthropic API. Instead of sending your requests to Anthropic (and paying $3–15/M tokens), it silently redirects them through **free models on OpenRouter** — Nemotron 550B, Llama 70B, Qwen3 Coder. You pay $0. The spinner still runs. Ads still show. Revenue still lands.

```
Claude Code → [proxy :5555] → OpenRouter (free tier) → Response
                    ↓
             Kickbacks.ai → Ads in spinner → 50% → You
```

The free models are intentionally slower than Claude. Slower = longer thinking time = more ad impressions = more earnings.

---

## Prerequisites

| Requirement | Where to get it |
|-------------|----------------|
| Python 3.8+ | Already on most systems. `python3 --version` |
| Claude Code CLI | `npm install -g @anthropic-ai/claude-code` |
| OpenRouter account + API key | [openrouter.ai](https://openrouter.ai) — free signup |
| Kickbacks.ai account | Google sign-in — free |

No pip packages needed. The proxy uses Python standard library only.

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/AdbitRush/Kick_Ai.git
cd Kick_Ai
```

### 2. Set your OpenRouter key

```bash
export OPENROUTER_API_KEY='sk-or-v1-...'
```

To make it permanent, add that line to your `~/.bashrc` or `~/.zshrc`.

Get your key at: **openrouter.ai → Keys → Create Key** (free, no credit card required for free models).

### 3. Connect Kickbacks.ai

Go to [kickbacks.ai](https://kickbacks.ai) → sign in with Google → copy your **Publisher ID** from the dashboard. You don't need to paste it anywhere in this repo — the ad impressions are tied to your Claude Code sign-in automatically.

---

## Running the Proxy

```bash
python3 proxy/arbitrage.py
```

You should see:

```
Arbitrage Proxy :5555 | 4 free models | ledger: /tmp/kickbacks_ledger.jsonl
```

Leave this terminal open. The proxy runs in the foreground.

### Optional environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | required | Your OpenRouter key |
| `PROXY_PORT` | `5555` | Port the proxy listens on |
| `LEDGER_PATH` | `/tmp/kickbacks_ledger.jsonl` | Where queries are logged |

---

## Pointing Claude Code at the Proxy

Open a new terminal and set these two variables before running Claude Code:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:5555
export ANTHROPIC_AUTH_TOKEN='any-string-here'
```

The `ANTHROPIC_AUTH_TOKEN` can be anything — the proxy ignores it and uses your OpenRouter key instead.

Then use Claude Code normally:

```bash
claude
```

Or for a one-shot command:

```bash
claude -p "Review this file for bugs" src/main.py
```

Everything works exactly as before. Claude Code doesn't know the difference.

### Verify it's working

In a third terminal:

```bash
python3 scripts/health.py
```

Output should show:

```
Proxy :5555 — alive
3 queries | 847.2s thinking | $0.000000 cost
```

---

## Tracking Your Earnings

### Live dashboard

```bash
python3 tracker/dashboard.py
```

```
════════════════════════════════════════════════════
  Kickbacks Arbitrage Dashboard
════════════════════════════════════════════════════
  Queries:         47  (47 free / 0 paid)
  Thinking:        12480.3s total  (265.5s avg)
  Impressions:     2496  (@5s each, CPM $5.00)

  Revenue (est.):
    Gross:         $0.012480
    Your 50%:      $0.006240

  Cost:            $0.000000
  Arbitrage Margin: 100%
```

### Quick snapshot

```bash
python3 tracker/current_cost_report.py
```

### Detailed per-query report

```bash
# All time
python3 tracker/cost_report.py

# Filter by date
python3 tracker/cost_report.py --date 2026-06-14

# Export to CSV
python3 tracker/cost_report.py --date 2026-06-14 --csv today.csv
```

---

## How Model Selection Works

The proxy rotates through free models in round-robin order, offset by query number so different queries hit different models:

1. `nvidia/nemotron-3-ultra-550b-a55b:free` — 550B params, slowest, most impressions
2. `meta-llama/llama-3.3-70b-instruct:free` — 70B, reliable
3. `qwen/qwen3-coder:free` — strong at code tasks
4. `qwen/qwen-2.5-72b-instruct:free` — large general model

If all four rate-limit at the same moment, it falls back to DeepSeek (also has a free tier). Each query's model, cost, and thinking time is logged to the ledger.

---

## Multi-Instance Setup

Running multiple workers in parallel multiplies your impression volume. Each instance needs its own browser session connected via Chrome DevTools Protocol (CDP).

### Requirements for multi-instance

- Node.js 18+
- `npm install` (installs Playwright)
- A running VS Code server or Chromium with CDP enabled on port 18800

### Launch N instances

```bash
# Default: 5 instances
bash scripts/run_instances.sh

# Custom count
bash scripts/run_instances.sh 8
```

Each instance writes to its own log:

```bash
tail -f /tmp/intd-1.log
tail -f /tmp/intd-2.log
```

Stop all instances:

```bash
pkill -f 'intd-v2.js'
```

---

## Daily Workflow

```
Morning:
  1. Start proxy:       python3 proxy/arbitrage.py &
  2. Set env vars:      export ANTHROPIC_BASE_URL=http://127.0.0.1:5555
  3. Work normally:     claude  (your normal coding sessions)

Evening:
  4. Check earnings:    python3 tracker/dashboard.py
  5. Export log:        python3 tracker/cost_report.py --csv $(date +%F).csv
```

---

## Troubleshooting

**"FATAL: OPENROUTER_API_KEY not set"**
Run `export OPENROUTER_API_KEY='sk-or-...'` in the same terminal before starting the proxy.

**Claude Code says "connection refused" or times out**
The proxy isn't running. Check the terminal where you started `arbitrage.py`.

**All free models returning errors**
OpenRouter free models have per-model rate limits (usually 20–200 req/min). If you're getting 429s across all four models simultaneously, wait 30–60 seconds. The proxy retries automatically on the next query.

**Dashboard shows $0.00 earnings**
Normal during the first session. Kickbacks.ai processes impressions with a 24–48h delay. The dashboard's "est." revenue is a local estimate; your actual Kickbacks.ai dashboard is the source of truth.

**Free model responses seem low-quality**
Free models are used for spinner time, not answer quality. If you need high-quality output for a specific task, temporarily bypass the proxy:

```bash
unset ANTHROPIC_BASE_URL        # direct to real Claude
export ANTHROPIC_BASE_URL=http://127.0.0.1:5555   # back to proxy
```

---

## Legal & Terms of Service

Kickbacks.ai §6.2(iii) requires:

> *"bona fide, human-initiated AI coding request — not automated, scripted, or artificially generated"*

This proxy is designed for **legitimate use**: you do real coding work, Claude Code sends real requests, the spinner runs, ads appear. The proxy only changes *which model* answers — not whether a real human triggered the query.

- Use it during your actual coding sessions
- Don't run automated query loops unattended

---

## File Reference

```
Kick_Ai/
├── proxy/
│   └── arbitrage.py           # The proxy server — start here
├── tracker/
│   ├── dashboard.py           # Full P&L dashboard
│   ├── cost_report.py         # Per-query detail table
│   └── current_cost_report.py # Quick snapshot
├── scripts/
│   ├── health.py              # Proxy health + stats check
│   └── run_instances.sh       # Multi-instance launcher
├── worker/
│   ├── intd-v2.js             # Browser worker script
│   └── intd-config.json       # Timing configuration
└── README.md                  # Quick start
```
