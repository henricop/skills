// rec.mjs — gravador de demo de página web (scroll-story, WebGL ok) · v1
// Uso: node rec.mjs <slug> <url> '<ações JSON>'
// Ações: ["wait",ms] ["mark","nome"] ["wheel",distPx,ms] ["click",x,y] ["move",x,y,(steps)]
//        ["clickframe","substring-da-url-do-frame","texto-do-link"] ["clicksel","seletor"]
//        ["keys",["teclas"],ms] ["type","texto"] ["press","tecla"] ["eval","js"] ["shot","nome"]
// Ex.: node rec.mjs home file://$PWD/template.html '[["wait",4000],["wheel",1300,3000],["wait",1100]]'
// Depende: playwright (npm i playwright && npx playwright install chromium) ou
//          PLAYWRIGHT_IMPORT=/caminho/playwright/index.mjs apontando para uma instalação existente.
// Vídeo: webm em $PVID/raw/<slug>.webm · log em $PVID/<slug>.log (PVID padrão: ./vid)

import fs from 'node:fs';
const PW = await import(process.env.PLAYWRIGHT_IMPORT || 'playwright');
const [,, slug, url, actsJson = '[["wait",8000]]'] = process.argv;
const acts = JSON.parse(actsJson);
const OUT = process.env.PVID || './vid';
const W = 1280, H = 800;
const log = [];
const say = (...a) => { const l = a.join(' '); process.stdout.write(l + '\n'); log.push(l); };

fs.mkdirSync(OUT + '/raw', { recursive: true });

setTimeout(() => { say('TIMEOUT'); process.exit(2); }, 150000);
const browser = await PW.chromium.launch({ channel: 'chromium', headless: true,
  args: ['--ignore-gpu-blocklist', '--enable-gpu', '--use-angle=metal', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'] });
const ctx = await browser.newContext({ viewport: { width: W, height: H },
  colorScheme: process.env.REC_LIGHT ? 'light' : 'dark',
  recordVideo: { dir: OUT + '/raw', size: { width: W, height: H } } });
const page = await ctx.newPage();
const t0 = Date.now(); const T = () => ((Date.now() - t0) / 1000).toFixed(2);
await page.goto(url, { waitUntil: 'load', timeout: 60000 }).catch(e => say('goto:', e.message.split('\n')[0]));
await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
say('ready_at', T());
say('gl', await page.evaluate(() => { const c = document.createElement('canvas'); const g = c.getContext('webgl2') || c.getContext('webgl'); if (!g) return 'SEM WEBGL'; const d = g.getExtension('WEBGL_debug_renderer_info'); return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : 'webgl'; }).catch(() => 'eval err'));

for (const [k, ...p] of acts) {
  if (k === 'wait') await page.waitForTimeout(p[0]);
  else if (k === 'mark') say('mark', p[0], T());
  else if (k === 'shot') await page.screenshot({ path: `${OUT}/${slug}-${p[0]}.png` });
  else if (k === 'wheel') { const [dist, ms] = p; const n = Math.max(1, Math.round(ms / 50)); for (let i = 0; i < n; i++) { await page.mouse.wheel(0, dist / n); await page.waitForTimeout(50); } }
  else if (k === 'keys') { for (const kk of p[0]) await page.keyboard.down(kk); await page.waitForTimeout(p[1]); for (const kk of p[0]) await page.keyboard.up(kk); }
  else if (k === 'click') await page.mouse.click(p[0], p[1]);
  else if (k === 'move') await page.mouse.move(p[0], p[1], { steps: p[2] || 25 });
  else if (k === 'clicksel') await page.click(p[0], { timeout: 5000 }).catch(() => say('clicksel falhou', p[0]));
  else if (k === 'type') await page.keyboard.type(p[0], { delay: 90 });
  else if (k === 'press') await page.keyboard.press(p[0]);
  else if (k === 'eval') await page.evaluate(p[0]).catch(() => say('eval falhou'));
  else if (k === 'clickframe') {
    const [urlSub, txt] = p;
    const fr = page.frames().find(f => f.url().includes(urlSub));
    if (!fr) { say('clickframe: frame nao achado', urlSub, T()); continue; }
    const loc = fr.locator('a', { hasText: txt }).first();
    if (!await loc.count().catch(() => 0)) { say('clickframe: elemento nao achado', txt, T()); continue; }
    const box = await loc.boundingBox();
    say('clickframe', txt, 'box=' + JSON.stringify(box && { x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.width), h: Math.round(box.height) }), T());
    await loc.hover().catch(e => say('hover falhou', e.message.slice(0, 60)));
    await page.waitForTimeout(500);
    await loc.click({ timeout: 8000 }).catch(e => say('click falhou', e.message.slice(0, 60)));
    say('clickframe ok', txt, T());
  }
}
say('end_at', T());
const v = page.video(); await ctx.close(); const vp = await v.path(); await browser.close();
fs.renameSync(vp, `${OUT}/raw/${slug}.webm`);
say('video', `${OUT}/raw/${slug}.webm`);
fs.writeFileSync(`${OUT}/${slug}.log`, log.join('\n') + '\n');
process.exit(0);
