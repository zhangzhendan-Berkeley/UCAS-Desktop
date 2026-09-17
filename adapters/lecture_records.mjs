import { browserLaunchOptions } from './browser_channel.mjs';
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';

export function parseAttendance(text) {
  const normalized = text.replace(/\s+/g, ' ');
  const found = [...normalized.matchAll(/累计听讲座\s*(\d+)\s*次[，,]?\s*其中有效\s*(\d+)\s*次/g)];
  if (found.length !== 1) throw new Error('未唯一识别学校听讲统计，保留上次结果；没有把空页面当成零次。');
  const total = Number(found[0][1]), valid = Number(found[0][2]);
  if (valid > total) throw new Error('学校听讲统计不一致，保留上次结果。');
  return { total, valid };
}

export async function queryAttendance(config, logger) {
  const browser = await chromium.launch({ ...browserLaunchOptions(), headless: config.headless });
  try {
    const state = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: state && existsSync(state) ? state : undefined });
    const page = await context.newPage();
    // Establish the ordinary humanities session first; record pages have different headers.
    await ensureAuthenticated(page, config, logger);
    const records = {};
    for (const [kind, path] of [['humanity', 'humanityStudent'], ['science', 'student']]) {
      const url = 'https://xkcts.ucas.ac.cn:8443/subject/' + path;
      await page.goto(url, { waitUntil: 'domcontentloaded', referer: page.url() });
      await page.locator('table th').first().waitFor({ timeout: 10000 });
      if (new URL(page.url()).pathname !== '/subject/' + path) throw new Error('讲座记录会话失效，请重新登录。');
      records[kind] = { ...parseAttendance(await page.locator('body').innerText()), url };
    }
    if (state) await context.storageState({ path: state });
    console.log(JSON.stringify({ event: 'lecture.attendance', records }));
    console.log('已读取学校有效听讲次数；未提交报名或签到。');
  } finally { await browser.close(); }
}
