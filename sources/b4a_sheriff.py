"""Bid4Assets sheriff and foreclosure sales: the online sheriff's sales, foreclosure auctions and clerk tax sales that
counties and parishes run through Bid4Assets landing pages (https://www.bid4assets.com/sheriffsales): Pennsylvania
sheriff's offices, Louisiana parish sheriffs, Milwaukee, Palm Beach, Citrus and Okaloosa (Florida), Oklahoma County,
Chelan and Grays Harbor (Washington).

Each landing page (/<slug>/listings) names its county and state, posts a sale calendar through
/api/storefront/seller/calendar/index (one entry per sale day, past and future), and embeds the full property table
for a sale day in /<slug>/listings?salesdate=YYYYMMDD: sheriff number, court case, plaintiff, defendant, attorney, debt
amount, township, address, parcel number, minimum bid, current or final bid, bid count and status ("Sold to Plaintiff",
"Sold", "Preview", "Postponed", "Stayed"). A sale day's table disappears a few days after the sale, so this source is
the upcoming lists plus the outcomes of the last few days. Philadelphia's pages use a different app and are not read
here. The site answers only browser user agents.
"""
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

NAME = "b4a_sheriff"
LABEL = "Bid4Assets (sheriff and foreclosure sales)"
HOMEPAGE = "https://www.bid4assets.com/sheriffsales"
BASE = "https://www.bid4assets.com"
PAUSE = 0.6
THREADS = 6
MONTHS_BACK = 1  # a sale day's table stays online only a few days after the sale, so there is no deep history here
MONTHS_AHEAD = 6
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
SKIP = {"philadelphia", "phillyhudpa"}  # a different app; the calendar endpoint answers 500 for it
MAX_PAGES = None  # for tests

LANDING = re.compile(r'<a[^>]+href="/([A-Za-z0-9]+)"[^>]*>(.*?)</a>', re.S)
TOKEN = re.compile(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"')
TITLE = re.compile(r"<title>Bid4Assets:\s*(.*?)</title>", re.S)
PLACE = re.compile(r"\b(County|Parish|City),\s*([A-Z][a-z]+(?: [A-Z][a-z]+)?)")


def state_of(text):
    """The state named right after 'County,' / 'Parish,' in the landing page's heading ('Milwaukee County, Wisconsin Sheriff')."""
    states = _states()
    for m in PLACE.finditer(text):
        words = m.group(2).split()
        for n in (2, 1):
            cand = " ".join(words[:n]).lower()
            if cand in states:
                return states[cand]
    return None
ROWS = re.compile(r'"data":\{"Data":(\[.*?\]),"Total":(\d+)', re.S)
WITHDRAWN = re.compile(r"^\W*withdrawn\W*", re.I)
TAGS = re.compile(r"<[^>]+>")
STATE_ABBR = {}


def _states():
    if not STATE_ABBR:
        from states import STATES
        STATE_ABBR.update({s["name"].lower(): s["abbr"] for s in STATES})
    return STATE_ABBR


def _get(path, retries=3, data=None, headers=None, opener=None):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + path, data=data, headers={"User-Agent": BROWSER, **(headers or {})})
            with (opener.open(req, timeout=90) if opener else urllib.request.urlopen(req, timeout=90)) as r:
                raw = r.read()
            time.sleep(PAUSE)
            return raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                break
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{BASE}{path}: {last}")


def _text(h):
    return htmllib.unescape(re.sub(r"\s+", " ", TAGS.sub(" ", h or ""))).strip()


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("saint ", "st "))


def roster():
    """(slug, label) for every landing page on the sheriff's sales county list."""
    page = _get("/sheriffsales")
    seen, out = set(), []
    for slug, inner in LANDING.findall(page):
        label = _text(inner)
        if re.search(r"\b(County|Parish|City)\b", label) and slug.lower() not in SKIP and slug not in seen:
            seen.add(slug)
            out.append((slug, label))
    return out


def calendar(slug, token, opener):
    today = dt.date.today()
    start = (today - dt.timedelta(days=30 * MONTHS_BACK)).replace(day=1)
    end = today + dt.timedelta(days=30 * MONTHS_AHEAD)
    body = json.dumps(dict(landingPageUrls=[f"/{slug}"], startDate=f"{start.isoformat()}T00:00:00", endDate=f"{end.isoformat()}T00:00:00")).encode()
    d = json.loads(_get("/api/storefront/seller/calendar/index?take=9999&skip=0&page=1&pageSize=9999", data=body, opener=opener,
                        headers={"Content-Type": "application/json", "X-CSRF-Header-Token": token, "Referer": f"{BASE}/{slug}/calendar"}))
    days = {}
    for x in d.get("Data") or []:
        days[x["SalesDateString"]] = dict(id=x.get("ID"), title=_text(x.get("Title")), kind=_text(x.get("Description")))
    return days


def day_rows(path, sales_date):
    page = _get(f"{path}?salesdate={sales_date}")
    m = ROWS.search(page)
    return json.loads(m.group(1)) if m else []


