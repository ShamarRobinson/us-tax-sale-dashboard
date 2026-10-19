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
  (currently `atlanta`, `clark`, `michigan`, `realauction`, `govease`, `bid4assets`, `mvba`, `b4a_sheriff`, `sri`, `cosl`, `iltaxsale`). GovEase (`sources/govease.py`)
  is reachable from the GitHub runner and from Claude Code on the web, so it refreshes itself monthly; it publishes
  sale lists with starting bids (no results) for whichever auctions are open, in CO, TN, PA, TX, CA, IN, MO, WA, KS and
  OK. Bid4Assets (`sources/bid4assets.py`) covers the County Tax Sales calendar (CA, NV, WA, PA, MN, LA) with sale
  lists and, for past sales, winning bids; it answers only browser user agents, and its item pages are read eight at
  a time because a Pennsylvania upset sale lists thousands of parcels. MVBA Tax Sales (`sources/mvba.py`) reads the Texas
  online tax sales that MVBA conducts, open sales and about 3,000 past lots with final bids, through the site's JSON
  API; MVBA's in-person sale list on mvbalaw.com refuses data-center addresses. Bid4Assets sheriff's sales
  (`sources/b4a_sheriff.py`) reads the 34 county and parish landing pages on bid4assets.com/sheriffsales (calendar API
  plus the property table embedded in each sale day's page): upcoming lists with judgment amounts, plaintiffs and
  defendants, and the last few days' outcomes, since a sale day's table disappears soon after the sale. Philadelphia's
  entry is a hub in front of two landing pages of the same kind (`/philataxsales`, `/philaforeclosures`), the largest
  on the platform, and is read through the same adapter. SRI Inc. (`sources/sri.py`) reads the public JSON API behind
  the property search on sriservices.com (`/api/property/carddetail` per state, `/downloadpropertylist` per upcoming
  sale for owners and minimum bids, `/detail` for the price of each parcel that sold): twelve months of tax sales,
  commissioners' certificate sales, deed sales, tax lien sales and sheriff's foreclosure sales in IN, CO, LA, TN, FL and
  MI, with online bidding on Zeus Auction. Parcels paid, removed or cancelled before a past sale are left out so the
  master CSV stays under GitHub's 100 MB file limit. The Arkansas Commissioner of State Lands (`sources/cosl.py`) pages
  through the cards on auction.cosl.org (`POST /auctions/get-listings`), the statewide list of tax-delinquent parcels
  offered online after the county auctions. ILTaxSale.com (`sources/iltaxsale.py`) reads the 95 Illinois county pages of
  Joseph E. Meyer & Associates: the next sealed-bid surplus auction and the free results PDFs, parsed by
  `sources/pdftext.py` (a standard-library PDF text extractor for FlateDecode page streams; it handles the fixed-column
  sheets these sites publish, nothing fancier). `sources/realauction.py` collects six portals at a time.
- Deal score (`master.py`): value 40, property 20, market 15, competition 15, history 10; 70+ Strong, 50 to 69 Good,
  35 to 49 Fair, under 35 Weak.

## Data On File (As Of 2026-10-19)

67,804 parcels across 364 counties: FL 21,478 (45), PA 14,605 (20), CO 9,155 (23), MI 7,359 (79), GA 3,931 (24), TX
3,918 (31), OH 3,501 (87), CA 1,591 (17), NV 1,156 (7), LA 582 (10), WA 183 (7), TN 124 (10), OK 87 (1), WI 68 (1), MN
35 (1), MO 31 (1). By adapter: realauction 28,192, bid4assets 13,234, govease 8,018, michigan 7,359, atlanta 3,931,
b4a_sheriff 3,367, mvba 2,967, clark 736. Raw portal dumps live in `data/raw/realauction/<fips>-<kind>.json` (135
files: FL taxdeed 35, FL foreclosure 9, CO taxdeed 4, OH sheriff 87). GovEase data is sale lists only (every auction
open on the platform that day, with starting bids and sale dates); Bid4Assets data is sale lists plus results with
winning bids for the past sales on its calendar; MVBA data is the open Texas sales plus every past online sale since
2017 with final bids; Bid4Assets sheriff's sales are upcoming lists with judgment amounts plus the last few days'
outcomes. All of these, RealAuction included, refresh on the monthly run and with `python3 fetch_all.py --source
<adapter>`.

## RealAuction Portals: The Main Open Work

RealAuction runs the Florida Clerk tax deed (`{county}.realtaxdeed.com`) and foreclosure (`{county}.realforeclose.com`)
portals, the Ohio sheriff portal (`{county}.sheriffsaleauction.ohio.gov`), the Texas sheriff portals
(`{county}.texas.sheriffsaleauctions.com`, only the 28 hosts in `TX_SHERIFF` exist), Colorado and Arizona treasurer
deed portals and two New Jersey foreclosure portals (the roster is `SITES` in `sources/realauction.py`). They refuse
Anthropic's cloud addresses with a marketing page, and refused GitHub's runners when the project was built, so the
first session collected them one browser tab at a time and transcribed the results (see docs/HANDOFF.md). **Two
things changed on 2026-10-19:** the monthly workflow's run of that night reached the portals from GitHub's runner
(155 counties, 28,192 parcels, in 2 hours 42 minutes), so the runner now refreshes RealAuction on its own; and
**from Shamar's Mac `collect_local.py` works from a residential address** for anything the runner misses.

```bash
python3 collect_local.py --county pasco,brevard,volusia,seminole,sarasota,manatee   # a few counties, any state
python3 collect_local.py --state TX                                                 # one state
python3 collect_local.py --import                                                   # fold data/raw/realauction/*.json dumps in
git add data && git commit -m "Collect RealAuction portal data for ..." && git push
```

Portals with no data on file after the 2026-10-19 runner pass (21 of 212): TX sheriff Harris, Bexar, Fort Bend,
Hidalgo, Hopkins, Rusk, San Patricio, Wilson, Brooks; AZ taxdeed Mohave, Coconino, Apache; CO foreclosure Eagle; CO
taxdeed Larimer, Pitkin; FL foreclosure Calhoun; FL taxdeed Monroe, Gulf; NJ Essex (newarknj) and Sussex
(hardystonnj); OH Vinton (the portal is empty). Some of these may simply have had no sale in the window; the Mac run
(`python3 collect_local.py --state TX`, then AZ, CO, FL, NJ) settles it. The big Florida foreclosure portals were first
collected with one month of history; the runner now refreshes them with the default three months.

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
2. Add adapters for more statewide platforms (GovDeals, LienHub, Grant Street
   and the county treasurer sites that publish lists), one module each in `sources/`.
3. Keep the analyzer and county pages in parity with the sibling trackers as those gain features.
4. Rerun `python3 discover_links.py --stale 45` monthly (the workflow does this) and review `ref/discovered_links.json`.

Slash commands for the routine work are in `.claude/commands/` (`/collect`, `/ship`).
