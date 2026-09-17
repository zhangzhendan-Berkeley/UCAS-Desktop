import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { readScienceSchedule } from '../vendor/ucas-humanity-lecture-bot/dist/src/portal.js';

export async function queryLectureCalendars(config, logger) {
  const browser = await chromium.launch({ channel: 'msedge', headless: config.headless });
  try {
    const state = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: state && existsSync(state) ? state : undefined });
    const page = await context.newPage();
    for (const [kind, path] of [['humanity', 'humanityLecture'], ['science', 'lecture']]) {
      await ensureAuthenticated(page, { ...config, humanityLectureUrl: 'https://xkcts.ucas.ac.cn:8443/subject/' + path }, logger);
      const rows = await readScienceSchedule(page);
      console.log(JSON.stringify({ event: 'lecture.calendar', kind, rows, scope: 'current-page' }));
    }
    if (state) await context.storageState({ path: state });
    console.log('人文 / 科研讲座时间表已查询；只读操作，没有提交报名或签到。');
  } finally { await browser.close(); }
}
