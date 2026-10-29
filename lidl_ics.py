#!/usr/bin/env python3
"""Scrape Lidl GB's themed offer weeks from the homepage and emit .ics calendars.

Lidl publishes no feed. The homepage marketing tiles are the only structured
source: each <div class="ABaseContentTile ..."> carries headline="<theme>" and
subheadline="From Thursday, 08/10". Dates have no year, so we infer it.

Usage: python3 lidl_ics.py [--domain www.lidl.co.uk] [--outdir .]
"""
import argparse
import datetime as dt
import html
import re
import sys
import urllib.parse
import urllib.request

# ponytail: keyword match for the food/non-food split. A theme we have never
# seen lands in nonfood rather than disappearing. Add a keyword only when a
# title is genuinely misfiled.
FOOD = re.compile(
    r"flavour|flavor|wine|pick of the week|lidl plus|kitchen|household|"
    r"health|wellness|food|sweet|drink|snack|bakery|fresh", re.I)

# Lidl names this promo inconsistently: "Flavour of the Week: The Alps" and
# "Flavour of the Week Sol and Mar" both occur, sometimes with stray spaces.
FLAVOUR = re.compile(r"flavour of the week|flavor of the week", re.I)

# Lidl's separator after the prefix drifts (": The Alps", " - Greece", or a
# plain space in "Flavour of the Week Sol and Mar"), so do not enumerate them:
# drop everything up to the first alphanumeric character instead. That survives
# separators nobody has seen yet ("|", "•"), and \w is Unicode-aware, so an
# accented theme ("- Österreich") keeps its first letter. Digits stop the strip
# too ("Flavour of the Week: 24 Christmas Puddings").
FLAVOUR_PREFIX = re.compile(r"^\s*flavou?r of the week\b[^\w]*", re.I)

# Season tiles carry the year in brackets: "The Alps (2026)", "The Alps (2025/26)".
# That reads as noise in a calendar entry, so it is dropped. A bracketed phrase
# that is not a year ("Summer (BBQ)") is kept - only date-like content goes.
YEARLIKE = re.compile(r"^\s*\d{2,4}(?:\s*[/\u2013\u2014-]\s*\d{2,4})?\s*$")
TRAILING_BRACKET = re.compile(r"\s*[(\[{]([^()\[\]{}]*)[)\]}]$")


def _drop_trailing_year(theme):
    m = TRAILING_BRACKET.search(theme)
    if m and YEARLIKE.match(m.group(1)):
        return theme[:m.start()].strip()
    return theme


def strip_flavour_prefix(title):
    """'Flavour of the Week - Greece' -> 'Greece'; unrelated titles untouched."""
    if not FLAVOUR.search(title):
        return title
    theme = _drop_trailing_year(FLAVOUR_PREFIX.sub("", title).strip())
    # Lidl sometimes wraps the theme: "Flavour of the Week (Greece)". The
    # separator strip eats the opening bracket but not its partner, so drop the
    # now-dangling closer rather than emitting "Greece)".
    opener = {")": "(", "]": "[", "}": "{"}.get(theme[-1:])
    if opener and theme.count(theme[-1:]) > theme.count(opener):
        theme = theme[:-1].strip()
    # A bare "Flavour of the Week" has no theme left; keep the original title
    # rather than emitting an empty SUMMARY.
    return theme or title

# Lidl advertises at most ~8 weeks ahead and leaves stale tiles on the homepage.
WINDOW_PAST, WINDOW_FUTURE = 21, 60
UA = "Mozilla/5.0 (compatible; lidl-calendar/1.0; +https://github.com/)"


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 200:
            raise SystemExit(f"HTTP {r.status} from {url}")
        return r.read().decode("utf-8", "replace")


def attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    if not m:
        return None
    return html.unescape(m.group(1)).strip()


def parse_date(text, today):
    """'From Thursday, 08/10' has no year. Search y-1..y+1 inside the window.

    Forward-only search misses a Christmas offer still on the page in early
    January; no window at all lets a stale 30/07 become next year.
    """
    m = re.search(r"(\d{1,2})/(\d{1,2})", text or "")
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    best = None
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            cand = dt.date(year, month, day)
        except ValueError:      # 31/02
            continue
        if not -WINDOW_PAST <= (cand - today).days <= WINDOW_FUTURE:
            continue
        if best is None or cand > best:
            best = cand
    return best


