"""RealAuction portals: Florida Clerk tax deed sales ({county}.realtaxdeed.com), Florida Clerk foreclosure sales
({county}.realforeclose.com) and Ohio's statewide sheriff sale portal ({county}.sheriffsaleauction.ohio.gov).

All three run the same software and expose the same public, login-free pages:
  calendar   index.cfm?zaction=USER&zmethod=CALENDAR&selCalDate=MM/DD/YYYY
             CALBOX divs with dayid="MM/DD/YYYY", a <b>label</b>, and CALACT / CALSCH counts
  preview    index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=MM/DD/YYYY   (sets the session's sale date)
  page load  index.cfm?zaction=AUCTION&Zmethod=UPDATE&FNC=LOAD&AREA=W|C&PageDir=0|1&doR=1&bypassPage=0&test=1
             JSON {retHTML, rlist}; retHTML uses @A..@L tokens that stand for common HTML fragments
  status     index.cfm?zaction=AUCTION&ZMETHOD=UPDATE&FNC=UPDATE&ref=ID,ID,   (only the page the session is on)
             JSON {ADATA: {AITEM: [{AID, A: "Auction Sold"|"B", B: date|"Withdrawn"|"Redeemed"|..., D: amount, ST: sold to}]}}
Counties are probed by host name; the ones that do not resolve are skipped.

The portals answer data-center addresses (GitHub's runners included) with the RealAuction marketing page instead of a
calendar, so this adapter only succeeds from an ordinary connection. collect_local.py runs it on a home machine, and
tools/realauction_console.js does the same job from a browser tab; both drop files that the next refresh keeps.
"""
import concurrent.futures
import datetime as dt
import html as htmllib
import http.cookiejar
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from . import UA, parcel, auction, money

NAME = "realauction"
LABEL = "RealAuction portals (Florida, Arizona and Colorado tax deed sales, Clerk and Public Trustee foreclosure sales, Ohio and Texas sheriff sales)"
HOMEPAGE = "https://www.realauction.com/"

TOKENS = [("@A", '<div class="'), ("@B", "</div>"), ("@C", 'class="'), ("@D", "<div>"), ("@E", "AUCTION"), ("@F", "</td><td"),
          ("@G", "</td></tr>"), ("@H", "<tr><td "), ("@I", "table"), ("@J", 'p_back="NextCheck='), ("@K", 'style="Display:none"'),
          ("@L", "/index.cfm?zaction=auction&zmethod=details&AID=")]
CALBOX = re.compile(r'<div[^>]*class=[\'"]CALBOX[^\'"]*[\'"][^>]*dayid=[\'"](\d\d/\d\d/\d{4})[\'"][^>]*>(.*?)</div>', re.S)
CALLABEL = re.compile(r'class=[\'"]CALTEXT[\'"][^>]*>(.*?)<br>|<b>(.*?)</b>', re.S)
CALNUM = re.compile(r'class=[\'"](CALACT|CALSCH)[\'"]>\s*(\d+)')
ITEM = re.compile(r'id="AITEM_(\d+)"(.*?)(?=<div[^>]*id="AITEM_|$)', re.S)
ROW = re.compile(r'<t[dh][^>]*class="AD_LBL"[^>]*>(.*?)</t[dh]>\s*<td[^>]*class="AD_DTA[^"]*"[^>]*>(.*?)(?:</td>|$)', re.S)
HREF = re.compile(r'href="([^"]+)"')
MAXP = re.compile(r'id="max(WA|CA)">\s*(\d+)')
PAGEOF = re.compile(r"page \d+ of (\d+)")

# Months back to collect results, by portal kind. Upcoming sales are always collected.
MONTHS_BACK = {"taxdeed": 6, "foreclosure": 2, "sheriff": 3}
KIND_LABEL = {"taxdeed": "Tax deed sale", "foreclosure": "Foreclosure sale", "sheriff": "Sheriff sale"}
PAUSE = 0.25
THREADS = 6  # portals collected at once; 212 portals took the GitHub runner 2 hours 42 minutes one at a time


