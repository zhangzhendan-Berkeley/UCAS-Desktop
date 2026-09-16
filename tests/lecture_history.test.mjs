import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, report } from '../adapters/lecture_history.mjs';

const lecture = (title, available = true) => ({ id: title, title, location: '雁栖湖教一楼', yanqi: true,
  startTimeText: '2026-10-01 19:00', actionAvailable: available, terminalState: null });
const date = value => new Date(`2026-09-${value}+08:00`);

test('baseline, new availability, dedup and stable identity despite button changes', () => {
  let result = observe(null, [lecture('已有'), lecture('未开放', false)], date('16T08:01:10'), '2026-09-16T08:01');
  assert.equal(result.newlyAvailable.length, 0);
  assert.equal(result.baseline, true);
  result = observe(result.state, [lecture('已有'), lecture('未开放'), lecture('新讲座')], date('16T08:31:10'), '2026-09-16T08:31');
  assert.equal(result.newlyAvailable.length, 2);
  assert.deepEqual(result.newlyAvailable.map(e => e.kind), ['opened', 'new']);
  assert.equal(result.newlyAvailable[0].previousCheck, date('16T08:01:10').toISOString());
  result = observe(result.state, [{ ...lecture('未开放'), id: 'changed-button-id' }, lecture('新讲座')], date('16T09:01:10'), '2026-09-16T09:01');
  assert.equal(result.newlyAvailable.length, 0);
  assert.equal(result.state.events.length, 2);
  assert.match(report(result.state), /08:31 \| 2/);
});

test('reopening seats does not masquerade as first publication; failed checks do not move lower bound', () => {
  let result = observe(null, [], date('16T08:01:10'), '2026-09-16T08:01');
  result.state.checks.push({ at: date('16T08:31:10').toISOString(), slot: '2026-09-16T08:31', ok: false });
  result = observe(result.state, [lecture('新讲座')], date('16T09:01:10'), '2026-09-16T09:01');
  assert.equal(result.newlyAvailable[0].previousCheck, date('16T08:01:10').toISOString());
  result = observe(result.state, [lecture('新讲座', false)], date('16T09:31:10'), '2026-09-16T09:31');
  result = observe(result.state, [lecture('新讲座')], date('23T10:01:10'), '2026-09-23T10:01');
  assert.equal(result.newlyAvailable.length, 0);
  const text = report(result.state);
  assert.match(text, /失败：1/);
  assert.match(text, /至少一周/);
});

test('other campuses retained but excluded from Yanqi histogram', () => {
  let result = observe(null, [], date('16T08:01:10'), '2026-09-16T08:01');
  result = observe(result.state, [{ ...lecture('外校区'), location: '玉泉路礼堂', yanqi: false }], date('16T08:31:10'), '2026-09-16T08:31');
  assert.equal(result.newlyAvailable.length, 1);
  const text = report(result.state);
  assert.match(text, /玉泉路礼堂/);
  assert.doesNotMatch(text.split('## 新出现')[0], /08:31 \| 1/);
});
