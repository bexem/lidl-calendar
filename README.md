# Lidl GB offers calendar

Subscribable calendar of Lidl GB's themed offer weeks — "Flavour of the Week:
The Alps", The Wine Edit, Halloween, DIY, and so on.

Lidl publishes no calendar feed. This scrapes the marketing tiles from
[lidl.co.uk](https://www.lidl.co.uk/) once a week and regenerates three `.ics`
files you can subscribe to.

## Subscribe

| Calendar | URL |
|---|---|
| Everything | `https://raw.githubusercontent.com/bexem/lidl-calendar/main/all.ics` |
| Food only | `https://raw.githubusercontent.com/bexem/lidl-calendar/main/food.ics` |
| Non-food only | `https://raw.githubusercontent.com/bexem/lidl-calendar/main/nonfood.ics` |

In Google Calendar: **Other calendars → From URL**, paste the link. In Apple
Calendar: **Add Calendar Subscription**, paste the link. Both accept the plain
`https://` URL; `webcal://` in place of `https://` also works.

`DTEND` is always 7 days after `DTSTART` — Lidl publishes no end date, but its
offers all run Thursday to Wednesday.

## How it works

```
lidl_ics.py            scraper, stdlib only, no dependencies
.github/workflows/     runs Thursdays 07:30 UTC, commits only if changed
food.ics nonfood.ics   generated, do not hand-edit
all.ics
```

Run it locally:

```bash
python3 lidl_ics.py --outdir .
```

## Notes

- The food/non-food split is a keyword match on the theme title
  (`FOOD` in `lidl_ics.py`). An unrecognised theme lands in non-food rather
  than vanishing.
- Lidl's dates carry no year. The scraper searches ±1 year within a
  −21/+60 day window, so stale tiles are dropped instead of rolling into the
  wrong year.
- If Lidl changes their markup the scraper exits non-zero rather than writing
  an empty calendar, so a silent breakage can't wipe your feed.

## Legal

Not affiliated with, endorsed by, or connected to Lidl. All offers and prices
belong to Lidl Great Britain Limited. This project reads publicly-served
homepage HTML; `lidl.co.uk/robots.txt` does not disallow it, and the site
publishes no terms of use covering automated access.

Scraping a website's terms is your own responsibility — check them yourself
before subscribing to anything.

## Not affiliated with Lidl

Lidl is a trademark of Lidl Stiftung & Co. KG. See
[lidl.co.uk/legal-information](https://www.lidl.co.uk/c/legal-information/s10022935).
