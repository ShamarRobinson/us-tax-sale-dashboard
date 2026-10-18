"""Bid4Assets: county tax sale auctions in California, Nevada, Washington, Pennsylvania, Minnesota and Louisiana
(https://www.bid4assets.com/county-tax-sales).

The County Tax Sales calendar lists one storefront per sale (/storefront/<slug>), past and upcoming. A storefront page
carries the sale's start and end dates, its storefront id and the ids of its closing groups; the storefront API
(/api/storefront/auctions/index, a POST with the page's anti-forgery token) returns every item in a closing group with
its minimum bid, status and, once the sale has closed, the winning bid; and each item's page (/auction/<id>) has the
parcel number, address, assessed value, legal description and parcel map links, and a photo. Past storefronts stay
online with their results, so this source gives sale lists before a sale and winning bids after it.
"""
import calendar
import concurrent.futures
import datetime as dt
import html as htmllib
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.request

from . import parcel, auction, money

NAME = "bid4assets"
LABEL = "Bid4Assets (county tax sale auctions)"
HOMEPAGE = "https://www.bid4assets.com/county-tax-sales"
BASE = "https://www.bid4assets.com"
PAUSE = 0.7
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
THREADS = 8  # item pages are fetched in parallel; a Pennsylvania upset sale lists thousands of parcels

CALENDAR_LINK = re.compile(r'<a[^>]+href="/storefront/([^"#?]+)"[^>]*>(.*?)</a>', re.S)
STOREFRONT_ID = re.compile(r"getauctiondisplay/(\d+)")
COLLECTIONS = re.compile(r'"Data":(\[\{"PublishedStorefrontCollectionId".*?\}\])')
TOKEN = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')
TITLE = re.compile(r"<title>Bid4Assets:\s*(.*?)</title>", re.S)
DATES = re.compile(r"(Starts|Ends)\s+([A-Z][a-z]+ \d{1,2}, \d{4})")
SPEC_ROW = re.compile(r"<td>\s*<strong[^>]*>([^<]*)</strong>\s*</td>\s*<td[^>]*>(.*?)</td>", re.S)
HREF = re.compile(r'href="([^"]+)"')
TAGS = re.compile(r"<[^>]+>")
STATE_ABBR = re.compile(r",\s*([A-Z]{2})\b")
WITHDRAWN = re.compile(r"^\W*withdrawn\W*", re.I)
MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}
STATE_NAMES = {"california": "CA", "nevada": "NV", "washington": "WA", "pennsylvania": "PA", "minnesota": "MN", "louisiana": "LA", "florida": "FL",
               "arizona": "AZ", "oregon": "OR", "idaho": "ID", "montana": "MT", "michigan": "MI", "ohio": "OH", "texas": "TX", "colorado": "CO"}


class Session:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        # the site answers 403 to anything that does not look like a browser, including a browser string with a URL appended
        self.opener.addheaders = [("User-Agent", BROWSER)]

    def get(self, path, retries=3, timeout=90, data=None, headers=None):
        last = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(BASE + path, data=data, headers=headers or {})
                with self.opener.open(req, timeout=timeout) as r:
                    raw = r.read()
                time.sleep(PAUSE)
                return raw.decode("utf-8", "replace")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
                last = e
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"{BASE}{path}: {last}")

    def post_json(self, path, payload, token, referer):
        return json.loads(self.get(path, data=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json", "X-CSRF-Header-Token": token, "Referer": referer}))


def _text(h):
    return htmllib.unescape(re.sub(r"\s+", " ", TAGS.sub(" ", h.replace("<br />", ", ").replace("<br>", ", ")))).strip(" ,")


def _date(s):
    m = re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", s or "")
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}" if m and m.group(1) in MONTHS else None


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("saint ", "st "))


def roster(session):
    """(slug, label) for every storefront on the County Tax Sales calendar, in calendar order."""
    page = session.get("/county-tax-sales")
    seen, out = set(), []
    for slug, label in CALENDAR_LINK.findall(page):
        if slug not in seen:
            seen.add(slug)
            out.append((slug, _text(label)))
    return out


