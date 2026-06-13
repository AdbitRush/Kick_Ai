#!/usr/bin/env python3
"""
Kickbacks Arbitrage Engine
Zero-cost proxy: Claude Code → OpenRouter Free Models → Ad impressions
"""

import http.server, json, urllib.request, urllib.error, ssl
import sys, os, time, datetime, signal, atexit

OR_KEY = ***'OPENROUTER_API_KEY', '')
PORT = int(os.environ.get('PROXY_PORT', '5555'))
LEDGER = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')

# ── Free model pool ($0 cost) ──────────────────────────────
# Slower models first = more thinking time = more ad impressions
FREE_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",   # 550B — very slow → max impressions
    "nvidia/nemotron-3-super-120b-a12b:free",
    "qwen/qwen3-coder:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-120b:free",
    "openrouter/free",
]

# ── Paid fallback (when free models hit rate limits) ───────
PAID_MODEL = "deepseek/deepseek-v4-flash-20260423"  # $0.098/M input

# ── Runtime state ──────────────────────────────────────────
q = 0
total_cost = 0.0
total_thinking_ms = 0
start_time = time.time()


def append_ledger(entry: dict):
    """JSONL — one entry per query."""
    with open(LEDGER, 'a') as f:
        f.write(json.dumps(entry) + '\n')


def write_status(signal_number=None, frame=None):
    """Periodic status snapshot."""
    elapsed = time.time() - start_time
    with open('/tmp/kickbacks_status.txt', 'w') as f:
        f.write(f"""═════ Kickbacks Arbitrage ═════
Uptime:    {elapsed/3600:.1f}h
Queries:   {q}
Thinking:  {total_thinking_ms/1000:.1f}s
Cost:      ${total_cost:.6f}
Rate:      {q/elapsed*3600:.1f} queries/h
Eff. CPM:  ${total_cost/(total_thinking_ms/3600000) if total_thinking_ms > 0 else 0:.4f}
""")


atexit.register(write_status)
signal.signal(signal.SIGTERM, write_status)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Converts Anthropic Messages API → OpenAI Chat API → free models on OpenRouter."""

    # ── HTTP handlers ──────────────────────────────────────

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')

    def do_POST(self):
        global q, total_cost, total_thinking_ms

        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        try:
            msg = json.loads(body)
        except json.JSONDecodeError:
            return self._send_json(400, {"type": "error", "error": {"message": "invalid JSON"}})

        original_model = msg.get('model', 'claude-sonnet-4-20250514')
        openai_messages = self._convert_to_openai(msg)
        max_tokens = min(msg.get('max_tokens', 2048), 4096)

        start = time.time()
        result, used_model, is_free = self._try_models(openai_messages, max_tokens)
        thinking_ms = int((time.time() - start) * 1000)

        # ── Update state ───────────────────────────────────
        q += 1
        total_thinking_ms += thinking_ms

        if result and result.get('choices'):
            # Calculate cost
            cost = 0.0
            if is_free:
                cost = 0.0  # Pure arbitrage
            else:
                usage = result.get('usage', {}) or {}
                pt = int(usage.get('prompt_tokens', 0) or 0)
                ct = int(usage.get('completion_tokens', 0) or 0)
                cost = (pt / 1_000_000 * 0.098) + (ct / 1_000_000 * 0.399)
            total_cost += cost

            # Log to ledger
            usage = result.get('usage', {}) or {}
            append_ledger({
                'ts': datetime.datetime.utcnow().isoformat(),
                'q': q,
                'model_actual': used_model,
                'model_claude': original_model,
                'free': is_free,
                'input_tokens': int(usage.get('prompt_tokens', 0) or 0),
                'output_tokens': int(usage.get('completion_tokens', 0) or 0),
                'thinking_ms': thinking_ms,
                'cost_usd': round(cost, 8),
            })

            # Build Anthropic response
            anth = self._to_anthropic(result, original_model, thinking_ms)
            self._send_json(200, anth)
        else:
            err = str(result.get('error', 'all models failed'))[:200] if result else 'no response'
            self._send_json(502, {"type": "error", "error": {"message": err}})

    # ── Model routing ──────────────────────────────────────

    def _try_models(self, messages, max_tokens):
        """Try free models first, fall back to paid."""
        # Free models with round-robin start
        offset = q % max(1, len(FREE_MODELS) - 1)
        ordered = FREE_MODELS[offset:] + FREE_MODELS[:offset]

        for model in ordered:
            res = self._call_openrouter(model, messages, max_tokens)
            if res and res.get('choices'):
                return res, model, True

        # Paid fallback
        res = self._call_openrouter(PAID_MODEL, messages, max_tokens)
        if res and res.get('choices'):
            return res, PAID_MODEL, False

        return res or {"error": "all models failed"}, None, False

    def _call_openrouter(self, model: str, messages: list, max_tokens: int) -> dict:
        """POST to OpenRouter chat completions."""
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OR_KEY}",
                "HTTP-Referer": "https://kickbacks.ai",
            },
        )

        try:
            ctx = ssl.create_default_context()
            resp = urllib.request.urlopen(req, context=ctx, timeout=120)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read())
            except Exception:
                return {"error": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"error": str(e)}

    # ── Format conversion ──────────────────────────────────

    def _convert_to_openai(self, msg: dict) -> list:
        """Anthropic Messages API → OpenAI Chat format."""
        msgs = []
        system_text = None

        if 'system' in msg:
            t = msg['system']
            system_text = t if isinstance(t, str) else ' '.join(
                b.get('text', '') for b in t
                if isinstance(b, dict) and b.get('type') == 'text'
            )

        for m in msg.get('messages', []):
            content = m.get('content', '')
            if isinstance(content, list):
                content = '\n'.join(
                    b.get('text', '') for b in content
                    if isinstance(b, dict) and b.get('type') == 'text'
                )
            msgs.append({"role": m['role'], "content": content or ''})

        if system_text:
            msgs.insert(0, {"role": "system", "content": system_text})

        return msgs

    def _to_anthropic(self, resp: dict, orig_model: str, thinking_ms: int) -> dict:
        """OpenAI Chat → Anthropic Messages API format."""
        choice = resp.get('choices', [{}])[0]
        message = choice.get('message', {}) or {}
        text = message.get('content', '') or ''
        usage = resp.get('usage', {}) or {}

        return {
            "id": resp.get('id', f'msg_{q}'),
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
            "model": orig_model,
            "stop_reason": choice.get('finish_reason', 'end_turn'),
            "stop_sequence": None,
            "usage": {
                "input_tokens": int(usage.get('prompt_tokens', 0) or 0),
                "output_tokens": int(usage.get('completion_tokens', 0) or 0),
                "thinking_time_ms": thinking_ms,
            },
        }

    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # Suppress default HTTP logs


# ── Entry point ────────────────────────────────────────────

if __name__ == '__main__':
    if not OR_KEY:
        ***"FATAL: OPENROUTER_API_KEY environment variable is required")
        sys.exit(1)

    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server = http.server.HTTPServer(('127.0.0.1', port), ProxyHandler)

    print(f"""╔══════════════════════════════════╗
║  Kickbacks Arbitrage Engine   ║
╠══════════════════════════════════╣
║  Proxy  → 127.0.0.1:{port:<5}         ║
║  Ledger → {LEDGER:<28s}║
║  Models → {len(FREE_MODELS):<2d} free + paid fallback    ║
╚══════════════════════════════════╝""")
    write_status()
    server.serve_forever()