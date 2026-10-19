"""The Kania Law Firm (https://kanialawfirm.com), tax foreclosure counsel for about two dozen North Carolina counties
and towns (Caldwell, Rowan, Harnett, Person, Burke, Cherokee, Rutherford, Surry, Davie, Cleveland, Davidson,
Mecklenburg, Union and others). Its Tax Sales Listings page is a Ninja Tables table of every parcel the firm has set
for sale or that sits in the ten-day upset bid period: county, address, parcel number, sale date and time, opening bid,
current bid, close of the upset bid period, property type and court file number.

The table is loaded through WordPress's admin-ajax.php (action wp_ajax_ninja_tables_public_action, target
get-all-data) with a table id and a public nonce that the listings page carries, so the adapter reads the page first.

North Carolina sells tax-foreclosed property at a judicial sale on the courthouse steps; the high bid can be raised by
an upset bid of 5% (at least $750) for ten days, and each upset bid restarts the ten days, so a parcel is only sold
once the close date passes without another bid.
"""
import datetime as dt
import html as htmllib
import json
import re
import time
import urllib.error
import urllib.request

from . import parcel, auction, money

NAME = "kania"
LABEL = "The Kania Law Firm (North Carolina tax foreclosure sales)"
HOMEPAGE = "https://kanialawfirm.com/tax-foreclosures/foreclosure-listings/"
BASE = "https://kanialawfirm.com"
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PAUSE = 0.5

TABLE = re.compile(r"action=wp_ajax_ninja_tables_public_action&table_id=(\d+)&target_action=get-all-data[^\"'&]*(?:&[^\"'&]+)*?&ninja_table_public_nonce=([0-9a-f]+)")
TAGS = re.compile(r"<[^>]+>")


def _get(url, headers=None, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER, **(headers or {})})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode("utf-8", "replace")
            time.sleep(PAUSE)
            return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def _lines(h):
    """'a<br />b' -> ['a', 'b'] with tags and entities removed."""
    parts = re.split(r"<br\s*/?>|\n", h or "")
    out = [htmllib.unescape(re.sub(r"\s+", " ", TAGS.sub(" ", p))).strip() for p in parts]
    return [p for p in out if p]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _date(s):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None


def rows():
    page = _get(HOMEPAGE)
    m = TABLE.search(page.replace("&amp;", "&"))
    if not m:
        raise RuntimeError("the listings page no longer carries a Ninja Tables data link")
    table_id, nonce = m.group(1), m.group(2)
    url = (f"{BASE}/wp-admin/admin-ajax.php?action=wp_ajax_ninja_tables_public_action&table_id={table_id}&target_action=get-all-data"
           f"&default_sorting=old_first&skip_rows=0&limit_rows=0&ninja_table_public_nonce={nonce}")
    data = json.loads(_get(url, headers={"Referer": HOMEPAGE, "X-Requested-With": "XMLHttpRequest"}))
    return [r.get("value") or r for r in (data if isinstance(data, list) else data.get("data") or [])]


def fetch(counties):
    by_name = {_norm(c["name"]): c for c in counties if c["state"] == "NC"}
    today = dt.date.today().isoformat()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    try:
        table = rows()
    except (RuntimeError, ValueError) as e:
        print(f"  kania: {e}")
        return {}
    print(f"  kania: {len(table)} parcels listed")
    groups = {}
    for r in table:
        county = by_name.get(_norm(r.get("county")))
        if not county:
            print(f"  kania: no county match for {r.get('county')!r}")
            continue
        sale = _date(r.get("saledatetime"))  # None while the firm says "Sale date not yet set"
        close = _date(r.get("closedate"))
        opening, current = money(re.sub(r"[^0-9.]", "", r.get("openingbid") or "")), money(re.sub(r"[^0-9.]", "", r.get("currentbid") or ""))
        status_text = (r.get("salestatus") or "").strip()
        if not sale or sale > today:
            status = "Listed"
            wb = None
        elif close and close >= today:
            status = "Upset bid period"
            wb = None
        elif current:
            status = "Sold"
            wb = current
        else:
            status = status_text.capitalize() if status_text else "Not published"
            wb = None
        addrs = _lines(r.get("address"))
        pins = _lines(r.get("parcel"))
        tm = re.search(r"(\d{1,2}:\d{2})(?::\d{2})?\s*([AP]M)", r.get("saledatetime") or "", re.I)
        tm_text = f"{tm.group(1)} {tm.group(2).upper()}" if tm else None
        desc_bits = []
        if len(pins) > 1:
            desc_bits.append(f"{len(pins)} parcels sold together: {', '.join(pins)}")
        if current and status != "Sold":
            desc_bits.append(f"Current bid {current:,.2f}, upset bids close {close}" if close else f"Current bid {current:,.2f}")
        first_addr = re.sub(r"^\(\d+\)\s*", "", addrs[0]) if addrs else None
        groups.setdefault((county["fips"], sale, tm_text), []).append(parcel(
            parcel=pins[0] if pins else None, address=first_addr.split(",")[0].strip() if first_addr else None, fullAddress=(first_addr + ", NC") if first_addr else None,
            area=first_addr.split(",")[-1].strip() if first_addr and "," in first_addr else None,
            minBid=opening, winningBid=wb, status=status, caseNo=(r.get("courtfile") or "").strip() or None, lot=(r.get("ourfile") or "").strip() or None,
            typeDetail=(r.get("propertytype") or "").strip() or None, desc="; ".join(desc_bits) or None, soldDate=close if wb else None, link=HOMEPAGE,
        ))
    out = {}
    for (fips, sale, tm), ps in sorted(groups.items(), key=lambda kv: kv[0][1] or "9999", reverse=True):
        upcoming = not sale or sale >= today
        rec = out.setdefault(fips, dict(fips=fips, source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                        info=dict(run="Tax Collector through The Kania Law Firm (judicial tax foreclosure sales with a ten-day upset bid period)", page=HOMEPAGE,
                                                  note="Sales are read from the firm's daily tax sales list: opening bid, current bid and the close of the upset bid period for every parcel it is selling."),
                                        auctions=[]))
        rec["auctions"].append(auction(
            id=f"kania-{fips}-{sale or 'pending'}", date=sale, kind="list" if upcoming else "results", saleKind="taxdeed",
            label=f"Tax foreclosure sale{' at ' + tm if tm else ''}" if sale else "Set for tax foreclosure sale (date not yet set)",
            source=HOMEPAGE, status="upcoming" if upcoming else "past", parcels=ps,
            note=None if sale else "The firm lists these parcels as scheduled for sale shortly; the sale date is posted once the court sets it.",
        ))
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out