def scrape(domain, today):
    page = fetch(f"https://{domain}/")
    seen, events = set(), []
    for tag in re.findall(r'<div class="ABaseContentTile[^"]*"[^>]*>', page):
        title = attr(tag, "headline")
        start = parse_date(attr(tag, "subheadline"), today)
        if not title or not start:
            continue
        href = attr(tag, "href") or ""
        if not href.startswith("http"):
            href = f"https://{domain}{href}"
        key = (title, start)
        if key in seen:          # same promo shows in "This week" and "Coming up"
            continue
        seen.add(key)
        events.append({"title": title, "start": start, "href": href,
                       "food": bool(FOOD.search(title))})
    if not events:
        raise SystemExit("No tiles parsed - Lidl changed their markup. "
                         "Check <div class=\"ABaseContentTile\"> before deploying.")
    return events


def esc(v):
    return (v.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


def ics(events, name, now):
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//lidl-calendar//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{esc(name)}"]
    for e in sorted(events, key=lambda x: x["start"]):
        end = e["start"] + dt.timedelta(days=7)   # Lidl offers run one week
        out += ["BEGIN:VEVENT",
                f"UID:{urllib.parse.quote(e['href'])}@lidl-calendar",
                f"DTSTAMP:{now}", f"DTSTART;VALUE=DATE:{e['start']:%Y%m%d}",
                f"DTEND;VALUE=DATE:{end:%Y%m%d}", f"SUMMARY:{esc(e['title'])}",
                f"DESCRIPTION:{esc('Lidl GB special week. See: ' + e['href'])}",
                f"URL:{e['href']}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    # RFC 5545 mandates CRLF. Write in binary so no platform translates it.
    return ("\r\n".join(out) + "\r\n").encode("utf-8")


def calendar_sets(events):
    """Split scraped events into the four calendars, stripping flavour prefixes.

    Pure so the wiring is testable without the network: the earlier bug was a
    correct regex that main() never called.
    """
    sets = {"food": [e for e in events if e["food"]],
            "nonfood": [e for e in events if not e["food"]],
            "all": events}
    # ponytail: flavour.ics drops the "Flavour of the Week" prefix so the
    # theme reads clean in a calendar ("The Alps", not "Flavour of the Week:
    # The Alps"). The prefix is kept in food/all, where it is the only thing
    # distinguishing one Lidl promo from another.
    sets["flavour"] = [dict(e, title=strip_flavour_prefix(e["title"]))
                       for e in events if FLAVOUR.search(e["title"])]
    return sets


def missing_sets(sets):
    """Calendars with no offers: their .ics on disk is stale, not "unchanged"."""
    return [name for name, evs in sets.items() if not evs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="www.lidl.co.uk")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--today", help="override date for testing (YYYY-MM-DD)")
    args = ap.parse_args()

    today = (dt.date.fromisoformat(args.today) if args.today
             else dt.datetime.now(dt.timezone.utc).date())
    events = scrape(args.domain, today)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    sets = calendar_sets(events)
    missing = missing_sets(sets)
    for name, evs in sets.items():
        if name in missing:
            # An empty set is not "nothing to do": the .ics already on disk is
            # now stale and subscribers keep being served last week's offers.
            print(f"warning: {name}.ics not written - no matching offers",
                  file=sys.stderr)
            continue
        with open(f"{args.outdir}/{name}.ics", "wb") as f:
            f.write(ics(evs, f"Lidl GB {name}", stamp))
        print(f"{name}.ics: {len(evs)} events")
    for e in sorted(events, key=lambda x: x["start"]):
        print(f"  {e['start']}  {e['title']}")
    # flavour.ics is the point of this repo. If Lidl renames or drops the promo
    # tile, no scrape of the other calendars should look like success. Exit
    # non-zero only after the other files are written, so a flavour breakage
    # does not freeze food/nonfood/all as well.
    if "flavour" in missing:
        print("error: no Flavour of the Week offer scraped; flavour.ics left stale",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
