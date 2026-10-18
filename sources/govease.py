"""GovEase: the online tax sale platform used by counties in Colorado, Tennessee, Pennsylvania, Texas, California,
Indiana, Missouri, Washington, Kansas and Oklahoma (https://www.govease.com/).

Every county auction on liveauctions.govease.com can be browsed without a login. The "Select Auctions" menu on any
browse page lists every open auction as state|slug|id; the public register (/PublicPortal/PublicRegisterAuctions)
gives each auction's name, entity (Treasurer, Public Trustee, Clerk and Master, Tax Claim Bureau), type (Tax Deed,
Tax Lien, Foreclosure, Redeemable Tax Deed) and start date; a browse page links each parcel; the parcel page says when
a live auction ends; and a CSV of every parcel (parcel number, owner, address, starting bid, assessed value, legal and
property descriptions) downloads from one of two endpoints depending on the auction layout. Auctions disappear from
the menu once they close, so results are not published here; what we keep is each sale list with its starting bids.

The site drops connections that arrive too quickly, so requests are paced and retried.
"""
import calendar
import csv
import datetime as dt
import html as htmllib
import http.cookiejar
import io
import re
import time
import urllib.error
import urllib.request

from . import UA, parcel, auction, money

NAME = "govease"
LABEL = "GovEase (online tax sale platform)"
HOMEPAGE = "https://www.govease.com/"
BASE = "https://liveauctions.govease.com"
PAUSE = 1.5

OPTION = re.compile(r'<option value="([a-z]{2}\|[^"|]+\|\d+)"[^>]*>([^<]+)</option>')
SELECT = re.compile(r'<select class="select2 form-control select2countybuilder".*?</select>', re.S)
PARCEL_LINK = re.compile(r'href="(/[a-z]{2}/[^/"]+/\d+/(open(?:standard)?parcel)/(\d+)/[^"]*)"', re.I)
AUCTION_NAME = re.compile(r'no-translate-auctionname">\s*<span class="no-translate">\s*([^<]+?)\s*</span>')
AUCTION_TYPE = re.compile(r'no-translate-auctiontype">\s*<span class="no-translate">\s*([^<]+?)\s*</span>')
REGISTER_ROW = re.compile(r'<tr role="row"[^>]*>\s*<td[^>]*></td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>\s*<span>([^<]*)</span>.*?name="auctionEntry\.AuctionID"[^>]*value="(\d+)"', re.S)
MDY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
BEGIN = re.compile(r"scheduled to (begin|end)\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.I)
ENDED = re.compile(r"auction (?:has )?(?:ended|closed|is closed|is complete)", re.I)
COUNTDOWN = re.compile(r">\s*(\d+)d \d+h\s*<")
MONTH = re.compile(r"\b(" + "|".join(calendar.month_name[1:]) + r")\b")
YEAR = re.compile(r"\b(20\d\d)\b")
ACRES = re.compile(r"Acres?:\s*([\d\.]+)", re.I)
JUDGMENT = re.compile(r"(?:Outstanding Principal Balance|Judgment(?: Amount)?|Amount Due):\s*\$?([\d,]+\.?\d*)", re.I)
VERSUS = re.compile(r"^(.{3,80}?)\s+vs?\.?\s+(.{3,120}?)\s*$", re.I | re.S)
BOILERPLATE = re.compile(r"Auctions are for Assessor Tax Numbers \(ATN\)\..*?based on ATN\.|A transfer tax of \$[\d\.]+ per \$\d+ will be added[^.]*\.", re.S)
RUN_TOGETHER = re.compile(r"(?<=[a-z0-9\.\)])(?=[A-Z][A-Za-z #]{1,40}:)")  # the CSV joins the page's paragraphs with no space
TAGS = re.compile(r"<[^>]+>")
NOISE = re.compile(r"\b(county|reoffer|re-offer|follow-up|followup|upset|judicial|adjourned|continuation|sheriff|sheriffs|sales?|surplus|"
                   r"treasurer's|treasurers|treasurer|deed|tread|lien|foreclosure|notices|posting|special|commissioners?|chancery|circuit|court|"
                   r"auction|nonprofit|post|3rd|listing|tax|city of)\b", re.I)
# auctions named for a city or court rather than a county, keyed by slug
PLACE = {"tncityjackson": "Madison", "gibsonhumboldt": "Gibson", "tngibsontrenton": "Gibson"}
FIRST_TUESDAY_STATES = {"TX"}


class Session:
    """A cookie-carrying client; the CSV export only answers a session that has opened the auction's browse page."""

    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.opener.addheaders = [("User-Agent", UA)]

    def get(self, path, retries=4, timeout=90, data=None):
        last = None
        for attempt in range(retries):
            try:
                with self.opener.open(BASE + path, data=data, timeout=timeout) as r:
                    raw = r.read()
                time.sleep(PAUSE)
                return raw.decode("utf-8", "replace")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
                last = e
                time.sleep(8 * (attempt + 1))
        raise RuntimeError(f"{BASE}{path}: {last}")


def roster(session):
    """Every auction in the site's menu as (state, slug, id, title)."""
    page = session.get("/")
    m = SELECT.search(page)
    if not m:
        raise RuntimeError("GovEase: auction menu not found")
    return [(v.split("|")[0].upper(), v.split("|")[1], v.split("|")[2], htmllib.unescape(t).strip()) for v, t in OPTION.findall(m.group(0))]


def register(session):
    """The public register, keyed by auction id: name, entity, type and start date. The page only renders after the
    site's time zone form has been posted once in the session."""
    out = {}
    try:
        session.get("/PublicPortal/PublicRegisterAuctions")
        try:
            session.get("/PublicPortal/ClientRequestInfo", data=b"hdut=Sat+Jan+01+2026+12%3A00%3A00+GMT-0600&hdps=&hdst=&hdc=&hdci=")
        except RuntimeError:
            pass  # it answers with a redirect to a page that does not exist; the session flag is set regardless
    except RuntimeError as e:
        print(f"  govease/register: {e}")
        return out
    for page_no in range(1, 20):  # 75 auctions per page
        try:
            page = session.get(f"/PublicPortal/PublicRegisterAuctions?pageNumber={page_no}")
        except RuntimeError as e:
            print(f"  govease/register page {page_no}: {e}")
            break
        rows = REGISTER_ROW.findall(page)
        if not rows or all(cid in out for *_, cid in rows):
            break
        for name, state, entity, atype, start, cid in rows:
            m = MDY.search(start)
            out[cid] = dict(name=htmllib.unescape(name).strip(), state=state.strip(), entity=htmllib.unescape(entity).strip(), type=atype.strip(),
                            start=f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None)
    return out


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("saint ", "st "))


