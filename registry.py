"""Every county (and county equivalent) in the United States, built from Census files plus the state rules.

Sources, all in ref/:
  census_gazetteer_2024.txt       Census Bureau 2024 Gazetteer: FIPS, name, land area, internal point (lat/lon)
  census_pop_2024.csv             Census Bureau Vintage 2024 population estimates
  wikidata_county_websites.csv    Wikidata: official website (P856) for each county by FIPS (P882)

county_links.py adds the tax sale page, who runs it and the auction platform for counties where that is known.
Everything else gets a search link so the county's own page is always one click away.
"""
import csv
import os
import re
import urllib.parse

from states import STATE_BY_ABBR
import county_links

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "ref")

SUFFIXES = re.compile(r"\s+(County|Parish|Borough|Census Area|Municipality|City and Borough|Planning Region|Municipio|city)$")


def _slug(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _search(q):
    return "https://duckduckgo.com/?q=" + urllib.parse.quote_plus(q)


def load_population():
    pop = {}
    with open(os.path.join(REF, "census_pop_2024.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                pop[r["fips"]] = int(r["pop2024"])
            except ValueError:
                pass
    return pop


def load_websites():
    sites = {}
    with open(os.path.join(REF, "wikidata_county_websites.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fips = r["fips"].strip().zfill(5)
            url = (r.get("site") or "").strip()
            if not url:
                continue
            # prefer https and .gov when Wikidata lists several
            cur = sites.get(fips)
            if cur is None or (".gov" in url and ".gov" not in cur) or (url.startswith("https") and not cur.startswith("https")):
                sites[fips] = url
    return sites


def build_counties():
    pop = load_population()
    sites = load_websites()
    counties = []
    with open(os.path.join(REF, "census_gazetteer_2024.txt"), encoding="utf-8") as f:
        rows = csv.DictReader(f, delimiter="\t")
        for r in rows:
            r = {k.strip(): (v or "").strip() for k, v in r.items()}
            fips = r["GEOID"]
            abbr = r["USPS"]
            st = STATE_BY_ABBR.get(abbr)
            if not st:
                continue
            label = r["NAME"]
            name = SUFFIXES.sub("", label)
            if abbr == "VA" and label.endswith(" city"):
                name = label[:-5] + " (city)"
            if abbr == "LA" and label.endswith(" Parish"):
                pass
            link = county_links.LINKS.get(fips, {})
            unit = "County"
            m = SUFFIXES.search(label)
            if m:
                unit = m.group(1).replace("city", "Independent city")
            c = dict(
                fips=fips,
                state=abbr,
                name=name,
                label=label,
                unit=unit,
                lat=float(r["INTPTLAT"]),
                lon=float(r["INTPTLONG"]),
                landSqmi=float(r["ALAND_SQMI"] or 0),
                pop=pop.get(fips),
                site=link.get("site") or sites.get(fips),
                taxsale=link.get("taxsale"),
                run=link.get("run"),
                platform=link.get("platform"),
                note=link.get("note"),
            )
            if st.get("state_portal") and not c["taxsale"]:
                c["taxsale"] = st["state_portal"]
                c["taxsaleKind"] = "state"
            elif c["taxsale"]:
                c["taxsaleKind"] = "county"
            counties.append(c)
    counties.sort(key=lambda c: (c["state"], c["name"]))
    return counties


if __name__ == "__main__":
    cs = build_counties()
    print(len(cs), "counties")
    print(sum(1 for c in cs if c["site"]), "with official site")
    print(sum(1 for c in cs if c["taxsale"]), "with tax sale link")
