// Served-HTML checks (F9): cache-busted bytes only, no browser, so they still run when Chrome is down.
export const RESIDUE = ['lorem ipsum', 'john doe', 'jane doe', 'example text', 'this is some text inside of a div block', 'thank you! your submission has been received', 'oops! something went wrong while submitting the form', 'jor\u00e9', 'omnera'];
export const DEFAULT_LABELS = ['Heading', 'Text Link', 'Button Text', 'Block Quote', 'List Item', 'Field Label'];
const SRI_HOSTS = /(^|\.)(cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|ajax\.googleapis\.com|code\.jquery\.com)$/i;
const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0', rsquo: '\u2019', lsquo: '\u2018', ldquo: '\u201c', rdquo: '\u201d', ndash: '\u2013', mdash: '\u2014', hellip: '\u2026', copy: '\u00a9', eacute: '\u00e9' };
export const decode = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => (e[0] === '#' ? String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)) : ENT[e.toLowerCase()] ?? m));
const strip = (s) => decode(s.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();

function attrs(s) {
  const out = {};
  const re = /([^\s=/>]+)(?:\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
  for (let m; (m = re.exec(s));) out[m[1].toLowerCase()] = decode(m[3] ?? m[4] ?? m[5] ?? '');
  return out;
}

export function parseHtml(html) {
  const scripts = [];
  let body = html.replace(/<!--[\s\S]*?-->/g, '');
  body = body.replace(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi, (m, a, inner) => { scripts.push({ attrs: attrs(a), inner }); return ''; });
  body = body.replace(/<style\b[^>]*>[\s\S]*?<\/style\s*>/gi, '');
  const tags = [];
  const re = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*)\s*\/?>/g;
  for (let m; (m = re.exec(body));) tags.push({ close: !!m[1], name: m[2].toLowerCase(), attrs: m[1] ? {} : attrs(m[3] || ''), start: m.index, end: re.lastIndex });
  const inner = (t) => {
    let depth = 0;
    for (const u of tags) {
      if (u.start < t.end || u.name !== t.name) continue;
      if (!u.close) depth++;
      else if (depth-- === 0) return body.slice(t.end, u.start);
    }
    return '';
  };
  return { body, tags, scripts, inner, text: strip(body) };
}

export async function fetchFresh(url) {
  const u = new URL(url);
  u.searchParams.set('wcb', Date.now().toString(36) + Math.random().toString(36).slice(2, 6));
  const r = await fetch(u, { headers: { 'cache-control': 'no-cache', pragma: 'no-cache', 'user-agent': 'webcheck/1 (+verify)' }, redirect: 'follow', signal: AbortSignal.timeout(20000) });
  const type = r.headers.get('content-type') || '';
  const text = /html|xml|text/.test(type) ? await r.text() : (await r.arrayBuffer(), '');
  const h = (k) => r.headers.get(k);
  return { status: r.status, type, text, headers: { age: h('age'), 'x-cache': h('x-cache'), 'cache-control': h('cache-control'), 'surrogate-control': h('surrogate-control'), 'x-robots-tag': h('x-robots-tag') } };
}

async function pool(items, n, fn) {
  const out = new Array(items.length);
  let k = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { while (k < items.length) { const i = k++; out[i] = await fn(items[i]); } }));
  return out;
}
const safe = async (url) => { try { return await fetchFresh(url); } catch (e) { return { status: 0, error: String(e.message || e), text: '', headers: {} }; } };

// Webflow injects this loader itself when Google Fonts are set in site settings, so it cannot carry SRI.
const WEBFONT = /^https?:\/\/ajax\.googleapis\.com\/ajax\/libs\/webfont\//i;

