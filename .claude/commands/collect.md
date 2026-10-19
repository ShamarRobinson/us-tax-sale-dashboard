---
description: Collect RealAuction portal data for a state or a list of counties, rebuild the data files, commit as Shamar and push
argument-hint: FL | TX | pasco,brevard,volusia
---

Collect RealAuction portal data for `$ARGUMENTS` and publish it. Follow the standing rules in CLAUDE.md.

1. Decide the selector: a two-letter state means `python3 collect_local.py --state $ARGUMENTS`; anything else is a
   comma-separated list of county names, so run `python3 collect_local.py --county $ARGUMENTS`. If `$ARGUMENTS` is
   empty, run `python3 collect_local.py --import` to fold in any dumps already in `data/raw/realauction/`.
2. Run it from this Mac (the portals refuse data-center addresses, a home connection works). A full state can take an
   hour; use a long timeout or run it in the background and watch the output. The script rebuilds the registry,
   index, master CSV, changes feed and calendar itself.
3. Check the result: `python3 -c "import json;print(json.load(open('data/master/index.json'))['parcels'])"`
   for the new parcel total, `git status --short data | head`, and spot-check one new county file in
   `data/counties/<fips>.json` (auctions with parcels, statuses, values).
4. Commit as Shamar with a message of the form `Add <sale kind> sales for <counties or state>`, a body with the
   portal hosts, the date window and the master CSV before-and-after counts, then rebase and push:
   `git add data && git commit -F - && git fetch origin && git rebase origin/main && git push origin HEAD`.
5. Confirm the Pages deploy:
   `gh run list --workflow=pages-build-deployment --limit 1 --json status,conclusion,headSha -q '.[0]'` and report
   the live county URL `https://shamarrobinson.github.io/us-tax-sale-dashboard/#c/<fips>` for one of the counties.
6. Report which portals are still uncollected (compare `data/raw/realauction/` against `sources.realauction.sites_for`).
