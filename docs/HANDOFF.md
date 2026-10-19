# Handoff From The Claude Session That Built This Tracker

Written 2026-10-18 at the end of the Claude session
https://claude.ai/code/session_0186Htxm6yjesny38nJy4aXQ so the work can continue in Claude Code. The short version
that Claude Code loads automatically is [CLAUDE.md](../CLAUDE.md); this file keeps the detail.

## 1. What Shamar Asked For (In Order)

1. Take the context from the Clark County and Metro Atlanta trackers and make a new tracker for every county in every
   state nationwide for tax deed auctions, sheriff sales and so on, in a new GitHub repo named accordingly.
2. Authenticate GitHub and push as Shamar.
3. Update monthly, not weekly.
4. Use dropdown menus and nested graphs.
5. Gather all of the data, photos and links now.
6. At the same time, create a master CSV with all of the data to be used as a Property Deal Analyzer, on its own
   dedicated page. All data must be added to the master CSV concurrently as the tracker is built.
7. Make sure all of the features in the Metro Atlanta and Clark County trackers are incorporated; every county page
   needs the full capabilities of both, plus capabilities Shamar had not thought of.
8. Continue in Claude Code with everything packaged (this document).

## 2. Repositories

| Repo | Live site | Role |
|---|---|---|
| https://github.com/ShamarRobinson/us-tax-sale-dashboard | https://shamarrobinson.github.io/us-tax-sale-dashboard/ | This project |
| https://github.com/ShamarRobinson/clark-county-tax-auction-dashboard | https://shamarrobinson.github.io/clark-county-tax-auction-dashboard/ | Clark County, NV Treasurer auctions since 2012; read by `sources/clark.py` from `auctions.json` and `parcels.json` |
| https://github.com/ShamarRobinson/atlanta-tax-sale-dashboard | https://shamarrobinson.github.io/atlanta-tax-sale-dashboard/ | 40 Georgia counties within 52 miles of downtown Atlanta; read by `sources/atlanta.py` from its published `data/*.json` |

All 31 human commits on this repo are authored `Shamar Robinson <shamarrobinson31@gmail.com>`; the other four are the
monthly `github-actions[bot]` data runs. Keep it that way.

## 3. How The Site Is Built

- Static GitHub Pages site, plain HTML, CSS and JavaScript: `index.html` with `app.js` (national and state views),
  `county.js` (county pages at `index.html#c/<fips>`), `common.js` (shared helpers), `analyzer.html` with
  `analyzer.js` and `analyzer.css` (Property Deal Analyzer over the per-state shards in `data/master/`),
  `sheet.html` (printable deal sheet). Libraries: Chart.js, Leaflet, d3-geo, TopoJSON (us-atlas county boundaries in
  `ref/us-counties-10m.json`).
- Python pipeline, standard library only: `registry.py` (county list from `ref/census_gazetteer_2024.txt`,
  `ref/census_pop_2024.csv`, `ref/wikidata_county_websites.csv`), `states.py` (rules card per state), `county_links.py`
  (known sale pages and platforms by FIPS), `discover_links.py` (crawls every official county site for tax sale,
  sheriff sale, assessor, treasurer and excess funds pages into `ref/discovered_links.json`), `sources/` (adapters),
  `fetch_all.py` (runs everything, `--offline` rebuilds from local files), `master.py` (master CSV, county CSV, deal
  score), `notify.py` (monthly email digest), `collect_local.py` (RealAuction collection and `--import`).
- Outputs in `data/`: `registry.json`, `index.json`, `counties/<fips>.json`, `master/<ST>.csv`, `master/<ST>.json`, `master/index.json`,
  `master_counties.csv`, `changes.json`, `upcoming.ics`, `raw/realauction/<fips>-<kind>.json`.
- Workflow `.github/workflows/update-data.yml`: cron `23 13 1 * *` (the 1st, about 6:23 AM Pacific), manual dispatch
  with an option to recrawl county websites, and pushes to `main` touching `*.py`, `sources/*.py` or the workflow. It
  keeps county files for FIPS codes no adapter returned, which is what protects the hand-collected portal data.
