"""Virginia tax delinquent real estate sales conducted by For Sale At Auction (https://www.forsaleatauction.biz) for
Taxing Authority Consulting Services (TACS) and county treasurers: judicial sales of tax delinquent land in Virginia
counties and independent cities, bid on the BidWrangler platform at https://bid.forsaleatauction.biz.

BidWrangler's JSON API is open: GET /api/auctions?page=N lists every auction the auctioneer has run (name, category,
status, scheduled end, item count) and GET /api/auctions/<id>/items?page=N lists the lots, each with its lot identifier
("Parcel N1"), name (owner, legal description and tax map number), starting bid, status (sold, no_sale, pending) and
the high bid with the bidder number. Sales by other auctioneers on BidWrangler can be added to HOSTS.
"""
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request

from . import parcel, auction, money

NAME = "bidwrangler"
LABEL = "For Sale At Auction (BidWrangler)"
HOMEPAGE = "https://www.forsaleatauction.biz/auctions/tax-delinquent-real-estate"
HOSTS = [("https://bid.forsaleatauction.biz", "VA", "For Sale At Auction")]
MONTHS_BACK = 24  # a county sells once a year or less, so two years of results is a reasonable history
PAUSE = 0.4
MAX_AUCTIONS = None  # for tests
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

TAX_MAP = re.compile(r"Tax Map(?:\s*(?:No\.?|Number|#|ID))?\s*:?\s*#?\s*([A-Za-z0-9][A-Za-z0-9().\-/]*)", re.I)
TAX_MAPS = re.compile(r"Tax Map(?:\s*(?:No\.?|Number|#|ID))?\s*:?\s*#?\s*(.+)$", re.I)
PARCEL_NO = re.compile(r"\b(?:Parcel|PIN|GPIN|RPC|Map)\s*(?:No\.?|#|ID)?\s*:?\s*([0-9][0-9A-Za-z.\-/]{4,})", re.I)
ACRES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\+/-\s*)?acres?\b", re.I)
SKIP_ITEM = re.compile(r"registration|information for|terms|buyer'?s premium|do not bid", re.I)
STRIP = re.compile(r"^(?:upcoming\s+)?|\s*\d{1,2}-\d{1,2}-\d{4}\s*$", re.I)


def _get_json(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            time.sleep(PAUSE)
            return json.loads(raw)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError, ValueError) as e:
            last = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("saint ", "st ").replace("st. ", "st "))


def _date(iso, tz_hours=-5):
    """The local calendar date of an ISO timestamp (Eastern time is close enough for a sale that closes at 11am)."""
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")) + dt.timedelta(hours=tz_hours)
        return t.date().isoformat()
    except ValueError:
        return iso[:10]


def paged(base, path, key):
    out, page = [], 1
    while True:
        d = _get_json(f"{base}{path}?page={page}&per_page=100")
        rows = d.get(key) or []
        out.extend(rows)
        if not rows or len(out) >= int(d.get("total") or 0):
            return out
        page += 1


def locality_for(name, state_counties):
    """The registry county (or independent city) a sale name refers to: 'City of Petersburg, VA Sale of ...',
    'Clarke County, VA Sale of ...', 'King William Tax Delinquent Sale'."""
    n = STRIP.sub("", name).strip()
    cities = {k: v for k, v in state_counties.items() if "(city)" in v["name"].lower()}
    counties = {k: v for k, v in state_counties.items() if "(city)" not in v["name"].lower()}
    m = re.match(r"(?:City|Town) of ([A-Za-z .']+?)(?:,|\s+(?:VA|Virginia|Sale|Tax|Online|Judicial)\b)", n, re.I)
    if m:
        key = _norm(m.group(1))
        return cities.get(key + "city") or cities.get(key) or counties.get(key)
    m = re.match(r"([A-Za-z .'&]+?)\s+County\b", n, re.I)
    if m:
        return counties.get(_norm(m.group(1)))
    m = re.match(r"([A-Za-z .']+?)\s+(?:Tax|Sale|Judicial|Online|Delinquent)\b", n, re.I)
    if m:
        key = _norm(m.group(1))
        return counties.get(key) or cities.get(key + "city")
    return None


