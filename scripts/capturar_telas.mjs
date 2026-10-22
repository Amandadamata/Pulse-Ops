// Captura as telas usadas no README e em docs/imagens/ (opcional; não faz parte dos testes).
// Requer Node e o pacote "playwright" com Chromium, e a demonstração no ar (scripts/demo.sh).
// Uso: node scripts/capturar_telas.mjs <pasta-de-saida> '[["painel","/"],["monitor","/monitors/1"]]'
import { chromium } from 'playwright';
import fs from 'node:fs';

const [out, pagesJson] = process.argv.slice(2);
const base = process.env.PULSEOPS_URL ?? 'http://127.0.0.1:8000';
const password = fs.readFileSync('.demo/admin-password', 'utf8').trim();
const pages = JSON.parse(pagesJson);
const browser = await chromium.launch();

async function shoot(viewport, list, suffix) {
  const ctx = await browser.newContext({ viewport, locale: 'pt-BR' });
  const page = await ctx.newPage();
  await page.goto(`${base}/login`);
  await page.screenshot({ path: `${out}/login${suffix}.png` });
  await page.fill('input[name=username]', process.env.PULSEOPS_DEMO_USERNAME ?? 'demo');
  await page.fill('input[name=password]', password);
  await page.click('button[type=submit]');
  await page.waitForURL(`${base}/`);
  for (const [name, path] of list) {
    await page.goto(base + path);
    await page.screenshot({ path: `${out}/${name}${suffix}.png`, fullPage: true });
  }
  await ctx.close();
}

await shoot({ width: 1280, height: 800 }, pages, '');
await shoot({ width: 390, height: 844 }, pages.slice(0, 2), '-celular');
await browser.close();
