#!/usr/bin/env node
// webcheck: one self-tested check runner for published pages. Drives the debug Chrome on
// 127.0.0.1:9222 over CDP (Node 22, no npm), plus a served-HTML mode that needs no browser.
// Usage and the inventory format: README.md beside this file.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureChrome, connect, openPage } from './lib/cdp.mjs';
import { servedChecks, RESIDUE, DEFAULT_LABELS } from './lib/served.mjs';
import { decodePng, contrast, blend } from './lib/png.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGE_SRC = readFileSync(join(HERE, 'lib/page.js'), 'utf8').replace(/^\s*\/\/.*\n/gm, '');
const SCRATCH = join(homedir(), '.claude/_scratch');
const WIDTHS = [320, 375, 390, 480, 768, 991, 1024, 1280, 1440, 1920];
const ALL = ['served', 'layout', 'text', 'images', 'a11y', 'state', 'console', 'completeness'];
const USAGE = `usage: node webcheck.mjs <url>... [--widths 320,375,...] [--checks ${ALL.join(',')}]
  [--inventory design-inventory.json] [--copy copy-map.json|.md] [--out <dir under ~/.claude/_scratch>]
  [--html-only] [--job <id>] [--expect <text>]... [--absent <text>]... [--ignore <css>]... [--waive "<served check>|<text>|<reason>"]...
  [--lang en-AU|any|<code>] [--noindex expect|forbid] [--sitemap] [--axe <path/to/axe.min.js>] [--port 9222]
exit 0 all pass (warnings allowed), 1 any fail, 2 usage or infrastructure error`;

function die(msg) { console.error(`webcheck: ${msg}\n${USAGE}`); process.exit(2); }

function parseArgs(argv) {
  const o = { urls: [], expect: [], absent: [], ignore: [], waive: [], port: 9222 };
  const multi = { '--expect': 'expect', '--absent': 'absent', '--ignore': 'ignore', '--waive': 'waive' };
  const single = { '--widths': 'widths', '--checks': 'checks', '--inventory': 'inventory', '--copy': 'copy', '--out': 'out', '--job': 'job', '--lang': 'lang', '--noindex': 'noindex', '--axe': 'axe', '--port': 'port' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { console.log(USAGE); process.exit(0); }
    else if (a === '--html-only') o.htmlOnly = true;
    else if (a === '--sitemap') o.sitemap = true;
    else if (multi[a]) { if (i + 1 >= argv.length) die(`${a} needs a value`); o[multi[a]].push(argv[++i]); }
    else if (single[a]) { if (i + 1 >= argv.length) die(`${a} needs a value`); o[single[a]] = argv[++i]; }
    else if (a.startsWith('--')) die(`unknown flag ${a}`);
    else o.urls.push(a);
  }
  o.port = Number(o.port);
  o.widths = o.widths ? o.widths.split(',').map(Number) : WIDTHS;
  if (o.widths.some((w) => !Number.isInteger(w) || w < 200 || w > 3840)) die('widths must be integers from 200 to 3840');
  o.checks = new Set(o.checks ? o.checks.split(',') : ALL.filter((c) => c !== 'completeness' || o.inventory));
  for (const c of o.checks) if (!ALL.includes(c)) die(`unknown check ${c}`);
  if (o.checks.has('completeness') && !o.inventory) die('completeness needs --inventory');
  if (o.htmlOnly && !o.checks.has('served')) die('--html-only runs only the served checks; add served to --checks');
  if (o.noindex && !['expect', 'forbid'].includes(o.noindex)) die('--noindex takes expect or forbid');
  o.waive = o.waive.map((w) => {
    const [check, text, ...why] = w.split('|').map((x) => x.trim());
    if (!/^served\.[a-z0-9-]+$/.test(check) || !text || !why.join('|')) die(`--waive takes "<served check>|<text>|<reason>", all three required: ${w}`);
    return { check, text, reason: why.join('|') };
  });
  for (const u of o.urls) { try { if (!/^https?:$/.test(new URL(u).protocol)) throw 0; } catch { die(`not an http(s) URL: ${u}`); } }
  return o;
}

const opt = parseArgs(process.argv.slice(2));
const started = new Date();
const stamp = started.toISOString().replace(/[-:]/g, '').slice(0, 15).replace('T', '-');
const job = opt.job || `wc-${stamp}`;
const outDir = resolve(opt.out || join(SCRATCH, `${started.toISOString().slice(0, 7)}-webcheck-${job}`));
if (!outDir.startsWith(`${SCRATCH}/`)) die(`--out must be under ${SCRATCH}`);
mkdirSync(outDir, { recursive: true });

const results = [];
const add = (check, status, message, extra = {}) => results.push({ check, status, message, ...extra });
const pathOf = (u) => { try { return new URL(u).pathname; } catch { return u; } };

// Design inventory (F12): pages -> viewport -> ordered sections.
let inv = null;
if (opt.inventory) {
  try { inv = JSON.parse(readFileSync(opt.inventory, 'utf8')); } catch (e) { die(`cannot read inventory: ${e.message}`); }
  if (!inv.pages || typeof inv.pages !== 'object') die('inventory needs a "pages" object');
  inv.viewports = { desktop: 1440, mobile: 390, ...(inv.viewports || {}) };
  const base = inv.base || opt.urls[0];
  if (!base) die('inventory has no "base" and no URL was given');
  const norm = (p) => (p.length > 1 ? p.replace(/\/+$/, '') : p);
  inv.urls = new Map();
  for (const key of Object.keys(inv.pages)) {
    const path = norm(new URL(key, base).pathname);
    const given = opt.urls.find((u) => norm(new URL(u).pathname) === path);
    inv.urls.set(key, given || new URL(key, base).href);
    for (const [vp, secs] of Object.entries(inv.pages[key])) {
      if (!inv.viewports[vp]) die(`inventory page ${key} uses undeclared viewport "${vp}"`);
      if (!Array.isArray(secs) || secs.some((s) => !s || typeof s.section !== 'string')) die(`inventory ${key} ${vp}: each row needs a "section" string`);
    }
  }
}
if (!opt.urls.length && !inv) die('give at least one URL');

