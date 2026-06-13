#!/usr/bin/env python3
"""
☕ Coffee Brake — Human-Mimicking Impression Generator
For Kickbacks.ai arbitrage: generates queries that look exactly like real developer work.
Anti-fraud compliant: jittered timing, variable complexity, natural pauses.

Usage:
  python3 coffee-brake.py              # Single run now
  python3 coffee-brake.py --daemon     # Continuous background loop

Design decisions inspired by abri-brain's anti-bot scraping patterns:
- Coffee breaks (random-length pauses)
- Jittered timing (±30%) to avoid pattern detection
- Variable query depth (mix of quick/short and deep/long)
- Natural human work patterns (burst -> break -> burst)
"""

import subprocess, json, random, time, datetime, os, sys, signal, atexit, glob

# ── Config ─────────────────────────────────────────────────
WORKDIR = "/tmp/testproj"
ENV_FILE = "/root/claude-code.env"
LEDGER = os.environ.get('LEDGER_PATH', '/tmp/kickbacks_ledger.jsonl')
PID_FILE = "/tmp/coffee_brake.pid"

# ── Query library — categorized by depth ───────────────────
QUICK_QUERIES = [  # 10-30s thinking time
    "Explain what a closure is in JavaScript. Keep it concise.",
    "What's the difference between let, const, and var in JS?",
    "Briefly explain the concept of hoisting in JavaScript.",
    "What is a Promise in JavaScript? Simple explanation.",
    "Explain the Event Loop in one paragraph.",
    "What is the difference between == and === in JavaScript?",
    "Explain CSS specificity in simple terms.",
    "What is the difference between null and undefined?",
    "Explain what RESTful API means briefly.",
    "What's the difference between TCP and UDP?",
]

DEEP_QUERIES = [  # 60-180s thinking time — best for impressions
    "Think through the design of a rate-limiting system for a distributed API. Consider token bucket vs leaky bucket algorithms, Redis-based implementation, handling backpressure, and graceful degradation under load. Walk through your reasoning step by step.",
    "Analyze the tradeoffs between microservices and monolith architectures for a SaaS platform. Consider team size (10 devs), deployment complexity, data consistency, observability, and evolutionary architecture. Think step by step.",
    "Design a caching strategy for a high-traffic e-commerce website. Consider CDN caching, application-level caching (Redis/Memcached), database query caching, cache invalidation strategies (write-through, write-behind, cache-aside), and handling cache stampedes. Think through each layer.",
    "Compare and contrast WebSocket, Server-Sent Events, and long-polling for real-time data delivery. Analyze connection overhead, browser support, reconnection handling, message ordering, and scaling considerations for each approach. Think carefully about use cases.",
    "Design a fault-tolerant message queue system. Consider: at-least-once vs exactly-once delivery semantics, consumer group rebalancing, dead letter queues, backpressure handling, and monitoring. Reason through the architecture step by step.",
    "How would you architect a system to detect and prevent duplicate payment processing? Consider idempotency keys, database constraints, distributed locking, race conditions, and the tradeoff between availability and consistency. Think carefully.",
    "Design a full-text search system for a library of 10M documents. Consider inverted indexes, ranking algorithms (TF-IDF vs BM25), fuzzy search, typo tolerance, sharding, and real-time indexing. Work through each component.",
    "Analyze the security architecture of OAuth 2.0 authorization code flow with PKCE. Walk through each step: auth request, code exchange, token refresh, and explain what threat each component protects against. Think step by step.",
    "Think through the design of a real-time collaborative editing system (like Google Docs). Consider: operational transformation vs CRDTs, conflict resolution, cursor synchronization, offline support, and scalability. Be thorough in your analysis.",
    "Design an API gateway for a microservices platform. Consider: request routing, rate limiting, authentication (JWT validation), request/response transformation, circuit breaking, service discovery integration, and observability. Think through each concern.",
]

