"""Known tax sale pages and auction platforms for individual counties, keyed by 5-digit FIPS.

Only counties where the page is known are listed here; every other county gets a search link in the dashboard
plus its official website from Wikidata. The source adapters in sources/ add or overwrite entries for the counties
they cover (Metro Atlanta, Clark County NV, Michigan), so this file is for counties with no automated source yet.

Fields: taxsale (the sale page), site (official site, when Wikidata's is missing or wrong), run (who holds the sale),
platform (auction platform name), note.
"""

LINKS = {
    # Nevada
    "32003": dict(taxsale="https://treasurer.clarkcountynv.gov/auction", run="County Treasurer", platform="County auction site",
                  note="Trustee auction of parcels held in trust by the Treasurer; registration deposit required."),
    "32031": dict(taxsale="https://www.washoecounty.gov/treas/", run="County Treasurer", note="Trustee property auction, usually in April."),
    # Texas
    "48201": dict(taxsale="https://www.hctax.net/Property/TaxSales", run="County Constables (eight precincts)", platform="In person, Bayou City Event Center",
                  note="Monthly, first Tuesday; all eight constable precincts sell at the same venue."),
    "48453": dict(taxsale="https://tax-office.traviscountytx.gov/", run="County Sheriff", note="Monthly, first Tuesday."),
    # California
    "06037": dict(taxsale="https://ttc.lacounty.gov/auctions/", run="Treasurer and Tax Collector", platform="Bid4Assets"),
    "06073": dict(taxsale="https://www.sdttc.com/", run="Treasurer-Tax Collector", platform="Bid4Assets"),
    "06059": dict(taxsale="https://ttc.ocgov.com/", run="Treasurer-Tax Collector", platform="Bid4Assets"),
    "06065": dict(taxsale="https://www.countytreasurer.org/", run="Treasurer-Tax Collector", platform="Bid4Assets"),
    "06071": dict(taxsale="https://www.mytaxcollector.com/", run="Auditor-Controller/Treasurer/Tax Collector", platform="Bid4Assets"),
    "06067": dict(taxsale="https://finance.saccounty.gov/Tax/", run="Tax Collector", platform="Bid4Assets"),
    "06075": dict(taxsale="https://sftreasurer.org/", run="Treasurer and Tax Collector", platform="Bid4Assets"),
    "06001": dict(taxsale="https://www.acgov.org/treasurer/", run="Treasurer-Tax Collector", platform="Bid4Assets"),
    "06085": dict(taxsale="https://dtac.santaclaracounty.gov/", run="Department of Tax and Collections", platform="Bid4Assets"),
    # Arizona (RealAuction tax lien portals)
    "04013": dict(taxsale="https://maricopa.arizonataxsale.com/", run="County Treasurer", platform="RealAuction"),
    "04021": dict(taxsale="https://pinal.arizonataxsale.com/", run="County Treasurer", platform="RealAuction"),
    "04025": dict(taxsale="https://yavapai.arizonataxsale.com/", run="County Treasurer", platform="RealAuction"),
    "04015": dict(taxsale="https://mohave.arizonataxsale.com/", run="County Treasurer", platform="RealAuction"),
    "04005": dict(taxsale="https://coconino.arizonataxsale.com/", run="County Treasurer", platform="RealAuction"),
    "04027": dict(taxsale="https://yuma.arizonataxsale.com/", run="County Treasurer", platform="RealAuction"),
    # Colorado (RealAuction tax lien portals)
    "08031": dict(taxsale="https://denver.coloradotaxsale.com/", run="City and County Treasurer", platform="RealAuction"),
    "08041": dict(taxsale="https://elpaso.coloradotaxsale.com/", run="County Treasurer", platform="RealAuction"),
    "08005": dict(taxsale="https://arapahoe.coloradotaxsale.com/", run="County Treasurer", platform="RealAuction"),
    "08001": dict(taxsale="https://adams.coloradotaxsale.com/", run="County Treasurer", platform="RealAuction"),
    "08013": dict(taxsale="https://boulder.coloradotaxsale.com/", run="County Treasurer", platform="RealAuction"),
    "08035": dict(taxsale="https://douglas.coloradotaxsale.com/", run="County Treasurer", platform="RealAuction"),
    "08069": dict(taxsale="https://larimer.coloradotaxsale.com/", run="County Treasurer", platform="RealAuction"),
    "08123": dict(taxsale="https://weld.coloradotaxsale.com/", run="County Treasurer", platform="RealAuction"),
    # District of Columbia
    "11001": dict(taxsale="https://otr.cfo.dc.gov/page/real-property-tax-sale", run="Office of Tax and Revenue", platform="OTR online tax sale"),
    # Florida (Clerk tax deed portals)
    "12086": dict(taxsale="https://www.miamidade.realtaxdeed.com/", run="Clerk of the Court (tax deeds); Tax Collector (certificates)", platform="RealAuction"),
    "12011": dict(taxsale="https://broward.deedauction.net/", run="Records, Taxes and Treasury Division", platform="Grant Street DeedAuction"),
    "12095": dict(taxsale="https://www.orange.realtaxdeed.com/", run="Comptroller (tax deeds)", platform="RealAuction"),
    "12057": dict(taxsale="https://www.hillsborough.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12103": dict(taxsale="https://www.pinellas.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12031": dict(taxsale="https://www.duval.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12099": dict(taxsale="https://www.palmbeach.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12071": dict(taxsale="https://www.lee.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12105": dict(taxsale="https://www.polk.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12009": dict(taxsale="https://www.brevard.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12127": dict(taxsale="https://www.volusia.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    "12117": dict(taxsale="https://www.seminole.realtaxdeed.com/", run="Clerk of Court (tax deeds)", platform="RealAuction"),
    # Illinois
    "17031": dict(taxsale="https://www.cookcountytreasurer.com/", run="County Treasurer", note="Annual Tax Sale plus the biennial Scavenger Sale."),
    # Michigan
    "26163": dict(taxsale="https://www.waynecountytreasurermi.com/", run="County Treasurer", note="Wayne County runs its own foreclosure auctions."),
    # Ohio (statewide online sheriff sale portal)
    "39049": dict(taxsale="https://franklin.sheriffsaleauction.ohio.gov/", run="County Sheriff (foreclosure sales); Treasurer (tax lien certificates)", platform="RealAuction (Ohio sheriff sale portal)"),
    "39035": dict(taxsale="https://cuyahoga.sheriffsaleauction.ohio.gov/", run="County Sheriff (foreclosure sales); Treasurer (tax lien certificates)", platform="RealAuction (Ohio sheriff sale portal)"),
    "39061": dict(taxsale="https://hamilton.sheriffsaleauction.ohio.gov/", run="County Sheriff (foreclosure sales); Treasurer (tax lien certificates)", platform="RealAuction (Ohio sheriff sale portal)"),
    # Pennsylvania
    "42101": dict(taxsale="https://phillysheriff.com/", run="Sheriff of Philadelphia", platform="Bid4Assets", note="Tax and mortgage foreclosure sheriff sales, online."),
    # New York City (one lien sale for all five boroughs)
    "36005": dict(taxsale="https://www.nyc.gov/site/finance/property/property-lien-sales.page", run="NYC Department of Finance", note="Tax lien sale covering all five boroughs."),
    "36047": dict(taxsale="https://www.nyc.gov/site/finance/property/property-lien-sales.page", run="NYC Department of Finance", note="Tax lien sale covering all five boroughs."),
    "36061": dict(taxsale="https://www.nyc.gov/site/finance/property/property-lien-sales.page", run="NYC Department of Finance", note="Tax lien sale covering all five boroughs."),
    "36081": dict(taxsale="https://www.nyc.gov/site/finance/property/property-lien-sales.page", run="NYC Department of Finance", note="Tax lien sale covering all five boroughs."),
    "36085": dict(taxsale="https://www.nyc.gov/site/finance/property/property-lien-sales.page", run="NYC Department of Finance", note="Tax lien sale covering all five boroughs."),
    # Maryland
    "24510": dict(taxsale="https://www.bidbaltimore.com/", run="Department of Finance", platform="BidBaltimore (RealAuction)"),
    # Tennessee
    "47157": dict(taxsale="https://www.shelbycountytrustee.com/", run="County Trustee; Chancery Court Clerk and Master holds the sale"),
    # Louisiana
    "22071": dict(taxsale="https://www.civicsource.com/", run="City of New Orleans (Bureau of Treasury)", platform="CivicSource"),
    # South Carolina
    "45019": dict(taxsale="https://www.charlestoncounty.org/departments/delinquent-tax/", run="Delinquent Tax Office"),
    # Minnesota
    "27053": dict(taxsale="https://www.hennepin.us/residents/property/tax-forfeited-land", run="County Resident and Real Estate Services"),
    # Kentucky
    "21111": dict(taxsale="https://jeffersoncountyclerk.org/", run="County Clerk (certificates of delinquency)"),
    # Hawaii
    "15003": dict(taxsale="https://www.realpropertyhonolulu.com/", run="Real Property Assessment Division"),
}

# Platforms the dashboard links to by name
PLATFORMS = {
    "Bid4Assets": "https://www.bid4assets.com/",
    "RealAuction": "https://www.realauction.com/",
    "GovEase": "https://www.govease.com/",
    "Zeus Auction": "https://www.zeusauction.com/",
    "SRI": "https://www.sriservices.com/",
    "Grant Street": "https://www.grantstreet.com/",
    "LienHub": "https://lienhub.com/",
    "CivicSource": "https://www.civicsource.com/",
    "Tax-Sale.info": "https://www.tax-sale.info/",
    "Auctions International": "https://www.auctionsinternational.com/",
    "Wisconsin Surplus": "https://www.wisconsinsurplus.com/",
    "GovDeals": "https://www.govdeals.com/",
    "Commissioner of State Lands (AR)": "https://www.cosl.org/",
    "NM Property Tax Division": "https://www.tax.newmexico.gov/property-tax-division/",
    "WV State Auditor": "https://www.wvsao.gov/",
    "TACS (VA)": "https://taxva.com/",
    "For Sale At Auction (VA)": "https://www.forsaleatauction.biz/",
    "Joseph E. Meyer & Associates (IL)": "https://www.iltaxsale.com/",
}
