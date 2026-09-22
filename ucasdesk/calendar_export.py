"""Export locally cached courses and lectures as an iCalendar file."""
from datetime import datetime, timedelta
from pathlib import Path
import re
import hashlib
from datetime import timezone
from .core import DATA
from .lecture_visibility import calendar_lecture

def _esc(value):
    return str(value or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

def _date_time(value):
    m = re.search(r'(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2}).*?(\d{1,2}):(\d{2})', str(value or ''))
    return datetime(*map(int, m.groups())) if m else None

def course_location(item):
    for key in ('classroomName', 'classroom', 'location', 'classRoomName', 'teachBuildName', 'teachingBuildingName'):
        value = str(item.get(key) or '').strip()
        if value and value.lower() not in ('null', 'none'):
            return value
    return ''

def export_ics(activity, course_account, sep_account, path=None):
    events = []
    today = activity.get_snapshot(course_account, 'today').get('payload', {})
    for item in today.get('courses', []):
        start = _date_time(item.get('start') or item.get('classBeginTime') or item.get('time'))
        if not start: continue
        end = _date_time(item.get('end') or item.get('classEndTime')) or start + timedelta(minutes=50)
        events.append((start, end, item.get('courseName') or item.get('name') or '课程', course_location(item)))
    for kind, label in (('humanity', '人文讲座'), ('science', '科研讲座')):
        snapshot = activity.get_snapshot(sep_account, 'calendar-' + kind).get('payload', {})
        for item in snapshot.get('rows', []):
            if not calendar_lecture(kind, item): continue
            start = _date_time(item.get('time') or item.get('start') or item.get('startTime'))
            if not start: continue
            events.append((start, start + timedelta(hours=2), f'{label} · {item.get("title") or "未命名"}', item.get('location') or ''))
    return write_ics(events, path or DATA / 'UCAS-Desktop.ics')


def write_ics(events, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//UCAS Desktop//CN', 'CALSCALE:GREGORIAN']
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    def utc(value):
        return value.replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for start, end, title, location in events:
        identity = hashlib.sha256(f'{start.isoformat()}|{title}|{location}'.encode()).hexdigest()
        lines += ['BEGIN:VEVENT', f'UID:{identity}@ucas-desktop', f'DTSTAMP:{timestamp}', f'DTSTART:{utc(start)}', f'DTEND:{utc(end)}', f'SUMMARY:{_esc(title)}', f'LOCATION:{_esc(location)}', 'END:VEVENT']
    lines.append('END:VCALENDAR')
    folded = []
    for line in lines:
        part = ''
        for char in line:
            if len((part + char).encode('utf-8')) > 75:
                folded.append(part)
                part = ' '
            part += char
        folded.append(part)
    path.write_bytes(('\r\n'.join(folded) + '\r\n').encode('utf-8'))
    return path, len(events)
