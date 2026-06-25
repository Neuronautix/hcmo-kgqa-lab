// Capture demo screenshots of the HCMO-KGQA Streamlit UI with Playwright.
//
// Prereqs: the Streamlit app and a SPARQL backend must be running, e.g.
//   make demo                       # build kg/generated/merged_kg.ttl
//   python scripts/demo_serve.py &  # offline Fuseki-compatible backend (:3030)
//   make ui                         # streamlit on :8501
//   node scripts/demo_screenshots.js
//
// Config via env: BASE_URL (default http://localhost:8501),
//                 OUT_DIR  (default ./demo_screenshots).
//
// Writes one PNG per key page (landing, ontology explorer, SPARQL playground
// with reasoning-inferred types, and the KGQA workflow grounded trace).

const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.env.BASE_URL || 'http://localhost:8501';
const OUT = process.env.OUT_DIR || 'demo_screenshots';
fs.mkdirSync(OUT, { recursive: true });

async function settle(page, ms = 1500) {
  try { await page.waitForLoadState('networkidle', { timeout: 8000 }); } catch (e) {}
  for (let i = 0; i < 30; i++) {
    const widget = page.locator('[data-testid="stStatusWidget"]');
    if (!(await widget.count())) break;
    const txt = await widget.innerText().catch(() => '');
    if (!/run|load/i.test(txt)) break;
    await page.waitForTimeout(400);
  }
  await page.waitForTimeout(ms);
}

async function shot(page, name) {
  const path = `${OUT}/${name}.png`;
  await page.screenshot({ path, fullPage: true });
  console.log('saved', path);
}

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();

  // 1. Landing page (design principle + architecture).
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await settle(page, 2500);
  await shot(page, '1_home');

  // 2. Ontology Explorer (what HCMO contributes: classes & properties).
  await page.goto(`${BASE}/Ontology_Explorer`, { waitUntil: 'domcontentloaded' });
  await settle(page, 2500);
  await shot(page, '2_ontology_explorer');

  // 3. SPARQL Playground — reasoning-inferred types over the single graph.
  await page.goto(`${BASE}/SPARQL_Playground`, { waitUntil: 'domcontentloaded' });
  await settle(page, 2000);
  const ta = page.locator('textarea').first();
  await ta.click();
  await ta.fill(
    'PREFIX hcmo: <http://w3id.org/hcmo#>\n' +
    'SELECT ?dataset ?type WHERE {\n' +
    '  ?dataset a hcmo:VCGReadyDataset ; a ?type .\n' +
    '} ORDER BY ?dataset LIMIT 25'
  );
  await page.getByRole('button', { name: 'Run query' }).click();
  await settle(page, 2500);
  await shot(page, '3_sparql_inferred');

  // 4. KGQA Workflow — full grounded trace.
  await page.goto(`${BASE}/KGQA_Workflow`, { waitUntil: 'domcontentloaded' });
  await settle(page, 2000);
  const q = page.getByPlaceholder('Ask a question about the HCMO knowledge graph');
  await q.click();
  await q.fill('Which datasets are VCG-ready?');
  await page.keyboard.press('Tab');
  await settle(page, 800);
  await page.getByRole('button', { name: 'Run KGQA' }).click();
  await settle(page, 3500);
  await shot(page, '4_kgqa_grounded');

  await browser.close();
  console.log('done ->', OUT);
})().catch((e) => { console.error('screenshot error:', e); process.exit(1); });