def make_parcel(it, upcoming, ui):
    name = (it.get("name") or "").strip()
    simple = (it.get("simple_description") or "").strip()
    desc_plain = (it.get("description_without_html") or "").strip()
    status_raw = (it.get("status") or "").lower()
    state = it.get("api_bidding_state") or {}
    high = state.get("high") or {}
    wb = money(high.get("amount")) if status_raw == "sold" else None
    redeemed = bool(re.search(r"\bREDEEMED\b", f"{name} {simple} {desc_plain}", re.I))
    if status_raw == "sold":
        status = "Sold"
    elif redeemed:
        status = "Redeemed"
    elif status_raw in ("no_sale", "passed", "unsold"):
        status = "Not sold"
    elif upcoming or status_raw in ("pending", "accepting_bids", "open", "live"):
        status = "Listed"
    else:
        status = status_raw.replace("_", " ").capitalize() or "Not sold"
    tm = TAX_MAPS.search(name) or TAX_MAPS.search(desc_plain)
    parcel_no = None
    if tm:
        first = re.split(r"[,;]|\s+and\s+|\s+&\s+", tm.group(1).strip(), 1)[0].strip().rstrip(".")
        parcel_no = first or None
    else:
        m = PARCEL_NO.search(name) or PARCEL_NO.search(desc_plain)
        parcel_no = m.group(1).rstrip(".") if m else None
    owner = name.split(",")[0].strip() if "," in name and not name.lower().startswith(("lot", "parcel", "tax map")) else None
    if owner and len(owner) > 60:
        owner = None
    acres_m = ACRES.search(name) or ACRES.search(simple) or ACRES.search(desc_plain)
    images = it.get("images") or []
    photo = (images[0].get("lg") or images[0].get("sm")) if images and isinstance(images[0], dict) else None
    start = money(it.get("start_amount"))
    buyer = f"Bidder {high.get('bidder_number')}" if wb and high.get("bidder_number") else None
    return parcel(
        lot=(it.get("lot_identifier") or "").strip() or None, parcel=parcel_no, owner=owner, desc=(name + (f". {simple}" if simple and simple not in name else ""))[:400] or None,
        minBid=start if start and start > 1 else None, winningBid=wb, bids=int(state.get("accepted_bid_count") or 0) or None, buyer=buyer, status=status,
        acres=float(acres_m.group(1)) if acres_m else None, photo=photo, photoCredit="For Sale At Auction" if photo else None,
        soldDate=_date(it.get("actual_end_time")) if wb else None, link=f"{ui}?item={it.get('id')}" if it.get("id") else ui,
    )


def fetch(counties):
    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=30 * MONTHS_BACK)).isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}
    for base, state, auctioneer in HOSTS:
        state_counties = {_norm(c["name"]): c for c in counties if c["state"] == state}
        try:
            all_aucs = paged(base, "/api/auctions", "auctions")
        except RuntimeError as e:
            print(f"  bidwrangler/{base}: {e}")
            continue
        sales = [a for a in all_aucs if re.search(r"tax|judicial sale|delinquent", f"{a.get('category') or ''} {a.get('name') or ''}", re.I)
                 and not re.search(r"personal property|vehicle|equipment|rv\b|boat", a.get("name") or "", re.I)]
        print(f"  bidwrangler/{auctioneer}: {len(all_aucs)} auctions, {len(sales)} tax delinquent sales")
        n = 0
        for a in sorted(sales, key=lambda a: a.get("scheduled_end_time") or "", reverse=True):
            date = _date(a.get("scheduled_end_time")) or _date(a.get("starts_at"))
            if not date or date < cutoff:
                continue
            if MAX_AUCTIONS and n >= MAX_AUCTIONS:
                break
            county = locality_for(a.get("name") or "", state_counties)
            if not county:
                print(f"  bidwrangler/{auctioneer}: no locality match for {a.get('name')!r}")
                continue
            n += 1
            upcoming = date >= today.isoformat() and a.get("status") != "complete"
            ui = f"{base}/ui/auctions/{a['id']}"
            try:
                items = paged(base, f"/api/auctions/{a['id']}/items", "items") if (a.get("items_count") or 0) > 0 else []
            except RuntimeError as e:
                print(f"  bidwrangler/{a['id']}: {e}")
                items = []
            ps = [make_parcel(it, upcoming, ui) for it in items if not SKIP_ITEM.search(f"{it.get('lot_identifier') or ''} {it.get('name') or ''}")]
            loc = a.get("location") or {}
            where = ", ".join(x for x in [loc.get("street"), loc.get("city"), loc.get("state")] if x) if loc else ""
            label = re.sub(r"\s+", " ", STRIP.sub("", a.get("name") or "Sale of Tax Delinquent Real Estate")).strip()
            rec = out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                     info=dict(run=f"Treasurer through Taxing Authority Consulting Services and {auctioneer} (judicial sale, bid on BidWrangler)",
                                                               page=HOMEPAGE, note="Virginia sells tax delinquent real estate at judicial sales ordered by the circuit court (Va. Code 58.1-3965); there is no redemption after the sale, and a 10% buyer's premium applies."),
                                                     auctions=[]))
            rec["auctions"].append(auction(
                id=f"bw-{a['id']}", date=date, kind="list" if upcoming else "results", saleKind="taxdeed", label=label + (f", {where}" if where and not a.get("online_only") else ""),
                source=ui, status="upcoming" if upcoming else "past", parcels=ps,
            ))
            print(f"  bidwrangler/{a['id']}: {county['name']}, {state}: {len(ps)} parcels, {date}, {a.get('status')}")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out
