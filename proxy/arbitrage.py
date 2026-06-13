#!/usr/bin/env python3
"""Kickbacks Arbitrage Engine — zero-cost free model proxy + financial tracking"""
import http.server, json, urllib.request, urllib.error, ssl, sys, os, time, datetime, signal, atexit

# Read API key from environment
try:
    OR_KEY = os.environ['OPENROUTER_API_KEY']
except KeyError:
    OR_KEY = ''

PORT = int(os.environ.get('PROXY_PORT', '5555'))
LEDGER = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')

FREE_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "qwen/qwen3-coder:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-120b:free",
    "openrouter/free",
]
PAID_MODEL = "deepseek/deepseek-v4-flash-20260423"

q = 0; total_cost = 0.0; total_thinking_ms = 0; start_time = time.time()

def append_ledger(d):
    with open(LEDGER, 'a') as f:
        f.write(json.dumps(d) + '\n')

def write_status():
    elapsed = time.time() - start_time
    with open('/tmp/kickbacks_status.txt', 'w') as f:
        f.write(f"Kickbacks Arbitrage\nUptime: {elapsed/3600:.1f}h\nQueries: {q}\nThinking: {total_thinking_ms/1000:.1f}s\nCost: ${total_cost:.6f}\n")

atexit.register(write_status)

class P(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')

    def do_POST(self):
        global q, total_cost, total_thinking_ms
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        try: msg = json.loads(body)
        except: return self._send(400, {"type":"error","error":{"message":"bad json"}})

        om = msg.get('model', 'claude-sonnet-4-20250514')
        oai = self._to_openai(msg)
        mt = min(msg.get('max_tokens', 2048), 4096)

        t1 = time.time()
        res, used, is_free, model_cost = None, None, False, 0.0

        offset = q % max(1, len(FREE_MODELS) - 1)
        ordered = FREE_MODELS[offset:] + FREE_MODELS[:offset]
        for model in ordered:
            res = self._call(model, oai, mt)
            if res and res.get('choices'):
                used, is_free = model, True
                break

        if not res or not res.get('choices'):
            res = self._call(PAID_MODEL, oai, mt)
            if res and res.get('choices'):
                used, is_free = PAID_MODEL, False
                u = res.get('usage', {}) or {}
                pt = int(u.get('prompt_tokens', 0) or 0)
                ct = int(u.get('completion_tokens', 0) or 0)
                model_cost = (pt/1e6 * 0.098) + (ct/1e6 * 0.399)

        ms = int((time.time() - t1) * 1000)
        q += 1; total_thinking_ms += ms; total_cost += model_cost

        if res and res.get('choices'):
            u = res.get('usage', {}) or {}
            append_ledger({
                'ts': datetime.datetime.utcnow().isoformat(), 'q': q,
                'model_actual': used, 'model_claude': om, 'free': is_free,
                'input_tokens': int(u.get('prompt_tokens', 0) or 0),
                'output_tokens': int(u.get('completion_tokens', 0) or 0),
                'thinking_ms': ms, 'cost_usd': round(model_cost, 8),
            })
            anth = self._to_anthropic(res, om, ms)
            self._send(200, anth)
        else:
            err = str(res.get('error', 'fail'))[:200] if res else 'no response'
            self._send(502, {"type":"error","error":{"message":err}})

    def _call(self, model, messages, max_tokens):
        payload = json.dumps({
            "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": 0.7,
        }).encode('utf-8')
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={"Content-Type":"application/json", "Authorization": f"Bearer {OR_KEY}",
                     "HTTP-Referer": "https://kickbacks.ai"},
        )
        try:
            ctx = ssl.create_default_context()
            return json.loads(urllib.request.urlopen(req, context=ctx, timeout=120).read())
        except urllib.error.HTTPError as e:
            try: return json.loads(e.read())
            except: return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}

    def _to_openai(self, msg):
        msgs = []; sys_t = None
        if 'system' in msg:
            t = msg['system']
            sys_t = t if isinstance(t, str) else ' '.join(b.get('text','') for b in t if isinstance(b,dict) and b.get('type')=='text')
        for m in msg.get('messages', []):
            c = m.get('content','')
            if isinstance(c, list): c = '\n'.join(b.get('text','') for b in c if isinstance(b,dict) and b.get('type')=='text')
            msgs.append({"role": m['role'], "content": c or ''})
        if sys_t: msgs.insert(0, {"role":"system","content":sys_t})
        return msgs

    def _to_anthropic(self, r, om, ms):
        c = r.get('choices',[{}])[0]
        text = (c.get('message',{}) or {}).get('content','') or ''
        u = r.get('usage',{}) or {}
        return {
            "id": r.get('id',f'msg_{q}'), "type":"message", "role":"assistant",
            "content":[{"type":"text","text":text}], "model":om,
            "stop_reason":c.get('finish_reason','end_turn'), "stop_sequence":None,
            "usage":{"input_tokens":int(u.get('prompt_tokens',0) or 0),
                     "output_tokens":int(u.get('completion_tokens',0) or 0),
                     "thinking_time_ms": ms}
        }

    def _send(self, code, data):
        b = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, fmt, *a): pass

if __name__ == '__main__':
    if not OR_KEY:
        print("FATAL: OPENROUTER_API_KEY not set"); sys.exit(1)
    sv = http.server.HTTPServer(('127.0.0.1', PORT), P)
    print(f"Arbitrage Proxy :{PORT} | {len(FREE_MODELS)} free models")
    write_status()
    sv.serve_forever()
