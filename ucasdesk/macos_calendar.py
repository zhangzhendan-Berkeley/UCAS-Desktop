"""macOS Calendar integration through Calendar.app's AppleScript interface."""
from datetime import datetime, timedelta
import subprocess
import sys
from .calendar_export import _date_time
from .lecture_visibility import visible_lecture

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
            events.append((start, end, item.get('courseName') or item.get('name') or '课程', item.get('classroom') or item.get('location') or item.get('classRoomName') or '学校未提供地点'))
    for kind, label in (('humanity', '人文讲座'), ('science', '科研讲座')):
        rows = activity.get_snapshot(sep_account, 'calendar-' + kind).get('payload', {}).get('rows', [])
        for item in rows:
            if not visible_lecture(kind, item): continue
            start = _date_time(item.get('time') or item.get('start') or item.get('startTime'))
            if start and target <= start.date() < until:
                end = _date_time(item.get('end'))
                if not end or end <= start: continue
                events.append((start, end, f'{label} · {item.get("title") or "未命名"}', item.get('location') or ''))
    def esc(s): return str(s or '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    lines = [f'set targetCalendar to missing value', f'tell application "Calendar"', f'  if not (exists calendar "{calendar_name}") then make new calendar with properties {{name:"{calendar_name}"}}', f'  set targetCalendar to calendar "{calendar_name}"']
    for start, end, title, location in events:
        lines.append(f'  set startDate to current date\n  set day of startDate to 1\n  set year of startDate to {start.year}\n  set month of startDate to {start.strftime("%B")}\n  set day of startDate to {start.day}\n  set time of startDate to ({start.hour} * hours + {start.minute} * minutes)')
        lines.append(f'  set endDate to current date\n  set day of endDate to 1\n  set year of endDate to {end.year}\n  set month of endDate to {end.strftime("%B")}\n  set day of endDate to {end.day}\n  set time of endDate to ({end.hour} * hours + {end.minute} * minutes)')
        lines.append(f'  if not (exists (events of targetCalendar whose summary is "{esc(title)}" and start date is startDate)) then')
        lines.append(f'  make new event at end of events of targetCalendar with properties {{summary:"{esc(title)}", start date:startDate, end date:endDate, location:"{esc(location)}", description:"UCAS Desktop 自动同步"}}')
        lines.append('  end if')
    lines.append('end tell')
    result = subprocess.run(['osascript'], input='\n'.join(lines), text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or '写入 macOS 日历失败')
    return len(events), f'已写入 macOS 日历：{target.isoformat()} 起 {days} 天，共 {len(events)} 项'


def sync_tomorrow(activity, course_account, sep_account, calendar_name='UCAS Desktop'):
    return sync_range(activity, course_account, sep_account, calendar_name, days=1, offset=1)
