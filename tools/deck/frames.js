// Renders deck.html into slide frames, moving parts and the crowd clip.
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require(path.join(__dirname, '..', '..', 'site', 'node_modules', 'playwright-core'));

const OUT = path.join(__dirname, 'build');
const PAGE = pathToFileURL(path.join(__dirname, 'deck.html')).href;
const STILL = '*,*::before,*::after{transition:none!important;animation:none!important} .hint{display:none!important}';
// Per slide, the elements that move and the regions they fill.
const SPEC = {
  'Results Summary': [{ hide: '.histchart polyline.ln', region: ['.histchart svg'] }],
  'Stocks and Bonds': [
    { hide: '.shockbars .bar', region: ['.shockbars'], union: true, kind: 'fade' },
    { hide: '.corrchart svg .ln', region: ['.corrchart svg'] },
  ],
  'Limits': [{ hide: '.lim svg .ln', region: ['.lim svg'] }],
  'Costs': [{ hide: '.wf .wb', region: ['.wf .wb'], union: true }],
  'Crises and the AI Crowd': [{ hide: '.crow .bar', region: ['.crow .bars'], union: true, kind: 'fade' }],
  'Arcana Verification': [{ hide: '.srows .hbar', region: ['.srows .hbar'], union: true }],
};
const CLIP = { slide: 'Crises and the AI Crowd', sel: '.cc svg' };
// On-screen copy may not hold dashes, colons, semicolons or Oxford commas.
const RULE = /[—–;:]|, and |, or /;

// Shows slide k alone.
async function show(p, k) {
  await p.evaluate((k) => document.querySelectorAll('.slide').forEach((s, j) => s.classList.toggle('on', j === k)), k);
}

// The boxes of one moving part, one per element or one around them all.
async function regions(p, k, sp) {
  return p.evaluate(({ k, sp }) => {
    const sec = document.querySelectorAll('.slide')[k];
    const rs = sp.region.flatMap((q) => [...sec.querySelectorAll(q)].map((e) => e.getBoundingClientRect()));
    const one = (r) => ({ x: r.left, y: r.top, w: r.width, h: r.height });
    if (!sp.union) return rs.map((r) => ({ ...one(r), kind: sp.kind || 'wipe' }));
    const x = Math.min(...rs.map((r) => r.left));
    const y = Math.min(...rs.map((r) => r.top));
    const w = Math.max(...rs.map((r) => r.right)) - x;
    const h = Math.max(...rs.map((r) => r.bottom)) - y;
    return [{ x, y, w, h, kind: sp.kind || 'wipe' }];
  }, { k, sp });
}

// Every slide's final and base frame, then the clip frame by frame.
(async () => {
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(path.join(OUT, 'frames'), { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  const errs = [];
  p.on('pageerror', (e) => errs.push(String(e)));
  p.on('requestfailed', (r) => errs.push('failed ' + r.url().slice(0, 80)));
  await p.goto(PAGE);
  await p.addStyleTag({ content: STILL });
  await p.evaluate(() => document.fonts.ready);
  const labels = await p.evaluate(() => [...document.querySelectorAll('.slide')].map((s) => s.getAttribute('aria-label')));
  const meta = [];
  const bad = [];
  for (let k = 0; k < labels.length; k++) {
    await show(p, k);
    await p.waitForTimeout(250);
    const n = String(k + 1).padStart(2, '0');
    await p.screenshot({ path: path.join(OUT, `final_${n}.png`) });
    const text = await p.evaluate((k) => {
      const s = document.querySelectorAll('.slide')[k];
      return [s.innerText, ...[...s.querySelectorAll('svg text')].map((x) => x.textContent)].join('\n');
    }, k);
    for (const line of text.split('\n')) if (RULE.test(line)) bad.push(`slide ${k + 1}: ${line.trim()}`);
    const m = { k, label: labels[k], final: `final_${n}.png`, regions: [] };
    const spec = SPEC[labels[k]] || [];
    const clip = CLIP.slide === labels[k];
    if (spec.length || clip) {
      for (const sp of spec) m.regions.push(...(await regions(p, k, sp)));
      const hide = spec.map((s) => s.hide).concat(clip ? [CLIP.sel] : []).join(',');
      const tag = await p.addStyleTag({ content: `${hide}{visibility:hidden!important}` });
      await p.screenshot({ path: path.join(OUT, `base_${n}.png`) });
      await tag.evaluate((t) => t.remove());
      m.base = `base_${n}.png`;
      if (clip) {
        m.clip = await p.evaluate(({ k, sel }) => {
          const r = document.querySelectorAll('.slide')[k].querySelector(sel).getBoundingClientRect();
          return { x: r.left, y: r.top, w: r.width, h: r.height };
        }, { k, sel: CLIP.sel });
      }
    }
    meta.push(m);
  }
  const broken = await p.evaluate(() => [...document.images].filter((i) => !i.naturalWidth).length);
  // The crowd clip on a paused clock, 30 frames a second.
  const q = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  await q.goto(PAGE);
  await q.addStyleTag({ content: '.slide,.slide.on{transition:none!important} .hint{display:none!important}' });
  await q.evaluate(() => document.fonts.ready);
  const k = labels.indexOf(CLIP.slide);
  const end = await q.evaluate(({ k, sel }) => {
    document.querySelectorAll('.slide').forEach((s, j) => s.classList.toggle('on', j === k));
    const el = document.querySelectorAll('.slide')[k].querySelector(sel);
    window.__a = document.getAnimations().filter((a) => a.effect && a.effect.target && el.contains(a.effect.target));
    window.__a.forEach((a) => a.pause());
    return Math.max(...window.__a.map((a) => a.effect.getComputedTiming().endTime));
  }, { k, sel: CLIP.sel });
  const box = meta[k].clip;
  let f = 0;
  for (let t = 0; t <= end + 600; t += 1000 / 30) {
    // Seek, then wait two painted frames so the compositor has caught up.
    await q.evaluate((t) => new Promise((done) => {
      window.__a.forEach((a) => { a.currentTime = t; });
      requestAnimationFrame(() => requestAnimationFrame(done));
    }), Math.min(t, end));
    const file = path.join(OUT, 'frames', `f_${String(f++).padStart(4, '0')}.png`);
    await q.screenshot({ path: file, clip: { x: box.x, y: box.y, width: box.w, height: box.h } });
  }
  fs.writeFileSync(path.join(OUT, 'meta.json'), JSON.stringify({ meta, clipEnd: end, frames: f }, null, 1));
  await b.close();
  console.log('slides', labels.length, 'animated', meta.filter((m) => m.base).length, 'clip frames', f);
  // A broken image, a page error or a rule hit stops the build.
  if (broken || errs.length || bad.length) {
    console.error(`broken images ${broken}, page errors ${errs.length}`, errs.slice(0, 3));
    if (bad.length) console.error('copy rule hits\n' + bad.join('\n'));
    process.exit(1);
  }
})();
