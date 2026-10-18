"""Find each county's tax sale, sheriff sale, assessor, treasurer and excess funds pages on its official website.

    python3 discover_links.py              crawl every county with an official site (about 20 minutes with 16 threads)
    python3 discover_links.py --limit 50   crawl the first 50 (for testing)
    python3 discover_links.py --state TX   one state
    python3 discover_links.py --stale 60   only recrawl counties not checked in the last 60 days (default 45)

Reads the county list from registry.py and writes ref/discovered_links.json:
    {fips: {"taxsale": url, "sheriff": url, "assessor": url, "treasurer": url, "excess": url, "checked": iso, "from": site}}
Links are picked by keywords in the link text and URL on the homepage and, when the homepage has no tax sale link, on
the treasurer / tax collector page it links to. fetch_all.py merges the result into the registry.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import html as htmllib
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from registry import build_counties

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ref", "discovered_links.json")
UA = "Mozilla/5.0 (compatible; us-tax-sale-dashboard/1.0; +https://github.com/ShamarRobinson/us-tax-sale-dashboard)"

KEYS = {
    "taxsale": [r"tax[\s_-]*sales?\b", r"tax[\s_-]*deeds?\b", r"tax[\s_-]*liens?\b", r"delinquent[\s_-]*(real[\s_-]*estate|property)?[\s_-]*tax", r"tax[\s_-]*certificates?\b",
                r"tax[\s_-]*auction", r"tax[\s_-]*forfeit", r"land[\s_-]*sales?\b", r"tax[\s_-]*foreclos", r"foreclosed[\s_-]*propert", r"surplus[\s_-]*(land|propert|real)",
                r"tax[\s_-]*title", r"treasurer.{0,20}(auction|sale)", r"\bresale\b", r"struck[\s_-]*off", r"property[\s_-]*auction", r"(land|lot|parcel|property|properties)[\s_-]*(for[\s_-]*sale|auction)",
                r"tax[\s_-]*delinquent", r"delinquent[\s_-]*(list|propert|parcel|land)", r"sale[\s_-]*of[\s_-]*(tax|land|propert|county)", r"county[\s_-]*(owned|held)[\s_-]*(land|propert)", r"tax[\s_-]*resale", r"commissioners?[\s_-]*(sale|deed)"],
    "sheriff": [r"sheriff'?s?[\s_-]*sales?", r"foreclosure[\s_-]*sales?", r"judicial[\s_-]*sales?", r"mortgage[\s_-]*foreclosure", r"real[\s_-]*estate[\s_-]*sales?", r"civil[\s_-]*(process|sales?)"],
    "excess": [r"excess[\s_-]*(funds?|proceeds)", r"surplus[\s_-]*(funds?|proceeds|money)", r"\boverages?\b", r"excess[\s_-]*tax"],
    "sheriffdept": [r"^\s*sheriff('?s)?(\s+(office|department|dept))?\s*$", r"sheriff'?s?[\s_-]*(office|department)"],
    "assessor": [r"\bassessor", r"property[\s_-]*(search|lookup|records|inquiry|information|appraiser|data)", r"parcel[\s_-]*(search|lookup|viewer|map|data)",
                 r"real[\s_-]*estate[\s_-]*(search|lookup|records|inquiry)", r"\bgis\b", r"\bmapping\b", r"appraisal[\s_-]*district", r"property[\s_-]*appraiser", r"land[\s_-]*records"],
    "treasurer": [r"\btreasurer", r"tax[\s_-]*collector", r"tax[\s_-]*commissioner", r"revenue[\s_-]*commissioner", r"tax[\s_-]*claim", r"\btax[\s_-]*office", r"collector[\s_-]*of[\s_-]*revenue", r"\bfinance[\s_-]*(department|dept)", r"property[\s_-]*tax"],
}
RX = {k: [re.compile(p, re.I) for p in v] for k, v in KEYS.items()}
ANCHOR = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
SKIP = re.compile(r"\.(pdf|jpg|jpeg|png|gif|zip|doc|docx|xls|xlsx|mp4)(\?|$)|^(mailto|tel|javascript):|#$", re.I)
PDF_OK_FOR = ("taxsale", "excess", "sheriff")


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final = r.geturl()
        raw = r.read(2_000_000)
    return final, raw.decode("utf-8", "replace")


def links(base, page):
    out = []
    for href, text in ANCHOR.findall(page):
        text = htmllib.unescape(re.sub(r"<[^>]+>", " ", text))
        text = re.sub(r"\s+", " ", text).strip()
        href = htmllib.unescape(href.strip())
        if href.startswith("//"):
            href = "https:" + href
        url = urllib.parse.urljoin(base, href)
        if not url.startswith("http"):
            continue
        out.append((url, text))
    return out


def score(url, text, cat):
    """Higher is better: a keyword in the link text beats one only in the URL; shorter paths beat deeper ones."""
    s = 0
    for rx in RX[cat]:
        if rx.search(text):
            s += 10
        if rx.search(urllib.parse.unquote(url)):
            s += 4
    if s and SKIP.search(url):
        if cat in PDF_OK_FOR and url.lower().split("?")[0].endswith(".pdf"):
            s -= 3
        else:
            return 0
    if s:
        s -= min(5, urllib.parse.urlparse(url).path.count("/"))
    return s


def pick(found, base_host):
    best = {}
    for url, text in found:
        host = urllib.parse.urlparse(url).hostname or ""
        for cat in KEYS:
            sc = score(url, text, cat)
            if sc <= 0:
                continue
            if cat == "taxsale" and re.search(r"\b(exempt|homestead|appeal|payment plan|pay (your|my) tax)", text, re.I):
                continue
            if host != base_host and not host.endswith("." + base_host.replace("www.", "")):
                sc -= 2  # external sites are fine (many counties outsource) but prefer the county's own page
            if sc > best.get(cat, (0, None))[0]:
                best[cat] = (sc, url)
    return {k: v[1] for k, v in best.items()}


def crawl(c):
    site = c.get("site")
    if not site:
        return c["fips"], None
    try:
        final, page = fetch(site)
    except Exception as e:
        return c["fips"], {"error": str(e)[:120], "checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "from": site}
    host = urllib.parse.urlparse(final).hostname or ""
    found = links(final, page)
    res = pick(found, host)
    # second hop: the treasurer / tax office, assessor and sheriff department pages usually hold the sale links
    for hopkey, wants in (("treasurer", ("taxsale", "excess", "sheriff")), ("assessor", ("taxsale", "excess")), ("sheriffdept", ("sheriff", "taxsale"))):
        hop = res.get(hopkey)
        if not hop or SKIP.search(hop) or all(k in res for k in wants):
            continue
        try:
            f2, p2 = fetch(hop, timeout=15)
            res2 = pick(links(f2, p2), urllib.parse.urlparse(f2).hostname or "")
            for k in wants:
                if k not in res and k in res2:
                    res[k] = res2[k]
        except Exception:
            pass
    res.pop("sheriffdept", None)
    res["checked"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    res["from"] = final
    return c["fips"], res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--state")
    ap.add_argument("--stale", type=int, default=45)
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    counties = [c for c in build_counties() if c.get("site")]
    if a.state:
        counties = [c for c in counties if c["state"] == a.state.upper()]
    try:
        with open(OUT, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        prev = {}
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.stale)).isoformat()
    todo = [c for c in counties if not prev.get(c["fips"]) or prev[c["fips"]].get("error") or (prev[c["fips"]].get("checked") or "") < cutoff]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(counties)} counties with a site, {len(todo)} to crawl")
    done = 0
    with cf.ThreadPoolExecutor(max_workers=a.threads) as ex:
        for fips, res in ex.map(crawl, todo):
            if res:
                prev[fips] = res
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(todo)}")
                with open(OUT, "w", encoding="utf-8") as f:
                    json.dump(prev, f, ensure_ascii=False, indent=0, sort_keys=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(prev, f, ensure_ascii=False, indent=0, sort_keys=True)
    ok = [v for v in prev.values() if v and not v.get("error")]
    print(f"saved {len(prev)} counties: {sum(1 for v in ok if v.get('taxsale'))} tax sale, {sum(1 for v in ok if v.get('sheriff'))} sheriff, "
          f"{sum(1 for v in ok if v.get('assessor'))} assessor, {sum(1 for v in ok if v.get('excess'))} excess funds, {sum(1 for v in prev.values() if v and v.get('error'))} errors")


if __name__ == "__main__":
    main()
