# US Tax Sale Tracker: Working Notes For Claude Code

This file is loaded automatically by Claude Code. It carries the context from the Claude session that built this
project (https://claude.ai/code/session_0186Htxm6yjesny38nJy4aXQ) and from the two trackers it grew out of. The long
version, including the session log and the browser collection protocol, is in [docs/HANDOFF.md](docs/HANDOFF.md).

## The Project In One Paragraph

A nationwide tracker of tax deed auctions, tax lien sales, treasurer and sheriff sales for every county in every state
(3,222 counties in `data/registry.json`), with a page per county (`index.html#c/<fips>`), nested state and national
views, a Property Deal Analyzer (`analyzer.html`) driven by a master CSV of every parcel on file, a printable deal
sheet (`sheet.html`), a calendar feed (`data/upcoming.ics`) and a monthly email digest (`notify.py`). Live site:
https://shamarrobinson.github.io/us-tax-sale-dashboard/ ; repo:
https://github.com/ShamarRobinson/us-tax-sale-dashboard . It is modeled on, and reads data from, Shamar's two earlier
trackers:

- Clark County Tax Auction Tracker: https://github.com/ShamarRobinson/clark-county-tax-auction-dashboard (live:
  https://shamarrobinson.github.io/clark-county-tax-auction-dashboard/ ), read by `sources/clark.py`.
- Metro Atlanta Tax Sale Tracker: https://github.com/ShamarRobinson/atlanta-tax-sale-dashboard (live:
  https://shamarrobinson.github.io/atlanta-tax-sale-dashboard/ ), read by `sources/atlanta.py`.

Every county page must have the full capabilities of both of those trackers (auction dropdown, bid stats, cost tiers,
parcel types, map, sortable and pivotable parcel grid with CSV download, bidding wars, time in default, deal score,
search syntax, photos and Street View, official links) plus the extras listed in [README.md](README.md). All parcel
data must land in the master CSV at the same time it lands on a county page; `master.py` does that in one pass.

## Standing Rules From Shamar

- Commit everything as Shamar so it counts toward his GitHub contributions. Check `git config user.name` is
  `Shamar Robinson` and `git config user.email` is `shamarrobinson31@gmail.com`; if not, pass
  `git -c user.name="Shamar Robinson" -c user.email="shamarrobinson31@gmail.com" commit ...`. Keep the
  `Co-Authored-By` trailer Claude Code adds. Push after every meaningful change; do not leave work uncommitted.
- Writing style everywhere (docs, commit messages, UI copy): Title Case for titles and subheadings, no em dashes in
  body text (use commas, colons or parentheses), and include links whenever something has one.
- After pushing, confirm the Pages deploy finished and show the result:
  `gh run list --workflow=pages-build-deployment --limit 1 --json status,conclusion,headSha -q '.[0]'` then open the
  live URL (add `?v=<n>` to beat the cache, for example `https://shamarrobinson.github.io/us-tax-sale-dashboard/?v=9#c/12086`).
- Monthly refresh cadence, not weekly. Dropdowns and nested charts for navigation. Do not reference Shamar's other
  ventures unless the task calls for it.
- Python standard library only in the pipeline (nothing to install on the GitHub runner).

## How The Pipeline Fits Together

```
sources/*.py adapters ──> fetch_all.py ──> data/counties/<fips>.json   (auctions and parcels per county)
                                      ├──> data/registry.json          (every county: rules, links, next sale, summary)
                                      ├──> data/index.json             (national totals, upcoming sales, source status)
                                      ├──> data/master_parcels.csv + data/master.json   (master.py, with deal score)
                                      ├──> data/master_counties.csv, data/changes.json, data/upcoming.ics
GitHub Pages serves index.html / analyzer.html / sheet.html, which load that JSON and CSV (Chart.js, Leaflet, d3-geo).
```

- `python3 fetch_all.py` refreshes every source; `python3 fetch_all.py --source govease` refreshes one adapter and
  keeps the rest from disk; `python3 fetch_all.py --offline` rebuilds everything from the county files without calling
  any source (use this after editing data by hand or importing dumps).
- A county can be on two platforms at once (Summit County, CO is on RealAuction and GovEase), so `fetch_all.py` tags
  each auction with its adapter (`src`) and merges adapters into one county file instead of replacing it; the county
  record's `sources` lists them and `source` names the first. `collect_local.py` follows the same rule.
- `.github/workflows/update-data.yml` runs on the 1st of each month (`23 13 1 * *`), on dispatch, and on pushes to
  `main` that touch `*.py`, `sources/*.py` or the workflow. It keeps county files for FIPS codes an adapter did not
  return, so portal data collected by hand survives the monthly run.
- Adapter contract: a module in `sources/` with `NAME`, `LABEL`, `HOMEPAGE` and `fetch(counties)` that returns county
  records in the shape documented in `sources/__init__.py` (`auction(...)` and `parcel(...)` helpers, `get`,
  `get_json`, `money`). The dashboard needs no change for a new adapter; add its name to `sources.ADAPTERS`
  (currently `atlanta`, `clark`, `michigan`, `realauction`, `govease`, `bid4assets`). GovEase (`sources/govease.py`)
  is reachable from the GitHub runner and from Claude Code on the web, so it refreshes itself monthly; it publishes
  sale lists with starting bids (no results) for whichever auctions are open, in CO, TN, PA, TX, CA, IN, MO, WA, KS and
  OK. Bid4Assets (`sources/bid4assets.py`) covers the County Tax Sales calendar (CA, NV, WA, PA, MN, LA) with sale
  lists and, for past sales, winning bids; it answers only browser user agents, and its item pages are read eight at
  a time because a Pennsylvania upset sale lists thousands of parcels. Its sheriff sale, Philadelphia and Florida
  (Okaloosa) channels are separate apps and are not read yet.
- Deal score (`master.py`): value 40, property 20, market 15, competition 15, history 10; 70+ Strong, 50 to 69 Good,
  35 to 49 Fair, under 35 Weak.

## Data On File (As Of 2026-10-18, Night)

52,890 parcels across 305 counties: FL 16,058 (35), PA 12,044 (10), MI 7,359 (79), CO 6,769 (20), GA 3,931 (24), OH
3,501 (87), CA 1,591 (17), NV 1,156 (7), WA 181 (7), TN 124 (10), TX 109 (6), MN 35 (1), MO 31 (1), LA 1 (1). By
adapter: realauction 19,612, bid4assets 13,234, govease 8,018, michigan 7,359, atlanta 3,931, clark 736. Raw portal
dumps live in `data/raw/realauction/<fips>-<kind>.json` (135 files: FL taxdeed 35, FL foreclosure 9, CO taxdeed 4, OH
sheriff 87). GovEase data is sale lists only (every auction open on the platform that day, with starting bids and sale
dates); Bid4Assets data is sale lists plus results with winning bids for the past sales on its calendar. Both refresh
themselves on the monthly run and with `python3 fetch_all.py --source govease` or `--source bid4assets`.

## RealAuction Portals: The Main Open Work

RealAuction runs the Florida Clerk tax deed (`{county}.realtaxdeed.com`) and foreclosure (`{county}.realforeclose.com`)
portals, the Ohio sheriff portal (`{county}.sheriffsaleauction.ohio.gov`), the Texas sheriff portals
(`{county}.texas.sheriffsaleauctions.com`, only the 28 hosts in `TX_SHERIFF` exist), Colorado and Arizona treasurer
deed portals and two New Jersey foreclosure portals (the roster is `SITES` in `sources/realauction.py`). They refuse
data-center addresses (GitHub runners and Anthropic's cloud included) with a marketing page, so the previous session
collected them one browser tab at a time and transcribed the results (see docs/HANDOFF.md). **From Shamar's Mac this
is unnecessary: `collect_local.py` works from a residential address.**

```bash
python3 collect_local.py --county pasco,brevard,volusia,seminole,sarasota,manatee   # a few counties, any state
python3 collect_local.py --state TX                                                 # one state
python3 collect_local.py --import                                                   # fold data/raw/realauction/*.json dumps in
git add data && git commit -m "Collect RealAuction portal data for ..." && git push
```

Still uncollected (by population, 77 portals): FL foreclosure Pasco, Brevard, Volusia, Seminole, Sarasota, Manatee,
Marion, St. Lucie, St. Johns, Escambia, Leon, Alachua, Clay, Charlotte, Santa Rosa, Bay, Indian River, Martin,
Flagler, Nassau, Walton, Putnam, Jackson, Okeechobee, Baker, Washington, Gilchrist, Gulf, Calhoun; FL taxdeed Monroe,
Gulf; all 28 TX sheriff portals (Harris, Dallas, Bexar, Fort Bend, Hidalgo, El Paso, Cameron, Galveston, Nueces,
Smith, Ellis, Kaufman, Gregg, Victoria, Angelina, Orange, San Patricio, Wilson, Rusk, Cherokee, Atascosa, Caldwell,
Hopkins, Matagorda, Aransas, Llano, Jackson, Brooks); CO foreclosure El Paso, Denver, Adams, Larimer, Weld, Mesa,
Eagle, Summit; CO taxdeed Larimer, Mesa, Eagle, Pitkin; AZ taxdeed Mohave, Coconino, Apache; NJ Essex (newarknj) and
Sussex (hardystonnj); OH Vinton (the portal is empty). The big Florida foreclosure portals were collected with one
month of history; a full `--state FL` run from the Mac would deepen every county's history.

If a portal ever has to be read from a browser again, `tools/realauction_console.js` is served from the live site with
CORS and the transcription helpers are `tools/ingest_chunks.py` and `tools/decode_dumps.py`.

## Sibling Trackers (What To Preserve And Reuse)

- Clark County (Nevada Treasurer trustee auctions since 2012): `fetch_data.py` calls the county's own JSON endpoints
  (`Event_Read`, `WinningBid_Read`, `ParcelNumberGroup_Read`), `enrich.py` adds Assessor land use, town, coordinates and
  ownership history into `parcels.json`, `notify.py` emails alerts through repository secrets (`ALERT_TO`,
  `SMTP_USER`, `SMTP_PASS`), weekly Actions run. Features: KPIs, cost tiers, parcel types from land-use codes, map,
  grid with 0 to 100 deal score and prior auctions, bidding wars, time in default.
- Metro Atlanta (40 Georgia counties within 52 miles of downtown): `registry.py` plus one parser per county in
  `counties_metro.py` and `counties_outer.py`, `ga_common.py` (PDF, OCR, spreadsheets), Census geocoder, photo and
  Street View helpers (`photo_store.py`, `photos_*.py`, `streetview*.py`), weekly Actions run. Features: region map,
  per-county tabs with auction dropdown, bid stats, cost tiers, history, multiples, most active buyers, parcel map,
  pivotable grid with CSV download, search syntax such as `county:gwinnett won>100000`.
- Neither sibling repo has a CLAUDE.md. If work there is needed, the same standing rules apply, and both are cloned
  beside this one at `../shamarrobinson/` in the original workspace (clone them fresh on the Mac if needed).

## Suggested Next Steps

1. `python3 collect_local.py --state FL` (then TX, CO, AZ, NJ) from the Mac, import, commit, push, confirm the deploy.
2. Add adapters for more statewide platforms (GovEase, Bid4Assets, Zeus Auction, SRI, GovDeals, LienHub, Grant Street
   and the county treasurer sites that publish lists), one module each in `sources/`.
3. Keep the analyzer and county pages in parity with the sibling trackers as those gain features.
4. Rerun `python3 discover_links.py --stale 45` monthly (the workflow does this) and review `ref/discovered_links.json`.

Slash commands for the routine work are in `.claude/commands/` (`/collect`, `/ship`).