- Master parcel columns: fips, county, state, system, saleKind, source, auctionDate, auctionStatus, auctionLabel,
  parcel, caseNo, certificate, lot, address, fullAddress, area, zip, owner, buyer, plaintiff, type, status, soldAt,
  minBid, winningBid, multiple, excess, value, bidToValue, winToValue, judgment, taxes, acres, sqft, yearBuilt,
  years, yearsUnpaid, tenure, priorAuctions, lat, lon, googleMaps, streetView, photo, photoCredit, listing,
  sourceDoc, parcelRecord, countyMap, countyPage, redemptionMonths, rate, countyMedianMultiple, dealScore,
  dealRating, typeDetail, desc.

## 4. Data Status

As of commit `330afcc` (2026-10-18): 31,638 parcels, 230 counties with parcel data.

| State | Counties | Parcels | Source |
|---|---|---|---|
| FL | 35 | 16,058 | RealAuction tax deed (35 portals) and foreclosure (9 portals: Miami-Dade, Broward, Palm Beach, Hillsborough, Orange, Duval, Pinellas, Lee, Polk) |
| MI | 79 | 7,359 | tax-sale.info (Title Check) |
| GA | 24 | 3,931 | Metro Atlanta tracker |
| OH | 87 | 3,501 | RealAuction sheriff portal (all but Vinton, which is empty) |
| NV | 1 | 736 | Clark County tracker |
| CO | 4 | 53 | RealAuction treasurer deed portals |

Uncollected RealAuction portals, by population: see the list in [CLAUDE.md](../CLAUDE.md). The five largest Florida
foreclosure portals were collected with `monthsBack = 1` to bound transcription volume; the tax deed portals and Ohio
were collected with the default 3 months back. Every collector run covers the current month plus two ahead.

## 5. RealAuction Portals

### 5.1 Protocol (Mirrored In `sources/realauction.py` And `tools/realauction_console.js`)

1. Calendar: `/index.cfm?zaction=USER&zmethod=CALENDAR&selCalDate=MM/01/YYYY`; days with sales are `CALBOX` divs
   carrying `dayid`.
2. Day preview: `zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=MM/DD/YYYY` sets the session's sale date.
3. Item pages: `zaction=AUCTION&Zmethod=UPDATE&FNC=LOAD&AREA=W|C&PageDir=0|1&doR=1&bypassPage=0&test=1` (area `W`
   waiting, `C` closed), paged until the ids repeat.
4. Status refresh: `zaction=AUCTION&ZMETHOD=UPDATE&FNC=UPDATE&ref=ID,ID,` for the page the session is on returns
   sold, cancelled, redeemed and rescheduled statuses, sold amounts and buyers.
5. `clean_auctions(auctions, kind)` drops placeholder parcel ids such as "Property Appraiser" and "MULTIPLE PARCELS",
   drops appraiser links without a folio, fixes ZIP codes and sets `portal` and `saleKind`.

Hosts: Florida `{county}.realtaxdeed.com` and `{county}.realforeclose.com` with the exceptions in `SITES`
(myorangeclerk, nassauclerk, saintjohns, stlucie, indian-river, santarosa); Ohio `{county}.sheriffsaleauction.ohio.gov`;
Texas `{county}.texas.sheriffsaleauctions.com` for the 28 counties in `TX_SHERIFF` (the other 226 hostnames do not
resolve; probed from a browser in October 2026); Colorado `*.treasurersdeedsale.realtaxdeed.com` and
`*.realforeclose.com`; Arizona `*.realtaxdeed.com`; New Jersey `newarknj.realforeclose.com` and
`hardystonnj.realforeclose.com`.

### 5.2 The Easy Path (Claude Code On The Mac)

The portals only refuse data-center addresses. From a residential connection:

```bash
python3 collect_local.py --county pasco,brevard,volusia,seminole
python3 collect_local.py --state FL          # every Florida portal, an hour or more
python3 collect_local.py --state TX
git add data && git commit -m "Collect RealAuction portal data for Florida" && git push
```

