/* US Tax Sale Tracker: national and state views, search and routing. County pages live in county.js; shared helpers in common.js. */
(function () {
  "use strict";
  const T = window.TS;
  const { $, esc, money, int, pct, sum, avg, median, fmtDate, slug, searchUrl, TODAY, NOWYEAR, chart, Drill, makeTable, downloadCsv, WATCH, ics, downloadText } = T;
  const SYS = { deed: { label: "Tax deed", color: "#2a78d6" }, lien: { label: "Tax lien", color: "#eb6834" }, redeemable: { label: "Redeemable deed", color: "#159c6c" }, hybrid: { label: "Hybrid (lien, then deed)", color: "#8e5ad6" } };
  let REG = null, STATES = {}, COUNTIES = [], BY_FIPS = {}, BY_STATE = {}, TOPO = null, INDEX = null, CHANGES = null, MASTER = null;
  const COUNTY_CACHE = {};
  const maps = {};
  T.stateOf = (abbr) => STATES[abbr];

  // ---------- loading ----------
  async function load() {
    const [reg, topo, idx, chg] = await Promise.all([
      fetch("data/registry.json", { cache: "no-cache" }).then((r) => r.json()),
      fetch("ref/us-counties-10m.json").then((r) => r.json()),
      fetch("data/index.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => null),
      fetch("data/changes.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => null),
    ]);
    REG = reg; TOPO = topo; INDEX = idx; CHANGES = chg;
    for (const s of reg.states) STATES[s.abbr] = s;
    COUNTIES = reg.counties;
    for (const c of COUNTIES) { c.st = STATES[c.state]; c.stateName = c.st.name; c.slug = slug(c.name); BY_FIPS[c.fips] = c; (BY_STATE[c.state] = BY_STATE[c.state] || []).push(c); }
    renderFreshness(); renderNav(); renderFooter(); route();
    if (INDEX && INDEX.generated) T.autoRefresh(INDEX.generated);
  }
  function renderFreshness() {
    const gen = REG.generated ? new Date(REG.generated) : null;
    const srcs = INDEX && INDEX.sources ? Object.values(INDEX.sources) : [];
    $("freshness").innerHTML = `<span class="dotlive"></span><b>Data generated ${gen ? gen.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "unknown"}</b> &middot; ${srcs.length ? `${srcs.filter((s) => s.ok).length} of ${srcs.length} sources answered` : "registry only"} &middot; refreshed on the 1st of every month &middot; open pages recheck every 30 minutes`;
  }
  function renderNav() {
    const sel = $("selState");
    sel.innerHTML = `<option value="us">United States (all)</option>` + REG.states.map((s) => `<option value="${s.abbr}">${esc(s.name)}${s.withData ? ` (${s.withData} with data)` : ""}</option>`).join("");
    sel.onchange = () => { location.hash = sel.value === "us" ? "" : sel.value.toLowerCase(); };
    $("selCounty").onchange = () => { const v = $("selCounty").value; if (v) location.hash = countyHref(BY_FIPS[v]).slice(1); };
    $("selType").onchange = () => { const v = $("selType").value; $("selShow").value = ""; location.hash = v ? "q=type:" + v : ""; };
    $("selShow").onchange = () => { let v = $("selShow").value; $("selType").value = ""; if (v === "next:__soon__") { const d = new Date(); d.setDate(d.getDate() + 60); v = "next:" + d.toISOString().slice(0, 10); } location.hash = v ? "q=" + v : ""; };
  }
  function fillCountyDropdown(abbr, fips) {
    const sel = $("selCounty"), list = BY_STATE[abbr] || [];
    if (!list.length) { sel.disabled = true; sel.innerHTML = `<option value="">Pick a state first</option>`; return; }
    sel.disabled = false;
    sel.innerHTML = `<option value="">All of ${esc(STATES[abbr].name)}</option>` + list.map((c) => `<option value="${c.fips}">${esc(c.label)}${c.data ? ` (${int(c.data.parcels)} parcels)` : ""}</option>`).join("");
    sel.value = fips || "";
  }
  function renderFooter() {
    const srcs = INDEX && INDEX.sources ? Object.values(INDEX.sources) : [];
    $("foot").innerHTML = `County list, boundaries, land area and 2024 population come from the <a href="https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html" target="_blank" rel="noopener">U.S. Census Bureau</a>; official county websites from <a href="https://www.wikidata.org/" target="_blank" rel="noopener">Wikidata</a>; tax sale, sheriff sale and assessor pages are found on each county's own site. State rules are summarized from each state's statutes and are for orientation only, not legal advice. Parcel-level data comes from: ${srcs.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a> (${s.ok ? `${s.counties} counties` : "unavailable at the last check"})`).join("; ")}. Lists change up to the day of the sale; always confirm with the county. Not affiliated with any government. <a href="https://github.com/ShamarRobinson/us-tax-sale-dashboard" target="_blank" rel="noopener">Source on GitHub</a> &middot; <a href="analyzer.html">Property Deal Analyzer</a> &middot; <a href="data/upcoming.ics" download>Calendar of upcoming sales (.ics)</a>.`;
  }

  // ---------- routing ----------
  function route() {
    const h = decodeURIComponent(location.hash.replace(/^#/, "")).trim();
    if (h.startsWith("q=")) { const q = h.slice(2); $("gSearch").value = q.replace(/^parcels:/, ""); if (q.startsWith("parcels:")) { $("searchMode").value = "parcels"; runParcelSearch(q.slice(8)); } else { $("searchMode").value = "counties"; runSearch(q); } return; }
    $("results").hidden = true;
    const path = h.split("?")[0];
    if (!path || path === "us") { showNation(); return; }
    const [st, rest] = path.split("/");
    const abbr = st.toUpperCase();
    if (st === "c" && rest && BY_FIPS[rest]) { showCounty(BY_FIPS[rest]); return; }
    if (!STATES[abbr]) { showNation(); return; }
    if (rest) { const c = (BY_STATE[abbr] || []).find((x) => x.slug === rest || x.fips === rest); if (c) { showCounty(c); return; } }
    showState(abbr);
  }
  window.addEventListener("hashchange", route);
  function setView(name, tab, fips) {
    for (const v of ["viewNation", "viewState", "viewCounty"]) $(v).hidden = v !== name;
    $("selState").value = tab; fillCountyDropdown(tab === "us" ? null : tab, fips);
    $("selType").value = ""; $("selShow").value = "";
    window.scrollTo({ top: 0 });
  }
  const go = (hash) => { location.hash = hash; };

  // ---------- map helpers ----------
  function simpleMap(id) { if (maps[id]) maps[id].remove(); const m = L.map(id, { crs: L.CRS.Simple, attributionControl: false, zoomSnap: 0.25, minZoom: -3, scrollWheelZoom: false }); maps[id] = m; return m; }
  const ALBERS = d3.geoAlbersUsa().scale(1300).translate([487.5, 305]);
  const projector = (proj) => (coords) => { const p = proj(coords); return p ? L.latLng(-p[1], p[0]) : L.latLng(0, 0); };
  const projects = (proj, f) => !!proj(d3.geoCentroid(f));
  const stateProjection = (features) => features.every((f) => projects(ALBERS, f)) ? ALBERS : d3.geoMercator().fitSize([975, 610], { type: "FeatureCollection", features });

  // ---------- county helpers ----------
  const nextSaleText = (c) => c.nextSale ? fmtDate(c.nextSale) : (c.nextSaleLabel || "");
  const nextSaleKind = (c) => c.nextSaleKind === "posted" ? "Posted" : c.nextSaleKind === "statutory" ? "By statute" : c.nextSaleKind === "window" ? "Season" : "";
  const sysPill = (k, big) => `<span class="pill ${k}${big ? " big" : ""}">${esc(SYS[k].label)}</span>`;
  const whoRuns = (c) => c.run || c.st.conducted_by;
  const shortRun = (c) => (c.run || c.st.conducted_by).split(/;| \(/)[0].trim();
  const countyHref = (c) => `#${c.state.toLowerCase()}/${c.slug}`;
  const coverage = (c) => [1, !!c.site, !!c.taxsale, !!c.data, !!(c.data && c.data.photos)].filter(Boolean).length;
  const coverageHtml = (c) => { const n = coverage(c); return `<span class="pill" title="Rules, official site, tax sale page, parcel data, photos">${"●".repeat(n)}${"○".repeat(5 - n)}</span>`; };
  const linkCell = (c) => {
    const out = [];
    if (c.taxsale) out.push(`<a href="${esc(c.taxsale)}" target="_blank" rel="noopener">${c.taxsaleKind === "state" ? "State sale site" : "Tax sale page"}</a>`);
    else out.push(`<a href="${searchUrl(`${c.label} ${c.st.name} tax sale`)}" target="_blank" rel="noopener">Find sale page</a>`);
    if (c.sheriffSale) out.push(`<a href="${esc(c.sheriffSale)}" target="_blank" rel="noopener">Sheriff sales</a>`);
    if (c.site) out.push(`<a href="${esc(c.site)}" target="_blank" rel="noopener">Official site</a>`);
    return out.join("");
  };
  function rulesHtml(s, full) {
    const rows = [["Sale type", SYS[s.system].label], ["Who holds the sale", s.conducted_by], ["When", s.sale_timing], ["Bidding", s.bidding], ["Interest, penalty or return", s.rate], ["Redemption", s.redemption], ["Mortgage foreclosures and sheriff sales", s.sheriff_sales], ["Statute", s.statute], ["Platforms", (s.platforms || []).join("; ")]];
    if (full && s.notes) rows.push(["Notes", s.notes]);
    if (s.state_portal) rows.push(["State sale site", `<a href="${esc(s.state_portal)}" target="_blank" rel="noopener">${esc(s.state_portal)}</a>`]);
    return rows.filter((r) => r[1]).map(([k, v]) => `<div${k.length > 20 || String(v).length > 120 ? ' class="wide"' : ""}><b>${esc(k)}</b>${k === "State sale site" ? v : esc(v)}</div>`).join("");
  }

  // ---------- NATION ----------
  function showNation() {
    setView("viewNation", "us");
    const withData = COUNTIES.filter((c) => c.data), parcels = withData.reduce((s, c) => s + c.data.parcels, 0);
    const posted = COUNTIES.filter((c) => c.nextSaleKind === "posted"), withSite = COUNTIES.filter((c) => c.site).length, withLink = COUNTIES.filter((c) => c.taxsale).length;
    $("nKpis").innerHTML = [
      ["Counties tracked", int(COUNTIES.length), "every county and county equivalent", true],
      ["States and territories", REG.states.length, "50 states, DC and Puerto Rico"],
      ["Counties with parcel data", int(withData.length), `${int(parcels)} parcels on file`],
      ["Posted upcoming sales", int(posted.length), "dates published by a source"],
      ["Tax sale pages linked", int(withLink), `plus ${int(withSite)} official county sites`],
      ["Parcel photos on file", int(INDEX?.photos || 0), "plus Street View for every parcel with coordinates"],
      ["On your watchlist", int(WATCH.count()), '<a href="analyzer.html#show=watch">open in the analyzer</a>'],
    ].map(([l, v, n, hero]) => `<div class="kpi${hero ? " hero" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");

    if (CHANGES && (CHANGES.newUpcoming?.length || CHANGES.newCounties?.length || CHANGES.parcelDelta)) {
      $("nChanges").hidden = false;
      $("nChangesBody").innerHTML = `<p class="muted small">Compared with the refresh of ${esc(fmtDate((CHANGES.previous || "").slice(0, 10)))}: ${CHANGES.parcelDelta ? `<b>${CHANGES.parcelDelta > 0 ? "+" : ""}${int(CHANGES.parcelDelta)} parcels</b> on file` : "no change in parcel count"}${CHANGES.newCounties?.length ? `; new counties with data: ${CHANGES.newCounties.map((f) => BY_FIPS[f] ? `<a href="${countyHref(BY_FIPS[f])}">${esc(BY_FIPS[f].label)}, ${BY_FIPS[f].state}</a>` : f).join(", ")}` : ""}${CHANGES.linkDelta ? `; ${CHANGES.linkDelta > 0 ? "+" : ""}${int(CHANGES.linkDelta)} tax sale pages linked` : ""}.</p>` +
        (CHANGES.newUpcoming?.length ? `<div class="tablewrap"><table class="data"><thead><tr><th>Newly posted sale</th><th>County</th><th class="num">Parcels</th></tr></thead><tbody>${CHANGES.newUpcoming.slice(0, 25).map((u) => `<tr class="row"><td>${fmtDate(u.date)}</td><td>${BY_FIPS[u.fips] ? `<a href="${countyHref(BY_FIPS[u.fips])}">${esc(u.name)}, ${u.state}</a>` : esc(u.name)}</td><td class="num">${int(u.parcels)}</td></tr>`).join("")}</tbody></table></div>` : "");
    } else $("nChanges").hidden = true;

    const sysRows = Object.keys(SYS).map((k) => { const sts = REG.states.filter((s) => s.system === k); return { k, states: sts.length, counties: sts.reduce((a, s) => a + s.counties, 0), list: sts.map((s) => s.abbr).join(", ") }; });
    $("nSystems").innerHTML = `<thead><tr><th>System</th><th class="num">States</th><th class="num">Counties</th><th>Where</th></tr></thead><tbody>${sysRows.map((r) => `<tr><td><span class="sw" style="background:${SYS[r.k].color}"></span>${esc(SYS[r.k].label)}</td><td class="num">${r.states}</td><td class="num">${int(r.counties)}</td><td class="wrap small">${esc(r.list)}</td></tr>`).join("")}</tbody>`;
    $("nLegend").innerHTML = Object.keys(SYS).map((k) => `<span><i class="sq" style="background:${SYS[k].color};opacity:.8"></i>${esc(SYS[k].label)}</span>`).join("");

    const m = simpleMap("nMap");
    const states = topojson.feature(TOPO, TOPO.objects.states);
    states.features = states.features.filter((f) => Object.values(STATES).some((x) => x.fips === f.id) && projects(ALBERS, f));
    const layer = L.geoJSON(states, { coordsToLatLng: projector(ALBERS),
      style: (f) => { const s = Object.values(STATES).find((x) => x.fips === f.id); return { color: "#000", weight: 0.8, fillColor: s ? SYS[s.system].color : "#ddd", fillOpacity: 0.75 }; },
      onEachFeature: (f, l) => { const s = Object.values(STATES).find((x) => x.fips === f.id); if (!s) return; l.bindTooltip(`<b>${esc(s.name)}</b><br>${esc(s.systemLabel)} &middot; ${s.counties} counties${s.withData ? `<br>${s.withData} with parcel data` : ""}`, { sticky: true }); l.on("mouseover", () => l.setStyle({ fillOpacity: 1, weight: 1.5 })); l.on("mouseout", () => l.setStyle({ fillOpacity: 0.75, weight: 0.8 })); l.on("click", () => go(s.abbr.toLowerCase())); } }).addTo(m);
    m.fitBounds(layer.getBounds(), { padding: [6, 6] });

    const stateLevel = (k) => { const sts = REG.states.filter((s) => s.system === k).sort((a, b) => b.counties - a.counties); return { name: SYS[k].label, title: `Counties per state (${SYS[k].label.toLowerCase()})`, labels: sts.map((s) => s.abbr), values: sts.map((s) => s.counties), colors: SYS[k].color, series: "Counties", hint: (i) => `in ${sts[i].name}`, click: (i) => { go(sts[i].abbr.toLowerCase()); } }; };
    new Drill("nSys", "nSysCrumb", { name: "All systems", title: "Counties by sale system", labels: sysRows.map((r) => SYS[r.k].label), values: sysRows.map((r) => r.counties), colors: sysRows.map((r) => SYS[r.k].color), series: "Counties", click: (i) => stateLevel(sysRows[i].k) });
    const byState = REG.states.filter((s) => s.parcels > 0).sort((a, b) => b.parcels - a.parcels);
    const countyLevel = (st) => { const cs = (BY_STATE[st.abbr] || []).filter((c) => c.data && c.data.parcels).sort((a, b) => b.data.parcels - a.data.parcels).slice(0, 30); return { name: st.name, title: `Parcels on file by county in ${st.name}${cs.length === 30 ? " (top 30)" : ""}`, labels: cs.map((c) => c.name), values: cs.map((c) => c.data.parcels), horizontal: true, series: "Parcels", click: (i) => { go(countyHref(cs[i]).slice(1)); } }; };
    new Drill("nRich", "nRichCrumb", { name: "All states", title: "Parcels on file by state", labels: byState.map((s) => s.name), values: byState.map((s) => s.parcels), horizontal: true, series: "Parcels", hint: (i) => `in ${byState[i].withData} counties`, click: (i) => countyLevel(byState[i]) });
    const months = {}; for (const c of posted) { const k = c.nextSale.slice(0, 7); (months[k] = months[k] || []).push(c); }
    const mk = Object.keys(months).sort(), mlabel = (k) => new Date(k + "-15T12:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" });
    new Drill("nCal", "nCalCrumb", { name: "All months", title: "Counties with a posted sale, by month", labels: mk.map(mlabel), values: mk.map((k) => months[k].length), series: "Counties", colors: "#8e5ad6",
      click: (i) => { const cs = months[mk[i]].sort((a, b) => (b.data?.parcels || 0) - (a.data?.parcels || 0)).slice(0, 30); return { name: mlabel(mk[i]), title: `Parcels listed for sale in ${mlabel(mk[i])}`, labels: cs.map((c) => `${c.name}, ${c.state}`), values: cs.map((c) => c.data?.parcels || 0), horizontal: true, series: "Parcels", colors: "#8e5ad6", hint: (j) => fmtDate(cs[j].nextSale), click: (j) => { go(countyHref(cs[j]).slice(1)); } }; } });

    const upcoming = posted.map((c) => ({ c, date: c.nextSale, name: c.label, state: c.state, parcels: c.data ? c.data.parcels : null })).sort((a, b) => a.date.localeCompare(b.date));
    makeTable("nUpcoming", [
      { key: "date", label: "Date", val: (r) => r.date, html: (r) => fmtDate(r.date) }, { key: "name", label: "County", html: (r) => `<a href="${countyHref(r.c)}">${esc(r.name)}</a>` }, { key: "state", label: "State" },
      { key: "parcels", label: "Parcels on file", num: true, html: (r) => int(r.parcels) }, { key: "link", label: "Links", cls: "links", html: (r) => linkCell(r.c) },
    ], upcoming, { sortKey: "date", sortDir: "asc", rowClass: () => "row", onRow: (r) => go(countyHref(r.c).slice(1)), empty: "No posted dates on file" });
    const stat = REG.states.filter((s) => s.nextStatutory || s.nextStatutoryLabel).map((s) => ({ s, date: s.nextStatutory, label: s.nextStatutory ? fmtDate(s.nextStatutory) : s.nextStatutoryLabel, timing: s.sale_timing })).sort((a, b) => (a.date || "9999").localeCompare(b.date || "9999") || a.s.name.localeCompare(b.s.name));
    $("nStatutory").innerHTML = `<thead><tr><th>State</th><th>Next sale</th><th>Schedule</th></tr></thead><tbody>${stat.map((r) => `<tr class="row" data-s="${r.s.abbr}"><td><a href="#${r.s.abbr.toLowerCase()}">${esc(r.s.name)}</a></td><td>${r.date ? `<b>${esc(r.label)}</b>` : `<span class="pill window">${esc(r.label)}</span>`}</td><td class="wrap small">${esc(r.timing)}</td></tr>`).join("")}</tbody>`;
    $("nStatutory").querySelectorAll("tr.row").forEach((tr) => tr.onclick = () => go(tr.dataset.s.toLowerCase()));
    makeTable("nStates", [
      { key: "name", label: "State", html: (r) => `<a href="#${r.abbr.toLowerCase()}">${esc(r.name)}</a>` }, { key: "system", label: "Sale type", html: (r) => sysPill(r.system) },
      { key: "conducted_by", label: "Who holds the sale", wrap: true }, { key: "redemption", label: "Redemption", wrap: true }, { key: "rate", label: "Rate or penalty", wrap: true },
      { key: "next", label: "Next sale", val: (r) => r.nextStatutory || r.nextStatutoryLabel || "", html: (r) => r.nextStatutory ? fmtDate(r.nextStatutory) : esc(r.nextStatutoryLabel || "As scheduled") },
      { key: "counties", label: "Counties", num: true }, { key: "withData", label: "With data", num: true },
    ], REG.states, { sortKey: "name", sortDir: "asc", rowClass: () => "row", onRow: (r) => go(r.abbr.toLowerCase()) });
  }

  // ---------- STATE ----------
  function showState(abbr) {
    const s = STATES[abbr], list = BY_STATE[abbr] || [];
    setView("viewState", abbr, "");
    $("sName").textContent = s.name;
    $("sSub").textContent = `${int(s.counties)} ${s.unit.toLowerCase().includes("county") ? "counties" : s.unit.toLowerCase().replace(/ \(.*\)/, "") + "s"} · ${s.withData ? `${s.withData} with parcel data on file · ` : ""}population ${int(s.pop)}`;
    $("sPill").innerHTML = sysPill(s.system, true);
    $("sSummary").innerHTML = `<b>${esc(s.summary)}</b>`;
    $("sInfo").innerHTML = rulesHtml(s, true) + `<div class="wide"><b>If the owner redeems (on $10,000 paid at the sale)</b>${T.redemptionTable(s, 10000)}</div>`;
    $("sActions").innerHTML = `<button type="button" id="sIcs">Add this state's sale dates to calendar</button><a class="btnlink" href="analyzer.html#state=${abbr}">Open ${esc(s.name)} in the analyzer</a>`;
    $("sIcs").onclick = () => { const evs = list.filter((c) => c.nextSale).map((c) => ({ date: c.nextSale, title: `${c.label}, ${c.state}: ${c.nextSaleKind === "posted" ? "tax sale" : "statutory sale date"}`, desc: c.schedule || s.sale_timing, url: `${location.origin}${location.pathname}${countyHref(c)}`, uid: `${c.fips}-${c.nextSale}` })); if (!evs.length) { alert("No sale dates on file."); return; } downloadText(`${abbr.toLowerCase()}-tax-sales.ics`, ics(evs.slice(0, 400), `${s.name} tax sales`), "text/calendar"); };
    $("sCountiesTitle").textContent = `${s.unit.includes("County") ? "Counties" : s.unit.replace(/ \(.*\)/, "") + "s"} In ${s.name}`;

    const m = simpleMap("sMap");
    const feats = topojson.feature(TOPO, TOPO.objects.counties).features.filter((f) => String(f.id).startsWith(s.fips));
    const style = (c) => ({ color: "#000", weight: 0.7, fillOpacity: 0.95, fillColor: c && c.data ? "#2a78d6" : c && c.taxsale ? "#bcd3f3" : "#eef1f5" });
    const layer = L.geoJSON({ type: "FeatureCollection", features: feats }, { coordsToLatLng: projector(stateProjection(feats)), style: (f) => style(BY_FIPS[f.id]),
      onEachFeature: (f, l) => { const c = BY_FIPS[f.id]; if (!c) return; l.bindTooltip(`<b>${esc(c.label)}</b>${c.data ? `<br>${int(c.data.parcels)} parcels on file` : ""}${nextSaleText(c) ? `<br>Next sale: ${esc(nextSaleText(c))}` : ""}`, { sticky: true }); l.on("mouseover", () => l.setStyle({ weight: 2 })); l.on("mouseout", () => l.setStyle({ weight: 0.7 })); l.on("click", () => go(countyHref(c).slice(1))); } }).addTo(m);
    if (feats.length) m.fitBounds(layer.getBounds(), { padding: [8, 8] });

    const priced = list.filter((c) => c.data && c.data.withPrice > 0).sort((a, b) => b.data.withPrice - a.data.withPrice).slice(0, 30);
    $("sPrices").hidden = !priced.length;
    if (priced.length) new Drill("sPriceChart", "sPriceCrumb", { name: "Counties with prices", title: "Parcels with a published winning bid, by county", labels: priced.map((c) => c.name), values: priced.map((c) => c.data.withPrice), horizontal: true, series: "Priced parcels", hint: (i) => `· ${int(priced[i].data.sold)} sold of ${int(priced[i].data.parcels)}`, click: (i) => { go(countyHref(priced[i]).slice(1)); } });

    const popTier = (p) => p == null ? "Unknown" : p < 10000 ? "Under 10k" : p < 50000 ? "10k to 50k" : p < 250000 ? "50k to 250k" : p < 1000000 ? "250k to 1M" : "1M and up";
    const mlabelOf = (d) => new Date(d.slice(0, 7) + "-15T12:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" });
    const groupers = {
      status: { title: "Counties by data on file", key: (c) => c.data ? "Parcel data on file" : c.taxsale ? "Tax sale page known" : "Official site and search links", order: ["Parcel data on file", "Tax sale page known", "Official site and search links"], colors: ["#2a78d6", "#bcd3f3", "#c9d4e5"] },
      month: { title: "Counties by next sale month", key: (c) => c.nextSale ? mlabelOf(c.nextSale) : (c.nextSaleLabel || "No date on file") },
      pop: { title: "Counties by population tier", key: (c) => popTier(c.pop), order: ["Under 10k", "10k to 50k", "50k to 250k", "250k to 1M", "1M and up", "Unknown"] },
      run: { title: "Counties by who holds the sale", key: (c) => shortRun(c) },
      coverage: { title: "Counties by coverage (rules, site, sale page, data, photos)", key: (c) => `${coverage(c)} of 5`, order: ["5 of 5", "4 of 5", "3 of 5", "2 of 5", "1 of 5"] },
    };
    const drawGroup = () => {
      const g = groupers[$("sGroup").value], groups = {};
      for (const c of list) { const k = g.key(c); (groups[k] = groups[k] || []).push(c); }
      let keys = g.order ? g.order.filter((k) => groups[k]) : Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
      if ($("sGroup").value === "month") keys = Object.keys(groups).sort((a, b) => (groups[a][0].nextSale || "9999").localeCompare(groups[b][0].nextSale || "9999"));
      new Drill("sChart", "sChartCrumb", { name: "All counties", title: g.title, labels: keys, values: keys.map((k) => groups[k].length), colors: g.colors || "#2a78d6", series: "Counties",
        click: (i) => { const cs = groups[keys[i]].sort((a, b) => (b.pop || 0) - (a.pop || 0)).slice(0, 40); return { name: keys[i], title: `${keys[i]}: population by county${cs.length === 40 ? " (top 40)" : ""}`, labels: cs.map((c) => c.name), values: cs.map((c) => c.pop || 0), horizontal: true, series: "Population", hint: (j) => cs[j].data ? `· ${int(cs[j].data.parcels)} parcels on file` : "", click: (j) => { go(countyHref(cs[j]).slice(1)); } }; } });
    };
    $("sGroup").onchange = drawGroup; drawGroup();

    const cols = [
      { key: "label", label: s.unit.includes("County") ? "County" : s.unit.replace(/ \(.*\)/, ""), html: (c) => `<a href="${countyHref(c)}">${esc(c.label)}</a>` },
      { key: "coverage", label: "Coverage", num: true, val: coverage, html: coverageHtml },
      { key: "pop", label: "Population", num: true, html: (c) => int(c.pop) },
      { key: "next", label: "Next sale", val: (c) => c.nextSale || (c.nextSaleLabel ? "9999-" + c.nextSaleLabel : null), html: (c) => nextSaleText(c) ? `${esc(nextSaleText(c))} <span class="pill ${c.nextSaleKind}">${nextSaleKind(c)}</span>` : "" },
      { key: "auctions", label: "Auctions", num: true, val: (c) => c.data ? c.data.auctions : null, html: (c) => c.data ? int(c.data.auctions) : "" },
      { key: "parcels", label: "Parcels", num: true, val: (c) => c.data ? c.data.parcels : null, html: (c) => c.data ? int(c.data.parcels) : "" },
      { key: "run", label: "Who holds the sale", val: shortRun },
      { key: "links", label: "Links", cls: "links", html: linkCell, csv: (c) => c.taxsale || c.site || "" },
    ];
    const draw = () => { const q = $("sFilter").value.trim().toLowerCase(); const rows = q ? list.filter((c) => c.label.toLowerCase().includes(q) || whoRuns(c).toLowerCase().includes(q)) : list; makeTable("sTable", cols, rows, { sortKey: "label", sortDir: "asc", rowClass: () => "row", onRow: (c) => go(countyHref(c).slice(1)) }); };
    $("sFilter").value = ""; $("sFilter").oninput = draw; draw();
    $("sCsv").onclick = () => downloadCsv(`${slug(s.name)}-counties.csv`, [{ key: "fips", label: "FIPS" }, { key: "label", label: "County" }, { key: "state", label: "State" }, { key: "pop", label: "Population" }, { key: "next", label: "Next sale", val: (c) => c.nextSale || c.nextSaleLabel || "" }, { key: "nextSaleKind", label: "Next sale basis" }, { key: "run", label: "Who holds the sale", val: whoRuns }, { key: "taxsale", label: "Tax sale page" }, { key: "sheriffSale", label: "Sheriff sale page" }, { key: "assessor", label: "Assessor page" }, { key: "site", label: "Official site" }, { key: "parcels", label: "Parcels on file", val: (c) => c.data ? c.data.parcels : "" }, { key: "coverage", label: "Coverage (of 5)", val: coverage }, { key: "lat", label: "Latitude" }, { key: "lon", label: "Longitude" }], list);
  }

  // ---------- COUNTY ----------
  function showCounty(c) {
    setView("viewCounty", c.state, c.fips);
    T.county.show(c, c.st, INDEX, COUNTY_CACHE, { nextSaleText, nextSaleKind, rulesHtml });
  }

  // ---------- SEARCH: counties ----------
  function parseQuery(q) { const terms = { words: [], fields: {} }; for (const tok of q.match(/"[^"]+"|\S+/g) || []) { const t = tok.replace(/"/g, ""); const m = t.match(/^([a-z]+)(:|>=|<=|>|<|=)(.+)$/i); if (m) terms.fields[m[1].toLowerCase()] = { op: m[2], v: m[3].toLowerCase() }; else terms.words.push(t.toLowerCase()); } return terms; }
  const num = (v) => { const m = String(v).replace(/[$,]/g, "").match(/^([\d.]+)([km]?)$/); if (!m) return NaN; return +m[1] * (m[2] === "k" ? 1e3 : m[2] === "m" ? 1e6 : 1); };
  const sysKey = (v) => Object.keys(SYS).find((k) => k.startsWith(v) || SYS[k].label.toLowerCase().includes(v));
  function showResults(title, note) { for (const v of ["viewNation", "viewState", "viewCounty"]) $(v).hidden = true; $("results").hidden = false; $("resTitle").textContent = title; $("resNote").textContent = note || ""; $("selState").value = "us"; fillCountyDropdown(null); window.scrollTo({ top: 0 }); }
  function runSearch(q) {
    const t = parseQuery(q);
    const rows = COUNTIES.filter((c) => {
      for (const [k, { op, v }] of Object.entries(t.fields)) {
        if (k === "state" && !(c.state.toLowerCase() === v || c.st.name.toLowerCase().includes(v))) return false;
        if (k === "type" && c.st.system !== sysKey(v)) return false;
        if (k === "data" && ((v.startsWith("y") && !c.data) || (v.startsWith("n") && c.data))) return false;
        if (k === "run" && !whoRuns(c).toLowerCase().includes(v)) return false;
        if (k === "platform" && !((c.platform || "") + " " + (c.st.platforms || []).join(" ")).toLowerCase().includes(v)) return false;
        if (k === "unit" && !c.unit.toLowerCase().includes(v)) return false;
        if (k === "next") { if (!c.nextSale || c.nextSale > v + (v.length === 7 ? "-31" : "")) return false; }
        if (k === "pop") { const n = num(v); if (isNaN(n) || c.pop == null) return false; if (op === ">" && !(c.pop > n)) return false; if (op === "<" && !(c.pop < n)) return false; if (op === ">=" && !(c.pop >= n)) return false; if (op === "<=" && !(c.pop <= n)) return false; }
        if (k === "fips" && !c.fips.startsWith(v)) return false;
        if (k === "coverage" && !(coverage(c) >= +v)) return false;
      }
      const hay = `${c.label} ${c.st.name} ${c.state} ${whoRuns(c)} ${SYS[c.st.system].label}`.toLowerCase();
      return t.words.every((w) => hay.includes(w));
    });
    showResults(`Search Results: ${int(rows.length)} counties`, rows.length > 1500 ? `Showing the 1,500 most populous of ${int(rows.length)} matches; narrow the search to see the rest.` : "");
    const tf = t.fields.type; $("selType").value = tf ? (sysKey(tf.v) || "") : "";
    const cols = [
      { key: "label", label: "County", html: (c) => `<a href="${countyHref(c)}">${esc(c.label)}</a>` }, { key: "state", label: "State", val: (c) => c.st.name },
      { key: "system", label: "Sale type", val: (c) => c.st.system, html: (c) => sysPill(c.st.system) }, { key: "coverage", label: "Coverage", num: true, val: coverage, html: coverageHtml },
      { key: "run", label: "Who holds the sale", val: shortRun },
      { key: "next", label: "Next sale", val: (c) => c.nextSale || null, html: (c) => nextSaleText(c) ? `${esc(nextSaleText(c))} <span class="pill ${c.nextSaleKind}">${nextSaleKind(c)}</span>` : "" },
      { key: "parcels", label: "Parcels on file", num: true, val: (c) => c.data ? c.data.parcels : null, html: (c) => c.data ? int(c.data.parcels) : "" },
      { key: "pop", label: "Population", num: true, html: (c) => int(c.pop) }, { key: "links", label: "Links", cls: "links", html: linkCell, csv: (c) => c.taxsale || c.site || "" },
    ];
    makeTable("resTable", cols, rows.slice(0, 1500), { sortKey: "pop", sortDir: "desc", rowClass: () => "row", onRow: (c) => go(countyHref(c).slice(1)) });
    $("resCsv").onclick = () => downloadCsv("tax-sale-county-search.csv", [{ key: "fips", label: "FIPS" }, ...cols.filter((x) => x.key !== "links"), { key: "taxsale", label: "Tax sale page" }, { key: "sheriffSale", label: "Sheriff sale page" }, { key: "site", label: "Official site" }], rows);
  }

  // ---------- SEARCH: parcels (every parcel on file, from the master file) ----------
  const PF = { county: (p) => p.county, state: (p) => p.state + " " + p.stateName, parcel: (p) => `${p.parcel} ${String(p.parcel || "").replace(/[^0-9A-Z]/gi, "")} ${p.lot || ""} ${p.caseNo || ""}`, owner: (p) => p.owner, address: (p) => p.fullAddress || p.address, area: (p) => p.area, type: (p) => p.type, buyer: (p) => p.buyer, status: (p) => p.status, kind: (p) => p.saleKind, date: (p) => p.auctionDate + " " + fmtDate(p.auctionDate, { month: "long" }), source: (p) => p.source, system: (p) => p.system };
  const PN = { year: (p) => +String(p.auctionDate || "").slice(0, 4), owed: (p) => p.minBid, won: (p) => p.winningBid, bid: (p) => p.winningBid, multiple: (p) => p.multiple, excess: (p) => p.excess, value: (p) => p.value, score: (p) => p.dealScore, acres: (p) => p.acres, sqft: (p) => p.sqft, age: (p) => p.yearBuilt ? NOWYEAR - p.yearBuilt : null, built: (p) => p.yearBuilt, redemption: (p) => p.redemptionMonths };
  function parseP(q) { const terms = []; (q.match(/"[^"]+"|\S+/g) || []).forEach((t) => { t = t.replace(/"/g, ""); let m = t.match(/^(\w+)\s*(>=|<=|>|<|=)\s*\$?([\d.,]+)(k|m)?$/i); if (m && PN[m[1].toLowerCase()]) { let v = parseFloat(m[3].replace(/,/g, "")); if (m[4]) v *= m[4].toLowerCase() === "k" ? 1e3 : 1e6; return terms.push({ num: m[1].toLowerCase(), op: m[2], v }); } m = t.match(/^(\w+):(.+)$/); if (m && PF[m[1].toLowerCase()]) return terms.push({ f: m[1].toLowerCase(), s: m[2].toLowerCase() }); if (m && PN[m[1].toLowerCase()]) return terms.push({ num: m[1].toLowerCase(), op: "=", v: parseFloat(m[2]) }); terms.push({ s: t.toLowerCase() }); }); return terms; }
  const hay = (p) => p._h || (p._h = [p.county, p.state, p.stateName, p.parcel, String(p.parcel || "").replace(/[^0-9A-Z]/gi, ""), p.lot, p.caseNo, p.owner, p.address, p.fullAddress, p.area, p.type, p.buyer, p.status, p.saleKind, p.auctionDate, fmtDate(p.auctionDate, { month: "long" }), p.desc].join(" ").toLowerCase());
  const matchesP = (p, ts) => ts.every((t) => { if (t.num) { const v = PN[t.num](p); if (v == null || isNaN(v)) return false; return t.op === ">" ? v > t.v : t.op === "<" ? v < t.v : t.op === ">=" ? v >= t.v : t.op === "<=" ? v <= t.v : Math.abs(v - t.v) < 0.5; } if (t.f) return String(PF[t.f](p) || "").toLowerCase().includes(t.s); return hay(p).includes(t.s); });
  async function loadMaster() {
    if (MASTER) return MASTER;
    MASTER = (await loadMasterShards()).map((o) => { o.stateName = STATES[o.state]?.name || ""; return o; });
    return MASTER;
  }
  // the master parcel file is split by state under data/master/ (GitHub refuses files over 100 MB); index.json lists the shards
  async function loadMasterShards() {
    const idx = await fetch("data/master/index.json", { cache: "no-cache" }).then((r) => r.json());
    const shards = await Promise.all(idx.states.map((s) => fetch(`data/master/${s.abbr}.json`, { cache: "no-cache" }).then((r) => r.json())));
    const out = [];
    for (const m of shards) for (const r of m.rows) { const o = {}; m.columns.forEach((c, i) => { o[c] = r[i]; }); out.push(o); }
    return out;
  }
  async function downloadMasterCsv(a) {
    const label = a.textContent; a.textContent = "Joining every state's CSV…";
    try {
      const idx = await fetch("data/master/index.json", { cache: "no-cache" }).then((r) => r.json());
      const parts = await Promise.all(idx.states.map((s) => fetch(`data/master/${s.abbr}.csv`, { cache: "no-cache" }).then((r) => r.text())));
      const body = parts.map((t, i) => i ? t.slice(t.indexOf("\n") + 1) : t).join("");
      const url = URL.createObjectURL(new Blob([body], { type: "text/csv" }));
      const link = Object.assign(document.createElement("a"), { href: url, download: "master_parcels.csv" });
      document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { alert("The master CSV could not be assembled: " + e.message); }
    a.textContent = label;
  }
  if ($("masterCsv")) $("masterCsv").onclick = (e) => { e.preventDefault(); downloadMasterCsv(e.currentTarget); };
  async function runParcelSearch(q) {
    showResults("Searching every parcel on file…");
    let all; try { all = await loadMaster(); } catch (e) { $("resTitle").textContent = "The master parcel file could not be loaded."; return; }
    const ts = parseP(q);
    const rows = all.filter((p) => matchesP(p, ts)).sort((a, b) => (b.dealScore || 0) - (a.dealScore || 0));
    showResults(`Parcel Search: ${int(rows.length)} parcels`, rows.length > 1000 ? `Showing the 1,000 highest-scoring of ${int(rows.length)} matches; narrow the search or download everything.` : "");
    const href = (p) => { const c = BY_FIPS[p.fips]; return c ? `${countyHref(c)}?parcel=${encodeURIComponent(String(p.parcel || p.lot || p.caseNo || "").toUpperCase())}` : "#"; };
    const cols = [
      { key: "dealScore", label: "Score", num: true, html: (p) => `<span class="pill r-${(p.dealRating || "weak").toLowerCase()}">${p.dealScore} ${esc(p.dealRating || "")}</span>` },
      { key: "parcel", label: "Parcel", html: (p) => `<a href="${href(p)}"><b>${esc(p.parcel || p.lot || p.caseNo || "")}</b></a>` },
      { key: "county", label: "County", html: (p) => `${esc(p.county)}, ${esc(p.state)}` }, { key: "address", label: "Address", wrap: true, val: (p) => p.address || p.fullAddress || "" },
      { key: "type", label: "Type", wrap: true }, { key: "auctionDate", label: "Sale", html: (p) => `${fmtDate(p.auctionDate)}${p.auctionStatus === "upcoming" ? ' <span class="pill posted">Upcoming</span>' : ""}` }, { key: "status", label: "Status" },
      { key: "minBid", label: "Owed", num: true, html: (p) => money(p.minBid) }, { key: "winningBid", label: "Won", num: true, html: (p) => money(p.winningBid) }, { key: "multiple", label: "Multiple", num: true, html: (p) => p.multiple ? p.multiple.toFixed(1) + "x" : "" },
      { key: "excess", label: "Excess", num: true, html: (p) => money(p.excess) }, { key: "value", label: "County value", num: true, html: (p) => money(p.value) }, { key: "buyer", label: "Buyer", wrap: true },
    ];
    makeTable("resTable", cols, rows.slice(0, 1000), { sortKey: "dealScore", sortDir: "desc", rowClass: () => "row", onRow: (p) => go(href(p).slice(1)) });
    $("resCsv").onclick = () => downloadCsv("tax-sale-parcel-search.csv", [{ key: "fips", label: "FIPS" }, ...cols, { key: "lat", label: "Latitude" }, { key: "lon", label: "Longitude" }, { key: "photo", label: "Photo" }, { key: "listing", label: "Listing" }, { key: "sourceDoc", label: "Source document" }], rows);
  }
  const submitSearch = () => { const q = $("gSearch").value.trim(); if (!q) { location.hash = ""; return; } location.hash = "q=" + ($("searchMode").value === "parcels" ? "parcels:" : "") + q; };
  $("gSearch").addEventListener("keydown", (e) => { if (e.key === "Enter") submitSearch(); });
  $("searchMode").addEventListener("change", () => { if ($("gSearch").value.trim()) submitSearch(); });
  $("gSearch").addEventListener("input", () => { if (!$("gSearch").value.trim() && location.hash.startsWith("#q=")) location.hash = ""; });
  document.querySelectorAll(".examples button[data-q]").forEach((b) => b.onclick = () => { $("gSearch").value = b.dataset.q; $("searchMode").value = b.dataset.mode || "counties"; submitSearch(); });
  $("searchHelpBtn").onclick = () => { $("searchHelp").hidden = !$("searchHelp").hidden; };
  $("resClear").onclick = () => { $("gSearch").value = ""; location.hash = ""; };

  load().catch((e) => { $("freshness").textContent = "The data could not be loaded: " + e.message; console.error(e); });
})();
