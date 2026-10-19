"""Absolute Auctions & Realty (AAR Auctions, https://aarauctions.com, also NYSAuctions.com): the tax foreclosure real
estate auctions it runs for New York counties, cities and towns (Dutchess, Orange, Essex, Orleans, Lewis and others, the
City of Poughkeepsie, the Town of Greenburgh).

The Tax Foreclosures page lists the auctions open for registration with their closing dates; each catalog
(/servlet/Search.do?auctionId=N) lists the lots with a title (lot number, address and municipality), the closing time,
the starting bid and a details block with the description, tax map number, lot size, school district and full market
value. The catalogs are upcoming lists only; AAR takes them down once the sale closes.
"""
import datetime as dt
import html as htmllib
import re
import time
import urllib.error
import urllib.request

from . import parcel, auction, money

NAME = "aarauctions"
LABEL = "AAR Auctions (New York tax foreclosure auctions)"
HOMEPAGE = "https://aarauctions.com/auctions/tax-foreclosures/"
BASE = "https://aarauctions.com"
PAUSE = 0.5
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
# Cities and towns that hold their own tax foreclosure auctions, and the county they sit in.
MUNICIPALITIES = {"poughkeepsie": "Dutchess", "greenburgh": "Westchester", "newburgh": "Orange", "middletown": "Orange", "kingston": "Ulster", "beacon": "Dutchess",
                  "yonkers": "Westchester", "mountvernon": "Westchester", "peekskill": "Westchester", "ramapo": "Rockland", "haverstraw": "Rockland", "amsterdam": "Montgomery"}

AUCTION_LINK = re.compile(r'href="/servlet/Search\.do\?auctionId=(\d+)"')
ITEM_ANCHOR = re.compile(r'<a name="item-(\d+)"></a>')
TITLE = re.compile(r"#\s*([A-Za-z0-9-]+)\s*[–-]\s*(.*?)(?=\s+Closes|\s+More Info|$)", re.S)
TAGS = re.compile(r"<[^>]+>")


def _get(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode("utf-8", "replace")
            time.sleep(PAUSE)
            return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def _text(h):
    return htmllib.unescape(re.sub(r"\s+", " ", TAGS.sub(" ", h or ""))).strip()


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("saint ", "st ").replace("st. ", "st "))


def _date(text):
    """'Wed, Oct. 21, 2026' or 'Oct 21, 2026 10:08:00 AM EST' -> '2026-10-21'."""
    m = re.search(r"\b([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),\s+(\d{4})", text or "")
    if not m or m.group(1) not in MONTHS:
        return None
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


CARD = re.compile(r'<a href="/servlet/Search\.do\?auctionId=(\d+)"><b>(.*?)</b></a>\s*</span>(.*?)</span>', re.S)


def roster():
    """(auctionId, title, closing date, live) for every tax foreclosure auction on the page."""
    page = _get(HOMEPAGE)
    out, seen = [], set()
    for aid, title, when in CARD.findall(page):
        if aid in seen:
            continue
        seen.add(aid)
        when = _text(when)
        out.append((aid, _text(title), _date(when), "Starts at" in when))
    return out


def locality_for(title, counties):
    t = title.replace("Online Only", "").replace("Tax Foreclosure", "").replace("Tax Foreclosed", "")
    m = re.search(r"([A-Z][\w'. ]+?)\s+County\b", t)
    if m and _norm(m.group(1)) in counties:
        return counties[_norm(m.group(1))]
    m = re.search(r"(?:City|Town|Village) of ([A-Z][\w'. ]+?)(?:\s+(?:Online|Tax|Real|Auction)|$|,)", t)
    if m:
        county = MUNICIPALITIES.get(_norm(m.group(1)))
        if county and _norm(county) in counties:
            return counties[_norm(county)]
    return None


