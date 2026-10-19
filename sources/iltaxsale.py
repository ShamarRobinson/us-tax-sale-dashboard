"""ILTaxSale.com (Joseph E. Meyer & Associates, https://iltaxsale.com): the county tax agent for about 95 Illinois
counties, which sells the parcels the counties took by tax deed at annual sealed-bid "surplus" auctions, and lists the
assignable tax certificates for sale.

Each county page (https://iltaxsale.com/new/index.php/county/<Name>/<CODE>) shows the next auction (date, location, type,
minimum bid, removed items; the catalog itself costs $5) and the past auctions with free results PDFs
(https://iltaxsale.com/new/pdf/<CODE>/<CODE><MMYY>Results.pdf): item number, parcel number, township, description,
purchase price and status (SOLD or AVAILABLE). The PDFs are read with sources/pdftext.py, so nothing has to be installed.
"""
import datetime as dt
import html as htmllib
import re
import time
import urllib.error
import urllib.request

from . import parcel, auction, money
from . import pdftext

NAME = "iltaxsale"
LABEL = "ILTaxSale.com (Joseph E. Meyer & Associates)"
HOMEPAGE = "https://iltaxsale.com/new/index.php/main/auctions/"
BASE = "https://iltaxsale.com"
MONTHS_BACK = 14  # the auctions are annual, so a year and a bit catches last year's results for every county
PAUSE = 0.5
MAX_COUNTIES = None  # for tests
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

COUNTY_LINK = re.compile(r'href="https?://(?:www\.)?iltaxsale\.com/new/index\.php/county/([^/"]+)/([A-Z]+)"')
RESULTS_PDF = re.compile(r'href="(https?://(?:www\.)?iltaxsale\.com/new/pdf/([A-Z]+)/\2(\d{4})Results\.pdf)"')
DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
ROW = re.compile(r"^\s*(\d{7}[A-Z]?)\s+(\S.*?)\s{1,}(\S.*?)(?:\s{2,}(\S.*?))?(?:\s{2,}([\d,]+\.\d{2}))?\s{2,}(SOLD|AVAILABLE|UNAVAILABLE|WITHDRAWN|REMOVED|PENDING|REDEEMED|NO SALE)\s*$")
TAGS = re.compile(r"<[^>]+>")


def _get(url, retries=3, binary=False):
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
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("saint ", "st ").replace("st. ", "st "))


def roster():
    page = _get(f"{BASE}/new/index.php")
    seen, out = set(), []
    for name, code in COUNTY_LINK.findall(page):
        if code not in seen:
            seen.add(code)
            out.append((htmllib.unescape(name), code))
    return out


def upcoming(text):
    """(date, type, minBid, location, removed) for the next auction described on a county page, or None."""
    i = text.find("upcoming tax deed auctions")
    j = text.find("previous tax deed auctions")
    chunk = text[i:j if j > i else None]
    if "No auctions scheduled" in chunk:
        return None
    m = DATE.search(chunk)
    if not m:
        return None
    date = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
    loc = re.search(r"Location:\s*(.*?)\s*(?:Hours:|Type:)", chunk)
    typ = re.search(r"Type:\s*(.*?)\s*Min Bid:", chunk)
    mb = re.search(r"Min Bid:\s*\$?([\d,]+\.?\d*)", chunk)
    removed = re.search(r"Removed Items:\s*(.*?)\s*(?:Digital Catalog|Catalog will|Submit|$)", chunk)
    return dict(date=date, type=typ.group(1).strip() if typ else None, minBid=money(mb.group(1)) if mb else None,
                location=loc.group(1).strip() if loc else None, removed=(removed.group(1).strip() if removed and removed.group(1).strip().lower() != "none" else None))


