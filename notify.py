#!/usr/bin/env python3
"""Email alerts for upcoming tax sales, nationwide.

Runs after each monthly data refresh. It emails one digest: every sale date newly posted since the last refresh
(from data/changes.json), every posted sale in the next 45 days, and the statutory dates coming up in the next
45 days for states that sell on a calendar. Recipients can limit the digest to states with the ALERT_STATES secret
(comma-separated abbreviations, e.g. "NV,GA,MI"). Nothing is emailed when there is nothing new and nothing
coming up. Watch-listed parcels live in each reader's browser, so they are not part of the email.

Configuration comes only from environment variables (GitHub Actions secrets):
  ALERT_TO       comma-separated recipient list (required; no email is sent without it)
  SMTP_USER      sending account
  SMTP_PASS      app password for the sending account
  SMTP_HOST      optional, default smtp.gmail.com
  SMTP_PORT      optional, default 465 (SSL)
  ALERT_STATES   optional, comma-separated state abbreviations to include
  ALERT_TEST     "true" to send a test digest even when nothing is new
Nothing about recipients is written to the repository or printed to logs.
"""
import datetime as dt
import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = "https://shamarrobinson.github.io/us-tax-sale-dashboard/"
STATE_FILE = HERE / "data" / "alert_state.json"  # remembers which posted dates were already announced (county + date only)


def load(name, default):
    try:
        with open(HERE / "data" / name, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main():
    to = [x.strip() for x in os.environ.get("ALERT_TO", "").split(",") if x.strip()]
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASS", "")
    test = os.environ.get("ALERT_TEST", "").lower() in ("1", "true", "yes")
    if not (to and user and pw):
        print("alerts: not configured (ALERT_TO, SMTP_USER and SMTP_PASS are needed); nothing sent")
        return 0
    only = {x.strip().upper() for x in os.environ.get("ALERT_STATES", "").split(",") if x.strip()}
    index = load("index.json", {})
    changes = load("changes.json", {})
    reg = load("registry.json", {})
    states = {s["abbr"]: s for s in reg.get("states", [])}
    announced = set(tuple(x) for x in (load("alert_state.json", {}) or {}).get("announced", []))
    today = dt.date.today()
    horizon = (today + dt.timedelta(days=45)).isoformat()

    keep = lambda st: not only or st in only
    new = [u for u in changes.get("newUpcoming", []) if keep(u["state"]) and (u["fips"], u["date"]) not in announced]
    soon = [u for u in index.get("upcomingPosted", []) if keep(u["state"]) and today.isoformat() <= u["date"] <= horizon]
    statutory = [s for s in states.values() if keep(s["abbr"]) and s.get("nextStatutory") and s["nextStatutory"] <= horizon]
    if not (new or soon or statutory) and not test:
        print("alerts: nothing new and nothing in the next 45 days; nothing sent")
        return 0

    lines = [f"US Tax Sale Tracker digest for {today:%B %d, %Y}", SITE, ""]
    if new:
        lines += [f"Newly posted sale dates ({len(new)}):"] + [f"  {u['date']}  {u['name']}, {u['state']}  ({u.get('parcels') or 0} parcels)  {SITE}#c/{u['fips']}" for u in sorted(new, key=lambda u: u["date"])] + [""]
    if soon:
        lines += [f"Posted sales in the next 45 days ({len(soon)}):"] + [f"  {u['date']}  {u['name']}, {u['state']}  ({u.get('parcels') or 0} parcels)  {u.get('page') or ''}" for u in sorted(soon, key=lambda u: u["date"])[:60]] + [""]
    if statutory:
        lines += ["Statutory sale dates in the next 45 days:"] + [f"  {s['nextStatutory']}  {s['name']}: {s['sale_timing']}  {SITE}#{s['abbr'].lower()}" for s in sorted(statutory, key=lambda s: s["nextStatutory"])] + [""]
    lines += ["Master CSV: " + SITE + "data/master_parcels.csv", "Deal analyzer: " + SITE + "analyzer.html", "Calendar: " + SITE + "data/upcoming.ics", "",
              "Sent by the tracker's monthly refresh. Dates change up to the day of the sale; confirm with the county."]
    if test:
        lines.insert(1, "(test message)")

    msg = EmailMessage()
    msg["Subject"] = f"Tax sale digest: {len(new)} newly posted, {len(soon)} in the next 45 days" + (" (test)" if test else "")
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg.set_content("\n".join(lines))
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=60) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"alerts: sent digest ({len(new)} new, {len(soon)} soon, {len(statutory)} statutory) to {len(to)} recipient(s)")
    announced |= {(u["fips"], u["date"]) for u in new}
    cutoff = today.isoformat()
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"announced": sorted(x for x in announced if x[1] >= cutoff)}, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
