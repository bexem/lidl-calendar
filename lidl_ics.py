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

    sets = {"food": [e for e in events if e["food"]],
            "nonfood": [e for e in events if not e["food"]],
            "all": events}
    for name, evs in sets.items():
        if not evs:
            continue
        with open(f"{args.outdir}/{name}.ics", "wb") as f:
            f.write(ics(evs, f"Lidl GB {name}", stamp))
        print(f"{name}.ics: {len(evs)} events")
    for e in sorted(events, key=lambda x: x["start"]):
        print(f"  {e['start']}  {e['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
