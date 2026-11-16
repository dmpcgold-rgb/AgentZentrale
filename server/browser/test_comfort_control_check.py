import unittest
from unittest.mock import MagicMock, patch
import worker


class ComfortControlTests(unittest.TestCase):
    def prepared(self, control):
        return {'status':'comfort_inspected','accountVerifiedBeforeSearch':True,
                'connection':{'date':'2026-11-20','departure':'18:22','trainNumber':'1009'},
                'inspection':{'targetClassLabels':1,'controls':[control]}}

    def test_disabled_zero_euro_control_blocks(self):
        with patch.object(worker,'authenticated_prepare',return_value=self.prepared(
            {'disabled':True,'visible':True,'prices':['0,00 €']})):
            result=worker.inspect_comfort_booking_control(MagicMock(),'2026-11-20')
        self.assertEqual(result['bookingFieldState'],'disabled')
        self.assertFalse(result['bookingAuthorized'])

    def test_enabled_zero_euro_control_only_reports_state(self):
        prepared=self.prepared({'disabled':False,'visible':True,'pointerEvents':'auto','prices':['0,00 €']})
        with patch.object(worker,'authenticated_prepare',return_value=prepared), patch.object(
            worker,'apply_comfort_control_price',return_value={'displayedPriceCents':0,'priceSource':'comfort_control'}):
            result=worker.inspect_comfort_booking_control(MagicMock(),'2026-11-20')
        self.assertEqual(result['bookingFieldState'],'enabled_zero_euro')
        self.assertTrue(result['bookingFieldClickable'])
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['purchaseExecuted'])

    def test_enabled_paid_control_blocks(self):
        prepared=self.prepared({'disabled':False,'visible':True,'pointerEvents':'auto','prices':['3,00 €']})
        with patch.object(worker,'authenticated_prepare',return_value=prepared), patch.object(
            worker,'apply_comfort_control_price',return_value={'displayedPriceCents':300,'priceSource':'comfort_control'}):
            result=worker.inspect_comfort_booking_control(MagicMock(),'2026-11-20')
        self.assertEqual(result['bookingFieldState'],'price_not_verified_zero')
        self.assertFalse(result['bookingFieldClickable'])

    def test_ambiguous_controls_block(self):
        prepared=self.prepared({'disabled':False})
        prepared['inspection']['targetClassLabels']=2
        with patch.object(worker,'authenticated_prepare',return_value=prepared):
            result=worker.inspect_comfort_booking_control(MagicMock(),'2026-11-20')
        self.assertEqual(result['bookingFieldState'],'control_ambiguous')

    def test_login_unverified_blocks(self):
        with patch.object(worker,'authenticated_prepare',return_value={'status':'login_required'}):
            result=worker.inspect_comfort_booking_control(MagicMock(),'2026-11-20')
        self.assertEqual(result['bookingFieldState'],'account_or_connection_unverified')


if __name__=='__main__':
    unittest.main()
