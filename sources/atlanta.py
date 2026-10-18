"""Metro Atlanta Tax Sale Tracker: 40 Georgia counties, read from that project's published data on GitHub."""
import datetime as dt

from . import get_json, parcel, auction

NAME = "atlanta"
LABEL = "Metro Atlanta Tax Sale Tracker"
HOMEPAGE = "https://shamarrobinson.github.io/atlanta-tax-sale-dashboard/"
RAW = "https://raw.githubusercontent.com/ShamarRobinson/atlanta-tax-sale-dashboard/main/data/"

KIND_LABEL = {"list": "Sale list", "results": "Results", "excess": "Excess funds list"}


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
                parcels.append(parcel(
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
