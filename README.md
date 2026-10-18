# US Tax Sale Tracker

Live dashboard: **https://shamarrobinson.github.io/us-tax-sale-dashboard/**

Tax deed auctions, tax lien sales, redeemable deed sales and sheriff sales for every county in every state: all 3,222 counties and county equivalents in the 50 states, the District of Columbia and Puerto Rico. It grew out of the [Clark County Tax Auction Tracker](https://github.com/ShamarRobinson/clark-county-tax-auction-dashboard) and the [Metro Atlanta Tax Sale Tracker](https://github.com/ShamarRobinson/atlanta-tax-sale-dashboard), which feed it directly.

## What It Shows

- **National overview:** a map of the United States colored by how each state sells delinquent property (tax deed, tax lien, redeemable deed or hybrid), the next sale dates fixed by statute, every sale date posted by a source, and a table of all states with their rules.
- **A tab per state** (with its own link, e.g. `#ga`): who holds the sale, when, how bidding works, the interest or penalty rate, the redemption period, how mortgage foreclosures and sheriff sales work in that state, the statute, the auction platforms in use, and a county map and table.
- **A page per county** (e.g. `#ga/fulton`, `#c/13121`, or `#ga/gwinnett?parcel=R6023%20008` to open straight to a parcel): who runs the sale, the next sale date (posted or by statute), the tax sale, sheriff sale, assessor, treasurer and excess funds pages, the official site, population and land area, the state rules with a redemption-return table, calendar export and a shareable link.
- **Every capability of the Clark County and Metro Atlanta trackers, on every county with data:** an auction picker (any sale or all sales on file); KPIs (parcels, sold, average, median, lowest, highest and most frequent winning bid, typical multiple, bidding wars, total bids, excess funds); cost tiers; parcel types (vacant, single-family, condo or townhouse, manufactured, multi-family, commercial) from county land-use codes or catalog descriptions; auction history; bidding wars with the biggest jumps and the most active buyers; a parcel map with winning bid and bidding-war rate by area (click an area to highlight it and filter the grid); time in default (years unpaid, how long former owners held the parcel) and excess funds waiting to be claimed; a parcel grid with sorting, a column chooser, drag-to-reorder, pivots on any column with click-to-filter, address copy buttons, per-parcel county record and county map links, prior auctions for the same parcel, a 0 to 100 deal score with its parts, and CSV download; a photo gallery and lightbox with stored photos and live Street View; and parcel detail dialogs with ownership history, the score breakdown, a watchlist note, a redemption calculator and a printable deal sheet.
- **Dropdown navigation:** State, County, Sale type and Show menus in the header cascade into each other (pick a state, then a county, then an auction).
- **Drill-down charts:** every chart is nested. On the national page, sale system > states > state page; parcels by state > counties > county page; posted sales by month > counties. On a state page, group counties by data status, next sale month, population tier or who holds the sale, then click a bar to list the counties, then open one. On a county page, cost tier > parcels (opening bid against winning bid) > parcel details, and the auction history bars switch the auction picker.
- **Search** across every county (`state:tx`, `type:lien next:2026-12`, `data:yes state:mi`, `run:sheriff`, `pop>500k`, `coverage:4`) or across every parcel on file (`county:gwinnett won>100000`, `status:listed score>70 state:mi`, `buyer:capital`, `excess>5k`), with CSV download of the results.
- **Beyond the two trackers:** a watchlist with notes (kept in your browser, exportable), calendar (.ics) downloads for a county, a state or every posted sale nationwide, a redemption-return calculator using each state's statutory interest and penalties, printable one-page deal sheets (`sheet.html`), a "what changed in this refresh" card, a coverage score per county (rules, site, sale page, data, photos), distance-from-home filtering in the analyzer, excess-funds recovery leads, buyer intelligence, shareable links to any analyzer view, monthly email digests of newly posted and upcoming sales, and pages that recheck for new data every 30 minutes.

## Property Deal Analyzer And Master CSV

- **[Property Deal Analyzer](https://shamarrobinson.github.io/us-tax-sale-dashboard/analyzer.html)** (`analyzer.html`): every parcel on file, rescored with your own assumptions (target discount to county value, repair and closing allowance, budget, value fallback). Filters by state, county, sale type and kind, status, property type, bid and value ranges, photos and coordinates; drill-down charts; a bid-against-value scatter; a map; a sortable grid; a photo and Street View gallery; CSV download of whatever is in view.
- **Master CSVs**, rebuilt by `fetch_all.py` on every run so every source flows into them: `data/master_parcels.csv` (one row per parcel: county, sale, parcel, address, owner, buyer, bids, multiple, excess, county value, bid-to-value, size, coordinates, Google Maps and Street View links, photo, listing and source links, redemption period, rate, county median multiple, deal score) and `data/master_counties.csv` (every county with its rules, links and next sale). `data/master.json` is the same parcel data for the analyzer page.
- **Deal score** (0 to 100, a screening aid, identical in the county pages, the analyzer and the master CSV): value 40 (cost against county value, or entry cost when none is published), property 20 (type from county records; improved beats vacant), market 15 (county population), competition 15 (the parcel's own multiple, or the county's median multiple), history 10 (earlier auctions for the same parcel; a prior no-bid scores lowest). 70 and up Strong, 50 to 69 Good, 35 to 49 Fair, under 35 Weak. Every parcel detail shows how its score was built.

## Email Alerts

`notify.py` runs after each monthly refresh and emails one digest: sale dates newly posted since the last refresh, posted sales in the next 45 days, and statutory dates in the next 45 days. It sends nothing unless the repository secrets `ALERT_TO` (comma-separated recipients), `SMTP_USER` and `SMTP_PASS` (an app password) are set; `SMTP_HOST`, `SMTP_PORT` and `ALERT_STATES` (e.g. `NV,GA,MI`) are optional. Recipients are never written to the repository. To test: **Actions > Update tax sale data > Run workflow**, check "Send a test alert digest".

## Use It As An API

Everything the pages read is a static file you can fetch from the site:

| File | Contents |
|---|---|
| `data/registry.json` | every county (FIPS, name, state, coordinates, population, links, next sale, data summary, coverage) and every state's rules |
| `data/index.json` | national totals, posted upcoming sales, source status |
| `data/counties/{fips}.json` | every sale and parcel on file for one county |
| `data/master.json`, `data/master_parcels.csv` | every parcel on file with the deal-analyzer fields |
| `data/master_counties.csv` | every county with its rules and links |
| `data/changes.json` | what changed in the latest refresh |
| `data/upcoming.ics` | calendar of posted sales and statutory dates |
| `ref/discovered_links.json` | the pages found on each county's website |

### Master Parcel Columns

`fips`, `county`, `state`, `system`, `saleKind` (list, results, excess, taxdeed, foreclosure, sheriff), `source`, `auctionDate`, `auctionStatus`, `auctionLabel`, `parcel`, `caseNo`, `certificate` (Florida tax certificate), `lot`, `address`, `fullAddress`, `area`, `zip`, `owner`, `buyer`, `plaintiff`, `type` (normalized category), `typeDetail` (CSV only), `status`, `soldAt` (time the hammer fell, where the portal publishes it), `minBid` (amount owed or opening bid), `winningBid`, `multiple`, `excess`, `value` (county value; Michigan is 2x SEV), `bidToValue`, `winToValue`, `judgment`, `taxes`, `acres`, `sqft`, `yearBuilt`, `years`, `yearsUnpaid`, `tenure` (years the former owner held it), `priorAuctions`, `lat`, `lon`, `googleMaps`, `streetView`, `photo`, `photoCredit`, `listing`, `sourceDoc`, `parcelRecord`, `countyMap`, `countyPage`, `redemptionMonths`, `rate`, `countyMedianMultiple`, `dealScore`, `dealRating`, `desc`.

## Where The Data Comes From

| What | Source |
|---|---|
| County list, FIPS codes, land area, coordinates | [Census Bureau 2024 Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html) (`ref/census_gazetteer_2024.txt`) |
| 2024 population | [Census Bureau Vintage 2024 estimates](https://www.census.gov/programs-surveys/popest.html) (`ref/census_pop_2024.csv`) |
| Official county websites | [Wikidata](https://www.wikidata.org/) property P856 by FIPS (`ref/wikidata_county_websites.csv`), 3,061 counties |
| County and state boundaries | [us-atlas](https://github.com/topojson/us-atlas) TopoJSON (`ref/us-counties-10m.json`), drawn with an Albers USA projection |
| State rules | `states.py`, summarized from each state's statutes (orientation only, not legal advice) |
| Known tax sale pages and platforms | `county_links.py` |
| Tax sale, sheriff sale, assessor, treasurer and excess funds pages found on each county's website | `discover_links.py` crawls every official site (homepage plus its treasurer, assessor and sheriff pages) and writes `ref/discovered_links.json`; rerun monthly for counties not checked in 45 days |
| Parcel photos | County assessor and historic survey photos through the Atlanta tracker; auction catalog photos from tax-sale.info; a live Google Street View embed for every parcel with coordinates |
| Parcel-level auction data | the source adapters in `sources/` (below) |

### Sources With Parcel Data

| Adapter | Covers | What it reads |
|---|---|---|
| `sources/atlanta.py` | 40 Georgia counties | The Metro Atlanta tracker's published `data/*.json`: sale lists, results, excess funds lists, geocoded parcels |
| `sources/clark.py` | Clark County, Nevada | The Clark County tracker's `auctions.json` and `parcels.json`: every Treasurer auction since 2012 |
| `sources/michigan.py` | 79 Michigan counties | [Tax-Sale.info](https://www.tax-sale.info/) (Title Check): the upcoming-auction calendar, two years of past results, and each county catalog's CSV, photos and sold prices |
| `sources/realauction.py` | Florida (67 counties probed), Ohio (88), Texas (254) | RealAuction portals: Florida Clerk tax deed sales (`{county}.realtaxdeed.com`) and foreclosure sales (`{county}.realforeclose.com`), Ohio's statewide sheriff sale portal (`{county}.sheriffsaleauction.ohio.gov`) and Texas sheriff sale portals (`{county}.texas.sheriffsaleauctions.com`): calendars, every item with parcel, address, value and opening bid, and sold prices and buyers. These portals refuse data-center addresses, GitHub's runners included, so they are collected from a home connection (below) and the monthly refresh keeps what was collected |
| `sources/govease.py` | Every county auction open on GovEase (Colorado, Tennessee, Pennsylvania, Texas, California, Indiana, Missouri, Washington, Kansas and Oklahoma counties) | [GovEase](https://www.govease.com/): the auction menu on `liveauctions.govease.com`, each auction's parcel CSV (parcel, owner, address, starting bid, assessed value, descriptions), its type (tax deed, tax lien, foreclosure, redeemable deed) and its sale date. GovEase lists a sale until it closes and does not publish results, so these are sale lists with starting bids |
| `sources/bid4assets.py` | Every sale on the Bid4Assets County Tax Sales calendar (California, Nevada, Washington, Pennsylvania, Minnesota and Louisiana counties) | [Bid4Assets](https://www.bid4assets.com/county-tax-sales): each sale's storefront, its closing groups through the storefront API, and each item's page (parcel number, address, assessed value, legal description and parcel map, photo). Past storefronts stay online with their outcomes, so this source has sale lists before a sale and winning bids after it |

Every other county has its state rules, statutory sale date, official site and search links. Adding a county means writing one adapter that returns the record shape documented in `sources/__init__.py`; the dashboard needs no changes.

## How It Stays Current

```
Sources ──(monthly, the 1st)──> GitHub Action runs fetch_all.py
                                   ├─ data/registry.json   every county, rules, links, next sale, data summary
                                   ├─ data/index.json      national totals, posted upcoming sales, source status
                                   └─ data/counties/*.json auctions and parcels for every county a source covers
GitHub Pages serves index.html ──> browser loads the JSON and renders (plain HTML/JS, Chart.js, Leaflet, d3-geo, TopoJSON)
```

- `.github/workflows/update-data.yml` runs on the 1st of every month and on demand (**Actions > Update tax sale data > Run workflow**, with an option to recrawl every county website). It crawls county sites first, then fetches every source and rebuilds the registry and master CSVs. If a source is down, the county files from the previous run are kept.
- `fetch_all.py` also computes the next statutory sale date for every county in states that sell on a calendar (first Tuesday in Georgia and Texas, third Monday of June in Iowa, and so on) and labels it "by statute"; dates from a source are labeled "posted".
- Python standard library only; nothing to install.

## Run Locally

```bash
python3 fetch_all.py            # refresh everything (a few minutes)
python3 fetch_all.py --offline  # rebuild the registry without calling any source
python3 -m http.server 8000     # then open http://localhost:8000
```

### Collecting The RealAuction Portals (Florida, Ohio, Texas)

RealAuction's portals answer GitHub's runners with a marketing page instead of the auction calendar, so Florida tax deed and foreclosure sales and the Ohio and Texas sheriff sales are collected from an ordinary connection and committed:

```bash
python3 collect_local.py --state FL                      # every Florida portal (an hour or more)
python3 collect_local.py --county duval,orange,hillsborough
git add data && git commit -m "Collect RealAuction portal data" && git push
```

`collect_local.py` writes `data/counties/<fips>.json`, rebuilds the registry, master CSV and calendar, and the next monthly refresh keeps those files whenever the portals refuse the runner. `tools/realauction_console.js` does the same job from a browser tab (paste it into the console on a county's calendar page, save `window.__ra` as `data/raw/realauction/<fips>-<kind>.json`, then `python3 collect_local.py --import`).

## Files

- `states.py`: the rules card for every state (sale type, who holds the sale, timing, bidding, rate, redemption, foreclosure and sheriff sales, statute, platforms, notes).
- `county_links.py`: known tax sale pages and auction platforms by county FIPS.
- `registry.py`: builds the county list from the Census, Wikidata and population files.
- `sources/`: one adapter per publisher of parcel-level data.
- `fetch_all.py`: runs everything and writes `data/`, including the master CSVs.
- `master.py`: builds the master parcel and county files and the deal score.
- `discover_links.py`: finds sale and assessor links on county websites.
- `analyzer.html`, `analyzer.js`, `analyzer.css`: the Property Deal Analyzer page.
- `index.html`, `app.js`, `county.js`, `common.js`, `style.css`: the dashboard (national and state views, county pages, shared helpers).
- `sheet.html`: the printable deal sheet.
- `notify.py`: the monthly email digest.
- `collect_local.py`, `tools/realauction_console.js`, `tools/ingest_chunks.py`, `tools/decode_dumps.py`: collecting the RealAuction portals from a home connection or a browser tab.
- `CLAUDE.md` and `docs/HANDOFF.md`: working notes and the full handoff for continuing the project in [Claude Code](https://claude.com/claude-code); `.claude/commands/` holds the `/collect` and `/ship` commands.

Informational only and not affiliated with any county, state or auction platform. Rules change (several states rewrote theirs after *Tyler v. Hennepin County* in 2023) and lists change up to the day of the sale; always confirm with the county.
