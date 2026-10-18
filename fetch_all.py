"""Build every data file the dashboard reads.

    python3 fetch_all.py            refresh everything (sources that fail keep their last saved data)
    python3 fetch_all.py --offline  rebuild the registry from local reference files without calling any source

Writes:
    data/registry.json        every county with its state rules, links, next sale and data summary
    data/index.json           national summary: counts, upcoming sales, per-state totals
    data/counties/{fips}.json auctions and parcels for every county a source covers
"""
import calendar
import datetime as dt
import importlib
import json
import os
import sys

import master
import sources
from registry import build_counties
from states import STATES, STATE_BY_ABBR, SYSTEM_LABELS

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
COUNTY_DIR = os.path.join(DATA, "counties")
TODAY = dt.date.today()


# ---------- statutory sale dates ----------

def nth_weekday(year, month, n, weekday):
    first = dt.date(year, month, 1)
    off = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=off + 7 * (n - 1))


def last_weekday(year, month, weekday):
    last = dt.date(year, month, calendar.monthrange(year, month)[1])
    off = (last.weekday() - weekday) % 7
    return last - dt.timedelta(days=off)


def shift_holiday(d):
    """Georgia and Texas move a first-Tuesday sale that lands on New Year's Day or July 4 to the next day."""
    if (d.month, d.day) in ((1, 1), (7, 4)):
        return d + dt.timedelta(days=1)
    return d


def next_statutory(rule):
    """Return (date or None, label) for the next sale a state's statute fixes."""
    t = rule.get("type")
    if t == "monthly_nth_weekday":
        y, m = TODAY.year, TODAY.month
        for _ in range(3):
            d = shift_holiday(nth_weekday(y, m, rule["n"], rule["weekday"]))
            if d >= TODAY:
                return d.isoformat(), d.strftime("%B %-d, %Y")
            m += 1
            if m > 12:
                m, y = 1, y + 1
    if t in ("annual_nth_weekday", "annual_last_weekday"):
        for y in (TODAY.year, TODAY.year + 1):
            d = nth_weekday(y, rule["month"], rule["n"], rule["weekday"]) if t == "annual_nth_weekday" else last_weekday(y, rule["month"], rule["weekday"])
            if d >= TODAY:
                return d.isoformat(), d.strftime("%B %-d, %Y")
    if t == "window":
        months = rule["months"]
        names = [calendar.month_abbr[m] for m in months]
        if TODAY.month in months:
            end = months[-1]
            end_year = TODAY.year if end >= TODAY.month or months[0] <= months[-1] else TODAY.year + 1
            return None, f"Sale season open (through {calendar.month_name[end]} {end_year})"
        # next start month
        start = months[0]
        y = TODAY.year if start > TODAY.month else TODAY.year + 1
        return None, f"{names[0]} to {names[-1]} {y}" if len(months) > 1 else f"{calendar.month_name[start]} {y}"
    return None, None


# ---------- helpers ----------

def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def dump(path, obj, compact=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)


def summarize(rec):
    """Counts the dashboard shows in the county table."""
    aucs = rec.get("auctions", [])
    parcels = sum(len(a.get("parcels", [])) for a in aucs)
    sold = sum(1 for a in aucs for p in a.get("parcels", []) if p.get("status") == "Sold")
    priced = sum(1 for a in aucs for p in a.get("parcels", []) if p.get("winningBid"))
    photos = sum(1 for a in aucs for p in a.get("parcels", []) if p.get("photo"))
    dates = sorted(a["date"] for a in aucs if a.get("date"))
    upcoming = [d for d in dates if d >= TODAY.isoformat()]
    past = [d for d in dates if d < TODAY.isoformat()]
    return dict(auctions=len(aucs), parcels=parcels, sold=sold, withPrice=priced, photos=photos,
                nextSale=upcoming[0] if upcoming else None, lastSale=past[-1] if past else None,
                source=rec.get("source"), lastChecked=rec.get("lastChecked"))


# ---------- main ----------

