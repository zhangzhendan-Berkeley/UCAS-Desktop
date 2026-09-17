import { browserLaunchOptions } from './browser_channel.mjs';
// One browser session, four independent reads, no registration/sign-in entry points.
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { readScienceSchedule } from '../vendor/ucas-humanity-lecture-bot/dist/src/portal.js';
import { parseAttendance } from './lecture_records.mjs';

export const dashboardParts = ['humanity', 'science', 'humanity-attendance', 'science-attendance'];

export async function queryDashboard(config, logger) {
  const browser = await chromium.launch({ ...browserLaunchOptions(), headless: config.headless });
  let failed = false;
  try {
    const state = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: state && existsSync(state) ? state : undefined });
    const page = await context.newPage();
    page.setDefaultNavigationTimeout(30000);
    for (const part of dashboardParts) {
      try {
        const science = part.startsWith('science');
        const url = 'https://xkcts.ucas.ac.cn:8443/subject/' + (science ? 'lecture' : 'humanityLecture');
        await ensureAuthenticated(page, { ...config, humanityLectureUrl: url }, logger);
        let value;
        if (part.endsWith('attendance')) {
          const path = science ? 'student' : 'humanityStudent';
          await page.goto('https://xkcts.ucas.ac.cn:8443/subject/' + path, {waitUntil:'domcontentloaded', referer:page.url()});
          await page.locator('table th').first().waitFor({timeout:10000});
          if (new URL(page.url()).pathname !== '/subject/' + path) throw new Error('讲座记录会话失效，请重新登录。');
          value = {...parseAttendance(await page.locator('body').innerText()), url:page.url()};
        } else {
          value = {rows: await readScienceSchedule(page), scope:'current-page'};
        }
        console.log(JSON.stringify({event:'dashboard.part', part, ok:true, value}));
      } catch (error) {
        failed = true;
        console.log(JSON.stringify({event:'dashboard.part', part, ok:false, error:error.message}));
      }
    }
    if (state) await context.storageState({path:state});
    console.log('概览讲座查询结束；成功项目已更新，失败项目保留旧值。未报名或签到。');
  } finally { await browser.close(); }
  return !failed;
}
