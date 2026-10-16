"""rendered.py — optional rendered (browser) checks via an already-installed Playwright; clean fallback when absent.

Never installs anything and never touches the network: the probe aborts every request that is not file:// or
data:. Availability: `node` on PATH and `require('playwright')` resolvable (global or local). Set
STUDIO_DETECTOR_BROWSER=off to force the static-only path. Without a browser the rendered rules are reported as
NOT RUN with the reason, never as clean.

The probe loads the page at a desktop (1280x800) and a phone (390x844) viewport, waits for load + settle (reveal
handlers get their chance), records uncaught errors, and MEASURES geometry in the page (JS below). rules(data) turns
those measures into findings with the thresholds, snippets and severities of impeccable's browser engine
(Apache-2.0; see PORT_MAP.md for the upstream fn per rule). Measuring is split from judging
so rules() is testable on hand-built measure dicts without a browser. Upstream scans one 1280x800 viewport; we judge
every rule on the desktop pass except body-text-viewport-edge, which also reads the phone pass (its 12px floor).
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

RENDERED_RULES = ("script-error", "content-hidden-at-rest", "text-overflow", "body-text-viewport-edge", "line-length",
                  "heading-rhythm", "first-viewport-column-overflow", "edge-flush-cards", "text-occlusion",
                  "blinking-cursor")
# rules whose static form runs anyway and that the browser adds a rendered form to (not "rendered-only")
RENDERED_EXTRA = ("cramped-padding",)

PROBE = r"""
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const opts = { headless: true };
  if (cfg.exe) opts.executablePath = cfg.exe;
  let browser = null, lastErr = null;
  // bundled Chromium first, then an installed Chrome or Edge (no browser download needed on Windows/macOS)
  for (const o of [opts, { headless: true, channel: 'chrome' }, { headless: true, channel: 'msedge' }]) {
    try { browser = await chromium.launch(o); break; } catch (e) { lastErr = e; }
  }
  if (!browser) throw lastErr;
  const out = { viewports: [] };
  for (const vp of cfg.viewports) {
    const page = await browser.newPage({ viewport: vp });
    const errors = [];
    page.on('pageerror', e => errors.push({ message: (e && e.name ? e.name + ': ' : '') + String(e && e.message || e),
                                            stack: String(e && e.stack || '') }));
    await page.route('**/*', r => { const u = r.request().url(); (u.startsWith('file:') || u.startsWith('data:')) ? r.continue() : r.abort(); });
    try { await page.goto(cfg.url, { waitUntil: 'load', timeout: 15000 }); } catch (e) { errors.push({ message: 'load: ' + e.message, stack: '' }); }
    await page.waitForTimeout(cfg.settle);
    let m = {};
    try { m = await page.evaluate(MEASURE, { full: vp.width >= 1000 }); } catch (e) { m = { measureError: String(e && e.message || e) }; }
    if (cfg.shot && vp.width >= 1000) { await page.screenshot({ path: cfg.shot, fullPage: true }); }
    out.viewports.push({ width: vp.width, height: vp.height, errors, ...m });
    await page.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stdout.write(JSON.stringify({ fatal: String(e && e.stack || e) })); });
