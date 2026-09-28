// In-page check library. The runner evaluates `(<this function>)(cfg)` after every
// navigation; it installs window.__webcheck and returns true. Pure DOM, no dependencies.
(cfg) => {
  const de = document.documentElement;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'LINK', 'META', 'BR', 'WBR', 'OPTION', 'HEAD', 'TITLE']);
  const IGN = ['.w-webflow-badge', '[data-webcheck-probe]', ...(cfg.ignore || [])].join(',');
  const ignored = (el) => !!(el.closest && el.closest(IGN));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const frames = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const round = (n) => Math.round(n * 10) / 10;
  const cs = (el, p) => getComputedStyle(el, p);
  const shown = (el) => {
    if (!el || el.nodeType !== 1) return false;
    if (el.checkVisibility && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true })) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0.5 && r.height > 0.5;
  };
  // The part of a box left after every ancestor below body that clips it (max-height:0 accordion
  // panels, slider masks). Overflow clips only descendants whose containing block chain runs
  // through it, so absolute boxes skip static ancestors and fixed boxes skip untransformed ones.
  const clipRect = (el, memo) => {
    if (!shown(el)) return null;
    const r = el.getBoundingClientRect();
    let l = r.left, t = r.top, rt = r.right, b = r.bottom, need = cs(el).position;
    for (let a = el.parentElement; a && a !== document.body && a !== de; a = a.parentElement) {
      let c = memo && memo.get(a);
      if (!c) {
        const s = cs(a);
        c = { pos: s.position, cb: s.transform !== 'none' || s.filter !== 'none', hx: /hidden|clip/.test(s.overflowX), hy: /hidden|clip/.test(s.overflowY) };
        if (c.hx || c.hy) c.r = a.getBoundingClientRect();
        if (memo) memo.set(a, c);
      }
      if (need === 'fixed' ? !c.cb : need === 'absolute' && c.pos === 'static' && !c.cb) continue;
      need = c.pos;
      if (c.hx) { l = Math.max(l, c.r.left); rt = Math.min(rt, c.r.right); }
      if (c.hy) { t = Math.max(t, c.r.top); b = Math.min(b, c.r.bottom); }
      if (rt - l < 1 || b - t < 1) return null;
    }
    return { l, t, r: rt, b };
  };
  const clippedVisible = (el, memo) => !!clipRect(el, memo);
  const visH = (el) => { const r = el && clipRect(el); return r ? Math.round(r.b - r.t) : 0; };
  const inSvg = (el) => el.namespaceURI === 'http://www.w3.org/2000/svg' && el.tagName.toLowerCase() !== 'svg';
  const all = () => [...document.body.querySelectorAll('*')].filter((el) => !SKIP.has(el.tagName) && !inSvg(el) && !ignored(el));
  const ownText = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.data.trim());
  const isBlockish = (el) => !cs(el).display.startsWith('inline') || /inline-(block|flex|grid|table)/.test(cs(el).display);
  const leafText = (el) => ![...el.querySelectorAll('*')].some((d) => !SKIP.has(d.tagName) && !inSvg(d) && /^(block|flex|grid|table|list-item|flow-root)/.test(cs(d).display));
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const outermost = (list) => { const s = new Set(list); return list.filter((el) => { for (let a = el.parentElement; a; a = a.parentElement) if (s.has(a)) return false; return true; }); };
  const desc = (el) => {
    if (!el || el.nodeType !== 1) return String(el);
    const part = (e) => {
      let s = e.tagName.toLowerCase();
      if (e.id) return `${s}#${CSS.escape(e.id)}`;
      const cls = typeof e.className === 'string' ? e.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
      return cls.length ? `${s}.${cls.map((c) => CSS.escape(c)).join('.')}` : s;
    };
    const parts = [];
    for (let e = el, i = 0; e && e.nodeType === 1 && e !== document.body && i < 3; e = e.parentElement, i++) {
      parts.unshift(part(e));
      if (e.id) break;
    }
    const t = (text(el) || el.getAttribute('aria-label') || el.getAttribute('alt') || '').slice(0, 50);
    return parts.join(' > ') + (t ? ` "${t}"` : '');
  };
  const rgba = (() => {
    const c = document.createElement('canvas');
    c.width = c.height = 1;
    const x = c.getContext('2d', { willReadFrequently: true });
    return (color) => { x.clearRect(0, 0, 1, 1); x.fillStyle = '#000'; x.fillStyle = color; x.fillRect(0, 0, 1, 1); const d = x.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  })();
  const opacityOf = (el) => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(cs(e).opacity); return o; };
  const W = {};
  W.desc = desc;

  W.viewport = () => ({ innerWidth, innerHeight, clientWidth: de.clientWidth, visibilityState: document.visibilityState, dpr: devicePixelRatio, scrollY });

  // Walk the page once so scroll reveals and lazy images resolve, then return to the top.
  W.settle = async () => {
    try { await Promise.race([document.fonts.ready, sleep(3000)]); } catch {}
    const H = () => de.scrollHeight;
    for (let y = 0; y < H() && y < 40000; y += Math.round(innerHeight * 0.8)) { scrollTo(0, y); await sleep(110); }
    scrollTo(0, H());
    await sleep(250);
    scrollTo(0, 0);
    await Promise.race([Promise.all([...document.images].filter((i) => !i.complete).map((i) => i.decode().catch(() => {}))), sleep(4000)]);
    await sleep(900);
    return scrollY;
  };

  // Layout: document overflow, visible escapes past the viewport, per-element containment
  // (L-90 amendment), clipped text. Overlaps are separate so band sweeps can call them alone.
  W.layout = () => {
    const vw = de.clientWidth;
    const els = all().filter(shown);
    const out = { vw, scrollWidth: de.scrollWidth, htmlOverflowX: cs(de).overflowX, bodyOverflowX: cs(document.body).overflowX, checked: els.length, overflow: [], escapes: [], containment: [], clipped: [] };
    const past = (r) => r.right > vw + 1 || r.left < -1;
    if (de.scrollWidth > vw + 1) {
      out.overflow = outermost(els.filter((el) => past(el.getBoundingClientRect()))).slice(0, 15)
        .map((el) => { const r = el.getBoundingClientRect(); return { el: desc(el), left: round(r.left), right: round(r.right) }; });
    }
    const clippedInside = (el) => {
      for (let a = el.parentElement; a && a !== document.body && a !== de; a = a.parentElement) {
        if (cs(a).overflowX !== 'visible') { const ar = a.getBoundingClientRect(); if (ar.left >= -1 && ar.right <= vw + 1) return true; }
      }
      return false;
    };
    const esc = els.filter((el) => {
      const r = el.getBoundingClientRect();
      const partly = (r.right > vw + 1 && r.left < vw - 1) || (r.left < -1 && r.right > 1);
      return partly && !clippedInside(el);
    });
    if (!out.overflow.length) out.escapes = outermost(esc).slice(0, 15).map((el) => { const r = el.getBoundingClientRect(); return { el: desc(el), left: round(r.left), right: round(r.right), vw }; });
    // An ancestor below body that clips x and cuts this box: a mask or marquee, so the overflow
    // is deliberate, and any text it cuts is reported as clipped text.
    const cutOff = (el, r) => {
      for (let a = el.parentElement; a && a !== document.body && a !== de; a = a.parentElement) {
        if (cs(a).overflowX === 'visible') continue;
        const ar = a.getBoundingClientRect();
        if (r.right > ar.right + 1 || r.left < ar.left - 1) return true;
      }
      return false;
    };
    const boxParent = (el) => { let p = el.parentElement; while (p && cs(p).display === 'contents') p = p.parentElement; return p; };
    const contain = [];
    for (const el of els) {
      const s = cs(el);
      if (s.position === 'absolute' || s.position === 'fixed') continue;
      if (s.display === 'inline' || s.display === 'contents') continue;
      if (parseFloat(s.marginLeft) < 0 || parseFloat(s.marginRight) < 0) continue;
      const p = boxParent(el);
      if (!p || p === document.body || p === de) continue;
      const ps = cs(p);
      if (ps.display === 'inline' || ps.overflowX !== 'visible') continue; // clipping or scrolling parent: deliberate
      const r = el.getBoundingClientRect(), pr = p.getBoundingClientRect();
      if (pr.width < 1) continue;
      const over = Math.max(r.right - pr.right, pr.left - r.left);
      if (over > 1 && !cutOff(el, r)) contain.push({ el: desc(el), parent: desc(p), px: round(over) });
      else if (ownText(el) && leafText(el) && s.overflowX === 'visible' && el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) {
        contain.push({ el: desc(el), parent: '(its own box: text overflows)', px: el.scrollWidth - el.clientWidth });
      }
    }
    out.containment = contain.slice(0, 20);
    out.containmentTotal = contain.length;
    const clip = [];
    for (const el of els) {
      const s = cs(el);
      const hid = (v) => v === 'hidden' || v === 'clip';
      const hx = hid(s.overflowX), hy = hid(s.overflowY);
      if (!(hx && el.scrollWidth > el.clientWidth + 1) && !(hy && el.scrollHeight > el.clientHeight + 1)) continue;
      if (s.textOverflow === 'ellipsis' || (s.webkitLineClamp && s.webkitLineClamp !== 'none')) continue;
      if (/slider|carousel|swiper|splide|marquee|ticker/i.test(el.className && el.className.baseVal === undefined ? el.className : '')) continue;
      if (el.getAnimations && el.getAnimations({ subtree: true }).some((a) => a.playState === 'running')) continue;
      const er = el.getBoundingClientRect();
      const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let n, k = 0, hit = null;
      while (!hit && (n = tw.nextNode()) && k++ < 300) {
        if (!n.data.trim() || !shown(n.parentElement)) continue;
        const rg = document.createRange();
        rg.selectNodeContents(n);
        for (const r of rg.getClientRects()) {
          if (r.right <= er.left || r.left >= er.right || r.bottom <= er.top || r.top >= er.bottom) continue;
          // Only an axis that clips can cut text; a scrolling axis is deliberate.
          const dx = hx ? Math.max(er.left - r.left, r.right - er.right) : 0;
          const dy = hy ? Math.max(er.top - r.top, r.bottom - er.bottom) : 0;
          if (dx > 2 || dy > 0.2 * r.height) { hit = { el: desc(el), text: n.data.trim().slice(0, 40), px: round(Math.max(dx, dy)) }; break; }
        }
      }
      if (hit) clip.push(hit);
    }
    out.clipped = clip.slice(0, 15);
    return out;
  };

  // L-106: absolutely positioned text blocks sharing a container must never intersect.
  W.overlaps = () => {
    const abs = all().filter((el) => cs(el).position === 'absolute' && shown(el) && text(el));
    const top = outermost(abs);
    const groups = new Map();
    for (const el of top) { const k = el.offsetParent || document.body; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(el); }
    const hits = [], near = [];
    for (const list of groups.values()) {
      for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
        const a = list[i].getBoundingClientRect(), b = list[j].getBoundingClientRect();
        const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        const pair = { a: desc(list[i]), b: desc(list[j]) };
        if (ox > 1 && oy > 1) hits.push({ ...pair, overlap: round(Math.min(ox, oy)), y: Math.round(Math.min(a.top, b.top) + scrollY) });
        else { const gap = Math.max(-ox, -oy); if (gap < 40) near.push({ ...pair, gap: round(gap) }); }
      }
    }
    return { checked: top.length, hits, near };
  };

  // Orphans (L-43): assign each word to the line of its LAST client rect, ~6px band.
  const analyse = (el) => {
    const segs = [];
    let full = '';
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = walker.nextNode())) {
      if (n.nodeType === 1) { if (n.tagName === 'BR' || isBlockish(n)) full += ' '; continue; }
      segs.push({ node: n, start: full.length });
      full += n.data;
    }
    if (!segs.length) return { lines: 0, orphan: false, lastLine: '', wrapped: [] };
    const locate = (idx) => { let s = segs[0]; for (const g of segs) { if (g.start <= idx) s = g; else break; } return { node: s.node, offset: Math.min(idx - s.start, s.node.data.length) }; };
    const words = [];
    const re = /[^\s\u00a0]+/g;
    let m;
    while ((m = re.exec(full))) {
      const a = locate(m.index), b = locate(m.index + m[0].length - 1);
      const rg = document.createRange();
      try { rg.setStart(a.node, a.offset); rg.setEnd(b.node, Math.min(b.offset + 1, b.node.data.length)); } catch { continue; }
      const rects = [...rg.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
      if (!rects.length) continue;
      const last = rects[rects.length - 1];
      words.push({ w: m[0], top: last.top, wrapped: rects.some((r) => Math.abs(r.top - rects[0].top) > 6) });
    }
    const lines = [];
    for (const wd of words) { const cur = lines[lines.length - 1]; if (cur && Math.abs(wd.top - cur.top) <= 6) cur.words.push(wd.w); else lines.push({ top: wd.top, words: [wd.w] }); }
    const lastLine = lines[lines.length - 1];
    return { lines: lines.length, orphan: lines.length > 1 && lastLine.words.length === 1, lastLine: lastLine ? lastLine.words.join(' ') : '', wrapped: words.filter((w) => w.wrapped && /-/.test(w.w)).map((w) => w.w) };
  };
  W.orphans = () => {
    const probe = document.createElement('div');
    probe.setAttribute('data-webcheck-probe', '');
    probe.style.cssText = 'position:fixed;left:0;top:0;width:130px;font:16px/1.4 sans-serif;visibility:visible;z-index:-1;';
    probe.innerHTML = '<h3 style="font:16px/1.4 sans-serif;margin:0">aaa bbb ccc ddd eeeeeeeeeeeee</h3><h3 style="font:16px/1.4 sans-serif;margin:0;width:1000px">one two three</h3><h3 style="font:16px/1.4 sans-serif;margin:0">aaaaaaa bbbbbbb cc dd</h3>';
    document.body.appendChild(probe);
    const [t1, t2, t3] = [...probe.children].map(analyse);
    probe.remove();
    const selftest = t1.orphan && !t2.orphan && !t3.orphan;
    const sel = 'h1,h2,h3,h4,h5,h6,p,blockquote,figcaption,[class*="kicker"],[class*="eyebrow"],[class*="label"],[class*="title"],[class*="quote"],[class*="caption"],[class*="heading"]';
    const els = [...new Set(document.body.querySelectorAll(sel))].filter((el) => !ignored(el) && shown(el) && cs(el).display !== 'inline' && leafText(el) && text(el).split(' ').length > 2);
    const orphans = [], wraps = [];
    for (const el of els) {
      const a = analyse(el);
      if (a.orphan) orphans.push({ el: desc(el), lastLine: a.lastLine, lines: a.lines });
      if (a.wrapped.length) wraps.push({ el: desc(el), words: a.wrapped });
    }
    return { selftest, checked: els.length, orphans, wraps };
  };

  // Visible heading-tier text for Sentence case and trailing full stops (dod 4b).
  W.headingTexts = () => {
    const kinds = [
      ['heading', 'h1,h2,h3,h4,h5,h6,[class*="kicker"],[class*="eyebrow"],[class*="title"]:not([class*="subtitle"]),[class*="heading"]:not([class*="subheading"])'],
      ['label', '[class*="label"]'],
      ['nav', 'nav a,[role="navigation"] a,.w-nav-link'],
      ['button', 'button,.w-button,a[class*="button"],a[class*="btn"]'],
    ];
    const seen = new Set(), out = [];
    for (const [kind, sel] of kinds) {
      for (const el of document.body.querySelectorAll(sel)) {
        if (seen.has(el) || ignored(el) || !shown(el) || !leafText(el)) continue;
        seen.add(el);
        const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
        if (t) out.push({ kind, el: desc(el), text: t, transform: cs(el).textTransform });
      }
    }
    return out;
  };

  // Visible copy grouped into runs by nearest block ancestor (for the copy-map diff).
  W.copyRuns = () => {
    const runs = new Map();
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode())) {
      const p = n.parentElement;
      if (!n.data.trim() || !p || SKIP.has(p.tagName) || inSvg(p) || ignored(p) || !shown(p)) continue;
      let b = p;
      while (b && b !== document.body && !isBlockish(b)) b = b.parentElement;
      if (!runs.has(b)) runs.set(b, []);
      runs.get(b).push(n.data);
    }
    const out = [];
    for (const [b, parts] of runs) { const t = parts.join(' ').replace(/\s+/g, ' ').trim(); if (t.split(' ').length >= 4) out.push({ el: desc(b), text: t }); }
    return out;
  };

  W.residue = (phrases, labels) => {
    const body = (document.body.innerText || '').toLowerCase();
    const found = phrases.filter((p) => body.includes(p));
    const exact = [];
    for (const el of all()) if (leafText(el) && shown(el) && labels.includes(text(el))) exact.push({ el: desc(el), text: text(el) });
    return { found, exact: exact.slice(0, 10) };
  };

  W.lcp = () => new Promise((res) => {
    let last = null;
    try {
      const po = new PerformanceObserver((l) => { const e = l.getEntries(); if (e.length) last = e[e.length - 1]; });
      po.observe({ type: 'largest-contentful-paint', buffered: true });
      setTimeout(() => {
        po.disconnect();
        if (!last) return res(null);
        const el = last.element;
        res({ el: el ? desc(el) : '(removed)', tag: el ? el.tagName.toLowerCase() : '', url: last.url || '', size: last.size, lazy: !!(el && el.tagName === 'IMG' && el.loading === 'lazy') });
      }, 250);
    } catch { res(null); }
  });

  // Images: ratio = currentSrc's own pixel width / rendered CSS width (dod.md 6), measured at
  // DPR 2 so srcset picks its retina candidate. Plus broken, lazy above the fold, width/height.
  W.images = async () => {
    const vh = innerHeight;
    const cache = new Map();
    const natural = (src) => {
      if (!cache.has(src)) cache.set(src, new Promise((res) => { const im = new Image(); const t = setTimeout(() => res(null), 8000); im.onload = () => { clearTimeout(t); res({ w: im.naturalWidth, h: im.naturalHeight }); }; im.onerror = () => { clearTimeout(t); res(null); }; im.src = src; }));
      return cache.get(src);
    };
    const isSvg = (src) => /\.svg(\?|#|$)/i.test(src) || src.startsWith('data:image/svg');
    const out = [];
    for (const img of document.images) {
      if (ignored(img) || !shown(img)) continue;
      const r = img.getBoundingClientRect();
      const src = img.currentSrc || img.src || '';
      if (!img.complete) await Promise.race([img.decode().catch(() => {}), sleep(3000)]);
      const broken = !src || (img.complete && img.naturalWidth === 0);
      const svg = isSvg(src);
      const n = broken || svg ? null : await natural(src);
      out.push({ el: desc(img), src, bg: false, rendered: round(r.width), natural: n ? n.w : null, ratio: n ? Math.round(n.w / r.width * 100) / 100 : null, srcset: !!img.srcset || !!img.closest('picture'), lazy: img.loading === 'lazy', aboveFold: r.top < vh && r.bottom > 0 && scrollY === 0, hasDims: img.hasAttribute('width') && img.hasAttribute('height'), broken, svg });
    }
    for (const el of all()) {
      const s = cs(el);
      const m = /^url\(["']?([^"')]+)["']?\)$/.exec(s.backgroundImage);
      if (!m || ignored(el) || isSvg(m[1]) || !/cover|contain/.test(s.backgroundSize) || !shown(el)) continue;
      const n = await natural(m[1]);
      if (!n || !n.w || !n.h) continue;
      const r = el.getBoundingClientRect();
      const disp = s.backgroundSize.includes('cover') ? Math.max(r.width, r.height * n.w / n.h) : Math.min(r.width, r.height * n.w / n.h);
      out.push({ el: desc(el), src: m[1], bg: true, rendered: round(disp), natural: n.w, ratio: Math.round(n.w / disp * 100) / 100, lazy: false, aboveFold: false, hasDims: true, broken: false, svg: false });
    }
    return out;
  };

  W.a11yStatic = () => {
    const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')].filter((h) => !ignored(h) && shown(h));
    const levels = hs.map((h) => (h.getAttribute('aria-level') ? +h.getAttribute('aria-level') : +h.tagName[1] || 2));
    const jumps = [];
    for (let i = 1; i < levels.length; i++) if (levels[i] > levels[i - 1] + 1) jumps.push({ from: `h${levels[i - 1]}`, to: `h${levels[i]}`, el: desc(hs[i]) });
    const count = (sel) => [...document.querySelectorAll(sel)].filter(shown).length;
    const imgs = [...document.images].filter((i) => !ignored(i));
    const noAlt = imgs.filter((i) => !i.hasAttribute('alt') && i.getAttribute('role') !== 'presentation').map(desc);
    const fileAlt = imgs.filter((i) => /\.(jpe?g|png|webp|gif|avif|svg)$|^(image|img|photo|picture)\s*\d*$|^img[_-]?\d+/i.test((i.getAttribute('alt') || '').trim())).map((i) => `${desc(i)} alt="${i.getAttribute('alt')}"`);
    const ctrls = [...document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]),select,textarea')].filter((c) => !ignored(c) && shown(c));
    const unlabelled = [];
    for (const c of ctrls) {
      const byLabel = [...(c.labels || [])].some((l) => text(l));
      const byAria = (c.getAttribute('aria-label') || '').trim() || (c.getAttribute('aria-labelledby') || '').split(/\s+/).some((id) => id && document.getElementById(id) && text(document.getElementById(id)));
      const byTitle = (c.getAttribute('title') || '').trim();
      if (!byLabel && !byAria && !byTitle) unlabelled.push(`${desc(c)}${c.getAttribute('placeholder') ? ' (placeholder only)' : ''}`);
    }
    const badFor = [...document.querySelectorAll('label[for]')].filter((l) => !ignored(l) && (!l.htmlFor || !document.getElementById(l.htmlFor))).map((l) => `${desc(l)} for="${l.htmlFor}"`);
    const positive = [...document.querySelectorAll('[tabindex]')].filter((e) => e.tabIndex > 0).map(desc);
    return {
      headings: levels.length, h1: levels.filter((l) => l === 1).length, jumps,
      landmarks: { main: count('main,[role="main"]'), nav: count('nav,[role="navigation"]'), banner: count('header,[role="banner"]'), contentinfo: count('footer,[role="contentinfo"]') },
      noAlt, fileAlt, unlabelled, badFor, positive,
    };
  };

  // Keyboard walk: baseline every focusable's unfocused styles, then the runner presses real Tab keys.
  const FOCUSABLE = 'a[href],area[href],button,input:not([type="hidden"]),select,textarea,summary,iframe,[tabindex],[contenteditable="true"],[contenteditable=""],audio[controls],video[controls]';
  const KEYS = ['outlineStyle', 'outlineWidth', 'outlineColor', 'outlineOffset', 'boxShadow', 'borderTopColor', 'borderBottomColor', 'borderLeftColor', 'borderTopWidth', 'borderBottomWidth', 'backgroundColor', 'backgroundImage', 'color', 'textDecorationLine', 'textDecorationColor', 'opacity', 'transform'];
  const snapOne = (el, p) => { const s = cs(el, p); return KEYS.map((k) => s[k]).join('|'); };
  const snap = (el) => [snapOne(el), snapOne(el, '::before'), snapOne(el, '::after'), el.parentElement ? snapOne(el.parentElement) : '', el.firstElementChild ? snapOne(el.firstElementChild) : ''];
  W.focusBaseline = () => {
    window.__wcBase = new Map();
    window.__wcIds = new Map();
    const tabbable = [];
    for (const el of document.querySelectorAll(FOCUSABLE)) {
      window.__wcBase.set(el, snap(el));
      if (!ignored(el) && shown(el) && el.tabIndex >= 0 && !el.disabled && !el.closest('[inert]')) tabbable.push(el);
    }
    window.__wcTabbable = tabbable;
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    scrollTo(0, 0);
    return { candidates: window.__wcBase.size, tabbable: tabbable.length };
  };
  W.focusProbe = () => {
    let a = document.activeElement;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
    if (!a || a === document.body || a === de) return { body: true };
    if (!window.__wcIds.has(a)) window.__wcIds.set(a, window.__wcIds.size);
    const r = a.getBoundingClientRect();
    const inView = r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < de.clientWidth;
    const vis = inView && (!a.checkVisibility || a.checkVisibility({ opacityProperty: true, visibilityProperty: true }));
    const s = cs(a);
    const ring = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 && rgba(s.outlineColor)[3] > 0;
    const base = window.__wcBase.get(a);
    const now = snap(a);
    const changed = !!base && base.some((v, i) => v !== now[i]);
    return { id: window.__wcIds.get(a), el: desc(a), tag: a.tagName, visible: vis, indicator: ring || changed, ignored: ignored(a) };
  };
  W.unreached = () => (window.__wcTabbable || []).filter((el) => !window.__wcIds.has(el)).map(desc);

  // Contrast: text colour from computed style, background from real pixels with text hidden.
  W.contrastTargets = (max) => {
    const map = new Map();
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode()) && map.size < max) {
      const p = n.parentElement;
      if (!p || map.has(p) || !/[\p{L}\p{N}]/u.test(n.data) || SKIP.has(p.tagName) || inSvg(p) || ignored(p) || !shown(p)) continue;
      const pr = p.getBoundingClientRect();
      if (pr.right <= 0 || pr.left >= de.clientWidth) continue;
      if (p.closest(':disabled,[aria-disabled="true"]')) continue;
      const s = cs(p);
      if (s.webkitTextFillColor && rgba(s.webkitTextFillColor)[3] === 0) continue;
      const op = opacityOf(p);
      if (op < 0.1) continue;
      const [r, g, b, a] = rgba(s.color);
      const size = parseFloat(s.fontSize), weight = parseInt(s.fontWeight, 10) || 400;
      map.set(p, { color: [r, g, b], alpha: a * op, size, weight, large: size >= 24 || (size >= 18.66 && weight >= 700), el: desc(p) });
    }
    window.__wcCT = [...map.keys()];
    return [...map.values()];
  };
  W.contrastChunk = async (y, done) => {
    scrollTo(0, y);
    await frames();
    await sleep(120);
    const vw = de.clientWidth, vh = innerHeight, skip = new Set(done);
    const items = [];
    window.__wcCT.forEach((p, i) => {
      if (skip.has(i)) return;
      const rects = [];
      for (const c of p.childNodes) {
        if (c.nodeType !== 3 || !c.data.trim()) continue;
        const rg = document.createRange();
        rg.selectNodeContents(c);
        for (const r of rg.getClientRects()) {
          if (r.width <= 1 || r.height <= 1 || r.top < 0 || r.bottom > vh || r.left < 0 || r.right > vw) continue;
          // Only sample text that is on top: stacked tab panels and clipped text are not what users see.
          const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          if (hit && (p.contains(hit) || hit.contains(p))) rects.push({ left: r.left, top: r.top, width: r.width, height: r.height });
        }
      }
      if (rects.length) items.push({ i, rects: rects.slice(0, 4) });
    });
    return { scrollY, vw, vh, items };
  };
  W.hideText = (on) => {
    let st = document.getElementById('__wc-hide');
    if (on && !st) {
      st = document.createElement('style');
      st.id = '__wc-hide';
      st.textContent = '*,*::before,*::after{color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;text-decoration-color:transparent!important;caret-color:transparent!important;transition:none!important}';
      document.head.appendChild(st);
    }
    if (!on && st) st.remove();
    return !!on;
  };

  // Negative states: nothing empty, erroring or validating on a fresh load, searched by id and class.
  W.negatives = () => {
    const sel = '.w-form-done,.w-form-fail,.w-dyn-empty,[class*="empty"],[id*="empty"],[class*="no-result"],[id*="no-result"],[class*="noresult"],[class*="error"],[id*="error"],[class*="validation"],[role="alert"]';
    return outermost([...document.body.querySelectorAll(sel)].filter((el) => !ignored(el) && clippedVisible(el) && text(el))).slice(0, 15).map((el) => ({ el: desc(el), text: text(el).slice(0, 60) }));
  };

  // Interactive states (F10): menus, accordions, dropdowns.
  const DISCLOSURE = '[aria-expanded],details>summary,.w-dropdown-toggle,[class*="accordion"] [class*="trigger"],[class*="accordion"] [class*="toggle"],[class*="accordion"] [class*="header"],[class*="accordion"] [class*="question"],[class*="faq"] [class*="question"],[class*="faq"] [class*="trigger"],[class*="faq"] [class*="toggle"]';
  // A click on a submit control posts a real submission (on a live site, into the client's pipeline).
  const submits = (el) => !!el.form && (el.tagName === 'BUTTON' || el.tagName === 'INPUT') && (el.type === 'submit' || el.type === 'image');
  W.controls = (withDisclosures, max) => {
    const list = [...document.querySelectorAll('.w-nav-button')].map((el) => ({ el, kind: 'nav' }));
    if (withDisclosures) {
      const d = [...document.querySelectorAll(DISCLOSURE)].filter((el) => !el.closest('.w-nav-button') && !(el.matches('a[href]') && !/^#/.test(el.getAttribute('href'))));
      list.push(...outermost(d).map((el) => ({ el, kind: 'disclosure' })));
    }
    const ok = list.filter((x) => !ignored(x.el) && shown(x.el) && !submits(x.el));
    const nav = ok.filter((x) => x.kind === 'nav');
    const dis = ok.filter((x) => x.kind === 'disclosure').slice(0, max);
    window.__wcControls = [...nav, ...dis].map((x) => x.el);
    return [...nav, ...dis].map((x, i) => ({ i, kind: x.kind, el: desc(x.el), expanded: x.el.getAttribute('aria-expanded'), dropdown: x.el.matches('.w-dropdown-toggle') }));
  };
  // Second line of defence for the state step: no submit event or form.submit() leaves the page,
  // and Webflow's own ajax handler never sees one.
  W.guardSubmits = () => {
    if (!window.__wcGuard) {
      window.__wcGuard = { blocked: 0 };
      addEventListener('submit', (e) => { e.preventDefault(); e.stopImmediatePropagation(); window.__wcGuard.blocked++; }, true);
      HTMLFormElement.prototype.submit = function () { window.__wcGuard.blocked++; };
    }
    return window.__wcGuard.blocked;
  };
  // Content that shows and hides on its own (sliders, marquees, rotating quotes) is not a reveal.
  // A control with an aria-controls target is judged on that target alone, so none of this touches it.
  const MOVING = '.w-slider,[class*="slider"],[class*="carousel"],[class*="swiper"],[class*="splide"],[class*="marquee"],[class*="ticker"]';
  const still = (el) => !el.closest(MOVING) && !(window.__wcMoving || []).some((m) => m.contains(el));
  const textish = (scope) => { const memo = new Map(); return all().filter((el) => (el.tagName === 'IMG' || el.tagName === 'INPUT' || ownText(el)) && (scope ? scope.contains(el) : still(el)) && clippedVisible(el, memo)); };
  const targetOf = (i) => { const c = (window.__wcControls || [])[i], id = c && c.getAttribute('aria-controls'); return id ? document.getElementById(id) : null; };
  W.markVisible = (i) => {
    if (i >= 0) window.__wcControls[i].scrollIntoView({ block: 'center', inline: 'nearest' });
    window.__wcScope = targetOf(i);
    window.__wcVis = new Set(textish(window.__wcScope));
    window.__wcT0 = { i, target: visH(window.__wcScope), doc: de.scrollHeight };
    return window.__wcVis.size;
  };
  // Movers: whatever changed visibility with nobody clicking, plus looping CSS animations that move
  // or fade (a slow marquee may not cross its mask edge while we watch).
  W.markNoise = () => {
    const now = new Set(textish()), was = window.__wcVis;
    const changed = [...now].filter((e) => !was.has(e)).concat([...was].filter((e) => !now.has(e)));
    const box = (e) => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) if (/hidden|clip/.test(cs(a).overflowX + cs(a).overflowY)) return a; return e.parentElement; };
    const loops = document.getAnimations().filter((a) => a.playState === 'running' && a.effect && a.effect.target && a.effect.getComputedTiming().endTime === Infinity
      && a.effect.getKeyframes().some((k) => ['transform', 'translate', 'left', 'top', 'marginLeft', 'opacity'].some((p) => p in k))).map((a) => a.effect.target);
    window.__wcMoving = [...new Set([...changed.map(box), ...loops])];
    return window.__wcMoving.length;
  };
  W.revealed = (i) => {
    const rev = textish(window.__wcScope).filter((e) => !window.__wcVis.has(e));
    window.__wcRev = rev;
    return { count: rev.length, target: visH(targetOf(i)), sig: rev.slice(0, 30).map((e) => { const r = clipRect(e); return r ? `${Math.round(r.l)},${Math.round(r.t)},${Math.round(r.r - r.l)},${Math.round(r.b - r.t)}` : '-'; }).join(';') };
  };
  W.clickPoint = (i) => {
    const c = window.__wcControls[i];
    c.scrollIntoView({ block: 'center', inline: 'nearest' });
    const r = c.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const hit = document.elementFromPoint(x, y);
    return { x, y, hit: !!hit && (hit === c || c.contains(hit)) };
  };
  W.nativeClick = (i) => { window.__wcControls[i].click(); return true; };
  W.openState = (i) => {
    const c = window.__wcControls[i];
    const rev = window.__wcRev || [];
    window.__wcOpen = rev;
    const vw = de.clientWidth, vh = innerHeight;
    const links = [...new Set(rev.map((e) => e.closest('a,button,[role="menuitem"],input,select,textarea')).filter(Boolean))].filter((e) => clippedVisible(e));
    const reachable = (e) => {
      let fixed = null;
      for (let a = e; a && a !== document.body; a = a.parentElement) if (cs(a).position === 'fixed') { fixed = a; break; }
      if (!fixed) return true;
      for (let a = e.parentElement; a; a = a.parentElement) { const s = cs(a); if (/auto|scroll/.test(s.overflowY) && a.scrollHeight > a.clientHeight) return true; if (a === fixed) break; }
      return false;
    };
    const off = links.filter((e) => { const r = e.getBoundingClientRect(); return r.left < -1 || r.right > vw + 1 || r.top < -1 || (r.bottom > vh + 1 && !reachable(e)); })
      .slice(0, 10).map((e) => { const r = e.getBoundingClientRect(); return `${desc(e)} at ${Math.round(r.left)},${Math.round(r.top)}`; });
    const target = targetOf(i), t0 = window.__wcT0;
    // Growth counts as a reveal too: a panel whose text was never clipped out, or a read-more.
    const grew = visH(target) - t0.target > 4 || de.scrollHeight - t0.doc > 4;
    return { revealed: rev.length + (grew ? 1 : 0), links: links.length, offscreen: off, expanded: c.getAttribute('aria-expanded'), declared: c.hasAttribute('aria-expanded') || c.hasAttribute('aria-controls'), hasTarget: !!target, targetShown: target ? clippedVisible(target) : null, isSummary: c.tagName === 'SUMMARY' };
  };
  // Escape as an in-page keydown: a CDP Escape key event hangs headless Chrome 154's browser
  // process on macOS. Menu Escape handlers are script, so an untrusted event reaches them.
  W.escape = () => {
    const t = document.activeElement || document.body;
    for (const type of ['keydown', 'keyup']) t.dispatchEvent(new KeyboardEvent(type, { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true, cancelable: true }));
    return true;
  };
  W.busy = () => document.getAnimations().filter((a) => a.playState === 'running' && a.effect && a.effect.getComputedTiming().endTime !== Infinity).length;
  W.stillOpen = () => { const memo = new Map(), t0 = window.__wcT0 || { target: 0 }; return (window.__wcOpen || []).filter((e) => clippedVisible(e, memo)).length + (visH(targetOf(t0.i)) - t0.target > 4 ? 1 : 0); };
  // Changes while a panel animates, so settling on it waits out a slow close transition.
  W.openSig = () => { const t0 = window.__wcT0 || {}; return `${(window.__wcOpen || []).map((e) => visH(e)).join(',')}|${visH(targetOf(t0.i))}`; };
  W.controlState = (i) => { const c = window.__wcControls[i], t = targetOf(i); return { expanded: c.getAttribute('aria-expanded'), targetShown: t ? clippedVisible(t) : null }; };

  // Forms: names at submit time, and validation state entered without submitting.
  W.forms = () => (window.__wcForms = [...document.forms].filter((f) => !ignored(f) && shown(f))).map((f, i) => {
    const ctrls = [...f.elements].filter((e) => e.matches('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]),select,textarea'));
    const names = ctrls.map((e) => e.name || '');
    const dup = names.filter((n, k) => n && names.indexOf(n) !== k);
    return { i, el: desc(f), controls: ctrls.length, emptyNames: ctrls.filter((e) => !e.name).map(desc), dupNames: [...new Set(dup)], invalidWhenEmpty: ctrls.filter((e) => e.willValidate && !e.validity.valid).length };
  });
  W.formValidate = (i) => { window.__wcForms[i].reportValidity(); return true; };
  W.formErrors = (i) => {
    const f = window.__wcForms[i];
    const invalid = [...f.elements].filter((e) => e.willValidate && !e.validity.valid);
    const unassociated = invalid.filter((e) => {
      const ids = `${e.getAttribute('aria-describedby') || ''} ${e.getAttribute('aria-errormessage') || ''}`.split(/\s+/).filter(Boolean);
      return !ids.some((id) => { const t = document.getElementById(id); return t && shown(t) && text(t); });
    }).map(desc);
    return { invalid: invalid.length, unassociated };
  };

  // Completeness (F12): each inventory section present, rendered, with its photos and elements.
  W.completeness = (sections) => sections.map((s) => {
    const sel = s.selector || `.section_${s.section}`;
    let els;
    try { els = [...document.querySelectorAll(sel)]; } catch { return { section: s.section, selector: sel, error: 'invalid selector' }; }
    const el = els.find(shown);
    if (!el) return { section: s.section, selector: sel, matched: els.length, present: false };
    const r = el.getBoundingClientRect();
    const photo = (e) => (e.tagName === 'IMG' && !/\.svg(\?|#|$)/i.test(e.currentSrc || e.src)) || /url\(/.test(cs(e).backgroundImage);
    const photos = [el, ...el.querySelectorAll('*')].filter((e) => !SKIP.has(e.tagName) && photo(e) && shown(e)).length;
    const missing = (s.elements || []).filter((q) => { try { return ![...el.querySelectorAll(q)].some(shown); } catch { return true; } });
    return { section: s.section, selector: sel, matched: els.length, present: true, top: Math.round(r.top + scrollY), height: Math.round(r.height), photos, missing };
  });

  window.__webcheck = W;
  return true;
}