export async function servedChecks(pages, opt, add) {
  // --waive "<check>|<text>|<reason>": a problem containing <text> stops counting; the reason stays in the evidence.
  const waive = (check, problems) => {
    const ws = (opt.waive || []).filter((w) => w.check === check);
    const kept = [], waived = [];
    for (const p of problems) { const w = ws.find((x) => p.includes(x.text)); if (w) waived.push({ problem: p, reason: w.reason }); else kept.push(p); }
    return { kept, waived };
  };
  const note = (waived) => (waived.length ? ` (${waived.length} waived: ${[...new Set(waived.map((w) => w.reason))].join('; ')})` : '');
  // One row from a list of problems: fails (or warns) on any problem left after waivers.
  const put = (check, level, problems, bad, good, where, evidence) => {
    const { kept, waived } = waive(check, problems);
    add(check, kept.length ? level : 'pass', kept.length ? bad(kept) : `${good}${note(waived)}`, { ...where, evidence: waived.length ? { ...evidence, waived } : evidence });
  };
  const origins = [...new Set(pages.map((p) => new URL(p).origin))];
  if (opt.sitemap) {
    for (const o of origins) {
      const sm = await safe(`${o}/sitemap.xml`);
      if (sm.status !== 200) { add('served.sitemap', 'warn', `no sitemap.xml (${sm.status || sm.error})`, { page: o }); continue; }
      const locs = [...sm.text.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/g)].map((m) => decode(m[1])).filter((u) => { try { return new URL(u).origin === o; } catch { return false; } });
      for (const u of locs.slice(0, 200)) if (!pages.includes(u)) pages.push(u);
      add('served.sitemap', 'pass', `${locs.length} sitemap URLs added`, { page: o });
    }
  }
  const meta = [];
  const linkTargets = new Map();
  const resp = await pool(pages, 6, safe);
  const onePage = (page, r) => {
    const R = (check, status, message, evidence) => add(check, status, message, { page, evidence });
    const P = (check, level, problems, bad, good, evidence) => put(check, level, problems, bad, good, { page }, evidence);
    if (r.status !== 200) { R('served.status', 'fail', `returned ${r.status || r.error}`, r.headers); return; }
    R('served.status', 'pass', `200, cache-busted (age ${r.headers.age ?? 'n/a'}, x-cache ${r.headers['x-cache'] ?? 'n/a'})`, r.headers);
    if (!/html/.test(r.type)) { R('served.type', 'fail', `not HTML (${r.type})`); return; }
    const doc = parseHtml(r.text);
    const T = (name) => doc.tags.filter((t) => !t.close && t.name === name);
    const host = new URL(page).host;
    const all = (k) => k.join('; ');

    const robots = T('meta').filter((t) => (t.attrs.name || '').toLowerCase() === 'robots').map((t) => t.attrs.content || '').join(',');
    const noindex = /noindex/i.test(robots) || /noindex/i.test(r.headers['x-robots-tag'] || '');
    const want = opt.noindex || (/\.webflow\.io$/i.test(host) ? 'expect' : '');
    if (want === 'expect') P('served.noindex', 'fail', noindex ? [] : ['staging page is indexable: noindex missing'], all, 'staging noindex present');
    else if (want === 'forbid') P('served.noindex', 'fail', noindex ? ['production page carries noindex'] : [], all, 'indexable, no noindex');

    const attrText = doc.tags.flatMap((t) => ['alt', 'title', 'placeholder', 'value', 'aria-label'].map((k) => t.attrs[k] || '')).join(' ');
    const ld = doc.scripts.filter((s) => /ld\+json/i.test(s.attrs.type || '')).map((s) => s.inner).join(' ');
    const hay = `${doc.text} ${attrText} ${ld}`.toLowerCase();
    const found = RESIDUE.filter((p) => hay.includes(p));
    const exact = [...doc.body.matchAll(/>\s*([^<>]{1,20}?)\s*</g)].map((m) => decode(m[1]).trim()).filter((t) => DEFAULT_LABELS.includes(t));
    P('served.residue', 'fail', [...found, ...new Set(exact)], (k) => `template residue in served bytes: ${all(k)}`, 'no template residue');

    const lang = (T('html')[0]?.attrs.lang || '').trim();
    const langOk = opt.lang === 'any' ? !!lang : lang.toLowerCase() === (opt.lang || 'en-AU').toLowerCase();
    P('served.lang', 'fail', langOk ? [] : [`html lang is "${lang || 'missing'}", expected ${opt.lang === 'any' ? 'a value' : opt.lang || 'en-AU'}`], all, `lang="${lang}"`);

    const levels = doc.tags.filter((t) => !t.close && /^h[1-6]$/.test(t.name)).map((t) => +t.name[1]);
    const h1 = levels.filter((l) => l === 1).length;
    const skips = levels.map((l, i) => (i && l > levels[i - 1] + 1 ? `skipped level h${levels[i - 1]} to h${l}` : null)).filter(Boolean);
    P('served.headings', 'fail', [...(h1 === 1 ? [] : [`${h1} h1 in served HTML`]), ...skips], all, 'one h1, no skipped levels');

    const title = strip(doc.inner(T('title')[0] || { end: 0, name: 'title' }) || '');
    const mv = (k) => (T('meta').find((t) => (t.attrs.name || t.attrs.property || '').toLowerCase() === k)?.attrs.content || '').trim();
    const canonical = T('link').find((t) => /(^|\s)canonical(\s|$)/i.test(t.attrs.rel || ''))?.attrs.href || '';
    const m = { title, description: mv('description'), 'og:title': mv('og:title'), 'og:description': mv('og:description'), 'og:image': mv('og:image'), 'twitter:card': mv('twitter:card'), canonical };
    const ldBad = doc.scripts.filter((s) => /ld\+json/i.test(s.attrs.type || '')).filter((s) => { try { JSON.parse(s.inner); return false; } catch { return true; } }).length;
    P('served.meta', 'fail', [...Object.entries(m).filter(([, v]) => !v).map(([k]) => `missing ${k}`), ...(ldBad ? [`${ldBad} JSON-LD block(s) do not parse`] : [])], all, 'title, description, canonical, og and twitter tags present; JSON-LD parses', m);
    meta.push({ page, ...m });

    const ids = new Set(doc.tags.map((t) => t.attrs.id).filter(Boolean));
    const labels = T('label').filter((t) => 'for' in t.attrs && (!t.attrs.for || !ids.has(t.attrs.for))).map((t) => `for="${t.attrs.for}"`);
    P('served.labels', 'fail', labels, (k) => `${k.length} label(s) point at no field: ${k.slice(0, 5).join(', ')}`, 'every label for= resolves');

    const noAlt = T('img').filter((t) => !('alt' in t.attrs)).map((t) => t.attrs.src || '(no src)');
    P('served.alt', 'fail', noAlt, (k) => `${k.length} img without an alt attribute: ${k.slice(0, 3).join(', ')}`, 'every img has an alt attribute', { missing: noAlt.slice(0, 10) });

    const third = doc.scripts.filter((s) => s.attrs.src).map((s) => ({ ...s.attrs, url: new URL(s.attrs.src, page) })).filter((s) => s.url.host !== host);
    const noSri = third.filter((s) => SRI_HOSTS.test(s.url.host) && (!s.integrity || !('crossorigin' in s))).map((s) => s.url.href);
    const hard = waive('served.sri', noSri.filter((u) => !WEBFONT.test(u))), font = waive('served.sri', noSri.filter((u) => WEBFONT.test(u)));
    const sriEv = { missing: hard.kept, webfont: font.kept, waived: [...hard.waived, ...font.waived], thirdParty: third.map((s) => s.url.host) };
    if (hard.kept.length) R('served.sri', 'fail', `${hard.kept.length} CDN script(s) without integrity plus crossorigin: ${hard.kept.slice(0, 3).join(', ')}`, sriEv);
    else if (font.kept.length) R('served.sri', 'warn', `Webflow's Google Fonts loader has no SRI (${font.kept[0]}); self-host the fonts (upload them as custom fonts in Site settings) so Webflow stops injecting it`, sriEv);
    else R('served.sri', 'pass', `static-CDN scripts carry SRI (${third.length} third-party scripts seen)${note(sriEv.waived)}`, sriEv);

    const mainAt = doc.tags.find((t) => !t.close && (t.name === 'main' || t.name === 'section'))?.start ?? 0;
    const hero = T('img').find((t) => t.start >= mainAt) || T('img')[0];
    if (hero) P('served.lazy-hero', 'warn', hero.attrs.loading === 'lazy' ? [`first content image is loading=lazy: ${hero.attrs.src}`] : [], all, 'first content image is not lazy-loaded');

    const bad = [];
    let toggles = 0;
    for (const t of T('a')) {
      if (!('href' in t.attrs)) continue;
      const href = t.attrs.href.trim();
      // A scripted toggle (role=button or aria-controls) and a Webflow lightbox carry href="#" by design.
      if (href === '#' && (t.attrs.role === 'button' || 'aria-controls' in t.attrs || /(^|\s)w-lightbox(\s|$)/.test(t.attrs.class || ''))) { toggles++; continue; }
      if (!href || href === '#' || /^javascript:/i.test(href)) { bad.push(`href="${href}"`); continue; }
      if (/^(mailto|tel|sms):/i.test(href)) continue;
      if (href.startsWith('#')) {
        let id;
        try { id = decodeURIComponent(href.slice(1)); } catch { bad.push(`${href} (malformed escape)`); continue; }
        if (!ids.has(id) && id.toLowerCase() !== 'top') bad.push(`${href} (no such id)`); // #top scrolls to the top by spec
        continue;
      }
      let u;
      try { u = new URL(href, page); } catch { bad.push(`${href} (unparseable)`); continue; }
      if (u.origin !== new URL(page).origin || !/^https?:$/.test(u.protocol)) continue;
      if (/\/[0-9a-f]{24}(\/|$)/i.test(u.pathname)) bad.push(`${href} (raw item id)`);
      u.hash = '';
      if (!linkTargets.has(u.href)) linkTargets.set(u.href, new Set());
      linkTargets.get(u.href).add(page);
    }
    P('served.links', 'fail', [...new Set(bad)], (k) => `${k.length} broken or placeholder link(s): ${k.slice(0, 8).join(', ')}`, `no #, empty, javascript: or dangling id links${toggles ? ` (${toggles} href="#" toggle or lightbox anchor(s) allowed)` : ''}`, { toggles });

    for (const e of opt.expect || []) R('served.expect', r.text.includes(e) ? 'pass' : 'fail', `${r.text.includes(e) ? 'present' : 'MISSING'}: "${e}"`);
    for (const e of opt.absent || []) R('served.absent', r.text.includes(e) ? 'fail' : 'pass', `${r.text.includes(e) ? 'still present' : 'absent'}: "${e}"`);

    const css = T('link').filter((t) => /(^|\s)stylesheet(\s|$)/i.test(t.attrs.rel || '') && t.attrs.href).map((t) => new URL(t.attrs.href, page).href);
    const js = doc.scripts.filter((s) => s.attrs.src).map((s) => new URL(s.attrs.src, page)).filter((u) => u.host === host).map((u) => u.href);
    meta[meta.length - 1].assets = [...css, ...js];
  };
  // One malformed page never stops the checks for the rest.
  pages.forEach((page, idx) => { try { onePage(page, resp[idx]); } catch (e) { add('served', 'error', e.message, { page }); } });

  const assets = [...new Set(meta.flatMap((m) => m.assets || []))];
  const assetRes = await pool(assets, 6, safe);
  const deadAssets = assets.map((a, i) => ({ a, s: assetRes[i].status || 'error' })).filter((x) => x.s !== 200).map((x) => `${x.a} (${x.s})`);
  if (assets.length) put('served.assets', 'fail', deadAssets, (k) => `${k.length} stylesheet/script(s) not 200 (cache-busted): ${k.slice(0, 5).join(', ')}`, `${assets.length} stylesheets and same-origin scripts return 200 cache-busted`, {});

  const targets = [...linkTargets.keys()].filter((u) => !pages.includes(u)).slice(0, 300);
  const tRes = await pool(targets, 6, safe);
  const dead = targets.map((u, i) => ({ u, s: tRes[i].status || tRes[i].error })).filter((x) => x.s !== 200).map((x) => `${x.u} (${x.s}) from ${[...linkTargets.get(x.u)].map((p) => new URL(p).pathname).join(', ')}`);
  const pageDead = pages.filter((p, i) => resp[i] && resp[i].status !== 200 && linkTargets.has(p));
  const deadAll = [...dead, ...pageDead];
  put('served.link-status', 'fail', deadAll, (k) => `${k.length} internal link target(s) not 200: ${k.slice(0, 3).join('; ')}`, `${targets.length + pages.length} internal targets return 200 cache-busted${linkTargets.size > 300 ? ' (first 300 checked)' : ''}`, {}, { dead: deadAll.slice(0, 20) });

  for (const key of ['title', 'description', 'og:image']) {
    const by = new Map();
    for (const m of meta) if (m[key]) { if (!by.has(m[key])) by.set(m[key], []); by.get(m[key]).push(new URL(m.page).pathname); }
    const dups = [...by.values()].filter((v) => v.length > 1).map((v) => v.join(' + '));
    if (meta.length > 1) put('served.unique', 'fail', dups, (k) => `duplicate ${key} across ${k.join('; ')}`, `${key} unique across ${meta.length} pages`, {}, { key });
  }

  for (const o of origins) {
    const r = await safe(`${o}/webcheck-missing-${Date.now().toString(36)}`);
    put('served.404', 'fail', r.status === 404 ? [] : [`bogus URL returned ${r.status || r.error} (soft 404)`], (k) => k[0], 'bogus URL returns a real 404', { page: o });
  }
}