def items(aid):
    page = _get(f"{BASE}/servlet/Search.do?auctionId={aid}&categoryName=No+Category&perPage=100")
    anchors = list(ITEM_ANCHOR.finditer(page))
    best = {}  # a lot appears twice on the page (grid tile, then details); keep the richer block
    for i, m in enumerate(anchors):
        chunk = page[m.start():anchors[i + 1].start() if i + 1 < len(anchors) else m.start() + 20000]
        text = _text(re.sub(r"<script.*?</script>|<style.*?</style>", "", chunk, flags=re.S))
        tm = TITLE.search(text)
        if not tm:
            continue
        lot, title = tm.group(1), tm.group(2).strip()
        details = text[text.find("More Details"):] if "More Details" in text else text
        img = re.search(r'<img[^>]+src="(/live/images/[^"]+|https?://[^"]+)"', chunk)
        photo = (BASE + img.group(1) if img.group(1).startswith("/") else img.group(1)) if img else None

        def field(pat, src=details):
            f = re.search(pat, src)
            return f.group(1).strip() if f else None
        desc = field(r"Register\s+(.*?)\s+Tax Map", details) or field(r"Register\s+(.*?)\s+Lot Size", details)
        start = money(field(r"Starting Bid:\s*\$\s*([\d,]+(?:\.\d{2})?)", text))
        value = money(field(r"Full Market Value:\s*\$\s*([\d,]+(?:\.\d{2})?)"))
        tax_map = field(r"Tax Map #?:?\s*([0-9A-Za-z.\-/]+)")
        lot_size = field(r"Lot Size:\s*(.*?)\s+(?:X\s+)?(?:School District|Full Market|Inspection)")
        acres = None
        if lot_size:
            am = re.search(r"([\d.]+)\s*(?:\+/-)?\s*Acre", lot_size, re.I)
            acres = float(am.group(1)) if am else None
        school = field(r"School District:\s*(.*?)\s+(?:Full Market|Inspection|School Tax)")
        addr, _, muni = title.partition(", ")
        muni = re.sub(r"^(?:Town|City|Village) of\s+", "", muni).strip() or None
        built = re.search(r"built\s+(\d{4})", desc or "")
        sqft = re.search(r"([\d,]+)\+?/?-?\s*sq\.?\s*ft", desc or "", re.I)
        br = re.search(r"(\d+)\s*BR", desc or "")
        item = parcel(
            lot=lot, parcel=tax_map, address=addr.strip() or None, fullAddress=f"{addr.strip()}, {muni}, NY" if muni else addr.strip() or None, area=muni,
            minBid=start, value=value, acres=acres, yearBuilt=int(built.group(1)) if built else None, sqft=int(sqft.group(1).replace(",", "")) if sqft else None,
            status="Listed", desc=(desc or "")[:300] or None, typeDetail=(desc or "").split(",")[0][:60] or None,
            photo=photo, photoCredit="AAR Auctions" if photo else None,
            link=f"{BASE}/servlet/Search.do?auctionId={aid}&itemId={m.group(1)}", note=f"School district: {school}" if school else None,
        )
        if m.group(1) not in best or len(item) > len(best[m.group(1)]):
            best[m.group(1)] = item
    return list(best.values())


def fetch(counties):
    ny = {_norm(c["name"]): c for c in counties if c["state"] == "NY"}
    today = dt.date.today().isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}
    try:
        sales = roster()
    except RuntimeError as e:
        print(f"  aarauctions: {e}")
        return out
    print(f"  aarauctions: {len(sales)} tax foreclosure auctions listed")
    for aid, title, date, live in sales:
        county = locality_for(title, ny)
        if not county:
            print(f"  aarauctions/{aid}: no locality match for {title!r}")
            continue
        try:
            ps = items(aid)
        except RuntimeError as e:
            print(f"  aarauctions/{aid}: {e}")
            continue
        date = date or today
        upcoming = date >= today
        rec = out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                 info=dict(run="County Treasurer or Commissioner of Finance through Absolute Auctions & Realty (tax foreclosure auction, online or live with online bidding)", page=HOMEPAGE,
                                                           note="New York counties take title to tax-delinquent parcels by in rem foreclosure and auction them; AAR posts each catalog with full market values and starting bids until the sale closes."),
                                                 auctions=[]))
        rec["auctions"].append(auction(id=f"aar-{aid}", date=date, kind="list", saleKind="taxdeed", label=re.sub(r"\s+", " ", title),
                                       source=f"{BASE}/servlet/Search.do?auctionId={aid}", status="upcoming" if upcoming else "past", parcels=ps))
        print(f"  aarauctions/{aid}: {county['name']}, NY: {len(ps)} parcels, closes {date}")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out
