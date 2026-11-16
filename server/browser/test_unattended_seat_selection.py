"""Offline tests for unattended seat-selection safety gates."""
import unittest
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

    def test_selection_never_purchases(self):
        page=MagicMock()
        choice={'coach':'11','seat':'233A'}
        with patch.object(worker,'authenticated_prepare',return_value={
            'status':'connection_found','accountVerifiedBeforeSearch':True,
            'connection':{'displayedPriceCents':0}}),patch.object(worker,'open_review_seat_map',return_value=page),patch.object(worker,'find_open_review_page',return_value=(page,{})),patch.object(worker,'select_primary_seat_in_open_modal',return_value={'status':'primary_seat_selected','selection':choice}),patch.object(worker,'confirm_review_selection',return_value={'status':'seat_confirmed','selection':choice}):
            result=worker.unattended_seat_selection(page,'2026-11-20')
        self.assertEqual(result['status'],'seat_selected_not_booked')
        self.assertEqual(result['seat'],'233A')
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['purchaseExecuted'])

    def test_unconfirmed_selection_blocks(self):
        page=MagicMock()
        choice={'coach':'11','seat':'233A'}
        with patch.object(worker,'authenticated_prepare',return_value={
            'status':'connection_found','accountVerifiedBeforeSearch':True,
            'connection':{'displayedPriceCents':0}}),patch.object(worker,'open_review_seat_map',return_value=page),patch.object(worker,'find_open_review_page',return_value=(page,{})),patch.object(worker,'select_primary_seat_in_open_modal',return_value={'status':'primary_seat_selected','selection':choice}),patch.object(worker,'confirm_review_selection',return_value={'status':'seat_confirmation_unverified'}):
            result=worker.unattended_seat_selection(page,'2026-11-20')
        self.assertEqual(result['status'],'unattended_selection_blocked')
        self.assertFalse(result['purchaseExecuted'])

if __name__=='__main__':
    unittest.main()
