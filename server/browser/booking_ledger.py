"""Durable, fail-closed local attempt ledger for WESTbahn.

This ledger prevents duplicate attempts from this agent, not tickets created
manually or via another system. It never authorizes an external purchase.
"""
import os
import sqlite3
import uuid
from datetime import date
from pathlib import Path

STATUSES = frozenset(('PENDING', 'CONFIRMED', 'FAILED', 'UNCERTAIN'))
BLOCKING = frozenset(('PENDING', 'CONFIRMED', 'UNCERTAIN'))


def _day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Expected YYYY-MM-DD')
    return value


class AttemptLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        self.db.execute('PRAGMA busy_timeout=30000')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute("""CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY,
            journey_key TEXT NOT NULL,
            travel_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING','CONFIRMED','FAILED','UNCERTAIN')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(journey_key, travel_date, attempt_id)
        )""")
        self.db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_active_attempt_per_journey_day
            ON attempts(journey_key, travel_date)
            WHERE status IN ('PENDING','CONFIRMED','UNCERTAIN')""")
        os.chmod(self.path, 0o600)

    def close(self):
        self.db.close()

    def claim(self, journey_key, travel_date, attempt_id=None):
        """Atomically claim one journey/day. Retries with same key are inert."""
        _day(travel_date)
        if not isinstance(journey_key, str) or not journey_key.strip():
            raise ValueError('journey_key required')
        key = attempt_id or str(uuid.uuid4())
        if not isinstance(key, str) or not key.strip():
            raise ValueError('attempt_id required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing = self.db.execute(
                'SELECT journey_key, travel_date, status FROM attempts WHERE attempt_id=?',
                (key,)).fetchone()
            if existing:
                result = {'claimed': False, 'reason': 'idempotent_replay' if
                          existing[:2] == (journey_key, travel_date) else 'key_reused_for_different_journey'}
            else:
                active = self.db.execute("""SELECT status FROM attempts
                    WHERE journey_key=? AND travel_date=? AND status IN ('PENDING','CONFIRMED','UNCERTAIN')
                    LIMIT 1""", (journey_key, travel_date)).fetchone()
                if active:
                    result = {'claimed': False, 'reason': 'already_' + active[0].lower()}
                else:
                    self.db.execute("""INSERT INTO attempts(attempt_id,journey_key,travel_date,status)
                        VALUES (?,?,?,'PENDING')""", (key, journey_key, travel_date))
                    result = {'claimed': True, 'reason': 'new_claim', 'attempt_id': key}
            self.db.execute('COMMIT')
            return result
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def transition(self, attempt_id, new_status, *, confirmed_by_provider=False):
        """Never infer FAILED from timeout; mark UNCERTAIN instead."""
        if new_status not in STATUSES or new_status == 'PENDING':
            raise ValueError('Invalid transition')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current = self.db.execute(
                'SELECT status FROM attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
            if not current or current[0] != 'PENDING':
                result = False
            elif new_status == 'CONFIRMED' and not confirmed_by_provider:
                result = False
            else:
                self.db.execute("""UPDATE attempts SET status=?,updated_at=CURRENT_TIMESTAMP
                    WHERE attempt_id=? AND status='PENDING'""", (new_status, attempt_id))
                result = True
            self.db.execute('COMMIT')
            return result
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def status(self, journey_key, travel_date):
        _day(travel_date)
        rows = self.db.execute("""SELECT status FROM attempts WHERE journey_key=?
            AND travel_date=? ORDER BY rowid DESC LIMIT 1""",
            (journey_key, travel_date)).fetchone()
        return rows[0] if rows else None
