"""Account-scoped local reminders; no school writes or attendance inference."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from .core import read_json, write_json

BEIJING = timezone(timedelta(hours=8))


def now_beijing():
    return datetime.now(BEIJING)


def start_time(row):
    try:
        value = datetime.fromisoformat(row.get('start', ''))
        return value.replace(tzinfo=BEIJING) if value.tzinfo is None else value.astimezone(BEIJING)
    except (ValueError, TypeError):
        return None


def lecture_key(kind, row):
    value = [kind, row.get('title'), row.get('start'), row.get('location')]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


class LectureReminders:
    def __init__(self, directory):
        self.path = directory / 'lecture-reminders.json'
        self.data = read_json(self.path, {'accounts': {}, 'sent': {}})

    def config(self, account):
        return {'enabled': False, 'minutes': 20, 'overrides': {}} | self.data['accounts'].get(account, {})

    def save(self, account, **changes):
        if not account:
            raise ValueError('请先在个人信息填写 SEP 账号。')
        self.data['accounts'][account] = self.config(account) | changes
        write_json(self.path, self.data)

    def options(self, account, kind, row):
        config = self.config(account)
        override = config['overrides'].get(lecture_key(kind, row), {})
        return override.get('enabled', True), int(override.get('minutes', config['minutes']))

    def save_lecture(self, account, kind, row, enabled, minutes=None):
        overrides = dict(self.config(account)['overrides'])
        item = {'enabled': bool(enabled)}
        if minutes is not None:
            item['minutes'] = max(0, min(1440, int(minutes)))
        overrides[lecture_key(kind, row)] = item
        self.save(account, overrides=overrides)

    def due(self, account, calendars, now=None):
        now = now or now_beijing()
        if not account or not self.config(account)['enabled']:
            return []
        found, seen = [], set()
        for kind, rows in calendars.items():
            for row in rows:
                key = account + ':' + lecture_key(kind, row)
                start = start_time(row)
                enabled, minutes = self.options(account, kind, row)
                # Catch up while still upcoming, never replay after the start.
                in_window = start and (start - timedelta(minutes=minutes) <= now <= start or
                                       minutes == 0 and 0 <= (now-start).total_seconds() < 10)
                if (enabled and in_window
                        and key not in self.data['sent'] and key not in seen):
                    found.append((kind, row))
                    seen.add(key)
        return sorted(found, key=lambda item: start_time(item[1]))

    def mark_sent(self, account, items, now=None):
        now = now or now_beijing()
        for kind, row in items:
            self.data['sent'][account + ':' + lecture_key(kind, row)] = now.isoformat()
        write_json(self.path, self.data)
