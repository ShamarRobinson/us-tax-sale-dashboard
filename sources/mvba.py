"""MVBA Tax Sales: the online property tax sales that McCreary, Veselka, Bragg & Allen, P.C. conducts for Texas counties,
cities and school districts (https://www.mvbataxsales.com/).

The site is an Angular app over a JSON API that needs no login: POST /api/auctions lists the open online sales,
POST /api/getitems with item_type=bidgallery lists one sale's lots, and POST /api/getitems with item_type=pastsales
pages through every lot of every past sale (about 3,000 lots, 24 per page) with its minimum bid, final bid, bid count
and winning bidder number. Each lot's title and description carry the account number, legal description, suit
number and case style, approximate address and acreage. In-person sales are listed on mvbalaw.com, which refuses
data-center addresses, so only the online sales are read here.
"""
import datetime as dt
import html as htmllib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import parcel, auction, money

NAME = "mvba"
LABEL = "MVBA Tax Sales (Texas online property tax sales)"
HOMEPAGE = "https://www.mvbataxsales.com/"
BASE = "https://www.mvbataxsales.com"
PAUSE = 0.8
MAX_PAGES = None  # for tests
# the API answered the GitHub runner's request with a non-JSON page while answering a browser string with JSON
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

TAGS = re.compile(r"<[^>]+>")
COUNTY_IN_TITLE = re.compile(r"([A-Z][A-Z .'\-]+?) COUNTY\b")
COUNTY_IN_TEXT = re.compile(r"([A-Z][\w .'\-]+?) County, Texas")
ACCOUNT = re.compile(r"Account (?:No|Number)\.?:?\s*([\w\-\.]+)", re.I)
SUIT = re.compile(r"(?:Suit|Cause) (?:No|Number)\.?:?\s*([\w\-\.,]+?)(?:\s*,|\s*:{3,}|\s*$)", re.I)
STYLE = re.compile(r":{3,}\s*(?:Suit|Cause) (?:No|Number)\.?:?\s*[\w\-\.,]+\s*,\s*(.+?)\s+vs?\.?\s+(.+?)(?:,\s*Judgment|\s*:{3,}|$)", re.I)
ADDRESS = re.compile(r"Approximate Property Address:\s*(.+?)(?:\s*:{3,}|$)", re.I)
ACRES = re.compile(r"(\d+(?:\.\d+)?)\s*Acres?\b", re.I)
JUDGMENT_YEAR = re.compile(r"Judgment Through Tax Year (\d{4})", re.I)
WITHDRAWN = re.compile(r"^\W*withdrawn", re.I)


def _post(path, data, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode(),
                                         headers={"User-Agent": BROWSER, "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest", "Referer": HOMEPAGE})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
            time.sleep(PAUSE)
            text = raw.decode("utf-8", "replace")
            try:
                return json.loads(text)
            except ValueError:
                raise RuntimeError(f"not JSON: {text[:120]!r}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError, RuntimeError) as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{BASE}{path}: {last}")


def _text(h):
    return htmllib.unescape(re.sub(r"\s+", " ", TAGS.sub(" ", h or ""))).strip()


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def county_for(title, text, by_name):
    hits = COUNTY_IN_TITLE.findall(title or "")
    for h in reversed(hits):  # "GLADEWATER ISD - GREGG COUNTY ONLINE ..." names the county last
        c = by_name.get(_norm(h))
        if c:
            return c
    for h in COUNTY_IN_TEXT.findall(text or ""):
        c = by_name.get(_norm(h))
        if c:
            return c
    return None


def lots(auction_id=None):
    """Every lot of one open sale, or of every past sale when auction_id is None."""
    out, page = [], 1
    while True:
        data = {"item_type": "pastsales"} if auction_id is None else {"auction_id": auction_id, "item_type": "bidgallery", "show_closed": 1}
        data["filters[page]"] = page  # the page number travels inside the filters object; a bare page is ignored
        data["filters[perpage]"] = 60
        d = _post("/api/getitems", data)
        items = d.get("items") or []
        out.extend(items)
        pages = int(d.get("total_pages") or 1)
        if not items or page >= pages or (MAX_PAGES and page >= MAX_PAGES):
            break
        page += 1
    return out


