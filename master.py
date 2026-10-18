"""The master data set: one row per parcel across every source, with the fields a deal analyzer needs.

fetch_all.py calls build() on every run, so any source added to sources/ lands in the master files automatically.
Writes:
    data/master_parcels.csv    every parcel (spreadsheet-ready)
    data/master_counties.csv   every county with its rules, links and next sale
    data/master.json           the parcel rows as {"columns": [...], "rows": [[...]]} for the deal analyzer page
"""
import csv
import json
import os
import re
import statistics

from states import STATE_BY_ABBR, SYSTEM_LABELS

PARCEL_COLUMNS = [
    "fips", "county", "state", "system", "saleKind", "source", "auctionDate", "auctionStatus", "auctionLabel",
    "parcel", "caseNo", "lot", "address", "fullAddress", "area", "owner", "buyer", "type", "status",
    "minBid", "winningBid", "multiple", "excess", "value", "bidToValue", "winToValue", "judgment", "taxes",
    "acres", "sqft", "yearBuilt", "years", "lat", "lon", "googleMaps", "streetView", "photo", "photoCredit",
    "listing", "sourceDoc", "countyPage", "redemptionMonths", "rate", "countyMedianMultiple", "dealScore", "dealRating", "desc",
]

COUNTY_COLUMNS = [
    "fips", "county", "state", "unit", "system", "whoHoldsSale", "nextSale", "nextSaleBasis", "lastSale", "taxSalePage", "officialSite",
    "sheriffSalePage", "assessorPage", "treasurerPage", "excessFundsPage", "parcelLookup", "platform", "population", "landSqMi", "lat", "lon",
    "auctionsOnFile", "parcelsOnFile", "soldOnFile", "withPriceOnFile", "dataSource", "redemption", "redemptionMonths", "rateOrPenalty",
    "saleTiming", "bidding", "foreclosure", "statute",
]

IMPROVED = re.compile(r"home|house|residential|single|condo|town|duplex|multi|commercial|building|improved|cottage|apartment|office|retail|industrial|warehouse", re.I)
MOBILE = re.compile(r"mobile|manufactured", re.I)
LAND = re.compile(r"acre|land|lot|vacant|agricult|farm|timber|parcel", re.I)


def street_view(p):
    sv = p.get("sv")
    if sv and len(sv) >= 2:
        la, lo = sv[0], sv[1]
        rad = min(300, max(100, (sv[3] if len(sv) > 3 and sv[3] else 0) + 60))
    elif p.get("lat") and p.get("lon"):
        la, lo, rad = p["lat"], p["lon"], 150
    else:
        return None
    return f"https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d{la:.6f}!2d{lo:.6f}!5f1!6d{rad}!7e1"


def google_maps(p, county, state_name):
    if p.get("lat") and p.get("lon"):
        return f"https://www.google.com/maps?q={p['lat']},{p['lon']}"
    addr = p.get("fullAddress") or p.get("address")
    if addr:
        q = addr if p.get("fullAddress") else f"{addr}, {county}, {state_name}"
        return "https://www.google.com/maps/search/" + q.replace(" ", "+")
    return None


def rating(score):
    return "Strong" if score >= 70 else "Good" if score >= 50 else "Fair" if score >= 35 else "Weak"


def deal_score(p, st, upcoming, county_mult):
    """0 to 100 screening score: value 40, property 20, competition 15, timing and redemption 15, data 10."""
    v, b = p.get("value"), p.get("minBid")
    if v and b is not None and v > 0:
        ratio = b / v
        s = 40 * max(0.0, min(1.0, 1 - ratio / 0.5))
    elif b is not None:
        s = 25 if b < 2000 else 18 if b < 10000 else 10 if b < 50000 else 5
    else:
        s = 10
    t = p.get("type") or ""
    if IMPROVED.search(t) or (p.get("sqft") or 0) > 0 or (p.get("yearBuilt") or 0) > 0:
        s += 20
    elif MOBILE.search(t):
        s += 14
    elif LAND.search(t):
        s += 8
    else:
        s += 10
    m = county_mult
    s += 8 if m is None else 15 if m <= 1.2 else 11 if m <= 2 else 7 if m <= 4 else 3
    s += 7 if upcoming else 0
    rm = st.get("redemption_months") or 0
    s += 8 if rm == 0 else 6 if rm <= 6 else 4 if rm <= 12 else 2 if rm <= 24 else 1
    s += (4 if p.get("lat") and p.get("lon") else 0) + (3 if v else 0) + (3 if p.get("photo") or p.get("sv") else 0)
    return int(round(min(100, s)))


