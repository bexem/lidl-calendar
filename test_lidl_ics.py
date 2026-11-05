"""Self-check for lidl_ics date handling. Run: python3 test_lidl_ics.py

The date logic is the one part that can silently produce a wrong year, so it
gets the coverage. Everything else is a straight scrape.
"""
import contextlib
import datetime as dt
import io
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

import lidl_ics
from lidl_ics import (calendar_sets, parse_date, strip_flavour_prefix)

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


class TestFlavourTitles(unittest.TestCase):
    """Lidl writes this promo two ways; both must reduce to the bare theme."""

    def strip(self, title):
        return strip_flavour_prefix(title)

    def test_with_colon(self):
        self.assertEqual(self.strip("Flavour of the Week: The Alps"), "The Alps")

    def test_hyphen_separator(self):
        self.assertEqual(self.strip("Flavour of the Week - Greece"), "Greece")
        self.assertEqual(self.strip("Flavor of the Week - Greece"), "Greece")

    def test_without_colon(self):
        self.assertEqual(self.strip("Flavour of the Week Sol and Mar"), "Sol and Mar")

    def test_trailing_space(self):
        self.assertEqual(self.strip("Flavour of the Week  The Alps "), "The Alps")

    def test_us_spelling(self):
        self.assertEqual(self.strip("Flavor of the Week: The Alps"), "The Alps")

    def test_non_flavour_untouched(self):
        for t in ("Pick of the Week", "The Wine Edit.", "Wooden Toys"):
            self.assertEqual(self.strip(t), t)

    def test_unseen_separators(self):
        # Lidl has used colon, dash and plain space so far; the strip must not
        # depend on knowing the next one.
        for sep in (" | ", " \u2022 ", " - ", " \u2013 ", ".", "  "):
            self.assertEqual(self.strip(f"Flavour of the Week{sep}Greece"),
                             "Greece", msg=repr(sep))

    def test_theme_starting_with_digit(self):
        self.assertEqual(self.strip("Flavour of the Week: 24 Christmas Puddings"),
                         "24 Christmas Puddings")

    def test_bare_prefix_not_emptied(self):
        self.assertEqual(self.strip("Flavour of the Week"), "Flavour of the Week")

    def test_accented_theme_keeps_first_letter(self):
        # The separator strip must stop at a letter, not at an ASCII one.
        self.assertEqual(self.strip("Flavour of the Week - \u00d6sterreich"),
                         "\u00d6sterreich")
        self.assertEqual(self.strip("Flavour of the Week: \u00c9picure"),
                         "\u00c9picure")

    def test_bracketed_theme_unwrapped(self):
        self.assertEqual(self.strip("Flavour of the Week (Greece)"), "Greece")
        self.assertEqual(self.strip("Flavour of the Week: [Greece]"), "Greece")

    def test_trailing_year_dropped(self):
        for raw in ("Flavour of the Week: The Alps (2026)",
                    "Flavour of the Week - The Alps (2025/26)",
                    "Flavour of the Week: The Alps (2025\u201326)",
                    "Flavour of the Week: The Alps [2026]"):
            self.assertEqual(self.strip(raw), "The Alps", msg=raw)

    def test_non_year_bracket_kept(self):
        text = "Flavour of the Week: Summer (BBQ)"
        self.assertEqual(self.strip(text), "Summer (BBQ)")


class TestCalendarSets(unittest.TestCase):
    """The prefix strip has to actually reach flavour.ics, not just exist."""

    def test_flavour_gets_bare_theme_and_others_keep_prefix(self):
        events = [
            {"title": "Flavour of the Week - Greece", "food": True},
            {"title": "Flavour of the Week: The Alps", "food": True},
            {"title": "The Wine Edit.", "food": True},
            {"title": "DIY", "food": False},
        ]
        sets = calendar_sets(events)

        self.assertEqual([e["title"] for e in sets["flavour"]],
                         ["Greece", "The Alps"])
        self.assertIn("Flavour of the Week - Greece",
                      [e["title"] for e in sets["food"]])
        self.assertEqual([e["title"] for e in sets["all"]],
                         [e["title"] for e in events])
        # Stripping must copy, not mutate the scraped events in place.
        self.assertEqual(events[0]["title"], "Flavour of the Week - Greece")

    def test_no_flavour_offers_yields_empty_set(self):
        self.assertEqual(calendar_sets([{"title": "DIY", "food": False}])["flavour"],
                         [])


PUBLISHED_FLAVOUR = (
    b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//lidl-calendar//EN\r\n"
    b"CALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\nX-WR-CALNAME:Lidl GB flavour\r\n"
    b"BEGIN:VEVENT\r\n"
    b"UID:https%3A//www.lidl.co.uk/c/flavour-of-the-week-greece/a10092213"
    b"@lidl-calendar\r\n"
    b"DTSTAMP:20261029T171739Z\r\n"
    b"DTSTART;VALUE=DATE:20261029\r\nDTEND;VALUE=DATE:20261105\r\n"
    b"SUMMARY:Greece\r\n"
    b"URL:https://www.lidl.co.uk/c/flavour-of-the-week-greece/a10092213\r\n"
    b"END:VEVENT\r\nEND:VCALENDAR\r\n")


class TestMergeWithPublished(unittest.TestCase):
    """Published weeks survive; only new offers are added."""

    PICK = {"title": "Pick of the Week", "start": D(2026, 11, 5),
            "href": "https://www.lidl.co.uk/c/store/pick-of-the-week/a10089584",
            "food": True}
    FLAVOUR = {"title": "Flavour of the Week: Greece", "start": D(2026, 11, 12),
               "href": "https://www.lidl.co.uk/c/flavour-of-the-week-greece/a2",
               "food": True}

    def run_main(self, outdir, events=None, error=None):
        scrape = mock.patch.object(lidl_ics, "scrape",
                                   return_value=events,
                                   side_effect=error)
        argv = mock.patch.object(sys, "argv",
                                 ["lidl_ics.py", "--outdir", outdir])
        with scrape, argv, contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            return lidl_ics.main()

    def seed(self, d):
        path = os.path.join(d, "flavour.ics")
        with open(path, "wb") as f:
            f.write(PUBLISHED_FLAVOUR)
        return path

    def read(self, path):
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    def test_week_without_the_promo_keeps_published_weeks(self):
        # Lidl's Christmas weeks have no flavour tile. That is not an error and
        # must not delete the last theme the feed published.
        with tempfile.TemporaryDirectory() as d:
            path = self.seed(d)
            rc = self.run_main(d, [self.PICK])
            body = self.read(path)
        self.assertEqual(rc, 0)
        self.assertIn("SUMMARY:Greece", body)
        self.assertEqual(body.encode(), PUBLISHED_FLAVOUR)

    def test_new_promo_is_added_beside_the_published_one(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.seed(d)
            self.assertEqual(self.run_main(d, [self.PICK, self.FLAVOUR]), 0)
            body = self.read(path)
        self.assertIn("SUMMARY:Greece", body)
        self.assertIn("DTSTART;VALUE=DATE:20261112", body)
        # The old event keeps its own DTSTAMP: an unchanged week commits nothing.
        self.assertIn("DTSTAMP:20261029T171739Z", body)

    def test_fetch_failure_leaves_published_feeds_alone(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.seed(d)
            with self.assertRaises(SystemExit):
                self.run_main(d, error=SystemExit("No tiles parsed"))
            body = self.read(path)
        self.assertEqual(body.encode(), PUBLISHED_FLAVOUR)


if __name__ == "__main__":
    unittest.main(verbosity=2)