def county_for(label, title, by_state):
    """Match a sale to a registry county: the state comes from ', CA' in the label or the state name in the page title,
    the county is the longest registry name the label starts with ('Carson City', 'West Baton Rouge', 'Elko')."""
    m = STATE_ABBR.search(label) or STATE_ABBR.search(title)
    state = m.group(1) if m else None
    if not state:
        for name, abbr in STATE_NAMES.items():
            if name in title.lower():
                state = abbr
                break
    head = _norm(re.split(r"\b(County|Parish|Co|Tax|Repository|Public|Treasurer|Sheriff|Upset|Judicial)\b", re.sub(r"^County of ", "", label))[0])
    states = [state] if state else list(by_state)
    best = None
    for st in states:
        for norm_name, c in by_state.get(st, {}).items():
            if head.startswith(norm_name) and (best is None or len(norm_name) > len(_norm(best["name"]))):
                best = c
    return best


def storefront(session, slug):
    """Storefront id, closing-group ids, anti-forgery token, title, start and end dates, and the page's own label."""
    page = session.get(f"/storefront/{slug}")
    sid = STOREFRONT_ID.search(page)
    cols = COLLECTIONS.search(page)
    tok = TOKEN.search(page)
    title = _text(TITLE.search(page).group(1)) if TITLE.search(page) else slug
    dates = dict((k, _date(v)) for k, v in DATES.findall(_text(page)))
    return dict(id=int(sid.group(1)) if sid else None, collections=[c["StorefrontCollectionId"] for c in json.loads(cols.group(1))] if cols else [],
                token=tok.group(1) if tok else "", title=title, start=dates.get("Starts"), end=dates.get("Ends"))


def items(session, sf, slug):
    out = []
    for cid in sf["collections"]:
        skip = 0
        while True:
            d = session.post_json(f"/api/storefront/auctions/index?take=200&skip={skip}&page={skip // 200 + 1}&pageSize=200",
                                  dict(storefrontId=sf["id"], storefrontCollectionId=cid), sf["token"], f"{BASE}/storefront/{slug}")
            batch = d.get("data") or []
            out.extend(batch)
            skip += len(batch)
            if not batch or skip >= (d.get("total") or 0):
                break
    return out


