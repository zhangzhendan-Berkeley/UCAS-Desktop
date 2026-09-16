import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucasdesk.iclass import IClass, eligible, parse_time, course_id


def main(payload):
    client = IClass(payload['username'], payload['password'])
    if payload['mode'] == 'single':
        result = client.sign(payload['identifier'])
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result['success'] else 1
    courses = payload['courses']
    if not courses:
        raise ValueError('没有选中的课程。')
    for course in courses:
        course_id(course['id'])
        parse_time(course['classBeginTime'])
        parse_time(course['classEndTime'])
    pending = {c['id']: c for c in courses if str(c.get('signStatus')) != '1'}
    attempts = {key: 0 for key in pending}
    next_attempt = {key: 0 for key in pending}
    failures = 0
    print(f'已排队 {len(pending)} 节课；在开课前 {payload["minutes_before"]} 分钟开始，每节最多尝试 3 次。', flush=True)
    while pending:
        now = datetime.now()
        for key, course in list(pending.items()):
            if now >= parse_time(course['classEndTime']):
                print(f'{course["courseName"]}：已过下课时间，未提交。', flush=True)
                del pending[key]
                failures += 1
                continue
            if not eligible(course, now, payload['minutes_before']) or time.monotonic() < next_attempt[key]:
                continue
            attempts[key] += 1
            try:
                current = [course] if payload.get('manual') else client.query(now.strftime('%Y%m%d'))
                updated = next((c for c in current if c['id'] == key), None)
                if updated is None:
                    raise RuntimeError('当前课表未找到该排课 ID，停止本节自动签到。')
                if updated['signStatus'] == '1':
                    print(f'{course["courseName"]}：学校已记录签到，跳过。', flush=True)
                    del pending[key]
                    continue
                if not eligible(updated, datetime.now(), payload['minutes_before']):
                    raise RuntimeError('课表时间发生变化，请重新查询并建立任务。')
                result = client.sign(key)
                print(course['courseName'] + '：' + json.dumps(result, ensure_ascii=False), flush=True)
                if result['success']:
                    del pending[key]
                    continue
                if not result.get('retryable'):
                    print('结果未明确允许重试，停止本节任务，请在学校系统核对。', flush=True)
                    del pending[key]
                    failures += 1
                    continue
            except Exception as exc:
                print(f'{course["courseName"]}：{exc}', flush=True)
                # Unknown submission outcome must not be blindly replayed.
                del pending[key]
                failures += 1
                continue
            if attempts[key] >= 3:
                print('达到本节尝试上限，请人工核对。', flush=True)
                failures += 1
                del pending[key]
            else:
                next_attempt[key] = time.monotonic() + 120
        if pending:
            time.sleep(10)
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        sys.exit(main(json.load(sys.stdin)))
    except Exception as exc:
        print(f'任务停止：{exc}', flush=True)
        sys.exit(1)
