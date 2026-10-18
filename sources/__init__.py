"""Source adapters: each one knows how to read one publisher of tax sale data and returns normalized county records.

An adapter is a module with:
    NAME        short id, e.g. "atlanta"
    LABEL       what the dashboard calls it
    HOMEPAGE    where the data comes from
    def fetch(counties) -> dict[fips] = county record (see normalize() for the shape)

A county record:
    {
      "fips": "13135", "source": NAME, "sourceUrl": "...", "lastChecked": iso, "lastChanged": iso,
      "info": {"run": ..., "page": ..., "schedule": ..., "excess": ..., "parcel": ..., "note": ..., "auction": {...}},
      "auctions": [
         {"id": "...", "date": "YYYY-MM-DD", "kind": "list|results|excess|upcoming", "label": "...", "source": url,
          "status": "upcoming|past", "parcels": [ {parcel, owner, address, fullAddress, minBid, winningBid, excess,
                                                  status, buyer, lat, lon, type, acres, sqft, yearBuilt, value, link} ]}
      ]
    }
Only the keys a source has are filled in; the dashboard copes with missing ones.
"""
import json
import time
import urllib.request
import urllib.error

UA = "us-tax-sale-dashboard/1.0 (+https://github.com/ShamarRobinson/us-tax-sale-dashboard)"


def get(url, retries=3, timeout=60, binary=False, data=None, headers=None):
    """GET (or POST when data is given) with retries. Returns text (or bytes when binary=True)."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return raw if binary else raw.decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def get_json(url, **kw):
    return json.loads(get(url, **kw))


def parcel(**kw):
    """Build a parcel dict, dropping empty values."""
    return {k: v for k, v in kw.items() if v not in (None, "", [])}


def auction(**kw):
    return {k: v for k, v in kw.items() if v not in (None, "")}


def money(s):
    """'$1,234.50' -> 1234.5; returns None when it is not a number."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


ADAPTERS = ["atlanta", "clark", "michigan", "realauction", "govease", "bid4assets", "mvba"]
