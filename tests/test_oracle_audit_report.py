import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "oracle-audit-report.py"

class OracleAuditReportTests(unittest.TestCase):
    def test_allowlist_excludes_private_data(self):
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            secret = "PRIVATE-TICKET-CODE-MUST-NOT-LEAK"
            (d / "log").write_text(
                "SNAPSHOT_CHECKSUMS=OK\n"
                "CHECKOUT_PYTHON_SYNTAX=OK\n"
                "LIVE_SOURCE_DIFFERENCES=0\n"
                "AUDIT_COMPLETE: checksum and syntax verified; production unchanged.\n"
                f"PASSWORD={secret}\n"
                f"File /root/oracle/{secret}/secret.env\n"
                f"TICKET_NUMBER={secret}\n",
                encoding="utf-8",
            )
            (d / "status").write_text("0\n")
            result = subprocess.run([sys.executable, str(SCRIPT), str(d / "log"), str(d / "status"),
                                     str(d / "report")], env={**os.environ, "MODE": "audit"},
                                     capture_output=True, text=True, check=True)
            payload = (d / "report").read_text(encoding="utf-8")
            self.assertNotIn(secret, payload)
            self.assertEqual(json.loads(payload)["status"], "audit_verified")
            self.assertEqual(json.loads(payload)["checks"]["LIVE_SOURCE_DIFFERENCES"], 0)
    def test_failed_remote_command_never_claims_verified(self):
        with tempfile.TemporaryDirectory() as td:
            d=pathlib.Path(td)
            (d / "log").write_text("AUDIT_COMPLETE: something\nSNAPSHOT_CHECKSUMS=OK\nCHECKOUT_PYTHON_SYNTAX=OK\nLIVE_SOURCE_DIFFERENCES=0\n")
            (d / "status").write_text("23\n")
            subprocess.run([sys.executable, str(SCRIPT),str(d/"log"),str(d/"status"),str(d/"out")],
                           env={**os.environ,"MODE":"audit"},check=True,capture_output=True,text=True)
            self.assertEqual(json.loads((d/"out").read_text())["status"],"failed")

if __name__ == "__main__":
    unittest.main()
