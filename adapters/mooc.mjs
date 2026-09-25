import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CHAPTERS, courseScope, waitForCourse, chapterInfo, openChapter } from './mooc_course.mjs';
import { browserLaunchOptions } from './browser_channel.mjs';
const require = createRequire(new URL('../vendor/mooc-english/package.json', import.meta.url));

const root = dirname(dirname(fileURLToPath(import.meta.url)));

let context;
try {
  let input = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) input += chunk.toString('utf8');
  const params = JSON.parse(input);
  const { chromium } = require('playwright');
  const {deal_video,deal_pdf} = await import('./mooc_helpers.mjs');
  const url = new URL(params.url || 'https://mooc.ucas.edu.cn/portal');
  if (!['https:', 'http:'].includes(url.protocol) || !(url.hostname === 'mooc.ucas.edu.cn' || url.hostname.endsWith('.mooc.ucas.edu.cn'))) throw new Error('请输入国科大在线页面地址。');
  context = await chromium.launchPersistentContext(join(root, 'data', 'browser-mooc'), {
    ...browserLaunchOptions(), headless: false, viewport: null,
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto(url.href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('请在打开的浏览器中登录国科大在线，并进入目标课程的任意章节。最长等待 10 分钟。');
  let course = await waitForCourse(context);
  let selected = courseScope(course);
  if (params.diagnostic) {
    console.log(JSON.stringify({event:'mooc.diagnostic',chapters:await selected.locator(CHAPTERS).count(),embedded:course.frame!==course.page.mainFrame(),ready:true}));
    console.log('章节诊断成功；没有播放视频、提交文档进度或处理作业。');
  } else {
  console.log('已识别章节页面。测验、作业和考试不包含在此自动任务内。');
  const processed = new Set();
  while (true) {
    const cells = selected.locator(CHAPTERS);
    const count = await cells.count();
    let target = null;
    for (let index = 0; index < count; index++) {
      const cell = cells.nth(index);
      const info = await chapterInfo(cell,index);
      if (info.remaining > 0 && !info.manual && !processed.has(info.id)) { target=info; break; }
    }
    if (!target) break;
    processed.add(target.id);
    console.log('处理章节：' + target.title);
    await openChapter(target);
    try {
      await selected.frameLocator('#iframe').locator('iframe[src*="video"], iframe[src*="pdf"]').first().waitFor({ timeout: 20000 });
    } catch {
      console.log('本章节未发现可处理的视频或 PDF，保留未完成状态并继续检查其他章节。');
      continue;
    }
    await selected.waitForTimeout(1000);
    await deal_video(selected);
    await deal_pdf(selected);
    await course.frame.goto(course.frame.url(), {waitUntil:'domcontentloaded'});
    course = await waitForCourse(context,{timeout:30000});
    selected = courseScope(course);
  }
  const remaining = await selected.locator(CHAPTERS).evaluateAll(cells => cells
    .filter(cell => Number(cell.querySelector('input.jobUnfinishCount')?.value) > 0)
    .map(cell => cell.textContent.replace(/\s+/g, ' ').trim()));
  console.log('已完成本轮自动处理。学校页面仍显示的未完成章节：' + JSON.stringify(remaining));
  console.log('请在国科大在线核对任务点、测验和课程完成度；脚本结束不等于整门课程已通过。');
  if (remaining.length) process.exitCode = 2;
  }
} catch (error) {
  const message = /ERR_MODULE_NOT_FOUND|MODULE_NOT_FOUND/.test(error.code||'') ? '慕课组件不完整，请在设置与更新点击“检查并修复功能组件”。' : /ProcessSingleton|SingletonLock|profile.*in use/i.test(error.message) ? '慕课浏览器目录正被另一任务使用，请先关闭旧慕课任务或其浏览器，再重试。' : error.message;
  console.error('慕课任务停止：' + message);
  process.exitCode = 1;
} finally {
  if (context) await context.close().catch(() => {});
}
