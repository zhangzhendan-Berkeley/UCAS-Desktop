import { test } from 'node:test';
import assert from 'node:assert/strict';
import { explainLectures } from '../adapters/lecture_diagnostics.mjs';
import { parseAttendance } from '../adapters/lecture_records.mjs';

const base = {id:'test', title:'M1168雁栖湖会场：生命何以为奇迹？ — 物理学如是说',
  location:'主会场：雁栖湖 - 国际会议中心报告厅', startTimeText:'2026-09-23 15:30-17:30',
  actionAvailable:true, terminalState:null};
const quota = {bookedCount:0,requiredCount:10};
const config = (start,end) => ({timeWindows:[{weekday:3,ranges:[{startMinutes:start,endMinutes:end}]}]});

test('real reported afternoon example: evening filter explains skip, all day allows Yanqi', () => {
  const evening = explainLectures({lectures:[base],quota},config(18*60,22*60))[0];
  assert.equal(evening.eligible,false);
  assert.equal(evening.reason,'time-window-mismatch');
  assert.match(evening.detail,/18:00-22:00/);
  assert.equal(explainLectures({lectures:[base],quota},config(0,1439))[0].eligible,true);
});
test('all-day never admits other campuses or already manually booked lecture', () => {
  for(const location of ['主会场：中关村 - 教学楼N308','主会场：玉泉路 - 人文楼报告厅','']) {
    assert.equal(explainLectures({lectures:[{...base,location}],quota},config(0,1439))[0].reason,'campus-mismatch');
  }
  assert.equal(explainLectures({lectures:[{...base,terminalState:'booked',actionAvailable:false}],quota},config(0,1439))[0].reason,'page-terminal-state');
  assert.equal(explainLectures({lectures:[base],quota:{bookedCount:10,requiredCount:10}},config(0,1439))[0].reason,'quota-reached');
});
test('official count parser distinguishes genuine zero from missing/changed/login pages', () => {
  assert.deepEqual(parseAttendance('统计信息：累计听讲座\u00a02\u00a0次，其中有效\u00a00\u00a0次'),{total:2,valid:0});
  assert.deepEqual(parseAttendance('累计听讲座 1 次，其中有效 1 次'),{total:1,valid:1});
  for(const text of ['请登录','累计听讲座 1 次，其中有效 2 次','累计听讲座 0 次，其中有效 0 次 累计听讲座 1 次，其中有效 1 次']) assert.throws(()=>parseAttendance(text));
});
