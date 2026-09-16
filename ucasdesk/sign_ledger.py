"""Atomic, account-scoped claims shared by scheduled and manual sign workers."""
import hashlib
import sqlite3
import time
from .core import DATA


class SignLedger:
    def __init__(self, username, path=None):
        self.account = hashlib.sha256(username.strip().encode()).hexdigest()
        self.path = path or DATA / 'sign-ledger.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS signs(account TEXT, id TEXT, status TEXT, attempts INTEGER, retry_at REAL, PRIMARY KEY(account,id))')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

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
