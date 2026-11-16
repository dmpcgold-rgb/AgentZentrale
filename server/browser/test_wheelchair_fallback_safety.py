"""Regression coverage for wheelchair exclusion in fallback seat ranking.

Pure offline fixtures: no browser, network, checkout, or reservation.
"""
import unittest
from worker import ranked_layout_seats


def seat(code, group="table-1", **overrides):
    result = {
        "kind": "seat", "value": code, "group": group,
        "layout": "single-facing-table", "fourSeat": False,
        "wheelchair": False, "free": True,
        "disabled": False, "unavailable": False,
    }
    result.update(overrides)
    return result


class WheelchairFallbackSafetyTests(unittest.TestCase):
    def test_accessible_seat_is_not_selected(self):
        self.assertEqual(ranked_layout_seats({'controls': [
            seat("233A", wheelchair=True), seat("233D")
        ]}), [])

    def test_four_seat_group_is_not_selected(self):
        self.assertEqual(ranked_layout_seats({'controls': [
            seat("233A", fourSeat=True), seat("233D")
        ]}), [])

    def test_valid_two_seat_group_still_works(self):
        self.assertEqual(ranked_layout_seats({'controls': [
            seat("233A"), seat("233D")
        ]}), [(0, "233A"), (0, "233D")])

    def test_disabled_seat_is_not_returned(self):
        self.assertEqual(ranked_layout_seats({'controls': [
            seat("233A", disabled=True, free=False), seat("233D")
        ]}), [(0, "233D")])

    def test_four_seat_group_with_only_two_visible_is_not_approved(self):
        self.assertEqual(ranked_layout_seats({'controls': [
            seat("233A", layout="four-seat"), seat("233D", layout="four-seat")
        ]}), [])


if __name__ == "__main__":
    unittest.main()