def row_parcel(r, upcoming):
    title = _text(r.get("Asset_Title"))
    status_text = _text(r.get("AuctionStatusString") or r.get("CustomClosedStatusLabel") or "")
    low = status_text.lower()
    wb, buyer = None, None
    if "sold" in low or r.get("StatusID") == 7:
        status, wb = "Sold", money(r.get("CurrentBid"))
        buyer = "Plaintiff" if "plaintiff" in low else ("Third party" if "third" in low else None)
    elif WITHDRAWN.search(title) or "withdrawn" in low:
        status = "Withdrawn"
    elif any(w in low for w in ("postponed", "stayed", "cancel", "bankrupt", "continued")):
        status = status_text.split(" ")[0].capitalize()
    elif upcoming or low in ("preview", "open", "active", ""):
        status = "Listed" if upcoming else "Not sold"
    else:
        status = "Not sold"
    addr = _text(r.get("Address"))
    attorney = _text(r.get("Attorney"))
    sale_type = _text(r.get("SaleType"))
    images = r.get("Images") or []
    photo = None
    if images and isinstance(images[0], dict):
        photo = images[0].get("ImageUrl") or images[0].get("Url") or images[0].get("MainImageUrl")
    return parcel(
        parcel=_text(r.get("Apn")) or None, address=addr.split(",")[0].strip() or None, fullAddress=addr or None, area=_text(r.get("Township")) or None,
        caseNo=_text(r.get("CourtCase")) or _text(r.get("SheriffNumber")) or None, plaintiff=_text(r.get("Plaintiff")) or None, owner=_text(r.get("Defendant")) or None,
        judgment=money(r.get("DebtAmount")), minBid=money(r.get("MinimumBid")), winningBid=wb, status=status, buyer=buyer, bids=int(r.get("BidCount") or 0) or None,
        typeDetail=sale_type or None, desc=f"Attorney: {attorney}" if attorney else None,
        soldDate=(r.get("SaleDate") or "")[:10] if wb else None, link=f"{BASE}/auction/{r['AuctionID']}", photo=photo, photoCredit="Bid4Assets" if photo else None,
    )


def fetch(counties):
    by_state = {}
    for c in counties:
        by_state.setdefault(c["state"], {})[_norm(c["name"])] = c
    states = _states()
    today = dt.date.today().isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}
    pages = roster()
    if MAX_PAGES:
        pages = pages[:MAX_PAGES]
    print(f"  b4a_sheriff: {len(pages)} landing pages")
    for slug, label in pages:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            path = f"/{slug}/listings"  # most landing pages; the rest serve the same table at their base path
            try:
                page = _get(path, opener=opener)
            except RuntimeError as e:
                if "404" not in str(e):
                    raise
                path = f"/{slug}"
                page = _get(path, opener=opener)
            tok = TOKEN.search(page)
            title = _text(TITLE.search(page).group(1)) if TITLE.search(page) else label
            state = state_of(_text(page))
            county = by_state.get(state, {}).get(_norm(re.sub(r"\s+(County|Parish|City)$", "", label))) if state else None
            if not county:
                print(f"  b4a_sheriff/{slug}: no county match for {label!r} in {state or 'unknown state'}")
                continue
            days = calendar(slug, tok.group(1) if tok else "", opener)
        except (RuntimeError, ValueError) as e:
            print(f"  b4a_sheriff/{slug}: {e}")
            continue
        if not days:
            continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
            fetched = list(pool.map(lambda d: _safe_rows(path, d), sorted(days)))
        rec = out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                 info=dict(run=f"{'Clerk of Court' if 'Clerk' in title else 'Sheriff'} (online sales on Bid4Assets)", page=f"{BASE}{path}",
                                                           note="Sheriff's sales, foreclosure auctions and clerk tax sales are read from the county's Bid4Assets landing page, with each sale day's outcomes (sold to plaintiff or a third party, postponed, stayed)."),
                                                 auctions=[]))
        total = 0
        for sales_date, rows in zip(sorted(days), fetched):
            if not rows:
                continue
            date = f"{sales_date[:4]}-{sales_date[4:6]}-{sales_date[6:]}"
            upcoming = date >= today
            meta = days[sales_date]
            kind_text = f"{meta['kind']} {title} {' '.join(_text(r.get('SaleType')) for r in rows[:3])}".lower()
            ps = [row_parcel(r, upcoming) for r in rows]
            total += len(ps)
            rec["auctions"].append(auction(
                id=f"b4as-{meta['id'] or sales_date}-{slug}", date=date, kind="list" if upcoming else "results",
                saleKind="taxdeed" if "tax" in kind_text and "foreclosure" not in kind_text else "foreclosure",
                label=meta["title"] or title, source=f"{BASE}{path}?salesdate={sales_date}", status="upcoming" if upcoming else "past", parcels=ps,
            ))
        print(f"  b4a_sheriff/{slug}: {county['name']}, {county['state']}: {len(days)} sale days, {total} properties")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out


def _safe_rows(path, sales_date):
    try:
        return day_rows(path, sales_date)
    except (RuntimeError, ValueError) as e:
        print(f"  b4a_sheriff{path} {sales_date}: {e}")
        return []
