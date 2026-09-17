import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deal_video, deal_pdf } from './mooc_helpers.mjs';
import { browserChannel } from './browser_channel.mjs';
const require = createRequire(new URL('../vendor/mooc-english/package.json', import.meta.url));
const { chromium } = require('playwright');
const root = dirname(dirname(fileURLToPath(import.meta.url)));

let context;
try {
  let input = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) input += chunk.toString('utf8');
  const params = JSON.parse(input);
  const url = new URL(params.url || 'https://mooc.ucas.edu.cn/portal');
  if (!['https:', 'http:'].includes(url.protocol) || !(url.hostname === 'mooc.ucas.edu.cn' || url.hostname.endsWith('.mooc.ucas.edu.cn'))) throw new Error('请输入国科大在线页面地址。');
  context = await chromium.launchPersistentContext(join(root, 'data', 'browser-mooc'), {
    channel: browserChannel(), headless: false, viewport: null,
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto(url.href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('请在打开的浏览器中登录国科大在线，并进入目标课程的任意章节。最长等待 10 分钟。');
  let selected = null;
  const deadline = Date.now() + 600000;
  while (Date.now() < deadline && !selected) {
    for (const tab of context.pages()) {
      if (await tab.locator('#coursetree .ncells:has(input.jobUnfinishCount)').count().catch(() => 0)) { selected = tab; break; }
    }
    if (!selected) await new Promise(resolve => setTimeout(resolve, 1500));
  }
  if (!selected) throw new Error('未检测到已适配的课程章节。页面结构可能变化，或还没有完成登录。');
  console.log('已识别章节页面。测验、作业和考试不包含在此自动任务内。');
  const processed = new Set();
  while (true) {
    const cells = selected.locator('#coursetree .ncells:has(input.jobUnfinishCount)');
    const count = await cells.count();
    let target = null;
    for (let index = 0; index < count; index++) {
      const cell = cells.nth(index);
      const title = (await cell.textContent()).replace(/\s+/g, ' ').trim();
      const id = await cell.locator('h4').getAttribute('id');
      const remaining = Number(await cell.locator('input.jobUnfinishCount').inputValue());
      if (remaining > 0 && !/quiz|exam|测验|考试/i.test(title) && !processed.has(id)) { target = { cell, id, title }; break; }
    }
    if (!target) break;
    processed.add(target.id);
    console.log('处理章节：' + target.title);
    if (!(await target.cell.locator('h4.currents').count())) await target.cell.locator('h4 span[onclick]').click();
    await selected.frameLocator('#iframe').locator('iframe[src*="video"], iframe[src*="pdf"]').first().waitFor({ timeout: 20000 });
    await selected.waitForTimeout(1000);
    await deal_video(selected);
    await deal_pdf(selected);
    await selected.reload({ waitUntil: 'domcontentloaded' });
    await selected.locator('#coursetree .ncells').first().waitFor();
  }
  const remaining = await selected.locator('#coursetree .ncells:has(input.jobUnfinishCount)').evaluateAll(cells => cells
    .filter(cell => Number(cell.querySelector('input.jobUnfinishCount')?.value) > 0)
    .map(cell => cell.textContent.replace(/\s+/g, ' ').trim()));
  console.log('已完成本轮自动处理。学校页面仍显示的未完成章节：' + JSON.stringify(remaining));
  console.log('请在国科大在线核对任务点、测验和课程完成度；脚本结束不等于整门课程已通过。');
  if (remaining.length) process.exitCode = 2;
} catch (error) {
  console.error('慕课任务停止：' + error.message);
  process.exitCode = 1;
} finally {
  if (context) await context.close().catch(() => {});
}