"""

MEASURE = r"""async (opt) => {
  const vw = window.innerWidth, vh = window.innerHeight, SY = window.scrollY || 0;
  const CS = el => getComputedStyle(el);
  const tag = el => el.tagName.toLowerCase();
  const csel = el => tag(el) + [...el.classList].map(c => '.' + c).join('');
  const pf = v => { const n = parseFloat(v); return isFinite(n) ? n : 0; };
  const alpha = c => { if (!c || c === 'transparent') return 0; const m = c.match(/rgba?\(([^)]*)\)/); if (!m) return 1; const p = m[1].split(/[\s,\/]+/).filter(Boolean); return p.length > 3 ? parseFloat(p[3]) : 1; };
  const rgb = c => { const m = (c || '').match(/rgba?\(([^)]*)\)/); if (!m) return null; return m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat); };
  const near = (a, b) => { const x = rgb(a), y = rgb(b); if (!x || !y) return false; return Math.abs((x[3] ?? 1) - (y[3] ?? 1)) <= 0.03 && Math.max(Math.abs(x[0]-y[0]), Math.abs(x[1]-y[1]), Math.abs(x[2]-y[2])) <= 3; };
  const ownText = el => { let s = ''; for (const c of el.childNodes) if (c.nodeType === 3) s += c.textContent; return s; };
  const directLonger = (el, n) => [...el.childNodes].some(c => c.nodeType === 3 && c.textContent.trim().length > n);
  const shown = el => { for (let n = el; n && n.nodeType === 1; n = n.parentElement) { const s = CS(n); if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse' || s.contentVisibility === 'hidden') return false; } return true; };
  const effOp = el => { let o = 1; for (let n = el; n && n.nodeType === 1; n = n.parentElement) o *= pf(CS(n).opacity); return o; };
  const painted = el => (!el.checkVisibility || el.checkVisibility()) && shown(el) && effOp(el) > 0.02;
  const textRects = el => { const r = document.createRange(); r.selectNodeContents(el); return [...r.getClientRects()].filter(q => q.width > 0.5 && q.height > 0.5); };
  const directRects = el => { const out = []; for (const c of el.childNodes) if (c.nodeType === 3 && c.textContent.trim()) { const r = document.createRange(); r.selectNodeContents(c); out.push(...[...r.getClientRects()].filter(q => q.width > 0.5)); } return out; };
  const textNodeRects = el => { const out = []; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); for (let t = w.nextNode(); t; t = w.nextNode()) { if (!t.textContent.trim()) continue; const p = t.parentElement; if (p && (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE'].includes(p.tagName) || (p !== el && !painted(p)))) continue; const r = document.createRange(); r.selectNodeContents(t); out.push(...[...r.getClientRects()].filter(q => q.width > 0.5 && q.height > 0.5)); } return out; };
  // painted.rs TEXT_MIN_VISIBLE_SHARE: share of the text's x extent left inside clipping ancestors (incl. itself), and
  // whether any of it shows on y at all
  const textVisible = (el, rs) => { if (!rs.length) return { x: 1, y: true }; let L = -Infinity, R = Infinity, T = -Infinity, B = Infinity; for (let a = el; a && a !== document.documentElement && a !== document.body; a = a.parentElement) { const s = getComputedStyle(a); if (s.display === 'inline' || s.display === 'contents') continue; const q = a.getBoundingClientRect(); const m = (s.overflowX === 'clip' || s.overflowY === 'clip') ? (parseFloat(s.overflowClipMargin) || 0) : 0; if (s.overflowX !== 'visible') { L = Math.max(L, q.left - m); R = Math.min(R, q.right + m); } if (s.overflowY !== 'visible') { T = Math.max(T, q.top - m); B = Math.min(B, q.bottom + m); } } let tot = 0, vis = 0, y = false; for (const r of rs) { tot += r.width; vis += Math.max(0, Math.min(r.right, R) - Math.max(r.left, L)); if (Math.min(r.bottom, B) - Math.max(r.top, T) > 0) y = true; } return { x: tot ? vis / tot : 1, y }; };
  const textPainted = el => { const v = textVisible(el, textNodeRects(el)); return v.y && v.x >= 0.25; };
  const union = rs => rs.length ? { left: Math.min(...rs.map(r => r.left)), right: Math.max(...rs.map(r => r.right)), top: Math.min(...rs.map(r => r.top)), bottom: Math.max(...rs.map(r => r.bottom)) } : null;
  const rows = rs => { const s = [...rs].sort((a, b) => a.top - b.top); const out = []; let mid = -Infinity; for (const r of s) { if (r.top >= mid) { out.push({ left: r.left, right: r.right, top: r.top, h: r.height }); mid = r.top + r.height / 2; } else { const o = out[out.length - 1]; o.left = Math.min(o.left, r.left); o.right = Math.max(o.right, r.right); } } return out; };
  const PHRASING = new Set('a abbr b bdi bdo br cite code data del dfn em font i ins kbd mark q s samp small span strong sub sup time u var wbr'.split(' '));
  const onlyPhrasing = el => [...el.querySelectorAll('*')].every(d => PHRASING.has(tag(d)) || ['script','style','template'].includes(tag(d)));
  const bodyBg = (() => { for (const n of [document.body, document.documentElement]) { if (n && alpha(CS(n).backgroundColor) > 0.05) return CS(n).backgroundColor; } return 'rgb(255, 255, 255)'; })();
  const groundOf = el => { for (let n = el.parentElement; n; n = n.parentElement) { const b = CS(n).backgroundColor; if (alpha(b) > 0.05) return b; } return 'rgb(255, 255, 255)'; };
  const bgBoundary = el => { const b = CS(el).backgroundColor; if (alpha(b) <= 0.05) return false; return !near(b, groundOf(el)); };
  const out = { vw, vh, scrollY: SY, docW: document.documentElement.scrollWidth };
  const all = [...document.querySelectorAll('body *')];

  // edge-flush-cards: check_edge_flush_cards_dom
  const scrolls = el => /(auto|scroll)/.test(CS(el).overflowX);
  out.scrollers = [];
  for (const sc of all) {
    if (!scrolls(sc) || sc.scrollWidth <= sc.clientWidth) continue;
    const r = sc.getBoundingClientRect();
    const cl = r.left + sc.clientLeft, cr = cl + sc.clientWidth;
    const cards = [];
    for (const card of sc.querySelectorAll('*')) {
      if (!painted(card)) continue;
      let o = card.parentElement; while (o && o !== sc && !scrolls(o)) o = o.parentElement;
      if (o !== sc) continue;
      const q = card.getBoundingClientRect();
      if (q.width < 80 || q.height < 40) continue;
      const s = CS(card);
      if (/^(td|th|tr|thead|tbody|tfoot|caption|colgroup|col)$/.test(tag(card)) || /^table-/.test(s.display)) continue;
      const nb = ['Top','Right','Bottom','Left'].filter(k => pf(s['border' + k + 'Width']) > 0).length;
      if (!(alpha(s.backgroundColor) > 0.5) && nb < 2) continue;
      cards.push({ sel: csel(card), left: q.left, right: q.right, lg: q.left - cl, rg: cr - q.right });
      if (cards.length > 60) break;
    }
    out.scrollers.push({ sel: csel(sc), scrollW: sc.scrollWidth, clientW: sc.clientWidth, scrollLeft: sc.scrollLeft, w: r.width, h: r.height, pageTop: r.top + SY, cards });
  }

  // body-text-viewport-edge: body_text_edge_span
  out.edgeText = [];
  for (const el of document.querySelectorAll('p, li, div, section, article, aside, main')) {
    const t = tag(el), s = CS(el), len = el.textContent.trim().length;
    const hasDirect = directLonger(el, 10);
    const edgeTag = t === 'p' || t === 'li';
    const prose = !edgeTag && hasDirect && pf(s.fontSize) < 24 && (s.display === 'block' || s.display === 'flow-root') && !s.whiteSpace.startsWith('pre') && onlyPhrasing(el) && !el.closest('a, button, label, summary, select, textarea, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="option"], [contenteditable="true"], [contenteditable=""]');
    if (!((hasDirect || (edgeTag && onlyPhrasing(el))) && len > 40 && (edgeTag || prose))) continue;
    if (el.closest('nav, header') || alpha(s.backgroundColor) > 0 || s.position === 'fixed' || s.position === 'absolute') continue;
    const r = el.getBoundingClientRect();
    if (!(r.width / vw > 0.5) || !painted(el) || !textPainted(el)) continue;
    let moving = false, cut = false;
    for (let a = el; a && a !== document.body; a = a.parentElement) { if (a.getAnimations && a.getAnimations().some(x => x.playState !== 'finished' && x.playState !== 'idle')) moving = true; }
    const tr = union(textRects(el));
    if (!tr) continue;
    for (let a = el.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      const as = CS(a); if (/(hidden|clip|auto|scroll)/.test(as.overflowX)) { const ar = a.getBoundingClientRect(); if (tr.left < ar.left - 1 || tr.right > ar.right + 1) cut = true; }
    }
    const lh = parseFloat(s.lineHeight) || pf(s.fontSize) * 1.2;
    const lines = rows(textRects(el)).length;
    const cL = r.left + pf(s.borderLeftWidth) + pf(s.paddingLeft), cR = r.right - pf(s.borderRightWidth) - pf(s.paddingRight);
    let left = tr.left, right = tr.right;
    if (lines >= 2 && (tr.right - tr.left) >= (cR - cL) * 0.9) { left = cL; right = cR; }
    else if (s.display === 'list-item') { left = Math.min(tr.left, cL); }
    out.edgeText.push({ sel: csel(el), tag: t, len, left, right, moving, cut, lh });
  }

  // text-overflow: check_element_text_overflow_dom
  out.overflow = [];
  const SKIPO = new Set(['pre','code','textarea','svg','canvas','select','option','marquee']);
  const box = el => { const d = CS(el).display; return d !== 'inline' && d !== 'contents'; };
  const truncates = el => { const s = CS(el); const ax = s.overflowX || (s.overflow || '').split(' ')[0]; if (ax !== 'hidden' && ax !== 'clip') return false; return (s.textOverflow && s.textOverflow !== 'clip') || (s.webkitLineClamp && s.webkitLineClamp !== 'none'); };
  const paintsBox = el => { const s = CS(el); return alpha(s.backgroundColor) > 0.05 || (s.backgroundImage && s.backgroundImage !== 'none') || ['Top','Right','Bottom','Left'].some(k => pf(s['border' + k + 'Width']) > 0); };
  const REPLACED = new Set(['audio','canvas','embed','iframe','img','input','meter','object','picture','progress','select','svg','textarea','video']);
  const harm = (el, boxL, boxR, reachL, reachR) => {
    const sr = reachR > boxR + 1, sl = reachL < boxL - 1;
    if (!sr && !sl) return false;
    const tol = (pf(CS(el).fontSize) || 16) * 0.25;
    for (let c = box(el) ? el : el.parentElement; c && c !== document.body && c !== document.documentElement; c = c.parentElement) {
      if (box(c) && /^(hidden|clip)$/.test(CS(c).overflowX)) { const q = c.getBoundingClientRect(); const l = c.clientWidth > 0 ? q.left + c.clientLeft : q.left; const rr = c.clientWidth > 0 ? l + c.clientWidth : q.right; if (reachR > rr + 1 || reachL < l - 1) return true; }
    }
    if ((sr && reachR >= vw - tol) || (sl && reachL <= tol)) return true;
    const own = el.getBoundingClientRect();
    const regions = []; if (sr) regions.push([boxR, reachR + tol]); if (sl) regions.push([reachL - tol, boxL]);
    for (const o of all) {
      if (o === el || o.contains(el) || el.contains(o)) continue;
      const q = o.getBoundingClientRect();
      if (!(q.width > 0 && q.height > 0) || Math.min(q.bottom, own.bottom) - Math.max(q.top, own.top) <= 1) continue;
      if (q.left <= own.left + 1 && q.right >= own.right - 1 && q.top <= own.top + 1 && q.bottom >= own.bottom - 1) continue;
      if (o.namespaceURI === 'http://www.w3.org/2000/svg' && tag(o) !== 'svg') continue;
      const os = CS(o); if (os.display === 'none' || os.visibility === 'hidden') continue;
      const ht = ownText(o).trim().length > 0, rep = REPLACED.has(tag(o)), pos = os.position;
      if (!ht && !rep && (pos === 'absolute' || pos === 'fixed') && (q.width <= 2 || q.height <= 2 || (os.backgroundImage === 'none' && !['Top','Right','Bottom','Left'].some(k => pf(os['border' + k + 'Width']) > 0) && alpha(os.backgroundColor) * pf(os.opacity) < 0.25))) continue;
      if (!(ht || rep || paintsBox(o))) continue;
      let L = q.left, R = q.right;
      if (ht) { const t = union(directRects(o)); if (t) { L = t.left; R = t.right; } }
      if (regions.some(([a, b]) => L < b && R > a)) return true;
    }
    return false;
  };
  for (const el of all) {
    if (SKIPO.has(tag(el)) || el.namespaceURI === 'http://www.w3.org/2000/svg' || !painted(el)) continue;
    if (!ownText(el).trim()) continue;
    const r = el.getBoundingClientRect(); const s = CS(el);
    if (s.position === 'absolute' && (r.width <= 1 || r.height <= 1 || (s.clip && s.clip !== 'auto') || (s.clipPath && s.clipPath !== 'none'))) continue;
    let sc = false; for (let a = el; a; a = a.parentElement) if (scrolls(a)) { sc = true; break; }
    if (sc || (box(el) && truncates(el))) continue;
    if (!textPainted(el)) continue;
    const cw = el.clientWidth;
    if (cw > 0) {
      const delta = el.scrollWidth - cw;
      if (delta < 16) continue;
      const L = r.left + el.clientLeft, R = L + cw;
      const tr = union(textNodeRects(el)) || { left: L, right: L + el.scrollWidth };
      let reachL = tr.left, reachR = tr.right;
      const after = getComputedStyle(el, '::after').content, before = getComputedStyle(el, '::before').content;
      if ((after && after !== 'none' && after !== 'normal') || (before && before !== 'none' && before !== 'normal')) reachR = Math.max(reachR, L + el.scrollWidth);
      out.overflow.push({ sel: csel(el), kind: 'box', delta, harm: harm(el, L, R, reachL, reachR) });
    } else if (r.width > 0) {
      let c = el.parentElement; while (c && c.clientWidth === 0) c = c.parentElement;
      if (!c) continue;
      let skip = false;
      for (let a = el.parentElement; a; a = a.parentElement) { if (box(a) && truncates(a)) { skip = true; break; } if (a === c) break; }
      for (let a = el; a && a !== c.parentElement; a = a.parentElement) { const t = CS(a).transform; if (t && t !== 'none') skip = true; }
      if (skip) continue;
      const q = c.getBoundingClientRect(); const L = q.left + c.clientLeft, R = L + c.clientWidth;
      out.overflow.push({ sel: csel(el), kind: 'container', delta: r.right - R, harm: harm(el, L, R, r.left, r.right) });
    }
  }

  // text-occlusion: check_text_occlusion_dom (forms i, ii, iii)
  out.occlusion = []; out.overhang = []; out.leaks = [];
  const layered = el => { for (let n = el; n && n !== document.body; n = n.parentElement) { const p = CS(n).position; if (p === 'absolute' || p === 'fixed' || p === 'sticky') return true; } return false; };
  const opaqueBox = el => { const s = CS(el); if (alpha(s.backgroundColor) > 0.6) return 'box'; const nb = ['Top','Right','Bottom','Left'].filter(k => pf(s['border' + k + 'Width']) > 0 && alpha(s['border' + k + 'Color']) > 0.05).length; return nb >= 2 ? 'border' : null; };
  const pinned = el => { for (let n = el; n && n !== document.body; n = n.parentElement) { const p = CS(n).position; if (p === 'fixed' || p === 'sticky') return true; } return false; };
  const marqueeish = el => { for (let n = el, k = 0; n && k < 5; n = n.parentElement, k++) { if (tag(n) === 'marquee') return true; if (/(marquee|ticker)/i.test((n.className && n.className.baseVal === undefined ? n.className : '') + ' ' + n.id) && n.getAnimations && n.getAnimations().length) return true; } return false; };
  const scrollerArrow = (top, victim) => {
    let control = null; for (let c = top, k = 0; c && k < 3; c = c.parentElement, k++) { if (tag(c) === 'button' || tag(c) === 'a' || (c.getAttribute('role') || '').trim().toLowerCase() === 'button') { control = c; break; } }
    if (!control || !/^(absolute|fixed)$/.test(CS(control).position)) return false;
    for (let sc = victim.parentElement; sc; sc = sc.parentElement) {
      if (sc.contains(control)) return false;
      const ox = CS(sc).overflowX; if (ox === 'auto' || ox === 'scroll') {
        const sr = sc.getBoundingClientRect(), cr = control.getBoundingClientRect();
        if (!(sr.height > 0 && cr.width > 0) || !(sc.scrollWidth > sc.clientWidth + 1) || cr.width > 0.25 * sr.width) return false;
        const spans = cr.top <= sr.top + 0.1 * sr.height && cr.bottom >= sr.bottom - 0.1 * sr.height;
        const atEnd = Math.abs(cr.right - sr.right) <= 2 || Math.abs(cr.left - sr.left) <= 2 || (cr.right >= sr.right - 2 && cr.left < sr.right) || (cr.left <= sr.left + 2 && cr.right > sr.left);
        return spans && atEnd;
      }
    }
    return false;
  };
  // a modal dialog or an open popover sits in the top layer, over the page on purpose
  const topLayer = el => { try { return !!el.closest('dialog:modal, :popover-open'); } catch (e) { return false; } };
  const occVictims = [];
  for (const el of all) {
    if (['script','style','noscript','template','title'].includes(tag(el))) continue;
    const text = ownText(el).replace(/\s+/g, ' ').trim();
    if ([...text].length < 2 || !painted(el) || effOp(el) <= 0.05) continue;
    const full = el.getBoundingClientRect();
    if (full.width < 6 || full.height < 6) continue;
    let L = full.left, T = full.top, R = full.right, B = full.bottom, dead = false;
    for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) {
      const s = CS(a); const cx = s.overflowX !== 'visible', cy = s.overflowY !== 'visible'; if (!cx && !cy) continue;
      const q = a.getBoundingClientRect(); if (cx) { L = Math.max(L, q.left); R = Math.min(R, q.right); } if (cy) { T = Math.max(T, q.top); B = Math.min(B, q.bottom); }
      if (R - L < 1 || B - T < 1) { dead = true; break; }
    }
    if (dead || R - L < 6 || B - T < 6 || B <= 0 || T >= vh) continue;
    const fm = (CS(el).filter || '').match(/blur\(([\d.]+)px\)/); if (fm && parseFloat(fm[1]) >= 4) continue;
    occVictims.push({ el, text, rect: { left: L, top: T, right: R, bottom: B, width: R - L, height: B - T } });
    const cols = Math.max(6, Math.min(30, Math.round((R - L) / 12))), rws = Math.max(1, Math.min(4, Math.round((B - T) / 14)));
    const lines = directRects(el);
    let pts = [];
    for (let i = 0; i < cols; i++) { const x = L + (R - L) * ((i + 0.5) / cols); if (x < 1 || x > vw - 1) continue; for (let j = 0; j < rws; j++) { const y = T + (B - T) * ((j + 0.5) / rws); if (y < 1 || y > vh - 1) continue; pts.push([x, y]); } }
    const onLine = pts.filter(([x, y]) => lines.some(q => x >= q.left - 1 && x <= q.right + 1 && y >= q.top - 1 && y <= q.bottom + 1));
    if (onLine.length) pts = onLine;
    let total = 0, occ = 0, kinds = {}, occEl = null;
    for (const [x, y] of pts) {
      total++;
      const top = document.elementFromPoint(x, y);
      if (!top || top === el || el.contains(top) || top.contains(el)) continue;
      if (effOp(top) <= 0.02 || CS(top).pointerEvents === 'none') continue;
      if (/^(left|right)$/.test(CS(top).float) || pinned(top) || topLayer(top) || marqueeish(top) || scrollerArrow(top, el)) continue;
      const stack = document.elementsFromPoint(x, y); const at = stack.indexOf(el);
      if (at > 0 && stack.slice(1, at).some(l => ['img','video','canvas','picture'].includes(tag(l)) || (l.contains(el) && alpha(CS(l).backgroundColor) > 0.6))) continue;
      let kind = null;
      if (ownText(top).trim()) {
        const tr = union(directRects(top)); const vr = union(lines);
        if (!tr || !vr || (x >= tr.left - 1 && x <= tr.right + 1 && y >= tr.top - 1 && y <= tr.bottom + 1) || (tr.left < vr.right && vr.left < tr.right && tr.top < vr.bottom && vr.top < tr.bottom)) kind = 'text';
        if (!kind) kind = opaqueBox(top);
      } else if (top.closest('svg') && top.namespaceURI === 'http://www.w3.org/2000/svg') kind = 'graphic';
      else kind = opaqueBox(top);
      if (!kind) continue;
      occ++; kinds[kind] = (kinds[kind] || 0) + 1; occEl = occEl || top;
    }
    if (occ) {
      const kind = Object.entries(kinds).sort((a, b) => b[1] - a[1])[0][0];
      const vs = el.closest('svg'), os = occEl.closest('svg');
      out.occlusion.push({ sel: csel(el), text: text.slice(0, 24), total, occluded: occ, kind, occSel: csel(occEl),
        layered: layered(el) || layered(occEl), sameSvg: !!(vs && os && vs === os) });
    }
  }
  const cards = [];
  for (const el of all) {
    if (el.closest('svg') || !painted(el)) continue;
    const s = CS(el); if (!(alpha(s.backgroundColor) > 0.7) || !rgb(s.backgroundColor)) continue;
    if (/(gradient|url)\(/.test(s.backgroundImage || '')) continue;
    if (!['Top','Right','Bottom','Left'].some(k => pf(s['border' + k + 'Width']) > 0) && !(s.boxShadow && s.boxShadow !== 'none')) continue;
    if (s.position === 'fixed' || s.position === 'sticky') continue;
    const q = el.getBoundingClientRect(); if (q.width < 100 || q.width > 0.8 * vw || q.height < 60) continue;
    cards.push({ el, q });
  }
  for (const v of occVictims) {
    const s = CS(v.el), fs = pf(s.fontSize) || 16; if (fs < 40) continue;
    const lh = parseFloat(s.lineHeight) || fs * 1.2; const r = v.el.getBoundingClientRect(); const cx = r.left + r.width / 2;
    for (const c of cards) {
      if (c.el === v.el || v.el.contains(c.el) || c.el.contains(v.el)) continue;
      const ix = Math.max(0, Math.min(r.right, c.q.right) - Math.max(r.left, c.q.left)), iy = Math.max(0, Math.min(r.bottom, c.q.bottom) - Math.max(r.top, c.q.top));
      if (ix < 8 || iy < 0.5 * lh || (cx >= c.q.left && cx <= c.q.right) || ix > 0.5 * r.width) continue;
      out.overhang.push({ sel: csel(v.el), text: v.text.slice(0, 24), card: csel(c.el), ix, fs }); break;
    }
  }
  for (const el of all) {
    if (el.closest('svg') || !painted(el)) continue;
    const s = CS(el); if (s.display !== 'inline' || !(alpha(s.backgroundColor) > 0.6) || !rgb(s.backgroundColor)) continue;
    const pt = pf(s.paddingTop), pb = pf(s.paddingBottom); const r = el.getBoundingClientRect();
    const fs = pf(s.fontSize) || 16, lh = parseFloat(s.lineHeight) || fs * 1.4;
    let onto = null;
    for (const o of (el.parentElement ? el.parentElement.children : [])) {
      if (o === el || o.contains(el) || el.contains(o) || CS(o).display === 'none') continue;
      const q = o.getBoundingClientRect(); const ix = Math.max(0, Math.min(r.right, q.right) - Math.max(r.left, q.left)), iy = Math.max(0, Math.min(r.bottom, q.bottom) - Math.max(r.top, q.top));
      if (ix > 4 && iy > 4 && o.textContent.trim()) { onto = csel(o); break; }
    }
    out.leaks.push({ sel: csel(el), pad: pt + pb, w: r.width, h: r.height, lh, lines: Math.max(1, rows(textRects(el)).length), onto });
  }

  // first-viewport-column-overflow: check_first_viewport_column_overflow_dom
  out.columns = [];
  const linkRail = col => { const chars = n => n.textContent.split(/\s+/).join('').length; const total = chars(col); if (!(total > 0)) return false; const links = [...col.querySelectorAll('a')]; const outer = links.filter(a => !links.some(o => o !== a && o.contains(a))); const shownL = outer.filter(a => painted(a)); if (shownL.length < 3) return false; const t = total - outer.filter(a => !painted(a)).reduce((s, a) => s + chars(a), 0); const lc = shownL.reduce((s, a) => s + chars(a), 0); return t > 0 && lc >= 0.9 * t && lc / shownL.length <= 40; };
  for (const el of all) {
    if (!/^(inline-)?(grid|flex)$/.test(CS(el).display)) continue;
    const r = el.getBoundingClientRect(); const top = r.top + SY;
    if (r.width < 0.5 * vw || top >= vh * 0.9 || top + r.height <= vh) continue;
    const cols = [];
    for (const ch of el.children) {
      const s = CS(ch); if (s.display === 'none' || ['absolute','fixed','sticky'].includes(s.position) || tag(ch) === 'nav') continue;
      if (/\b(navigation|tablist)\b/i.test(ch.getAttribute('role') || '') || linkRail(ch)) continue;
      const q = ch.getBoundingClientRect(); const share = q.width / r.width; if (share < 0.25 || share > 0.9 || q.height < 40) continue;
      let bottom = q.top; const lifted = [];
      for (const d of ch.querySelectorAll('*')) {
        const ds = CS(d); if (ds.position === 'absolute' || ds.position === 'fixed') { lifted.push(d); continue; }
        if (lifted.some(l => l.contains(d)) || ds.display === 'none' || ds.visibility === 'hidden') continue;
        const det = d.parentElement && d.parentElement.closest('details:not([open])'); if (det && ch.contains(det) && d.parentElement !== det) continue;
        if (det && ch.contains(det) && tag(d) !== 'summary') continue;
        const dr = d.getBoundingClientRect(); if (!(dr.width > 0 && dr.height > 0)) continue;
        let b = dr.bottom; for (let a = d.parentElement; a && a !== el.parentElement; a = a.parentElement) { if (/(hidden|clip|auto|scroll)/.test(CS(a).overflowY)) b = Math.min(b, a.getBoundingClientRect().bottom); if (a === el) break; }
        bottom = Math.max(bottom, b);
      }
      if (bottom - q.top < 1) continue;
      cols.push({ top: q.top, left: q.left, right: q.right, contentH: bottom - q.top });
    }
    if (cols.length >= 2) out.columns.push({ sel: csel(el), cols });
  }

  // heading-rhythm: check_heading_rhythm_dom (simplified walk; thresholds are applied in Python)
  out.heads = [];
  const MEDIA = new Set(['img','picture','video','canvas','svg','iframe']);
  const inFlow = el => { const s = CS(el); const r = el.getBoundingClientRect(); return s.display !== 'none' && s.position !== 'absolute' && s.position !== 'fixed' && r.width >= 1 && r.height >= 1; };
  const isContents = el => CS(el).display === 'contents';
  const imgBand = s => s.backgroundImage && s.backgroundImage !== 'none' && (!/no-repeat/.test(s.backgroundRepeat) || /cover|100%/.test(s.backgroundSize));
  const band = el => { const s = CS(el); return bgBoundary(el) || imgBand(s) || (s.boxShadow && s.boxShadow !== 'none'); };
  const edgeTop = el => { const s = CS(el); return (pf(s.borderTopWidth) > 0 && alpha(s.borderTopColor) > 0.05) || band(el); };
  const edgeBottom = el => { const s = CS(el); return (pf(s.borderBottomWidth) > 0 && alpha(s.borderBottomColor) > 0.05) || band(el); };
  const spacer = el => !el.shadowRoot && !el.textContent.trim() && !el.querySelector('img,picture,video,canvas,svg,iframe,input,textarea,select,button,hr') && !MEDIA.has(tag(el)) && tag(el) !== 'hr' && !edgeTop(el) && !edgeBottom(el) && !(CS(el).backgroundImage !== 'none');
  // rhythm_repeats: a run of like boxes, each holding a heading like this one at the same place
  const pathTo = (row, h) => { const p = []; for (let n = h; n && n !== row; n = n.parentElement) p.unshift(tag(n)); return p.join('>'); };
  const repeats = (p, h) => { const want = pathTo(p, h); return [...(p.parentElement ? p.parentElement.children : [])].some(s => s !== p && tag(s) === tag(p) && s.className === p.className && [...s.querySelectorAll(tag(h))].some(x => pathTo(s, x) === want)); };
  const contentBottom = el => { const r = el.getBoundingClientRect(); const s = CS(el); return edgeBottom(el) ? r.bottom : r.bottom - pf(s.paddingBottom); };
  const cardLike = el => { const s = CS(el); return (s.boxShadow && s.boxShadow !== 'none') || ((pf(s.borderTopLeftRadius) > 0) && (bgBoundary(el) || ['Top','Right','Bottom','Left'].filter(k => pf(s['border' + k + 'Width']) > 0).length >= 3)); };
  const flowBox = (s, rect, pick) => { if (isContents(s)) { const k = [...s.children].filter(c => inFlow(c)); return k.length ? k : null; } return inFlow(s) ? [s] : null; };
  const textSize = el => { let best = 0; for (const d of [el, ...el.querySelectorAll('*')]) if (ownText(d).trim()) { best = pf(CS(d).fontSize); break; } return best; };
  const framed = el => { const s = CS(el); return ['Top','Right','Bottom','Left'].every(k => pf(s['border' + k + 'Width']) > 0); };
  const separates = el => { if (tag(el) === 'hr' || MEDIA.has(tag(el))) return true; const s = CS(el); if (pf(s.borderBottomWidth) > 0 && alpha(s.borderBottomColor) > 0.05 && !framed(el)) return true; if (imgBand(s)) return true; const last = el.lastElementChild; return !!(last && (MEDIA.has(tag(last)) || tag(last) === 'hr')); };
  const endsInProse = (block, h, ts) => { const ps = [block, ...block.querySelectorAll('*')].filter(d => ownText(d).trim().length > 0); const last = ps[ps.length - 1]; if (!last) return false; const len = last.textContent.trim().length; const lines = rows(textRects(last)).length; const fs = pf(CS(last).fontSize); return len >= 80 && lines >= 2 && fs <= ts * 1.25 && last.getBoundingClientRect().width >= 0.5 * h.getBoundingClientRect().width; };
  const pageText = pf(CS(document.body).fontSize) || 16;
  const colDiff = (a, b) => { const x = rgb(CS(a).color), y = rgb(CS(b).color); if (!x || !y) return false; return [0,1,2].some(i => Math.abs(x[i] - y[i]) >= 32) || Math.abs((x[3] ?? 1) - (y[3] ?? 1)) >= 0.25; };
  const italic = el => /^(italic|oblique)/.test(CS(el).fontStyle);
  const weight = el => { const w = CS(el).fontWeight; return w === 'bold' ? 700 : w === 'normal' ? 400 : pf(w); };
  // rhythm_reads_as_eyebrow + rhythm_set_apart
  const readsAsEyebrow = (line, h, ts, opens) => {
    const hs = pf(CS(h).fontSize); const span = Math.max(h.getBoundingClientRect().width, line.getBoundingClientRect().width);
    for (const e of [line, ...line.querySelectorAll('*')].slice(0, 40)) {
      const er = e.getBoundingClientRect(); const es = CS(e);
      if (pf(es.borderBottomWidth) > 0 && alpha(es.borderBottomColor) > 0.05 && er.width >= 1 && er.width < span * 0.6 && e.textContent.trim()) return true;
      if (!ownText(e).trim()) continue;
      const size = pf(es.fontSize); if (size > hs) continue;
      if (size < ts * 0.92 || es.textTransform === 'uppercase' || pf(es.letterSpacing) >= 0.5) return true;
      const cased = ownText(e).replace(/[^A-Za-zÀ-ɏ]/g, ''); if (cased.length >= 3 && cased === cased.toUpperCase()) return true;
      if (opens) {
        const box = line.parentElement; if (!box || line.textContent.replace(/\s+/g, ' ').trim().length > 40) continue;
        const lh = parseFloat(es.lineHeight) || size * 1.2; const t = union(directRects(e));
        if (!(t && t.bottom - t.top > 0 && t.bottom - t.top < Math.max(lh, size * 1.2) * 1.5)) continue;
        if ((colDiff(e, box) && colDiff(e, h)) || (italic(e) && !italic(box) && !italic(h)) || weight(e) <= weight(box) - 300) return true;
      }
    }
    return false;
  };
  for (const h of document.querySelectorAll('h2, h3, h4')) {
    if (!inFlow(h) || !painted(h) || h.closest('blockquote, q')) continue;
    const text = h.textContent.replace(/\s+/g, ' ').trim(); if (text.length < 3) continue;
    if (edgeTop(h)) continue;
    const rect = h.getBoundingClientRect();
    // below
    let below = null, belowEl = null, node = h;
    while (node && node !== document.body) {
      let best = null;
      for (let s = node.nextElementSibling; s; s = s.nextElementSibling) { const bs = flowBox(s); if (!bs) continue; for (const b of bs) { const q = b.getBoundingClientRect(); if (q.top < rect.bottom - 2 || spacer(b)) continue; if (!best || q.top < best[0]) best = [q.top, b]; } }
      if (best) { if (node !== h && /^(footer|aside|nav)$/.test(tag(best[1]))) best = null; [below, belowEl] = best || [null, null]; break; }
      const p = node.parentElement; if (!p || p === document.body) break;
      if (!isContents(p) && (edgeBottom(p) || repeats(p, h))) break;
      if (tag(p) === 'main') break;
      node = p;
    }
    if (below === null) continue;
    const ts = Math.max(pageText, textSize(belowEl));
    // cluster top: fold an eyebrow label sitting just above
    let top = rect.top, startEl = h;
    for (let k = 0, cur = h; k < 3; k++) {
      let sib = cur.previousElementSibling; while (sib && !inFlow(sib)) sib = sib.previousElementSibling;
      if (!sib) { const p = cur.parentElement; if (p && p !== document.body && Math.abs(p.getBoundingClientRect().top - top) <= 1 && !edgeTop(p)) { cur = p; k--; if (cur === document.body) break; continue; } break; }
      const sr = sib.getBoundingClientRect(); const gap = top - sr.bottom; const tx = sib.textContent.trim();
      if (gap < 0 || gap >= 28 || sr.height > 60 || !tx || tx.length > 80 || /^h[1-6]$/.test(tag(sib))) break;
      const opens = (() => { let p = sib.previousElementSibling; while (p && !inFlow(p)) p = p.previousElementSibling; return !p; })();
      const eyebrow = readsAsEyebrow(sib, h, ts, opens);
      if (!eyebrow) break;
      top = sr.top; startEl = sib; cur = sib;
    }
    // above
    let above = null, aboveEl = null; node = startEl;
    const inset = edgeTop(startEl) ? 0 : pf(CS(startEl).paddingTop);
    while (node && node !== document.body) {
      let best = null;
      for (let s = node.previousElementSibling; s; s = s.previousElementSibling) { const bs = flowBox(s); if (!bs) continue; for (const b of bs) { const q = b.getBoundingClientRect(); if (q.bottom > top + 2 || spacer(b)) continue; if (q.right < rect.left || q.left > rect.right) continue; const cb = contentBottom(b); if (!best || cb > best[0]) best = [cb, b]; } }
      if (best) { above = best[0] - inset; aboveEl = best[1]; break; }
      const p = node.parentElement; if (!p || p === document.body) break;
      if (edgeTop(p)) break;
      node = p;
    }
    if (above === null) continue;
    let small = false; for (let c = h.parentElement; c && c !== document.body; c = c.parentElement) if (cardLike(c) && c.getBoundingClientRect().height < 200) { small = true; break; }
    out.heads.push({ sel: csel(h), tag: tag(h), text: text.slice(0, 60), above: Math.max(0, top - above), below: Math.max(0, below - rect.bottom),
      small, prose: endsInProse(aboveEl, h, ts), separates: separates(aboveEl) });
  }

  // line-length (browser quality.rs), cramped-padding text-inset form, blinking-cursor
  out.lines = []; out.cramped = []; out.cursors = [];
  // rendered_text_len: the characters a reader sees (no <style> payload, no hidden child, white space collapsed)
  const renderedLen = el => { let t = ''; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); for (let n = w.nextNode(); n; n = w.nextNode()) { const p = n.parentElement; if (!p || ['SCRIPT','STYLE','NOSCRIPT','TEMPLATE'].includes(p.tagName) || (p !== el && !painted(p))) continue; t += n.textContent; } return t.replace(/\s+/g, ' ').trim().length; };
  const QTAGS = new Set(['p','li','td','th','dd','blockquote','figcaption']);
  for (const el of all) {
    const t = tag(el); const s = CS(el); const pt = painted(el);
    // a blinking cursor is caught at whatever phase: its own animated opacity may be 0 at capture
    if (!pt && !(shown(el) && (!el.parentElement || effOp(el.parentElement) > 0.02))) continue;
    const hasDirect = directLonger(el, 10); const len = el.textContent.trim().length;
    const proseIn = !hasDirect && ['p','li','dd','blockquote'].includes(t) && onlyPhrasing(el);
    const proseBlock = !QTAGS.has(t) && hasDirect && ['div','section','article','aside','main'].includes(t) && (s.display === 'block' || s.display === 'flow-root') && onlyPhrasing(el) && pf(s.fontSize) < 24;
    if (pt && (hasDirect || proseIn) && (QTAGS.has(t) || proseBlock) && len > 80 && textPainted(el)) {
      const ws = rows(textRects(el)).map(r => r.right - r.left);
      out.lines.push({ sel: csel(el), widths: ws, len: renderedLen(el) });
    }
    const r = el.getBoundingClientRect();
    if (pt && hasDirect && len > 20 && r.width > 100 && s.display !== 'inline' && r.height > 30 && !(t === 'code' && !el.closest('pre'))) {
      const bw = ['Top','Right','Bottom','Left'].map(k => pf(s['border' + k + 'Width']));
      const bv = ['Top','Right','Bottom','Left'].map((k, i) => bw[i] > 0 && alpha(s['border' + k + 'Color']) > 0.05);
      const hasBg = bgBoundary(el);
      if (bv.filter(Boolean).length >= 2 || hasBg) {
        const tr = union(directRects(el));
        if (tr) out.cramped.push({ sel: csel(el), fs: pf(s.fontSize), pads: ['Top','Right','Bottom','Left'].map(k => pf(s['padding' + k])),
          insets: [tr.top - (r.top + bw[0]), (r.right - bw[1]) - tr.right, (r.bottom - bw[2]) - tr.bottom, tr.left - (r.left + bw[3])],
          borders: bv, bg: hasBg, fullBleed: hasBg && r.left <= 2 && r.right >= document.documentElement.clientWidth - 2 });
      }
    }
    if (!['input','textarea','select','img','svg','script','style'].includes(t) && el.getAnimations) {
      const anims = el.getAnimations().filter(a => a.animationName && a.effect && a.effect.getTiming().iterations === Infinity);
      if (anims.length && !el.closest('[contenteditable=""], [contenteditable="true"], [role="textbox"]') && !el.isContentEditable) {
        let name = (anims.find(a => /blink|caret|cursor/i.test(a.animationName)) || {}).animationName;
        if (!name) for (const a of anims) { const kf = a.effect.getKeyframes(); let tog = false, other = false; for (const f of kf) for (const [k, v] of Object.entries(f)) { if (['offset','computedOffset','easing','composite'].includes(k)) continue; if (k === 'opacity') { if (parseFloat(v) <= 0.15) tog = true; } else if (k === 'visibility') { if (/hidden/i.test(v)) tog = true; } else if (k !== 'animationTimingFunction') other = true; } if (tog && !other) { name = a.animationName; break; } }
        if (name && r.width > 0 && r.height > 0) {
          const txt = el.textContent.trim();
          out.cursors.push({ sel: csel(el), name, w: r.width, h: r.height, pageTop: r.top + SY, glyph: /^[_|▀-▟■▮❙❚｜]$/.test(txt),
            empty: !txt && el.children.length === 0, filled: alpha(s.backgroundColor) > 0.2 || ['Left','Right','Bottom'].some(k => pf(s['border' + k + 'Width']) >= 1),
            radius: pf(s.borderTopLeftRadius), inHeader: !!el.closest('header, nav, [role="banner"], [role="navigation"]') });
        }
      }
    }
  }

  // content-hidden-at-rest: measure_hidden_text_dom (+ scroll probe of the largest hidden roots)
  const EXCL = new Set(['script','style','noscript','template','title','head','meta','link','option','optgroup','select','datalist','dialog']);
  // closed_container (page_checks.rs): navigation, closed panels, collapsed triggers, inert, off-screen drawers
  const classWords = tok => { const w = []; let cur = '', prevLower = false; for (const c of tok) { const an = /[A-Za-z0-9]/.test(c); if (!an || (/[A-Z]/.test(c) && prevLower)) { if (cur) { w.push(cur); cur = ''; } } if (an) cur += c.toLowerCase(); prevLower = /[a-z]/.test(c); } if (cur) w.push(cur); return w; };
  const closedClass = tok => { const w = classWords(tok); const has = x => w.includes(x); const pair = (a, b) => w.some((x, i) => x === a && w[i + 1] === b);
    if (['offcanvas','drawer','megamenu','submenu','dropdown','flyout','modal','tabpanel','tabpane'].some(has) || pair('off','canvas') || pair('mega','menu') || pair('sub','menu')) return true;
    return ['content','panel','pane','body'].some(has) && (has('tab') || has('tabs') || has('accordion')); };
  const ctl = [...document.querySelectorAll('[aria-controls]')];
  const isTrue = (e, n) => (e.getAttribute(n) || '').trim().toLowerCase() === 'true';
  const closedIds = (() => { const c = new Set(), o = new Set(); for (const t of ctl) { const ex = (t.getAttribute('aria-expanded') || '').trim().toLowerCase(), se = (t.getAttribute('aria-selected') || '').trim().toLowerCase(); for (const id of t.getAttribute('aria-controls').split(/\s+/)) { if (ex === 'true' || se === 'true') o.add(id); else if (ex === 'false' || se === 'false') c.add(id); } } for (const id of o) c.delete(id); return c; })();
  const markedOpen = el => { const id = (el.id || '').trim(); if (id && ctl.some(t => t.getAttribute('aria-controls').split(/\s+/).includes(id) && (isTrue(t, 'aria-selected') || isTrue(t, 'aria-expanded')))) return true; const lab = (el.getAttribute('aria-labelledby') || '').trim(); if (!lab) return false; return [...document.querySelectorAll('[aria-selected]')].some(t => isTrue(t, 'aria-selected') && t.id && lab.split(/\s+/).includes(t.id)); };
  const roleOf = e => (e.getAttribute('role') || '').trim().toLowerCase();
  const closedContainer = el => {
    const cls = typeof el.className === 'string' ? el.className : ''; const r = roleOf(el);
    const tabLike = r === 'tabpanel' || cls.split(/\s+/).some(t => classWords(t).some(w => ['tab','tabs','tabpanel','tabpane'].includes(w)));
    const selected = tabLike && markedOpen(el);
    if (!selected && ['dialog','alertdialog','tabpanel'].includes(r)) return true;
    if (!selected && cls.split(/\s+/).filter(Boolean).some(closedClass)) return true;
    const collapsed = e => (e.getAttribute('aria-expanded') || '').trim().toLowerCase() === 'false';
    const before = el.previousElementSibling;
    if (before && (collapsed(before) || (before.firstElementChild && collapsed(before.firstElementChild) && (/^h[1-6]$/.test(tag(before)) || roleOf(before) === 'heading' || before.children.length === 1)))) return true;
    const s = CS(el);
    if (s.position === 'fixed') { const q = el.getBoundingClientRect(); if (q.width > 0 && (q.right <= 0 || q.left >= vw)) return true;
      if (/^(hidden|collapse)$/.test(s.visibility) && q.left <= 1 && q.top <= 1 && q.right >= vw - 1 && q.bottom >= vh - 1 && !(el.matches('main, [role="main"], h1') || el.querySelector('main, [role="main"], h1') || el.textContent.trim().length * 2 >= document.body.textContent.trim().length)) return true; }
    for (let a = el; a && a.nodeType === 1; a = a.parentElement) {
      if (tag(a) === 'nav' || ['navigation','menu','menubar'].includes(roleOf(a)) || a.hasAttribute('inert') || (a.id && closedIds.has(a.id))) return true;
      const as = CS(a); if ((as.position === 'absolute' || as.position === 'fixed') && as.transform && as.transform !== 'none' && /transform|all/.test(as.transitionProperty)) { const q = a.getBoundingClientRect(); if (q.width > 0 && (q.right <= 0 || q.left >= vw)) return true; }
    }
    return false;
  };
  const parkedOutsideClip = el => { const q = el.getBoundingClientRect(); for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { const s = CS(a); if (/(hidden|clip)/.test(s.overflowX + ' ' + s.overflowY)) { const c = a.getBoundingClientRect(); if (q.right <= c.left || q.left >= c.right || q.bottom <= c.top || q.top >= c.bottom) return true; } } return false; };
  const SLIDER = /(^|[\s_-])(slider|carousel|swiper|slick|splide|glide|flickity|slideshow|revslider)($|[\s_-])/i;
  // unstarted_slider: a slider box in which no text and no picture shows at all
  const SLIDE_PART = /(^|[\s_-])(slide|item|cell|card|pane|caption)($|[\s_-])/i;
  const sliderMemo = new Map();
  const unstarted = a => { if (!sliderMemo.has(a)) sliderMemo.set(a, ![...a.querySelectorAll('*')].some(d => (ownText(d).trim() || ['img','picture','video','canvas','svg'].includes(tag(d))) && painted(d) && d.getBoundingClientRect().width > 0)); return sliderMemo.get(a); };
  const cache = new Map();
  const state = el => {
    if (!el || el === document.documentElement || el === document.body) return 'V';
    if (cache.has(el)) return cache.get(el);
    let st;
    if (EXCL.has(tag(el))) st = 'X';
    else {
      const ps = state(el.parentElement); const s = CS(el);
      if (ps === 'X' || s.display === 'none' || el.hidden || el.getAttribute('aria-hidden') === 'true' || s.contentVisibility === 'hidden') st = 'X';
      else if (ps === 'U' || ps === 'I') st = ps;
      else if (pf(s.opacity) <= 0.02 || /^(hidden|collapse)$/.test(s.visibility)) {
        const byVis = /^(hidden|collapse)$/.test(s.visibility);
        if (closedContainer(el) || parkedOutsideClip(el)) st = 'X';
        else if (!byVis && el.getAnimations && el.getAnimations().some(a => a.playState === 'running' && a.effect && a.effect.getKeyframes().some(f => 'opacity' in f && parseFloat(f.opacity) > 0.02))) st = 'V';
        else { let un = false; for (let a = el; a; a = a.parentElement) if (typeof a.className === 'string' && SLIDER.test(a.className) && !SLIDE_PART.test(a.className) && unstarted(a)) { un = true; break; } st = un ? 'U' : 'I'; }
      } else st = 'V';
    }
    cache.set(el, st); return st;
  };
  let total = 0, hidden = 0; const hiddenEls = [], roots = new Map();
  for (const el of all) {
    let len = 0; for (const c of el.childNodes) if (c.nodeType === 3) len += c.textContent.replace(/\s+/g, ' ').trim().length;
    if (!len) continue;
    const st = state(el); if (st === 'X' || st === 'U') continue;
    total += len;
    if (st === 'I') { hidden += len; let start = el; while (start.parentElement && cache.get(start.parentElement) === 'I') start = start.parentElement; hiddenEls.push([el, start, len]); roots.set(start, (roots.get(start) || 0) + len); }
  }
  if (opt && opt.full && total >= 200 && hidden >= 150 && hidden / total > 0.3) {
    const big = [...roots.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(e => e[0]); const shownRoots = new Set();
    // Dom::shown_when_scrolled_to: scroll the box through the window and look again at each stop
    for (const root of big) {
      const base = window.scrollY + root.getBoundingClientRect().top;
      for (const off of [-vh / 2, 0, vh / 2, vh, 1.5 * vh]) {
        window.scrollTo({ top: Math.max(0, base + off), behavior: 'instant' });
        await new Promise(r => setTimeout(r, 160));
        if (effOp(root) > 0.02 && shown(root)) { shownRoots.add(root); for (const he of hiddenEls) if (he[1] === root && effOp(he[0]) > 0.02) he[0].__shown = true; break; }
      }
    }
    window.scrollTo({ top: 0, behavior: 'instant' }); await new Promise(r => setTimeout(r, 100));
    for (const [el, start, len] of hiddenEls) if (el.__shown) hidden -= len;
  }
  out.hiddenText = { total, hidden, samples: hiddenEls.filter(([el]) => !el.__shown).slice(0, 3).map(([el]) => el.textContent.replace(/\s+/g, ' ').trim().slice(0, 40)) };
  return out;
}"""


def _exe():
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    for cand in ([Path(base) / "chromium"] if base else []) + [Path("/opt/pw-browsers/chromium")]:
        if cand.is_file():
            return str(cand)
    return None


INSTALL_HINT = ("optional, one line: `pip install playwright` (Python) or `npm i -g playwright` (node); an installed "
                "Chrome or Edge is used as-is, else add `python -m playwright install chromium`")


def available():
    """(bool, reason). Python Playwright first, then node's; STUDIO_DETECTOR_BROWSER=off forces static."""
    if os.environ.get("STUDIO_DETECTOR_BROWSER", "").lower() in ("off", "0", "no"):
        return False, "STUDIO_DETECTOR_BROWSER=off"
    if importlib.util.find_spec("playwright") is not None:
        return True, "playwright via python"
    node = shutil.which("node")
    if node:
        p = subprocess.run([node, "-e", "require.resolve('playwright')"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return True, "playwright via node"
    return False, "no Playwright found (%s)" % INSTALL_HINT


def _viewports():
    return [{"width": 1280, "height": 800}, {"width": 390, "height": 844}]


def _probe_python(path, shot, settle):
    """The same probe through Python Playwright (sync API)."""
    from playwright.sync_api import sync_playwright
    out = {"viewports": []}
    with sync_playwright() as pw:
        browser, last = None, None
        exe = _exe()
        for kw in ([{"executable_path": exe}] if exe else []) + [{}, {"channel": "chrome"}, {"channel": "msedge"}]:
            try:
                browser = pw.chromium.launch(headless=True, **kw)
                break
            except Exception as e:  # noqa: BLE001 - try the next browser
                last = e
        if browser is None:
            raise RuntimeError(str(last))
        for vp in _viewports():
            page = browser.new_page(viewport=vp)
            errors = []
            page.on("pageerror", lambda e, errors=errors: errors.append({"message": "%s: %s" % (getattr(e, "name", "Error"), getattr(e, "message", e)), "stack": getattr(e, "stack", "") or ""}))
            page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("file:", "data:")) else r.abort())
            try:
                page.goto(Path(path).resolve().as_uri(), wait_until="load", timeout=15000)
            except Exception as e:  # noqa: BLE001
                errors.append({"message": "load: %s" % e, "stack": ""})
            page.wait_for_timeout(settle)
            try:
                m = page.evaluate(MEASURE, {"full": vp["width"] >= 1000})
            except Exception as e:  # noqa: BLE001
                m = {"measureError": str(e)}
            if shot and vp["width"] >= 1000:
                page.screenshot(path=shot, full_page=True)
            d = {"width": vp["width"], "height": vp["height"], "errors": errors}
            d.update(m)
            out["viewports"].append(d)
            page.close()
        browser.close()
    return out


def probe(path, shot=None, settle=1200):
    ok, why = available()
    if not ok:
        return None, why
    if why.endswith("python"):
        try:
            return _probe_python(path, shot, settle), "playwright (python)"
        except Exception as e:  # noqa: BLE001 - fall through to node, else report
            if not shutil.which("node"):
                return None, "browser probe failed: %s" % str(e)[:200]
    with tempfile.TemporaryDirectory() as t:
        js = Path(t) / "probe.cjs"
        js.write_text(PROBE.replace("MEASURE", MEASURE), encoding="utf-8")
        cfg = Path(t) / "cfg.json"
        cfg.write_text(json.dumps({"url": Path(path).resolve().as_uri(), "exe": _exe(), "settle": settle, "shot": shot,
                                   "viewports": _viewports()}), encoding="utf-8")
        try:
            p = subprocess.run([shutil.which("node"), str(js), str(cfg)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        except subprocess.TimeoutExpired:
            return None, "browser probe timed out"
        try:
            data = json.loads(p.stdout)
        except ValueError:
            return None, "browser probe failed: %s" % (p.stderr.strip()[-200:] or p.stdout[-200:])
        if "fatal" in data:
            return None, "browser probe failed: %s" % data["fatal"][:200]
        return data, "playwright (node)"


# ---------------------------------------------------------------------------------------------------------------------
# static approximations: used ONLY when no browser is available; every hit is advisory and labelled static-approx, and
# the rule still reads NOT RUN (approximated) in the summary, so a static pass is never presented as rendered parity.
APPROX_RULES = ("line-length", "body-text-viewport-edge", "content-hidden-at-rest")


def static_approx(ctx):
    """[(rule, snippet)] from the static cascade at a 1280px desktop: text blocks whose declared measure runs past
    ~85 characters, long paragraphs with no horizontal inset on any ancestor, and text hidden at rest by CSS."""
    from . import css as C
    hits = []
    if ctx.doc is None:
        return hits
    total = hidden = 0
    for n in ctx.elements():
        txt = " ".join(n.own_text().split())
        if not txt:
            continue
        total += len(txt)
        st = n.style or {}
        chain = [n] + list(n.ancestors())
        if any((a.style or {}).get("opacity", "1").strip() in ("0", "0.0") or (a.style or {}).get("visibility") == "hidden" for a in chain):
            hidden += len(txt)
        if n.tag not in ("p", "li", "dd", "blockquote") or len(txt) < 160:
            continue
        fs = st.get("__font_px__", 16.0)
        width, inset = 1280.0, 0.0
        for a in chain:
            ast = a.style or {}
            mw = C.length_px(ast.get("max-width"), ast.get("__font_px__", 16.0), 16.0, 1280.0) if ast.get("max-width") else None
            if mw:
                width = min(width, mw)
            for side in ("left", "right"):
                for k in ("padding-" + side, "margin-" + side):
                    v = C.length_px(ast.get(k), ast.get("__font_px__", 16.0), 16.0, 1280.0) if ast.get(k) not in (None, "auto") else None
                    inset = max(inset, v or 0.0) if k.startswith("padding") or (ast.get(k) or "") != "auto" else inset
            if (ast.get("margin-left") or "") == "auto" and mw:
                inset = max(inset, 16.0)
        chars = width / (fs * 0.5)
        if chars > 85:
            hits.append({"rule": "line-length", "severity": "advisory", "engine": "static-approx",
                         "snippet": "static approximation: %s measure ~%d characters at 1280px (declared max-width %s)" % (n.selector(), chars, "none" if width == 1280 else "%dpx" % width)})
        if inset < 16 and width >= 1200:
            hits.append({"rule": "body-text-viewport-edge", "severity": "advisory", "engine": "static-approx",
                         "snippet": "static approximation: %s has no >=16px horizontal inset on any ancestor" % n.selector()})
    if total >= 200 and hidden / total >= 0.3:
        hits.append({"rule": "content-hidden-at-rest", "severity": "advisory", "engine": "static-approx",
                     "snippet": "static approximation: %d of %d text characters hidden by CSS at rest" % (hidden, total)})
    seen, out = set(), []
    for h in hits:
        k = (h["rule"], h["snippet"])
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out[:20]


# ---------------------------------------------------------------------------------------------------------------------
# judging: measures -> findings
def _n(v):
    """JS number -> string (4 not 4.0)."""
    v = float(v)
    return str(int(v)) if v.is_integer() else ("%.6f" % v).rstrip("0").rstrip(".")


def _r(v):
    import math
    return int(math.floor(float(v) + 0.5))


REACT_RECOVERABLE = {418, 419, 422, 423, 425}
AD_TECH_HOSTS = (("AnyMind", "anymind360.com"), ("Meta Pixel", "connect.facebook.net"),
                 ("Google Tag Manager", "googletagmanager.com"), ("OneTrust", "cookielaw.org"),
                 ("Google Ads", "googlesyndication.com"), ("Google Ads", "doubleclick.net"),
                 ("Google Ads", "googleadservices.com"), ("Nagich", "nagich.co.il"),
                 ("Chase Reporting", "asset.chase.com/web/library/digddsautomation/reportingjs/"))
AD_TECH_APIS = (("browsingTopics", "ad tech"), ("joinAdInterestGroup", "ad tech"), ("runAdAuction", "ad tech"),
                ("adsbygoogle", "Google Ads"), ("_prebidjs", "Prebid"))


def ad_tech_vendor(message, source):
    """third_party.rs ad_tech_vendor: by the script URL's host/path (or a prebid* file), else by the API named."""
    for tok in re.split(r"[\s,()]+", source or ""):
        if "://" not in tok:
            continue
        rest = re.split(r"[?#]", tok.split("://", 1)[1])[0]
        auth, _, path = rest.partition("/")
        host = auth.rsplit("@", 1)[-1].split(":")[0].lower()
        path = path.lower()
        for name, src in AD_TECH_HOSTS:
            dom, _, prefix = src.partition("/")
            if (host == dom or host.endswith("." + dom)) and path.startswith(prefix):
                return name
        fname = re.sub(r"(:\d+){1,2}$", "", path.rsplit("/", 1)[-1])
        if fname.startswith("prebid"):
            return "Prebid"
    for api, name in AD_TECH_APIS:
        if api in (message or ""):
            return name
    return None


def script_error_hits(errors):
    """script_errors.rs + third_party.rs: one finding per uncaught error; ad tech / React hydration -> advisory."""
    hits, seen = [], set()
    for e in errors:
        msg, stack = (e, "") if isinstance(e, str) else (e.get("message", ""), e.get("stack", ""))
        if msg.startswith("load:") or msg in seen:
            continue
        seen.add(msg)
        snippet, sev = msg[:200], None
        m = re.search(r"Minified React error #(\d+)", msg)
        vendor = ad_tech_vendor(msg, stack)
        if vendor:
            snippet, sev = "%s (third-party: %s)" % (snippet, vendor), "advisory"
        elif m and int(m.group(1)) in REACT_RECOVERABLE:
            sev = "advisory"
        h = {"rule": "script-error", "snippet": snippet}
        if sev:
            h["severity"] = sev
        hits.append(h)
    return hits


def hidden_hits(m):
    """measures.rs check_content_hidden_at_rest: >=200 chars, >=150 hidden, share > 0.3."""
    t = m or {}
    total, hidden = t.get("total", 0), t.get("hidden", 0)
    if not (total >= 200 and hidden >= 150 and hidden / total > 0.3):
        return []
    sample = ' (e.g. "%s")' % t["samples"][0] if t.get("samples") else ""
    return [("content-hidden-at-rest", "%s%% of page text (%s of %s chars) stays at opacity 0 / visibility hidden after "
             "reveal handlers ran%s" % (_n(_r(hidden / total * 100)), _n(hidden), _n(total), sample))]


def edge_flush_hits(vp):
    """page_checks.rs check_edge_flush_cards_dom."""
    hits = []
    for sc in vp.get("scrollers", []):
        if sc["scrollW"] <= sc["clientW"] + 8 or sc["scrollLeft"] > 4 or sc["w"] < 120 or sc["h"] < 60:
            continue
        if sc["pageTop"] > 2 * vp["vh"]:
            continue
        flush, first_right, last_left = [], float("inf"), float("-inf")
        for c in sc["cards"]:
            first_right, last_left = min(first_right, c["right"]), max(last_left, c["left"])
            fr = c["lg"] >= 6 and -24 < c["rg"] < 8
            fl = c["rg"] >= 6 and -24 < c["lg"] < 8
            if fr or fl:
                flush.append((c["sel"], "right" if fr else "left", _r(c["rg"] if fr else c["lg"])))
        if not flush or first_right > last_left + 1:
            continue
        worst = min(flush, key=lambda f: f[2])
        hits.append(("edge-flush-cards", "%d card%s flush against the %s edge of %s at rest (%spx gap, e.g. %s)"
                     % (len(flush), "" if len(flush) == 1 else "s", worst[1], sc["sel"], _n(worst[2]), worst[0])))
    return hits


def body_edge_hits(vp):
    """quality.rs body-text-viewport-edge: 16px gutter, 12px at <=480px."""
    hits = []
    vw = vp["vw"]
    floor = 12 if vw <= 480 else 16
    for t in vp.get("edgeText", []):
        if t.get("moving") or t.get("cut"):
            continue
        left, right = t["left"], t["right"]
        if not (right > 0 and left < vw):
            continue
        l, r = _r(left), _r(vw - right)
        lc, rc = l >= 0 and left < floor, r >= 0 and right > vw - floor
        if not (lc or rc):
            continue
        which = ("left %spx / right %spx" % (_n(l), _n(r)) if lc and rc else "left %spx" % _n(l) if lc else "right %spx" % _n(r))
        hits.append(("body-text-viewport-edge", "<%s> with %d-char body bleeds to viewport edge (%s)" % (t["tag"], t["len"], which)))
    return hits


def overflow_hits(vp):
    """element_checks.rs check_element_text_overflow_dom: >=16px and the spill does harm."""
    hits = []
    for o in vp.get("overflow", []):
        if o["delta"] >= 16 and o["harm"]:
            hits.append(("text-overflow", "%s overflows its %s by %spx" % (o["sel"], "box" if o["kind"] == "box" else "container", _n(_r(o["delta"])))))
    return hits


def occlusion_hits(vp):
    """page_checks.rs check_text_occlusion_dom: covered text, headline overhang, inline padding leak."""
    hits, seen = [], set()
    names = {"text": "overlapping text", "graphic": "an SVG graphic", "border": "a bordered element", "box": "an opaque element"}
    for o in vp.get("occlusion", []):
        if not o["total"]:
            continue
        frac = o["occluded"] / o["total"]
        text_like = o["kind"] in ("text", "graphic")
        if frac < (0.45 if text_like else 0.3):
            continue
        if text_like and (o.get("sameSvg") or not o.get("layered")):
            continue
        seen.add(o["sel"])
        hits.append(("text-occlusion", '%s "%s" is %s%% covered by %s (%s)' % (o["sel"], o["text"], _n(_r(frac * 100)), names[o["kind"]], o["occSel"])))
    for o in vp.get("overhang", []):
        if o["sel"] in seen:
            continue
        seen.add(o["sel"])
        hits.append(("text-occlusion", '%s "%s" overhangs %s by %spx — the headline and the card collide' % (o["sel"], o["text"], o["card"], _n(_r(o["ix"])))))
    for k in vp.get("leaks", []):
        if k["pad"] < 24 or k["w"] < 12 or k["h"] < 24 or k["h"] < 2.2 * k["lh"] or not k.get("onto") or k["sel"] in seen:
            continue
        over = k["h"] - k["lines"] * k["lh"]
        if over > 0:
            hits.append(("text-occlusion", "%s is an inline element whose opaque fill leaks %spx past its line onto %s" % (k["sel"], _n(_r(over)), k["onto"])))
    return hits


def column_hits(vp):
    """page_checks.rs check_first_viewport_column_overflow_dom: tall > 1.4vh while a sibling fits in 1vh."""
    hits, vh = [], vp["vh"]
    for row in vp.get("columns", []):
        cols = sorted(row["cols"], key=lambda c: -c["contentH"])
        tall = cols[0]
        rest = [c for c in cols[1:] if not (tall["left"] < c["right"] - 1 and c["left"] < tall["right"] - 1)
                and abs(tall["top"] - c["top"]) <= 0.25 * vh]
        if not rest:
            continue
        short = min(rest, key=lambda c: c["contentH"])
        if tall["contentH"] <= vh * 1.4 or short["contentH"] > vh:
            continue
        hits.append(("first-viewport-column-overflow", "%s opens the page with one column running %s%% of the viewport tall "
                     "while a sibling fits in %s%% — the fold falls deep inside the section"
                     % (row["sel"], _n(_r(tall["contentH"] / vh * 100)), _n(_r(short["contentH"] / vh * 100)))))
    return hits


def rhythm_hits(vp):
    """page_checks.rs check_heading_rhythm_dom: >=2 headings crowded against the block above."""
    cands = []
    for h in vp.get("heads", []):
        above, below = h["above"], h["below"]
        if h.get("small") or below < 6 or below > 160:
            continue
        crowded = above < below * 0.75 and below - above >= 12
        even = not crowded and above <= below + 0.5 and h.get("prose")
        if (crowded or even) and not h.get("separates"):
            cands.append(h)
    if len(cands) < 2:
        return []
    return [("heading-rhythm", '%s "%s" has %spx above vs %spx below — it reads as bound to the block above (%d headings on page)'
             % (h["tag"], h["text"], _n(_r(h["above"])), _n(_r(h["below"])), len(cands))) for h in cands]


def line_length_hits(vp, line_max=80):
    """quality.rs line-length: >= 2 rendered lines over line_max + 5 characters."""
    hits = []
    for t in vp.get("lines", []):
        ws = t["widths"]
        total = sum(ws)
        if total <= 0:
            continue
        chars = [t["len"] * w / total for w in ws]
        long = sum(1 for c in chars if c > line_max + 5)
        if long >= 2:
            hits.append(("line-length", "~%s chars on %d of %d rendered lines (aim for <%d)" % (_n(_r(max(chars))), long, len(ws), line_max)))
    return hits


def cramped_hits(vp):
    """quality.rs cramped-padding (rendered text-inset form)."""
    hits = []
    for c in vp.get("cramped", []):
        if min(c["insets"]) < -2:      # text not laid inside its own box: no inset to measure
            continue
        bv, bg = c["borders"], c["bg"]
        v_sides = [s for s in (0, 2) if bg or bv[s]]
        h_sides = [s for s in (3, 1) if (bg and not c.get("fullBleed")) or bv[s]]
        fs = c["fs"]
        vt, ht = max(4.0, fs * 0.3), max(8.0, fs * 0.5)
        vmin = min([c["pads"][s] for s in v_sides] or [float("inf")])
        hmin = min([c["pads"][s] for s in h_sides] or [float("inf")])
        vin = min([c["insets"][s] for s in v_sides] or [float("inf")])
        hin = min([c["insets"][s] for s in h_sides] or [float("inf")])
        fmt = lambda v: _n(_r(v * 10) / 10)
        if vmin < vt and vin < vt:
            hits.append(("cramped-padding", "%spx of space above and below the text (need ≥%.1fpx for %spx text)" % (fmt(vin), vt, _n(fs))))
        elif hmin < ht and hin < ht:
            hits.append(("cramped-padding", "%spx of space beside the text (need ≥%.1fpx for %spx text)" % (fmt(hin), ht, _n(fs))))
    return hits


def cursor_hits(vp):
    """element_checks.rs check_element_blinking_cursor_dom (spec D §4)."""
    hits = []
    for c in vp.get("cursors", []):
        w, h = c["w"], c["h"]
        if c["pageTop"] > 1200:
            continue
        if not c["glyph"]:
            if not (c["empty"] and c["filled"]):
                continue
            vertical = 1 <= w <= 24 and 6 <= h <= 48 and h >= w
            under = 1 <= h <= 6 and 4 <= w <= 24
            if not (vertical or under) or c["radius"] >= 0.4 * min(w, h):
                continue
        d = {"rule": "blinking-cursor", "snippet": '%s — %sx%spx blinking cursor (animation "%s") in the first viewport'
             % (c["sel"], _n(_r(w)), _n(_r(h)), c["name"])}
        if c["pageTop"] <= 900 or c.get("inHeader"):
            d["severity"] = "warning"
        hits.append(d)
    return hits


def rules(data):
    """Measures -> findings: (rule id, snippet) tuples or {rule, snippet, severity} dicts."""
    vps = data.get("viewports") or []
    if not vps:
        return []
    desk = vps[0]
    hits = script_error_hits(desk.get("errors", []))
    hits += hidden_hits(desk.get("hiddenText"))
    hits += overflow_hits(desk)
    seen = set()
    edge_vps = vps if not desk.get("edgeText") else vps[:1]   # phone pass only for pages laid out narrower than desktop
    for vp in edge_vps:
        for h in body_edge_hits(vp):
            if h[1] not in seen:
                seen.add(h[1])
                hits.append(h)
    hits += occlusion_hits(desk)
    hits += line_length_hits(desk)
    hits += rhythm_hits(desk)
    hits += column_hits(desk)
    hits += edge_flush_hits(desk)
    hits += cursor_hits(desk)
    hits += cramped_hits(desk)
    return hits