`collect_local.py` writes `data/counties/<fips>.json`, then runs `fetch_all.py --offline` so the registry, index,
master CSV, changes and calendar are all rebuilt in the same step. `--no-rebuild` skips that.

### 5.3 The Hard Path (Browser Tab Transcription), Kept For Reference

Used in the original session because the cloud workspace could not reach the portals and the Mac had no connected
folders. Everything needed is in the repo:

1. Open the county's calendar page in a browser tab and run
   `window.__kind = "foreclosure"; window.__fips = "12105"; window.__monthsBack = 1;
   const src = await (await fetch("https://shamarrobinson.github.io/us-tax-sale-dashboard/tools/realauction_console.js?v=" + Date.now())).text();
   (0, eval)(src);` The collector sets `window.__done` when finished and `window.__err` on failure.
   `window.__monthsBack || 3` means 0 is not possible.
2. `await window.__pack()` gzips and base64-encodes `window.__ra` into `window.__gz`; `window.__chunk(i, 1500)` returns
   `{i, crc, d}` for piece `i` (CRC-32 of the piece). Copy pieces as lines `index crc base64`.
3. `python3 tools/ingest_chunks.py <kind> < pasted.txt` writes `data/raw/realauction/<fips>-<kind>.chunks`;
   `python3 tools/decode_dumps.py` verifies every CRC and writes `<fips>-<kind>.json`. "Compressed file ended before
   the end-of-stream marker" means pieces are missing; "bad CRC pieces [n]" means piece n was transcribed wrong.
4. To fix a bad piece without re-copying it: in the browser
   `(() => { const d = window.__chunk(N, 1500).d; return Array.from({length: 10}, (_, k) => k + ':' + window.__crc(d.slice(k * 150, (k + 1) * 150))).join(' '); })()`,
   compare with `zlib.crc32` locally, copy only the 150-character slice that differs and patch it into the `.chunks`
   line. Transcription slips were single characters about one piece in twenty (for example `bPzn` for `bOzn`).
5. `python3 collect_local.py --import`, commit, push.

### 5.4 Things That Did Not Work (Do Not Retry Them)

- Reaching the portals from the Anthropic cloud workspace (marketing page every time). GitHub Actions was refused the
  same way while the project was built, but the monthly workflow's run on the night of 2026-10-18 reached 155
  counties from the runner, so that part no longer holds; keep `collect_local.py` for what the runner misses.
- Publishing a drop page as a Claude artifact and navigating the built-in browser to claude.ai to upload a dump; the
  browser could not open claude.ai from that session.
- Requesting Downloads folder access on the Mac (declined). Claude Code on the Mac has the filesystem anyway.

## 6. Conventions

- Author every commit as Shamar (`git config user.name "Shamar Robinson"`, `git config user.email
  "shamarrobinson31@gmail.com"`, or `-c` overrides on the commit). Keep Claude Code's `Co-Authored-By` trailer.
- Rebase before pushing: `git fetch origin && git rebase origin/main && git push origin HEAD`. The monthly bot commit
  can land at any time.
- Confirm the deploy: `gh run list --workflow=pages-build-deployment --limit 1 --json status,conclusion,headSha -q '.[0]'`.
- Title Case for titles and subheadings; no em dashes in body text; include links; monthly cadence; dropdowns and
  nested charts for navigation.
- Everything in the pipeline is Python standard library. Front end has no build step.

## 7. Feature Parity Checklist (Sibling Trackers)

From Clark County: average winning bid, parcels sold, total bids, bidding wars and excess proceeds KPIs; cost tiers by
minimum bid with average winning bid per tier; parcel types from assessor land-use codes; map with average bid and
bidding-war rate by area; all-parcels grid with correct site address (or nearest street for unaddressed land),
sold status, prior auctions, estimated years unpaid, deal score 0 to 100, column show, hide, reorder and pivot;
bidding wars (count above minimum and biggest jumps); time in default (years unpaid, former owner tenure, unclaimed
excess age); email alerts via repository secrets; weekly Action (monthly here).

