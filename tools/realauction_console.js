// RealAuction portal collector that runs inside a browser tab (the portals refuse data-center addresses, so GitHub's
// runner cannot read them; a home connection can). Open the county's calendar page, for example
//   https://duval.realtaxdeed.com/index.cfm?zaction=USER&zmethod=CALENDAR
// then paste this whole file into the browser console after setting:
//   window.__kind = "taxdeed";      // "taxdeed" (realtaxdeed.com), "foreclosure" (realforeclose.com) or "sheriff" (OH/TX)
//   window.__fips = "12031";        // the county's FIPS code from data/registry.json
//   window.__monthsBack = 6;        // how many months of results to collect (upcoming sales are always collected)
// When it finishes, window.__ra holds {base, kind, fips, auctions} in the adapter's record shape and window.__done the
// counts. Save it with:  copy(JSON.stringify(window.__ra))  and paste into data/raw/realauction/<fips>-<kind>.json,
// then run  python3 collect_local.py --import  to fold it into data/counties/<fips>.json.
// The protocol mirrors sources/realauction.py (calendar CALBOX days, PREVIEW, LOAD areas W and C, FNC=UPDATE statuses).
window.__ra = null; window.__err = null; window.__done = null; window.__gen = (window.__gen || 0) + 1;
window.__p = (async () => {
  const KIND = window.__kind || "taxdeed", MONTHS_BACK = window.__monthsBack || 3, PAUSE = 150, GEN = window.__gen;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const TOK = [["@A", '<div class="'], ["@B", "</div>"], ["@C", 'class="'], ["@D", "<div>"], ["@E", "AUCTION"], ["@F", "</td><td"], ["@G", "</td></tr>"], ["@H", "<tr><td "], ["@I", "table"], ["@J", 'p_back="NextCheck='], ["@K", 'style="Display:none"'], ["@L", "/index.cfm?zaction=auction&zmethod=details&AID="]];
  const PK = ["Parcel ID", "Parcel Number", "Parcel Key", "Parcel No", "Parcel #", "Parcel", "Folio", "Folio Number", "Alternate Key", "Alt Key", "Tax ID", "Property ID", "Account #", "Account Number", "Strap", "PIN", "Schedule Number", "Schedule #", "Schedule No"];
  const get = async (u) => { const r = await fetch(u, { credentials: "include", headers: { "X-Requested-With": "XMLHttpRequest" } }); return r.text(); };
  const money = (s) => { if (s == null) return null; const v = parseFloat(String(s).replace(/[$,]/g, "")); return isNaN(v) ? null : v; };
  const strip = (h) => h.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
  const today = new Date().toISOString().slice(0, 10);
  // 1. the calendar: every day with scheduled or active items, two months ahead and MONTHS_BACK behind
  const days = {};
  const now = new Date();
  for (let back = -2; back <= MONTHS_BACK; back++) {
    const d = new Date(now.getFullYear(), now.getMonth() - back, 1);
    const txt = await get(`/index.cfm?zaction=USER&zmethod=CALENDAR&selCalDate=${String(d.getMonth() + 1).padStart(2, "0")}/01/${d.getFullYear()}`);
    const re = /<div[^>]*class=['"]CALBOX[^'"]*['"][^>]*dayid=['"](\d\d\/\d\d\/\d{4})['"][^>]*>([\s\S]*?)<\/div>/g;
    let m;
    while ((m = re.exec(txt))) {
      const body = m[2], lab = (body.match(/class=['"]CALTEXT['"][^>]*>([\s\S]*?)<br>/) || body.match(/<b>([\s\S]*?)<\/b>/) || [])[1];
      const act = +((body.match(/class=['"]CALACT['"]>\s*(\d+)/) || [])[1] || 0), sch = +((body.match(/class=['"]CALSCH['"]>\s*(\d+)/) || [])[1] || 0);
      if (act || sch) days[m[1]] = { date: m[1], label: lab ? strip(lab) : "Sale", active: act, scheduled: sch };
    }
    await sleep(PAUSE);
  }
  window.__days = Object.keys(days).length;
  // 2. the items of one page: label/value rows plus the first link in each value (the parcel number links to the appraiser)
  const parseItems = (h) => {
    const items = [];
    const re = /id="AITEM_(\d+)"([\s\S]*?)(?=<div[^>]*id="AITEM_|$)/g;
    let m;
    while ((m = re.exec(h))) {
      const rows = {}, links = {}, extra = [];
      const rr = /<t[dh][^>]*class="AD_LBL"[^>]*>([\s\S]*?)<\/t[dh]>\s*<td[^>]*class="AD_DTA[^"]*"[^>]*>([\s\S]*?)(?:<\/td>|$)/g;
      let r;
      while ((r = rr.exec(m[2]))) {
        const k = strip(r[1]).replace(/:$/, "").trim(), v = strip(r[2]), href = (r[2].match(/href="([^"]+)"/) || [])[1];
        if (!k) extra.push(v); else if (!(k in rows)) { rows[k] = v; if (href) links[k] = href; }
      }
      items.push([m[1], rows, extra, links]);
    }
    return items;
  };
  const auctions = [];
  window.__progress = 0;
  for (const day of Object.keys(days).sort((a, b) => (a.slice(6) + a.slice(0, 5)).localeCompare(b.slice(6) + b.slice(0, 5)))) {
    if (GEN !== window.__gen) return null;  // a newer run replaced this one
    const iso = `${day.slice(6)}-${day.slice(0, 2)}-${day.slice(3, 5)}`, upcoming = iso >= today;
    await get(`/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=${day}`); await sleep(PAUSE);
    const items = [], seenAll = new Set(), st = {};
    for (const area of ["W", "C"]) {
      const seen = new Set(); let dir = 0;
      for (let i = 0; i < 120; i++) {
        let j; try { j = JSON.parse((await get(`/index.cfm?zaction=AUCTION&Zmethod=UPDATE&FNC=LOAD&AREA=${area}&PageDir=${dir}&doR=1&tx=${Date.now()}&bypassPage=0&test=1`)).trim()); } catch (e) { break; }
        const rl = (j.rlist || "").split(",").filter(Boolean), fresh = rl.filter((x) => !seen.has(x));
        if (!fresh.length) break;
        rl.forEach((x) => seen.add(x));
        let h = j.retHTML || ""; for (const [a, b] of TOK) h = h.split(a).join(b);
        for (const it of parseItems(h)) if (!seenAll.has(it[0])) { seenAll.add(it[0]); items.push(it); }
        // 3. statuses: the portal only answers for the page the session is on, so ask right after each page load
        try { const sj = JSON.parse((await get(`/index.cfm?zaction=AUCTION&ZMETHOD=UPDATE&FNC=UPDATE&ref=${rl.join(",")},&tx=${Date.now()}`)).trim()); for (const it of (sj.ADATA || {}).AITEM || []) st[String(it.AID)] = it; } catch (e) { }
        dir = 1; await sleep(PAUSE);
      }
    }
    const parcels = items.map(([aid, rows, extra, links]) => {
      const s = st[aid], addr = rows["Property Address"] || rows["Address"] || null, city = extra[0] || null;
      let status = upcoming ? "Listed" : "Not published", wb = null, buyer = null, soldDate = null;
      if (s) {
        if ((s.A || "").toLowerCase().startsWith("auction sold")) { status = "Sold"; wb = money(s.D) || money(s.P); buyer = (s.ST || "").trim() || null; soldDate = s.B || null; }
        else if (["Withdrawn", "Canceled", "Cancelled", "Rescheduled", "Redeemed", "Bankruptcy"].includes(s.B)) status = s.B;
      }
      const o = { parcel: PK.map((k) => rows[k]).find(Boolean) || null,
        caseNo: rows["Case #"] || rows["Case Number"] || null, certificate: rows["Certificate #"] || null,
        address: addr, fullAddress: [addr, city].filter(Boolean).join(", ") || null,
        area: city ? city.split(",")[0].trim().replace(/\b\w+/g, (w) => w[0] + w.slice(1).toLowerCase()) : null,
        zip: city ? (city.match(/(\d{5})(?:-?\d{4})?\s*$/) || [])[1] : null,
        minBid: money(rows["Opening Bid"]), value: money(rows["Assessed Value"] || rows["Appraised Value"]), judgment: money(rows["Final Judgment Amount"]),
        type: rows["Auction Type"] || null, owner: rows["Owner"] || rows["Defendant"] || null, plaintiff: rows["Plaintiff"] || null,
        parcelInfo: PK.map((k) => links[k]).find(Boolean) || null,
        winningBid: wb, buyer, status, soldDate, link: `${location.origin}/index.cfm?zaction=auction&zmethod=details&AID=${aid}` };
      Object.keys(o).forEach((k) => { if (o[k] == null || o[k] === "") delete o[k]; });
      return o;
    });
    if (parcels.length) auctions.push({ id: `ra-${KIND}-${window.__fips}-${iso}`, date: iso, kind: upcoming ? "list" : "results", label: `${days[day].label} ${iso}`, source: `${location.origin}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=${day}`, saleKind: KIND, status: upcoming ? "upcoming" : "past", parcels });
    window.__progress++;
  }
  if (GEN !== window.__gen) return null;  // a newer run replaced this one
  window.__ra = { base: location.origin, kind: KIND, fips: window.__fips, collected: new Date().toISOString(), auctions };
  return { days: Object.keys(days).length, auctions: auctions.length, parcels: auctions.reduce((s, a) => s + a.parcels.length, 0), bytes: JSON.stringify(auctions).length };
})().then((r) => { if (r) window.__done = r; }).catch((e) => { window.__err = String(e && e.stack || e); });

// Helpers for moving the result out of the tab in verified pieces: __pack() gzips window.__ra into window.__gz
// (base64), __chunk(i) returns piece i with a CRC32 so a copy can be checked. tools/decode_dumps.py reassembles them.
window.__pack = async () => {
  const s = JSON.stringify(window.__ra); const cs = new CompressionStream("gzip"); const w = cs.writable.getWriter(); w.write(new TextEncoder().encode(s)); w.close();
  const u = new Uint8Array(await new Response(cs.readable).arrayBuffer()); let b = ""; for (let i = 0; i < u.length; i += 0x8000) b += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  window.__gz = btoa(b); return { raw: s.length, b64: window.__gz.length, chunks: Math.ceil(window.__gz.length / 6000) };
};
window.__crc = (str) => { let c, crc = 0xFFFFFFFF; for (let i = 0; i < str.length; i++) { c = (crc ^ str.charCodeAt(i)) & 0xFF; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xEDB88320 : c >>> 1; crc = (crc >>> 8) ^ c; } return ((crc ^ 0xFFFFFFFF) >>> 0).toString(16); };
window.__chunk = (i, size = 6000) => { const d = window.__gz.slice(i * size, (i + 1) * size); return { i, n: Math.ceil(window.__gz.length / size), crc: window.__crc(d), d }; };
