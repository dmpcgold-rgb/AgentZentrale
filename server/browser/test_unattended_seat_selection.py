"""Offline tests for unattended seat-selection safety gates."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import worker

class SeatSelectionTests(unittest.TestCase):
    def test_nonzero_price_never_opens_seat_map(self):
        with patch.object(worker,'authenticated_prepare',return_value={
            'status':'connection_found','accountVerifiedBeforeSearch':True,
            'connection':{'displayedPriceCents':790}}),patch.object(worker,'open_review_seat_map') as open_map:
            result=worker.unattended_seat_selection(MagicMock(),'2026-11-20')
        open_map.assert_not_called()
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['purchaseExecuted'])

    def test_unverified_account_blocks(self):
        with patch.object(worker,'authenticated_prepare',return_value={'status':'account_unverified'}),patch.object(worker,'open_review_seat_map') as open_map:
            result=worker.unattended_seat_selection(MagicMock(),'2026-11-20')
        open_map.assert_not_called()
        self.assertEqual(result['status'],'unattended_selection_blocked')

    def test_zero_price_still_blocks_without_duplicate_proof(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'WESTBAHN_BOOKING_LEDGER':str(Path(directory)/'ledger.db')}), patch.object(worker,'authenticated_prepare',return_value={
            'status':'connection_found','accountVerifiedBeforeSearch':True,
            'connection':{'displayedPriceCents':0}}),patch.object(worker,'open_review_seat_map') as open_map:
            result=worker.unattended_seat_selection(MagicMock(),'2026-11-20')
        open_map.assert_not_called()
        self.assertEqual(result['phase'],'duplicate_absence_not_verified')
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['purchaseExecuted'])

    def test_confirmed_local_booking_blocks(self):
        from booking_ledger import AttemptLedger
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'ledger.db')
            ledger=AttemptLedger(path)
            journey='westbahn|Wien Meidling|Wiener Neustadt Hbf|18:22|Comfort2+'
            attempt=ledger.claim(journey,'2026-11-20')
            ledger.transition(attempt['attempt_id'],'CONFIRMED',confirmed_by_provider=True)
            ledger.close()
            with patch.dict('os.environ', {'WESTBAHN_BOOKING_LEDGER':path}), patch.object(worker,'authenticated_prepare',return_value={
                'status':'connection_found','accountVerifiedBeforeSearch':True,
                'connection':{'displayedPriceCents':0}}), patch.object(worker,'open_review_seat_map') as open_map:
                result=worker.unattended_seat_selection(MagicMock(),'2026-11-20')
            open_map.assert_not_called()
            self.assertEqual(result['phase'],'local_duplicate_confirmed')

    def test_missing_price_blocks(self):
        with patch.object(worker,'authenticated_prepare',return_value={
            'status':'connection_found','accountVerifiedBeforeSearch':True,
            'connection':{'displayedPriceCents':None}}),patch.object(worker,'open_review_seat_map') as open_map:
            result=worker.unattended_seat_selection(MagicMock(),'2026-11-20')
        open_map.assert_not_called()
        self.assertEqual(result['phase'],'fare_not_verified')

if __name__=='__main__':
    unittest.main()