def lot_parcel(x, upcoming):
    title = _text(x.get("title"))
    desc = _text(x.get("description"))
    text = f"{title} ::::: {desc}"
    bids = int(x.get("bid_count") or 0)
    wb = money(x.get("current_bid")) if bids else None
    if WITHDRAWN.search(title):
        status, wb = "Withdrawn", None
    elif upcoming:
        status, wb = "Listed", None
    elif wb:
        status = "Sold"
    else:
        status = "Not sold"
    style = STYLE.search(text)
    addr = ADDRESS.search(text)
    acres = ACRES.search(text)
    jy = JUDGMENT_YEAR.search(text)
    images = x.get("images") or []
    photo = (images[0].get("image_url") if images else None) or x.get("thumb_url") or None
    owner = style.group(2).strip() if style else None
    if owner:
        owner = re.sub(r",?\s*et\s+al\.?$", "", owner, flags=re.I).strip(" ,")
    return parcel(
        lot=(x.get("lot_number") or "").lstrip("0") or x.get("lot_number"), parcel=(ACCOUNT.search(text) or [None, None])[1],
        caseNo=(SUIT.search(text) or [None, None])[1], plaintiff=style.group(1).strip() if style else None, owner=owner,
        address=addr.group(1).split(",")[0].strip() if addr else None, fullAddress=addr.group(1).strip() if addr else None,
        minBid=money(x.get("minimum_bid")) or money(x.get("starting_bid")), winningBid=wb, status=status,
        buyer=f"Bidder {x.get('winner')}" if wb and x.get("winner") else None, bids=bids or None,
        acres=float(acres.group(1)) if acres and float(acres.group(1)) < 10000 else None, years=f"through {jy.group(1)}" if jy else None,
        desc=desc[:400] or None, link=x.get("item_url"), photo=photo, photoCredit="MVBA Tax Sales" if photo else None,
        soldDate=dt.datetime.fromtimestamp(int(x["ends"]), dt.timezone.utc).date().isoformat() if wb and str(x.get("ends") or "").isdigit() else None,
    )


def fetch(counties):
    by_name = {_norm(c["name"]): c for c in counties if c["state"] == "TX"}
    today = dt.date.today().isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    sales = {}  # auction id -> dict(title, ends, upcoming, lots)
    open_list = (_post("/api/auctions", dict(past_sales="false")).get("data") or [])
    for a in open_list:
        if not int(a.get("item_count") or 0):
            continue
        sales[str(a["id"])] = dict(title=_text(a.get("title")), ends=(a.get("ends") or "")[:10], slug=a.get("auction_id_slug"), upcoming=True, lots=lots(a["id"]))
    print(f"  mvba: {len(sales)} open sales")
    past = lots(None)
    print(f"  mvba: {len(past)} lots in past sales")
    for x in past:
        aid = str(x.get("auction_id"))
        if aid in sales and sales[aid]["upcoming"]:
            continue
        s = sales.setdefault(aid, dict(title=_text(x.get("auction_title")), ends=None, slug=x.get("auction_id_slug"), upcoming=False, lots=[]))
        s["lots"].append(x)
        if str(x.get("ends") or "").isdigit():
            s["ends"] = dt.datetime.fromtimestamp(int(x["ends"]), dt.timezone.utc).date().isoformat()
    out = {}
    for aid, s in sales.items():
        if not s["lots"]:
            continue
        county = county_for(s["title"], " ".join(_text(x.get("description")) for x in s["lots"][:5]), by_name)
        if not county:
            print(f"  mvba/{aid}: no county match for {s['title']!r}")
            continue
        upcoming = s["upcoming"] or bool(s["ends"] and s["ends"] >= today)
        ps = [lot_parcel(x, upcoming) for x in s["lots"]]
        url = f"{BASE}/auction/{s['slug']}/" if s.get("slug") else HOMEPAGE
        rec = out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                 info=dict(run="County Sheriff or Constable; MVBA (McCreary, Veselka, Bragg & Allen) conducts the online tax sales", page=url,
                                                           note="Online tax sales and resales conducted by MVBA for the county and its taxing units are read from mvbataxsales.com, with final bids and bid counts for past sales."),
                                                 auctions=[]))
        rec["auctions"].append(auction(
            id=f"mvba-{aid}", date=s["ends"], kind="list" if upcoming else "results", saleKind="sheriff", label=s["title"].title(), source=url,
            status="upcoming" if upcoming else "past", parcels=ps,
        ))
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    print(f"  mvba: {sum(len(r['auctions']) for r in out.values())} sales in {len(out)} counties")
    return out
