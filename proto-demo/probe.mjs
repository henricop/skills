// probe.mjs — validação programática de página scroll-story (sem depender de visão) · v1
// Uso: node probe.mjs <url> '<posições JSON: [["tag",scrollY],...]>'
// Ex.: node probe.mjs file://$PWD/template.html '[["hero",0],["ch1",1280],["ch2",3040],["ch3",4800],["fin",7360]]'
// O que faz: abre a página com GPU, rola até cada posição, coleta erros de console,
// opacidade dos blocos de texto, screenshot por posição (em /tmp/probe-<tag>.png).
// Analise os PNGs com estatística de pixels (ver SKILL.md, passo 3) ou olhe-os você mesmo.

const PW = await import(process.env.PLAYWRIGHT_IMPORT || 'playwright');
const [,, url, posJson = '[["hero",0]]'] = process.argv;
const pos = JSON.parse(posJson);
const b = await PW.chromium.launch({ channel: 'chromium', headless: true,
  args: ['--ignore-gpu-blocklist', '--enable-gpu', '--use-angle=metal', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'] });
const p = await (await b.newContext({ viewport: { width: 1280, height: 800 }, colorScheme: process.env.REC_LIGHT ? 'light' : 'dark' })).newPage();
const errs = [];
p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)); });
p.on('pageerror', e => errs.push('PAGEERR ' + e.message.slice(0, 120)));
await p.goto(url, { waitUntil: 'load', timeout: 30000 });
await p.waitForTimeout(3500);
console.log('erros:', errs.length ? errs : 'nenhum');
const info = await p.evaluate(() => JSON.stringify({
  scrollH: document.body.scrollHeight, vh: innerHeight,
  maxScroll: document.body.scrollHeight - innerHeight
}));
console.log('página:', info);
for (const [tag, y] of pos) {
  await p.evaluate(v => scrollTo(0, v), y);
  await p.waitForTimeout(1300);
  const st = await p.evaluate(() => {
    const blks = [...document.querySelectorAll('.ch .blk, section .blk')];
    const vis = blks.map(b => Math.round(parseFloat(getComputedStyle(b).opacity) * 100));
    const ov = document.getElementById('dentro');
    return JSON.stringify({ txtOp: vis, dentro: ov ? Math.round(parseFloat(getComputedStyle(ov).opacity) * 100) : null });
  });
  console.log(tag, 'y=' + y, st);
  await p.screenshot({ path: `/tmp/probe-${tag}.png` });
}
await b.close(); process.exit(0);
