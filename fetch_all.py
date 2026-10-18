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
    dates = sorted(a["date"] for a in aucs if a.get("date"))
    upcoming = [d for d in dates if d >= TODAY.isoformat()]
    past = [d for d in dates if d < TODAY.isoformat()]
    return dict(auctions=len(aucs), parcels=parcels, sold=sold, withPrice=priced,
                nextSale=upcoming[0] if upcoming else None, lastSale=past[-1] if past else None,
                source=rec.get("source"), lastChecked=rec.get("lastChecked"))


# ---------- main ----------

def main(offline=False):
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
        systems={k: sum(1 for c in counties if STATE_BY_ABBR[c["state"]]["system"] == k) for k in SYSTEM_LABELS},
        upcomingPosted=upcoming[:200], sources=source_status,
    )
    dump(os.path.join(DATA, "index.json"), index, compact=False)
    print(f"wrote data/registry.json ({os.path.getsize(os.path.join(DATA, 'registry.json'))//1024} KB), "
          f"{index['withData']} counties with parcel data, {index['parcels']} parcels")


if __name__ == "__main__":
    main(offline="--offline" in sys.argv)
