import { browserLaunchOptions } from './browser_channel.mjs';
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { readUpcomingSchedule } from './lecture_pagination.mjs';

async function retryRead(page, config, logger, path, attempts = 3) {
  let last;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      await ensureAuthenticated(page, { ...config, humanityLectureUrl: 'https://xkcts.ucas.ac.cn:8443/subject/' + path }, logger);
      return await readUpcomingSchedule(page, logger);
    } catch (error) {
      last = error;
      if (attempt === attempts) break;
      logger?.warn?.('lecture.query.retry', { path, attempt, error: String(error?.message || error) });
      await new Promise(resolve => setTimeout(resolve, 1500 * attempt));
    }
  }
  throw last;
}

export async function queryLectureCalendars(config, logger) {
  const browser = await chromium.launch({ ...browserLaunchOptions(), headless: false });
  try {
    const state = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: state && existsSync(state) ? state : undefined });
    const page = await context.newPage();
    for (const [kind, path] of [['humanity', 'humanityLecture'], ['science', 'lecture']]) {
      const result = await retryRead(page, config, logger, path);
      console.log(JSON.stringify({ event: 'lecture.calendar', kind, ...result }));
    }
    if (state) await context.storageState({ path: state });
    console.log('人文 / 科研讲座时间表已查询；只读操作，没有提交报名或签到。');
  } finally { await browser.close(); }
}
