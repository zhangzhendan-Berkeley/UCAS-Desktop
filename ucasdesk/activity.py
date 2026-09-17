"""Confirmed outcomes, account-scoped counters and a durable notification outbox."""
from datetime import datetime
import json
import sqlite3
from contextlib import contextmanager
from .enrollment import account_hash

MILESTONES = [
    ('signs', 1, '签到初体验'), ('signs', 10, '十次准时'), ('signs', 50, '五十次坚持'),
    ('days', 7, '七日同行'), ('days', 30, '三十日积累'),
    ('bookings', 1, '讲座启程'), ('bookings', 5, '人文探索者'),
    ('selections', 1, '心仪课程到手'), ('selections', 5, '规划落地'),
]
NOTICE_TYPES = {'booking': '人文讲座预约成功', 'selection': '选课成功',
    'task_failed': '任务失败 / 有未完成项', 'mooc_completed': '慕课本轮任务结束', 'sign': '签到成功'}
NOTICE_DEFAULTS = {'booking': True, 'selection': True, 'task_failed': True, 'mooc_completed': True, 'sign': False}


class Activity:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS outcomes(
                    account TEXT, kind TEXT, identifier TEXT, title TEXT, at TEXT,
                    automatic INTEGER, detail TEXT, PRIMARY KEY(account,kind,identifier));
                CREATE TABLE IF NOT EXISTS achievements(
                    scope TEXT, metric TEXT, threshold INTEGER, title TEXT, at TEXT,
                    PRIMARY KEY(scope,metric,threshold));
                CREATE TABLE IF NOT EXISTS mail(
                    account TEXT, identifier TEXT, state TEXT, at TEXT, detail TEXT,
                    PRIMARY KEY(account,identifier));
                CREATE TABLE IF NOT EXISTS snapshots(
                    account TEXT, kind TEXT, at TEXT, payload TEXT, PRIMARY KEY(account,kind));
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(mail)')}
            if 'payload' not in columns:
                db.execute("ALTER TABLE mail ADD COLUMN payload TEXT NOT NULL DEFAULT '{}'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db: yield db
        finally: db.close()

    def record(self, account, kind, identifier, title, automatic=True, detail=None, at=None, notify=None):
        if not account or kind not in ('sign', 'booking', 'selection') or not identifier:
            return False
        at = at or datetime.now().isoformat(timespec='seconds')
        with self.connect() as db:
            added = db.execute('INSERT OR IGNORE INTO outcomes VALUES(?,?,?,?,?,?,?)',
                (account, kind, str(identifier), str(title), at, int(automatic),
                 json.dumps(detail or {}, ensure_ascii=False))).rowcount == 1
            if added and notify is not None:
                key = str(identifier) if kind == 'booking' else kind + ':' + str(identifier)
                payload = dict(kind=kind, title=str(title), at=at, detail=detail or {})
                db.execute('INSERT OR IGNORE INTO mail(account,identifier,state,at,detail,payload) VALUES(?,?,?,?,?,?)',
                    (account, key, 'pending' if notify else 'disabled', at, '', json.dumps(payload, ensure_ascii=False)))
            return added

    def counts(self, iclass, sep):
        with self.connect() as db:
            signs, days = db.execute("SELECT count(*),count(DISTINCT substr(at,1,10)) FROM outcomes WHERE account=? AND kind='sign' AND automatic=1", (iclass,)).fetchone()
            bookings = db.execute("SELECT count(*) FROM outcomes WHERE account=? AND kind='booking'", (sep,)).fetchone()[0]
            selections = db.execute("SELECT count(*) FROM outcomes WHERE account=? AND kind='selection'", (sep,)).fetchone()[0]
        return dict(signs=signs, days=days, bookings=bookings, selections=selections)

    def unlock(self, iclass, sep):
        counts = self.counts(iclass, sep)
        new = []
        with self.connect() as db:
            for metric, threshold, title in MILESTONES:
                scope = iclass if metric in ('signs', 'days') else sep
                if scope and counts[metric] >= threshold:
                    if db.execute('INSERT OR IGNORE INTO achievements VALUES(?,?,?,?,?)',
                        (scope, metric, threshold, title, datetime.now().isoformat(timespec='seconds'))).rowcount:
                        new.append(title)
        return new

    def badges(self, iclass, sep):
        with self.connect() as db:
            return [r[0] for r in db.execute('SELECT title FROM achievements WHERE scope IN (?,?) ORDER BY at', (iclass, sep))]

    def snapshot(self, account, kind, payload):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?)',
                (account, kind, datetime.now().isoformat(timespec='seconds'), json.dumps(payload, ensure_ascii=False)))

    def get_snapshot(self, account, kind):
        with self.connect() as db:
            row = db.execute('SELECT at,payload FROM snapshots WHERE account=? AND kind=?', (account, kind)).fetchone()
        return {'at': row[0], 'payload': json.loads(row[1])} if row else {}

    def queue_mail(self, account, identifier, enabled, payload=None):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO mail(account,identifier,state,at,detail,payload) VALUES(?,?,?,?,?,?)',
                (account, str(identifier), 'pending' if enabled else 'disabled', datetime.now().isoformat(timespec='seconds'), '', json.dumps(payload or {})))

    def recover_mail(self):
        with self.connect() as db:
            db.execute("UPDATE mail SET state='unknown',detail='上次发送中断，请先核对收件箱' WHERE state='sending'")

    def next_mail(self, account):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT m.identifier,m.payload,o.title,o.at,o.detail FROM mail m LEFT JOIN outcomes o ON m.account=o.account AND m.identifier=o.identifier AND o.kind='booking' WHERE m.account=? AND m.state='pending' ORDER BY m.at LIMIT 1", (account,)).fetchone()
            if row:
                db.execute("UPDATE mail SET state='sending' WHERE account=? AND identifier=?", (account, row[0]))
        if not row: return None
        payload = json.loads(row[1])
        return payload | {'identifier': row[0]} if payload else dict(identifier=row[0], kind='booking', title=row[2], at=row[3], detail=json.loads(row[4] or '{}'))

    def mail_result(self, account, identifier, state, detail=''):
        with self.connect() as db:
            db.execute('UPDATE mail SET state=?,detail=?,at=? WHERE account=? AND identifier=?',
                (state, detail, datetime.now().isoformat(timespec='seconds'), account, identifier))

    def mail_status(self, account):
        with self.connect() as db:
            row = db.execute('SELECT state,at,detail FROM mail WHERE account=? ORDER BY at DESC LIMIT 1', (account,)).fetchone()
        return row


def scope(vault, key):
    username = vault.get(key).get('username', '')
    return account_hash(username) if username else ''