def num(v):
    return v if isinstance(v, (int, float)) and v == v else None


def build(counties, records, data_dir):
    by_fips = {c["fips"]: c for c in counties}
    rows = []
    for fips, rec in records.items():
        c = by_fips.get(fips)
        if not c:
            continue
        st = STATE_BY_ABBR[c["state"]]
        sold_mults = [p["winningBid"] / p["minBid"] for a in rec.get("auctions", []) for p in a.get("parcels", []) if p.get("winningBid") and p.get("minBid")]
        cmult = round(statistics.median(sold_mults), 2) if sold_mults else None
        for a in rec.get("auctions", []):
            upcoming = a.get("status") == "upcoming"
            for p in a.get("parcels", []):
                mb, wb, v = num(p.get("minBid")), num(p.get("winningBid")), num(p.get("value"))
                score = deal_score(p, st, upcoming, cmult)
                rows.append([
                    fips, c["label"], c["state"], SYSTEM_LABELS[st["system"]], a.get("saleKind") or a.get("kind"), rec.get("source"), a.get("date"), a.get("status"), a.get("label"),
                    p.get("parcel"), p.get("caseNo"), p.get("lot"), p.get("address"), p.get("fullAddress"), p.get("area"), p.get("owner"), p.get("buyer"), p.get("type"), p.get("status"),
                    mb, wb, round(wb / mb, 2) if wb and mb else None, num(p.get("excess")), v,
                    round(mb / v, 3) if mb is not None and v else None, round(wb / v, 3) if wb and v else None, num(p.get("judgment")), num(p.get("taxes")),
                    num(p.get("acres")), num(p.get("sqft")), p.get("yearBuilt") or None, p.get("years"), num(p.get("lat")), num(p.get("lon")),
                    google_maps(p, c["label"], st["name"]), street_view(p), p.get("photo"), p.get("photoCredit"),
                    p.get("link"), a.get("source"), c.get("taxsale"), st.get("redemption_months"), st.get("rate"), cmult, score, rating(score), (p.get("desc") or "")[:300] or None,
                ])
    rows.sort(key=lambda r: (r[2], r[1], r[6] or "", r[9] or ""))

    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "master_parcels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(PARCEL_COLUMNS)
        for r in rows:
            w.writerow(["" if x is None else x for x in r])
    # the analyzer page derives map and Street View links itself, so the JSON leaves out the long URL columns
    keep = [i for i, c in enumerate(PARCEL_COLUMNS) if c not in ("googleMaps", "streetView", "desc")]
    with open(os.path.join(data_dir, "master.json"), "w", encoding="utf-8") as f:
        json.dump({"columns": [PARCEL_COLUMNS[i] for i in keep], "rows": [[r[i] for i in keep] for r in rows]}, f, ensure_ascii=False, separators=(",", ":"))

    with open(os.path.join(data_dir, "master_counties.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COUNTY_COLUMNS)
        for c in counties:
            st = STATE_BY_ABBR[c["state"]]
            d = c.get("data") or {}
            w.writerow(["" if x is None else x for x in [
                c["fips"], c["label"], c["state"], c["unit"], SYSTEM_LABELS[st["system"]], c.get("run") or st["conducted_by"], c.get("nextSale") or c.get("nextSaleLabel"), c.get("nextSaleKind"), c.get("lastSale"),
                c.get("taxsale"), c.get("site"), c.get("sheriffSale"), c.get("assessor"), c.get("treasurer"), c.get("excess"), c.get("parcelLookup"), c.get("platform"), c.get("pop"), c.get("landSqmi"), c.get("lat"), c.get("lon"),
                d.get("auctions"), d.get("parcels"), d.get("sold"), d.get("withPrice"), d.get("source"), st["redemption"], st.get("redemption_months"), st["rate"],
                st["sale_timing"], st["bidding"], st["foreclosure"], st["statute"],
            ]])
    return len(rows)