def info_for(kind, state, base):
    """Who runs the sale and what the portal is, for the county page."""
    if kind == "taxdeed" and state == "AZ":
        return dict(run="Board of Supervisors (tax deed land sales)", page=base, note="Tax deed sales are read from the county's RealAuction tax deed portal.")
    if kind == "taxdeed" and state == "CO":
        return dict(run="County Treasurer (Treasurer's deed sales)", page=base, note="Treasurer's deed sales are read from the Treasurer's RealAuction portal; foreclosure sales from the Public Trustee's portal where it exists.")
    if kind == "taxdeed":
        return dict(run="Clerk of the Court (tax deeds)", page=base, note="Tax deed auctions are read from the Clerk's RealTaxDeed portal; foreclosure sales from the Clerk's RealForeclose portal where it exists.")
    if kind == "sheriff" and state == "OH":
        return dict(run="County Sheriff (foreclosure and tax foreclosure sales)", page=base, note="Sales are read from Ohio's statewide online sheriff sale portal.")
    if kind == "sheriff":
        return dict(run="County Sheriff or Constable (tax sales, resales and foreclosure sales)", page=base, note="Sales are read from the county's online sheriff sale portal.")
    if state == "CO":
        return dict(page=base, note="Foreclosure sales are read from the Public Trustee's RealAuction portal.")
    if state == "NJ":
        return dict(page=base, note="Sheriff foreclosure sales are read from the municipality's RealAuction portal.")
    return dict(page=base, note="Foreclosure sales are read from the Clerk's RealForeclose portal.")