def write_ics(path, events, name):
    """Minimal iCalendar file of all-day events."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    def esc(v):
        v = str(v or "")
        v = v.replace(chr(92), chr(92) * 2).replace(chr(10), chr(92) + "n")
        return v.replace(",", chr(92) + ",").replace(";", chr(92) + ";")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//US Tax Sale Tracker//EN", f"X-WR-CALNAME:{esc(name)}"]
    for ev in events:
        d = dt.date.fromisoformat(ev["date"])
        lines += ["BEGIN:VEVENT", f"UID:{esc(ev['uid'])}@ustaxsale", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{esc(ev['title'])}", f"DESCRIPTION:{esc(ev.get('desc'))}", f"URL:{esc(ev.get('url'))}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))


def main(offline=False):
    previous = load_json(os.path.join(DATA, "index.json")) or {}
    counties = build_counties()
    by_fips = {c["fips"]: c for c in counties}
    print(f"{len(counties)} counties in the registry")

    # statutory dates per state
    statutory = {}
    for s in STATES:
        statutory[s["abbr"]] = next_statutory(s.get("sale_rule") or {})

    # run every source; keep the previous file for any county a source fails on
    records = {}
    source_status = {}
    if offline:  # keep the last run's source status so the dashboard footer stays accurate
        source_status = (load_json(os.path.join(DATA, "index.json")) or {}).get("sources", {})
    for name in ([] if offline else sources.ADAPTERS):
        mod = importlib.import_module(f"sources.{name}")
        print(f"Fetching {mod.LABEL} ...")
        try:
            got = mod.fetch(counties)
            records.update(got)
            source_status[name] = dict(label=mod.LABEL, url=mod.HOMEPAGE, counties=len(got), ok=True, checked=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
            print(f"  {len(got)} counties")
        except Exception as e:
            source_status[name] = dict(label=mod.LABEL, url=mod.HOMEPAGE, counties=0, ok=False, error=str(e)[:300])
            print(f"  FAILED: {e}")

    # previously saved county files fill in for sources that failed this run
    kept = 0
    if os.path.isdir(COUNTY_DIR):
        for fn in os.listdir(COUNTY_DIR):
            fips = fn[:-5]
            if fn.endswith(".json") and fips not in records and fips in by_fips:
                old = load_json(os.path.join(COUNTY_DIR, fn))
                if old:
                    records[fips] = old
                    kept += 1
    if kept:
        print(f"kept {kept} county files from the previous run")

    # the footer counts what is on file per source, so counties collected in a browser (collect_local.py) count too
    for name in sources.ADAPTERS:
        n = sum(1 for r in records.values() if r.get("source") == name)
        st = source_status.get(name)
        if st is None:
            mod = importlib.import_module(f"sources.{name}")
            st = source_status[name] = dict(label=mod.LABEL, url=mod.HOMEPAGE, counties=0, ok=False)
        if n:
            st.update(counties=n, ok=True)

    # write county files and fold summaries into the registry
    for fips, rec in records.items():
        c = by_fips.get(fips)
        if not c:
            continue
        rec["name"] = c["name"]
        rec["state"] = c["state"]
        dump(os.path.join(COUNTY_DIR, f"{fips}.json"), rec)
        info = rec.get("info", {})
        if info.get("page"):
            c["taxsale"] = info["page"]
            c["taxsaleKind"] = "county"
        if info.get("run"):
            c["run"] = info["run"]
        if info.get("note"):
            c["note"] = info["note"]
        if info.get("schedule"):
            c["schedule"] = info["schedule"]
        if info.get("excess"):
            c["excess"] = info["excess"]
        if info.get("parcel"):
            c["parcelLookup"] = info["parcel"]
        c["data"] = summarize(rec)

    # links found by discover_links.py on each county's own website
    found = load_json(os.path.join(HERE, "ref", "discovered_links.json")) or {}
    crawled = 0
    for c in counties:
        f = found.get(c["fips"]) or {}
        if f.get("error"):
            continue
        if f.get("taxsale") and not c.get("taxsale"):
            c["taxsale"], c["taxsaleKind"] = f["taxsale"], "crawl"
        for src, dst in (("sheriff", "sheriffSale"), ("assessor", "assessor"), ("treasurer", "treasurer"), ("excess", "excess")):
            if f.get(src) and not c.get(dst):
                c[dst] = f[src]
        if f.get("checked"):
            crawled += 1
    if crawled:
        print(f"merged crawled links for {crawled} counties")

    # next sale for every county: posted date beats the statutory one
    for c in counties:
        d = c.get("data") or {}
        sd, slabel = statutory.get(c["state"], (None, None))
        if d.get("nextSale"):
            c["nextSale"], c["nextSaleKind"] = d["nextSale"], "posted"
        elif sd:
            c["nextSale"], c["nextSaleKind"] = sd, "statutory"
        elif slabel:
            c["nextSaleLabel"], c["nextSaleKind"] = slabel, "window"
        if d.get("lastSale"):
            c["lastSale"] = d["lastSale"]

    for c in counties:
        c["coverage"] = sum([1, bool(c.get("site")), bool(c.get("taxsale")), bool(c.get("data")), bool(c.get("data") and c["data"].get("photos"))])

    # drop empty keys to keep the registry small
    slim = []
    for c in counties:
        slim.append({k: v for k, v in c.items() if v not in (None, "", {}, [])})

    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    states_out = []
    for s in STATES:
        cs = [c for c in counties if c["state"] == s["abbr"]]
        with_data = [c for c in cs if c.get("data")]
        sd, slabel = statutory[s["abbr"]]
        states_out.append({**{k: v for k, v in s.items() if k != "sale_rule"},
                           "systemLabel": SYSTEM_LABELS[s["system"]], "counties": len(cs), "withData": len(with_data),
                           "parcels": sum(c["data"]["parcels"] for c in with_data), "auctions": sum(c["data"]["auctions"] for c in with_data),
                           "pop": sum(c.get("pop") or 0 for c in cs), "nextStatutory": sd, "nextStatutoryLabel": slabel})

    dump(os.path.join(DATA, "registry.json"), dict(generated=generated, states=states_out, counties=slim))

    upcoming = sorted(
        [dict(fips=c["fips"], state=c["state"], name=c["label"], date=c["nextSale"], kind=c.get("nextSaleKind"),
              parcels=(c.get("data") or {}).get("parcels"), page=c.get("taxsale"))
         for c in counties if c.get("nextSaleKind") == "posted"],
        key=lambda x: x["date"])
    index = dict(
        generated=generated, counties=len(counties), states=len(STATES),
        withData=sum(1 for c in counties if c.get("data")),
        parcels=sum(c["data"]["parcels"] for c in counties if c.get("data")),
        auctions=sum(c["data"]["auctions"] for c in counties if c.get("data")),
        withTaxSaleLink=sum(1 for c in counties if c.get("taxsale")),
        withSite=sum(1 for c in counties if c.get("site")),
        withSheriffLink=sum(1 for c in counties if c.get("sheriffSale")),
        withAssessorLink=sum(1 for c in counties if c.get("assessor") or c.get("parcelLookup")),
        withPhotos=sum(1 for c in counties if c.get("data") and c["data"].get("photos")),
        photos=sum(c["data"].get("photos", 0) for c in counties if c.get("data")),
        systems={k: sum(1 for c in counties if STATE_BY_ABBR[c["state"]]["system"] == k) for k in SYSTEM_LABELS},
        upcomingPosted=upcoming[:200], sources=source_status,
    )
    dump(os.path.join(DATA, "index.json"), index, compact=False)

    # what changed since the previous refresh
    prev_up = {(u["fips"], u["date"]) for u in previous.get("upcomingPosted", [])}
    prev_with = set(previous.get("countiesWithData", []))
    now_with = sorted(c["fips"] for c in counties if c.get("data"))
    index["countiesWithData"] = now_with
    dump(os.path.join(DATA, "index.json"), index, compact=False)
    changes = dict(generated=generated, previous=previous.get("generated"),
                   newUpcoming=[u for u in upcoming if (u["fips"], u["date"]) not in prev_up],
                   newCounties=[f for f in now_with if f not in prev_with] if prev_with else [],
                   parcelDelta=(index["parcels"] - previous["parcels"]) if previous.get("parcels") is not None else 0,
                   linkDelta=(index["withTaxSaleLink"] - previous["withTaxSaleLink"]) if previous.get("withTaxSaleLink") is not None else 0)
    dump(os.path.join(DATA, "changes.json"), changes, compact=False)

    # calendar of every posted sale date plus each state's next statutory date
    site = "https://shamarrobinson.github.io/us-tax-sale-dashboard/"
    events = [dict(date=u["date"], uid=f"{u['fips']}-{u['date']}", title=f"{u['name']}, {u['state']}: tax sale ({u['parcels'] or 0} parcels on file)", desc=u.get("page") or "", url=f"{site}#c/{u['fips']}") for u in upcoming]
    for s in states_out:
        if s.get("nextStatutory"):
            events.append(dict(date=s["nextStatutory"], uid=f"{s['abbr']}-{s['nextStatutory']}", title=f"{s['name']}: statutory sale date ({s['sale_timing']})", desc=s["summary"], url=f"{site}#{s['abbr'].lower()}"))
    write_ics(os.path.join(DATA, "upcoming.ics"), sorted(events, key=lambda e: e["date"]), "US tax sales")

    n = master.build(counties, records, DATA)
    print(f"wrote data/master_parcels.csv and data/master.json ({n} parcels), data/master_counties.csv")
    print(f"wrote data/registry.json ({os.path.getsize(os.path.join(DATA, 'registry.json'))//1024} KB), "
          f"{index['withData']} counties with parcel data, {index['parcels']} parcels")


if __name__ == "__main__":
    main(offline="--offline" in sys.argv)