From Metro Atlanta: region overview map, upcoming sales, county table and winning bids compared across counties; a
tab per county with its own link; who runs the sale, schedule, links to the sale page, excess funds and parcel lookup;
auction dropdown with every sale on file (upcoming lists, published results, excess funds lists); bid stats (average,
median, lowest, highest, most frequent); cost tiers, auction history, bidding multiples, most active buyers; geocoded
parcel map; parcel grid with sorting, column controls, pivots and CSV download; search across every county and field
(`county:gwinnett won>100000`); Census geocoder for street addresses; assessor photos and Street View.

Added in the US tracker beyond both: every county in every state with state rules cards, statutory next sale dates,
official and discovered links, nested national, state and county views, the Property Deal Analyzer page over the
master CSV, printable deal sheet, iCalendar feed, changes feed, JSON and CSV endpoints usable as an API, and the
monthly digest.

## 8. Ideas Not Yet Built

- More statewide platforms as adapters: LienHub and Grant Street (403 to a cloud address), GovDeals, Civic Source,
  and the treasurer sites that publish PDF lists (reuse the
  Atlanta tracker's `ga_common.py` approach for PDF and OCR). Added on 2026-10-18 from Claude Code on the web:
  GovEase (`sources/govease.py`), Bid4Assets county tax sales (`sources/bid4assets.py`), MVBA Texas online tax sales
  (`sources/mvba.py`) and Bid4Assets sheriff's sales (`sources/b4a_sheriff.py`). Bid4Assets answers only browser user
  agents (a plain Mozilla string, nothing appended). Added on 2026-10-19: SRI Inc. (`sources/sri.py`), which reads the
  public JSON API behind https://www.sriservices.com/properties (the client key is in the site's own JavaScript), so
  the Zeus Auction site itself never has to be scraped. If zeusauction.com or civicsource.com ever do have to be read,
  both serve an incomplete TLS chain; load GoDaddy's intermediates (gdig2.crt and gd_tls_issuing_dv-r1v1.crt from
  https://certificates.godaddy.com/repository/) into `ssl.create_default_context()` with `load_verify_locations` and
  they verify. Also added on 2026-10-19: the Arkansas Commissioner of State Lands online auction (`sources/cosl.py`)
  and ILTaxSale.com for Illinois (`sources/iltaxsale.py`, with `sources/pdftext.py` to read the results PDFs without
  installing anything). Still to try: the New York tax foreclosure auctions on aarauctions.com (a few parcels per
  county, catalog pages at /servlet/Search.do?auctionId=N), the West Virginia State Auditor's delinquent land search
  (wvsao.gov, an ASP.NET postback form) and Mississippi's tax-forfeited inventory (sos.ms.gov/tfsearch, the same kind
  of form; these are state-held parcels at fixed prices rather than auctions). The RealAuction roster gained the 152 tax
  lien portals listed on realauction.com (New Jersey municipalities, Maryland counties, Bogalusa); they could not be
  read from the cloud, so check the first monthly run's log for them and fix the row labels in `to_parcel` if the
  parcels come back without block and lot or amount due.
- Philadelphia sheriff sales (https://www.bid4assets.com/philadelphia) turned out to be a hub in front of two
  ordinary landing pages, `/philataxsales` and `/philaforeclosures`; `sources/b4a_sheriff.py` reads them since
  2026-10-19 (about 1,500 properties listed at a time).
- The monthly workflow's fetch step took 2 hours 42 minutes on 2026-10-19 because `sources/realauction.py` collected
  212 portals one at a time; it now collects six at a time (`THREADS`), which should bring the run under an hour.
  Check the next run's timing in the Actions log.
- Deeper history for the big Florida foreclosure portals (rerun with the default 3 months or more from the Mac).
- Per-county alert subscriptions and a saved-search feature in the analyzer.
- A Street View and assessor photo cache like the Atlanta tracker's `photo_store.py` for counties without photos.