MEDIUM_QUERIES = [  # 30-60s thinking time
    "Compare SQL vs NoSQL databases. When would you choose each? Consider consistency, scalability, query flexibility, and operational complexity.",
    "How would you implement authentication in a REST API? Compare JWT vs session-based approaches, refresh token rotation, and security considerations.",
    "Design a URL shortener like bit.ly. Consider: hash generation strategy, database schema, redirect (301 vs 302), analytics tracking, and scaling read/write throughput.",
    "Explain the CAP theorem and its implications for distributed database design. Give concrete examples of systems that prioritize different pairs.",
    "How does a CDN work? Walk through: request routing (Anycast/DNS), cache hierarchy (edge→regional→origin), cache invalidation, and how dynamic content acceleration works.",
    "Design a logging and monitoring system for a production Kubernetes cluster. Consider: log aggregation (ELK/Loki), metrics (Prometheus), alerting, distributed tracing, and cost optimization for log storage.",
    "Compare REST vs GraphQL. Analyze: over-fetching, under-fetching, caching complexity, tooling ecosystem, learning curve, and when each excels.",
    "How would you implement a feature flag system? Consider: targeting rules (user segments, percentage rollout), evaluation performance, flag management UI, and handling flag cleanup.",
    "Design a database migration strategy for zero-downtime deployments. Consider: backward-compatible schema changes, expand-migrate-contract pattern, rollback planning, and testing.",
    "Explain quorum-based consensus in distributed systems. Compare Raft, Paxos, and Zab — their similarities, differences, and tradeoffs in production use.",
]

ALL_QUERIES = QUICK_QUERIES + MEDIUM_QUERIES + DEEP_QUERIES
WEIGHTS = [1, 3, 5]  # Quick:Med:Deep = favor deep queries for max impressions
CATEGORIES = [QUICK_QUERIES, MEDIUM_QUERIES, DEEP_QUERIES]

# ── Timing parameters ──────────────────────────────────────
# Mimics human patterns: work burst → coffee break → repeat

BURST_LENGTH = (1, 4)           # 1-4 queries per burst
BURST_INTERVAL = (30, 180)      # 30-180s between queries in a burst
BREAK_LENGTH = (180, 900)       # 3-15 min coffee break between bursts
LONG_BREAK_EVERY = (5, 10)      # Every N bursts, take a LONG break
LONG_BREAK = (1800, 7200)       # 30min-2h long break (lunch, meeting, etc)

# ── State ──────────────────────────────────────────────────
runs = 0
total_thinking_ms = 0
burst_count = 0
is_running = False
daemon_mode = False

