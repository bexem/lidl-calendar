"""Self-check for lidl_ics date handling. Run: python3 test_lidl_ics.py

The date logic is the one part that can silently produce a wrong year, so it
gets the coverage. Everything else is a straight scrape.
"""
import datetime as dt
import unittest

from lidl_ics import parse_date

D = dt.date


class TestParseDate(unittest.TestCase):
    def test_plain_thursday(self):
        self.assertEqual(parse_date("From Thursday, 01/10", D(2026, 10, 3)),
                         D(2026, 10, 1))

    def test_no_comma(self):
        self.assertEqual(parse_date("From Sunday, 11/10", D(2026, 10, 3)),
                         D(2026, 10, 11))
        self.assertEqual(parse_date("From Thursday 08/10", D(2026, 10, 3)),
                         D(2026, 10, 8))

    def test_undated_tiles_dropped(self):
        self.assertIsNone(parse_date("In Store Now", D(2026, 10, 3)))
        self.assertIsNone(parse_date("In Store From Next Week", D(2026, 10, 3)))
        self.assertIsNone(parse_date(None, D(2026, 10, 3)))

    def test_stale_does_not_roll_into_next_year(self):
        # A 30/07 offer still on the page in October must vanish, not become
        # July next year.
        self.assertIsNone(parse_date("From Thursday, 30/07", D(2026, 10, 3)))

    def test_year_rollover_forward(self):
        # Seen in late December, a January offer is next year.
        self.assertEqual(parse_date("From Thursday, 05/01", D(2026, 12, 30)),
                         D(2027, 1, 5))

    def test_year_rollover_backward(self):
        # Seen in early January, a late-December offer is THIS year - a
        # forward-only search misses it entirely.
        self.assertEqual(parse_date("From Thursday, 28/12", D(2027, 1, 2)),
                         D(2026, 12, 28))

    def test_impossible_date_rejected(self):
        self.assertIsNone(parse_date("From Thursday, 31/02", D(2026, 10, 3)))
        self.assertIsNone(parse_date("From Thursday, 32/13", D(2026, 10, 3)))

    def test_window_edges(self):
        # 60 days ahead is included, 61 is not.
        self.assertIsNotNone(parse_date("From Tuesday, 02/12", D(2026, 10, 3)))
        self.assertIsNone(parse_date("From Wednesday, 03/12", D(2026, 10, 3)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
