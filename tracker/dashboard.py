#!/usr/bin/env python3
"""
Kickbacks Dashboard — real-time financial overview
Reads the JSONL ledger and displays profit/loss analysis.
"""
import json, os, sys
from datetime import datetime

LEDGER = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')


def fmt_usd(n: float) -> str:
    return f"${n:.6f}" if abs(n) < 1 else f"${n:.2f}"


def main():
    lines = []
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            lines = [json.loads(l) for l in f if l.strip()]

    if not lines:
        print("📭 No data yet. Proxy has not processed any queries.")
        return

    # Aggregates
    n = len(lines)
    total_cost = sum(l.get('cost_usd', 0) for l in lines)
    total_ms = sum(l.get('thinking_ms', 0) for l in lines)
    total_input = sum(l.get('input_tokens', 0) for l in lines)
    total_output = sum(l.get('output_tokens', 0) for l in lines)
    free_count = sum(1 for l in lines if l.get('free'))
    paid_count = n - free_count

    # Revenue estimation
    # Each 5-second impression block at $5 CPM → $0.005 per impression
    # 50% revenue split → $0.0025 per impression for user
    impressions = total_ms / 5000.0
    est_revenue = impressions * 0.005        # Gross ad revenue generated
    est_earnings = impressions * 0.0025      # Your 50% share
    margin = ((est_earnings - total_cost) / est_earnings * 100) if est_earnings > 0 else 0

    # Per-model breakdown
    models = {}
    for l in lines:
        m = l.get('model_actual', 'unknown')
        models.setdefault(m, {'q': 0, 'ms': 0, 'cost': 0.0})
        models[m]['q'] += 1
        models[m]['ms'] += l.get('thinking_ms', 0)
        models[m]['cost'] += l.get('cost_usd', 0)

    # Time range
    first_ts = lines[0].get('ts', '')
    last_ts = lines[-1].get('ts', '')

    # ── Render ─────────────────────────────────────────────
    print(f"\n{'═'*50}")
    print(f"  🏦  Kickbacks Arbitrage Dashboard")
    print(f"{'═'*50}")
    print(f"  📊 Queries:       {n}")
    print(f"     ↳ Free models: {free_count} ({free_count/n*100:.0f}%)")
    print(f"     ↳ Paid models: {paid_count} ({paid_count/n*100:.0f}%)")
    print(f"")
    print(f"  ⏱  Thinking:     {total_ms/1000:.1f}s total ({total_ms/n/1000:.1f}s avg)")
    print(f"     ↳ Ad impressions: {impressions:.0f} (each = 5s)")
    print(f"")
    print(f"  💰 Revenue (est.):")
    print(f"     ↳ Gross:    {fmt_usd(est_revenue)}  (advertiser spend)")
    print(f"     ↳ Your 50%: {fmt_usd(est_earnings)}")
    print(f"")
    print(f"  🪙  Cost:")
    print(f"     ↳ Total:    {fmt_usd(total_cost)}")
    print(f"     ↳ Avg/query:{fmt_usd(total_cost/n)}")
    print(f"")
    print(f"  📈 Arbitrage Margin: {margin:.0f}%")
    print(f"")
    print(f"  📝 Tokens:      {total_input:,} in + {total_output:,} out")
    print(f"  📅 Period:      {first_ts[:19]} → {last_ts[:19]}")
    print()

    if models:
        print(f"  {'─'*50}")
        print(f"  Models used (by thinking time):")
        for m, d in sorted(models.items(), key=lambda x: -x[1]['ms']):
            tag = "🆓" if d['cost'] == 0 else "💵"
            pct = d['q'] / n * 100
            print(f"    {tag} {m[:44]:44s} {d['q']:3d}× ({pct:3.0f}%)  {d['ms']/1000:7.1f}s  {fmt_usd(d['cost'])}")
        print()

    # Projection
    if n >= 3:
        elapsed_h = (datetime.fromisoformat(last_ts) - datetime.fromisoformat(first_ts)).total_seconds() / 3600
        rate = n / elapsed_h if elapsed_h > 0 else 0
        projected_daily = rate * 24
        daily_rev = projected_daily * (total_ms / n / 1000 / 5 * 0.0025)
        print(f"  📊 Projection (at current rate):")
        print(f"     ↳ Queries/day: {projected_daily:.0f}")
        print(f"     ↳ Est. daily earnings: {fmt_usd(daily_rev)}")
        print(f"     ↳ Est. monthly: {fmt_usd(daily_rev * 30)}")
        print()


if __name__ == '__main__':
    main()