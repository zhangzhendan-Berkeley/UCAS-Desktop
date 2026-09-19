import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { readUpcomingSchedule } from './lecture_pagination.mjs';
import { browserLaunchOptions } from './browser_channel.mjs';

export async function queryScienceSchedule(config, logger) {
  const browser = await chromium.launch({ ...browserLaunchOptions(), headless: false });
  try {
    const state = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: state && existsSync(state) ? state : undefined });
    const page = await context.newPage();
    await ensureAuthenticated(page, { ...config, humanityLectureUrl: "https://xkcts.ucas.ac.cn:8443/subject/lecture" }, logger);
    if (state) await context.storageState({ path: state });
    if (new URL(page.url()).pathname !== '/subject/lecture') throw new Error('科研讲座时间表会话失效，请重新查询。');
    const result = await readUpcomingSchedule(page, logger);
    console.log(JSON.stringify({ event: 'lecture.science-schedule', ...result }));
    console.log(`读取 ${result.pages} 页，共 ${result.rows.length} 场今天及之后的科研讲座。返回“课程与讲座签到”选择场次、填入时间；仍需该场轻新课堂二维码。未提交任何报名或签到。`);
  } finally { await browser.close(); }
}