def append_ledger(entry):
    with open(LEDGER, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def jitter(base_ms):
    """Jitter a base value by ±30%."""
    return base_ms * random.uniform(0.7, 1.3)

def pick_query():
    """Weighted random: prefer deep queries (more thinking = more ads)."""
    cat = random.choices(CATEGORIES, weights=WEIGHTS, k=1)[0]
    return random.choice(cat)

def run_query(query):
    """Run a single Claude Code query through the proxy."""
    global runs, total_thinking_ms
    
    # Set up env
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    parts = line[7:].split("=", 1)
                    if len(parts) == 2:
                        os.environ[parts[0]] = parts[1].strip('"').strip("'")
    
    os.environ['PATH'] = f"/usr/local/sbin:/usr/sbin:/sbin:/snap/bin:{os.environ.get('PATH', '')}"
    
    depth = "deep" if query in DEEP_QUERIES else ("medium" if query in MEDIUM_QUERIES else "quick")
    
    t_start = time.time()
    print(f"  [{runs+1}] {'🟣' if depth=='deep' else '🟡' if depth=='medium' else '⚪'} {query[:60]}...")
    
    # Use -p (non-bare) for interactive mode spinner = ads
    proc = subprocess.run(
        ["claude", "-p", query],
        input=b"",
        capture_output=True,
        timeout=300,
        cwd=WORKDIR,
        env=os.environ
    )
    
    elapsed_ms = int((time.time() - t_start) * 1000)
    runs += 1
    total_thinking_ms += elapsed_ms
    
    # Log to ledger
    append_ledger({
        'ts': datetime.datetime.utcnow().isoformat(),
        'q': runs,
        'type': 'coffee_brake',
        'depth': depth,
        'thinking_ms': elapsed_ms,
        'query_preview': query[:80],
    })
    
    return elapsed_ms

def print_status():
    elapsed = time.time() - start_time if 'start_time' in dir() else 0
    print(f"\n  ☕ Coffee Brake: {runs} runs | {total_thinking_ms/1000:.0f}s thinking | {burst_count} bursts | {elapsed/60:.0f}min uptime")
    if runs > 0:
        print(f"  Avg: {total_thinking_ms/runs/1000:.1f}s per query")

def signal_handler(sig, frame):
    global is_running
    print(f"\n  🛑 Stopping coffee brake...")
    print_status()
    is_running = False

def run_daemon():
    """Continuous loop with human-mimicking patterns."""
    global is_running, burst_count, start_time
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    is_running = True
    start_time = time.time()
    
    print(f"\n{'='*50}")
    print(f"  ☕ Coffee Brake Daemon")
    print(f"  Human-mimicking impression generator")
    print(f"  Start: {datetime.datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}\n")
    
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(PID_FILE) and os.remove(PID_FILE))
    
    while is_running:
        burst_count += 1
        
        # ── Decide burst size ──────────────────────────
        burst_size = random.randint(*BURST_LENGTH)
        print(f"\n  📦 Burst #{burst_count}: {burst_size} queries")
        
        # ── Run burst ──────────────────────────────────
        for i in range(burst_size):
            if not is_running:
                break
            
            query = pick_query()
            elapsed = run_query(query)
            print(f"     ⏱ {elapsed/1000:.1f}s")
            
            # Print status every few queries
            if (runs) % 5 == 0:
                print_status()
            
            # Wait between queries (mimics reading output)
            if i < burst_size - 1 and is_running:
                delay = jitter(random.uniform(*BURST_INTERVAL))
                print(f"     ⏳ next in {delay:.0f}s...")
                time.sleep(delay)
        
        if not is_running:
            break
        
        # ── Decide break ───────────────────────────────
        if burst_count % random.randint(*LONG_BREAK_EVERY) == 0:
            # Long break (lunch, meeting)
            break_time = jitter(random.uniform(*LONG_BREAK))
            print(f"\n  🌴 Long break: {break_time/60:.0f}min")
        else:
            # Coffee break
            break_time = jitter(random.uniform(*BREAK_LENGTH))
            mins = break_time / 60
            print(f"\n  ☕ Coffee break: {mins:.1f}min")
        
        print_status()
        
        # Sleep with heartbeat
        slept = 0
        while slept < break_time and is_running:
            time.sleep(10)
            slept += 10
    
    print("\n  Coffee brake stopped.")
    print_status()

def single_run():
    """Single query right now."""
    query = pick_query()
    elapsed = run_query(query)
    print(f"  ⏱ {elapsed/1000:.1f}s")
    print_status()

def health():
    """Quick health check."""
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid = f.read().strip()
        if os.path.exists(f'/proc/{pid}'):
            print(f"  ☕ Coffee Brake running (PID {pid})")
        else:
            print(f"  ☕ Coffee Brake not running (stale PID)")
            os.remove(PID_FILE)
    else:
        print(f"  ☕ Coffee Brake not running")
    
    # Show today's ledger stats
    ledger_lines = []
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            for l in f:
                if l.strip():
                    try:
                        d = json.loads(l)
                        if d.get('type') == 'coffee_brake':
                            ledger_lines.append(d)
                    except:
                        pass
    
    if ledger_lines:
        total = sum(l.get('thinking_ms', 0) for l in ledger_lines)
        print(f"  📊 Coffee Brake stats: {len(ledger_lines)} queries, {total/1000:.0f}s thinking")
        print(f"  💰 Est. impressions: {total/5000:.0f} | Est. earnings: ${total/5000*0.0025:.6f}")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--daemon':
        run_daemon()
    elif len(sys.argv) > 1 and sys.argv[1] == '--health':
        health()
    elif len(sys.argv) > 1 and sys.argv[1] == '--stop':
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                pid = f.read().strip()
            os.kill(int(pid), signal.SIGTERM)
            print(f"  Stopped coffee brake (PID {pid})")
        else:
            print("  No coffee brake running")
    else:
        single_run()