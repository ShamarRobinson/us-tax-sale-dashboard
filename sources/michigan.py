"""Michigan: county treasurer foreclosure auctions run by Title Check on tax-sale.info (most of the state's 83 counties).

The site publishes, with no login, an upcoming-auction calendar, a past-results calendar for each year, and for each
county catalog a CSV of every lot (parcel id, address, minimum bid, SEV, coordinates, inspector's notes) plus an HTML
page that shows the sold price of each lot once the auction has run.
"""
import csv
import datetime as dt
import html as htmllib
import io
import re
import urllib.parse

from . import get, parcel, auction, money

NAME = "michigan"
LABEL = "Tax-Sale.info (Michigan Public Land Auction)"
HOMEPAGE = "https://www.tax-sale.info/"
BASE = "https://www.tax-sale.info"

ENTRY = re.compile(r'<div class="entry clearfix">(.*?)<!--|<div class="entry clearfix">(.*?)(?=<div class="entry clearfix">|<div id="posts"|</section>)', re.S)
AUCTION_ID = re.compile(r'/listings/auction/(\d+)')
TITLE = re.compile(r'<h2><a href="/listings/auction/\d+">([^<]*)</a>')
DATE = re.compile(r'([A-Z][a-z]+ \d{1,2}, \d{4})')
CATALOG = re.compile(r'<a href="/listings/catalog/(\d+)">([^<]+)</a>')
LOT = re.compile(r'<a href="/lot/show/id/(\d+)" aria-label="Lot (\d+) - ([^"]*)"(.*?)</a>', re.S)
PRICE = re.compile(r'(Sold for|Minimum Bid:?)\s*\$?([\d,\.]+)')
PHOTO = re.compile(r'src="(https?://taxsaleimg\.com/[^"]+)"')
TIME = re.compile(r'<time datetime="([^"]+)"')

MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def _date(s):
    m = DATE.search(s or "")
    if not m:
        return None
    mon, day, year = m.group(1).replace(",", "").split()
    return f"{year}-{MONTHS[mon]:02d}-{int(day):02d}"


def _entries(page_html):
    """Yield (auction_id, title, date, [(catalog_id, county_label), ...]) for each auction block on a calendar page."""
    parts = page_html.split('<div class="entry clearfix">')[1:]
    for part in parts:
        ids = AUCTION_ID.findall(part)
        if not ids:
            continue
        title = TITLE.search(part)
        yield ids[0], htmllib.unescape(title.group(1).strip()) if title else "Auction", _date(part), CATALOG.findall(part)


def _norm(name):
    name = name.strip()
    name = re.sub(r"\s+(DNR|Re-Offer|Reoffer)$", "", name, flags=re.I)
    name = name.replace("Saint ", "St. ")
    return name.lower()


def _coord(s):
    s = (s or "").strip()
    if not s:
        return None
    neg = s[:1] in "WSws" or s.startswith("-")
    s = re.sub(r"[^\d\.]", "", s)
    try:
        v = float(s)
    except ValueError:
        return None
    return -abs(v) if neg else v


def _catalog(cat_id):
    """Return (date, status_by_lot, type_by_lot, note) from the catalog page and the list of parcels from its CSV."""
    page = get(f"{BASE}/listings/catalog/{cat_id}")
    sold, types, photos = {}, {}, {}
    for lot_id, lot, typ, body in LOT.findall(page):
        types[lot] = htmllib.unescape(typ)
        m = PRICE.search(body)
        if m and m.group(1).startswith("Sold"):
            sold[lot] = money(m.group(2))
        ph = PHOTO.search(body)
        if ph:
            photos[lot] = ph.group(1)
    t = TIME.search(page)
    date = t.group(1)[:10] if t else None
    rows = []
    try:
        text = get(f"{BASE}/catalog/getCsv/id/{cat_id}")
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception as e:
        print(f"  michigan/catalog {cat_id} csv: {e}")
    return date, sold, types, photos, rows


def fetch(counties):
    today = dt.date.today()
    mi = {c["fips"]: c for c in counties if c["state"] == "MI"}
    by_name = {_norm(c["name"]): c["fips"] for c in mi.values()}
    pages = [("upcoming", get(f"{BASE}/auctions"))]
    for year in (today.year, today.year - 1):
        try:
            pages.append((str(year), get(f"{BASE}/pastAuctionsNav", data=urllib.parse.urlencode({"year": year}).encode())))
        except Exception as e:
            print(f"  michigan/past {year}: {e}")
    seen_catalogs = set()
    out = {}
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for label, page_html in pages:
        for auc_id, title, date, catalogs in _entries(page_html):
            for cat_id, county_label in catalogs:
                if cat_id in seen_catalogs:
                    continue
                seen_catalogs.add(cat_id)
                fips = by_name.get(_norm(county_label))
                if not fips:
                    continue
                try:
                    cdate, sold, types, photos, rows = _catalog(cat_id)
                except Exception as e:
                    print(f"  michigan/catalog {cat_id}: {e}")
                    continue
                date = cdate or date
                upcoming = bool(date and date >= today.isoformat())
                parcels = []
                for r in rows:
                    lot = (r.get("Lot Number") or "").strip()
                    wb = sold.get(lot)
                    desc = (r.get("Comment 2") or "").strip()
                    parcels.append(parcel(
                        lot=lot, parcel=(r.get("Parcel Id") or "").strip(), address=(r.get("Address") or "").strip() or None,
                        area=(r.get("Local Unit") or "").strip().title() or None, minBid=money(r.get("Minimum Bid")),
                        taxes=money(r.get("Current Taxes")), sev=money(r.get("SEV")), value=(money(r.get("SEV")) or 0) * 2 or None, winningBid=wb,
                        status="Sold" if wb else ("Listed" if upcoming else "Not published"), type=types.get(lot),
                        lat=_coord(r.get("Latitude")), lon=_coord(r.get("Longitude")), desc=desc[:400] + ("..." if len(desc) > 400 else ""),
                        link=f"{BASE}/listings/catalog/{cat_id}", photo=photos.get(lot), photoCredit="Title Check / tax-sale.info" if photos.get(lot) else None,
                    ))
                variant = ""
                if re.search(r"DNR", county_label):
                    variant = " (DNR parcels)"
                elif re.search(r"re-?offer", county_label, re.I):
                    variant = " (re-offer)"
                rec = out.setdefault(fips, dict(
                    fips=fips, source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                    info=dict(run="County Treasurer", page=f"{BASE}/auctions", schedule="Online, usually a minimum-bid round in July or August and a no-reserve round in the fall",
                              parcel="https://www.tax-sale.info/", note="Catalogs, inspector notes, photos and results come from Title Check's tax-sale.info, which runs the auctions for most Michigan treasurers. County value is twice the State Equalized Value (SEV), since Michigan sets SEV at half of market value."),
                    auctions=[]))
                rec["auctions"].append(auction(
                    id=f"mi-{cat_id}", date=date, kind="list" if upcoming else "results",
                    label=f"{title}{variant} {date or ''}".strip(), source=f"{BASE}/listings/catalog/{cat_id}",
                    status="upcoming" if upcoming else "past", parcels=parcels,
                ))
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
        rec["info"]["page"] = rec["auctions"][0]["source"] if rec["auctions"] else rec["info"]["page"]
    return out
