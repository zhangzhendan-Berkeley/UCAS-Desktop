// Shared, explicit explanations. No school submissions occur here.
import { isYanqiLocation } from '../vendor/ucas-humanity-lecture-bot/dist/src/campus.js';
import { decideLectures, isQuotaReached, summarizeDecisionReasonWithRules } from '../vendor/ucas-humanity-lecture-bot/dist/src/filter.js';

export function explainLectures(snapshot, config) {
  return snapshot.lectures.map(lecture => {
    if (!isYanqiLocation(lecture.location)) return { lecture, reason: 'campus-mismatch',
      eligible: false, detail: `仅预约雁栖湖；页面地点：${lecture.location || '未提供，无法确认校区'}` };
    const decision = decideLectures([lecture], { terminalLectures: {} }, new Set(),
      isQuotaReached(snapshot.quota), config.timeWindows)[0];
    return { lecture, reason: decision.reason, eligible: decision.action === 'candidate',
      detail: summarizeDecisionReasonWithRules(decision, config.timeWindows) };
  });
}

export function logDecisions(snapshot, config) {
  const decisions = explainLectures(snapshot, config);
  console.log(JSON.stringify({ event: 'lecture.filters', timeWindows: config.timeWindows, quota: snapshot.quota }));
  for (const item of decisions) {
    console.log(JSON.stringify({ event: 'lecture.decision', title: item.lecture.title,
      time: item.lecture.startTimeText, location: item.lecture.location,
      eligible: item.eligible, reason: item.reason, detail: item.detail }));
    console.log(`${item.eligible ? '符合条件' : '未报名'}：${item.lecture.title} | ${item.lecture.startTimeText || '时间未识别'} | ${item.detail}`);
  }
  return decisions;
}
