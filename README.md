# US Tax Sale Tracker

Live dashboard: **https://shamarrobinson.github.io/us-tax-sale-dashboard/**

Tax deed auctions, tax lien sales, redeemable deed sales and sheriff sales for every county in every state: all 3,222 counties and county equivalents in the 50 states, the District of Columbia and Puerto Rico. It grew out of the [Clark County Tax Auction Tracker](https://github.com/ShamarRobinson/clark-county-tax-auction-dashboard) and the [Metro Atlanta Tax Sale Tracker](https://github.com/ShamarRobinson/atlanta-tax-sale-dashboard), which feed it directly.

## What It Shows

- **National overview:** a map of the United States colored by how each state sells delinquent property (tax deed, tax lien, redeemable deed or hybrid), the next sale dates fixed by statute, every sale date posted by a source, and a table of all states with their rules.
- **A tab per state** (with its own link, e.g. `#ga`): who holds the sale, when, how bidding works, the interest or penalty rate, the redemption period, how mortgage foreclosures and sheriff sales work in that state, the statute, the auction platforms in use, and a county map and table.
- **A page per county** (e.g. `#ga/fulton` or `#c/13121`): who runs the sale, the next sale date (posted or by statute), the tax sale page when known, the official county site, parcel lookup and sheriff sale links, population and land area, and the state rules.
- **Parcel-level data** where a source publishes it: an auction picker, bid statistics, cost tiers, auction history, a parcel map and a sortable parcel grid with CSV download, the same way the Atlanta tracker works.
- **Dropdown navigation:** State, County, Sale type and Show menus in the header cascade into each other (pick a state, then a county, then an auction).
- **Drill-down charts:** every chart is nested. On the national page, sale system > states > state page; parcels by state > counties > county page; posted sales by month > counties. On a state page, group counties by data status, next sale month, population tier or who holds the sale, then click a bar to list the counties, then open one. On a county page, cost tier > parcels (opening bid against winning bid) > parcel details, and the auction history bars switch the auction picker.
- **Search** across every county, e.g. `state:tx`, `type:lien next:2026-12`, `data:yes state:mi`, `run:sheriff`, `pop>500k`.

## Property Deal Analyzer And Master CSV

- **[Property Deal Analyzer](https://shamarrobinson.github.io/us-tax-sale-dashboard/analyzer.html)** (`analyzer.html`): every parcel on file, rescored with your own assumptions (target discount to county value, repair and closing allowance, budget, value fallback). Filters by state, county, sale type and kind, status, property type, bid and value ranges, photos and coordinates; drill-down charts; a bid-against-value scatter; a map; a sortable grid; a photo and Street View gallery; CSV download of whatever is in view.
- **Master CSVs**, rebuilt by `fetch_all.py` on every run so every source flows into them: `data/master_parcels.csv` (one row per parcel: county, sale, parcel, address, owner, buyer, bids, multiple, excess, county value, bid-to-value, size, coordinates, Google Maps and Street View links, photo, listing and source links, redemption period, rate, county median multiple, deal score) and `data/master_counties.csv` (every county with its rules, links and next sale). `data/master.json` is the same parcel data for the analyzer page.
- **Deal score** (0 to 100, a screening aid): value 40 (opening bid against county value), property 20 (improved beats vacant), competition 15 (how far above the opening bid parcels sell in that county), timing and redemption 15, data 10 (coordinates, value, photo). 70 and up Strong, 50 to 69 Good, 35 to 49 Fair, under 35 Weak.

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
| `sources/realauction.py` | Florida (67 counties probed), Ohio (88), Texas (254) | RealAuction portals: Florida Clerk tax deed sales (`{county}.realtaxdeed.com`) and foreclosure sales (`{county}.realforeclose.com`), Ohio's statewide sheriff sale portal (`{county}.sheriffsaleauction.ohio.gov`) and Texas sheriff sale portals (`{county}.texas.sheriffsaleauctions.com`): calendars, every item with parcel, address, value and opening bid, and sold prices and buyers |

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

## Files

- `states.py`: the rules card for every state (sale type, who holds the sale, timing, bidding, rate, redemption, foreclosure and sheriff sales, statute, platforms, notes).
- `county_links.py`: known tax sale pages and auction platforms by county FIPS.
- `registry.py`: builds the county list from the Census, Wikidata and population files.
- `sources/`: one adapter per publisher of parcel-level data.
- `fetch_all.py`: runs everything and writes `data/`, including the master CSVs.
- `master.py`: builds the master parcel and county files and the deal score.
- `discover_links.py`: finds sale and assessor links on county websites.
- `analyzer.html`, `analyzer.js`, `analyzer.css`: the Property Deal Analyzer page.
- `index.html`, `app.js`, `style.css`: the dashboard.

Informational only and not affiliated with any county, state or auction platform. Rules change (several states rewrote theirs after *Tyler v. Hennepin County* in 2023) and lists change up to the day of the sale; always confirm with the county.