def detail(auction_id, retries=3):
    """Parcel number, address, assessed value and links from an item page (no session needed, so it can run in a thread)."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{BASE}/auction/{auction_id}", headers={"User-Agent": BROWSER})
            with urllib.request.urlopen(req, timeout=90) as r:
                page = r.read().decode("utf-8", "replace")
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"{BASE}/auction/{auction_id}: {last}")
    spec = {}
    for label, value in SPEC_ROW.findall(page):
        key = _text(label).rstrip(":").lower()
        links = HREF.findall(value)
        spec[key] = (_text(value), htmllib.unescape(links[0]).strip() if links else None)
    def val(*keys):
        for k in keys:
            if k in spec:
                return spec[k][0]
    def link(*keys):
        for k in keys:
            if k in spec and spec[k][1]:
                return spec[k][1]
    address = val("address", "property address", "situs address", "site address")
    legal = val("legal description", "legal")
    return dict(
        parcel=val("apn", "parcel number", "parcel id", "parcel no", "tax id", "pin", "account number"),
        address=address.split(",")[0].strip() if address else None, fullAddress=address or None,
        value=money(val("total assessed values", "total assessed value", "assessed value", "assessed values")) or None,
        acres=money(val("acreage", "acres", "lot size (acres)")) or None,
        type=val("property type", "use code", "land use", "zoning", "property class"),
        desc=(legal if legal and "click here" not in legal.lower() else val("property description", "description", "improvements")),
        legalDoc=link("legal description", "legal"), parcelMap=link("parcel map", "map"), parcelInfo=link("add'l information", "assessor", "assessor's property search", "property search"),
    )


def _safe_detail(slug, auction_id):
    try:
        return detail(auction_id)
    except RuntimeError as e:
        print(f"  bid4assets/{slug} item {auction_id}: {e}")
        return {}


def info_for(state, page):
    run = {"PA": "County Tax Claim Bureau (upset, judicial and repository sales)", "LA": "Parish (adjudicated property sales)", "MN": "County Auditor-Treasurer (tax-forfeited land sales)",
           "WA": "County Treasurer (tax foreclosed property auctions)"}.get(state, "County Treasurer-Tax Collector (tax defaulted property auctions)")
    return dict(run=run, page=page, note="Sale lists, results and winning bids are read from the county's Bid4Assets storefront, which stays online after the sale with each parcel's outcome.")


def fetch(counties):
    by_state = {}
    for c in counties:
        by_state.setdefault(c["state"], {})[_norm(c["name"])] = c
    session = Session()
    today = dt.date.today().isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}
    listed = roster(session)
    print(f"  bid4assets: {len(listed)} storefronts on the calendar")
    for slug, label in listed:
        try:
            sf = storefront(session, slug)
            if not sf["id"] or not sf["collections"]:
                print(f"  bid4assets/{slug}: no closing groups published")
                continue
            county = county_for(label, sf["title"], by_state)
            if not county:
                print(f"  bid4assets/{slug}: no county match for {label!r} / {sf['title']!r}")
                continue
            rows = items(session, sf, slug)
        except (RuntimeError, ValueError) as e:
            print(f"  bid4assets/{slug}: {e}")
            continue
        date = sf["end"] or (min(r["bidCloseTime"] for r in rows if r.get("bidCloseTime"))[:10] if any(r.get("bidCloseTime") for r in rows) else None)
        upcoming = bool(date and date >= today)
        outcomes = {}
        for r in rows:
            title = _text(r.get("asset_title") or "")
            if r.get("statusID") == 7 or _text(r.get("timeRemaining") or "") == "Sold":
                outcomes[r["auctionID"]] = ("Sold", money(r.get("currentWinningAmount")))
            elif WITHDRAWN.search(title) or r.get("statusID") == 6:
                outcomes[r["auctionID"]] = ("Withdrawn", None)
            else:
                outcomes[r["auctionID"]] = ("Listed" if upcoming else "Not sold", None)
        # item pages for everything in an upcoming sale and for what sold in a past one; unsold and withdrawn parcels of
        # a past sale keep the list row (parcel number from the title, minimum bid, status) without a page fetch
        wanted = [r["auctionID"] for r in rows if upcoming or outcomes[r["auctionID"]][0] == "Sold"]
        details = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
            for aid, got in zip(wanted, pool.map(lambda a: _safe_detail(slug, a), wanted)):
                details[aid] = got
        ps = []
        for i, r in enumerate(rows, 1):
            title = _text(r.get("asset_title") or "")
            d = details.get(r["auctionID"]) or {}
            status, wb = outcomes[r["auctionID"]]
            apn = d.get("parcel") or (re.search(r"(?:APN|Parcel)[:#\s]*([\w\-\.]+)\s*$", title) or re.search(r":\s*([\w\-\.]+)\s*$", title) or [None, None])[1]
            ps.append(parcel(
                lot=str(i), parcel=apn, address=d.get("address"), fullAddress=d.get("fullAddress"), minBid=money(r.get("minimumBid")),
                winningBid=wb, status=status, value=d.get("value"), acres=d.get("acres"), type=d.get("type"), desc=(d.get("desc") or "")[:400] or None,
                soldDate=(r.get("actualCloseTime") or "")[:10] if wb else None,
                link=f"{BASE}/auction/{r['auctionID']}", parcelMap=d.get("parcelMap"), parcelInfo=d.get("parcelInfo"), sourceDoc=d.get("legalDoc"),
                photo=r.get("assetMainImageMainUrl") or r.get("s3thumbnailUrl"), photoCredit="Bid4Assets" if r.get("assetMainImageMainUrl") or r.get("s3thumbnailUrl") else None,
            ))
        rec = out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                 info=info_for(county["state"], f"{BASE}/storefront/{slug}"), auctions=[]))
        rec["auctions"].append(auction(
            id=f"b4a-{sf['id']}", date=date, kind="list" if upcoming else "results", saleKind="taxdeed", label=sf["title"],
            source=f"{BASE}/storefront/{slug}", status="upcoming" if upcoming else "past", parcels=ps,
        ))
        sold = sum(1 for p in ps if p.get("winningBid"))
        print(f"  bid4assets/{slug}: {county['name']}, {county['state']}: {len(ps)} parcels, {sold} sold, {date or 'date not posted'}")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out
