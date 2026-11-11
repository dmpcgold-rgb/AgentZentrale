import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from worker import price_audit_view, classify_price_audit

DAY='2026-11-18'
CONNECTION={'date':DAY,'trainNumber':'1009','departure':'18:22',
            'arrival':'18:49','class':'2+','displayedPriceCents':0}


class PriceAuditLoginTests(unittest.TestCase):
    def test_normal_profile_unverified_does_not_read_price_or_search(self):
        page=Mock()
        ctx=Mock(pages=[page])
        with patch('worker.ensure_austrian_session',
                   return_value={'status':'login_required'}) as login, \
             patch('worker.prepare') as search, \
             patch('worker.apply_comfort_control_price') as price:
            result=price_audit_view(ctx,DAY,root=Path('/tmp/only-test'))
        login.assert_called_once_with(page,Path('/tmp/only-test'))
        search.assert_not_called()
        price.assert_not_called()
        page.goto.assert_not_called()
        self.assertEqual(result['status'],'account_unverified_before_search')
        self.assertFalse(result['accountVerifiedBeforeSearch'])
        self.assertEqual(result['priceSamplesCents'],[])

    def test_disposable_copy_without_session_is_not_auto_logged_in(self):
        page=Mock()
        ctx=Mock(pages=[page])
        with patch('worker.verify_austrian_session',
                   return_value={'status':'login_required'}) as verify, \
             patch('worker.ensure_austrian_session') as login, \
             patch('worker.prepare') as search:
            result=price_audit_view(ctx,DAY)
        verify.assert_called_once_with(page)
        login.assert_not_called()
        search.assert_not_called()
        page.goto.assert_not_called()
        self.assertFalse(result['accountVerifiedBeforeSearch'])
        self.assertEqual(result['priceSamplesCents'],[])

    def test_verified_normal_profile_reads_four_read_only_price_samples(self):
        page=Mock()
        ctx=Mock(pages=[page])
        with patch('worker.ensure_austrian_session',
                   return_value={'status':'account_verified'}) as login, \
             patch('worker.verify_austrian_session',
                   return_value={'status':'account_verified'}) as after, \
             patch('worker.prepare',
                   return_value={'status':'connection_found','connection':CONNECTION}) as search, \
             patch('worker.comfort_control_details',
                   return_value={'targetClassLabels':1,'controls':[]}) as controls, \
             patch('worker.apply_comfort_control_price',
                   return_value={'displayedPriceCents':0}) as price:
            result=price_audit_view(ctx,DAY,root=Path('/tmp/only-test'))
        login.assert_called_once_with(page,Path('/tmp/only-test'))
        search.assert_called_once_with(page,DAY)
        after.assert_called_once_with(page)
        self.assertEqual(controls.call_count,4)
        self.assertEqual(price.call_count,4)
        self.assertEqual(result['priceSamplesCents'],[0,0,0,0])
        self.assertTrue(result['accountVerifiedBeforeSearch'])
        self.assertTrue(result['accountVerified'])
        self.assertEqual(result['status'],'price_observed')
        self.assertNotIn('bookingAuthorized',result)

    def test_audit_classifier_does_not_call_anonymous_price_a_valid_zero(self):
        verified_zero={'accountVerifiedBeforeSearch':True,
                       'priceSamplesCents':[0,0,0,0]}
        verified_paid={'accountVerifiedBeforeSearch':True,
                       'priceSamplesCents':[790,790]}
        unverified={'accountVerifiedBeforeSearch':False,
                    'priceSamplesCents':[0,0,0,0]}
        self.assertEqual(classify_price_audit(
            unverified,verified_zero,verified_zero),'normal_session_unverified')
        self.assertEqual(classify_price_audit(
            verified_zero,unverified,verified_zero),'cloned_session_unverified')
        self.assertEqual(classify_price_audit(
            verified_zero,verified_zero,unverified),'restricted_session_unverified')
        self.assertEqual(classify_price_audit(
            verified_zero,verified_paid,verified_paid),'profile_copy_price_differs')
        self.assertEqual(classify_price_audit(
            verified_zero,verified_zero,verified_paid),'restricted_context_price_differs')
        self.assertEqual(classify_price_audit(
            verified_paid,verified_zero,verified_zero),'normal_browser_zero_not_confirmed')
        self.assertEqual(classify_price_audit(
            verified_zero,verified_zero,verified_zero),'isolated_zero_observed')


if __name__=='__main__':
    unittest.main()
