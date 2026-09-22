// Offline fixture only: no school traffic or real registration.
import assert from 'node:assert/strict';
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { extractLectureSnapshot } from '../vendor/ucas-humanity-lecture-bot/dist/src/lecture-page.js';
import { registerLecture } from '../vendor/ucas-humanity-lecture-bot/dist/src/register.js';
import { readScienceSchedule } from '../adapters/lecture_pagination.mjs';
import { browserLaunchOptions } from '../adapters/browser_channel.mjs';
const browser = await chromium.launch({...browserLaunchOptions(), headless:true});
try {
 const page=await browser.newPage();
 await page.route('**/*',route=>route.fulfill({body:'<html></html>',contentType:'text/html'}));
 await page.goto('https://xkcts.ucas.ac.cn:8443/subject/lecture');
 const html=department=>`<table><tr><th>讲座名称</th><th>部门</th><th>讲座地点</th><th>讲座时间</th><th>操作</th></tr><tr><td>人工智能测试讲座</td><td>${department}</td><td>雁栖湖</td><td>2026-10-01 19:00-20:30</td><td><button onclick="window.clicked=true">报名</button></td></tr></table>`;
 await page.setContent(html('计算机学院'));
 for (const [text,expected] of [['已经预约过','registered'],['已经报名过','registered'],['此讲座无需报名','not-required'],['报名','unknown-or-unregistered'],['未预约','unknown-or-unregistered']]) {
  await page.setContent(html('化学科学学院').replace('>报名</button>',`>${text}</button>`));
  assert.equal((await readScienceSchedule(page))[0].registrationStatus,expected);
 }
 await page.setContent(html('计算机学院'));
 const candidate=(await extractLectureSnapshot(page)).lectures[0];
 assert.ok(candidate);
 assert.equal((await readScienceSchedule(page))[0].department,'计算机学院');
 await page.setContent(html(' 本科部 '));
 assert.equal((await readScienceSchedule(page))[0].department,'本科部');
 assert.equal((await extractLectureSnapshot(page)).lectures.length,0);
 const result=await registerLecture(page,candidate,{info(){}});
 assert.equal(result.outcome,'unknown');
 assert.equal(await page.evaluate(()=>Boolean(window.clicked)),false);
 console.log('Department extraction, candidate exclusion and pre-submit recheck: PASS');
} finally {await browser.close();}