def _host(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


# Every portal RealAuction runs, taken from the "Jump To" menu each portal carries (October 2026), keyed by state and
# the county name used in the registry. Kinds: taxdeed (Clerk tax deed sales in Florida, Board of Supervisors tax deed
# sales in Arizona, Treasurer's deed sales in Colorado) and foreclosure (Clerk, Public Trustee or Sheriff foreclosure
# sales). Counties missing here have no RealAuction portal: their hostnames answer with the marketing page.
SITES = {
    "AZ": {
        "Apache": {"taxdeed": "apache.realtaxdeed.com"},
        "Coconino": {"taxdeed": "coconino.realtaxdeed.com"},
        "Mohave": {"taxdeed": "mohave.realtaxdeed.com"},
    },
    "CO": {
        "Adams": {"taxdeed": "adams.treasurersdeedsale.realtaxdeed.com", "foreclosure": "adams.realforeclose.com"},
        "Denver": {"taxdeed": "denver.treasurersdeedsale.realtaxdeed.com", "foreclosure": "denver.realforeclose.com"},
        "Eagle": {"taxdeed": "eagle.treasurersdeedsale.realtaxdeed.com", "foreclosure": "eagle.realforeclose.com"},
        "El Paso": {"taxdeed": "elpasoco.treasurersdeedsale.realtaxdeed.com", "foreclosure": "elpasoco.realforeclose.com"},
        "Larimer": {"taxdeed": "larimer.treasurersdeedsale.realtaxdeed.com", "foreclosure": "larimer.realforeclose.com"},
        "Mesa": {"taxdeed": "mesa.treasurersdeedsale.realtaxdeed.com", "foreclosure": "mesa.realforeclose.com"},
        "Pitkin": {"taxdeed": "pitkin.treasurersdeedsale.realtaxdeed.com"},
        "Summit": {"foreclosure": "summit.realforeclose.com"},
        "Weld": {"taxdeed": "weld.treasurersdeedsale.realtaxdeed.com", "foreclosure": "weld.realforeclose.com"},
    },
    "FL": {
        "Alachua": {"taxdeed": "alachua.realtaxdeed.com", "foreclosure": "alachua.realforeclose.com"},
        "Baker": {"foreclosure": "baker.realforeclose.com"},
        "Bay": {"taxdeed": "bay.realtaxdeed.com", "foreclosure": "bay.realforeclose.com"},
        "Brevard": {"foreclosure": "brevard.realforeclose.com"},
        "Broward": {"taxdeed": "broward.realtaxdeed.com", "foreclosure": "broward.realforeclose.com"},
        "Calhoun": {"foreclosure": "calhoun.realforeclose.com"},
        "Charlotte": {"foreclosure": "charlotte.realforeclose.com"},
        "Citrus": {"taxdeed": "citrus.realtaxdeed.com"},
        "Clay": {"taxdeed": "clay.realtaxdeed.com", "foreclosure": "clay.realforeclose.com"},
        "Duval": {"taxdeed": "duval.realtaxdeed.com", "foreclosure": "duval.realforeclose.com"},
        "Escambia": {"taxdeed": "escambia.realtaxdeed.com", "foreclosure": "escambia.realforeclose.com"},
        "Flagler": {"taxdeed": "flagler.realtaxdeed.com", "foreclosure": "flagler.realforeclose.com"},
        "Gilchrist": {"taxdeed": "gilchrist.realtaxdeed.com", "foreclosure": "gilchrist.realforeclose.com"},
        "Gulf": {"taxdeed": "gulf.realtaxdeed.com", "foreclosure": "gulf.realforeclose.com"},
        "Hendry": {"taxdeed": "hendry.realtaxdeed.com"},
        "Hernando": {"taxdeed": "hernando.realtaxdeed.com"},
        "Highlands": {"taxdeed": "highlands.realtaxdeed.com"},
        "Hillsborough": {"taxdeed": "hillsborough.realtaxdeed.com", "foreclosure": "hillsborough.realforeclose.com"},
        "Indian River": {"taxdeed": "indian-river.realtaxdeed.com", "foreclosure": "indian-river.realforeclose.com"},
        "Jackson": {"taxdeed": "jackson.realtaxdeed.com", "foreclosure": "jackson.realforeclose.com"},
        "Lake": {"taxdeed": "lake.realtaxdeed.com"},
        "Lee": {"taxdeed": "lee.realtaxdeed.com", "foreclosure": "lee.realforeclose.com"},
        "Leon": {"taxdeed": "leon.realtaxdeed.com", "foreclosure": "leon.realforeclose.com"},
        "Manatee": {"foreclosure": "manatee.realforeclose.com"},
        "Marion": {"taxdeed": "marion.realtaxdeed.com", "foreclosure": "marion.realforeclose.com"},
        "Martin": {"taxdeed": "martin.realtaxdeed.com", "foreclosure": "martin.realforeclose.com"},
        "Miami-Dade": {"taxdeed": "miamidade.realtaxdeed.com", "foreclosure": "miamidade.realforeclose.com"},
        "Monroe": {"taxdeed": "monroe.realtaxdeed.com"},
        "Nassau": {"taxdeed": "nassau.realtaxdeed.com", "foreclosure": "nassauclerk.realforeclose.com"},
        "Okeechobee": {"foreclosure": "okeechobee.realforeclose.com"},
        "Orange": {"taxdeed": "orange.realtaxdeed.com", "foreclosure": "myorangeclerk.realforeclose.com"},
        "Osceola": {"taxdeed": "osceola.realtaxdeed.com"},
        "Palm Beach": {"taxdeed": "palmbeach.realtaxdeed.com", "foreclosure": "palmbeach.realforeclose.com"},
        "Pasco": {"taxdeed": "pasco.realtaxdeed.com", "foreclosure": "pasco.realforeclose.com"},
        "Pinellas": {"taxdeed": "pinellas.realtaxdeed.com", "foreclosure": "pinellas.realforeclose.com"},
        "Polk": {"taxdeed": "polk.realtaxdeed.com", "foreclosure": "polk.realforeclose.com"},
        "Putnam": {"taxdeed": "putnam.realtaxdeed.com", "foreclosure": "putnam.realforeclose.com"},
        "St. Johns": {"foreclosure": "saintjohns.realforeclose.com"},
        "St. Lucie": {"foreclosure": "stlucie.realforeclose.com"},
        "Santa Rosa": {"taxdeed": "santarosa.realtaxdeed.com", "foreclosure": "santarosa.realforeclose.com"},
        "Sarasota": {"taxdeed": "sarasota.realtaxdeed.com", "foreclosure": "sarasota.realforeclose.com"},
        "Seminole": {"taxdeed": "seminole.realtaxdeed.com", "foreclosure": "seminole.realforeclose.com"},
        "Suwannee": {"taxdeed": "suwannee.realtaxdeed.com"},
        "Volusia": {"taxdeed": "volusia.realtaxdeed.com", "foreclosure": "volusia.realforeclose.com"},
        "Walton": {"foreclosure": "walton.realforeclose.com"},
        "Washington": {"taxdeed": "washington.realtaxdeed.com", "foreclosure": "washington.realforeclose.com"},
    },
    "NJ": {
        "Sussex": {"foreclosure": "hardystonnj.realforeclose.com"},  # Hardyston Township
        "Essex": {"foreclosure": "newarknj.realforeclose.com"},  # City of Newark
    },
}


# Texas counties whose sheriff sale portal (<county>.texas.sheriffsaleauctions.com) actually exists. The other 226
# hostnames do not resolve (checked from a browser in October 2026), so the adapter skips them.
TX_SHERIFF = frozenset("""
angelina aransas atascosa bexar brooks caldwell cameron cherokee dallas elpaso ellis fortbend galveston gregg harris
hidalgo hopkins jackson kaufman llano matagorda nueces orange rusk sanpatricio smith victoria wilson
""".split())


def sites_for(counties):
    """Yield (fips, kind, base_url) for every county that has a portal (tax deed portals first)."""
    for c in counties:
        hosts = SITES.get(c["state"], {}).get(c["name"])
        if hosts:
            for kind in ("taxdeed", "foreclosure"):
                if hosts.get(kind):
                    yield c["fips"], kind, f"https://{hosts[kind]}"
        elif c["state"] == "OH":
            yield c["fips"], "sheriff", f"https://{_host(c['name'])}.sheriffsaleauction.ohio.gov"
        elif c["state"] == "TX" and _host(c["name"]) in TX_SHERIFF:
            yield c["fips"], "sheriff", f"https://{_host(c['name'])}.texas.sheriffsaleauctions.com"


class Site:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9", "Connection": "keep-alive",
    }

    def get(self, path, timeout=40):
        hdrs = dict(self.HEADERS)
        if "Zmethod=UPDATE" in path or "ZMETHOD=UPDATE" in path:
            hdrs.update({"Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest", "Referer": self.base + "/index.cfm?zaction=USER&zmethod=CALENDAR"})
        req = urllib.request.Request(self.base + path, headers=hdrs)
        with self.opener.open(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def resolves(self):
        host = urllib.parse.urlparse(self.base).hostname
        try:
            socket.gethostbyname(host)
            return True
        except socket.gaierror:
            return False

    def calendar(self, year, month):
        txt = self.get(f"/index.cfm?zaction=USER&zmethod=CALENDAR&selCalDate={month:02d}/01/{year}")
        if "CALBOX" not in txt:
            # a first visit sometimes answers with an interstitial that sets a cookie; try once more with the jar warmed
            time.sleep(PAUSE)
            txt = self.get(f"/index.cfm?zaction=USER&zmethod=CALENDAR&selCalDate={month:02d}/01/{year}")
        if "CALBOX" not in txt and not getattr(self, "_debugged", False):
            self._debugged = True
            t = re.search(r"<title>(.*?)</title>", txt, re.S)
            print(f"  realauction/{self.base}: no calendar in the page (title: {(t.group(1).strip() if t else '')[:60]!r}, {len(txt)} chars, starts {txt[:160]!r})")
        days = []
        for day, body in CALBOX.findall(txt):
            lab = CALLABEL.search(body)
            nums = dict((k, int(v)) for k, v in CALNUM.findall(body))
            if not lab and not nums:
                continue
            days.append(dict(date=day, label=htmllib.unescape(re.sub(r"<[^>]+>", "", lab.group(1) or lab.group(2) or "")).strip() if lab else "Sale",
                             active=nums.get("CALACT", 0), scheduled=nums.get("CALSCH", 0)))
        return days

    def load(self, area, pagedir):
        txt = self.get(f"/index.cfm?zaction=AUCTION&Zmethod=UPDATE&FNC=LOAD&AREA={area}&PageDir={pagedir}&doR=1&tx={int(time.time()*1000)}&bypassPage=0&test=1")
        j = json.loads(txt.strip())
        h = j.get("retHTML", "")
        for a, b in TOKENS:
            h = h.replace(a, b)
        return h, [x for x in (j.get("rlist") or "").split(",") if x]

    def status(self, ids):
        """Statuses for the items on the page the session is currently on (the portal ignores other ids)."""
        out = {}
        if not ids:
            return out
        txt = self.get(f"/index.cfm?zaction=AUCTION&ZMETHOD=UPDATE&FNC=UPDATE&ref={','.join(ids)},&tx={int(time.time()*1000)}")
        try:
            j = json.loads(txt.strip())
        except ValueError:
            return out
        for it in (j.get("ADATA") or {}).get("AITEM") or []:
            out[str(it.get("AID"))] = it
        time.sleep(PAUSE)
        return out


def parse_items(h):
    items = []
    for aid, body in ITEM.findall(h):
        rows = {}
        links = {}
        extra_lines = []
        for k, v in ROW.findall(body):
            k = htmllib.unescape(re.sub(r"<[^>]+>", "", k)).strip().rstrip(":").strip()
            href = HREF.search(v)
            v = htmllib.unescape(re.sub(r"<[^>]+>", " ", v)).strip()
            v = re.sub(r"\s+", " ", v)
            if not k:
                extra_lines.append(v)
            elif k not in rows:
                rows[k] = v
                if href:
                    links[k] = href.group(1)
        items.append((aid, rows, extra_lines, links))
    return items


def to_parcel(aid, rows, extra, st, base, upcoming, links=None):
    links = links or {}
    addr = rows.get("Property Address") or rows.get("Address")
    city = extra[0] if extra else None
    full = ", ".join(x for x in (addr, city) if x) or None
    zip_m = re.search(r"(\d{5})(?:-\d{4})?\s*$", city or "")
    status = "Listed"
    wb = buyer = None
    sold_date = None
    if st:
        if (st.get("A") or "").lower().startswith("auction sold"):
            status = "Sold"
            wb = money(st.get("D")) or money(st.get("P"))
            buyer = (st.get("ST") or "").strip() or None
            sold_date = st.get("B")
        elif st.get("B") in ("Withdrawn", "Canceled", "Cancelled", "Rescheduled", "Redeemed", "Bankruptcy"):
            status = st.get("B")
        elif not upcoming:
            status = "Not published"
    elif not upcoming:
        status = "Not published"
    return parcel(
        parcel=next((rows[k] for k in PARCEL_KEYS if rows.get(k)), None),
        caseNo=rows.get("Case #") or rows.get("Case Number"), certificate=rows.get("Certificate #"),
        address=addr, fullAddress=full, area=city.split(",")[0].strip().title() if city else None, zip=zip_m.group(1) if zip_m else None,
        parcelInfo=next((links[k] for k in PARCEL_KEYS if links.get(k)), None),
        minBid=money(rows.get("Opening Bid")), value=money(rows.get("Assessed Value") or rows.get("Appraised Value")),
        judgment=money(rows.get("Final Judgment Amount")), type=rows.get("Auction Type"), owner=rows.get("Owner") or rows.get("Defendant"),
        plaintiff=rows.get("Plaintiff"), winningBid=wb, buyer=buyer, status=status, soldDate=sold_date,
        link=f"{base}/index.cfm?zaction=auction&zmethod=details&AID={aid}",
    )


PARCEL_ISH = re.compile(r"\d")
# Row labels the portals use for the parcel number (Hernando says "Parcel Key", Miami-Dade "Folio", and so on).
PARCEL_KEYS = ["Parcel ID", "Parcel Number", "Parcel Key", "Parcel No", "Parcel #", "Parcel", "Folio", "Folio Number", "Alternate Key", "Alt Key",
               "Tax ID", "Property ID", "Account #", "Account Number", "Strap", "PIN", "Schedule Number", "Schedule #", "Schedule No"]


def clean_auctions(auctions, kind):
    """Tidy portal output in place: drop link text stored as a parcel number ("Property Appraiser", "MULTIPLE PARCELS"),
    drop appraiser links with no folio, tag every sale with the portal it came from, and type a sale day by what was
    sold on it (Florida tax deed portals also list the Clerk's foreclosure sales)."""
    for a in auctions:
        a["portal"] = kind
        types = set()
        for p in a.get("parcels") or []:
            v = p.get("parcel")
            if v and not PARCEL_ISH.search(v):
                if "multiple" in v.lower():
                    p["note"] = "Multiple parcels; see the listing"
                p.pop("parcel", None)
            info = p.get("parcelInfo") or ""
            if info.endswith(("folio=", "parcel=", "id=", "=")):
                p.pop("parcelInfo", None)
            fa = p.get("fullAddress") or ""
            z = re.search(r"(\d{5})(?:-?\d{4})?\s*$", fa)
            if z:
                p["zip"] = z.group(1)  # nine-digit ZIPs without a hyphen used to yield the last five digits
                p["fullAddress"] = re.sub(r"\s*,\s*(\d{5})(\d{4})\s*$", r", \1", fa)
            if p.get("type"):
                types.add(p["type"].strip().upper())
        label = (a.get("label") or "").lower()
        if kind == "taxdeed" and (types == {"FORECLOSURE"} or (not types and label.startswith("foreclosure"))):
            a["saleKind"] = "foreclosure"
        elif kind == "taxdeed":
            a["saleKind"] = "taxdeed"
        else:
            a["saleKind"] = a.get("saleKind") or kind
    return auctions


def collect_day(site, day, kind, base, upcoming):
    """All items for one sale date, with status."""
    site.get(f"/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={day}")
    time.sleep(PAUSE)
    items = []
    seen_all = set()
    st = {}
    for area in ("W", "C"):
        seen = set()
        pagedir = 0
        for _ in range(120):
            h, rlist = site.load(area, pagedir)
            time.sleep(PAUSE)
            new = [r for r in rlist if r not in seen]
            if not new:
                break
            seen.update(rlist)
            for it in parse_items(h):
                if it[0] not in seen_all:
                    seen_all.add(it[0])
                    items.append(it)
            # the portal only answers status questions about the page the session is on, so ask after every page
            st.update(site.status(rlist))
            pagedir = 1
    return [to_parcel(aid, rows, extra, st.get(aid), base, upcoming, links) for aid, rows, extra, links in items]


def collect_site(fips, kind, base, today):
    """Every sale day with items on one portal: (auctions, refusal). Each portal has its own session, so portals are
    collected in parallel threads; one portal's requests stay sequential and paced."""
    site = Site(base)
    if not site.resolves():
        return [], None
    months = []
    y, m = today.year, today.month
    for back in range(-2, MONTHS_BACK[kind] + 1):
        yy, mm = y, m - back
        while mm < 1:
            mm += 12; yy -= 1
        while mm > 12:
            mm -= 12; yy += 1
        months.append((yy, mm))
    days = {}
    for yy, mm in months:
        try:
            for d in site.calendar(yy, mm):
                if d["active"] or d["scheduled"]:
                    days[d["date"]] = d
        except urllib.error.HTTPError as e:
            return [], f"{urllib.parse.urlparse(base).hostname}: HTTP {e.code}"
        except Exception as e:
            return [], f"{urllib.parse.urlparse(base).hostname}: {str(e)[:80]}"
        time.sleep(PAUSE)
    aucs = []
    for day in sorted(days, key=lambda s: (s[6:], s[:2], s[3:5])):
        iso = f"{day[6:]}-{day[:2]}-{day[3:5]}"
        upcoming = iso >= today.isoformat()
        try:
            ps = collect_day(site, day, kind, base, upcoming)
        except Exception as e:
            print(f"  realauction/{base} {day}: {e}")
            continue
        if not ps:
            continue
        lab = days[day]["label"] or KIND_LABEL[kind]
        aucs.append(auction(id=f"ra-{kind}-{fips}-{iso}", date=iso, kind="list" if upcoming else "results",
                            label=f"{lab} {iso}", source=f"{base}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={day}",
                            saleKind=kind, status="upcoming" if upcoming else "past", parcels=ps))
    return aucs, None


def fetch(counties):
    today = dt.date.today()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    by_fips = {c["fips"]: c for c in counties}
    out = {}
    refused = []
    sites = list(sites_for(counties))

    def job(args):
        fips, kind, base = args
        try:
            return collect_site(fips, kind, base, today)
        except Exception as e:
            print(f"  realauction/{base}: {e}")
            return [], None

    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = pool.map(job, sites)
        for (fips, kind, base), (aucs, blocked) in zip(sites, results):
            c = by_fips[fips]
            if blocked:
                refused.append(blocked)
            if not aucs:
                continue
            clean_auctions(aucs, kind)
            rec = out.setdefault(fips, dict(fips=fips, source=NAME, sourceUrl=base, lastChecked=checked, lastChanged=None, info={}, auctions=[]))
            rec["auctions"].extend(aucs)
            info = rec["info"]
            new_info = info_for(kind, c["state"], base)
            if kind != "foreclosure" or "page" not in info:
                info.update(new_info)
            print(f"  {c['label']}, {c['state']} {kind}: {len(aucs)} sale days, {sum(len(a['parcels']) for a in aucs)} items")
    if refused:
        print(f"  {len(refused)} portals refused or unreachable, e.g. {'; '.join(refused[:5])}")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out
