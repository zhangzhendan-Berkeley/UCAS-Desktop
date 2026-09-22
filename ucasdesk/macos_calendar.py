"""Export a date range for manual import into the user's iCloud calendar."""
from datetime import datetime, timedelta
from pathlib import Path
import json
import subprocess
from zoneinfo import ZoneInfo
import sys
from .calendar_export import _date_time, write_ics, course_location
from .lecture_visibility import calendar_lecture

def sync_range(activity, course_account, sep_account, calendar_name='UCAS Desktop', days=1, offset=0, courses=None):
    if sys.platform != 'darwin':
        return 0, '仅 macOS 支持自动写入系统日历'
    target = datetime.now().date() + timedelta(days=offset)
    until = target + timedelta(days=days)
    events = []
    today = activity.get_snapshot(course_account, 'today').get('payload', {})
    for item in (courses if courses is not None else today.get('courses', [])):
        start = _date_time(item.get('start') or item.get('classBeginTime') or item.get('time'))
        if start and target <= start.date() < until:
            end = _date_time(item.get('end') or item.get('classEndTime')) or start + timedelta(minutes=50)
            events.append((start, end, item.get('courseName') or item.get('name') or '课程', course_location(item)))
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
    path, count = write_ics(events, Path.home() / 'Documents' / filename)
    payload = [{'start': start.replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp(),
                'end': end.replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp(),
                'title': title, 'location': location}
               for start, end, title, location in events]
    try:
        result = subprocess.run(
            ['/usr/bin/swift', str(Path(__file__).resolve().parents[1] / 'scripts/icloud_calendar.swift')],
            input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True, timeout=120)
        if result.returncode == 0:
            return count, f'已提交到 iCloud 的 UCAS 日历，共检查 {count} 项（重复事件跳过）；备份：{path}'
        reason = '请在系统设置中授予日历完全访问权限' if 'access denied' in result.stderr else '未能写入，请确认 iCloud 下存在唯一且可写的 UCAS 日历及 Swift 工具可用'
    except (OSError, subprocess.TimeoutExpired):
        reason = '日历访问超时或 Swift 工具不可用'
    return count, f'{reason}。已导出 {count} 项至 {path}，尚未确认同步到 iCloud'


def sync_tomorrow(activity, course_account, sep_account, calendar_name='UCAS Desktop'):
    return sync_range(activity, course_account, sep_account, calendar_name, days=1, offset=1)
