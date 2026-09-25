"""Sync courses and eligible lectures using EventKit, retaining an ICS fallback."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import sys
from .calendar_export import _date_time, write_ics, course_location
from .lecture_visibility import calendar_lecture

BEIJING = timezone(timedelta(hours=8))


def helper_command(root=None):
    root = root or Path(__file__).resolve().parents[1]
    binary = root / 'runtime/calendar/ucas-calendar'
    if binary.is_file():
        return [str(binary)]
    return ['/usr/bin/swift', str(root / 'scripts/icloud_calendar.swift')]

def sync_range(activity, course_account, sep_account, calendar_name='UCAS Desktop', days=1, offset=0, courses=None):
    if sys.platform != 'darwin':
        return 0, '仅 macOS 支持自动写入系统日历'
    target = datetime.now(BEIJING).date() + timedelta(days=offset)
    until = target + timedelta(days=days)
    events = []
    today = activity.get_snapshot(course_account, 'today').get('payload', {})
    cached = activity.get_snapshot(course_account, 'calendar-courses').get('payload', {}).get('courses', [])
    seen = set()
    for item in (courses if courses is not None else cached + today.get('courses', [])):
        start = _date_time(item.get('start') or item.get('classBeginTime') or item.get('time'))
        if start and target <= start.date() < until:
            end = _date_time(item.get('end') or item.get('classEndTime')) or start + timedelta(minutes=50)
            event = (start, end, item.get('courseName') or item.get('name') or '课程', course_location(item))
            if event not in seen:
                seen.add(event)
                events.append(event)
    for kind, label in (('humanity', '人文讲座'), ('science', '科研讲座')):
        rows = activity.get_snapshot(sep_account, 'calendar-' + kind).get('payload', {}).get('rows', [])
        for item in rows:
            if not calendar_lecture(kind, item): continue
            start = _date_time(item.get('time') or item.get('start') or item.get('startTime'))
            if start and target <= start.date() < until:
                end = _date_time(item.get('end'))
                if not end or end <= start: continue
                events.append((start, end, f'{label} · {item.get("title") or "未命名"}', item.get('location') or ''))
    filename = 'UCAS.ics' if days > 1 else f'UCAS-{target.isoformat()}.ics'
    from .core import DATA
    path, count = write_ics(events, DATA / 'calendar-exports' / filename)
    if not count:
        return 0, '所选日期没有可同步的课程或已报名讲座；请先刷新课表和讲座列表。'
    payload = [{'start': start.replace(tzinfo=BEIJING).timestamp(),
                'end': end.replace(tzinfo=BEIJING).timestamp(),
                'title': title, 'location': location}
               for start, end, title, location in events]
    try:
        result = subprocess.run(
            helper_command(),
            input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True, timeout=120)
        if result.returncode == 0:
            return count, f'已写入本机 iCloud 的 UCAS 日历，共检查 {count} 项（重复事件跳过）；云端同步由系统日历完成；备份：{path}'
        reason = '请在系统设置→隐私与安全性→日历中授予 UCAS Desktop 日历完全访问权限' if 'access denied' in result.stderr else '未能写入，请确认系统日历的 iCloud 下存在唯一且可写的 UCAS 日历；源码版还需安装 Swift 工具'
    except (OSError, subprocess.TimeoutExpired):
        reason = '日历访问超时或日历组件不可用；请允许日历权限后重试'
    return count, f'{reason}。已导出 {count} 项至 {path}，尚未确认同步到 iCloud'


def sync_tomorrow(activity, course_account, sep_account, calendar_name='UCAS Desktop'):
    return sync_range(activity, course_account, sep_account, calendar_name, days=1, offset=1)
