// Converte o HTML do material de estudo em PDF A4 com o Chromium (Playwright).
// Uso: node study/imprimir.mjs entrada.html saida.pdf
import { chromium } from 'playwright';
import path from 'node:path';

const [input, output] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto('file://' + path.resolve(input), { waitUntil: 'load' });
await page.pdf({
  path: output,
  format: 'A4',
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: '<span></span>',
  footerTemplate:
    '<div style="font-size:8px;width:100%;text-align:center;color:#666;font-family:Inter,sans-serif">' +
    '<span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  margin: { top: '16mm', bottom: '16mm', left: '15mm', right: '15mm' },
});
await browser.close();
