import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { extractLectureSnapshot } from '../vendor/ucas-humanity-lecture-bot/dist/src/lecture-page.js';
import { loadHistory, saveHistory, observe } from './lecture_history.mjs';
import { browserChannel } from './browser_channel.mjs';
import { isYanqiLocation } from '../vendor/ucas-humanity-lecture-bot/dist/src/campus.js';
import { logDecisions } from './lecture_diagnostics.mjs';

export async function observeAndBook(config, logger, dir, payload, runAutomation) {
  let history = loadHistory(dir);
  let snapshot;
  let browser;
  try {
    browser = await chromium.launch({ channel: browserChannel(), headless: true });
    const statePath = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: statePath && existsSync(statePath) ? statePath : undefined });
    const page = await context.newPage();
    await ensureAuthenticated(page, { ...config, headless: true }, logger);
    snapshot = await extractLectureSnapshot(page);
    console.log(JSON.stringify({event:'lecture.calendar', kind:'humanity', scope:'current-page',
      rows:snapshot.lectures.map(row=>({title:row.title,time:row.startTimeText,location:row.location}))}));
    const observed = observe(history, snapshot.lectures.map(row => ({ ...row, yanqi: isYanqiLocation(row.location) })), new Date(), payload.slot);
    history = observed.state;
    saveHistory(dir, history);
    if (statePath) await context.storageState({ path: statePath });
    console.log(JSON.stringify({ event: 'lecture.observed', baseline: observed.baseline,
      count: snapshot.lectures.length, newCount: observed.newlyAvailable.length,
      observedAt: history.lastSuccess }));
    console.log(observed.baseline ? '首次检查建立基线，已有讲座不计入新增发布时间统计。' : `发现 ${observed.newlyAvailable.length} 场首次可报名讲座，已记录时间。`);
    for (const item of observed.newlyAvailable) console.log(`首次可报名：${item.title} | ${item.observedAt}`);
  } catch (error) {
    history.checks.push({ at: new Date().toISOString(), slot: payload.slot, ok: false });
    saveHistory(dir, history);
    throw error;
  } finally {
    if (browser) await browser.close();
  }
  const decisions = logDecisions(snapshot, config);
  if (payload.preview || !payload.book) return;
  if (history.bookingPending) {
    console.log('此前自动报名结果未确认，保持只读观察。请核对学校记录后，在应用中解除报名暂停。');
    return;
  }
  const eligible = decisions.some(d => d.eligible);
  if (!eligible) {
    console.log('本轮没有符合所选星期、时间及页面配额条件的可报名讲座。');
    return;
  }
  // Persist before any write: errors/crashes cannot silently replay a submission next slot.
  history.bookingPending = true;
  saveHistory(dir, history);
  const summary = await runAutomation({ ...config, headless: true, dryRun: false }, logger);
  console.log(JSON.stringify({ event: 'lecture.booking', attempts: summary.attempts, stopReason: summary.stopReason }));
  if (summary.attempts.some(a => a.outcome === 'unknown')) {
    throw new Error('存在报名结果不明确的讲座，自动报名已暂停；后续定点观察继续。');
  }
  history.bookingPending = false;
  saveHistory(dir, history);
}