def county_for(state, slug, title, csv_name, by_state):
    """Match an auction to a registry county by the CSV's county name, then by the menu title."""
    if slug in PLACE:
        return by_state.get(state, {}).get(_norm(PLACE[slug]))
    names = by_state.get(state, {})
    for raw in (csv_name, title.split(" - ", 1)[-1] if " - " in title else title):
        if not raw:
            continue
        cleaned = _norm(NOISE.sub(" ", raw.replace("(", " ").replace(")", " ")))
        if cleaned in names:
            return names[cleaned]
        hits = [n for n in names if cleaned.startswith(n)]
        if hits:
            return names[max(hits, key=len)]
    return None


def sale_kind(auction_type, name, state):
    t = (auction_type or "").lower()
    n = (name or "").lower()
    if "lien" in t and state != "PA":  # Pennsylvania upset and judicial sales convey a deed, whatever the site calls them
        return "taxlien"
    if "foreclosure" in t or ("foreclosure" in n and "tax" not in n):
        return "foreclosure"
    if state == "TX" or "sheriff" in n or "constable" in n:
        return "sheriff"
    return "taxdeed"


def info_for(kind, state, page, entity=None):
    run = entity.replace("&amp;", "and").replace("&", "and") if entity else None
    if not run:
        run = {"taxlien": "County Treasurer (tax lien sale)", "foreclosure": "Public Trustee or Sheriff (foreclosure sales)" if state == "CO" else "Sheriff or court (foreclosure sales)",
               "sheriff": "County Sheriff or Constable (tax sales and resales)"}.get(kind)
    if not run:
        run = {"PA": "County Tax Claim Bureau (upset and judicial sales)", "TN": "Clerk and Master (delinquent tax sales)", "CA": "County Treasurer-Tax Collector (tax deed sales)",
               "IN": "County Treasurer and Auditor (tax sales)", "CO": "County Treasurer (Treasurer's deed sales)"}.get(state, "County Treasurer or Tax Collector (tax sales)")
    return dict(run=run, page=page, note="Sale lists and starting bids are read from the county's GovEase auction site, which lists each sale until it closes; results are not published there.")


def sale_date(session, state, name, browse_page, link, start=None):
    """(date, status) from the register's start date, the parcel page, the browse page countdown, or the month in the
    auction's name. A sale that started already is live until its posted end date, then past."""
    today = dt.date.today()
    if start and start >= today.isoformat():
        return start, "upcoming"
    if link:
        try:
            text = re.sub(r"\s+", " ", TAGS.sub(" ", re.sub(r"<script.*?</script>", "", session.get(link), flags=re.S)))
        except RuntimeError as e:
            print(f"  govease/parcel {link}: {e}")
            text = ""
        m = BEGIN.search(text)
        if m:
            return f"{m.group(4)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", "upcoming"
        if ENDED.search(text) or start:
            return start, "past"
    m = COUNTDOWN.search(browse_page)
    if m:
        return (today + dt.timedelta(days=int(m.group(1)))).isoformat(), "upcoming"
    mm, yy = MONTH.search(name or ""), YEAR.search(name or "")
    if mm and yy and state in FIRST_TUESDAY_STATES:
        month = list(calendar.month_name).index(mm.group(1))
        first = dt.date(int(yy.group(1)), month, 1)
        d = first + dt.timedelta(days=(1 - first.weekday()) % 7)
        return d.isoformat(), "upcoming" if d >= today else "past"
    return None, "upcoming"


