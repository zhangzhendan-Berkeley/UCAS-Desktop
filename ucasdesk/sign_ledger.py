"""Atomic, account-scoped claims shared by scheduled and manual sign workers."""
import hashlib
import sqlite3
from contextlib import contextmanager
import time
import math
import secrets
from .core import DATA


class SignLedger:
    def __init__(self, username, path=None):
        self.account = hashlib.sha256(username.strip().encode()).hexdigest()
        self.path = path or DATA / 'sign-ledger.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS signs(account TEXT, id TEXT, status TEXT, attempts INTEGER, retry_at REAL, PRIMARY KEY(account,id))')
            db.execute('CREATE TABLE IF NOT EXISTS schedules(account TEXT, id TEXT, start REAL, run_at REAL, PRIMARY KEY(account,id,start))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def planned_time(self, identifier, start, now=None):
        """One durable random time per account and class occurrence, shared by workers."""
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT run_at FROM schedules WHERE account=? AND id=? AND start=?',
                             (self.account, identifier, start)).fetchone()
            if old:
                return old[0]
            earliest = max(start - 20 * 60, math.ceil(now))
            # Late startup keeps the existing catch-up behavior; do not invent a past time.
            run_at = earliest + secrets.randbelow(int(start - earliest)) if earliest < start else now
            db.execute('INSERT INTO schedules VALUES(?,?,?,?)', (self.account, identifier, start, run_at))
            return run_at

    def claim(self, identifier, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT status,attempts,retry_at FROM signs WHERE account=? AND id=?', (self.account, identifier)).fetchone()
            if old:
                status, attempts, retry_at = old
                if status != 'retry' or attempts >= 3:
                    return 'skip'
                if now < retry_at:
                    return 'wait'
            else:
                attempts = 0
            db.execute('INSERT OR REPLACE INTO signs VALUES(?,?,?,?,?)', (self.account, identifier, 'attempting', attempts + 1, 0))
        return 'claimed'

    def finish(self, identifier, status, retry_at=0):
        with self.connect() as db:
            db.execute('UPDATE signs SET status=?,retry_at=? WHERE account=? AND id=?', (status, retry_at, self.account, identifier))

    def rows(self):
        with self.connect() as db:
            return db.execute('SELECT id,status,attempts FROM signs WHERE account=?', (self.account,)).fetchall()
