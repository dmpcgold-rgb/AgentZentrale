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

    def test_no_matches_and_no_account_pages_still_require_review(self):
        result=summarize_inventory_batch([],['2026-11-17'],[])
        self.assertEqual(result['days'][0]['status'],'review_required')
        self.assertEqual(result['status'],'account_unavailable')
        self.assertFalse(result['inventoryComplete'])
        self.assertFalse(result['safeToBook'])


if __name__=='__main__':
    unittest.main()