def read_csv(session, state, slug, cid, standard):
    for endpoint in (["CountyOpenStandardAuctionsDownload", "CountyOpenAuctionsDownload"] if standard else ["CountyOpenAuctionsDownload", "CountyOpenStandardAuctionsDownload"]):
        text = session.get(f"/OpenAuction/{endpoint}?stateAbbr={state}&countySlug={slug}&countyID={cid}")
        rows = list(csv.DictReader(io.StringIO(text))) if text.strip() else []
        if rows:
            return rows
    return []


def parcels_from(rows, state, slug, cid, layout, upcoming):
    out = []
    for r in rows:
        g = lambda k: (r.get(k) or "").strip()
        loc = g("Parcel Location")
        desc = RUN_TOGETHER.sub("; ", BOILERPLATE.sub("", re.sub(r"\s+", " ", g("Property Description")))).strip(" ;")
        owner, plaintiff = g("Owner") or None, None
        m = VERSUS.search(owner or "")  # Texas lists the case style, "City of Waco v Jane Doe", as the owner
        if m:
            plaintiff, owner = m.group(1).strip(), m.group(2).strip()
        else:
            m = VERSUS.search(desc) if re.search(r"\bvs?\b", desc, re.I) else None
            if m:
                plaintiff = re.split(r"(?:[.:;]|\s-\s)\s*", m.group(1))[-1].strip(" -:") or None
        acres = ACRES.search(desc)
        judgment = JUDGMENT.search(desc)
        value = money(g("Total True Value")) or money(g("Total Assessed Value")) or None
        out.append(parcel(
            lot=g("Unique #"), parcel=g("Parcel Number"), owner=owner, plaintiff=plaintiff,
            address=loc.split(",")[0].strip() or None, fullAddress=loc or None,
            minBid=money(g("Face Value Owed")) or money(g("Minimum Bid Owed")), value=value or None, acres=float(acres.group(1)) if acres else None,
            judgment=money(judgment.group(1)) if judgment else None,
            status="Listed" if upcoming else "Not published", desc=(desc or re.sub(r"\s+", " ", g("Legal Text")))[:400] or None,
            link=f"{BASE}/{state.lower()}/{slug}/{cid}/{layout}/{g('Auction ID')}/{g('Parcel Number')}" if g("Auction ID") else None,
        ))
    return out


def fetch(counties):
    by_state = {}
    for c in counties:
        by_state.setdefault(c["state"], {})[_norm(c["name"])] = c
    session = Session()
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {}
    listed = roster(session)
    reg = register(session)
    print(f"  govease: {len(listed)} auctions in the menu, {len(reg)} in the register")
    for state, slug, cid, title in listed:
        meta = reg.get(cid) or {}
        browse = f"/{state}/{slug}/{cid}/browsestandard"
        try:
            page = session.get(browse)
        except RuntimeError as e:
            print(f"  govease/{slug}: {e}")
            continue
        links = PARCEL_LINK.findall(page)
        if not links:
            continue  # nothing listed yet
        layout = links[0][1].lower()
        try:
            rows = read_csv(session, state, slug, cid, layout == "openstandardparcel")
        except RuntimeError as e:
            print(f"  govease/{slug} csv: {e}")
            rows = []
        name = meta.get("name") or htmllib.unescape((AUCTION_NAME.search(page) or [None, title])[1]).strip()
        atype = meta.get("type") or htmllib.unescape((AUCTION_TYPE.search(page) or [None, ""])[1]).strip()
        county = county_for(state, slug, title, (rows[0].get("County Name") or "").strip() if rows else "", by_state)
        if not county:
            print(f"  govease/{slug}: no county match for {title!r}")
            continue
        date, status = sale_date(session, state, name, page, links[0][0], meta.get("start"))
        kind = sale_kind(atype, name, state)
        ps = parcels_from(rows, state, slug, cid, layout, status == "upcoming")
        rec = out.setdefault(county["fips"], dict(fips=county["fips"], source=NAME, sourceUrl=HOMEPAGE, lastChecked=checked, lastChanged=None,
                                                 info=info_for(kind, state, BASE + browse, meta.get("entity")), auctions=[]))
        rec["auctions"].append(auction(
            id=f"ge-{cid}-{date or 'tbd'}", date=date, kind="list", saleKind=kind,
            label=f"{name} ({atype})" if atype and atype.lower() not in name.lower() else name, source=BASE + browse, status=status, parcels=ps,
        ))
        print(f"  govease/{slug}: {county['name']}, {state}: {len(ps)} parcels, {date or 'date not posted'}")
    for rec in out.values():
        rec["auctions"].sort(key=lambda a: a.get("date") or "", reverse=True)
    return out
