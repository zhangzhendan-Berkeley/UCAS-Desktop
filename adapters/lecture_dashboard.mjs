import { browserLaunchOptions } from './browser_channel.mjs';
import { backgroundArgs } from '../vendor/ucas-humanity-lecture-bot/dist/src/background.js';
// One browser session, four independent reads, no registration/sign-in entry points.
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { readUpcomingSchedule } from './lecture_pagination.mjs';
import { readAttendance } from './lecture_records.mjs';

export const dashboardParts = ['humanity', 'science', 'humanity-attendance', 'science-attendance'];

export async function queryDashboard(config, logger) {
  // Dashboard refresh is interactive: keep Edge visible so the user can
  // complete CAPTCHA, new-device, or email verification when required.
  const browser = await chromium.launch({ ...browserLaunchOptions(), args: backgroundArgs, headless: false });
  let failed = false;
  let authenticationFailure = null;
  try {
    const state = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: state && existsSync(state) ? state : undefined });
    const page = await context.newPage();
    page.setDefaultNavigationTimeout(30000);
    for (const part of dashboardParts) {
      try {
        if (authenticationFailure) throw new Error('SEP 会话未建立，后续查询已暂停：' + authenticationFailure);
        const science = part.startsWith('science');
        const url = 'https://xkcts.ucas.ac.cn:8443/subject/' + (science ? 'lecture' : 'humanityLecture');
        try { await ensureAuthenticated(page, { ...config, humanityLectureUrl: url }, logger); }
        catch (error) { authenticationFailure = error.message; throw error; }
        let value;
        if (part.endsWith('attendance')) {
          const path = science ? 'student' : 'humanityStudent';
          await page.goto('https://xkcts.ucas.ac.cn:8443/subject/' + path, {waitUntil:'domcontentloaded', referer:page.url()});
          await page.locator('table th').first().waitFor({timeout:10000});
          if (new URL(page.url()).pathname !== '/subject/' + path) throw new Error('讲座记录会话失效，请重新登录。');
          value = {...await readAttendance(page), url:page.url()};
        } else {
          value = await readUpcomingSchedule(page, logger);
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
