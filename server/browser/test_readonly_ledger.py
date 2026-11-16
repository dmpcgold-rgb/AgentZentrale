import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from booking_ledger import inspect_existing_attempt

DAY="2026-11-20"
KEY="westbahn|Wien Meidling|Wiener Neustadt Hbf|18:22|Comfort2+"

class ReadonlyLedgerTests(unittest.TestCase):
    def test_missing_path_never_creates_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"missing.db"
            result=inspect_existing_attempt(str(path),KEY,DAY)
            self.assertEqual(result["status"],"UNAVAILABLE")
            self.assertFalse(path.exists())

    def test_existing_empty_ledger_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"existing.db"
            db=sqlite3.connect(str(path))
            db.execute("CREATE TABLE attempts(journey_key TEXT, travel_date TEXT, status TEXT)")
            db.commit()
            db.close()
            result=inspect_existing_attempt(str(path),KEY,DAY)
            self.assertEqual(result["status"],"NONE")

    def test_existing_pending_attempt_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"existing.db"
            db=sqlite3.connect(str(path))
            db.execute("CREATE TABLE attempts(journey_key TEXT, travel_date TEXT, status TEXT)")
            db.execute("INSERT INTO attempts VALUES (?,?,?)",(KEY,DAY,"PENDING"))
            db.commit()
            db.close()
            result=inspect_existing_attempt(str(path),KEY,DAY)
            self.assertEqual(result["status"],"PENDING")

    def test_invalid_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"invalid.db"
            path.write_text("not a sqlite database")
            result=inspect_existing_attempt(str(path),KEY,DAY)
            self.assertEqual(result["status"],"UNAVAILABLE")

if __name__=="__main__":
    unittest.main()