// Copy map (F11): every string leaf of a JSON file, or every line and table cell of a text file.
// Inline code (node ids such as `408:195`) and bare leading node ids are not copy.
let copy = null;
if (opt.copy) {
  let raw;
  try { raw = readFileSync(opt.copy, 'utf8'); } catch (e) { die(`cannot read copy map: ${e.message}`); }
  const entries = [];
  if (/\.json$/i.test(opt.copy)) { const walk = (v) => (typeof v === 'string' ? entries.push(v) : v && typeof v === 'object' ? Object.values(v).forEach(walk) : 0); walk(JSON.parse(raw)); }
  else for (const line of raw.split('\n')) for (const cell of line.replace(/`[^`]*`/g, ' ').split('|')) { const t = cell.replace(/^[\s#>*-]+/, '').replace(/^I?\d+:\d+(;\d+:\d+)*\s*/, '').trim(); if (/\p{L}/u.test(t)) entries.push(t); }
  const tok = (s) => s.toLowerCase().replace(/[\u2018\u2019]/g, "'").match(/[\p{L}\p{N}']+/gu) || [];
  // A proper noun is capitalised mid-sentence somewhere in the map and never written in lower case.
  const caps = new Set(), lower = new Set();
  for (const e of entries) e.split(/\s+/).forEach((w, i, a) => { const c = w.replace(/^[^\p{L}]+|[^\p{L}']+$/gu, ''); if (/^\p{Ll}/u.test(c)) lower.add(c.toLowerCase()); else if (i && !/[.?!:]$/.test(a[i - 1]) && /^\p{Lu}\p{Ll}/u.test(c)) caps.add(c.toLowerCase()); });
  const proper = new Set([...caps].filter((w) => !lower.has(w)));
  copy = { entries, exact: new Set(entries.map((e) => e.replace(/\s+/g, ' ').trim().replace(/\.$/, ''))), toks: entries.map((e) => ({ t: tok(e), s: new Set(tok(e)) })), tok, proper };
}
function copyMatch(text) {
  const run = copy.tok(text);
  if (!run.length) return 1;
  let best = 0;
  for (const e of copy.toks) {
    let shared = 0;
    for (const t of run) if (e.s.has(t)) shared++;
    if (shared / run.length < 0.5) continue;
    const prev = new Array(e.t.length + 1).fill(0);
    for (let i = 1; i <= run.length; i++) {
      let diag = 0;
      for (let j = 1; j <= e.t.length; j++) { const tmp = prev[j]; prev[j] = run[i - 1] === e.t[j - 1] ? diag + 1 : Math.max(prev[j], prev[j - 1]); diag = tmp; }
    }
    best = Math.max(best, prev[e.t.length] / run.length);
    if (best >= 0.9) break;
  }
  return best;
}
function caseOffenders(text) {
  const words = text.split(/\s+/);
  let cands = 0;
  const caps = [];
  for (let i = 1; i < words.length; i++) {
    if (/[.?!:|/&\u2013\u2014-]$/.test(words[i - 1])) continue;
    const w = words[i].replace(/^[^\p{L}]+|[^\p{L}']+$/gu, '');
    if ((w.match(/\p{L}/gu) || []).length < 4 || w === w.toUpperCase() || (copy && copy.proper.has(w.toLowerCase()))) continue;
    cands++;
    if (/^\p{Lu}/u.test(w)) caps.push(w);
  }
  return cands && caps.length / cands > 0.5 ? caps : null;
}

// ---------- browser ----------
let page, current = {};
const consoleLog = [];
const loadedWidths = new Set();
async function ev(expr, timeoutMs = 30000) {
  const r = await page.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true }, timeoutMs);
  if (r.exceptionDetails) throw new Error(`page: ${(r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text}`.split('\n')[0]);
  return r.result.value;
}
const J = (v) => JSON.stringify(v);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const key = async (k, code) => {
  await page.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: k, code: k, windowsVirtualKeyCode: code, nativeVirtualKeyCode: code });
  await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code: k, windowsVirtualKeyCode: code, nativeVirtualKeyCode: code });
};
const net = { inflight: new Set(), last: Date.now(), loader: null, status: null };
// Viewport shot at 1x of the scrolled position. A full DPR 2 frame of a photo-heavy page exceeds
// what Node's WebSocket accepts in one message and closes the CDP socket.
const shoot = (y, vw, vh) => page.send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y, width: vw, height: vh, scale: 0.5 } }, 60000);

async function setViewport(w) {
  const h = w < 768 ? 812 : w < 1024 ? 1024 : 900;
  await page.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 2, mobile: false });
}
async function load(url, w) {
  await setViewport(w);
  loadedWidths.add(w);
  const u = new URL(url);
  u.searchParams.set('wcb', Date.now().toString(36));
  net.status = null;
  const loaded = page.waitFor('Page.loadEventFired', 30000);
  const nav = await page.send('Page.navigate', { url: u.href });
  if (nav.errorText) return `navigation failed: ${nav.errorText}`;
  net.loader = nav.loaderId;
  if (!(await loaded)) return 'load event did not fire within 30s';
  const t0 = Date.now();
  while (Date.now() - t0 < 6000) {
    const idle = Date.now() - net.last;
    if ((net.inflight.size === 0 && idle > 500) || (net.inflight.size <= 2 && idle > 1500)) break;
    await wait(100);
  }
  if (net.status && net.status !== 200) return `document returned HTTP ${net.status}`;
  await ev(`(${PAGE_SRC})(${J({ ignore: opt.ignore })})`);
  return null;
}

async function click(i) {
  const p = await ev(`__webcheck.clickPoint(${i})`);
  if (p.hit) {
    await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: p.x, y: p.y });
    await page.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: p.x, y: p.y, button: 'left', clickCount: 1 });
    await page.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: p.x, y: p.y, button: 'left', clickCount: 1 });
  } else await ev(`__webcheck.nativeClick(${i})`);
}
// Park the pointer off the control so a hover-opened menu can close.
async function unhover() {
  const v = await ev('({ x: 2, y: innerHeight - 2 })');
  await page.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: v.x, y: v.y });
}
// Stable twice running and no finite CSS transition or animation still playing: a max-height
// panel keeps the same visible height for most of its transition.
async function settleOn(expr) {
  let prev = null;
  for (let k = 0; k < 25; k++) {
    await wait(120);
    const [v, busy] = await ev(`[${expr}, __webcheck.busy()]`);
    const s = J(v);
    if (s === prev && !busy && k > 1) return;
    prev = s;
  }
}

const layoutFails = (L) => [...L.overflow.map((o) => `overflow ${o.el} right ${o.right}`), ...L.escapes.map((o) => `escapes viewport ${o.el} ${o.left}..${o.right}`), ...L.containment.map((c) => `${c.el} escapes ${c.parent} by ${c.px}px`)];

async function checkLayout(R, w, overlapWidths) {
  const L = await ev('__webcheck.layout()');
  const docOver = L.scrollWidth > L.vw + 1;
  R('layout.overflow', docOver ? 'fail' : 'pass', docOver ? `page scrolls sideways: scrollWidth ${L.scrollWidth} > ${L.vw}; ${L.overflow.map((o) => o.el).slice(0, 3).join('; ')}` : `no horizontal overflow (${L.checked} elements)`, { overflow: L.overflow, htmlOverflowX: L.htmlOverflowX, bodyOverflowX: L.bodyOverflowX });
  R('layout.escape', L.escapes.length ? 'fail' : 'pass', L.escapes.length ? `${L.escapes.length} element(s) cut off at the viewport edge: ${L.escapes.slice(0, 3).map((e) => `${e.el} (${e.left}..${e.right})`).join('; ')}` : 'nothing cut off at the viewport edge', L.escapes);
  R('layout.containment', L.containment.length ? 'fail' : 'pass', L.containment.length ? `${L.containmentTotal} element(s) escape their parent: ${L.containment.slice(0, 3).map((c) => `${c.el} by ${c.px}px`).join('; ')}` : 'every in-flow element fits inside its parent', L.containment);
  R('layout.clipped', L.clipped.length ? 'fail' : 'pass', L.clipped.length ? `${L.clipped.length} box(es) clip their text: ${L.clipped.slice(0, 3).map((c) => `${c.el} cuts ${c.px}px`).join('; ')}` : 'no text clipped by overflow', L.clipped);
  const O = await ev('__webcheck.overlaps()');
  R('layout.overlap', O.hits.length ? 'fail' : 'pass', O.hits.length ? `${O.hits.length} absolute text block pair(s) overlap: ${O.hits.slice(0, 2).map((h) => `${h.a} x ${h.b} (${h.overlap}px)`).join('; ')}` : `no overlapping absolute text blocks (${O.checked} checked${O.near.length ? `, ${O.near.length} within 40px: band swept` : ''})`, O);
  if (O.hits.length || O.near.length) overlapWidths.push(w);
}

async function checkImages(R, lcp, sizes) {
  const imgs = await ev('__webcheck.images()', 90000);
  for (const i of imgs) {
    if (!/^https?:/.test(i.src) || sizes.has(i.src)) continue;
    sizes.set(i.src, fetch(i.src, { method: 'HEAD', signal: AbortSignal.timeout(10000) }).then((r) => Number(r.headers.get('content-length')) || null).catch(() => null));
  }
  for (const i of imgs) i.bytes = sizes.has(i.src) ? await sizes.get(i.src) : null;
  const broken = imgs.filter((i) => i.broken);
  const rated = imgs.filter((i) => i.ratio !== null);
  const up = rated.filter((i) => i.ratio < 1), soft = rated.filter((i) => i.ratio >= 1 && i.ratio < 1.8);
  // With srcset the browser already picked the candidate for DPR 2, and candidate steps can reach
  // about 3.2x, so only a ratio over 4 means the set lacks a small enough file.
  // A small file over the ratio costs little, so it warns; a big one fails.
  const big = rated.filter((i) => i.ratio > (i.srcset ? 4 : 3));
  const over = rated.filter((i) => (big.includes(i) && !(i.bytes < 60000)) || (i.bytes > 300000 && i.ratio > 2.2));
  const heavy = rated.filter((i) => !over.includes(i) && (i.bytes > 300000 || big.includes(i)));
  const fmt = (i) => `${i.el} ${i.natural}px for ${i.rendered}px (x${i.ratio}${i.bytes >= 1024 ? `, ${Math.round(i.bytes / 1024)}KB` : ''})`;
  R('images.broken', broken.length ? 'fail' : 'pass', broken.length ? `${broken.length} broken image(s): ${broken.slice(0, 3).map((i) => i.el).join('; ')}` : `${imgs.length} images load`, broken.map((i) => i.src));
  R('images.floor', up.length ? 'fail' : soft.length ? 'warn' : 'pass', up.length ? `${up.length} upscaled (source narrower than its box): ${up.slice(0, 3).map(fmt).join('; ')}` : soft.length ? `${soft.length} soft (under 1.8x): ${soft.slice(0, 3).map(fmt).join('; ')}` : `${rated.length} raster images at or above 1.8x of rendered width`, [...up, ...soft].map(fmt));
  R('images.ceiling', over.length ? 'fail' : heavy.length ? 'warn' : 'pass', over.length ? `${over.length} oversupplied (over 3x, 4x with srcset, and 60KB or more; or over 300KB and 2.2x): ${over.slice(0, 3).map(fmt).join('; ')}` : heavy.length ? `${heavy.length} heavy or oversized but cheap: ${heavy.slice(0, 3).map(fmt).join('; ')}` : 'no oversupplied images', [...over, ...heavy].map(fmt));
  const noDims = imgs.filter((i) => !i.bg && !i.hasDims);
  R('images.dimensions', noDims.length ? 'fail' : 'pass', noDims.length ? `${noDims.length} img without width and height attributes: ${noDims.slice(0, 3).map((i) => i.el).join('; ')}` : 'every img has width and height', noDims.map((i) => i.el));
  if (lcp) R('images.lazy-lcp', lcp.lazy ? 'fail' : 'pass', lcp.lazy ? `LCP image is loading=lazy: ${lcp.el}` : `LCP element ${lcp.tag} not lazy-loaded: ${lcp.el}`, lcp);
  const lazyTop = imgs.filter((i) => i.lazy && i.aboveFold && !(lcp && lcp.url && i.src === lcp.url));
  if (lazyTop.length) R('images.lazy-fold', 'warn', `${lazyTop.length} lazy image(s) above the fold: ${lazyTop.slice(0, 3).map((i) => i.el).join('; ')}`, lazyTop.map((i) => i.el));
}

async function checkText(R, firstPass) {
  const T = await ev('__webcheck.orphans()');
  if (!T.selftest) R('text.orphans', 'fail', 'orphan detector failed its synthetic self-test; result not trusted');
  else R('text.orphans', T.orphans.length ? 'fail' : 'pass', T.orphans.length ? `${T.orphans.length} one-word last line(s): ${T.orphans.slice(0, 3).map((o) => `${o.el} ends "${o.lastLine}"`).join('; ')}` : `no one-word last lines (${T.checked} blocks, self-test passed)`, T.orphans);
  if (T.wraps.length) R('text.hyphen-wrap', 'warn', `${T.wraps.length} hyphenated word(s) split across lines: ${T.wraps.slice(0, 3).map((x) => x.words.join(',')).join('; ')}`, T.wraps);
  if (!firstPass) return;
  const H = await ev('__webcheck.headingTexts()');
  const caseBad = [], stops = [];
  for (const h of H) {
    const clean = h.text.replace(/\s+/g, ' ').trim();
    if (h.kind !== 'nav' && h.kind !== 'button' && /[^.]\.$/.test(clean)) stops.push(`${h.el}`);
    if (h.kind === 'label' || h.transform === 'uppercase') continue;
    if (h.transform === 'capitalize') { caseBad.push(`${h.el} (CSS text-transform: capitalize)`); continue; }
    if (copy && copy.exact.has(clean.replace(/\.$/, ''))) continue;
    const off = caseOffenders(clean);
    if (off) caseBad.push(`${h.el} [${off.join(', ')}]`);
  }
  R('text.case', caseBad.length ? (copy ? 'fail' : 'warn') : 'pass', caseBad.length ? `${caseBad.length} heading-tier line(s) not in Sentence case${copy ? '' : ' (no --copy, so proper nouns unknown)'}: ${caseBad.slice(0, 3).join('; ')}` : `${H.length} heading-tier lines in Sentence case`, caseBad);
  R('text.full-stop', stops.length ? 'fail' : 'pass', stops.length ? `${stops.length} heading(s) end in a full stop: ${stops.slice(0, 3).join('; ')}` : 'no heading ends in a full stop', stops);
  const res = await ev(`__webcheck.residue(${J(RESIDUE)}, ${J(DEFAULT_LABELS)})`);
  R('text.residue', res.found.length || res.exact.length ? 'fail' : 'pass', res.found.length || res.exact.length ? `template residue on the rendered page: ${[...res.found, ...res.exact.map((x) => x.text)].join('; ')}` : 'no template residue in rendered text', res);
  if (copy) {
    const runs = await ev('__webcheck.copyRuns()');
    const un = runs.map((r) => ({ ...r, score: copyMatch(r.text) })).filter((r) => r.score < 0.9);
    R('text.copy', un.length ? 'fail' : 'pass', un.length ? `${un.length} visible text run(s) match nothing in the copy map: ${un.slice(0, 3).map((u) => `"${u.text.slice(0, 50)}"`).join('; ')}` : `${runs.length} text runs of 4+ words all match the copy map`, un.slice(0, 40).map((u) => ({ el: u.el, text: u.text.slice(0, 160), score: Math.round(u.score * 100) / 100 })));
  }
}

async function checkA11y(R) {
  const S = await ev('__webcheck.a11yStatic()');
  const hBad = S.h1 !== 1 || S.jumps.length;
  R('a11y.headings', hBad ? 'fail' : 'pass', hBad ? `${S.h1} visible h1${S.jumps.length ? `; skipped levels: ${S.jumps.slice(0, 3).map((j) => `${j.from} to ${j.to} at ${j.el}`).join('; ')}` : ''}` : `one h1, ${S.headings} headings in order`, S.jumps);
  const lm = S.landmarks;
  R('a11y.landmarks', lm.main !== 1 ? 'fail' : !lm.nav || !lm.banner || !lm.contentinfo ? 'warn' : 'pass', lm.main !== 1 ? `${lm.main} main landmarks (need exactly one)` : !lm.nav || !lm.banner || !lm.contentinfo ? `missing landmark(s): ${['nav', 'banner', 'contentinfo'].filter((k) => !lm[k]).join(', ')}` : 'main, nav, banner and contentinfo present', lm);
  R('a11y.alt', S.noAlt.length ? 'fail' : S.fileAlt.length ? 'warn' : 'pass', S.noAlt.length ? `${S.noAlt.length} img without alt: ${S.noAlt.slice(0, 3).join('; ')}` : S.fileAlt.length ? `${S.fileAlt.length} alt text(s) look like file names: ${S.fileAlt.slice(0, 3).join('; ')}` : 'every image has alt', [...S.noAlt, ...S.fileAlt]);
  const lab = [...S.unlabelled, ...S.badFor];
  R('a11y.labels', lab.length ? 'fail' : 'pass', lab.length ? `${lab.length} form label problem(s): ${lab.slice(0, 3).join('; ')}` : 'every form field has a label', lab);
  const { nodes } = await page.send('Accessibility.getFullAXTree', {}, 60000);
  const roles = new Set(['link', 'button', 'textbox', 'searchbox', 'combobox', 'listbox', 'checkbox', 'radio', 'switch', 'slider', 'spinbutton', 'menuitem', 'tab', 'image', 'img']);
  const nameless = [];
  for (const n of nodes) {
    if (n.ignored || !roles.has(n.role && n.role.value) || ((n.name && n.name.value) || '').trim() || !n.backendDOMNodeId) continue;
    try {
      const { object } = await page.send('DOM.resolveNode', { backendNodeId: n.backendDOMNodeId });
      const d = await page.send('Runtime.callFunctionOn', { objectId: object.objectId, functionDeclaration: 'function(){return window.__webcheck.desc(this)}', returnByValue: true });
      nameless.push(`${n.role.value}: ${d.result.value}`);
    } catch { nameless.push(`${n.role.value}: (node ${n.backendDOMNodeId})`); }
    if (nameless.length >= 25) break;
  }
  R('a11y.names', nameless.length ? 'fail' : 'pass', nameless.length ? `${nameless.length} control(s) or image(s) with no accessible name: ${nameless.slice(0, 3).join('; ')}` : 'every link, button, field and image has an accessible name (browser AX tree)', nameless);
  if (opt.axe) {
    await ev(readFileSync(opt.axe, 'utf8') + '\n;true', 60000);
    const v = await ev("axe.run(document, { resultTypes: ['violations'] }).then(r => r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, first: v.nodes[0] && v.nodes[0].target.join(' ') })))", 120000);
    const bad = v.filter((x) => x.impact === 'critical' || x.impact === 'serious');
    R('a11y.axe', bad.length ? 'fail' : v.length ? 'warn' : 'pass', v.length ? `${bad.length} serious or critical, ${v.length - bad.length} other axe violation(s): ${v.slice(0, 3).map((x) => `${x.id} (${x.nodes})`).join('; ')}` : 'axe-core: no violations', v);
  }
  // Keyboard walk with real Tab key events.
  const base = await ev('__webcheck.focusBaseline()');
  const stops = [];
  let first = null, prev = null, same = 0, frames = 0, trap = null;
  for (let k = 0; k < 250; k++) {
    await key('Tab', 9);
    const p = await ev('__webcheck.focusProbe()');
    if (p.body) { if (stops.length) break; continue; }
    if (p.id === first) break;
    if (first === null) first = p.id;
    if (p.id === prev) {
      if (p.tag === 'IFRAME') { if (++frames > 60) break; continue; }
      if (++same >= 3) { trap = p.el; break; }
      continue;
    }
    if (stops.some((s) => s.id === p.id)) { trap = p.el; break; }
    same = 0; prev = p.id;
    stops.push(p);
  }
  const counted = stops.filter((s) => !s.ignored);
  const noRing = counted.filter((s) => s.visible && !s.indicator).map((s) => s.el);
  const hidden = counted.filter((s) => !s.visible).map((s) => s.el);
  R('a11y.focus-visible', noRing.length ? 'fail' : 'pass', noRing.length ? `${noRing.length} of ${counted.length} tab stop(s) show no focus indicator: ${noRing.slice(0, 3).join('; ')}` : `${counted.length} tab stops, each with a visible focus change`, noRing);
  R('a11y.focus-hidden', hidden.length ? 'fail' : 'pass', hidden.length ? `focus lands on ${hidden.length} element(s) you cannot see: ${hidden.slice(0, 3).join('; ')}` : 'focus never lands on a hidden element', hidden);
  R('a11y.focus-trap', trap ? 'fail' : 'pass', trap ? `keyboard focus loops at ${trap}` : 'no keyboard trap', { stops: stops.length });
  const unreached = await ev('__webcheck.unreached()');
  if (unreached.length || S.positive.length) R('a11y.focus-order', 'warn', `${unreached.length ? `${unreached.length} of ${base.tabbable} visible focusables never reached by Tab` : ''}${S.positive.length ? ` ${S.positive.length} positive tabindex (breaks logical order)` : ''}`.trim(), { unreached: unreached.slice(0, 15), positive: S.positive });
  await ev('document.activeElement && document.activeElement.blur && document.activeElement.blur(), scrollTo(0,0), true');
  // Contrast from real pixels: hide text, screenshot each viewport chunk, sample under each line.
  const targets = await ev('__webcheck.contrastTargets(500)');
  await ev('__webcheck.hideText(true)');
  const done = new Map();
  let lastY = -1;
  try {
    for (let y = 0; y < 30000; ) {
      const c = await ev(`__webcheck.contrastChunk(${y}, ${J([...done.keys()])})`);
      if (c.scrollY === lastY) break;
      lastY = c.scrollY;
      const items = c.items;
      if (items.length) {
        const shot = await shoot(c.scrollY, c.vw, c.vh);
        const img = decodePng(Buffer.from(shot.data, 'base64'));
        const scale = img.width / c.vw;
        for (const it of items) {
          const t = targets[it.i];
          const ratios = [];
          for (const r of it.rects.slice(0, 3)) for (const fx of [0.1, 0.3, 0.5, 0.7, 0.9]) for (const fy of [0.25, 0.5, 0.75]) {
            const bg = img.at((r.left + fx * r.width) * scale, (r.top + fy * r.height) * scale);
            ratios.push(contrast(blend(t.color, t.alpha, bg), bg));
          }
          ratios.sort((a, b) => a - b);
          done.set(it.i, Math.round(ratios[Math.floor(ratios.length * 0.1)] * 100) / 100);
        }
      }
      y = c.scrollY + Math.floor(c.vh * 0.9);
    }
  } finally { await ev('__webcheck.hideText(false), scrollTo(0,0), true'); }
  const low = [...done].filter(([i, r]) => r < (targets[i].large ? 3 : 4.5)).map(([i, r]) => `${targets[i].el} ${r}:1 (needs ${targets[i].large ? 3 : 4.5})`);
  R('a11y.contrast', low.length ? 'fail' : 'pass', low.length ? `${low.length} text block(s) below AA on sampled pixels: ${low.slice(0, 3).join('; ')}` : `${done.size} text blocks meet AA on sampled pixels`, low.slice(0, 30));
  if (done.size < targets.length) R('a11y.contrast-coverage', 'warn', `${targets.length - done.size} of ${targets.length} text blocks never sampled: covered by other content, scroll-jacked, or taller than the viewport`);
}

async function checkState(R, w, withForms, withDisclosures) {
  await ev('__webcheck.guardSubmits()');
  const neg = await ev('__webcheck.negatives()');
  R('state.negative', neg.length ? 'fail' : 'pass', neg.length ? `${neg.length} empty, error or success state visible on a fresh load: ${neg.slice(0, 3).map((n) => `${n.el}`).join('; ')}` : 'no empty, error or success state showing on load', neg);
  if (withForms) {
    const forms = await ev('__webcheck.forms()');
    for (const f of forms) {
      if (f.emptyNames.length || f.dupNames.length) R('state.form-names', 'fail', `${f.el}: ${[f.emptyNames.length ? `${f.emptyNames.length} field(s) without a name` : '', f.dupNames.length ? `duplicate name(s) ${f.dupNames.join(', ')}` : ''].filter(Boolean).join('; ')}`, f);
      if (!f.invalidWhenEmpty) { R('state.form-validation', 'warn', `${f.el}: no required fields, so an empty submit would send`); continue; }
      await ev('__webcheck.markVisible(-1)');
      await ev(`__webcheck.formValidate(${f.i})`);
      await wait(400);
      const E = await ev(`__webcheck.formErrors(${f.i})`);
      const L = layoutFails(await ev('__webcheck.layout()'));
      if (L.length) R('state.form-layout', 'fail', `${f.el} in its validation state: ${L.slice(0, 3).join('; ')}`, L);
      R('state.form-validation', E.unassociated.length ? 'warn' : 'pass', E.unassociated.length ? `${f.el}: ${E.unassociated.length} of ${E.invalid} invalid field(s) have no associated error text (aria-describedby or aria-errormessage)` : `${f.el}: ${E.invalid} invalid field(s) each carry an associated error`, E);
    }
  }
  const ctrls = await ev(`__webcheck.controls(${withDisclosures}, 8)`);
  if (ctrls.length) { await ev('__webcheck.markVisible(-1)'); await wait(1200); await ev('__webcheck.markNoise()'); }
  const open = async (i) => { await ev(`__webcheck.markVisible(${i})`); await click(i); await settleOn(`__webcheck.revealed(${i})`); return ev(`__webcheck.openState(${i})`); };
  let ok = 0, tested = 0;
  for (const c of ctrls) {
    const tag = `${c.kind} ${c.el}`;
    const before = results.length;
    // A hover-opened dropdown can close again on the click itself, so a blank first click gets a second.
    let st = await open(c.i);
    if (!st.revealed) st = await open(c.i);
    if (!st.revealed) { R('state.toggle', st.declared ? 'fail' : 'warn', `${tag}: clicking revealed nothing at ${w}px${st.declared ? ' although it declares aria-expanded or aria-controls' : ''}`); continue; }
    tested++;
    if (st.expanded === null && !st.isSummary) R('state.aria', 'fail', `${tag}: opens content but has no aria-expanded`);
    else if (st.hasTarget && String(st.targetShown) !== st.expanded) R('state.aria', 'fail', `${tag}: aria-expanded="${st.expanded}" but its aria-controls target is ${st.targetShown ? 'shown' : 'hidden'}`);
    else if (!st.hasTarget && st.expanded !== null && st.expanded !== 'true') R('state.aria', 'fail', `${tag}: aria-expanded stays "${st.expanded}" while open`);
    if (st.offscreen.length) R('state.menu-links', 'fail', `${tag}: ${st.offscreen.length} of ${st.links} link(s) outside the viewport when open: ${st.offscreen.slice(0, 3).join('; ')}`, st.offscreen);
    const L = layoutFails(await ev('__webcheck.layout()'));
    if (L.length) R('state.open-layout', 'fail', `${tag} open: ${L.slice(0, 3).join('; ')}`, L);
    await click(c.i);
    await unhover();
    await settleOn('__webcheck.openSig()');
    if (await ev('__webcheck.stillOpen()')) R('state.close', 'fail', `${tag}: a second click does not close it`);
    else if (c.kind === 'nav' || c.dropdown) {
      await open(c.i);
      await unhover();
      await ev('__webcheck.escape()');
      await settleOn('__webcheck.openSig()');
      if (await ev('__webcheck.stillOpen()')) { R('state.close', 'fail', `${tag}: Escape does not close it`); await click(c.i); await unhover(); await settleOn('__webcheck.openSig()'); }
    }
    const after = await ev(`__webcheck.controlState(${c.i})`);
    if (after.expanded === 'true') R('state.aria', 'fail', `${tag}: aria-expanded stays "true" after closing`);
    if (results.slice(before).every((r) => r.status !== 'fail')) ok++;
  }
  if (tested && ok === tested) R('state.toggle', 'pass', `${tested} menu or disclosure control(s) opened, measured and closed cleanly at ${w}px`);
  const blocked = await ev('__webcheck.guardSubmits()');
  if (blocked) R('state.submit-blocked', 'warn', `${blocked} form submission(s) fired while testing controls and were blocked: a disclosure control submits its form`);
}

async function checkCompleteness(R, pageKey, w) {
  const waivers = inv.waivers || [];
  for (const [vp, secs] of Object.entries(inv.pages[pageKey])) {
    if (inv.viewports[vp] !== w) continue;
    const rows = await ev(`__webcheck.completeness(${J(secs)})`);
    let maxTop = -1;
    const table = [], bad = [];
    rows.forEach((row, k) => {
      const want = secs[k].photos || 0;
      const inOrder = row.present ? row.top >= maxTop - 1 : null;
      if (row.present) maxTop = Math.max(maxTop, row.top);
      const problems = [];
      if (row.error) problems.push(row.error);
      else if (!row.present) problems.push(row.matched ? `${row.matched} match(es), none rendered` : 'not built');
      else {
        if (!inOrder) problems.push('out of design order');
        if (row.photos < want) problems.push(`photos ${row.photos}/${want}`);
        if (row.missing.length) problems.push(`missing ${row.missing.join(', ')}`);
      }
      const wv = waivers.find((x) => x.section === row.section && (!x.page || x.page === pageKey) && (!x.viewport || x.viewport === vp));
      const waived = problems.length && wv && wv.reason && wv.approver;
      if (problems.length && wv && !waived) problems.push('waiver lacks reason or approver');
      table.push({ row: row.section, viewport: vp, selector: row.selector, present: row.present ? 'Y' : 'N', order: inOrder === null ? '-' : inOrder ? 'OK' : 'NO', photos: `${row.photos ?? 0}/${want}`, missing: row.missing || [], waiver: waived ? `${wv.approver}: ${wv.reason}` : undefined });
      if (problems.length && !waived) bad.push(`${row.section}: ${problems.join(', ')}`);
    });
    R('completeness.inventory', bad.length ? 'fail' : 'pass', bad.length ? `${vp} ${bad.length} of ${rows.length} designed section(s) fail: ${bad.slice(0, 6).join('; ')}` : `${vp}: all ${rows.length} designed sections present, in order, photos met${table.some((t) => t.waiver) ? ' (with named waivers)' : ''}`, table);
  }
  const missingVp = Object.keys(inv.viewports).filter((vp) => !inv.pages[pageKey][vp]);
  if (missingVp.length && w === Math.max(...Object.keys(inv.pages[pageKey]).map((vp) => inv.viewports[vp]))) R('completeness.viewports', 'warn', `no ${missingVp.join(', ')} inventory for this page: that twin was not checked`);
}

// Viewport screenshot at a failing width, reloaded first when the state step changed the page.
async function snapshot(R, url, w, reload, y) {
  if (reload && (await load(url, w))) return;
  const vp = await ev(`(scrollTo(0, ${y}), { y: scrollY, vw: document.documentElement.clientWidth, vh: innerHeight })`);
  const shot = await shoot(vp.y, vp.vw, vp.vh);
  const file = join(outDir, `shot-${(pathOf(url).replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'home')}-${w}.png`);
  writeFileSync(file, Buffer.from(shot.data, 'base64'));
  R('screenshot', 'info', `viewport screenshot of the failing width${y ? ` at y ${vp.y}` : ''}`, file);
}

async function runBrowser(plan) {
  let v, browser;
  try { v = await ensureChrome(opt.port); browser = await connect(v.webSocketDebuggerUrl); } catch (e) { add('browser', 'error', e.message); return null; }
  const onEvent = (m) => {
    const p = m.params || {};
    if (m.method === 'Network.requestWillBeSent') { net.inflight.add(p.requestId); net.last = Date.now(); }
    else if (m.method === 'Network.loadingFinished' || m.method === 'Network.loadingFailed') { net.inflight.delete(p.requestId); net.last = Date.now(); }
    else if (m.method === 'Network.responseReceived' && p.type === 'Document' && p.loaderId === net.loader) net.status = p.response.status;
    else if (m.method === 'Runtime.exceptionThrown') consoleLog.push({ ...current, text: ((p.exceptionDetails.exception && p.exceptionDetails.exception.description) || p.exceptionDetails.text || '').split('\n')[0] });
    else if (m.method === 'Runtime.consoleAPICalled' && (p.type === 'error' || p.type === 'assert')) consoleLog.push({ ...current, text: p.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 300) });
    else if (m.method === 'Log.entryAdded' && p.entry.level === 'error') consoleLog.push({ ...current, text: `${p.entry.text}${p.entry.url ? ` ${p.entry.url}` : ''}`.slice(0, 300) });
  };
  // A fresh page in its own browser context. Also the recovery path when a page hangs.
  const attach = async () => {
    if (page) await page.close().catch(() => {});
    page = await openPage(browser);
    page.onEvent(onEvent);
    net.inflight.clear();
    for (const d of ['Page.enable', 'Runtime.enable', 'Log.enable', 'Network.enable', 'DOM.enable', 'Accessibility.enable']) await page.send(d);
    await page.send('Network.setCacheDisabled', { cacheDisabled: true });
    await page.send('Emulation.setFocusEmulationEnabled', { enabled: true });
    await page.send('Emulation.setScrollbarsHidden', { hidden: true }).catch(() => {});
    await page.send('Page.bringToFront').catch(() => {});
  };
  // Returns false when the browser itself is gone (another session restarted the shared Chrome).
  const recover = async (e) => {
    if (browser.closed) { add('browser', 'error', `debug Chrome went away mid-run (${e.message}); another session may have restarted it. Rerun.`); return false; }
    try { await attach(); return true; } catch (e2) { add('browser', 'error', `could not reopen a page after "${e.message}": ${e2.message}`); return false; }
  };
  try {
    try { await attach(); } catch (e) { add('browser', 'error', `debug Chrome on port ${opt.port} answers but cannot open a page (${e.message}); restart it or rerun with --html-only`); return v.Browser; }
    const sizes = new Map();
    outer: for (const [url, { widths, pageKey }] of plan) {
      const general = [...widths].filter(([, s]) => [...s].some((c) => c !== 'completeness')).map(([w]) => w);
      const near = (t) => general.reduce((b, w) => (Math.abs(w - t) < Math.abs(b - t) ? w : b), general[0]);
      const focusW = new Set(general.length ? [near(1440), near(375)] : []);
      const textW = general.length ? near(1440) : null;
      const overlapWidths = [];
      const sorted = [...widths.keys()].sort((a, b) => a - b);
      for (const w of sorted) {
        const set = widths.get(w);
        current = { page: url, width: w };
        const R = (check, status, message, evidence) => add(check, status, message, { page: url, width: w, evidence });
        const failsBefore = results.filter((r) => r.status === 'fail').length;
        try {
          const err = await load(url, w);
          if (err) { R('load', 'fail', err); continue; }
          let vp = await ev('__webcheck.viewport()');
          if (vp.visibilityState !== 'visible') { await page.send('Page.bringToFront').catch(() => {}); vp = await ev('__webcheck.viewport()'); }
          if (vp.innerWidth !== w || vp.visibilityState !== 'visible') { R('layout.viewport', 'fail', `measurement invalid: innerWidth ${vp.innerWidth} for ${w}, visibility ${vp.visibilityState}`); continue; }
          const step = async (name, fn) => { try { await fn(); } catch (e) { if (/timed out|socket closed/.test(e.message)) throw e; R(name, 'error', e.message); } };
          const lcp = set.has('images') ? await ev('__webcheck.lcp()').catch(() => null) : null;
          await ev('__webcheck.settle()', 90000);
          if (set.has('layout')) await step('layout', () => checkLayout(R, w, overlapWidths));
          if (set.has('text')) await step('text', () => checkText(R, w === textW));
          if (set.has('images')) await step('images', () => checkImages(R, lcp, sizes));
          if (set.has('completeness')) await step('completeness', () => checkCompleteness(R, pageKey, w));
          if (set.has('a11y') && focusW.has(w)) await step('a11y', () => checkA11y(R));
          if (set.has('state')) await step('state', () => checkState(R, w, focusW.has(w), focusW.has(w)));
          if (results.filter((r) => r.status === 'fail').length > failsBefore) await snapshot(R, url, w, set.has('state'), 0).catch(() => {});
        } catch (e) {
          R('browser', 'error', `stopped at this width: ${e.message}`);
          if (!(await recover(e))) break outer;
        }
      }
      // L-106: sweep 20px steps through each band next to a width with a near or overlapping pair.
      const bands = new Set();
      for (const w of overlapWidths) {
        const k = sorted.indexOf(w);
        if (k > 0) bands.add(`${sorted[k - 1]}-${w}`);
        if (k < sorted.length - 1) bands.add(`${w}-${sorted[k + 1]}`);
      }
      for (const band of bands) {
        const [lo, hi] = band.split('-').map(Number);
        current = { page: url, width: band };
        try {
          const err = await load(url, lo);
          if (err) throw new Error(err);
          await ev('__webcheck.settle()', 90000);
          const hits = [];
          for (let x = lo + 20; x < hi; x += 20) {
            await setViewport(x);
            await wait(200);
            const O = await ev('__webcheck.overlaps()');
            if (O.hits.length) hits.push({ width: x, pairs: O.hits.slice(0, 3) });
          }
          const RB = (check, status, message, evidence) => add(check, status, message, { page: url, width: band, evidence });
          RB('layout.overlap-band', hits.length ? 'fail' : 'pass', hits.length ? `absolute text blocks collide between breakpoints at ${hits.map((h) => h.width).join(', ')}px: ${hits[0].pairs.map((p) => `${p.a} x ${p.b}`).join('; ')}` : `swept ${lo} to ${hi} in 20px steps: no collision`, hits);
          if (hits.length) { await setViewport(hits[0].width); await wait(200); await snapshot(RB, url, hits[0].width, false, Math.max(0, hits[0].pairs[0].y - 100)).catch(() => {}); }
        } catch (e) { add('layout.overlap-band', 'error', e.message, { page: url, width: band }); }
      }
      if (opt.checks.has('console')) {
        const mine = consoleLog.filter((c) => c.page === url);
        const uniq = [...new Map(mine.map((c) => [c.text, c])).values()];
        add('console.errors', uniq.length ? 'fail' : 'pass', uniq.length ? `${uniq.length} distinct console error(s): ${uniq.slice(0, 3).map((c) => c.text.slice(0, 120)).join(' | ')}` : `no console errors across ${sorted.length} load(s)`, { page: url, evidence: uniq.map((c) => ({ text: c.text, widths: [...new Set(mine.filter((m) => m.text === c.text).map((m) => m.width))] })) });
      }
    }
    return v.Browser;
  } finally {
    if (page) await page.close().catch(() => {});
    browser.close();
  }
}

// ---------- main ----------
const browserChecks = [...opt.checks].filter((c) => c !== 'served');
let chrome = null;
if (opt.checks.has('served')) {
  try { await servedChecks(opt.urls.slice(), { lang: opt.lang, noindex: opt.noindex, sitemap: opt.sitemap, expect: opt.expect, absent: opt.absent, waive: opt.waive }, add); }
  catch (e) { add('served', 'error', e.message); }
}
if (opt.htmlOnly) { if (browserChecks.length) add('browser', 'skip', `--html-only: skipped ${browserChecks.join(', ')}`); }
else if (browserChecks.length) {
  const plan = new Map();
  const want = (url, w, c, pageKey) => {
    if (!plan.has(url)) plan.set(url, { widths: new Map(), pageKey: null });
    const p = plan.get(url);
    if (pageKey) p.pageKey = pageKey;
    if (!p.widths.has(w)) p.widths.set(w, new Set());
    p.widths.get(w).add(c);
  };
  for (const u of opt.urls) for (const w of opt.widths) for (const c of browserChecks) if (c !== 'completeness') want(u, w, c);
  if (inv && browserChecks.includes('completeness')) for (const [key, url] of inv.urls) for (const vp of Object.keys(inv.pages[key])) want(url, inv.viewports[vp], 'completeness', key);
  try { chrome = await runBrowser(plan); } catch (e) { add('browser', 'error', `browser run stopped: ${e.message}`); }
}

const count = (s) => results.filter((r) => r.status === s).length;
const ran = [...new Set(results.filter((r) => ['pass', 'fail', 'warn'].includes(r.status)).map((r) => r.check.split('.')[0]))].filter((c) => ALL.includes(c));
if (!count('pass') && !count('fail')) add('webcheck', 'error', 'no check produced a pass or fail result, so this report proves nothing');
const summary = { pass: count('pass'), fail: count('fail'), warn: count('warn'), error: count('error'), skip: count('skip') };
const verdict = summary.fail ? 'FAIL' : summary.error ? 'ERROR' : 'PASS';
const report = { tool: 'webcheck', version: 1, verdict, job, started: started.toISOString(), finished: new Date().toISOString(), chrome, urls: opt.urls, widths: opt.widths, checks: [...opt.checks], checksRun: ran, inventory: opt.inventory || null, copy: opt.copy || null, waivers: opt.waive, summary, results };
const reportPath = join(outDir, 'report.json');
writeFileSync(reportPath, JSON.stringify(report, null, 1));
const where = (r) => `${r.page ? pathOf(r.page) : ''}${r.width ? ` @${r.width}` : ''}`;
const lines = [`webcheck ${verdict}: ${summary.fail} fail, ${summary.error} error, ${summary.warn} warn, ${summary.pass} pass | ${new Set([...opt.urls, ...(inv ? inv.urls.values() : [])]).size} page(s), widths ${loadedWidths.size ? [...loadedWidths].sort((a, b) => a - b).join(',') : 'none (no browser)'} | checks run ${ran.join(',') || 'none'}`];
const bad = results.filter((r) => r.status === 'fail' || r.status === 'error');
for (const r of bad.slice(0, 40)) lines.push(`${r.status.toUpperCase()} ${r.check} ${where(r)}: ${r.message}`);
if (bad.length > 40) lines.push(`... ${bad.length - 40} more in the report`);
const warns = results.filter((r) => r.status === 'warn');
for (const r of warns.slice(0, 12)) lines.push(`WARN ${r.check} ${where(r)}: ${r.message}`);
if (warns.length > 12) lines.push(`... ${warns.length - 12} more warnings in the report`);
lines.push(`report: ${reportPath}`);
writeFileSync(join(outDir, 'summary.txt'), `${lines.join('\n')}\n`);
console.log(lines.join('\n'));
process.exit(summary.fail ? 1 : summary.error ? 2 : 0);
