"""Metro Atlanta Tax Sale Tracker: 40 Georgia counties, read from that project's published data on GitHub."""
import datetime as dt

from . import get_json, parcel, auction

NAME = "atlanta"
LABEL = "Metro Atlanta Tax Sale Tracker"
HOMEPAGE = "https://shamarrobinson.github.io/atlanta-tax-sale-dashboard/"
RAW = "https://raw.githubusercontent.com/ShamarRobinson/atlanta-tax-sale-dashboard/main/data/"

KIND_LABEL = {"list": "Sale list", "results": "Results", "excess": "Excess funds list"}

# qPublic application ids per county: [AppID, LayerID, record PageID, map PageID]; DeKalb has its own appraisal site
QP = {"fulton": [936, 18251, 8156, 8153], "cobb": [1051, 23951, 9969, 9966], "clayton": [1234, 39180, 14580, 14577], "gwinnett": [1282, 43872, 16060, 16057], "henry": [1035, 22139, 15803, 9365],
      "douglas": [988, 20162, 8762, 8759], "rockdale": [694, 11394, 4834, None], "fayette": [942, 18406, 8206, 8203], "coweta": [704, 11412, 4878, None], "walton": [628, 11921, 5798, None], "forsyth": [1027, 21667, 9230, 9227],
      "carroll": [663, 15076, 6801, 0], "clarke": [630, 11199, 4601, 0], "dawson": [676, 11636, 5339, 0], "floyd": [802, 13374, 6034, 0], "heard": [701, 11409, 4864, 0], "jackson": [797, 11838, 5759, 0], "lumpkin": [991, 20168, 8782, 8779],
      "meriwether": [775, 11811, 5653, 0], "pickens": [627, 11193, 4592, 0], "polk": [690, 11379, 4806, 0], "spalding": [766, 11802, 5608, 0], "troup": [633, 18434, 8224, 0]}


def _pad7(t):
    return t[0].ljust(7) + " ".join(t[1:])


def _key(slug, s):
    """The parcel number in the form each county's search expects (kept in step with the Atlanta tracker)."""
    import re as _re
    s = _re.sub(r"\s+", " ", (s or "").strip().upper())
    if not s:
        return None
    t = s.split(" ")
    try:
        if slug == "fulton":
            d = _re.sub(r"[^0-9A-Z]", "", s); return d[:2] + " " + d[2:] if len(d) >= 12 else None
        if slug == "cobb":
            d = _re.sub(r"[^0-9]", "", s); return d if len(d) == 11 else None
        if slug == "walton":
            return _re.sub(r"[-\s]", "", s)
        if slug == "coweta":
            return t[0].ljust(5) + t[1].ljust(4) + " " + t[2] if len(t) == 3 else (t[0].ljust(5) + "     " + t[1] if len(t) == 2 else None)
        if slug == "forsyth":
            return t[0].ljust(6) + t[1] if len(t) == 2 else None
        if slug == "carroll":
            d = _re.sub(r"\s", "", s); return d[:3] + d[3:].rjust(8) if 5 <= len(d) <= 11 else None
        if slug == "clarke":
            return t[0].ljust(5) + " " + ("" if _re.match(r"^[A-Z]\d{3}", t[1]) else " ") + t[1] if len(t) == 2 else None
        if slug == "dawson":
            return None if (s.endswith("MH") or len(t) < 2) else _pad7(t)
        if slug == "heard":
            m = _re.match(r"^(\d{4})([A-Z]?)$", t[0]); return f"{m.group(1)} {m.group(2) or ' '} {t[1]}" if (m and len(t) > 1) else None
        if slug == "jackson":
            m = _re.match(r"^(\d{3}[A-Z]?)(.+)$", _re.sub(r"\s", "", s)); return m.group(1).ljust(7) + m.group(2) if m else None
        if slug == "lumpkin":
            t2 = _re.split(r"[-\s]+", s); return _pad7(t2) if len(t2) >= 2 else None
        if slug in ("meriwether", "pickens"):
            return _pad7(t) if len(t) >= 2 else None
        if slug == "polk":
            return "-".join(t)
        if slug == "troup":
            return t[0].ljust(5) + t[1] + t[2] if len(t) == 3 else None
    except IndexError:
        return None
    return s