def results_parcels(pdf, fallback_date):
    """Parcels from a results PDF: item number, parcel number, township, description, price, status."""
    pages = pdftext.extract(pdf)
    sale_date = None
    out, section = [], None
    for lines in pages:
        for raw in lines:
            line = raw.rstrip()
            if sale_date is None:
                m = re.search(r"AUCTION\s*-\s*(\d{2})/(\d{2})/(\d{4})", line)
                if m:
                    sale_date = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
            s = line.strip()
            if s in ("Real Estate", "Mobile Homes", "Mobile Home", "Real Estate / Mobile Home"):
                section = s
                continue
            m = ROW.match(line)
            if not m:
                if out and line.startswith(" " * 40) and s and not s.startswith(("ITEM", "PURCHASE", "PRICE", "All requests", "Prepared")):
                    out[-1]["desc"] = (out[-1].get("desc", "") + " " + s).strip()  # a wrapped description line
                continue
            item, pnum, town, desc, price, status = m.groups()
            status = status.strip()
            if status in ("STATUS", "PRICE"):
                continue
            wb = money(price) if price else None
            sold = status.upper().startswith("SOLD")
            out.append(parcel(
                lot=item, parcel=pnum.strip(), area=town.strip() or None, desc=(desc or "").strip() or None, winningBid=wb if sold else None,
                status="Sold" if sold else ("Not sold" if status.upper() == "AVAILABLE" else status.capitalize()),
                typeDetail="Mobile home" if section and "Mobile" in section and "Real" not in section else None,
                soldDate=(sale_date or fallback_date) if sold else None,
            ))
    return sale_date or fallback_date, out


def fetch(counties):
    by_name = {_norm(c["name"]): c for c in counties if c["state"] == "IL"}
    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=30 * MONTHS_BACK)).isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}
    pages = roster()
    if MAX_COUNTIES:
        pages = pages[:MAX_COUNTIES]
    print(f"  iltaxsale: {len(pages)} county pages")
    for name, code in pages:
        county = by_name.get(_norm(name))
        if not county:
            print(f"  iltaxsale/{code}: no county match for {name!r}")
            continue
        url = f"{BASE}/new/index.php/county/{name}/{code}"
        try:
            page = _get(url)
        except RuntimeError as e:
            print(f"  iltaxsale/{code}: {e}")
            continue
        text = _text(re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S))
        nxt = upcoming(text)
        rec = dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                   info=dict(run="County tax agent (Joseph E. Meyer & Associates, ILTaxSale.com) for the County Board", page=url,
                             schedule="Annual sealed-bid auction of the parcels the county took by tax deed; the catalog is sold on iltaxsale.com and the results are posted free",
                             note="Illinois sells tax liens at the annual tax sale (2.5-year redemption); these are the leftover parcels the county took by deed and resells at a sealed-bid auction."),
                   auctions=[])
        aucs = []
        if nxt:
            label = f"Surplus tax deed auction ({nxt['type']})" if nxt.get("type") else "Surplus tax deed auction"
            rec["info"]["auction"] = dict(date=nxt["date"], minBid=nxt.get("minBid"), location=nxt.get("location"), removed=nxt.get("removed"))
            aucs.append(auction(id=f"ilts-{code}-{nxt['date']}", date=nxt["date"], kind="list", saleKind="taxdeed", label=label, source=url,
                                status="upcoming" if nxt["date"] >= today.isoformat() else "past", parcels=[],
                                note=f"Minimum bid {nxt['minBid']:,.2f} per parcel; catalog $5 on iltaxsale.com" + (f"; removed items {nxt['removed']}" if nxt.get("removed") else "") if nxt.get("minBid") else None))
        # the sale dates in the page's table, oldest first, line up with the results PDFs
        prev = text[text.find("previous tax deed auctions"):text.find("assignable tax lien certificates")]
        dates = [f"{y}-{m}-{d}" for m, d, y in DATE.findall(prev)]
        pdfs = RESULTS_PDF.findall(page)
        total = 0
        for href, _code, mmyy in pdfs:
            approx = f"20{mmyy[2:]}-{mmyy[:2]}"
            fallback = next((d for d in dates if d.startswith(approx)), None) or f"{approx}-01"
            if fallback < cutoff:
                continue
            try:
                date, ps = results_parcels(_get(href, binary=True), fallback)
            except (RuntimeError, ValueError) as e:
                print(f"  iltaxsale/{code}: {href}: {e}")
                continue
            if not ps:
                continue
            total += len(ps)
            aucs.append(auction(id=f"ilts-{code}-{date}", date=date, kind="results", saleKind="taxdeed", label="Surplus tax deed auction results", source=href,
                                status="past", parcels=ps))
        if not aucs:
            continue
        rec["auctions"] = sorted(aucs, key=lambda a: a.get("date") or "", reverse=True)
        out[county["fips"]] = rec
        print(f"  iltaxsale/{code}: {county['name']}: {len(aucs)} auctions, {total} parcels in results" + (f", next sale {nxt['date']}" if nxt else ""))
    return out
