"""Clark County, Nevada: the Treasurer's trustee auctions, read from the Clark County Tax Auction Tracker on GitHub."""
import datetime as dt
import re

from . import get_json, parcel, auction

NAME = "clark"
LABEL = "Clark County Tax Auction Tracker"
HOMEPAGE = "https://shamarrobinson.github.io/clark-county-tax-auction-dashboard/"
RAW = "https://raw.githubusercontent.com/ShamarRobinson/clark-county-tax-auction-dashboard/main/"
FIPS = "32003"


def _years(a, b):
    try:
        return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days / 365.25
    except (ValueError, TypeError):
        return None


def _tenure(d, ref_date):
    """How long the former owner held the parcel, and how long the county held it in trust (Assessor ownership history)."""
    hist = sorted([h for h in (d.get("history") or []) if h.get("date") and ref_date and h["date"] < ref_date], key=lambda h: h["date"])
    trustee = lambda h: bool(re.search(r"TREASURER|TRUSTEE CLARK COUNTY", h.get("owner") or "", re.I))
    last = hist[-1] if hist else None
    trust = last if (last and trustee(last) and last["date"] > "1950") else None
    prior = next((h for h in reversed(hist) if not trustee(h) and (not trust or h["date"] < trust["date"])), None)
    tenure = _years(prior["date"], trust["date"] if trust else ref_date) if prior else None
    in_trust = _years(trust["date"], ref_date) if trust else None
    if in_trust is not None and in_trust >= 40:
        in_trust = None
    return (round(tenure, 1) if tenure is not None else None, round(in_trust + 3, 1) if in_trust is not None else None, trust["date"] if trust else None,
            [dict(owner=h.get("owner"), date=h.get("date")) for h in hist[-4:]])


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
            tenure, default_yrs, trust_date, hist = _tenure(d, p.get("deedRecorded") or date)
            parcels.append(parcel(
                tenure=tenure, defaultYrs=default_yrs, trustDate=trust_date, history=hist or None, addressExact=d.get("addressExact"),
                legal=(d.get("legal") or "")[:200] or None, landUse=d.get("landUse"), parcelInfo=f"https://maps.clarkcountynv.gov/assessor/AssessorParcelDetail/parceldetail.aspx?hdnParcel={re.sub(r'[^0-9]', '', apn or '')}",
                parcelMap=f"https://maps.clarkcountynv.gov/openweb/?@{re.sub(r'[^0-9]', '', apn or '')}",
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
