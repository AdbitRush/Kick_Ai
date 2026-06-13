#!/usr/bin/env python3
"""Simple CLI to check proxy health and stats."""
import urllib.request, json, sys, os

LEDGER = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')

def check_proxy():
    try:
        req = urllib.request.Request("http://127.0.0.1:5555/v1/messages",
            data=b'{"model":"health","messages":[{"role":"user","content":"ping"}]}',
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5)
        return "✅ Proxy alive"
    except Exception as e:
        return f"❌ Proxy down: {e}"

def summary():
    lines = []
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            lines = [json.loads(l) for l in f if l.strip()]
    total = sum(l.get('cost_usd', 0) for l in lines)
    ms = sum(l.get('thinking_ms', 0) for l in lines)
    return f"{len(lines)} queries | {ms/1000:.1f}s thinking | ${total:.6f} cost"

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd in ('proxy', 'all'):
        print(check_proxy())
    if cmd in ('stats', 'all'):
        print(summary())