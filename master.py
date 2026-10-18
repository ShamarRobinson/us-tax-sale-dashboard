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
    "acres", "sqft", "yearBuilt", "years", "yearsUnpaid", "tenure", "priorAuctions", "lat", "lon", "googleMaps", "streetView", "photo", "photoCredit",
    "listing", "sourceDoc", "parcelRecord", "countyMap", "countyPage", "redemptionMonths", "rate", "countyMedianMultiple", "dealScore", "dealRating", "typeDetail", "desc",
]

COUNTY_COLUMNS = [
    "fips", "county", "state", "unit", "system", "whoHoldsSale", "nextSale", "nextSaleBasis", "lastSale", "taxSalePage", "officialSite",
    "sheriffSalePage", "assessorPage", "treasurerPage", "excessFundsPage", "parcelLookup", "platform", "population", "landSqMi", "lat", "lon",
    "auctionsOnFile", "parcelsOnFile", "soldOnFile", "withPriceOnFile", "photosOnFile", "coverage", "dataSource", "redemption", "redemptionMonths", "rateOrPenalty", "penaltyPct", "penaltyStepPct",
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


CONDO = re.compile(r"condo|town ?ho|duplex", re.I)
MULTI = re.compile(r"multi|apartment|units|plex", re.I)
COMMERCIAL = re.compile(r"commercial|retail|office|industrial|warehouse|business|building(?!\s*lot)", re.I)
AGRI = re.compile(r"agric|farm|timber|conservation", re.I)
VACANT = re.compile(r"vacant|land|^lot\b|acre|waterfront lot|exempt|utility", re.I)
SFR = re.compile(r"single|home|house|cottage|residential|sfr|dwelling|water ?front home", re.I)


def type_cat(p):
    """Same classifier as common.js typeCat()."""
    t = str(p.get("type") or "")
    m = re.match(r"^\s*(\d+(?:\.\d+)?)", t)
    if m:
        code = float(m.group(1))
        if 10 <= code < 20: return "Vacant land"
        if 20 <= code < 21: return "Single-family home"
        if 21 <= code < 22 or 24 <= code < 25: return "Condo or townhouse"
        if 22 <= code < 24: return "Manufactured home"
        if 30 <= code < 40: return "Multi-family"
        if 40 <= code < 60: return "Commercial or industrial"
        return "Other or unknown"
    if MOBILE.search(t): return "Manufactured home"
    if CONDO.search(t): return "Condo or townhouse"
    if MULTI.search(t): return "Multi-family"
    if COMMERCIAL.search(t): return "Commercial or industrial"
    if AGRI.search(t): return "Agricultural"
    if VACANT.search(t): return "Vacant land"
    if SFR.search(t): return "Single-family home"
    if (p.get("sqft") or 0) > 0 or (p.get("yearBuilt") or 0) > 0: return "Single-family home"
    return "Other or unknown"


PT = {"Single-family home": 20, "Multi-family": 20, "Condo or townhouse": 16, "Commercial or industrial": 16, "Agricultural": 10, "Vacant land": 8, "Manufactured home": 6}


def deal_score(p, county, county_mult, priors):
    """0 to 100, the same formula as common.js dealScore(): value 40, property 20, market 15, competition 15, history 10."""
    cost = p.get("winningBid") or p.get("minBid") or None
    v = p.get("value")
    if v and v > 0 and cost:
        r = cost / v
        s = round(40 * max(0.0, min(1.0, (0.6 - r) / 0.55)))
    elif cost:
        s = 24 if cost < 2500 else 19 if cost < 10000 else 14 if cost < 25000 else 9 if cost < 75000 else 5
    else:
        s = 10
    cat = type_cat(p)
    ad = (p.get("address") or "").strip()
    mh = re.search(r"MH$|MOBILE|PERSONAL PROP", f"{p.get('parcel') or ''} {p.get('type') or ''} {p.get('desc') or ''}", re.I)
    t = PT.get(cat)
    if t is None:
        t = 3 if mh else 14 if re.match(r"^[1-9]\d*[A-Z]?\s+\S", ad) else 8 if re.match(r"^0\s", ad) else 10 if ad else 8
    s += t
    pop = county.get("pop") or 0
    s += 15 if pop >= 1e6 else 13 if pop >= 250000 else 11 if pop >= 100000 else 9 if pop >= 40000 else 6
    mult = (p["winningBid"] / p["minBid"]) if p.get("winningBid") and p.get("minBid") else county_mult
    s += 8 if not mult else 15 if mult <= 1.005 else 11 if mult < 2 else 7 if mult < 5 else 3
    n = len(priors)
    nb = any(x.get("status") == "No bid" for x in priors)
    s += 2 if nb else 10 if n == 0 else 6 if n == 1 else 3
    return int(min(100, s)), cat


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
        # earlier sales on file for the same parcel (one record per date, preferring the one with a price)
        by_key = {}
        for a in rec.get("auctions", []):
            for p in a.get("parcels", []):
                k = re.sub(r"\s+", " ", str(p.get("parcel") or p.get("lot") or p.get("caseNo") or "")).upper().strip()
                if k:
                    by_key.setdefault(k, {}).setdefault(a.get("date") or "", []).append((a.get("kind"), p))
        def priors_for(p, date):
            k = re.sub(r"\s+", " ", str(p.get("parcel") or p.get("lot") or p.get("caseNo") or "")).upper().strip()
            out = []
            for d, recs in by_key.get(k, {}).items():
                if d and date and d < date:
                    best = sorted(recs, key=lambda r: (bool(r[1].get("winningBid")), r[0] != "list"), reverse=True)[0][1]
                    out.append(best)
            return out
        for a in rec.get("auctions", []):
            upcoming = a.get("status") == "upcoming"
            for p in a.get("parcels", []):
                mb, wb, v = num(p.get("minBid")), num(p.get("winningBid")), num(p.get("value"))
                priors = priors_for(p, a.get("date"))
                score, cat = deal_score(p, c, cmult, priors)
                rows.append([
                    fips, c["label"], c["state"], SYSTEM_LABELS[st["system"]], a.get("saleKind") or a.get("kind"), rec.get("source"), a.get("date"), a.get("status"), a.get("label"),
                    p.get("parcel"), p.get("caseNo"), p.get("lot"), p.get("address"), p.get("fullAddress"), p.get("area"), p.get("owner"), p.get("buyer"), cat, p.get("status"),
                    mb, wb, round(wb / mb, 2) if wb and mb else None, num(p.get("excess")), v,
                    round(mb / v, 3) if mb is not None and v else None, round(wb / v, 3) if wb and v else None, num(p.get("judgment")), num(p.get("taxes")),
                    num(p.get("acres")), num(p.get("sqft")), p.get("yearBuilt") or None, p.get("years"), num(p.get("defaultYrs")) if p.get("defaultYrs") is not None else p.get("yearsUnpaid"), num(p.get("tenure")), len(priors), num(p.get("lat")), num(p.get("lon")),
                    google_maps(p, c["label"], st["name"]), street_view(p), p.get("photo"), p.get("photoCredit"),
                    p.get("link"), a.get("source"), p.get("parcelInfo"), p.get("parcelMap"), c.get("taxsale"), st.get("redemption_months"), st.get("rate"), cmult, score, rating(score), p.get("typeDetail") or (p.get("type") if p.get("type") != cat else None), (p.get("desc") or "")[:300] or None,
                ])
    rows.sort(key=lambda r: (r[2], r[1], r[6] or "", r[9] or ""))

    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "master_parcels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(PARCEL_COLUMNS)
        for r in rows:
            w.writerow(["" if x is None else x for x in r])
    # the analyzer page derives map and Street View links itself, so the JSON leaves out the long URL columns
    keep = [i for i, c in enumerate(PARCEL_COLUMNS) if c not in ("googleMaps", "streetView", "desc", "typeDetail")]
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
                d.get("auctions"), d.get("parcels"), d.get("sold"), d.get("withPrice"), d.get("photos"), c.get("coverage"), d.get("source"), st["redemption"], st.get("redemption_months"), st["rate"], st.get("penalty_pct"), st.get("penalty_step_pct"),
                st["sale_timing"], st["bidding"], st["foreclosure"], st["statute"],
            ]])
    return len(rows)
