import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
const require = createRequire(new URL('../vendor/ucas-humanity-lecture-bot/package.json', import.meta.url));
const { chromium } = require('playwright');
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const report = [];
try {
  const page = await browser.newPage();
  await page.setContent('<title>Offline health check</title><button>ready</button>');
  report.push({ test: 'Playwright Edge DOM', passed: (await page.getByRole('button').innerText()) === 'ready' });
  for (const url of ['https://sep.ucas.ac.cn/', 'https://mooc.ucas.edu.cn/portal', 'https://xkcts.ucas.ac.cn:8443/subject/humanityLecture', 'https://xkgo.ucas.ac.cn:3000/courseManage/main']) {
    try {
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
      report.push({ url, status: response?.status(), title: await page.title(), redirectHost: new URL(page.url()).hostname });
    } catch (error) { report.push({ url, error: error.message.split('\n')[0] }); }
  }
} finally { await browser.close(); }
writeFileSync(new URL('../docs/browser-health.json', import.meta.url), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
