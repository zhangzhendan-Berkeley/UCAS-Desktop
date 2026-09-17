// Offline browser test: registration clicks are confined to locally injected HTML.
import assert from 'node:assert/strict';
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { extractLectureSnapshot } from '../vendor/ucas-humanity-lecture-bot/dist/src/lecture-page.js';
import { registerLecture } from '../vendor/ucas-humanity-lecture-bot/dist/src/register.js';
import { isYanqiLocation } from '../vendor/ucas-humanity-lecture-bot/dist/src/campus.js';
import { browserChannel } from '../adapters/browser_channel.mjs';

const browser = await chromium.launch({ channel: browserChannel(), headless: true });
try {
  const context = await browser.newContext();
  await context.route('**/*', route => route.abort());
  const page = await context.newPage();
  for (const location of ['中关村教学楼', '玉泉路礼堂', '教一楼101', '雁栖湖教一楼101']) {
    await page.setContent(`<table><tr><th>讲座名称</th><th>讲座地点</th><th>讲座时间</th><th>操作</th></tr>
      <tr data-id="fixture"><td>雁栖湖主办的测试讲座</td><td>${location}</td><td>2026-10-01 19:00-20:30</td>
      <td><button onclick="window.clicked=true;this.textContent='已预约'">报名</button></td></tr></table>`);
    await page.evaluate(() => { window.clicked = false; });
    const snapshot = await extractLectureSnapshot(page);
    assert.equal(snapshot.lectures.length, 1);
    assert.equal(snapshot.lectures[0].location, location, 'Venue comes from location column, never title');
    const result = await registerLecture(page, snapshot.lectures[0], { info() {} });
    assert.equal(await page.evaluate(() => Boolean(window.clicked)), isYanqiLocation(location));
    assert.equal(result.outcome, isYanqiLocation(location) ? 'registered' : 'unknown');
  }
  // A venue changed between discovery and submission must not be clicked.
  const candidate = (await extractLectureSnapshot(page)).lectures[0];
  await page.locator('td').nth(1).evaluate(el => { el.textContent = '中关村教学楼'; });
  await page.evaluate(() => { window.clicked = false; });
  await registerLecture(page, candidate, { info() {} });
  assert.equal(await page.evaluate(() => Boolean(window.clicked)), false);
  console.log('Campus extraction, rejected venues, allowed venue and changed venue: PASS');
} finally {
  await browser.close();
}