def parcel_links(slug, parcel_no):
    import urllib.parse
    k = _key(slug, parcel_no)
    if not k:
        return None, None
    q = urllib.parse.quote(k)
    if slug == "dekalb":
        return (f"https://propertyappraisal.dekalbcountyga.gov/Datalets/Datalet.aspx?UseSearch=no&pin={q}",
                f"https://propertyappraisal.dekalbcountyga.gov/maps/map.aspx?UseSearch=no&pin={q}&jur=000")
    if slug in QP:
        a, l, r, m = QP[slug]
        b = f"https://qpublic.schneidercorp.com/Application.aspx?AppID={a}&LayerID={l}"
        return f"{b}&PageTypeID=4&PageID={r}&KeyValue={q}", f"{b}&PageTypeID=1{'' if m is None else '&PageID=' + str(m)}&KeyValue={q}"
    return None, None


def years_unpaid(years):
    """'2019-2022' or '2019, 2020, 2021' -> 4 or 3."""
    import re as _re
    if not years:
        return None
    s = str(years)
    m = _re.match(r"^\s*(\d{4})\s*[-–]\s*(\d{4})\s*$", s)
    if m:
        return int(m.group(2)) - int(m.group(1)) + 1
    ys = _re.findall(r"(?:19|20)\d{2}", s)
    return len(set(ys)) or None


def _status(p):
    s = (p.get("status") or "").lower()
    if s == "sold":
        return "Sold"
    if s == "no bid":
        return "No bid"
    if s == "paid":
        return "Paid before sale"
    return "Listed"


def fetch(counties):
    today = dt.date.today().isoformat()
    index = get_json(RAW + "index.json")
    out = {}
    for c in index.get("counties", []):
        fips = c.get("fips")
        slug = c.get("slug")
        if not fips or not slug:
            continue
        try:
            d = get_json(RAW + f"{slug}.json")
        except Exception as e:  # keep going; the county keeps its registry-level info
            print(f"  atlanta/{slug}: {e}")
            continue
        aucs = []
        for i, a in enumerate(d.get("auctions", [])):
            date = a.get("date")
            kind = a.get("kind") or "list"
            parcels = []
            for p in a.get("parcels", []):
                phs = [(HOMEPAGE + x["src"]) if x.get("src") else x.get("url") for x in (p.get("photos") or []) if x.get("src") or x.get("url")]
                info_link, map_link = parcel_links(slug, p.get("parcel"))
                parcels.append(parcel(
                    parcelInfo=info_link, parcelMap=map_link, yearsUnpaid=years_unpaid(p.get("years")), addrNum=p.get("addrNum"), addrNote=p.get("addrNote"),
                    priceSource=p.get("priceSource"), typeDetail=p.get("ptypeDetail"), acresSrc=p.get("acresSrc"), zip=p.get("zip"),
                    photo=phs[0] if phs else None, photos=phs if len(phs) > 1 else None, photoCredit=(p.get("photos") or [{}])[0].get("credit") if phs else None, sv=p.get("sv"),
                    parcel=p.get("parcel"), owner=p.get("owner"), address=p.get("address"), fullAddress=p.get("fullAddress"),
                    minBid=p.get("minBid"), winningBid=p.get("winningBid"), excess=p.get("excess"), status=_status(p),
                    buyer=p.get("buyer"), lat=p.get("lat"), lon=p.get("lon"), type=p.get("ptype") or p.get("type"),
                    acres=p.get("acres"), sqft=p.get("sqft"), yearBuilt=p.get("yearBuilt"), value=p.get("value"),
                    years=p.get("years"), area=p.get("area"),
                ))
            aucs.append(auction(
                id=f"{slug}-{i}", date=date, kind=kind, label=f"{KIND_LABEL.get(kind, kind)} {date or ''}".strip(),
                source=a.get("source"), note=a.get("note"), status="upcoming" if (date and date >= today and kind == "list") else "past",
                parcels=parcels,
            ))
        info = dict(run=d.get("run"), page=d.get("page"), schedule=d.get("schedule"), excess=d.get("excess"),
                    parcel=d.get("parcel"), note=d.get("note"), auction=d.get("auction"))
        out[fips] = dict(
            fips=fips, source=NAME, sourceUrl=HOMEPAGE + f"#{slug}", lastChecked=d.get("lastChecked"), lastChanged=d.get("lastChanged"),
            info={k: v for k, v in info.items() if v}, auctions=aucs,
        )
    return out
