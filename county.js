/* County page: every capability of the Clark County and Metro Atlanta trackers, over the normalized county files. */
(function () {
  "use strict";
  const T = window.TS;
  const { $, esc, money, money2, short, int, pct, sum, avg, median, mode, fmtDate, TODAY, NOWYEAR, chart, Drill, makeTable, downloadCsv, downloadText, gmapUrl, svUrl, photos, addrText, copyBtn, TYPES, TIERS, tierOf, scoreHtml, prepCounty, WATCH, ics, redemptionTable } = T;
  const KIND = { list: "Sale list", results: "Results", excess: "Excess funds list", taxdeed: "Tax deed sale", foreclosure: "Foreclosure sale", sheriff: "Sheriff sale" };
  const KIND_HELP = { results: "Full results published by the county (sold and not sold)", excess: "From the excess funds list: only parcels that sold above what was owed", list: "Parcels advertised for the sale; outcomes not published", taxdeed: "Clerk tax deed auction", foreclosure: "Clerk foreclosure (judicial) sale", sheriff: "Sheriff sale" };
  const sysPill = (k, label) => `<span class="pill ${k}">${esc(label)}</span>`;

  let C = null, D = null, PREP = null, SEL = null;   // county, data file, prepared data, current selection
  const G = { sort: "score", dir: -1, hidden: [], order: null, pivot: "", pSort: "n", pDir: -1, filter: null, rows: [], area: null };
  const LS = "ts-grid-v1";
  const GAL = { page: 0, per: 12, filter: "all", items: [] };
  const maps = {};

  // ---------- page ----------
  async function show(c, state, index, cache, helpers) {
    C = c; const st = state;
    $("cName").textContent = `${c.label}, ${st.name}`;
    $("cSub").innerHTML = `${sysPill(st.system, st.systemLabel)} &nbsp;<a href="#${c.state.toLowerCase()}">All of ${esc(st.name)}</a> &middot; FIPS ${c.fips}${c.pop ? ` &middot; population ${int(c.pop)}` : ""}${c.landSqmi ? ` &middot; ${int(Math.round(c.landSqmi))} sq mi` : ""}`;
    const nextText = helpers.nextSaleText(c), nextKind = helpers.nextSaleKind(c);
    const trim = (u) => esc(u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "").slice(0, 60));
    const info = [
      ["Who holds the sale", esc(c.run || st.conducted_by)],
      ["Next sale", nextText ? `${esc(nextText)} <span class="pill ${c.nextSaleKind}">${nextKind}</span>` : esc(st.sale_timing)],
      ["Schedule", esc(c.schedule || st.sale_timing)],
      ["Tax sale page", c.taxsale ? `<a href="${esc(c.taxsale)}" target="_blank" rel="noopener">${trim(c.taxsale)}</a>` : `Not on file. <a href="${T.searchUrl(`${c.label} ${st.name} tax sale`)}" target="_blank" rel="noopener">Search for it</a>`],
      ["Official site", c.site ? `<a href="${esc(c.site)}" target="_blank" rel="noopener">${trim(c.site)}</a>` : `<a href="${T.searchUrl(`${c.label} ${st.name} official website`)}" target="_blank" rel="noopener">Search for it</a>`],
      ["Parcel lookup", c.parcelLookup ? `<a href="${esc(c.parcelLookup)}" target="_blank" rel="noopener">County parcel records</a>` : c.assessor ? `<a href="${esc(c.assessor)}" target="_blank" rel="noopener">${trim(c.assessor)}</a>` : `<a href="${T.searchUrl(`${c.label} ${st.name} property search parcel assessor`)}" target="_blank" rel="noopener">Search the assessor</a>`],
      ["Sheriff and foreclosure sales", `${c.sheriffSale ? `<a href="${esc(c.sheriffSale)}" target="_blank" rel="noopener">${trim(c.sheriffSale)}</a>` : `<a href="${T.searchUrl(`${c.label} ${st.name} sheriff sale`)}" target="_blank" rel="noopener">Search sheriff sales</a>`} &middot; ${esc(st.foreclosure === "judicial" ? "judicial foreclosure state" : st.foreclosure === "nonjudicial" ? "nonjudicial foreclosure state" : "both judicial and nonjudicial foreclosure")}`],
    ];
    if (c.treasurer) info.push(["Treasurer / tax office", `<a href="${esc(c.treasurer)}" target="_blank" rel="noopener">${trim(c.treasurer)}</a>`]);
    if (c.excess) info.push(["Excess funds", `<a href="${esc(c.excess)}" target="_blank" rel="noopener">Excess funds page</a>`]);
    if (c.platform) info.push(["Platform", esc(c.platform)]);
    if (c.data) info.push(["Data source", `<a href="#" id="cSrcLink" target="_blank" rel="noopener">${esc((index?.sources?.[c.data.source]?.label) || c.data.source)}</a> &middot; checked ${esc(fmtDate((c.data.lastChecked || "").slice(0, 10)))} &middot; next refresh on the 1st`]);
    if (c.taxsaleKind === "crawl") info.push(["About this link", "The tax sale page was found automatically on the county's website; check it is the current one."]);
    $("cInfo").innerHTML = info.map(([k, v]) => `<div><b>${k}</b>${v}</div>`).join("");
    $("cNote").hidden = !c.note; $("cNote").innerHTML = c.note ? `<b>Note:</b> ${esc(c.note)}` : "";
    $("cRulesTitle").textContent = `${st.name} Rules`;
    $("cRules").innerHTML = helpers.rulesHtml(st, true);
    $("cRedeem").innerHTML = `<h3>If The Owner Redeems</h3>${redemptionTable(st, 10000)}`;
    $("cActions").innerHTML = `<button type="button" id="cIcs">Add sale dates to calendar</button><button type="button" id="cShare">Copy link to this county</button>${c.data ? `<button type="button" id="cAllCsv">Download every parcel on file</button>` : ""}`;
    $("cIcs").onclick = () => {
      const evs = [];
      if (c.nextSale) evs.push({ date: c.nextSale, title: `${c.label}, ${c.state}: ${c.nextSaleKind === "posted" ? "tax sale" : "statutory sale date"}`, desc: `${c.schedule || st.sale_timing}. ${c.taxsale || ""}`, url: location.href, uid: `${c.fips}-${c.nextSale}` });
      for (const a of (D && D.auctions) || []) if (a.date && a.date >= TODAY) evs.push({ date: a.date, title: `${c.label}, ${c.state}: ${a.label}`, desc: `${a.parcels ? a.parcels.length + " parcels. " : ""}${a.source || ""}`, url: location.href, uid: a.id });
      if (!evs.length) { alert("No upcoming sale date is on file for this county."); return; }
      downloadText(`${c.state.toLowerCase()}-${T.slug(c.name)}-sales.ics`, ics(evs, `${c.label}, ${c.state} tax sales`), "text/calendar");
    };
    $("cShare").onclick = (e) => { navigator.clipboard?.writeText(location.href).then(() => { e.target.textContent = "Link copied"; setTimeout(() => { e.target.textContent = "Copy link to this county"; }, 1500); }); };

    $("cPickerWrap").hidden = true; $("cBody").hidden = true; $("cEmpty").hidden = true;
    if (!c.data) {
      $("cEmpty").hidden = false;
      $("cEmpty").innerHTML = `<div class="emptyinfo"><h3>No parcel-level data on file yet</h3><p class="muted">This tracker has the rules, schedule and links for ${esc(c.label)}, but no source that publishes its sale lists in a form that can be read automatically. Use the links above to reach the county's own list.</p><ul class="small muted"><li>${esc(st.summary)}</li><li>${esc(st.sheriff_sales)}</li><li>Know a page that lists this county's sales as a spreadsheet, PDF or JSON? <a href="https://github.com/ShamarRobinson/us-tax-sale-dashboard/issues/new?template=add-county-source.yml" target="_blank" rel="noopener">Suggest it on GitHub</a> and it can be added as a source.</li></ul></div>`;
      return;
    }
    D = cache[c.fips];
    if (!D) {
      try { D = await fetch(`data/counties/${c.fips}.json`).then((r) => r.json()); cache[c.fips] = D; }
      catch (e) { $("cEmpty").hidden = false; $("cEmpty").innerHTML = `<p class="muted">The county data file could not be loaded.</p>`; return; }
    }
    const srcLink = $("cSrcLink"); if (srcLink && D.sourceUrl) srcLink.href = D.sourceUrl;
    if (D.info && D.info.auction) {
      const a = D.info.auction;
      const extra = [["Venue", a.venue], ["Address", a.address], ["Time", a.time], ["Registration", a.registration], ["Payment", a.payment], ["Phone", a.phone], ["Email", a.email], ["Office", a.office]].filter((x) => x[1]);
      if (extra.length) $("cInfo").insertAdjacentHTML("beforeend", extra.map(([k, v]) => `<div class="${String(v).length > 120 ? "wide" : ""}"><b>${k}</b>${esc(v)}</div>`).join(""));
    }
    PREP = prepCounty(D, c);
    if (!PREP.aucs.length) { $("cEmpty").hidden = false; $("cEmpty").innerHTML = `<p class="muted">Sales are on file but none has parcels listed.</p>`; return; }
    $("cPickerWrap").hidden = false; $("cBody").hidden = false;
    const sel = $("cAuction");
    sel.innerHTML = `<option value="all">All sales on file (${PREP.aucs.length}, ${int(PREP.all.length)} parcels)</option>` + PREP.aucs.map((a, i) => `<option value="${i}">${esc(a.label)} (${a.parcels.length} parcels${a.status === "upcoming" ? ", upcoming" : ""})</option>`).join("");
    const params = new URLSearchParams((location.hash.split("?")[1] || ""));
    const wanted = params.get("auction");
    const first = wanted != null && PREP.aucs.some((a) => a.id === wanted) ? PREP.aucs.findIndex((a) => a.id === wanted) : PREP.aucs.findIndex((a) => a.status === "upcoming" && a.parcels.length >= 5);
    sel.value = first >= 0 ? String(first) : (PREP.aucs.length > 1 ? "all" : "0");
    sel.onchange = () => { G.filter = null; G.area = null; draw(); };
    $("cAllCsv").onclick = () => downloadCsv(`${c.state.toLowerCase()}-${T.slug(c.name)}-all-parcels.csv`, csvCols(), PREP.all);
    draw();
    drawHistory();
    const pid = params.get("parcel");
    if (pid) { const p = PREP.all.find((x) => x.key === pid.toUpperCase()); if (p) setTimeout(() => showDetail(p), 300); }
  }

  const selected = () => { const v = $("cAuction").value; return v === "all" ? { label: "all sales on file", parcels: PREP.all, all: true } : { label: PREP.aucs[+v].label, parcels: PREP.aucs[+v].parcels, auction: PREP.aucs[+v] }; };

  function draw() {
    SEL = selected();
    const ps = SEL.parcels;
    renderKpis(ps); renderTiers(ps); renderTypes(ps); renderBids(ps); renderAreasAndMap(ps); renderTenure(ps);
    G.rows = ps; G.filter = null; $("fSearch").value = ""; drawGrid();
    GAL.items = ps; GAL.page = 0; gallery();
  }

  // ---------- KPIs ----------
  function renderKpis(ps) {
    const bids = ps.filter((p) => p.winningBid > 0).map((p) => p.winningBid);
    const sold = ps.filter((p) => p.sold), wars = ps.filter((p) => p.war), listed = ps.filter((p) => p.status === "Listed");
    const lo = ps.filter((p) => p.winningBid > 0).sort((a, b) => a.winningBid - b.winningBid)[0], hi = ps.filter((p) => p.winningBid > 0).sort((a, b) => b.winningBid - a.winningBid)[0];
    let mv = null, mnote = "";
    if (bids.length) { let m = mode(bids); if (m && m[1] > 1) { mv = m[0]; mnote = `${m[1]} parcels sold for exactly this`; } else { m = mode(bids.map((v) => Math.round(v / 500) * 500)); mv = m ? m[0] : null; mnote = m && m[1] > 1 ? `about this (nearest $500): ${m[1]} parcels` : "every bid was different"; } }
    const who = (p) => p ? `<a href="#" class="kpilink" data-id="${esc(p.id)}">${esc(p.parcel || p.lot || "")}</a>${p.area && p.area !== "Not stated" ? ", " + esc(p.area) : ""}` : "";
    const k = (label, value, note, hero) => `<div class="kpi${hero ? " hero" : ""}"><div class="label">${label}</div><div class="value">${value}</div><div class="note">${note || ""}</div></div>`;
    const excess = sum(ps.map((p) => p.excess));
    $("cKpis").innerHTML = [
      k("Parcels", int(ps.length), SEL.all ? `across ${PREP.aucs.length} sales` : esc(SEL.label), true),
      k("Sold", int(sold.length), ps.length ? `${Math.round(100 * sold.length / ps.length)}% of parcels · ${int(listed.length)} listed, not yet sold` : ""),
      k("Average winning bid", bids.length ? money(avg(bids)) : "n/a", bids.length ? `mean of ${int(bids.length)} published prices` : "no prices published"),
      k("Median winning bid", bids.length ? money(median(bids)) : "n/a", "half sold above, half below"),
      k("Lowest winning bid", lo ? money(lo.winningBid) : "n/a", who(lo)),
      k("Highest winning bid", hi ? money(hi.winningBid) : "n/a", who(hi)),
      k("Most frequent bid", mv != null ? money(mv) : "n/a", esc(mnote)),
      k("Typical multiple", bids.length ? (median(ps.map((p) => p.multiple)) || 0).toFixed(2) + "x" : "n/a", "winning bid over amount owed"),
      k("Bidding wars", sold.length ? `${int(wars.length)} of ${int(sold.length)}` : "n/a", sold.length ? `${pct(wars.length / sold.length)} sold above the amount owed` : ""),
      k("Total bids", bids.length ? short(sum(bids)) : "n/a", "all published winning bids"),
      k("Excess funds", excess ? money(excess) : "n/a", "sold above what was owed, claimable by former owners"),
    ].join("");
    $("cKpis").querySelectorAll(".kpilink").forEach((a) => a.onclick = (e) => { e.preventDefault(); const p = ps.find((x) => x.id === a.dataset.id); if (p) showDetail(p); });
  }

  // ---------- cost tiers ----------
  function renderTiers(ps) {
    const rows = TIERS.map((t) => { const g = ps.filter((p) => p.tier === t[2]); const s = g.filter((p) => p.winningBid); return { name: t[2], n: g.length, priced: s.length, avg: avg(s.map((p) => p.winningBid)), mult: median(s.map((p) => p.multiple)), g }; }).filter((r) => r.n);
    $("secTiers").hidden = !rows.length; if (!rows.length) return;
    new Drill("cTiers", "cTiersCrumb", { name: "All tiers", title: "Parcels by amount owed", labels: rows.map((r) => r.name), values: rows.map((r) => r.n), series: "Parcels", hint: (i) => rows[i].avg ? `· avg winning bid ${money(rows[i].avg)}` : "",
      click: (i) => { const g = rows[i].g.slice().sort((a, b) => (b.winningBid || b.minBid || 0) - (a.winningBid || a.minBid || 0)).slice(0, 40); return { name: rows[i].name, title: `${rows[i].name}: amount owed and winning bid per parcel${g.length === 40 ? " (top 40)" : ""}`, labels: g.map((p) => p.parcel || p.lot || ""), values: g.map((p) => p.minBid || 0), values2: g.map((p) => p.winningBid || 0), series: "Owed", series2: "Winning bid", horizontal: true, money: true, hint: (j) => g[j].address ? `· ${g[j].address}` : "", click: (j) => { showDetail(g[j]); } }; } });
    $("tTiers").innerHTML = `<thead><tr><th>Amount owed</th><th class="num">Parcels</th><th class="num">With price</th><th class="num">Avg winning bid</th><th class="num">Median multiple</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${r.name}</td><td class="num">${int(r.n)}</td><td class="num">${int(r.priced)}</td><td class="num">${r.avg ? money(r.avg) : ""}</td><td class="num">${r.mult ? r.mult.toFixed(2) + "x" : ""}</td></tr>`).join("")}</tbody>`;
    const cheap = rows.filter((r) => r.n && ["Under $1k", "$1k to $2.5k"].includes(r.name)), top = rows.filter((r) => r.avg).sort((a, b) => b.mult - a.mult)[0];
    $("kTiers").innerHTML = `<b>${pct(sum(cheap.map((r) => r.n)) / ps.length)}</b> of parcels owed under $2,500.${top ? ` The highest competition is in the <b>${esc(top.name)}</b> tier, where parcels sold for a median <b>${top.mult.toFixed(1)}x</b> the amount owed.` : ""}`;
  }

  // ---------- parcel types ----------
  function renderTypes(ps) {
    const rows = TYPES.map((t) => { const g = ps.filter((p) => p.cat === t); const s = g.filter((p) => p.winningBid); return { name: t, n: g.length, sold: g.filter((p) => p.sold).length, avg: avg(s.map((p) => p.winningBid)), mult: median(s.map((p) => p.multiple)), war: s.length ? s.filter((p) => p.war).length / s.length : null, g }; }).filter((r) => r.n);
    const known = rows.filter((r) => r.name !== "Other or unknown");
    $("secTypes").hidden = !known.length; if (!known.length) return;
    new Drill("cTypes", "cTypesCrumb", { name: "All types", title: "Parcels by property type", labels: rows.map((r) => r.name), values: rows.map((r) => r.n), series: "Parcels", colors: "#159c6c", hint: (i) => rows[i].avg ? `· avg winning bid ${money(rows[i].avg)}` : "",
      click: (i) => { const g = rows[i].g.slice().sort((a, b) => b.score - a.score).slice(0, 40); return { name: rows[i].name, title: `${rows[i].name}: deal score by parcel (top 40)`, labels: g.map((p) => p.parcel || p.lot || ""), values: g.map((p) => p.score), colors: g.map((p) => T.RCOLOR[p.rating]), horizontal: true, series: "Score", hint: (j) => `· owed ${money(g[j].minBid)}${g[j].winningBid ? " · sold " + money(g[j].winningBid) : ""}`, click: (j) => { showDetail(g[j]); } }; } });
    $("tTypes").innerHTML = `<thead><tr><th>Type</th><th class="num">Parcels</th><th class="num">Sold</th><th class="num">Avg winning bid</th><th class="num">Median multiple</th><th class="num">Bidding wars</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${int(r.n)}</td><td class="num">${int(r.sold)}</td><td class="num">${r.avg ? money(r.avg) : ""}</td><td class="num">${r.mult ? r.mult.toFixed(1) + "x" : ""}</td><td class="num">${pct(r.war)}</td></tr>`).join("")}</tbody>`;
    const big = known.sort((a, b) => b.n - a.n)[0], pricey = rows.filter((r) => r.avg).sort((a, b) => b.avg - a.avg)[0];
    $("kTypes").innerHTML = `Most parcels are <b>${esc(big.name.toLowerCase())}</b> (${int(big.n)}, ${pct(big.n / ps.length)}).${pricey ? ` <b>${esc(pricey.name)}</b> parcels brought the highest average winning bid at <b>${money(pricey.avg)}</b>.` : ""} Types come from county records or the auction catalog; "Other or unknown" means the source published no type.`;
  }

  // ---------- bidding ----------
  function renderBids(ps) {
    const s = ps.filter((p) => p.multiple), buyers = ps.filter((p) => p.buyer);
    $("secBids").hidden = !s.length && !buyers.length; if ($("secBids").hidden) return;
    const bins = [["1.0x (at minimum)", (m) => m <= 1.005], ["1x to 2x", (m) => m > 1.005 && m < 2], ["2x to 5x", (m) => m >= 2 && m < 5], ["5x to 10x", (m) => m >= 5 && m < 10], ["10x to 25x", (m) => m >= 10 && m < 25], ["25x and up", (m) => m >= 25]];
    if (s.length) new Drill("cMult", "cMultCrumb", { name: "All multiples", title: "How far above the amount owed parcels sold", labels: bins.map((b) => b[0]), values: bins.map((b) => s.filter((p) => b[1](p.multiple)).length), series: "Parcels", colors: "#eb6834",
      click: (i) => { const g = s.filter((p) => bins[i][1](p.multiple)).sort((a, b) => b.multiple - a.multiple).slice(0, 40); return { name: bins[i][0], title: `${bins[i][0]}: winning bid per parcel`, labels: g.map((p) => p.parcel || p.lot || ""), values: g.map((p) => p.winningBid), series: "Winning bid", money: true, horizontal: true, colors: "#eb6834", hint: (j) => `· ${g[j].multiple.toFixed(1)}x owed`, click: (j) => { showDetail(g[j]); } }; } });
    const w = s.filter((p) => p.war), prem = sum(w.map((p) => p.winningBid - p.minBid));
    const stat = (v, l) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`;
    const byType = Object.entries(w.reduce((o, p) => { o[p.cat] = (o[p.cat] || 0) + 1; return o; }, {})).sort((a, b) => b[1] - a[1])[0];
    $("cWar").innerHTML = s.length ? [stat(`${w.length} of ${s.length}`, "sold above the amount owed"), stat(median(s.map((p) => p.multiple)).toFixed(1) + "x", "median multiple of amount owed"), stat(short(prem), "paid above amounts owed"), stat(byType ? esc(byType[0]) : "n/a", byType ? `most common type in bidding wars (${byType[1]})` : "")].join("") : `<p class="muted small">Prices are not published for this selection.</p>`;
    const top = w.slice().sort((a, b) => b.multiple - a.multiple).slice(0, 8);
    $("tWars").innerHTML = top.length ? `<thead><tr><th>Parcel</th><th>Type &middot; Area</th><th class="num">Owed</th><th class="num">Won</th><th class="num">Multiple</th></tr></thead><tbody>${top.map((p) => `<tr class="row" data-id="${esc(p.id)}"><td><b>${esc(p.parcel || p.lot || "")}</b></td><td class="wrap">${esc(p.cat)}<br><span class="muted small">${esc(p.area)}</span></td><td class="num">${money(p.minBid)}</td><td class="num">${money(p.winningBid)}</td><td class="num"><b>${p.multiple.toFixed(1)}x</b></td></tr>`).join("")}</tbody>` : "";
    $("tWars").querySelectorAll("tr.row").forEach((tr) => tr.onclick = () => { const p = ps.find((x) => x.id === tr.dataset.id); if (p) showDetail(p); });
    const bc = {}; buyers.forEach((p) => { const b = p.buyer.toUpperCase().trim(); (bc[b] = bc[b] || []).push(p); });
    const tb = Object.entries(bc).sort((x, y) => y[1].length - x[1].length || sum(y[1].map((p) => p.winningBid)) - sum(x[1].map((p) => p.winningBid))).slice(0, 10);
    $("buyersTitle").hidden = !tb.length;
    $("tBuyers").innerHTML = tb.length ? `<thead><tr><th>Buyer</th><th class="num">Parcels</th><th class="num">Total spent</th><th class="num">Median multiple</th></tr></thead><tbody>${tb.map(([b, g]) => `<tr class="row" data-b="${esc(b)}"><td>${esc(b)}</td><td class="num">${g.length}</td><td class="num">${money(sum(g.map((p) => p.winningBid)))}</td><td class="num">${median(g.map((p) => p.multiple)) ? median(g.map((p) => p.multiple)).toFixed(1) + "x" : ""}</td></tr>`).join("")}</tbody>` : "";
    $("tBuyers").querySelectorAll("tr.row").forEach((tr) => tr.onclick = () => { G.filter = { label: "Buyer", value: tr.dataset.b, fn: (p) => (p.buyer || "").toUpperCase().trim() === tr.dataset.b }; drawGrid(); $("parcels").scrollIntoView({ behavior: "smooth" }); });
  }

  // ---------- location: map and areas ----------
  function renderAreasAndMap(ps) {
    const geo = ps.filter((p) => p.lat && p.lon);
    const areas = {}; ps.forEach((p) => (areas[p.area] = areas[p.area] || []).push(p));
    const rows = Object.entries(areas).map(([name, g]) => { const s = g.filter((p) => p.winningBid); return { name, n: g.length, avg: avg(s.map((p) => p.winningBid)), mult: median(s.map((p) => p.multiple)), war: s.length ? s.filter((p) => p.war).length / s.length : null, score: avg(g.map((p) => p.score)) }; }).sort((a, b) => b.n - a.n);
    $("secMap").hidden = !geo.length && rows.length < 2; if ($("secMap").hidden) return;
    drawMap(geo, null);
    $("tAreas").innerHTML = `<thead><tr><th>Area</th><th class="num">Parcels</th><th class="num">Avg winning bid</th><th class="num">Median multiple</th><th class="num">Bidding wars</th><th class="num">Avg score</th></tr></thead><tbody>${rows.map((r) => `<tr class="arearow" tabindex="0" data-area="${esc(r.name)}" title="Click to highlight on the map and in the table"><td><span class="areaname">${esc(r.name)}</span></td><td class="num">${int(r.n)}</td><td class="num"><b>${r.avg ? money(r.avg) : ""}</b></td><td class="num">${r.mult ? r.mult.toFixed(1) + "x" : ""}</td><td class="num">${pct(r.war)}</td><td class="num">${r.score != null ? Math.round(r.score) : ""}</td></tr>`).join("")}</tbody>`;
    $("tAreas").querySelectorAll("tr.arearow").forEach((tr) => { const go = () => highlightArea(G.area === tr.dataset.area ? null : tr.dataset.area, geo); tr.onclick = go; tr.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }; });
    $("areaClear").onclick = () => highlightArea(null, geo);
    const withAvg = rows.filter((r) => r.avg && r.n >= 2).sort((a, b) => b.avg - a.avg);
    $("kAreas").innerHTML = withAvg.length ? `Highest average winning bid among areas with 2+ priced parcels: <b>${esc(withAvg[0].name)}</b> at <b>${money(withAvg[0].avg)}</b>${withAvg.length > 1 ? `; lowest: <b>${esc(withAvg[withAvg.length - 1].name)}</b> at ${money(withAvg[withAvg.length - 1].avg)}` : ""}. ${geo.length ? `${int(geo.length)} of ${int(ps.length)} parcels have coordinates.` : ""}` : (geo.length ? `${int(geo.length)} of ${int(ps.length)} parcels have coordinates.` : "");
    $("mapNote").textContent = geo.length ? "Orange dots sold; blue dots listed or unsold; dot size follows the winning bid or the amount owed. Click a dot for details." : "No coordinates are published for this selection.";
  }
  function drawMap(geo, area) {
    if (maps.cMap) maps.cMap.remove();
    const m = L.map("cMap", { scrollWheelZoom: false }); maps.cMap = m;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(m);
    if (!geo.length) { m.setView([C.lat, C.lon], 9); return; }
    const maxv = Math.max(...geo.map((p) => p.winningBid || p.minBid || 0), 1);
    const group = L.featureGroup(), sel = L.featureGroup();
    for (const p of geo) {
      const v = p.winningBid || p.minBid || 0, r = 4 + 10 * Math.sqrt(v / maxv), dim = area && p.area !== area;
      const mk = L.circleMarker([p.lat, p.lon], { radius: r, color: "#000", weight: dim ? 0.3 : 1, fillColor: p.sold ? "#eb6834" : "#2a78d6", fillOpacity: dim ? 0.15 : 0.8 })
        .bindTooltip(`<b>${esc(p.parcel || p.lot || "")}</b><br>${esc(addrText(p))}<br>${p.minBid != null ? "Owed " + money(p.minBid) : ""}${p.winningBid ? " · Sold " + money(p.winningBid) : ""}<br>Score ${p.score} ${p.rating}`).on("click", () => showDetail(p));
      mk.addTo(group); if (area && p.area === area) mk.addTo(sel);
    }
    group.addTo(m);
    m.fitBounds((area && sel.getLayers().length ? sel : group).getBounds().pad(0.15));
  }
  function highlightArea(name, geo) {
    G.area = name;
    $("tAreas").querySelectorAll("tr.arearow").forEach((tr) => tr.classList.toggle("sel", tr.dataset.area === name));
    $("areaNote").innerHTML = name ? `Showing <b>${esc(name)}</b>` : "";
    $("areaClear").hidden = !name;
    drawMap(geo, name);
    G.filter = name ? { label: "Area", value: name, fn: (p) => p.area === name } : null;
    drawGrid();
  }

  // ---------- time in default and unclaimed money ----------
  function renderTenure(ps) {
    const d = ps.map((p) => p.defaultYrs ?? p.yearsUnpaid).filter((x) => x != null && !isNaN(x));
    const ten = ps.map((p) => p.tenure).filter((x) => x != null && x >= 0);
    const withExcess = ps.filter((p) => p.excess > 0);
    $("secTenure").hidden = !d.length && !ten.length && !withExcess.length; if ($("secTenure").hidden) return;
    const B = [[0, 3, "Under 3 yrs"], [3, 4, "3 to 4 yrs"], [4, 5, "4 to 5 yrs"], [5, 7, "5 to 7 yrs"], [7, 10, "7 to 10 yrs"], [10, 999, "10+ yrs"]];
    const TT = [[0, 5, "Under 5 yrs"], [5, 10, "5 to 10 yrs"], [10, 20, "10 to 20 yrs"], [20, 30, "20 to 30 yrs"], [30, 999, "30+ yrs"]];
    const useD = d.length >= 3 || !ten.length, bins = useD ? B : TT, vals = useD ? d : ten;
    $("tenureTitle").textContent = useD ? "Years taxes went unpaid before the sale" : "How long the former owner held the parcel before losing it";
    $("cTenure").parentElement.hidden = !vals.length;
    if (vals.length) chart("cTenure", { type: "bar", data: { labels: bins.map((b) => b[2]), datasets: [{ label: "Parcels", data: bins.map((b) => vals.filter((x) => x >= b[0] && x < b[1]).length), backgroundColor: "#8e5ad6", borderRadius: 4, maxBarThickness: 34 }] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { color: "#ebe9e4" }, ticks: { precision: 0 } }, x: { grid: { display: false } } } } });
    const byA = {}; withExcess.forEach((p) => (byA[p._date] = byA[p._date] || []).push(p));
    const rows = Object.entries(byA).sort((a, b) => b[0].localeCompare(a[0])).slice(0, 8).map(([date, g]) => { const since = Math.floor((Date.now() - new Date(date + "T12:00:00")) / 864e5); return `<tr><td>${fmtDate(date)}</td><td class="num">${int(g.length)}</td><td class="num">${money(sum(g.map((p) => p.excess)))}</td><td class="num">${since > 0 ? int(since) + " days" : "upcoming"}</td></tr>`; });
    $("tClaims").innerHTML = rows.length ? `<thead><tr><th>Sale</th><th class="num">Parcels with excess</th><th class="num">Excess funds</th><th class="num">Since the sale</th></tr></thead><tbody>${rows.join("")}</tbody>` : `<tbody><tr><td class="muted">No excess funds are recorded for this selection.</td></tr></tbody>`;
    const longest = ps.filter((p) => (p.defaultYrs ?? p.yearsUnpaid) != null).sort((a, b) => (b.defaultYrs ?? b.yearsUnpaid) - (a.defaultYrs ?? a.yearsUnpaid))[0];
    $("kTenure").innerHTML = [
      d.length ? `For the ${int(d.length)} parcels with a known delinquency, taxes had gone unpaid for a median of <b>${median(d).toFixed(1)} years</b> by the sale, including ${pct(d.filter((x) => x >= 5).length / d.length)} at 5+ years.${longest ? ` Longest: <a href="#" class="kpilink" data-id="${esc(longest.id)}">${esc(longest.parcel || longest.lot)}</a> at about <b>${Math.round(longest.defaultYrs ?? longest.yearsUnpaid)} years</b>.` : ""}` : "",
      ten.length ? `Former owners had held the median parcel for <b>${median(ten).toFixed(0)} years</b> before losing it, and ${pct(ten.filter((x) => x >= 20).length / ten.length)} for 20+ years, which often points to inherited or forgotten land.` : "",
      withExcess.length ? `<b>${money(sum(withExcess.map((p) => p.excess)))}</b> in excess funds sits with the county from ${int(withExcess.length)} parcels that sold above what was owed; former owners and lienholders can claim it${C.excess ? ` (<a href="${esc(C.excess)}" target="_blank" rel="noopener">county excess funds page</a>)` : ""}.` : "",
    ].filter(Boolean).join(" ");
    $("kTenure").querySelectorAll(".kpilink").forEach((a) => a.onclick = (e) => { e.preventDefault(); const p = ps.find((x) => x.id === a.dataset.id); if (p) showDetail(p); });
  }

  // ---------- the grid: columns, chooser, drag reorder, pivots ----------
  const ext = (u, t) => u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>` : "";
  const gmap = (p) => gmapUrl(p, C.label, C.stateName || C.state);
  const COLS = {
    parcel: { label: "Parcel", val: (p) => p.parcel || p.lot || p.caseNo || "", html: (p) => `<b>${esc(p.parcel || p.lot || p.caseNo || "")}</b>${p.caseNo && p.parcel ? `<br><span class="muted small">${esc(p.caseNo)}</span>` : ""}` },
    watch: { label: "Watch", nosort: 1, val: (p) => WATCH.has(p.id) ? "Yes" : "", html: (p) => WATCH.btn(p.id, watchInfo(p)) },
    date: { label: "Sale Date", val: (p) => p._date, html: (p) => `${fmtDate(p._date)}${p._upcoming ? ' <span class="pill posted">Upcoming</span>' : ""}` },
    score: { label: "Deal Score", num: 1, val: (p) => p.score, html: (p) => scoreHtml(p, PREP.ctx) },
    kind: { label: "Source Type", val: (p) => KIND[p._kind] || p._kind, html: (p) => `<span class="kind ${esc(p._kind)}" title="${esc(KIND_HELP[p._kind] || "")}">${esc(KIND[p._kind] || p._kind)}</span>` },
    status: { label: "Status", val: (p) => p.status, html: (p) => `<span class="pill ${p.sold ? "ok" : ""}">${esc(p.status)}</span>` },
    type: { label: "Property Type", val: (p) => p.cat, html: (p) => `${esc(p.cat)}${p.type && p.type !== p.cat ? `<br><span class="muted small">${esc(p.typeDetail || p.type)}</span>` : ""}`, wrap: 1 },
    area: { label: "Area", val: (p) => p.area, html: (p) => esc(p.area) },
    address: { label: "Address", val: (p) => addrText(p), html: (p) => { const t = addrText(p); return t ? `<span class="addr">${esc(t)}</span>${copyBtn(t)}${p.addressExact === false ? ' <span class="pill">Approx.</span>' : ""}${p.addrNote ? `<br><span class="muted small">${esc(/mailing/i.test(p.addrNote) ? "Owner mailing address" : "Nearest road, not a street address")}</span>` : ""}` : '<span class="muted small">Not available</span>'; }, wrap: 1 },
    owner: { label: "Owner", val: (p) => p.owner || "", html: (p) => esc(p.owner || ""), wrap: 1 },
    acres: { label: "Lot Size (Acres)", num: 1, val: (p) => p.acres ?? null, html: (p) => p.acres != null ? `${p.acres < 10 ? (+p.acres).toFixed(2) : (+p.acres).toFixed(1)}${p.acresSrc === "map" ? "<sup>m</sup>" : ""}` : "" },
    sqft: { label: "Home Sq Ft", num: 1, val: (p) => p.sqft ?? null, html: (p) => p.sqft ? int(p.sqft) : "" },
    age: { label: "Home Age (Years)", num: 1, val: (p) => p.yearBuilt ? NOWYEAR - p.yearBuilt : null, html: (p) => p.yearBuilt ? `${NOWYEAR - p.yearBuilt} <span class="muted small">built ${p.yearBuilt}</span>` : "" },
    years: { label: "Yrs Unpaid", num: 1, val: (p) => p.defaultYrs ?? p.yearsUnpaid ?? null, html: (p) => (p.defaultYrs ?? p.yearsUnpaid) != null ? `${(+(p.defaultYrs ?? p.yearsUnpaid)).toFixed(1)}${p.years ? ` <span class="muted small">${esc(p.years)}</span>` : ""}` : "" },
    tenure: { label: "Owner Held (Years)", num: 1, val: (p) => p.tenure ?? null, html: (p) => p.tenure != null ? Math.round(p.tenure) : "" },
    owed: { label: "Owed / Opening Bid", num: 1, val: (p) => p.minBid ?? null, html: (p) => money2(p.minBid) },
    value: { label: "County Value", num: 1, val: (p) => p.value ?? null, html: (p) => p.value ? money(p.value) : "" },
    won: { label: "Sold For (Winning Bid)", num: 1, val: (p) => p.winningBid ?? null, html: (p) => p.winningBid > 0 ? `<span${p.priceSource ? ` title="${esc(p.priceSource)}"` : ""}>${money(p.winningBid)}${/^Derived/.test(p.priceSource || "") ? '<sup title="Derived: amount owed plus excess funds">*</sup>' : ""}</span>` : p._date < TODAY ? `<span class="muted small">${p.status === "No bid" ? "No bid" : p.sold ? "Sold, price not published" : p.status === "Listed" ? "Not published" : esc(p.status)}</span>` : "" },
    multiple: { label: "Multiple", num: 1, val: (p) => p.multiple, html: (p) => p.multiple ? p.multiple.toFixed(1) + "x" : "" },
    excess: { label: "Excess", num: 1, val: (p) => p.excess ?? null, html: (p) => money(p.excess) },
    buyer: { label: "Buyer", val: (p) => p.buyer || "", html: (p) => esc(p.buyer || ""), wrap: 1 },
    priors: { label: "Prior Auctions", num: 1, val: (p) => (p.priors || []).length, html: (p) => (p.priors || []).length ? `${p.priors.length} <span class="muted small">(${p.priors.map((x) => fmtDate(x._date, { day: undefined })).join(", ")})</span>` : "None" },
    priorSold: { label: "Prior Sold For", num: 1, val: (p) => { const s = (p.priors || []).filter((x) => x.winningBid > 0); return s.length ? s[s.length - 1].winningBid : null; }, html: (p) => (p.priors || []).map((x) => x.winningBid > 0 ? `<b>${money(x.winningBid)}</b> <span class="muted small">${fmtDate(x._date, { day: undefined })}</span>` : `<span class="muted small">${x.status === "No bid" ? "No bid" : "Not published"} ${fmtDate(x._date, { day: undefined })}</span>`).join("<br>") },
    photo: { label: "Photo", val: (p) => photos(p).length ? "Photo" : svUrl(p) ? "Street View" : "", html: (p) => photos(p).length ? `<button type="button" class="linkbtn" data-photo="${esc(p.id)}">View photo</button>` : svUrl(p) ? `<button type="button" class="linkbtn" data-photo="${esc(p.id)}">Street View</button>` : '<span class="muted small">Image N/A</span>' },
    links: { label: "Open In", nosort: 1, val: (p) => [p.parcelInfo && "record", p.parcelMap && "map", p.link && "listing"].filter(Boolean).join(" "), html: (p) => [ext(p.parcelInfo, "Parcel record"), ext(p.parcelMap, "County map"), ext(p.link, "Listing"), ext(gmap(p), "Google Maps")].filter(Boolean).join(" &middot; ") },
  };
  const ORDER = ["parcel", "watch", "date", "score", "kind", "status", "type", "area", "address", "owed", "value", "won", "multiple", "excess", "buyer", "acres", "sqft", "age", "years", "tenure", "priors", "priorSold", "owner", "photo", "links"];
  const DEFAULT_HIDDEN = ["kind", "owner", "tenure", "priorSold"];
  try { const saved = JSON.parse(localStorage.getItem(LS) || "null"); if (saved && Array.isArray(saved.order)) { G.order = saved.order.filter((k) => COLS[k]).concat(ORDER.filter((k) => !saved.order.includes(k))); G.hidden = saved.hidden || DEFAULT_HIDDEN.slice(); } } catch (e) { /* storage unavailable */ }
  if (!G.order) { G.order = ORDER.slice(); G.hidden = DEFAULT_HIDDEN.slice(); }
  const saveG = () => { try { localStorage.setItem(LS, JSON.stringify({ order: G.order, hidden: G.hidden })); } catch (e) { /* ignore */ } };
  const watchInfo = (p) => ({ county: C.label, state: C.state, parcel: p.parcel || p.lot || p.caseNo, address: addrText(p), date: p._date, minBid: p.minBid, link: `${location.origin}${location.pathname}#${C.state.toLowerCase()}/${T.slug(C.name)}?parcel=${encodeURIComponent(p.key)}` });

  const band = (cuts, v, none, fmt) => { fmt = fmt || short; if (v == null) return none; const i = cuts.findIndex((c) => v < c); return i < 0 ? `${fmt(cuts[cuts.length - 1])} and up` : i === 0 ? `Under ${fmt(cuts[0])}` : `${fmt(cuts[i - 1])} to ${fmt(cuts[i])}`; };
  const PIV = {
    parcel: { label: "Parcel (first 3 characters)", key: (p) => String(p.parcel || p.lot || "").slice(0, 3) },
    watch: { label: "Watchlist", key: (p) => WATCH.has(p.id) ? "On my watchlist" : "Not watched", order: ["On my watchlist", "Not watched"] },
    date: { label: "Sale Date", key: (p) => fmtDate(p._date), sort: (p) => p._date },
    score: { label: "Deal Score (rating)", key: (p) => p.rating, order: ["Strong", "Good", "Fair", "Weak"] },
    kind: { label: "Source type", key: (p) => KIND[p._kind] || p._kind }, status: { label: "Status", key: (p) => p.status },
    type: { label: "Property Type", key: (p) => p.cat, order: TYPES }, area: { label: "Area", key: (p) => p.area },
    address: { label: "Street", key: (p) => ((p.address || "").replace(/^\d+[A-Z]?\s+/, "").split(",")[0] || "Not stated").toUpperCase() },
    owner: { label: "Owner", key: (p) => (p.owner || "Not stated").toUpperCase() },
    acres: { label: "Lot Size (range)", key: (p) => p.acres == null ? "Not available" : p.acres < 0.25 ? "Under 0.25 acre" : p.acres < 0.5 ? "0.25 to 0.5 acre" : p.acres < 1 ? "0.5 to 1 acre" : p.acres < 5 ? "1 to 5 acres" : p.acres < 20 ? "5 to 20 acres" : "20 acres and up", order: ["Under 0.25 acre", "0.25 to 0.5 acre", "0.5 to 1 acre", "1 to 5 acres", "5 to 20 acres", "20 acres and up", "Not available"] },
    sqft: { label: "Home Sq Ft (range)", key: (p) => !p.sqft ? "Not available" : p.sqft < 1000 ? "Under 1,000" : p.sqft < 1500 ? "1,000 to 1,500" : p.sqft < 2000 ? "1,500 to 2,000" : p.sqft < 3000 ? "2,000 to 3,000" : "3,000 and up", order: ["Under 1,000", "1,000 to 1,500", "1,500 to 2,000", "2,000 to 3,000", "3,000 and up", "Not available"] },
    age: { label: "Home Age (range)", key: (p) => { if (!p.yearBuilt) return "Not available"; const g = NOWYEAR - p.yearBuilt; return g < 10 ? "Under 10 years" : g < 25 ? "10 to 25 years" : g < 50 ? "25 to 50 years" : g < 75 ? "50 to 75 years" : "75 years and up"; }, order: ["Under 10 years", "10 to 25 years", "25 to 50 years", "50 to 75 years", "75 years and up", "Not available"] },
    years: { label: "Years Unpaid (range)", key: (p) => band([3, 4, 5, 7, 10], p.defaultYrs ?? p.yearsUnpaid ?? null, "Not recorded", (v) => v + " yrs") },
    tenure: { label: "Owner Held (range)", key: (p) => band([5, 10, 20, 30], p.tenure ?? null, "Not recorded", (v) => v + " yrs") },
    owed: { label: "Amount owed (cost tier)", key: (p) => p.tier, order: TIERS.map((t) => t[2]).concat("Not stated") },
    value: { label: "County value (range)", key: (p) => band([50000, 100000, 200000, 400000], p.value || null, "Not stated") },
    won: { label: "Winning bid (range)", key: (p) => band([2500, 10000, 25000, 75000, 150000], p.winningBid || null, "No price") },
    multiple: { label: "Multiple (range)", key: (p) => !p.multiple ? "No price" : p.multiple <= 1.005 ? "At minimum" : p.multiple < 2 ? "1x to 2x" : p.multiple < 5 ? "2x to 5x" : p.multiple < 10 ? "5x to 10x" : "10x and up", order: ["At minimum", "1x to 2x", "2x to 5x", "5x to 10x", "10x and up", "No price"] },
    excess: { label: "Excess (range)", key: (p) => band([5000, 25000, 100000], p.excess || null, "None") },
    buyer: { label: "Buyer", key: (p) => (p.buyer || "Not stated").toUpperCase() },
    priors: { label: "Prior Auctions (count)", key: (p) => (p.priors || []).length ? `${p.priors.length} prior auction${p.priors.length > 1 ? "s" : ""}` : "None on file" },
    priorSold: { label: "Prior Sold For (range)", key: (p) => { const s = (p.priors || []).filter((x) => x.winningBid > 0); return band([2500, 10000, 25000, 75000, 150000], s.length ? s[s.length - 1].winningBid : null, "No prior price"); } },
    photo: { label: "Photo (type)", key: (p) => photos(p).length ? "Stored photo" : svUrl(p) ? "Live Street View" : "Image N/A" },
    links: { label: "County record link", key: (p) => p.parcelInfo ? "Parcel record available" : "No parcel record link" },
    year: { label: "Sale year", key: (p) => p._date ? p._date.slice(0, 4) : "Unknown" },
    war: { label: "Bidding war", key: (p) => !p.sold ? "Not sold" : p.war ? "Bidding war" : "Sold at minimum" },
  };
  const visible = (ps) => G.order.filter((k) => !G.hidden.includes(k) && (["parcel", "watch", "links", "photo", "score", "priors"].includes(k) || ps.some((p) => { const v = COLS[k].val(p); return v !== null && v !== "" && v !== undefined; })));
  function fillPivot() {
    $("pivotBy").innerHTML = `<option value="">None (show parcels)</option><optgroup label="By column">${G.order.map((k) => `<option value="${k}">${esc(PIV[k] ? PIV[k].label : COLS[k].label)}</option>`).join("")}</optgroup><optgroup label="Other groupings"><option value="year">Sale year</option><option value="war">Bidding war</option></optgroup>`;
    $("pivotBy").value = PIV[G.pivot] ? G.pivot : "";
  }
  function gridRows() {
    const q = $("fSearch").value.trim().toLowerCase(), qd = q.replace(/\D/g, "");
    let rows = G.rows.filter((p) => !q || [p.parcel, p.lot, p.caseNo, p.owner, p.address, p.fullAddress, p.area, p.cat, p.type, p.status, p.buyer, p.rating, p.legal].join(" ").toLowerCase().includes(q) || (qd.length >= 5 && String(p.parcel || "").replace(/\D/g, "").includes(qd)));
    if (G.filter) rows = rows.filter(G.filter.fn);
    return rows;
  }
  function drawGrid() {
    const rows = gridRows();
    $("pivotFilter").hidden = !G.filter;
    if (G.filter) { $("pivotFilter").innerHTML = `Showing <b>${esc(G.filter.label)}: ${esc(G.filter.value)}</b> <button type="button" id="clearPivotFilter">Show all</button>`; $("clearPivotFilter").onclick = () => { G.filter = null; if (G.area) { G.area = null; $("tAreas").querySelectorAll("tr.arearow").forEach((tr) => tr.classList.remove("sel")); $("areaNote").innerHTML = ""; $("areaClear").hidden = true; } drawGrid(); }; }
    if (G.pivot) return drawPivot(rows);
    const cols = visible(rows);
    const c = COLS[G.sort] ? G.sort : "score";
    rows.sort((a, b) => { const x = COLS[c].val(a), y = COLS[c].val(b); if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * G.dir; });
    const shown = rows.slice(0, 1000);
    $("parcelTable").innerHTML = `<thead><tr>${cols.map((k) => `<th draggable="true" data-k="${k}" class="${COLS[k].num ? "num" : ""}"${G.sort === k ? ` aria-sort="${G.dir > 0 ? "ascending" : "descending"}"` : ""} title="Drag to move; click to sort">${COLS[k].label}</th>`).join("")}</tr></thead><tbody>${shown.map((p, i) => `<tr class="row" data-i="${i}">${cols.map((k) => `<td class="${COLS[k].num ? "num" : ""}${COLS[k].wrap ? " wrap" : ""}">${COLS[k].html(p)}</td>`).join("")}</tr>`).join("")}</tbody>`;
    wireHeaders(cols);
    $("parcelTable").querySelectorAll("tbody tr").forEach((tr) => tr.onclick = (e) => { if (e.target.closest("a, button.copy, button.star")) return; const b = e.target.closest("button[data-photo]"); if (b) { openLightbox(shown[+tr.dataset.i]); return; } showDetail(shown[+tr.dataset.i]); });
    $("tableNote").textContent = `${int(rows.length)} parcel${rows.length === 1 ? "" : "s"} in ${SEL.label}${rows.length > 1000 ? " (first 1,000 shown; download for all)" : ""}. "Not published" means the source has not released the outcome. An asterisk marks a price worked out as amount owed plus excess funds; a small m after a lot size means it was measured from the parcel map.`;
    renderColPanel(rows);
  }
  function wireHeaders(cols) {
    let dragK = null;
    $("parcelTable").querySelectorAll("th").forEach((th) => {
      th.onclick = () => { const k = th.dataset.k; if (COLS[k].nosort) return; G.dir = G.sort === k ? -G.dir : (COLS[k].num ? -1 : 1); G.sort = k; drawGrid(); };
      th.addEventListener("dragstart", (e) => { dragK = th.dataset.k; e.dataTransfer.effectAllowed = "move"; th.classList.add("dragging"); });
      th.addEventListener("dragend", () => th.classList.remove("dragging"));
      th.addEventListener("dragover", (e) => { e.preventDefault(); th.classList.add("dropzone"); });
      th.addEventListener("dragleave", () => th.classList.remove("dropzone"));
      th.addEventListener("drop", (e) => { e.preventDefault(); const to = th.dataset.k; if (!dragK || dragK === to) return; const o = G.order.filter((k) => k !== dragK); o.splice(o.indexOf(to), 0, dragK); G.order = o; saveG(); drawGrid(); });
    });
  }
  function renderColPanel(rows) {
    fillPivot();
    $("colPanel").innerHTML = G.order.map((k, i) => { const unavailable = !["parcel", "watch", "links", "photo", "score", "priors"].includes(k) && !rows.some((p) => { const v = COLS[k].val(p); return v !== null && v !== "" && v !== undefined; }); return `<div class="colrow"><label><input type="checkbox" data-k="${k}" ${G.hidden.includes(k) ? "" : "checked"} ${unavailable ? "disabled" : ""}> ${COLS[k].label}${unavailable ? ' <span class="muted small">(no data)</span>' : ""}</label><span><button type="button" data-pivot="${k}" title="Summarize the grid by this column">Pivot</button><button type="button" data-up="${k}" ${i === 0 ? "disabled" : ""} aria-label="Move up">&#8593;</button><button type="button" data-down="${k}" ${i === G.order.length - 1 ? "disabled" : ""} aria-label="Move down">&#8595;</button></span></div>`; }).join("") + `<div class="colrow"><button type="button" id="resetCols">Reset columns</button></div>`;
    $("colPanel").querySelectorAll("input").forEach((cb) => cb.onchange = () => { const k = cb.dataset.k; G.hidden = cb.checked ? G.hidden.filter((x) => x !== k) : G.hidden.concat(k); saveG(); drawGrid(); });
    $("colPanel").querySelectorAll("[data-pivot]").forEach((b) => b.onclick = () => setPivot(b.dataset.pivot));
    $("colPanel").querySelectorAll("[data-up],[data-down]").forEach((b) => b.onclick = () => { const k = b.dataset.up || b.dataset.down, i = G.order.indexOf(k), j = i + (b.dataset.up ? -1 : 1); [G.order[i], G.order[j]] = [G.order[j], G.order[i]]; saveG(); drawGrid(); });
    $("resetCols").onclick = () => { G.order = ORDER.slice(); G.hidden = DEFAULT_HIDDEN.slice(); saveG(); drawGrid(); };
  }
  function setPivot(k) { G.pivot = PIV[k] ? k : ""; const P = PIV[k]; G.pSort = P && (P.order || P.sort) ? "name" : "n"; G.pDir = P && (P.order || P.sort) ? 1 : -1; $("colPanel").hidden = true; drawGrid(); }
  function drawPivot(rows) {
    const P = PIV[G.pivot], groups = {};
    rows.forEach((p) => (groups[P.key(p)] = groups[P.key(p)] || []).push(p));
    const names = Object.keys(groups);
    const stat = (g) => { const s = g.filter((p) => p.winningBid); return { n: g.length, sold: g.filter((p) => p.sold).length, owed: avg(g.map((p) => p.minBid)), won: avg(s.map((p) => p.winningBid)), mult: median(s.map((p) => p.multiple)), deal: avg(g.map((p) => p.score)), war: s.length ? s.filter((p) => p.war).length / s.length : null, excess: sum(g.map((p) => p.excess)), prior: g.filter((p) => (p.priors || []).length).length }; };
    const S = {}; names.forEach((n) => (S[n] = stat(groups[n])));
    const pc = [["name", P.label], ["n", "Parcels", 1], ["sold", "Sold", 1], ["owed", "Avg owed", 1], ["won", "Avg winning bid", 1], ["mult", "Median multiple", 1], ["deal", "Avg deal score", 1], ["war", "Bidding wars", 1], ["prior", "Seen at earlier sales", 1], ["excess", "Total excess", 1]];
    const k = G.pSort, oi = (o, v) => { const i = o.indexOf(v); return i < 0 ? 999 : i; };
    const sortKey = (n) => P.sort ? P.sort(groups[n][0]) : n;
    names.sort((a, b) => k === "name" ? (P.order ? oi(P.order, a) - oi(P.order, b) || a.localeCompare(b) : String(sortKey(a)).localeCompare(String(sortKey(b)), undefined, { numeric: true })) * G.pDir : ((S[a][k] ?? -1) - (S[b][k] ?? -1)) * G.pDir);
    const fmt = { n: int, sold: int, owed: money, won: money, mult: (v) => v ? v.toFixed(1) + "x" : "", deal: (v) => v != null ? Math.round(v) : "", war: (v) => v == null ? "" : pct(v), prior: int, excess: (v) => v ? money(v) : "" };
    const tot = stat(rows);
    $("parcelTable").innerHTML = `<thead><tr>${pc.map((c) => `<th data-k="${c[0]}" class="${c[2] ? "num" : ""}"${k === c[0] ? ` aria-sort="${G.pDir > 0 ? "ascending" : "descending"}"` : ""}>${c[1]}</th>`).join("")}</tr></thead><tbody>${names.map((n) => `<tr data-g="${esc(n)}" class="pivotrow"><td><b>${esc(n)}</b></td>${pc.slice(1).map((c) => `<td class="num">${fmt[c[0]](S[n][c[0]])}</td>`).join("")}</tr>`).join("")}</tbody><tfoot><tr><td><b>Total</b></td>${pc.slice(1).map((c) => `<td class="num"><b>${fmt[c[0]](tot[c[0]])}</b></td>`).join("")}</tr></tfoot>`;
    $("parcelTable").querySelectorAll("th").forEach((th) => th.onclick = () => { const kk = th.dataset.k; G.pDir = G.pSort === kk ? -G.pDir : (kk === "name" ? 1 : -1); G.pSort = kk; drawGrid(); });
    $("parcelTable").querySelectorAll("tbody tr").forEach((tr) => tr.onclick = () => { const key = P.key, v = tr.dataset.g; G.filter = { label: P.label, value: v, fn: (p) => key(p) === v }; G.pivot = ""; $("pivotBy").value = ""; drawGrid(); $("parcels").scrollIntoView({ behavior: "smooth" }); });
    $("tableNote").textContent = `${names.length} group${names.length === 1 ? "" : "s"} across ${int(rows.length)} parcels in ${SEL.label}. Click a group to see its parcels.`;
    renderColPanel(rows);
  }
  const csvCols = () => [{ key: "county", label: "County", val: () => C.label }, { key: "state", label: "State", val: () => C.state }, ...ORDER.filter((k) => !["watch", "links", "photo"].includes(k)).map((k) => ({ key: k, label: COLS[k].label, val: (p) => COLS[k].val(p) })),
    { key: "lat", label: "Latitude" }, { key: "lon", label: "Longitude" }, { key: "parcelInfo", label: "Parcel record" }, { key: "parcelMap", label: "County map" }, { key: "link", label: "Listing" }, { key: "gmap", label: "Google Maps", val: gmap }, { key: "photo", label: "Photo", val: (p) => photos(p)[0] || (svUrl(p) ? "Street View" : "") }, { key: "_src", label: "Source document" }];
  $("fSearch").addEventListener("input", () => drawGrid());
  $("pivotBy").addEventListener("change", () => setPivot($("pivotBy").value));
  $("colBtn").addEventListener("click", () => { $("colPanel").hidden = !$("colPanel").hidden; });
  document.addEventListener("click", (e) => { if (!e.target.closest(".colmenu")) $("colPanel").hidden = true; });
  $("csvBtn").addEventListener("click", () => downloadCsv(`${C.state.toLowerCase()}-${T.slug(C.name)}-parcels.csv`, csvCols(), gridRows()));
  document.addEventListener("watchlist-change", () => { if (G.pivot === "watch") drawGrid(); });

  // ---------- history ----------
  function drawHistory() {
    const hist = [...PREP.aucs].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    const labels = hist.map((a) => (a.date ? fmtDate(a.date) : a.label));
    chart("cHist", { type: "bar", data: { labels, datasets: [{ label: "Parcels", data: hist.map((a) => a.parcels.length), backgroundColor: hist.map((a) => a.status === "upcoming" ? "#8e5ad6" : "#2a78d6"), borderRadius: 4, maxBarThickness: 30 }] },
      options: { maintainAspectRatio: false, onClick: (e, els) => { if (!els.length) return; const a = hist[els[0].index]; setTimeout(() => { $("cAuction").value = String(PREP.aucs.indexOf(a)); $("cAuction").dispatchEvent(new Event("change")); $("cKpis").scrollIntoView({ behavior: "smooth", block: "start" }); }, 0); }, onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
        plugins: { legend: { display: false }, title: { display: true, text: "Parcels per sale (purple = upcoming); click a bar to pick that sale" } }, scales: { y: { beginAtZero: true, grid: { color: "#ebe9e4" }, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { maxRotation: 45, autoSkip: true } } } } });
    const avgs = hist.map((a) => { const b = a.parcels.filter((p) => p.winningBid).map((p) => p.winningBid); return b.length ? avg(b) : null; });
    chart("cHistBid", { type: "line", data: { labels, datasets: [{ label: "Average winning bid", data: avgs, borderColor: "#eb6834", backgroundColor: "#eb6834", borderWidth: 2, pointRadius: 4, spanGaps: true, tension: 0.2 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: "Average winning bid per sale" }, tooltip: { callbacks: { label: (x) => money(x.raw) } } }, scales: { y: { beginAtZero: true, grid: { color: "#ebe9e4" }, ticks: { callback: (v) => money(v) } }, x: { grid: { display: false }, ticks: { maxRotation: 45, autoSkip: true } } } } });
    makeTable("tHist", [
      { key: "date", label: "Date", html: (a) => fmtDate(a.date) }, { key: "label", label: "Sale", wrap: true },
      { key: "kind", label: "Type", html: (a) => `<span class="kind ${esc(a.saleKind || a.kind)}">${esc(KIND[a.saleKind || a.kind] || a.kind)}</span>` },
      { key: "status", label: "Status", html: (a) => a.status === "upcoming" ? '<span class="open">Upcoming</span>' : "Past" },
      { key: "n", label: "Parcels", num: true, val: (a) => a.parcels.length }, { key: "sold", label: "Sold", num: true, val: (a) => a.parcels.filter((p) => p.sold).length },
      { key: "avg", label: "Avg winning bid", num: true, val: (a) => { const b = a.parcels.filter((p) => p.winningBid).map((p) => p.winningBid); return b.length ? avg(b) : null; }, html: (a) => { const b = a.parcels.filter((p) => p.winningBid).map((p) => p.winningBid); return b.length ? money(avg(b)) : ""; } },
      { key: "excess", label: "Excess", num: true, val: (a) => sum(a.parcels.map((p) => p.excess)) || null, html: (a) => money(sum(a.parcels.map((p) => p.excess)) || null) },
      { key: "source", label: "Source", cls: "links", html: (a) => a.source ? `<a href="${esc(a.source)}" target="_blank" rel="noopener">Open</a>` : "" },
    ], hist, { sortKey: "date", sortDir: "desc", rowClass: () => "row", onRow: (a) => { $("cAuction").value = String(PREP.aucs.indexOf(a)); $("cAuction").dispatchEvent(new Event("change")); $("cKpis").scrollIntoView({ behavior: "smooth" }); } });
  }

  // ---------- gallery and lightbox ----------
  const mediaRank = (p) => photos(p).length ? 0 : svUrl(p) ? 1 : 2;
  function gallery() {
    const all = GAL.items, f = $("gFilter").value;
    const items = all.filter((p) => f === "all" || (f === "photo" && mediaRank(p) === 0) || (f === "sv" && mediaRank(p) === 1) || (f === "na" && mediaRank(p) === 2));
    const n = [0, 1, 2].map((r) => all.filter((p) => mediaRank(p) === r).length);
    $("gFilter").innerHTML = [["all", `All parcels (${all.length})`], ["photo", `Stored photos (${n[0]})`], ["sv", `Live Street View (${n[1]})`], ["na", `Image N/A (${n[2]})`]].map(([v, t]) => `<option value="${v}"${v === f ? " selected" : ""}>${t}</option>`).join("");
    const pages = Math.max(1, Math.ceil(items.length / GAL.per)); GAL.page = Math.min(GAL.page, pages - 1);
    const page = items.slice(GAL.page * GAL.per, (GAL.page + 1) * GAL.per);
    $("gPage").textContent = `page ${GAL.page + 1} of ${pages}`;
    $("gGrid").innerHTML = page.map((p, i) => { const ph = photos(p)[0], sv = svUrl(p); return `<div class="gtile" data-i="${i}"><div class="media">${ph ? `<img loading="lazy" src="${esc(ph)}" alt="Photo of ${esc(addrText(p) || p.parcel)}">` : sv ? `<iframe loading="lazy" src="${sv}" title="Street View" tabindex="-1"></iframe>` : `<div class="na">Image N/A</div>`}<span class="badge">${ph ? `Photo${photos(p).length > 1 ? " · " + photos(p).length : ""}` : sv ? "Street View" : "No image"} · ${p.score} ${p.rating}</span></div><div class="cap"><b>${esc(addrText(p) || p.parcel || p.lot || "")}</b>${p.minBid != null ? "Owed " + money(p.minBid) : ""}${p.winningBid ? " · sold " + money(p.winningBid) : ""} · ${esc(p.status)}</div></div>`; }).join("");
    $("gGrid").querySelectorAll(".gtile").forEach((t) => t.onclick = () => openLightbox(page[+t.dataset.i]));
    $("gGrid").querySelectorAll("img").forEach((im) => im.addEventListener("error", () => { const p = page[+im.closest(".gtile").dataset.i], sv = svUrl(p); im.outerHTML = sv ? `<iframe loading="lazy" src="${sv}" tabindex="-1"></iframe>` : `<div class="na">Image N/A</div>`; }));
    $("gNote").textContent = `${int(all.length)} parcels in ${SEL.label}: ${n[0]} with stored photos, ${n[1]} with a live Street View near the lot, ${n[2]} with no image. Click a tile to enlarge it.`;
  }
  $("gFilter").addEventListener("change", () => { GAL.page = 0; gallery(); });
  $("gPrev").addEventListener("click", () => { GAL.page = Math.max(0, GAL.page - 1); gallery(); });
  $("gNext").addEventListener("click", () => { GAL.page++; gallery(); });
  function openLightbox(p) {
    const phs = photos(p), sv = svUrl(p), slides = phs.map((x) => ({ t: "img", src: x })).concat(sv ? [{ t: "sv" }] : []);
    let cur = 0;
    const show = () => {
      const s = slides[cur];
      $("lbMedia").innerHTML = !s ? `<div class="na big">Image N/A</div>` : s.t === "img" ? `<img src="${esc(s.src)}" alt="Photo of ${esc(addrText(p) || p.parcel)}">` : `<iframe src="${sv}" title="Street View" allowfullscreen></iframe>`;
      $("lbCredit").innerHTML = !s ? "No photo is published for this parcel and no coordinates are on file." : s.t === "img" ? `Stored photo. Source: ${esc(p.photoCredit || "county records or the auction catalog")}.` : "Live Google Street View near the parcel. Drag to look around; Google shows the imagery date.";
      $("lbThumbs").innerHTML = slides.length > 1 ? slides.map((x, i) => `<button type="button" class="${i === cur ? "on" : ""}" data-i="${i}">${x.t === "img" ? `<img src="${esc(x.src)}" alt="">` : "Street View"}</button>`).join("") : "";
      $("lbThumbs").querySelectorAll("button").forEach((b) => b.onclick = () => { cur = +b.dataset.i; show(); });
    };
    const row = (l, v) => v === "" || v == null ? "" : `<div><span>${l}</span><span>${v}</span></div>`;
    $("lbInfo").innerHTML = `<h2>${esc(p.parcel || p.lot || "Parcel")} ${WATCH.btn(p.id, watchInfo(p))}</h2><p class="muted">${addrText(p) ? esc(addrText(p)) + copyBtn(addrText(p)) : "No address published"} · ${esc(C.label)}</p><div class="dgrid">${row("Sale date", fmtDate(p._date)) + row("Status", esc(p.status)) + row("Deal score", scoreHtml(p, PREP.ctx)) + row("Property type", esc(p.cat)) + row("Lot size", p.acres != null ? p.acres + " acres" : "") + row("Home square footage", p.sqft ? int(p.sqft) : "") + row("Home age", p.yearBuilt ? `${NOWYEAR - p.yearBuilt} years (built ${p.yearBuilt})` : "") + row("Amount owed", money2(p.minBid)) + row("Sold for", p.winningBid > 0 ? money(p.winningBid) : "") + row("County value", money(p.value)) + row("Prior auctions", (p.priors || []).length || "")}</div><div class="dlinks"><button type="button" class="primary" id="lbHl">Highlight In Table</button><button type="button" class="linkbtn" id="lbDetail">Full details</button>${ext(p.parcelInfo, "Parcel record")}${ext(p.parcelMap, "County parcel map")}${ext(p.link, "Listing")}${ext(gmap(p), "Google Maps")}</div>`;
    $("lbHl").onclick = () => highlightInTable(p);
    $("lbDetail").onclick = () => { $("lightbox").close(); showDetail(p); };
    show();
    if (!$("lightbox").open) $("lightbox").showModal();
  }
  function highlightInTable(p) {
    $("lightbox").close();
    G.pivot = ""; G.filter = null; $("pivotBy").value = ""; $("fSearch").value = p.parcel || p.lot || ""; drawGrid();
    const tr = $("parcelTable").querySelector("tbody tr");
    if (tr) { tr.scrollIntoView({ behavior: "smooth", block: "center" }); tr.classList.add("flash"); setTimeout(() => tr.classList.remove("flash"), 2500); }
  }

  // ---------- parcel detail ----------
  function showDetail(p) {
    const st = PREP.st || (PREP.st = window.TS.stateOf ? window.TS.stateOf(C.state) : null);
    const d = p.ds;
    const rows = [["Sale", `${fmtDate(p._date)} · ${esc(p._auction || "")}`], ["Source type", esc(KIND[p._kind] || p._kind)], ["Status", esc(p.status)], ["Deal score", scoreHtml(p, PREP.ctx)], ["Property type", esc(p.cat) + (p.type && p.type !== p.cat ? ` <span class="muted small">(${esc(p.typeDetail || p.type)})</span>` : "")], ["Area", esc(p.area)], ["Owner", esc(p.owner)], ["Buyer", esc(p.buyer)], ["Plaintiff", esc(p.plaintiff)], ["Case", esc(p.caseNo)], ["Certificate", esc(p.certificate)], ["Lot", esc(p.lot)], ["Sold at", esc(p.soldDate)],
      ["Amount owed / opening bid", money2(p.minBid)], ["Sold for", p.winningBid > 0 ? money(p.winningBid) + (p.priceSource ? ` <span class="muted small">(${esc(p.priceSource)})</span>` : "") : ""], ["Multiple", p.multiple ? p.multiple.toFixed(2) + "x" : ""], ["Excess funds", money(p.excess)], ["County value", money(p.value)], ["Judgment", money(p.judgment)], ["Current taxes", money(p.taxes)],
      ["Lot size", p.acres != null ? `${p.acres} acres${p.acresSrc === "map" ? " (measured from the parcel map)" : ""}` : ""], ["Home square footage", p.sqft ? int(p.sqft) : ""], ["Year built", p.yearBuilt], ["Years unpaid", (p.defaultYrs ?? p.yearsUnpaid) != null ? `${(+(p.defaultYrs ?? p.yearsUnpaid)).toFixed(1)}${p.years ? " (" + esc(p.years) + ")" : ""}` : ""], ["Former owner held", p.tenure != null ? `${Math.round(p.tenure)} years` : ""], ["County took title", fmtDate(p.trustDate)], ["Deed recorded", fmtDate(p.deedRecorded)], ["Legal description", esc(p.legal)],
      ["Prior auctions on file", (p.priors || []).length ? p.priors.map((x) => `${fmtDate(x._date)}: ${x.winningBid > 0 ? money(x.winningBid) : x.status}`).join("; ") : ""]].filter((r) => r[1] !== undefined && r[1] !== null && r[1] !== "");
    const hist = (p.history || []).length ? `<h3 class="mt">Ownership history</h3><table class="data mini"><tbody>${p.history.map((h) => `<tr><td>${fmtDate(h.date)}</td><td class="wrap">${esc(h.owner)}</td></tr>`).join("")}</tbody></table>` : "";
    const w = WATCH.get(p.id);
    const media = photos(p).length ? `<div class="lbmedia"><img src="${esc(photos(p)[0])}" alt="Photo"></div>` : svUrl(p) ? `<div class="lbmedia"><iframe src="${svUrl(p)}" title="Street View" allowfullscreen></iframe></div>` : "";
    $("detailBody").innerHTML = `<h2>${esc(p.parcel || p.lot || p.caseNo || "Parcel")} ${WATCH.btn(p.id, watchInfo(p))}</h2><p class="muted small">${addrText(p) ? esc(addrText(p)) + copyBtn(addrText(p)) : "No address published"} · ${esc(C.label)}, ${esc(C.state)}</p>${media}${p.desc ? `<p class="desc">${esc(p.desc)}</p>` : ""}<div class="dgrid">${rows.map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`).join("")}</div>
      <details class="scorehelp"><summary>How the ${d.score} score was built</summary><ul>${d.parts.map((x) => `<li><b>${x[0]} ${x[1]}/${x[2]}:</b> ${esc(x[3])}</li>`).join("")}</ul></details>
      ${hist}
      <div class="watchnote"><label>Watchlist note <textarea id="dNote" rows="2" placeholder="Your notes on this parcel (kept in this browser)">${esc(w ? w.note : "")}</textarea></label></div>
      <h3 class="mt">If The Owner Redeems</h3>${st ? redemptionTable(st, p.winningBid || p.minBid || 0) : ""}
      <div class="dlinks">${ext(p.parcelInfo, "Parcel record")}${ext(p.parcelMap, "County parcel map")}${ext(p.link, "Listing")}${ext(p._src, "Source document")}${ext(C.taxsale, "County tax sale page")}${ext(gmap(p), "Google Maps")}<a href="sheet.html?fips=${C.fips}&id=${encodeURIComponent(p.id)}" target="_blank" rel="noopener">Print deal sheet</a><a href="analyzer.html#state=${C.state}&county=${encodeURIComponent(C.label)}">Open in the analyzer</a></div>`;
    $("dNote").oninput = () => { if (!WATCH.has(p.id)) WATCH.toggle(p.id, watchInfo(p)); WATCH.note(p.id, $("dNote").value); document.querySelectorAll(`button.star[data-watch="${CSS.escape(p.id)}"]`).forEach((x) => { x.classList.add("on"); x.textContent = "★"; }); };
    $("detail").showModal();
  }

  window.TS.county = { show, setState: (st) => { if (PREP) PREP.st = st; } };
})();
