// Generic Playwright renderer. No output-specific code.
//
// stdin:  [{html, pdf?, png?, wait?, timeout?}, ...]   (JSON; paths absolute)
//   html     the page to load (a file path)
//   pdf      write the page as a PDF here (print CSS, CSS page size, backgrounds)
//   png      {path, selector, scale?, limit?}: one screenshot per element matching `selector`;
//            `path` holds "{n}" (1-based), e.g. ".../sheet-p{n}.png"
//   wait     selector to wait for before output (default "body[data-ready]")
// stdout: [{html, pdf, pages, pngs, stats}, ...]   (JSON; stats = window.__occultStats or null)
//
// Env: PLAYWRIGHT_BROWSERS_PATH (Chromium), OCCULT_PLAYWRIGHT (the playwright module, if not on
// the default resolve path). Chromium is launched once per batch.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
function loadPlaywright() {
  const tries = [process.env.OCCULT_PLAYWRIGHT, 'playwright', '/opt/node22/lib/node_modules/playwright'].filter(Boolean);
  for (const t of tries) { try { return require(t); } catch { /* next */ } }
  console.error('error: cannot load the playwright module; set OCCULT_PLAYWRIGHT to its path');
  process.exit(3);
}
const { chromium } = loadPlaywright();

const input = fs.readFileSync(0, 'utf8');
const jobs = JSON.parse(input || '[]');

let browser;
try { browser = await chromium.launch(); }
catch (e) {
  console.error('error: cannot launch Chromium; set PLAYWRIGHT_BROWSERS_PATH (' + String(e.message).split('\n')[0] + ')');
  process.exit(4);
}

const pdfPages = (file) => (fs.readFileSync(file, 'latin1').match(/\/Type\s*\/Page(?![s\w])/g) || []).length;

const results = [];
for (const job of jobs) {
  const scale = job.png?.scale ?? 1;
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: scale });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.emulateMedia({ media: 'print' });       // fit under the same media the PDF uses
  // The page's own script (fit.js, book.js) waits for fonts and images and sets the ready mark;
  // waiting for `load` here as well would time out on decks with hundreds of art files.
  await page.goto(pathToFileURL(job.html).href, { waitUntil: 'domcontentloaded', timeout: job.timeout || 120000 });
  try {
    await page.waitForSelector(job.wait || 'body[data-ready]', { state: 'attached', timeout: job.timeout || 120000 });
  } catch (e) {
    console.error(`error: ${job.html} never became ready${errors.length ? ': ' + errors.join('; ') : ''}`);
    process.exit(5);
  }
  const stats = await page.evaluate(() => window.__occultStats ?? null);
  const out = { html: job.html, pdf: null, pages: null, pngs: [], stats, errors };
  if (job.pdf) {
    fs.mkdirSync(path.dirname(job.pdf), { recursive: true });
    await page.pdf({ path: job.pdf, preferCSSPageSize: true, printBackground: true });
    out.pdf = job.pdf;
    out.pages = pdfPages(job.pdf);
  }
  if (job.png) {
    const els = page.locator(job.png.selector);
    const n = Math.min(await els.count(), job.png.limit ?? Infinity);
    fs.mkdirSync(path.dirname(job.png.path), { recursive: true });
    for (let i = 0; i < n; i++) {
      const p = job.png.path.replace('{n}', String(i + 1));
      await els.nth(i).screenshot({ path: p });
      out.pngs.push(p);
    }
  }
  results.push(out);
  await page.close();
}
await browser.close();
process.stdout.write(JSON.stringify(results) + '\n');
