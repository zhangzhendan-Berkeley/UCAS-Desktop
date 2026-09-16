import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { loadConfig } from '../vendor/ucas-humanity-lecture-bot/dist/src/config.js';
import { Logger } from '../vendor/ucas-humanity-lecture-bot/dist/src/log.js';
import { runAutomation } from '../vendor/ucas-humanity-lecture-bot/dist/src/workflow.js';
import { queryScienceSchedule } from './lecture_schedule.mjs';
import { observeAndBook } from './lecture_observe.mjs';

try {
  let input = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) input += chunk.toString('utf8');
  const p = JSON.parse(input);
  process.env.UCAS_USERNAME = p.username;
  process.env.UCAS_PASSWORD = p.password;
  const root = dirname(dirname(fileURLToPath(import.meta.url)));
  const accountId = createHash('sha256').update(p.username).digest('hex').slice(0, 16);
  const dir = join(root, 'data', 'lecture', accountId);
  mkdirSync(dir, { recursive: true });
  process.env.UCAS_STORAGE_STATE = join(dir, 'browser-state.json');
  const configPath = join(dir, 'config.json');
  writeFileSync(configPath, JSON.stringify({
    runtime: { mode: 'single', dryRun: Boolean(p.preview), headless: false, statePath: join(dir, 'state.json') },
    captcha: { enabled: true, pythonExecutable: join(root, '.venv', 'Scripts', 'python.exe'), maxAttempts: 3 },
    filter: { timeWindows: (p.days || [0, 1, 2, 3, 4, 5, 6]).map(weekday => ({ weekday, periods: [[p.from || '00:00', p.to || '23:59']] })) },
    logging: { level: 'info' },
  }));
  const config = loadConfig(['--config', configPath]);
  const logger = new Logger('info');
  if (p.observe) {
    await observeAndBook(config, logger, dir, p, runAutomation);
  } else if (p.action === 'science-schedule') {
    await queryScienceSchedule(config, logger);
  } else {
  const rounds = p.scheduled ? Math.min(144, Math.max(1, Number(p.rounds || 12))) : 1;
  console.log(p.preview ? '仅检查候选讲座，不提交报名。' : '开始按所选星期与时段筛选并报名；浏览器中如出现邮箱验证，请手工完成。');
  for (let n = 0; n < rounds; n++) {
    console.log(`巡检 ${n + 1}/${rounds}`);
    const summary = await runAutomation(config, logger);
    for (const lecture of summary.candidates) console.log(`候选：${lecture.title} | ${lecture.startTimeText} | ${lecture.location || ''}`);
    console.log(JSON.stringify({候选数量: summary.candidates.length, 报名结果: summary.attempts, 停止原因: summary.stopReason, 配额: summary.quota}));
    if (summary.attempts.some(x => x.outcome === 'unknown')) throw new Error('存在报名结果不明确的讲座，停止巡检，请在学校页面核对。');
    if (summary.quota.bookedCount !== null && summary.quota.requiredCount !== null && summary.quota.bookedCount >= summary.quota.requiredCount) break;
    if (n + 1 < rounds) {
      const minutes = Math.max(5, Number(p.interval || 30));
      console.log(`等待 ${minutes} 分钟，电脑需保持运行。`);
      await delay(minutes * 60000);
    }
  }
  }
} catch (error) {
  console.error('讲座任务停止：' + error.message);
  process.exitCode = 1;
}
