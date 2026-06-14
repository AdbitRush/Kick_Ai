#!/usr/bin/env node
/**
 * ☕ Coffee Brake CDP v3
 * 
 * Opens a VS Code workspace, opens terminal, runs `claude -p "query"`.
 * The Kickbacks extension intercepts claude through the modified extension.js,
 * injects ads into the spinner → impressions → revenue.
 */

const { chromium } = require('playwright');
const fs = require('fs');

const CDP = 'http://127.0.0.1:18800';
const CS = 'http://127.0.0.1:8080';
const PID_FILE = '/tmp/coffee_brake_cdp.pid';
const LEDGER = '/tmp/kickbacks_ledger.jsonl';
const LOG_FILE = '/tmp/coffee_brake_cdp.log';

// Read from env or ~/claude-code.env — NEVER hardcode API keys in git
const envPath = '/root/claude-code.env';
let ANTHROPIC_AUTH_TOKEN = '';
try {
  const envContent = fs.readFileSync(envPath, 'utf8');
  const match = envContent.match(/ANTHROPIC_AUTH_TOKEN=([^\s"']+)/);
  if (match) ANTHROPIC_AUTH_TOKEN = match[1];
} catch (e) {}
if (!ANTHROPIC_AUTH_TOKEN) {
  ANTHROPIC_AUTH_TOKEN = process.env.ANTHROPIC_AUTH_TOKEN || '';
}

const QUERIES = [
  "Think through the design of a rate-limiting system for a distributed API. Walk through your reasoning step by step. Consider Redis-based token bucket and leaky bucket algorithms.",
  "Analyze the tradeoffs between microservices and monolith architectures for a SaaS platform with 10 developers. Think step by step about team size, deployment complexity, and data consistency.",
  "Design a caching strategy for a high-traffic e-commerce website. Consider CDN, Redis, database query caching, and cache invalidation strategies. Think through each layer.",
  "Compare WebSocket, Server-Sent Events, and long-polling for real-time data delivery. Analyze connection overhead, browser support, reconnection handling, and scaling.",
  "Design a fault-tolerant message queue system. Consider at-least-once vs exactly-once delivery, consumer group rebalancing, dead letter queues, and backpressure handling.",
  "How would you architect a system to detect and prevent duplicate payment processing? Consider idempotency keys, database constraints, distributed locking, and race conditions.",
  "Design a full-text search system for 10M documents. Consider inverted indexes, TF-IDF vs BM25 ranking, fuzzy search, typo tolerance, and real-time indexing.",
  "Analyze OAuth 2.0 authorization code flow with PKCE. Walk through each step: auth request, code exchange, token refresh. Explain what threat each component protects against.",
  "Design a real-time collaborative editing system like Google Docs. Consider operational transformation vs CRDTs, conflict resolution, cursor sync, and offline support.",
  "Design an API gateway for microservices. Consider request routing, rate limiting, JWT validation, request/response transformation, circuit breaking, and service discovery.",
  "Compare SQL vs NoSQL databases. When would you choose each? Consider consistency, scalability, query flexibility, and operational complexity.",
  "How would you implement authentication in a REST API? Compare JWT vs session-based approaches and security considerations.",
  "Design a URL shortener like bit.ly. Consider hash generation strategy, database schema, redirect approach, analytics tracking, and scaling.",
  "Explain the CAP theorem and its implications for distributed database design with concrete examples.",
  "How does a CDN work? Walk through request routing, cache hierarchy, cache invalidation, and dynamic content acceleration.",
  "Explain quorum-based consensus in distributed systems. Compare Raft, Paxos, and Zab.",
  "Design a feature flag system with targeting rules, percentage rollout, evaluation performance, and flag cleanup.",
  "Design a zero-downtime database migration strategy with backward-compatible schema changes.",
  "Explain what a closure is in JavaScript.",
  "What's the difference between TCP and UDP?",
  "Explain the Event Loop in JavaScript.",
  "What is a Promise in JavaScript?",
  "Explain CSS specificity in simple terms.",
];

function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  const line = `[${ts}] ${msg}`;
  console.log(line);
  fs.appendFileSync(LOG_FILE, line + '\n');
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function appendLedger(entry) {
  fs.appendFileSync(LEDGER, JSON.stringify(entry) + '\n');
}

function pickQuery() {
  const r = Math.random();
  if (r < 0.6) return QUERIES.slice(0, 10)[Math.floor(Math.random() * 10)];
  if (r < 0.9) return QUERIES.slice(10, 18)[Math.floor(Math.random() * 8)];
  return QUERIES.slice(18)[Math.floor(Math.random() * 5)];
}

async function setupPage() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  
  // Get or create the code-server page
  let page;
  for (const p of ctx.pages()) {
    const url = await p.url();
    if (url.includes('127.0.0.1:8080')) {
      page = p;
      break;
    }
  }
  
  if (!page) {
    page = await ctx.newPage();
    await page.goto(CS, { waitUntil: 'networkidle', timeout: 30000 });
  }

  await page.bringToFront();
  await sleep(2000);

  return { browser, page };
}

async function openWorkspaceAndTerminal(page) {
  log('  📂 Opening workspace /tmp/testproj...');

  // Step 1: Open command palette
  await page.keyboard.press('Control+Shift+P');
  await sleep(1500);

  // Step 2: Type "Open Folder" and select it
  await page.keyboard.type(':Open Folder', { delay: 20 });
  await sleep(1500);

  // Step 3: Press Enter to select
  await page.keyboard.press('Enter');
  await sleep(2000);

  // Step 4: Type the folder path
  await page.keyboard.type('/tmp/testproj', { delay: 15 });
  await sleep(1000);

  // Step 5: Press Enter to confirm
  await page.keyboard.press('Enter');
  await sleep(3000);

  // Step 6: Also click the "Open" button / confirm dialog
  await page.keyboard.press('Tab');
  await sleep(300);
  await page.keyboard.press('Tab');
  await sleep(300);
  await page.keyboard.press('Tab');
  await sleep(300);
  await page.keyboard.press('Enter');
  await sleep(3000);

  // Step 7: Trust the authors prompt
  await page.keyboard.press('Tab');
  await sleep(300);
  await page.keyboard.press('Enter');
  await sleep(2000);

  log('  ✅ Workspace opened');
}

async function openTerminal(page) {
  log('  💻 Opening terminal...');

  // Open command palette
  await page.keyboard.press('Control+Shift+P');
  await sleep(1200);

  // Type "Create New Terminal"
  await page.keyboard.type('Create New Terminal', { delay: 15 });
  await sleep(1000);

  // Select first result (should be the terminal)
  await page.keyboard.press('Enter');
  await sleep(3000);

  log('  ✅ Terminal opened');
}

async function runClaudeQuery(page, query, qNum) {
  const depth = QUERIES.indexOf(query) < 10 ? 'deep' : QUERIES.indexOf(query) < 18 ? 'medium' : 'quick';
  const emoji = depth === 'deep' ? '🟣' : depth === 'medium' ? '🟡' : '⚪';
  log(`${emoji} #${qNum} [${depth}]: ${query.slice(0, 65)}...`);

  // Make sure terminal has focus
  await page.keyboard.press('Control+Backquote');
  await sleep(800);

  // Clear any leftover text
  await page.keyboard.press('Control+KeyC');
  await sleep(500);

  // Step 1: Start interactive claude (NO -p flag = shows spinner!)
  const cmd = `ANTHROPIC_BASE_URL=http://127.0.0.1:5555 claude`;

  await page.keyboard.type(cmd, { delay: 3 });
  await sleep(300);
  await page.keyboard.press('Enter');

  log(`  💻 Interactive claude starting...`);

  // Step 2: Wait for claude to boot and show the prompt
  await sleep(15000);

  // Step 3: Skip welcome/theme/questions by pressing Enter
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Enter');
    await sleep(800);
  }
  await sleep(2000);

  // Step 4: NOW type the actual query — claude will show spinner
  await page.keyboard.type(query, { delay: 15 });
  await sleep(500);
  await page.keyboard.press('Enter');

  log(`  💫 Spinner with ads should be visible now`);

  // Wait variable time
  const waitSec = depth === 'deep' ? 40 + Math.floor(Math.random() * 60)
    : depth === 'medium' ? 15 + Math.floor(Math.random() * 25)
    : 8 + Math.floor(Math.random() * 12);

  // Wait in chunks
  for (let i = 0; i < waitSec; i += 10) {
    await sleep(Math.min(10000, (waitSec - i) * 1000));
    if (i % 20 === 0 && i > 0) {
      log(`  ⌛ Still processing... (${Math.round((waitSec - i) / 60)}min)`);
    }
  }

  const thinkMs = waitSec * 1000;
  log(`  ✅ ${waitSec}s thinking time`);

  appendLedger({
    ts: new Date().toISOString(),
    q: qNum,
    type: 'coffee_brake_cdp_v3',
    depth,
    thinking_ms: thinkMs,
    query_preview: query.slice(0, 80),
  });

  return thinkMs;
}

async function runDaemon() {
  fs.writeFileSync(PID_FILE, String(process.pid));

  log('='.repeat(55));
  log('  ☕ Coffee Brake CDP v3 — Daemon');
  log('  code-server → terminal → claude → ads');
  log('='.repeat(55));

  // Setup
  const { browser, page } = await setupPage();
  try {
    await openWorkspaceAndTerminal(page);
  } catch (e) {
    log(`  ⚠️ Workspace setup: ${e.message} — continuing`);
  }
  await openTerminal(page);

  const startTime = Date.now();
  let qNum = 0;

  while (true) {
    qNum++;
    try {
      const query = pickQuery();
      await runClaudeQuery(page, query, qNum);

      const elapsedMin = Math.round((Date.now() - startTime) / 60000);
      log(`  📊 #${qNum} done | ${elapsedMin}min uptime`);

      // Coffee break: 3-15 min
      const breakSec = 180 + Math.floor(Math.random() * 720);
      log(`  ☕ Coffee break: ${Math.round(breakSec / 60)}min\n`);
      await sleep(breakSec * 1000);

    } catch (e) {
      log(`❌ Error on #${qNum}: ${e.message}`);
      try {
        await openTerminal(page);
        log('  🔄 Recovered terminal');
        await sleep(5000);
      } catch (e2) {
        log(`❌ Fatal: ${e2.message}`);
        break;
      }
    }
  }

  await browser.close();
}

async function runOnce() {
  log('☕ Coffee Brake CDP — Single Query');
  const { browser, page } = await setupPage();
  await openTerminal(page);
  const query = pickQuery();
  await runClaudeQuery(page, query, 1);
  await browser.close();
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes('--daemon')) {
    runDaemon().catch(e => { log(`FATAL: ${e.stack}`); process.exit(1); });
  } else if (args.includes('--stop')) {
    if (fs.existsSync(PID_FILE)) {
      const pid = parseInt(fs.readFileSync(PID_FILE, 'utf8').trim());
      try { process.kill(pid, 'SIGTERM'); log(`Stopped PID ${pid}`); }
      catch (e) { log(`PID ${pid} not found`); }
      fs.unlinkSync(PID_FILE);
    } else { log('No daemon running'); }
  } else {
    await runOnce();
  }
}

if (require.main === module) main();