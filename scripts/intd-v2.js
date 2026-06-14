const { chromium } = require('/root/Kick_Ai/node_modules/playwright');
const fs = require('fs');
const { execSync } = require('child_process');
const LOG = '/tmp/intd.log';

function log(m) {
  const ts = new Date().toISOString().slice(11,19);
  fs.appendFileSync(LOG, `[${ts}] ${m}\n`);
  console.log(`[${ts}] ${m}`);
}

const QUERIES = [
  "Read all src/ files and create a complete architecture document listing every class, method, dependency, and design pattern.",
  "Analyze every bug in src/ across all modules. Rank by severity with line numbers.",
  "Write complete TypeScript type defs for all DataProcessor classes.",
  "Design a monitoring system: metrics, tracing, logging, alerting.",
  "Compare WebSocket vs SSE vs long-polling for real-time data.",
  "Explain the CAP theorem with concrete distributed examples.",
  "Design a CI/CD pipeline for the project with GitHub Actions.",
  "Design a refactoring plan to eliminate code duplication between all modules.",
  "Write Jest tests covering all edge cases for DataProcessor modules.",
  "Create a performance benchmark suite for all DataProcessor classes.",
  "Write a README for this project with badges and examples.",
  "Document the error handling patterns used across the codebase.",
  "Write a docker-compose.yml for development and production.",
  "Create an API reference doc for all exported functions.",
  "Write a migration guide from CommonJS to ESM.",
  "Explain the observer pattern and find all places it applies.",
  "Design a caching layer for the DataProcessor pipeline.",
  "Implement a health check endpoint design.",
  "Create a contribution guide with code style rules.",
  "Design a plugin system for extensible data processing.",
  "Write a haiku about server automation.",
  "Explain async/await vs promises in one paragraph.",
  "What is tail recursion? Example in JS.",
  "Write a regex for validating email addresses.",
  "What are the SOLID principles? One sentence each.",
  "Name 3 ways to handle errors in async code.",
  "What is the difference between let, const, var?",
  "Explain REST vs GraphQL in one sentence each.",
  "Write a one-line memoization utility function.",
  "What is the event loop? Explain simply.",
];

function pickQ(lastIdx) {
  const pool = [];
  for (let i = 0; i < 3; i++) pool.push(Math.floor(Math.random() * 10));
  for (let i = 0; i < 4; i++) pool.push(10 + Math.floor(Math.random() * 10));
  for (let i = 0; i < 3; i++) pool.push(20 + Math.floor(Math.random() * 10));
  let p = pool[Math.floor(Math.random() * pool.length)];
  while (p === lastIdx && pool.length > 1) p = pool[Math.floor(Math.random() * pool.length)];
  return p;
}

async function main() {
  log('=== INTD V2 ===');
  const b = await chromium.connectOverCDP('http://127.0.0.1:18800');
  let p = null;
  for (const c of b.contexts()) { for (const pg of c.pages()) { if (pg.url().includes('8080')) { p = pg; break; } } if (p) break; }
  if (!p) { const c = b.contexts()[0] || await b.newContext(); p = await c.newPage(); await p.goto('http://127.0.0.1:8080/?folder=/tmp/testproj', { timeout: 15000 }); }

  let hasTerm = await p.evaluate(() => !!document.querySelector('.xterm-helper-textarea'));
  if (!hasTerm) { await p.keyboard.press('Control+`'); await new Promise(r => setTimeout(r, 5000)); }
  await p.evaluate(() => { const ta = document.querySelector('.xterm-helper-textarea'); if (ta) ta.focus(); });
  await new Promise(r => setTimeout(r, 1000));

  const claudeRunning = execSync("ps aux | grep -E '[c]laude ' | wc -l").toString().trim();
  if (parseInt(claudeRunning) < 2) {
    await p.keyboard.type('cd /tmp/testproj && ANTHROPIC_BASE_URL=http://127.0.0.1:5555 claude', { delay: 15 });
    await p.keyboard.press('Enter');
    await new Promise(r => setTimeout(r, 15000));
    for (let i = 0; i < 12; i++) { await p.keyboard.press('Enter'); await new Promise(r => setTimeout(r, 600)); }
  } else log('Claude already running');

  let lastQ = -1;
  for (let qi = 0; ; qi++) {
    const idx = pickQ(lastQ); lastQ = idx;
    const q = QUERIES[idx];
    const depth = idx < 10 ? 'DEEP' : idx < 20 ? 'MED' : 'QK';

    log(`#${qi+1} ${depth}: ${q.slice(0,55)}...`);
    await p.keyboard.type(q, { delay: 10 + Math.floor(Math.random() * 15) });
    await new Promise(r => setTimeout(r, 200 + Math.random() * 500));
    await p.keyboard.press('Enter');

    const thinkSec = depth === 'DEEP' ? 300 + Math.random() * 180
                   : depth === 'MED' ? 180 + Math.random() * 120
                   : 60 + Math.random() * 60;
    log(`  ~${Math.round(thinkSec/60)}min spin`);
    await new Promise(r => setTimeout(r, thinkSec * 1000));

    const lines = fs.readFileSync('/root/.vibe-ads/debug.log','utf8').split('\n').filter(l => l.includes('signedIn') || l.includes('auth.'));
    log(`  ${lines.slice(-1)[0]?.slice(38,80) || '?'}`);

    const brakeSec = depth === 'DEEP' ? 300 + Math.random() * 600
                   : depth === 'MED' ? 180 + Math.random() * 480
                   : 120 + Math.random() * 240;
    log(`  ☕${Math.round(brakeSec/60)}m`);
    await new Promise(r => setTimeout(r, brakeSec * 1000));
  }
}

main().catch(e => { log(`FATAL: ${e.message||e}`); process.exit(1); });
