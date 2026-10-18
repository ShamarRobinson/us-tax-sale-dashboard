#!/usr/bin/env python3
"""Collect RealAuction portal data from an ordinary connection and fold it into the tracker.

The RealAuction portals (Florida Clerk tax deed and foreclosure sales, Arizona and Colorado tax deed sales, Ohio and
Texas sheriff sales; the full roster is realauction.SITES) answer data-center addresses (GitHub's runners included) with a
marketing page instead of the auction calendar. Run this on a home or office machine instead, then commit what it wrote:

    python3 collect_local.py                      # every county with a portal (slow: hundreds of sites)
    python3 collect_local.py --state FL           # one state
    python3 collect_local.py --county duval,orange,hillsborough   # a few counties by name (any state)
    python3 collect_local.py --import             # fold browser dumps in data/raw/realauction/*.json into county files

Either way the script writes data/counties/<fips>.json, rebuilds the registry, index, master CSV and calendar with
fetch_all.py --offline, and prints the git commands that publish the result. The monthly GitHub Actions refresh keeps
these county files whenever the portals refuse the runner, so what you collect stays on the site until you collect again.

Browser dumps come from tools/realauction_console.js (run in a browser tab on a portal; it leaves window.__ra holding
{base, kind, fips, auctions}). Save that object as data/raw/realauction/<fips>-<kind>.json and run --import.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from registry import build_counties  # noqa: E402
from sources import realauction  # noqa: E402

COUNTY_DIR = os.path.join(HERE, "data", "counties")
RAW_DIR = os.path.join(HERE, "data", "raw", "realauction")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def info_for(kind, state, base):
    return realauction.info_for(kind, state, base)


def merge(fips, county, kind, base, auctions, checked):
    """Replace this portal's auctions in the county file, keeping auctions from the county's other portals and from
    other adapters (fetch_all.py tags each auction with its adapter as `src`)."""
    path = os.path.join(COUNTY_DIR, f"{fips}.json")
    rec = load_json(path) if os.path.exists(path) else None
    if not rec:
        rec = dict(fips=fips, source=realauction.NAME, sourceUrl=base, lastChecked=checked, lastChanged=None, info={}, auctions=[])
    realauction.clean_auctions(auctions, kind)
    for a in auctions:
        a["src"] = realauction.NAME
    kept = [a for a in rec.get("auctions", []) if (a.get("src") or rec.get("source")) != realauction.NAME or (a.get("portal") or a.get("saleKind")) != kind]
    new = sorted(kept + auctions, key=lambda a: a.get("date") or "", reverse=True)
    before = json.dumps(rec.get("auctions", []), sort_keys=True)
    rec.update(name=county["name"], state=county["state"], lastChecked=checked, auctions=new,
               sources=sorted(set(rec.get("sources") or [rec.get("source")]) | {realauction.NAME}))
    if json.dumps(new, sort_keys=True) != before:
        rec["lastChanged"] = checked
    info = rec.setdefault("info", {})
    new_info = info_for(kind, county["state"], base)
    if kind != "foreclosure" or "page" not in info:
        info.update(new_info)
    os.makedirs(COUNTY_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, separators=(",", ":"))
    return len(auctions), sum(len(a.get("parcels") or []) for a in auctions)


def import_raw(by_fips, checked):
    n = 0
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*.json"))):
        raw = load_json(path)
        if not raw or "auctions" not in raw:
            print(f"  skipped {os.path.basename(path)}: not a collector dump")
            continue
        fips = str(raw.get("fips") or os.path.basename(path).split("-")[0])
        kind = raw.get("kind") or (os.path.basename(path).split("-")[1].split(".")[0] if "-" in os.path.basename(path) else "taxdeed")
        c = by_fips.get(fips)
        if not c:
            print(f"  skipped {os.path.basename(path)}: unknown FIPS {fips}")
            continue
        aucs, parcels = merge(fips, c, kind, raw.get("base") or "", raw["auctions"], raw.get("collected") or checked)
        print(f"  {c['label']}, {c['state']} {kind}: {aucs} sale days, {parcels} items")
        n += 1
    return n


def collect(counties, checked):
    n = 0
    for fips, kind, base in realauction.sites_for(counties):
        c = next(x for x in counties if x["fips"] == fips)
        got = realauction.fetch([c])
        rec = got.get(fips)
        aucs = [a for a in (rec or {}).get("auctions", []) if (a.get("portal") or a.get("saleKind")) == kind]
        if not aucs:
            continue
        merge(fips, c, kind, base, aucs, checked)
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", help="two-letter state, e.g. FL")
    ap.add_argument("--county", help="comma-separated county names, e.g. duval,orange")
    ap.add_argument("--import", dest="do_import", action="store_true", help="import browser dumps from data/raw/realauction/")
    ap.add_argument("--no-rebuild", action="store_true", help="skip fetch_all.py --offline afterwards")
    a = ap.parse_args()
    counties = build_counties()
    by_fips = {c["fips"]: c for c in counties}
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if a.do_import:
        n = import_raw(by_fips, checked)
        print(f"imported {n} dump(s)")
    else:
        wanted = [c for c in counties if c["state"] in ("AZ", "CO", "FL", "NJ", "OH", "TX")]
        if a.state:
            wanted = [c for c in wanted if c["state"] == a.state.upper()]
        if a.county:
            names = {re.sub(r"[^a-z0-9]", "", x.lower()) for x in a.county.split(",")}
            wanted = [c for c in wanted if re.sub(r"[^a-z0-9]", "", c["name"].lower()) in names]
        print(f"collecting {len(wanted)} counties from their portals ...")
        n = collect(wanted, checked)
        print(f"updated {n} portal(s)")
    if not a.no_rebuild:
        subprocess.run([sys.executable, os.path.join(HERE, "fetch_all.py"), "--offline"], check=False)
    print("\nPublish with:\n  git add data && git commit -m 'Collect RealAuction portal data' && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
