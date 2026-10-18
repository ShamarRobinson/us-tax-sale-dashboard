"""Clark County, Nevada: the Treasurer's trustee auctions, read from the Clark County Tax Auction Tracker on GitHub."""
import datetime as dt

from . import get_json, parcel, auction

NAME = "clark"
LABEL = "Clark County Tax Auction Tracker"
HOMEPAGE = "https://shamarrobinson.github.io/clark-county-tax-auction-dashboard/"
RAW = "https://raw.githubusercontent.com/ShamarRobinson/clark-county-tax-auction-dashboard/main/"
FIPS = "32003"


def fetch(counties):
    today = dt.date.today().isoformat()
    data = get_json(RAW + "auctions.json")
    try:
        details = get_json(RAW + "parcels.json")
    except Exception as e:
        print(f"  clark/parcels.json: {e}")
        details = {}
    aucs = []
    for a in data.get("auctions", []):
        events = a.get("events") or []
        date = events[0]["start"][:10] if events and events[0].get("start") else None
        venue = events[0].get("address") if events else None
        parcels = []
        for p in a.get("parcels", []):
            apn = p.get("apn")
            d = details.get(apn, {}) if isinstance(details, dict) else {}
            wb = p.get("winningBid")
            status = "Sold" if wb else ("Listed" if (date and date >= today) else "No bid")
            parcels.append(parcel(
                parcel=apn, owner=p.get("owner"), address=None if (p.get("location") or "").upper() == "UNASSIGNED SITUS" else p.get("location"),
                fullAddress=d.get("address"), minBid=p.get("minBid"), winningBid=wb or None, excess=p.get("excess") or None,
                status=status, lat=d.get("lat"), lon=d.get("lon"), type=d.get("landUse"), acres=d.get("acres"), sqft=d.get("sqft"),
                yearBuilt=d.get("yearBuilt") or None, value=d.get("taxable") or d.get("assessed"), area=d.get("town") or d.get("area"),
                deedRecorded=p.get("deedRecorded"),
            ))
        upcoming = bool(date and date >= today)
        aucs.append(auction(
            id=f"clark-{a.get('id')}", date=date, kind="list" if upcoming else "results",
            label=f"{'Upcoming auction' if upcoming else 'Auction'} {date or ''}".strip(), source=data.get("source"),
            note=venue, status="upcoming" if upcoming else "past", parcels=parcels,
        ))
    aucs.sort(key=lambda x: x.get("date") or "", reverse=True)
    return {FIPS: dict(
        fips=FIPS, source=NAME, sourceUrl=HOMEPAGE, lastChecked=data.get("lastChecked"), lastChanged=data.get("lastChanged"),
        info=dict(run="County Treasurer", page="https://treasurer.clarkcountynv.gov/auction",
                  schedule="Held when needed, usually in May; registration deposit of $5,000 and certified funds the same day",
                  parcel="https://maps.clarkcountynv.gov/assessor/AssessorParcelDetail/",
                  note="Trustee auction of parcels held in trust by the Treasurer after three years of delinquency. All sales are final; the IRS keeps a 120-day right on parcels with federal tax liens."),
        auctions=aucs,
    )}
