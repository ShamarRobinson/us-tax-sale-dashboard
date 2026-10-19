"""Arkansas Commissioner of State Lands (https://www.cosl.org): the tax-delinquent parcels certified to the state that did
not sell at the county auctions and are offered online, continuously, at https://auction.cosl.org (the "post-auction
sales"). Every Arkansas county forfeits to the Commissioner, so this is a statewide list.

The listings page loads cards from POST /auctions/get-listings (pageIndex, pageSize, fipsId, acreage filters), each with
the owner, county, parcel number, acreage, starting bid (the taxes, penalties and costs owed) and a link to the listing
page, which adds the delinquent year, legal description, city and addition and the current bid once bidding starts.
/auctions/get-listings-count gives the total. Listings have no sale date: each parcel's auction starts with its first
bid, so the whole list is one ongoing sale dated the day it was read.
"""
import datetime as dt
import html as htmllib
import re
import time
import urllib.parse
import urllib.request
import urllib.error

from . import parcel, auction, money

NAME = "cosl"
LABEL = "Arkansas Commissioner of State Lands"
HOMEPAGE = "https://auction.cosl.org/Auctions/ListingsView"
BASE = "https://auction.cosl.org"
PAGE_SIZE = 200
PAUSE = 0.5
MAX_PAGES = None  # for tests
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

CARD = re.compile(r'data-gisid="(\d+)"(.*?)</div>\s*</div>\s*</div>\s*</div>', re.S)
FIELD = re.compile(r'<label style="font-weight: bold">([^<]+)</label>\s*<br>\s*<label[^>]*>(.*?)</label>', re.S)
LISTING = re.compile(r'href="(/auction/listing/[^"]+)"')
TAGS = re.compile(r"<[^>]+>")


def _post(path, data, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode(),
                                         headers={"User-Agent": BROWSER, "X-Requested-With": "XMLHttpRequest", "Referer": HOMEPAGE})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode("utf-8", "replace")
            time.sleep(PAUSE)
            return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"{BASE}{path}: {last}")


def _text(h):
    return htmllib.unescape(re.sub(r"\s+", " ", TAGS.sub(" ", h or ""))).strip()


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("saint ", "st ").replace("st. ", "st "))


def listings():
    """Every card on the online auction, as (gisId, fields dict, listing path)."""
    params = dict(gisIds="", fipsId=0, lowerA="", upperA="", watched="false", bidding="false", pageIndex=0, pageSize=PAGE_SIZE)
    total = int(re.sub(r"\D", "", _post("/auctions/get-listings-count", params)) or 0)
    out, page = [], 0
    while len(out) < total:
        params["pageIndex"] = page
        chunk = _post("/auctions/get-listings", params)
        cards = CARD.findall(chunk)
        if not cards:
            break
        for gis, body in cards:
            fields = {k.strip(): _text(v) for k, v in FIELD.findall(body)}
            link = LISTING.search(body)
            out.append((gis, fields, link.group(1) if link else None))
        page += 1
        if MAX_PAGES and page >= MAX_PAGES:
            break
    return total, out


def fetch(counties):
    by_name = {_norm(c["name"]): c for c in counties if c["state"] == "AR"}
    today = dt.date.today().isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    total, cards = listings()
    print(f"  cosl: {total} parcels on the online auction, {len(cards)} read")
    groups = {}
    for gis, f, link in cards:
        county = by_name.get(_norm(f.get("County", "")))
        if not county:
            print(f"  cosl: no county match for {f.get('County')!r}")
            continue
        acres = money(f.get("Acres"))
        groups.setdefault(county["fips"], []).append(parcel(
            parcel=f.get("Parcel Number") or None, owner=f.get("Owner") or None, acres=acres if acres else None, minBid=money(f.get("Starting Bid")),
            status="Listed", link=BASE + link if link else None, typeDetail="Tax-delinquent land certified to the state",
        ))
    out = {}
    for fips, ps in groups.items():
        out[fips] = dict(fips=fips, source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                         info=dict(run="Arkansas Commissioner of State Lands (online post-auction sales)", page=HOMEPAGE,
                                   schedule="Continuous: parcels the county auction did not sell are listed online and each parcel's auction starts with its first bid",
                                   note="Starting bids are the taxes, penalties and costs owed. The Commissioner also holds one live auction per county each year; those catalogs are posted at cosl.org."),
                         auctions=[auction(id=f"cosl-online-{today}", date=today, kind="list", saleKind="taxdeed", label="Online post-auction sales (ongoing)",
                                           source=HOMEPAGE, status="upcoming", parcels=ps)])
    return out
