import { existsSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

export function observe(previous, rows, now, slot) {
  const state = structuredClone(previous || { version: 1, lectures: {}, checks: [], events: [] });
  const at = now.toISOString();
  const baseline = !state.lastSuccess;
  state.startedAt ||= at;
  const newlyAvailable = [];
  for (const row of rows) {
    // Upstream IDs may contain changing button text; observation identity must not.
    const id = createHash('sha256').update(JSON.stringify([row.title, row.startTimeText, row.location])).digest('hex');
    const available = Boolean(row.actionAvailable && !row.terminalState);
    const record = state.lectures[id] ||= {
      id, title: row.title, lectureTime: row.startTimeText, location: row.location, yanqi: Boolean(row.yanqi),
      firstSeen: at, baseline, firstAvailable: null,
    };
    record.lastSeen = at;
    record.title = row.title;
    if (available && !record.firstAvailable) {
      record.firstAvailable = at;
      record.availabilityBaseline = baseline;
      if (!baseline) {
        const event = { id, title: row.title, lectureTime: row.startTimeText, location: row.location, yanqi: Boolean(row.yanqi),
          observedAt: at, previousCheck: state.lastSuccess, slot,
          kind: record.firstSeen === at ? 'new' : 'opened' };
        state.events.push(event);
        newlyAvailable.push(event);
      }
    }
    record.available = available;
  }
  state.lastSuccess = at;
  state.checks.push({ at, slot, ok: true, count: rows.length, newCount: newlyAvailable.length, baseline });
  return { state, newlyAvailable, baseline };
}

const local = value => value ? new Date(value).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai' }) : '—';
const cell = value => String(value ?? '').replace(/[\r\n|]/g, ' ');

export function report(state) {
  const checks = state.checks || [];
  const events = state.events || [];
  const first = checks.find(c => c.ok);
  const last = [...checks].reverse().find(c => c.ok);
  const days = first && last ? (Date.parse(last.at) - Date.parse(first.at)) / 86400000 : 0;
  const counts = new Map();
  for (const event of events.filter(e => e.yanqi)) {
    const key = event.slot?.slice(-5) || local(event.observedAt).slice(11, 16);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const lines = ['# 人文讲座可报名时间观察', '',
    `开始：${local(state.startedAt)}；最近成功：${local(state.lastSuccess)}`,
    `观察跨度：${days.toFixed(1)} 天；成功检查：${checks.filter(c => c.ok).length} 次；失败：${checks.filter(c => !c.ok).length} 次；非初始样本：${events.length} 场。`, '',
    days >= 7 ? '已积累至少一周跨度。可参考下方时段分布，在应用中缩小“检查小时”；不会自动减少检查时段。' : '尚不足一周，继续每小时 01 / 31 分取样。', '',
    '**时间是首次发现可报名的北京时间，不是学校准确发布时间。** 初次检查已有讲座作为基线，不纳入新增统计；已看到但不可报名的讲座以后变为可报名，会记为开放。',
    '每轮读取当前列表页；列表分页、补放名额、个体配额、登录失败、休眠或关机均可能影响观察。长检查间隔不能用于推断精确发布时间。一周没有新增样本也不能说明没有新讲座。',
    '“上次成功检查—首次发现”表示两次列表观察之间的区间；未连续观测的时段不填造记录。', '',
    `自动报名状态：${state.bookingPending ? '暂停：有未确认的提交，请人工核对学校记录；观察继续' : '无未确认的自动报名轮次'}`, '',
    '## 雁栖湖首次可报名的检查时点分布', '', '| 计划时点（北京时间） | 场数 |', '| --- | ---: |',
    ...[...counts].sort((a, b) => b[1] - a[1]).map(([k, n]) => `| ${k} | ${n} |`), '',
    '## 新出现 / 首次开放（所有校区，仅雁栖湖参与上方统计）', '', '| 讲座 | 地点 | 类型 | 上次成功检查 | 首次发现可报名 |', '| --- | --- | --- | --- | --- |',
    ...events.map(e => `| ${cell(e.title)} | ${cell(e.location)} | ${e.kind === 'new' ? '新出现' : '首次开放'} | ${local(e.previousCheck)} | ${local(e.observedAt)} |`), '',
    '## 检查记录（最近 100 次）', '', '| 计划时点 | 实际检查时间 | 结果 |', '| --- | --- | --- |',
    ...checks.slice(-100).map(c => `| ${cell(c.slot)} | ${local(c.at)} | ${c.ok ? `成功，${c.count} 场${c.baseline ? '（基线）' : ''}` : '失败，详见任务日志'} |`), '',
  ];
  return lines.join('\n');
}

export function loadHistory(dir) {
  const path = join(dir, 'observations.json');
  return existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : { version: 1, lectures: {}, checks: [], events: [] };
}

export function saveHistory(dir, state) {
  const path = join(dir, 'observations.json');
  writeFileSync(path + '.tmp', JSON.stringify(state, null, 2));
  renameSync(path + '.tmp', path);
  writeFileSync(join(dir, '发布时间观察.md'), report(state));
}
