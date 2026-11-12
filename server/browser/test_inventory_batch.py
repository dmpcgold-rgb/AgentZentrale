import unittest
from inventory_batch import validate_batch_dates, summarize_inventory_batch


class InventoryBatchTests(unittest.TestCase):
    def test_accept_five_unique_weekdays(self):
        dates='2026-11-16,2026-11-17,2026-11-18,2026-11-19,2026-11-20'
        self.assertEqual(len(validate_batch_dates(dates)),5)

    def test_reject_weekend_duplicate_bad_format_or_oversize(self):
        for raw in (
            '',None,'2026-11-14','2026-11-17,2026-11-17',
            '2026-11-17,2026-11-18,2026-11-19,2026-11-20,2026-11-23,2026-11-24',
            '2026-2-17','2026-11-31','2026-11-17;shutdown',
        ):
            with self.subTest(value=raw):
                with self.assertRaises(ValueError):
                    validate_batch_dates(raw)

    def test_existing_tickets_are_visible_but_never_make_inventory_complete(self):
        rows=[
            {'dateLabel':'DI 17 NOV','seat':'191D','fullDate':'2026-11-17',
             'bookingReference':True,'ticketReference':True,'privateToken':'DO_NOT_LOG'},
            {'dateLabel':'MI 18 NOV','seat':'233A','fullDate':None,
             'bookingReference':False,'privateToken':'PRIVATE-SECOND'}
        ]
        days=['2026-11-17','2026-11-18','2026-11-19']
        result=summarize_inventory_batch(rows,days,[{'status':'account_verified'},
                                      {'status':'timeout'}])
        self.assertEqual(result['status'],'inventory_batch_read')
        self.assertEqual(result['accountPageReads'],1)
        self.assertEqual([r['status'] for r in result['days']],
                         ['visible_year_verified','possible_existing','review_required'])
        self.assertEqual(result['days'][0]['seats'],['191D'])
        self.assertEqual(result['days'][1]['seats'],['233A'])
        self.assertEqual(result['days'][2]['seats'],[])
        self.assertTrue(result['days'][1]['potentialDuplicate'])
        self.assertFalse(result['inventoryComplete'])
        self.assertFalse(result['safeToBook'])
        self.assertFalse(result['bookingAuthorized'])
        self.assertNotIn('DO_NOT_LOG',str(result))
        self.assertNotIn('PRIVATE-SECOND',str(result))

    def test_booking_preflight_blockers_are_fail_closed(self):
        result=summarize_inventory_batch([],['2026-11-19'],[])
        self.assertEqual(result['bookingPreflight'],'blocked')
        self.assertEqual(result['days'][0]['bookingBlockers'],['reservation_absence_not_verified'])
        self.assertFalse(result['bookingAuthorized'])

    def test_coverage_reports_partial_pages_without_exposing_identifiers(self):
        reports=[
            {'domain':'westbahn.at','page':1,'status':'account_verified'},
            {'domain':'westbahn.de','page':2,'status':'account_verified'},
            {'domain':'westbahn.at','page':3,'status':'timeout',
             'privateToken':'NEVER_EXPOSE_ME'}
        ]
        result=summarize_inventory_batch([],['2026-11-17'],reports)
        self.assertEqual(result['status'],'inventory_batch_read')
        self.assertEqual(result['coverage'],{
            'pagesAttempted':3,'pagesVerified':2,'pagesFailed':1,
            'domainsRead':2,'complete':False,'reason':'page_error_or_login'
        })
        self.assertFalse(result['inventoryComplete'])
        self.assertFalse(result['safeToBook'])
        self.assertNotIn('NEVER_EXPOSE_ME',str(result))

    def test_successful_scanned_pages_still_never_prove_complete_inventory(self):
        reports=[
            {'domain':'westbahn.at','page':1,'status':'account_verified'},
            {'domain':'westbahn.at','page':2,'status':'account_verified'},
            {'domain':'westbahn.de','page':1,'status':'account_verified'},
            {'domain':'westbahn.de','page':2,'status':'account_verified'}
        ]
        result=summarize_inventory_batch([],['2026-11-17'],reports)
        self.assertEqual(result['coverage']['pagesVerified'],4)
        self.assertEqual(result['coverage']['pagesFailed'],0)
        self.assertEqual(result['coverage']['reason'],'pagination_not_authoritative')
        self.assertFalse(result['coverage']['complete'])
        self.assertEqual(result['days'][0]['status'],'review_required')
        self.assertFalse(result['bookingAuthorized'])

    def test_strict_detail_evidence_upgrades_matching_yearless_ticket(self):
        rows=[{'dateLabel':'DI 17 NOV','seat':'191D','fullDate':None}]
        day='2026-11-17'
        detail={
            'status':'ticket_detail_check','date':day,'seat':'191D',
            'detailStatus':'detail_read','yearVerified':True,
            'seatMatched':True,'tripMatched':True,'referenceVisible':True,
            'dateExplicit':True,'bookingAuthorized':False,
            'confirmationVerified':False,'safeToBook':False,
            'inventoryComplete':False,'privateReference':'MUST_NOT_LEAK'
        }
        res=summarize_inventory_batch(rows,[day],[{'status':'account_verified'}],{day:detail})
        self.assertEqual(res['days'][0]['status'],'detail_verified')
        self.assertEqual(res['days'][0]['seats'],['191D'])
        self.assertTrue(res['days'][0]['detailVerified'])
        self.assertTrue(res['days'][0]['dateVerified'])
        self.assertFalse(res['inventoryComplete'])
        self.assertFalse(res['safeToBook'])
        self.assertFalse(res['bookingAuthorized'])
        self.assertNotIn('MUST_NOT_LEAK',str(res))

    def test_unverified_wrong_date_or_conflicting_detail_does_not_upgrade(self):
        rows=[{'dateLabel':'DI 17 NOV','seat':'191D'}]
        day='2026-11-17'
        good={
            'status':'ticket_detail_check','date':day,'seat':'191D',
            'detailStatus':'detail_read','yearVerified':True,'seatMatched':True,
            'tripMatched':True,'referenceVisible':True,'dateExplicit':True,
            'bookingAuthorized':False,'confirmationVerified':False,
            'safeToBook':False,'inventoryComplete':False
        }
        variants=[
            {'date':'2027-11-17'},
            {'seat':'233A'},
            {'yearVerified':False},
            {'referenceVisible':False},
            {'inventoryComplete':True},
            {'safeToBook':True},
            {'bookingAuthorized':True},
            {'confirmationVerified':True},
            {'detailStatus':'detail_unavailable'},
            {'status':'unknown'}
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                result=summarize_inventory_batch(
                    rows,[day],[{'status':'account_verified'}],
                    {day:{**good,**changes}})
                self.assertEqual(result['days'][0]['status'],'possible_existing')
                self.assertFalse(result['days'][0]['detailVerified'])
                self.assertFalse(result['days'][0]['safeToBook'])

    def test_conflicting_seats_never_upgrade_to_verified(self):
        rows=[{'dateLabel':'DI 17 NOV','seat':'191D'},
              {'dateLabel':'DI 17 NOV','seat':'233A'}]
        day='2026-11-17'
        detail={'status':'ticket_detail_check','date':day,'seat':'191D',
                'detailStatus':'detail_read','yearVerified':True,'seatMatched':True,
                'tripMatched':True,'referenceVisible':True,'dateExplicit':True,
                'bookingAuthorized':False,'confirmationVerified':False,
                'safeToBook':False,'inventoryComplete':False}
        result=summarize_inventory_batch(rows,[day],[{'status':'account_verified'}],{day:detail})
        self.assertEqual(result['days'][0]['status'],'possible_existing')
        self.assertFalse(result['days'][0]['detailVerified'])

    def test_no_matches_and_no_account_pages_still_require_review(self):
        result=summarize_inventory_batch([],['2026-11-17'],[])
        self.assertEqual(result['days'][0]['status'],'review_required')
        self.assertEqual(result['status'],'account_unavailable')
        self.assertFalse(result['inventoryComplete'])
        self.assertFalse(result['safeToBook'])


if __name__=='__main__':
    unittest.main()
