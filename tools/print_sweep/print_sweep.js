// Print sweep — step 2 of 3 (see render_variants.py for the whole run).
//
//     node tools/print_sweep/print_sweep.js <html_dir> <out_dir>
//
// Needs Node and Playwright with a Chromium (require('playwright')). Prints
// every HTML to <out_dir>/pdf/ under print media on the paper the sheet's own
// @page asks for (preferCSSPageSize — A4 portrait, or landscape for the BOQ
// and the joint sheet), with margins 0 and no browser header/footer, exactly
// as the app's print CSS intends. Before printing it checks the laid-out page,
// still under print emulation, and writes <out_dir>/dom.json:
//
//   covered            a text glyph box with another element painted on top
//                      of it (elementFromPoint) — the title band under the
//                      banner was this. The DRAFT/CANCELLED watermark and the
//                      wet stamp overlap on purpose and are skipped.
//   overflow-clipped   overflow hidden/clip whose content is bigger than it
//   cell-spill         a table cell's text running past the cell's own edge
//   page-wider / past-right-edge   content wider than the page
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [src, out] = process.argv.slice(2);
fs.mkdirSync(path.join(out, 'pdf'), { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const result = {};
  for (const f of fs.readdirSync(src).filter(f => f.endsWith('.html')).sort()) {
    const html = fs.readFileSync(path.join(src, f), 'utf8');
    const land = /@page\s*\{\s*size:\s*A4 landscape/.test(html);
    const ctx = await browser.newContext({ viewport: { width: land ? 1123 : 794, height: 1100 } });
    const page = await ctx.newPage();
    await page.goto('file://' + path.join(src, f));
    await page.emulateMedia({ media: 'print' });
    await page.waitForTimeout(50);
    const dom = await page.evaluate(() => {
      const issues = [];
      const vis = el => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden'; };
      const desc = el => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '');
      // 1. Text whose glyph box is painted over by an element that is not its own.
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = walker.nextNode())) {
        const t = n.textContent.trim();
        if (!t || !n.parentElement || !vis(n.parentElement)) continue;
        // The DRAFT / CANCELLED watermark is pointer-events:none, so every probe
        // of its own text 'hits' whatever lies under it. It is drawn over on purpose.
        if (n.parentElement.closest('.lc-mark')) continue;
        const r = document.createRange(); r.selectNodeContents(n);
        const sy0 = window.scrollY;
        const rects = Array.from(r.getClientRects()).map(q => ({left: q.left, top: q.top + sy0, width: q.width, height: q.height}));
        for (const rect of rects) {
          if (rect.width < 2 || rect.height < 2) continue;
          // Sample 3 points across the lower and middle of the glyph box.
          for (const fy of [0.35, 0.75]) for (const fx of [0.2, 0.5, 0.8]) {
            const x = rect.left + rect.width * fx, y = rect.top + rect.height * fy;
            if (x < 0 || y < 0 || x > innerWidth) continue;
            window.scrollTo(0, Math.max(0, y - 300));
            const yy = y - window.scrollY;
            const hit = document.elementFromPoint(x, yy);
            if (!hit) continue;
            if (hit === n.parentElement || n.parentElement.contains(hit) || hit.contains(n.parentElement)) continue;
            // Something else is on top at that point.
            const cls = desc(hit);
            if (/lc-mark|sig-stamp/.test(cls)) continue; // watermark / wet stamp: by design
            issues.push({ kind: 'covered', text: t.slice(0, 60), by: cls,
                          at: [Math.round(x), Math.round(y)], parent: desc(n.parentElement) });
            
          }
        }
      }
      window.scrollTo(0, 0);
      // 2. Clipped overflow.
      for (const el of document.querySelectorAll('body *')) {
        if (!vis(el)) continue;
        const s = getComputedStyle(el);
        const clipX = /hidden|clip/.test(s.overflowX), clipY = /hidden|clip/.test(s.overflowY);
        if ((clipX && el.scrollWidth > el.clientWidth + 1) || (clipY && el.scrollHeight > el.clientHeight + 1))
          if (el.textContent.trim()) issues.push({ kind: 'overflow-clipped', el: desc(el),
            sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight,
            text: el.textContent.trim().slice(0, 60) });
      }
      // 2b. Text spilling out of its own table cell.
      for (const cell of document.querySelectorAll('td, th')) {
        if (!vis(cell) || !cell.textContent.trim()) continue;
        const cr = cell.getBoundingClientRect();
        const rg = document.createRange(); rg.selectNodeContents(cell);
        for (const q of rg.getClientRects()) {
          if (q.width < 1) continue;
          if (q.right > cr.right + 0.5 || q.left < cr.left - 0.5) {
            issues.push({ kind: 'cell-spill', el: desc(cell), text: cell.textContent.trim().slice(0, 40),
                          over: Math.round(Math.max(q.right - cr.right, cr.left - q.left) * 10) / 10 });
            break;
          }
        }
      }
      // 3. Wider than the page.
      const W = document.documentElement.clientWidth;
      if (document.documentElement.scrollWidth > W + 1)
        issues.push({ kind: 'page-wider', sw: document.documentElement.scrollWidth, w: W });
      for (const el of document.querySelectorAll('.doc-outer *')) {
        const r = el.getBoundingClientRect();
        if (vis(el) && r.width && r.right > W + 1 && el.textContent.trim())
          { issues.push({ kind: 'past-right-edge', el: desc(el), right: Math.round(r.right), w: W }); break; }
      }
      return issues;
    });
    // de-duplicate
    const seen = new Set();
    result[f] = dom.filter(i => { const k = JSON.stringify([i.kind, i.text, i.by, i.el]); if (seen.has(k)) return false; seen.add(k); return true; });
    await page.pdf({ path: path.join(out, 'pdf', f.replace('.html', '.pdf')), preferCSSPageSize: true, printBackground: true });
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(out, 'dom.json'), JSON.stringify(result, null, 1));
  for (const [f, is] of Object.entries(result)) if (is.length) console.log(f, JSON.stringify(is));
})();
