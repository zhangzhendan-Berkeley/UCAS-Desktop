"""Export locally cached courses and lectures as an iCalendar file."""
from datetime import datetime, timedelta
from pathlib import Path
import re
from .core import DATA
from .lecture_visibility import visible_lecture

def _esc(value):
    return str(value or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

def _date_time(value):
    m = re.search(r'(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2}).*?(\d{1,2}):(\d{2})', str(value or ''))
    return datetime(*map(int, m.groups())) if m else None

def export_ics(activity, course_account, sep_account, path=None):
    events = []
    today = activity.get_snapshot(course_account, 'today').get('payload', {})
    for item in today.get('courses', []):
        start = _date_time(item.get('start') or item.get('classBeginTime') or item.get('time'))
        if not start: continue
        end = _date_time(item.get('end') or item.get('classEndTime')) or start + timedelta(minutes=50)
        events.append((start, end, item.get('courseName') or item.get('name') or '课程', item.get('classroom') or item.get('location') or ''))
    for kind, label in (('humanity', '人文讲座'), ('science', '科研讲座')):
        snapshot = activity.get_snapshot(sep_account, 'calendar-' + kind).get('payload', {})
        for item in snapshot.get('rows', []):
            if not visible_lecture(kind, item): continue
            start = _date_time(item.get('time') or item.get('start') or item.get('startTime'))
            if not start: continue
            events.append((start, start + timedelta(hours=2), f'{label} · {item.get("title") or "未命名"}', item.get('location') or ''))
    path = Path(path or DATA / 'UCAS-Desktop.ics')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//UCAS Desktop//CN', 'CALSCALE:GREGORIAN']
    for start, end, title, location in events:
        stamp = start.strftime('%Y%m%dT%H%M%S')
        lines += ['BEGIN:VEVENT', f'UID:ucas-{stamp}-{abs(hash(title))}@ucas-desktop', f'DTSTAMP:{stamp}', f'DTSTART:{stamp}', f'DTEND:{end.strftime("%Y%m%dT%H%M%S")}', f'SUMMARY:{_esc(title)}', f'LOCATION:{_esc(location)}', 'END:VEVENT']
    lines.append('END:VCALENDAR')
    path.write_text('\r\n'.join(lines) + '\r\n', encoding='utf-8')
    return path, len(events)
