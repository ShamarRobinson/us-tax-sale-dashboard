"""Connecticut municipal tax sales run by Adam J. Cohen of Pullman & Comley (https://cttaxsales.com): the tax collector's
levy and sale of real estate (Conn. Gen. Stat. 12-155 et seq.) for the municipalities the firm represents, with a
six-month redemption period after the auction.

The Upcoming Tax Sales page lists, per municipality, the auction date and place and every property slated for sale (a
link to its notice of levy); the Recently Completed Tax Sales page links the notice of results for each auction, a
prose PDF that names each property, its owner, the buyer and the price. The results notices are read with
sources/pdftext.py. Connecticut municipalities are filed under their counties.
"""
import datetime as dt
import html as htmllib
import re
import time
import urllib.error
import urllib.request

from . import parcel, auction, money
from . import pdftext

NAME = "cttaxsales"
LABEL = "Connecticut Tax Sales (Pullman & Comley)"
HOMEPAGE = "https://cttaxsales.com/upcoming-tax-sales/"
UPCOMING = HOMEPAGE
COMPLETED = "https://cttaxsales.com/recently-completed-tax-sales/"
MONTHS_BACK = 12
PAUSE = 0.5
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

BLOCK = re.compile(r"<p>\s*MUNICIPALITY:\s*(.*?)<br\s*/?>\s*AUCTION DATE:\s*(.*?)<br\s*/?>\s*LOCATION:\s*(.*?)</p>(.*?)(?=<p>\s*MUNICIPALITY:|<hr|</div>)", re.S | re.I)
PROP = re.compile(r'<a href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.S)
RESULT_LINK = re.compile(r'<a href="([^"]+\.pdf)"[^>]*>\s*([A-Z][a-z]+ \d{1,2}(?: and \d{1,2})?, \d{4})\s+(.*?)\s+auction results\s*</a>', re.S)
SOLD = re.compile(r"\bowned\s+(?:by\s+)?(.+?)\s+(?:was|were)\s+sold\s+to\s+(.+?)\s+for\s+\$([\d,]+(?:\.\d{2})?)", re.S)
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
TAGS = re.compile(r"<[^>]+>")

# Connecticut's 169 towns and their planning regions, the county equivalents the Census Bureau (and the registry) use since 2022.
TOWN_COUNTY = {
    "Andover": "Capitol",
    "Ansonia": "Naugatuck Valley",
    "Ashford": "Northeastern Connecticut",
    "Avon": "Capitol",
    "Barkhamsted": "Northwest Hills",
    "Beacon Falls": "Naugatuck Valley",
    "Berlin": "Capitol",
    "Bethany": "South Central Connecticut",
    "Bethel": "Western Connecticut",
    "Bethlehem": "Naugatuck Valley",
    "Bloomfield": "Capitol",
    "Bolton": "Capitol",
    "Bozrah": "Southeastern Connecticut",
    "Branford": "South Central Connecticut",
    "Bridgeport": "Greater Bridgeport",
    "Bridgewater": "Western Connecticut",
    "Bristol": "Naugatuck Valley",
    "Brookfield": "Western Connecticut",
    "Brooklyn": "Northeastern Connecticut",
    "Burlington": "Northwest Hills",
    "Canaan": "Northwest Hills",
    "Canterbury": "Northeastern Connecticut",
    "Canton": "Capitol",
    "Chaplin": "Northeastern Connecticut",
    "Cheshire": "Naugatuck Valley",
    "Chester": "Lower Connecticut River Valley",
    "Clinton": "Lower Connecticut River Valley",
    "Colchester": "Southeastern Connecticut",
    "Colebrook": "Northwest Hills",
    "Columbia": "Capitol",
    "Cornwall": "Northwest Hills",
    "Coventry": "Capitol",
    "Cromwell": "Lower Connecticut River Valley",
    "Danbury": "Western Connecticut",
    "Darien": "Western Connecticut",
    "Deep River": "Lower Connecticut River Valley",
    "Derby": "Naugatuck Valley",
    "Durham": "Lower Connecticut River Valley",
    "East Granby": "Capitol",
    "East Haddam": "Lower Connecticut River Valley",
    "East Hampton": "Lower Connecticut River Valley",
    "East Hartford": "Capitol",
    "East Haven": "South Central Connecticut",
    "East Lyme": "Southeastern Connecticut",
    "East Windsor": "Capitol",
    "Eastford": "Northeastern Connecticut",
    "Easton": "Greater Bridgeport",
    "Ellington": "Capitol",
    "Enfield": "Capitol",
    "Essex": "Lower Connecticut River Valley",
    "Fairfield": "Greater Bridgeport",
    "Farmington": "Capitol",
    "Franklin": "Southeastern Connecticut",
    "Glastonbury": "Capitol",
    "Goshen": "Northwest Hills",
    "Granby": "Capitol",
    "Greenwich": "Western Connecticut",
    "Griswold": "Southeastern Connecticut",
    "Groton": "Southeastern Connecticut",
    "Guilford": "South Central Connecticut",
    "Haddam": "Lower Connecticut River Valley",
    "Hamden": "South Central Connecticut",
    "Hampton": "Northeastern Connecticut",
    "Hartford": "Capitol",
    "Hartland": "Northwest Hills",
    "Harwinton": "Northwest Hills",
    "Hebron": "Capitol",
    "Kent": "Northwest Hills",
    "Killingly": "Northeastern Connecticut",
    "Killingworth": "Lower Connecticut River Valley",
    "Lebanon": "Southeastern Connecticut",
    "Ledyard": "Southeastern Connecticut",
    "Lisbon": "Southeastern Connecticut",
    "Litchfield": "Northwest Hills",
    "Lyme": "Lower Connecticut River Valley",
    "Madison": "South Central Connecticut",
    "Manchester": "Capitol",
    "Mansfield": "Capitol",
    "Marlborough": "Capitol",
    "Meriden": "South Central Connecticut",
    "Middlebury": "Naugatuck Valley",
    "Middlefield": "Lower Connecticut River Valley",
    "Middletown": "Lower Connecticut River Valley",
    "Milford": "South Central Connecticut",
    "Monroe": "Greater Bridgeport",
    "Montville": "Southeastern Connecticut",
    "Morris": "Northwest Hills",
    "Naugatuck": "Naugatuck Valley",
    "New Britain": "Capitol",
    "New Canaan": "Western Connecticut",
    "New Fairfield": "Western Connecticut",
    "New Hartford": "Northwest Hills",
    "New Haven": "South Central Connecticut",
    "New London": "Southeastern Connecticut",
    "New Milford": "Western Connecticut",
    "Newington": "Capitol",
    "Newtown": "Western Connecticut",
    "Norfolk": "Northwest Hills",
    "North Branford": "South Central Connecticut",
    "North Canaan": "Northwest Hills",
    "North Haven": "South Central Connecticut",
    "North Stonington": "Southeastern Connecticut",
    "Norwalk": "Western Connecticut",
    "Norwich": "Southeastern Connecticut",
    "Old Lyme": "Lower Connecticut River Valley",
    "Old Saybrook": "Lower Connecticut River Valley",
    "Orange": "South Central Connecticut",
    "Oxford": "Naugatuck Valley",
    "Plainfield": "Northeastern Connecticut",
    "Plainville": "Capitol",
    "Plymouth": "Naugatuck Valley",
    "Pomfret": "Northeastern Connecticut",
    "Portland": "Lower Connecticut River Valley",
    "Preston": "Southeastern Connecticut",
    "Prospect": "Naugatuck Valley",
    "Putnam": "Northeastern Connecticut",
    "Redding": "Western Connecticut",
    "Ridgefield": "Western Connecticut",
    "Rocky Hill": "Capitol",
    "Roxbury": "Northwest Hills",
    "Salem": "Southeastern Connecticut",
    "Salisbury": "Northwest Hills",
    "Scotland": "Northeastern Connecticut",
    "Seymour": "Naugatuck Valley",
    "Sharon": "Northwest Hills",
    "Shelton": "Naugatuck Valley",
    "Sherman": "Western Connecticut",
    "Simsbury": "Capitol",
    "Somers": "Capitol",
    "South Windsor": "Capitol",
    "Southbury": "Naugatuck Valley",
    "Southington": "Capitol",
    "Sprague": "Southeastern Connecticut",
    "Stafford": "Capitol",
    "Stamford": "Western Connecticut",
    "Sterling": "Northeastern Connecticut",
    "Stonington": "Southeastern Connecticut",
    "Stratford": "Greater Bridgeport",
    "Suffield": "Capitol",
    "Thomaston": "Naugatuck Valley",
    "Thompson": "Northeastern Connecticut",
    "Tolland": "Capitol",
    "Torrington": "Northwest Hills",
    "Trumbull": "Greater Bridgeport",
    "Union": "Northeastern Connecticut",
    "Vernon": "Capitol",
    "Voluntown": "Northeastern Connecticut",
    "Wallingford": "South Central Connecticut",
    "Warren": "Northwest Hills",
    "Washington": "Northwest Hills",
    "Waterbury": "Naugatuck Valley",
    "Waterford": "Southeastern Connecticut",
    "Watertown": "Naugatuck Valley",
    "West Hartford": "Capitol",
    "West Haven": "South Central Connecticut",
    "Westbrook": "Lower Connecticut River Valley",
    "Weston": "Western Connecticut",
    "Westport": "Western Connecticut",
    "Wethersfield": "Capitol",
    "Willington": "Capitol",
    "Wilton": "Western Connecticut",
    "Winchester": "Northwest Hills",
    "Windham": "Southeastern Connecticut",
    "Windsor": "Capitol",
    "Windsor Locks": "Capitol",
    "Wolcott": "Naugatuck Valley",
    "Woodbridge": "South Central Connecticut",
    "Woodbury": "Naugatuck Valley",
    "Woodstock": "Northeastern Connecticut",
}


def _get(url, binary=False, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
            time.sleep(PAUSE)
            return raw if binary else raw.decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def _text(h):
    return htmllib.unescape(re.sub(r"\s+", " ", TAGS.sub(" ", h or ""))).strip()


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _date(text):
    m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", text or "")
    if not m or m.group(1) not in MONTHS:
        return None
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


def town_of(municipality):
    """'City of Hartford', 'Town of Windsor Locks', 'Borough of Naugatuck' -> the town."""
    name = re.sub(r"^(?:City|Town|Borough|Village)\s+of\s+", "", _text(municipality), flags=re.I).strip()
    paren = re.search(r"\(([^)]+)\)\s*$", name)  # 'Oronoque Village Tax District (Stratford)'
    name = re.sub(r"\s*\(.*?\)\s*$", "", name)
    for cand in ([paren.group(1)] if paren else []) + [name]:
        for t in TOWN_COUNTY:
            if _norm(t) == _norm(cand):
                return t
    for t in TOWN_COUNTY:  # a borough or fire district inside a town
        if _norm(t) and _norm(t) in _norm(name):
            return t
    return None


def upcoming():
    page = _get(UPCOMING)
    sales = []
    for muni, when, where, body in BLOCK.findall(page):
        props = [(href, _text(label).rstrip("|").strip()) for href, label in PROP.findall(body)]
        sales.append(dict(municipality=_text(muni), date=_date(_text(when)), when=_text(when), where=_text(where), props=props))
    return sales


def results(cutoff):
    page = _get(COMPLETED)
    out = []
    for href, when, town in RESULT_LINK.findall(page):
        date = _date(when)
        if not date or date < cutoff:
            continue
        try:
            pages = pdftext.extract(_get(href, binary=True))
        except (RuntimeError, ValueError) as e:
            print(f"  cttaxsales: {href}: {e}")
            continue
        text = re.sub(r"\s+", " ", " ".join(" ".join(p) for p in pages))
        text = text[:len(text) // 2 + 200] if pages and len(pages) == 1 and text.count("PROPERTY AUCTION") > 1 else text  # the notice is printed twice
        ps, seen = [], set()
        for m in SOLD.finditer(text):
            before = text[:m.start()]
            addr = re.split(r"[:;]\s+|(?<=[a-z])\.\s+|(?<=\d)\.\s+(?=[A-Z\d\u00b1])|\s+and\s+(?=\d)|\bauctioned\s+(?!the following)", before)[-1].strip(" ,")
            addr = re.sub(r"^(?:The\s+)?(?:property\s+(?:at|known\s+as)\s+)?", "", addr, flags=re.I).strip()
            addr = re.sub(r"\s+in\s+" + re.escape(town) + r"\s*$", "", addr, flags=re.I).strip()
            owner, buyer, price = (x.strip() for x in m.groups())
            if not addr or addr in seen:
                continue
            seen.add(addr)
            ps.append(parcel(address=addr, fullAddress=f"{addr}, {town} CT", area=town, owner=owner, buyer=re.sub(r"\s+of\s+\d.*$", "", buyer), winningBid=money(price),
                             status="Sold", soldDate=date, sourceDoc=href))
        out.append(dict(town=_text(town), date=date, href=href, parcels=ps))
    return out


def fetch(counties):
    by_name = {_norm(c["name"]): c for c in counties if c["state"] == "CT"}
    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=30 * MONTHS_BACK)).isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}

    def record(town):
        county = by_name.get(_norm(TOWN_COUNTY.get(town, "")))
        if not county:
            return None
        return out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                  info=dict(run="Municipal Tax Collector (tax sale of real estate, Conn. Gen. Stat. 12-155; six-month redemption)", page=HOMEPAGE,
                                                            note="Connecticut tax sales are held by each town's tax collector; the ones Pullman & Comley runs are read from cttaxsales.com and filed under the county."),
                                                  auctions=[]))

    try:
        sales = upcoming()
    except RuntimeError as e:
        print(f"  cttaxsales: {e}")
        sales = []
    n = 0
    for s in sales:
        town = town_of(s["municipality"])
        rec = record(town) if town else None
        if not rec:
            print(f"  cttaxsales: no town match for {s['municipality']!r}")
            continue
        date = s["date"] or today.isoformat()
        ps = [parcel(address=label.split(",")[0].strip(), fullAddress=label, area=town, status="Listed", sourceDoc=href, link=href) for href, label in s["props"]]
        n += len(ps)
        rec["auctions"].append(auction(id=f"ctts-{_norm(s['municipality'])}-{date}", date=date, kind="list", saleKind="taxdeed",
                                       label=f"{s['municipality']} tax sale" + (f", {s['where'][:70]}" if s["where"] else ""), source=HOMEPAGE,
                                       status="upcoming" if date >= today.isoformat() else "past", parcels=ps, note=s["when"] or None))
    try:
        done = results(cutoff)
    except RuntimeError as e:
        print(f"  cttaxsales: {e}")
        done = []
    m = 0
    for r in done:
        town = town_of(r["town"])
        rec = record(town) if town else None
        if not rec:
            print(f"  cttaxsales: no town match for {r['town']!r}")
            continue
        m += len(r["parcels"])
        rec["auctions"].append(auction(id=f"ctts-{_norm(r['town'])}-{r['date']}-results", date=r["date"], kind="results", saleKind="taxdeed",
                                       label=f"{r['town']} tax sale results", source=r["href"], status="past", parcels=r["parcels"]))
    print(f"  cttaxsales: {len(sales)} upcoming sales with {n} properties, {len(done)} completed sales with {m} sold")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out
