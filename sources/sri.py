"""SRI Inc. (https://www.sriservices.com): the tax sale, commissioners' certificate sale, deed sale, tax lien sale and
sheriff's foreclosure sale lists that SRI runs for county treasurers, auditors and sheriffs in Indiana (most of the
state's 92 counties), Colorado, Louisiana, Tennessee, Florida, Michigan and Alabama. Online sales are bid on Zeus
Auction (https://www.zeusauction.com), SRI's own platform; in-person sales are held at the courthouse.

The property search on sriservices.com is a public JSON API (https://sriservicesusermgmtprod.azurewebsites.net/api/...,
read with the site's public client key):

    POST /api/property/carddetail            every property in a state for a date range: parcel number, address, county,
                                             sale type, sale status (DELINQUENT, PAID, REMOVED, SOLD, COUNTY, TAX DEED,
                                             REDEEMED ...), sale date, time and place, sale id, coordinates
    POST /api/property/downloadpropertylist  the spreadsheet rows for an upcoming sale in one county: owner, minimum bid,
                                             cause number, legal description, and for sheriff's sales the plaintiff,
                                             defendant, attorney and judgment
    POST /api/property/detail                one property: minimum bid, sale price and status after the sale
    GET  /api/property/states, /counties     the roster

Past sales come back with each parcel's outcome but no prices, so the adapter asks /detail for the parcels that sold
(SOLD, SOLD CERT SALE, TAX DEED, REDEEMED) eight at a time; parcels that were paid, removed or cancelled before a past
sale are left out. Twelve months of history by default.
"""
import concurrent.futures
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request

from . import parcel, auction, money

