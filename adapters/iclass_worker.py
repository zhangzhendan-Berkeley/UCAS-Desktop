import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucasdesk.iclass import IClass, eligible, parse_time, course_id
from ucasdesk.sign_ledger import SignLedger


def daily_courses(client, date, now=None):
    now = now or datetime.now()
    result = {}
    for course in client.query(date):
        course_id(course['id'])
        start, end = parse_time(course['classBeginTime']), parse_time(course['classEndTime'])
        if start.strftime('%Y%m%d') != date or end <= start:
            raise ValueError('课表日期或起止时间不正确，停止建立当天计划。')
        if end > now and str(course.get('signStatus')) != '1':
            result[course['id']] = course
    return list(result.values())


def main(payload):
    client = IClass(payload['username'], payload['password'])
    ledger = SignLedger(payload['username'])
    if payload['mode'] == 'single':
        identifier = course_id(payload['identifier'])
        if ledger.claim(identifier) != 'claimed':
            print('此排课已处理、正在处理或上次结果不明，未重复提交。请核对学校记录。', flush=True)
            return 1
        try:
            result = client.sign(identifier)
        except Exception:
            ledger.finish(identifier, 'unknown')
            raise
        ledger.finish(identifier, 'success' if result['success'] else 'retry' if result.get('retryable') else 'unknown', time.time() + 120)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result['success'] else 1
    if payload['mode'] == 'daily':
        date = payload['date']
        for attempt in range(3):
            if datetime.now().strftime('%Y%m%d') != date:
                raise ValueError('已跨日，停止昨日课表检查；等待新的每日计划。')
            try:
                courses = daily_courses(client, date)
                break
            except Exception as exc:
                print(f'每日课表检查 {attempt + 1}/3 失败：{exc}', flush=True)
                if attempt == 2:
                    raise
                print('5 分钟后重试只读查询。', flush=True)
                time.sleep(300)
        print(json.dumps({'event': 'iclass.daily-plan', 'date': date, 'courses': courses}, ensure_ascii=False), flush=True)
        if not courses:
            print('今天没有尚未结束且未签到的课程，不需要建立任务。', flush=True)
            return 0
    else:
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
                claim = ledger.claim(key)
                if claim == 'wait':
                    next_attempt[key] = time.monotonic() + 10
                    continue
                if claim == 'skip':
                    print(f'{course["courseName"]}：本机已有处理记录（成功、处理中、次数用完或结果不明），未重复提交；请核对学校记录。', flush=True)
                    del pending[key]
                    failures += 1
                    continue
                attempts[key] += 1
                # Claim is committed before HTTP: a crash cannot replay an uncertain submission.
                try:
                    result = client.sign(key)
                except Exception:
                    ledger.finish(key, 'unknown')
                    raise
                retry_at = max(time.time() + 120, parse_time(updated['classBeginTime']).timestamp())
                ledger.finish(key, 'success' if result['success'] else 'retry' if result.get('retryable') else 'unknown', retry_at)
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
                # Do not spend all three attempts before class actually begins.
                next_attempt[key] = time.monotonic() + max(120, retry_at - time.time())
                print('下次允许尝试：' + datetime.fromtimestamp(retry_at).strftime('%Y-%m-%d %H:%M:%S'), flush=True)
        if pending:
            time.sleep(10)
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        sys.exit(main(json.load(sys.stdin)))
    except Exception as exc:
        print(f'任务停止：{exc}', flush=True)
        sys.exit(1)
