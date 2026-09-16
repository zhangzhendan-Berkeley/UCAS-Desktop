// Offline DOM regression: every browser request is intercepted; no school account.
import assert from 'node:assert/strict';
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { establishLectureSession, isLecturePage } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { readScienceSchedule } from '../vendor/ucas-humanity-lecture-bot/dist/src/portal.js';
import { extractLectureSnapshot } from '../vendor/ucas-humanity-lecture-bot/dist/src/lecture-page.js';

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const messages = [];
const logger = { info: (event, data) => messages.push({ event, data }) };
const ticket = 'a'.repeat(64);
const table = '<table><tr><th>讲座专题</th><th>讲座名称</th><th>讲座地点</th><th>讲座时间</th></tr>' +
  '<tr><td>同名系列专题</td><td>测试科研讲座</td><td>教室</td><td>2026-10-16 19:00-20:30</td></tr></table>';
try {
  for (const kind of ['humanity', 'science', 'legacy']) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const requests = [];
    await context.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      requests.push(path);
      let body = '';
      if (path === '/sepCard/card') {
        body = kind === 'legacy'
          ? '<a href="/portal/legacy">人文讲座报名</a>'
          : `<div>PRIVATE-PROFILE-FIXTURE</div><div id="cards"></div><script>setTimeout(()=>document.querySelector('#cards').innerHTML='<a href="/portal/course">选课系统</a>',150)</script>`;
      } else if (path === '/portal/course' || path === '/portal/legacy') {
        assert.equal(new URL(request.headers().referer).pathname, '/sepCard/card');
        const next = path.endsWith('legacy')
          ? 'https://xkcts.ucas.ac.cn:8443/subject/humanityLecture'
          : 'https://xkgo.ucas.ac.cn:3000/courseManage/main';
        await route.fulfill({ contentType: 'text/html', body: `<script>location.replace(${JSON.stringify(next)})</script>` });
        return;
      } else if (path === '/courseManage/main') {
        // Hidden Bootstrap submenus must still be discoverable by DOM inspection.
        body = `<ul><li><a href="#">科学前沿讲座</a><ul style="display:none"><li><a href="http://sep.ucas.ac.cn/portal/science/${ticket}">讲座预告</a></li></ul></li>` +
          `<li><a href="#">人文讲座</a><ul style="display:none"><li><a href="http://sep.ucas.ac.cn/portal/humanity/${ticket}">讲座预告</a></li></ul></li></ul>`;
      } else if (/^\/portal\/(science|humanity)\//.test(path)) {
        assert.equal(url.protocol, 'https:');
        assert.equal(new URL(request.headers().referer).hostname, 'xkgo.ucas.ac.cn');
        const target = path.includes('/science/') ? 'lecture' : 'humanityLecture';
        await route.fulfill({ contentType: 'text/html', body: `<script>location.replace('https://xkcts.ucas.ac.cn:8443/subject/${target}')</script>` });
        return;
      } else if (path.startsWith('/subject/')) {
        body = table;
      } else {
        throw new Error('Unexpected request: ' + url.origin + path);
      }
      await route.fulfill({ contentType: 'text/html; charset=utf-8', body });
    });
    await page.goto('https://sep.ucas.ac.cn/sepCard/card');
    const target = kind === 'science' ? 'lecture' : 'humanityLecture';
    const config = { loginUrl: 'https://sep.ucas.ac.cn/sepCard/card',
      humanityLectureUrl: `https://xkcts.ucas.ac.cn:8443/subject/${target}` };
    await establishLectureSession(page, config, logger);
    assert.equal(await isLecturePage(page, config.humanityLectureUrl), true);
    const snapshot = await extractLectureSnapshot(page);
    assert.equal(snapshot.lectures.length, 1, 'Header is not a lecture');
    assert.equal(snapshot.lectures[0].title, '测试科研讲座', 'Use the title column, not the series column');
    assert.equal(requests.filter(p => p === '/subject/' + target).length, 1, 'No redundant target navigation');
    if (kind === 'science') {
      assert(requests.some(p => p.startsWith('/portal/science/')));
      assert(!requests.some(p => p.startsWith('/portal/humanity/')));
      const rows = await readScienceSchedule(page);
      assert.equal(rows[0].start, '2026-10-16 19:00:00');
      assert.equal(rows[0].end, '2026-10-16 20:30:00');
      assert(!('id' in rows[0]), 'A lecture system ID must not become an iClass ID');
    }
    await page.setContent('<title>讲座预告</title><p>请重新登录</p>');
    assert.equal(await isLecturePage(page, config.humanityLectureUrl), false);
    await context.close();
  }
  assert(!JSON.stringify(messages).includes(ticket));
  assert(!JSON.stringify(messages).includes('PRIVATE-PROFILE-FIXTURE'));
  console.log('PASS: new/legacy portal, hidden menus, science/humanity separation, Referer, timetable and privacy');
} finally { await browser.close(); }