NAME = "sri"
LABEL = "SRI Inc. (Zeus Auction)"
HOMEPAGE = "https://www.sriservices.com/properties"
API = "https://sriservicesusermgmtprod.azurewebsites.net"
SITE = "https://www.sriservices.com"
ZEUS = "https://www.zeusauction.com"
API_KEY = "9f8fd9fe5160294175e1c737567030f495d838a7922a678bc06e0a093910"  # the public client key in the site's own JavaScript
HEADERS = {"x-api-key": API_KEY, "Accept": "application/json", "Content-Type": "application/json", "Origin": SITE, "Referer": SITE + "/",
           "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
MONTHS_BACK = 12
THREADS = 8
PAUSE = 0.2
MAX_STATES = None  # for tests
DETAIL_STATUSES = {"SOLD", "SOLD CERT SALE", "TAX DEED", "REDEEMED", "REDEEMED CERT SALE", "SOLD TO 3RD PARTY", "SOLD TO PLAINTIFF", "SOLD TO THIRD PARTY"}  # past outcomes worth a /detail call for the price
SKIP_PAST = {"PAID", "REMOVED", "CANCELLED", "INVALID", "INVALID CERT", "INTGOVTRNSFR", "BANKRUPT", "WITHDRAWN"}  # never offered at a past sale
SKIP_ALWAYS = {"INVALID", "INVALID CERT", "INTGOVTRNSFR"}
KINDS = {"F": "foreclosure", "D": "taxdeed", "J": "taxdeed", "B": "taxdeed", "A": "taxlien", "C": "taxlien", "O": "taxlien", "R": "taxlien", "T": "taxlien"}
KIND_NAMES = {"F": "Foreclosure Sale", "D": "Deed Sale", "J": "Adjudicated Sale", "B": "Blighted Property Sale", "A": "Tax Sale", "C": "Certificate Sale",
              "O": "Tax Lien Sale", "R": "Redemption Sale", "T": "Tax Sale"}
STATUS = {"DELINQUENT": "Listed", "SALE ACTIVE": "Listed", "PAID": "Paid", "REMOVED": "Withdrawn", "CANCELLED": "Cancelled", "BANKRUPT": "Bankruptcy",
          "WITHDRAWN": "Withdrawn", "SOLD": "Sold", "SOLD CERT SALE": "Sold", "TAX DEED": "Sold", "REDEEMED": "Redeemed", "REDEEMED CERT SALE": "Redeemed",
          "COUNTY": "Not sold", "STRUCK": "Not sold", "SOLD TO 3RD PARTY": "Sold", "SOLD TO PLAINTIFF": "Sold", "SOLD TO THIRD PARTY": "Sold"}
CITY_PARISH = {"villeplatte": "Evangeline", "cityofshreveport": "Caddo", "shreveport": "Caddo", "bossiercity": "Bossier"}  # Louisiana cities that hold their own sales


def _post(path, body, retries=3, timeout=300):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, headers=HEADERS,
                                         method="POST" if body is not None else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            time.sleep(PAUSE)
            return json.loads(raw)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError, ValueError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{API}{path}: {last}")


def _norm(s):
    s = re.sub(r"\s+(county|parish|city)$", "", (s or "").strip().lower())
    return re.sub(r"[^a-z0-9]", "", s.replace("saint ", "st ").replace("st. ", "st "))


def _date(s):
    """'10/19/2026' or '2026-10-19T00:00:00' -> '2026-10-19'."""
    if not s:
        return None
    s = str(s)
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def _range(start, end=""):
    return dict(startDate=start, endDate=end, compareOperator=">")


def search(state, county="", kind="", start=None, end=""):
    body = dict(auctionDateRange=_range(start, end), auctionStyle="", county=county, propertySaleType=kind, recordCount=50000, saleStatus="",
                searchText="", startIndex=0, state=state)
    return _post("/api/property/carddetail", body).get("properties") or []


def download(state, county, kind, start):
    """The spreadsheet rows (owner, minimum bid, legal, cause number, plaintiff, judgment) for one county's upcoming sales of one kind, by parcel id."""
    body = dict(auctionDateRange=_range(start), auctionStyle="", county=county, propertySaleType=kind, recordCount=50000, saleStatus="", searchText="",
                startIndex=0, state=state)
    rows = _post("/api/property/downloadpropertylist", body).get("downloadList") or []
    return {(r.get("propertyID") or "").strip(): r for r in rows}


def detail(p):
    d = _post("/api/property/detail", dict(id=p["id"], propertyId=p["propertyId"], saleId=p["saleId"], saleType=p["saleType"]))
    return d.get("propertyInfo") or {}, d.get("propertyCardDetail") or {}


def states():
    return [s["id"] for s in _post("/api/property/states", None)]


def _status(p, upcoming):
    raw = (p.get("saleStatusDescription") or "").strip().upper()
    # a past parcel still marked DELINQUENT had no outcome posted; the dashboard shows "Listed" at a past sale as "Not published"
    return raw, STATUS.get(raw) or (raw.capitalize() if raw else "Listed")


REDEMPTION = re.compile(r"\s*Redemption Period:\s*([^,;]+?)\s*$", re.I)
ACRES = re.compile(r"Ac(?:e)?reage:\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*Acres?\b", re.I)


def _clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def _full_address(p):
    """Street and full address; Tennessee's lists tack the redemption period onto the street line, which goes to the note instead."""
    parts, redemption = [], None
    for x in (_clean(p.get("address1")), _clean(p.get("address2"))):
        m = REDEMPTION.search(x)
        if m:
            redemption, x = m.group(1), x[:m.start()].strip()
        if x and x.upper() != "NONE ON FILE":
            parts.append(x)
    street = " ".join(parts)
    city, zip_ = _clean(p.get("city")), _clean(p.get("zip"))
    if city and street.lower().endswith(city.lower()):
        street = street[:-len(city)].strip(" ,")
    tail = " ".join(x for x in [city, zip_] if x)
    return street or None, (f"{street}, {tail}" if street and tail else street or None), redemption


def make_parcel(p, upcoming, row, info, card):
    raw, status = _status(p, upcoming)
    street, full, redemption = _full_address(p)
    owner = (card.get("ownerName1") or row.get("ownerName") or p.get("ownerName1") or "").strip() or None
    owner2 = (card.get("ownerName2") or p.get("ownerName2") or "").strip()
    if owner2:
        owner = f"{owner} & {owner2}" if owner else owner2
    min_bid = money(info.get("minimumBid")) or money(row.get("minimumBid"))
    sale_price = money(info.get("salePrice")) if info else None
    wb = sale_price if status in ("Sold", "Redeemed") and sale_price else None
    buyer = "County" if raw == "COUNTY" else "Plaintiff" if "PLAINTIFF" in raw else "Third party" if "3RD PARTY" in raw or "THIRD PARTY" in raw else None
    judgment = money(info.get("judgementAmount")) if p.get("saleType") == "F" else None
    judgment = judgment or (money(row.get("judgmentAmount")) if p.get("saleType") == "F" else None)
    legal = _clean(row.get("legal") or card.get("briefLegal") or p.get("briefLegal"))
    attorney = _clean(row.get("attorneyName") or info.get("attorney"))
    m = ACRES.search(legal)
    acres = float(m.group(1) or m.group(2)) if m else None
    desc = "; ".join(x for x in [legal[:300] if legal else "", f"Redemption period: {redemption}" if redemption else "", f"Attorney: {attorney}" if attorney else ""] if x) or None
    return parcel(
        parcel=(p.get("propertyId") or "").split(" / ")[0].strip() or None, address=street, fullAddress=full, zip=(p.get("zip") or "").strip() or None,
        area=(p.get("city") or "").strip() or None, owner=owner if p.get("saleType") != "F" else ((row.get("defendantName") or info.get("defendant") or "").strip() or None),
        plaintiff=(row.get("plaintiffName") or info.get("plantiff") or "").strip() or None,
        caseNo=(row.get("causeNumber") or info.get("causeNumber") or "").strip() or None,
        minBid=min_bid, winningBid=wb, judgment=judgment, status=status, buyer=buyer, lat=p.get("latitude"), lon=p.get("longitude"), acres=acres,
        typeDetail=(p.get("saleTypeDescription") or KIND_NAMES.get(p.get("saleType"))), desc=desc,
        soldDate=_date(p.get("auctionDate")) if wb else None,
    )


def fetch(counties):
    by_state = {}
    for c in counties:
        by_state.setdefault(c["state"], {})[_norm(c["name"])] = c
    today = dt.date.today()
    start = (today - dt.timedelta(days=30 * MONTHS_BACK)).isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}
    try:
        roster = states()
    except RuntimeError as e:
        print(f"  sri: {e}")
        return out
    if MAX_STATES:
        roster = roster[:MAX_STATES]
    for state in roster:
        try:
            props = search(state, start=start)
        except RuntimeError as e:
            print(f"  sri/{state}: {e}")
            continue
        if not props:
            print(f"  sri/{state}: nothing listed")
            continue
        sales, seen = {}, set()
        for p in props:
            date = _date(p.get("auctionDate"))
            key = (p.get("id"), p.get("saleId"))
            if not date or key in seen:
                continue
            seen.add(key)
            upcoming = date >= today.isoformat()
            raw = (p.get("saleStatusDescription") or "").strip().upper()
            if raw in SKIP_ALWAYS or (not upcoming and raw in SKIP_PAST):
                continue
            sales.setdefault((p.get("county") or "", p.get("saleId"), date, p.get("saleType")), []).append(p)
        # spreadsheet rows for the upcoming sales, one call per county and sale type
        rows = {}
        for county_name, sale_id, date, kind in sorted(sales):
            if date >= today.isoformat() and (county_name, kind) not in rows:
                try:
                    rows[(county_name, kind)] = download(state, county_name, kind or "", today.isoformat())
                except RuntimeError as e:
                    print(f"  sri/{state}/{county_name}: {e}")
                    rows[(county_name, kind)] = {}
        # prices for the parcels that sold at past sales
        wanted = [p for (county_name, sale_id, date, kind), ps in sales.items() if date < today.isoformat() for p in ps
                  if (p.get("saleStatusDescription") or "").strip().upper() in DETAIL_STATUSES]
        details = {}
        if wanted:
            with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
                for p, got in zip(wanted, pool.map(_safe_detail, wanted)):
                    details[(p.get("id"), p.get("saleId"))] = got
        total, matched = 0, set()
        for (county_name, sale_id, date, kind), ps in sorted(sales.items(), key=lambda kv: kv[0][2], reverse=True):
            county = by_state.get(state, {}).get(_norm(county_name)) or by_state.get(state, {}).get(_norm(CITY_PARISH.get(_norm(county_name), "")))
            if not county:
                print(f"  sri/{state}: no county match for {county_name!r}")
                continue
            upcoming = date >= today.isoformat()
            first = ps[0]
            style = (first.get("auctionStyle") or "").strip()
            where = (first.get("location") or "").strip()
            online = "zeus" in where.lower() or style.lower() == "online"
            page = f"{SITE}/county/{state}/{urllib.request.quote(county_name)}"
            kind_name = first.get("saleTypeDescription") or KIND_NAMES.get(kind, "Tax Sale")
            parcels = []
            for p in ps:
                info, card = details.get((p.get("id"), p.get("saleId")), ({}, {}))
                row = rows.get((county_name, kind), {}).get((p.get("propertyId") or "").strip(), {}) if upcoming else {}
                parcels.append(make_parcel(p, upcoming, row, info, card))
            total += len(parcels)
            matched.add(county["fips"])
            rec = out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                     info=dict(run="SRI Inc. for the county (online bidding on Zeus Auction)" if online else "SRI Inc. for the county (in-person sale)",
                                                               page=page, note="Sale lists and outcomes come from SRI's public property search; online sales are bid on Zeus Auction."),
                                                     auctions=[]))
            label = f"{kind_name} ({style})" if style and style.lower() not in kind_name.lower() else kind_name
            if where and not online:
                label += f", {where.splitlines()[0][:60]}"
            rec["auctions"].append(auction(
                id=f"sri-{county['fips']}-{sale_id}-{kind}-{date}", date=date, kind="list" if upcoming else "results", saleKind=KINDS.get(kind, "taxlien"),
                label=label, source=page if not online else ZEUS, status="upcoming" if upcoming else "past", parcels=parcels,
            ))
        print(f"  sri/{state}: {len(matched)} counties, {len(sales)} sales, {total} parcels ({len(wanted)} priced)")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out


def _safe_detail(p):
    try:
        return detail(p)
    except RuntimeError as e:
        print(f"  sri detail {p.get('propertyId')}: {e}")
        return {}, {}
