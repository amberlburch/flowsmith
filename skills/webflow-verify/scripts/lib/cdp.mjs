// Minimal Chrome DevTools Protocol client over Node 22's global WebSocket.
// Flat sessions: one browser socket, commands carry a sessionId per page.
import { execFileSync } from 'node:child_process';
import { homedir } from 'node:os';
import { join } from 'node:path';

const LAUNCHER = join(homedir(), '.claude/lib/debug_chrome.sh');

async function version(port) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(2000) });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

// Reuse the debug Chrome on :port, starting it through debug_chrome.sh when nothing listens.
export async function ensureChrome(port) {
  let v = await version(port);
  if (v) return v;
  if (port !== 9222) throw new Error(`no Chrome on 127.0.0.1:${port}`);
  let out = '';
  try { out = execFileSync('bash', [LAUNCHER], { encoding: 'utf8', timeout: 45000 }); }
  catch (e) { out = String(e.stdout || e.message); }
  v = await version(port);
  if (!v) throw new Error(`debug Chrome unavailable (${out.trim()}); rerun with --html-only`);
  return v;
}

export async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => {
    const t = setTimeout(() => { ws.close(); rej(new Error(`no WebSocket handshake from ${wsUrl} within 10s`)); }, 10000);
    ws.addEventListener('open', () => { clearTimeout(t); res(); }, { once: true });
    ws.addEventListener('error', () => { clearTimeout(t); rej(new Error(`cannot open ${wsUrl}`)); }, { once: true });
  });
  let seq = 0, closed = false;
  const pending = new Map();
  const listeners = new Set();
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(typeof ev.data === 'string' ? ev.data : Buffer.from(ev.data).toString());
    if (msg.id && pending.has(msg.id)) {
      const p = pending.get(msg.id);
      pending.delete(msg.id);
      clearTimeout(p.timer);
      if (msg.error) p.rej(new Error(`${p.method}: ${msg.error.message}`));
      else p.res(msg.result);
      return;
    }
    for (const fn of listeners) fn(msg);
  });
  ws.addEventListener('close', () => {
    closed = true;
    for (const p of pending.values()) { clearTimeout(p.timer); p.rej(new Error('CDP socket closed')); }
    pending.clear();
  });
  const send = (method, params = {}, sessionId, timeoutMs = 45000) => new Promise((res, rej) => {
    if (closed) return rej(new Error('CDP socket closed'));
    const id = ++seq;
    const timer = setTimeout(() => { pending.delete(id); rej(new Error(`${method}: timed out`)); }, timeoutMs);
    pending.set(id, { res, rej, method, timer });
    ws.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
  });
  const on = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
  return { send, on, close: () => ws.close(), get closed() { return closed; } };
}

// A page in its own browser context, so parallel jobs never share cookies, storage or tabs.
// A healthy Chrome answers in milliseconds; the short first timeout catches a stalled one.
export async function openPage(browser) {
  const { browserContextId } = await browser.send('Target.createBrowserContext', { disposeOnDetach: true }, undefined, 15000);
  const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId } = await browser.send('Target.attachToTarget', { targetId, flatten: true });
  const send = (method, params, timeoutMs) => browser.send(method, params, sessionId, timeoutMs);
  const waiters = new Set();
  const handlers = new Set();
  browser.on((msg) => {
    if (msg.sessionId !== sessionId) return;
    for (const h of handlers) h(msg);
    for (const w of [...waiters]) if (w.method === msg.method) { waiters.delete(w); clearTimeout(w.timer); w.res(msg.params); }
  });
  const waitFor = (method, timeoutMs = 30000) => new Promise((res) => {
    const w = { method, res, timer: setTimeout(() => { waiters.delete(w); res(null); }, timeoutMs) };
    waiters.add(w);
  });
  const close = async () => {
    try { await browser.send('Target.closeTarget', { targetId }, undefined, 5000); } catch {}
    try { await browser.send('Target.disposeBrowserContext', { browserContextId }, undefined, 5000); } catch {}
  };
  return { send, waitFor, onEvent: (fn) => handlers.add(fn), close, targetId };
}
