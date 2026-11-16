"""Regression tests: read-only WESTbahn audit must not infer ticket absence."""
import unittest
from unittest.mock import patch
import unattended_audit as audit


class AuditSafetyTests(unittest.TestCase):
    DAYS=['2026-11-16','2026-11-17','2026-11-18','2026-11-19','2026-11-20']

    def test_no_visible_ticket_remains_needs_review(self):
        payload={'status':'inventory_batch_read','days':[
            {'date':day,'status':'review_required','seats':[],
             'dateVerified':False,'detailVerified':False,'potentialDuplicate':False}
            for day in self.DAYS]}
        result=audit.safe_summary(payload,self.DAYS)
        self.assertEqual(result['status'],'audit_completed')
        self.assertTrue(all(d['status']=='needs_review' for d in result['days']))
        self.assertFalse(result['bookingAuthorized'])

    def test_partial_ticket_card_is_a_conflict(self):
        payload={'status':'inventory_batch_read','days':[
            {'date':day,'status':'possible_existing' if i==4 else 'review_required',
             'seats':['233A'] if i==4 else [],'potentialDuplicate':i==4}
            for i,day in enumerate(self.DAYS)]}
        result=audit.safe_summary(payload,self.DAYS)
        self.assertEqual(result['days'][4]['status'],'possible_existing')

    def test_zero_euro_fare_never_authorizes_purchase(self):
        summary={'status':'audit_completed','days':[{'date':'2026-11-20','status':'needs_review','seats':[]}],
                 'bookingAuthorized':False,'purchaseExecuted':False}
        proc=type('Proc',(),{'returncode':0,'stdout':(
            '{"status":"comfort_inspected","date":"2026-11-20",'
            '"accountVerifiedBeforeSearch":true,"bookingAuthorized":false,'
            '"connection":{"displayedPriceCents":0}}')})()
        with patch.object(audit.subprocess,'run',return_value=proc):
            result=audit.inspect_unbooked_days(summary,worker='dummy.py')
        self.assertEqual(result['days'][0]['fareInspection'],'zero_euro_observed')
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['purchaseExecuted'])

    def test_coverage_diagnostics_are_redacted_and_non_authoritative(self):
        payload={'status':'inventory_batch_read','days':[
            {'date':day,'status':'review_required','seats':[]} for day in self.DAYS],
            'coverage':{'pagesAttempted':5,'pagesVerified':4,'pagesFailed':1,
                        'secretToken':'DO_NOT_EXPOSE'},
            'paginationDiagnostics':{'westbahn.at':{
                'pagesVerified':[1,2],'linkedPagesObserved':[1,2,3],
                'linkedPagesNotVerified':[3],
                'cardCoverage':{'unmatchedComfortCards':2,
                                'visibleParserConsistent':False},
                'rawTicketReference':'DO_NOT_EXPOSE'}}}
        result=audit.safe_summary(payload,self.DAYS)
        self.assertEqual(result['scanDiagnostics']['austrianLinkedPagesMissing'],1)
        self.assertEqual(result['scanDiagnostics']['unmatchedComfortCards'],2)
        self.assertFalse(result['scanDiagnostics']['providerInventoryComplete'])
        self.assertFalse(result['bookingAuthorized'])
        self.assertNotIn('DO_NOT_EXPOSE',str(result))

    def test_duplicate_dates_block_audit(self):
        payload={'status':'inventory_batch_read','days':[
            {'date':self.DAYS[0],'status':'review_required'} for _ in self.DAYS]}
        result=audit.safe_summary(payload,self.DAYS)
        self.assertEqual(result['status'],'audit_blocked')


if __name__=='__main__':
    unittest.main()
