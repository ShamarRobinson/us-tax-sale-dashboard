/* US Tax Sale Tracker: plain JS over data/registry.json (+ data/counties/{fips}.json on demand). */
(function () {
  "use strict";

  const SYS = {
    deed: { label: "Tax deed", color: "#2a78d6" },
    lien: { label: "Tax lien", color: "#eb6834" },
    redeemable: { label: "Redeemable deed", color: "#159c6c" },
    hybrid: { label: "Hybrid (lien, then deed)", color: "#8e5ad6" },
  };
  const TODAY = new Date().toISOString().slice(0, 10);
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (v) => (v == null || isNaN(v)) ? "" : "$" + Math.round(v).toLocaleString("en-US");
  const int = (v) => (v == null) ? "" : Number(v).toLocaleString("en-US");
  const fmtDate = (s) => { if (!s) return ""; const d = new Date(s + "T12:00:00"); return isNaN(d) ? s : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); };
  const slug = (s) => String(s).toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const searchUrl = (q) => "https://duckduckgo.com/?q=" + encodeURIComponent(q);
  const median = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const avg = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;

  let REG = null, STATES = {}, COUNTIES = [], BY_FIPS = {}, BY_STATE = {}, TOPO = null, INDEX = null;
  const COUNTY_CACHE = {};
  const maps = {};
  const charts = {};

  // ---------- loading ----------
  async function load() {
    const [reg, topo, idx] = await Promise.all([
      fetch("data/registry.json").then((r) => r.json()),
      fetch("ref/us-counties-10m.json").then((r) => r.json()),
      fetch("data/index.json").then((r) => r.json()).catch(() => null),
    ]);
    REG = reg; TOPO = topo; INDEX = idx;
    for (const s of reg.states) STATES[s.abbr] = s;
    COUNTIES = reg.counties;
    for (const c of COUNTIES) {
      c.st = STATES[c.state];
      c.slug = slug(c.name);
      BY_FIPS[c.fips] = c;
      (BY_STATE[c.state] = BY_STATE[c.state] || []).push(c);
    }
    renderFreshness();
    renderTabs();
    renderFooter();
    route();
  }

  function renderFreshness() {
    const gen = REG.generated ? new Date(REG.generated) : null;
    const srcs = INDEX && INDEX.sources ? Object.values(INDEX.sources) : [];
    const ok = srcs.filter((s) => s.ok).length;
    $("freshness").innerHTML = `<span class="dotlive"></span><b>Data generated ${gen ? gen.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "unknown"}</b> &middot; ${srcs.length ? `${ok} of ${srcs.length} sources answered` : "registry only"} &middot; refreshed on the 1st of every month`;
  }

  function renderTabs() {
    const sel = $("selState");
    sel.innerHTML = `<option value="us">United States (all)</option>` + REG.states.map((s) => `<option value="${s.abbr}">${esc(s.name)}${s.withData ? ` (${s.withData} with data)` : ""}</option>`).join("");
    sel.onchange = () => { location.hash = sel.value === "us" ? "" : sel.value.toLowerCase(); };
    $("selCounty").onchange = () => { const v = $("selCounty").value; if (v) location.hash = countyHref(BY_FIPS[v]).slice(1); };
    $("selType").onchange = () => { const v = $("selType").value; $("selShow").value = ""; location.hash = v ? "q=type:" + v : ""; };
    $("selShow").onchange = () => {
      let v = $("selShow").value; $("selType").value = "";
      if (v === "next:__soon__") { const d = new Date(); d.setDate(d.getDate() + 60); v = "next:" + d.toISOString().slice(0, 10); }
      location.hash = v ? "q=" + v : "";
    };
  }

  function fillCountyDropdown(abbr, fips) {
    const sel = $("selCounty");
    const list = BY_STATE[abbr] || [];
    if (!list.length) { sel.disabled = true; sel.innerHTML = `<option value="">Pick a state first</option>`; return; }
    sel.disabled = false;
    sel.innerHTML = `<option value="">All of ${esc(STATES[abbr].name)}</option>` + list.map((c) => `<option value="${c.fips}">${esc(c.label)}${c.data ? ` (${int(c.data.parcels)} parcels)` : ""}</option>`).join("");
    sel.value = fips || "";
  }

  function renderFooter() {
    const srcs = INDEX && INDEX.sources ? Object.values(INDEX.sources) : [];
    $("foot").innerHTML = `County list, boundaries, land area and 2024 population come from the <a href="https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html" target="_blank" rel="noopener">U.S. Census Bureau</a>; official county websites from <a href="https://www.wikidata.org/" target="_blank" rel="noopener">Wikidata</a>. State rules are summarized from each state's statutes and are for orientation only, not legal advice. Parcel-level data comes from: ${srcs.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a> (${s.ok ? `${s.counties} counties` : "unavailable at the last check"})`).join("; ")}. Lists change up to the day of the sale; always confirm with the county. Not affiliated with any government. <a href="https://github.com/ShamarRobinson/us-tax-sale-dashboard" target="_blank" rel="noopener">Source on GitHub</a>.`;
  }

  // ---------- routing ----------
  function route() {
    const h = decodeURIComponent(location.hash.replace(/^#/, "")).trim();
    if (h.startsWith("q=")) { $("gSearch").value = h.slice(2); runSearch(h.slice(2)); return; }
    $("results").hidden = true;
    if (!h || h === "us") { showNation(); return; }
    const [st, rest] = h.split("/");
    const abbr = st.toUpperCase();
    if (st === "c" && rest && BY_FIPS[rest]) { showCounty(BY_FIPS[rest]); return; }
    if (!STATES[abbr]) { showNation(); return; }
    if (rest) {
      const c = (BY_STATE[abbr] || []).find((x) => x.slug === rest || x.fips === rest);
      if (c) { showCounty(c); return; }
    }
    showState(abbr);
  }
  window.addEventListener("hashchange", route);

  function setView(name, tab, fips) {
    for (const v of ["viewNation", "viewState", "viewCounty"]) $(v).hidden = v !== name;
    $("selState").value = tab;
    fillCountyDropdown(tab === "us" ? null : tab, fips);
    $("selType").value = ""; $("selShow").value = "";
    window.scrollTo({ top: 0 });
  }

  // ---------- drill-down charts ----------
  // A level is { name, title, labels, values, colors?, horizontal?, money?, click(i) -> next level | undefined }.
  class Drill {
    constructor(canvasId, crumbId, root) { this.id = canvasId; this.crumb = $(crumbId); this.stack = [root]; this.render(); }
    push(level) { this.stack.push(level); this.render(); }
    pop(i) { this.stack.length = i + 1; this.render(); }
    render() {
      const lv = this.stack[this.stack.length - 1];
      this.crumb.innerHTML = this.stack.map((l, i) => i < this.stack.length - 1 ? `<button type="button" data-i="${i}">${esc(l.name)}</button><span class="sep">&rsaquo;</span>` : `<span class="here">${esc(l.name)}</span>`).join("");
      this.crumb.querySelectorAll("button").forEach((b) => b.onclick = () => this.pop(+b.dataset.i));
      const fmt = lv.money ? money : int;
      const box = $(this.id).parentElement;
      box.style.height = lv.horizontal ? Math.max(box.classList.contains("short") ? 230 : 280, lv.labels.length * 22 + 70) + "px" : "";
      chart(this.id, {
        type: "bar",
        data: { labels: lv.labels, datasets: [{ label: lv.series || "", data: lv.values, backgroundColor: lv.colors || "#2a78d6", borderRadius: 4, maxBarThickness: 34 }, ...(lv.values2 ? [{ label: lv.series2, data: lv.values2, backgroundColor: "#eb6834", borderRadius: 4, maxBarThickness: 34 }] : [])] },
        options: {
          indexAxis: lv.horizontal ? "y" : "x", maintainAspectRatio: false,
          onClick: (e, els) => { if (!els.length) return; const i = els[0].index; setTimeout(() => { const next = lv.click && lv.click(i); if (next) this.push(next); }, 0); },
          onHover: (e, els) => { e.native.target.style.cursor = els.length && lv.click ? "pointer" : "default"; },
          plugins: { legend: { display: !!lv.values2 }, title: { display: true, text: lv.title }, tooltip: { callbacks: { label: (c) => `${c.dataset.label ? c.dataset.label + ": " : ""}${fmt(c.raw)}${lv.hint ? " " + lv.hint(c.dataIndex) : ""}` } } },
          scales: { [lv.horizontal ? "x" : "y"]: { beginAtZero: true, grid: { color: "#ebe9e4" }, ticks: { callback: (v) => fmt(v), precision: 0 } }, [lv.horizontal ? "y" : "x"]: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: lv.horizontal ? 0 : 45 } } },
        },
      });
    }
  }
  const go = (hash) => { location.hash = hash; };

  // ---------- helpers for maps ----------
  function simpleMap(id) {
    if (maps[id]) { maps[id].remove(); }
    const m = L.map(id, { crs: L.CRS.Simple, attributionControl: false, zoomSnap: 0.25, minZoom: -3, zoomControl: true, scrollWheelZoom: false });
    maps[id] = m;
    return m;
  }
  // The TopoJSON is plain longitude/latitude; project it with Albers USA (insets for Alaska and Hawaii) and show the
  // result on a tile-less Leaflet map. Puerto Rico falls outside Albers USA, so it gets its own Mercator projection.
  const ALBERS = d3.geoAlbersUsa().scale(1300).translate([487.5, 305]);
  const projector = (proj) => (coords) => { const p = proj(coords); return p ? L.latLng(-p[1], p[0]) : L.latLng(0, 0); };
  const projects = (proj, feature) => { const c = d3.geoCentroid(feature); return !!proj(c); };
  const stateProjection = (features) => {
    if (features.every((f) => projects(ALBERS, f))) return ALBERS;
    const fc = { type: "FeatureCollection", features };
    return d3.geoMercator().fitSize([975, 610], fc);
  };
  function tileMap(id) {
    if (maps[id]) { maps[id].remove(); }
    const m = L.map(id, { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(m);
    maps[id] = m;
    return m;
  }
  function chart(id, cfg) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart($(id), cfg);
  }
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.color = "#52514e";

  // ---------- sortable tables ----------
  function makeTable(tableId, cols, rows, opts = {}) {
    const t = $(tableId);
    const state = t._sort || (t._sort = { key: opts.sortKey || null, dir: opts.sortDir || "desc" });
    const sorted = [...rows];
    if (state.key) {
      const col = cols.find((c) => c.key === state.key);
      sorted.sort((a, b) => {
        let x = col.val ? col.val(a) : a[state.key], y = col.val ? col.val(b) : b[state.key];
        if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
        if (typeof x === "number" && typeof y === "number") return state.dir === "asc" ? x - y : y - x;
        x = String(x).toLowerCase(); y = String(y).toLowerCase();
        return state.dir === "asc" ? x.localeCompare(y) : y.localeCompare(x);
      });
    }
    const head = cols.map((c) => `<th class="${c.num ? "num" : ""}" data-key="${c.key}" ${state.key === c.key ? `aria-sort="${state.dir === "asc" ? "ascending" : "descending"}"` : ""}>${esc(c.label)}</th>`).join("");
    const body = sorted.map((r, i) => `<tr class="${opts.rowClass ? opts.rowClass(r) : ""}" data-i="${i}">${cols.map((c) => `<td class="${c.num ? "num" : ""}${c.wrap ? " wrap" : ""}${c.cls ? " " + c.cls : ""}">${c.html ? c.html(r) : esc(c.val ? c.val(r) : r[c.key])}</td>`).join("")}</tr>`).join("");
    t.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body || `<tr><td colspan="${cols.length}" class="muted">${esc(opts.empty || "Nothing to show")}</td></tr>`}</tbody>`;
    t._rows = sorted;
    if (t.classList.contains("sortable")) {
      t.querySelectorAll("th").forEach((th) => th.onclick = () => {
        const k = th.dataset.key;
        if (state.key === k) state.dir = state.dir === "asc" ? "desc" : "asc"; else { state.key = k; state.dir = cols.find((c) => c.key === k).num ? "desc" : "asc"; }
        makeTable(tableId, cols, rows, opts);
      });
    }
    if (opts.onRow) t.querySelectorAll("tbody tr[data-i]").forEach((tr) => tr.onclick = (e) => { if (e.target.closest("a")) return; opts.onRow(sorted[+tr.dataset.i]); });
    return sorted;
  }

  function downloadCsv(name, cols, rows) {
    const q = (v) => { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const lines = [cols.map((c) => q(c.label)).join(",")];
    for (const r of rows) lines.push(cols.map((c) => q(c.csv ? c.csv(r) : (c.val ? c.val(r) : r[c.key]))).join(","));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  // ---------- county helpers ----------
  const nextSaleText = (c) => {
    if (c.nextSale) return fmtDate(c.nextSale);
    if (c.nextSaleLabel) return c.nextSaleLabel;
    return "";
  };
  const nextSaleKind = (c) => c.nextSaleKind === "posted" ? "Posted" : c.nextSaleKind === "statutory" ? "By statute" : c.nextSaleKind === "window" ? "Season" : "";
  const sysPill = (k, big) => `<span class="pill ${k}${big ? " big" : ""}">${esc(SYS[k].label)}</span>`;
  const whoRuns = (c) => c.run || c.st.conducted_by;
  const shortRun = (c) => (c.run || c.st.conducted_by).split(/;| \(/)[0].trim();
  const countyHref = (c) => `#${c.state.toLowerCase()}/${c.slug}`;
  const linkCell = (c) => {
    const out = [];
    if (c.taxsale) out.push(`<a href="${esc(c.taxsale)}" target="_blank" rel="noopener">${c.taxsaleKind === "state" ? "State sale site" : "Tax sale page"}</a>`);
    else out.push(`<a href="${searchUrl(`${c.label} ${c.st.name} tax sale`)}" target="_blank" rel="noopener">Find sale page</a>`);
    if (c.site) out.push(`<a href="${esc(c.site)}" target="_blank" rel="noopener">Official site</a>`);
    return out.join("");
  };

  // ---------- NATION ----------
  function showNation() {
    setView("viewNation", "us");
    const withData = COUNTIES.filter((c) => c.data);
    const parcels = withData.reduce((s, c) => s + c.data.parcels, 0);
    const posted = COUNTIES.filter((c) => c.nextSaleKind === "posted");
    const withSite = COUNTIES.filter((c) => c.site).length;
    const withLink = COUNTIES.filter((c) => c.taxsale).length;
    $("nKpis").innerHTML = [
      ["Counties tracked", int(COUNTIES.length), "every county and county equivalent", true],
      ["States and territories", REG.states.length, "50 states, DC and Puerto Rico"],
      ["Counties with parcel data", int(withData.length), `${int(parcels)} parcels on file`],
      ["Posted upcoming sales", int(posted.length), "dates published by a source"],
      ["Tax sale pages linked", int(withLink), `plus ${int(withSite)} official county sites`],
    ].map(([l, v, n, hero]) => `<div class="kpi${hero ? " hero" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");

    // systems table + legend
    const sysRows = Object.keys(SYS).map((k) => {
      const sts = REG.states.filter((s) => s.system === k);
      return { k, states: sts.length, counties: sts.reduce((a, s) => a + s.counties, 0), list: sts.map((s) => s.abbr).join(", ") };
    });
    $("nSystems").innerHTML = `<thead><tr><th>System</th><th class="num">States</th><th class="num">Counties</th><th>Where</th></tr></thead><tbody>${sysRows.map((r) => `<tr><td><span class="sw" style="background:${SYS[r.k].color}"></span>${esc(SYS[r.k].label)}</td><td class="num">${r.states}</td><td class="num">${int(r.counties)}</td><td class="wrap small">${esc(r.list)}</td></tr>`).join("")}</tbody>`;
    $("nLegend").innerHTML = Object.keys(SYS).map((k) => `<span><i class="sq" style="background:${SYS[k].color};opacity:.8"></i>${esc(SYS[k].label)}</span>`).join("");

    // national map
    const m = simpleMap("nMap");
    const states = topojson.feature(TOPO, TOPO.objects.states);
    states.features = states.features.filter((f) => Object.values(STATES).some((x) => x.fips === f.id) && projects(ALBERS, f));
    const layer = L.geoJSON(states, {
      coordsToLatLng: projector(ALBERS),
      style: (f) => { const s = Object.values(STATES).find((x) => x.fips === f.id); return { color: "#000", weight: 0.8, fillColor: s ? SYS[s.system].color : "#ddd", fillOpacity: 0.75 }; },
      onEachFeature: (f, l) => {
        const s = Object.values(STATES).find((x) => x.fips === f.id);
        if (!s) return;
        l.bindTooltip(`<b>${esc(s.name)}</b><br>${esc(s.systemLabel)} &middot; ${s.counties} counties${s.withData ? `<br>${s.withData} with parcel data` : ""}`, { sticky: true });
        l.on("mouseover", () => l.setStyle({ fillOpacity: 1, weight: 1.5 }));
        l.on("mouseout", () => l.setStyle({ fillOpacity: 0.75, weight: 0.8 }));
        l.on("click", () => { location.hash = s.abbr.toLowerCase(); });
      },
    }).addTo(m);
    m.fitBounds(layer.getBounds(), { padding: [6, 6] });

    // drill 1: systems -> states in the system -> open state
    const stateLevel = (k) => {
      const sts = REG.states.filter((s) => s.system === k).sort((a, b) => b.counties - a.counties);
      return { name: SYS[k].label, title: `Counties per state (${SYS[k].label.toLowerCase()})`, labels: sts.map((s) => s.abbr), values: sts.map((s) => s.counties), colors: SYS[k].color, series: "Counties",
        hint: (i) => `in ${sts[i].name}`, click: (i) => { go(sts[i].abbr.toLowerCase()); } };
    };
    new Drill("nSys", "nSysCrumb", { name: "All systems", title: "Counties by sale system", labels: sysRows.map((r) => SYS[r.k].label), values: sysRows.map((r) => r.counties), colors: sysRows.map((r) => SYS[r.k].color), series: "Counties", click: (i) => stateLevel(sysRows[i].k) });

    // drill 2: parcels by state -> counties in the state -> open county
    const byState = REG.states.filter((s) => s.parcels > 0).sort((a, b) => b.parcels - a.parcels);
    const countyLevel = (st) => {
      const cs = (BY_STATE[st.abbr] || []).filter((c) => c.data && c.data.parcels).sort((a, b) => b.data.parcels - a.data.parcels).slice(0, 30);
      return { name: st.name, title: `Parcels on file by county in ${st.name}${cs.length === 30 ? " (top 30)" : ""}`, labels: cs.map((c) => c.name), values: cs.map((c) => c.data.parcels), horizontal: true, series: "Parcels",
        click: (i) => { go(countyHref(cs[i]).slice(1)); } };
    };
    new Drill("nRich", "nRichCrumb", { name: "All states", title: "Parcels on file by state", labels: byState.map((s) => s.name), values: byState.map((s) => s.parcels), horizontal: true, series: "Parcels", hint: (i) => `in ${byState[i].withData} counties`, click: (i) => countyLevel(byState[i]) });

    // drill 3: posted sales by month -> counties selling that month -> open county
    const months = {};
    for (const c of posted) { const k = c.nextSale.slice(0, 7); (months[k] = months[k] || []).push(c); }
    const mk = Object.keys(months).sort();
    const mlabel = (k) => new Date(k + "-15T12:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" });
    new Drill("nCal", "nCalCrumb", { name: "All months", title: "Counties with a posted sale, by month", labels: mk.map(mlabel), values: mk.map((k) => months[k].length), series: "Counties", colors: "#8e5ad6",
      click: (i) => { const cs = months[mk[i]].sort((a, b) => (b.data?.parcels || 0) - (a.data?.parcels || 0)).slice(0, 30); return { name: mlabel(mk[i]), title: `Parcels listed for sale in ${mlabel(mk[i])}`, labels: cs.map((c) => `${c.name}, ${c.state}`), values: cs.map((c) => c.data?.parcels || 0), horizontal: true, series: "Parcels", colors: "#8e5ad6", hint: (j) => fmtDate(cs[j].nextSale), click: (j) => { go(countyHref(cs[j]).slice(1)); } }; } });

    // upcoming posted
    const upcoming = posted.map((c) => ({ c, date: c.nextSale, name: c.label, state: c.state, parcels: c.data ? c.data.parcels : null, kind: whoRuns(c) })).sort((a, b) => a.date.localeCompare(b.date));
    makeTable("nUpcoming", [
      { key: "date", label: "Date", val: (r) => r.date, html: (r) => fmtDate(r.date) },
      { key: "name", label: "County", html: (r) => `<a href="${countyHref(r.c)}">${esc(r.name)}</a>` },
      { key: "state", label: "State" },
      { key: "parcels", label: "Parcels on file", num: true, html: (r) => int(r.parcels) },
      { key: "link", label: "Links", cls: "links", html: (r) => linkCell(r.c) },
    ], upcoming, { sortKey: "date", sortDir: "asc", rowClass: () => "row", onRow: (r) => { location.hash = countyHref(r.c).slice(1); }, empty: "No posted dates on file" });

    // statutory
    const stat = REG.states.filter((s) => s.nextStatutory || s.nextStatutoryLabel).map((s) => ({ s, date: s.nextStatutory, label: s.nextStatutory ? fmtDate(s.nextStatutory) : s.nextStatutoryLabel, timing: s.sale_timing }))
      .sort((a, b) => (a.date || "9999").localeCompare(b.date || "9999") || a.s.name.localeCompare(b.s.name));
    $("nStatutory").innerHTML = `<thead><tr><th>State</th><th>Next sale</th><th>Schedule</th></tr></thead><tbody>${stat.map((r) => `<tr class="row" data-s="${r.s.abbr}"><td><a href="#${r.s.abbr.toLowerCase()}">${esc(r.s.name)}</a></td><td>${r.date ? `<b>${esc(r.label)}</b>` : `<span class="pill window">${esc(r.label)}</span>`}</td><td class="wrap small">${esc(r.timing)}</td></tr>`).join("")}</tbody>`;
    $("nStatutory").querySelectorAll("tr.row").forEach((tr) => tr.onclick = () => { location.hash = tr.dataset.s.toLowerCase(); });

    // all states
    makeTable("nStates", [
      { key: "name", label: "State", html: (r) => `<a href="#${r.abbr.toLowerCase()}">${esc(r.name)}</a>` },
      { key: "system", label: "Sale type", html: (r) => sysPill(r.system) },
      { key: "conducted_by", label: "Who holds the sale", wrap: true },
      { key: "redemption", label: "Redemption", wrap: true },
      { key: "rate", label: "Rate or penalty", wrap: true },
      { key: "next", label: "Next sale", val: (r) => r.nextStatutory || r.nextStatutoryLabel || "", html: (r) => r.nextStatutory ? fmtDate(r.nextStatutory) : esc(r.nextStatutoryLabel || "As scheduled") },
      { key: "counties", label: "Counties", num: true },
      { key: "withData", label: "With data", num: true },
    ], REG.states, { sortKey: "name", sortDir: "asc", rowClass: () => "row", onRow: (r) => { location.hash = r.abbr.toLowerCase(); } });
  }

  // ---------- STATE ----------
  function showState(abbr) {
    const s = STATES[abbr];
    const list = BY_STATE[abbr] || [];
    setView("viewState", abbr, "");
    $("sName").textContent = s.name;
    $("sSub").textContent = `${int(s.counties)} ${s.unit.toLowerCase().includes("county") ? "counties" : s.unit.toLowerCase() + "s"} · ${s.withData ? `${s.withData} with parcel data on file · ` : ""}population ${int(s.pop)}`;
    $("sPill").innerHTML = sysPill(s.system, true);
    $("sSummary").innerHTML = `<b>${esc(s.summary)}</b>`;
    $("sInfo").innerHTML = rulesHtml(s, true);
    $("sCountiesTitle").textContent = `${s.unit.includes("County") ? "Counties" : s.unit.replace(/ \(.*\)/, "") + "s"} In ${s.name}`;

    // map of counties
    const m = simpleMap("sMap");
    const feats = topojson.feature(TOPO, TOPO.objects.counties).features.filter((f) => String(f.id).startsWith(s.fips));
    const style = (c) => ({ color: "#000", weight: 0.7, fillOpacity: 0.95, fillColor: c && c.data ? "#2a78d6" : c && c.taxsale ? "#bcd3f3" : "#eef1f5" });
    const layer = L.geoJSON({ type: "FeatureCollection", features: feats }, {
      coordsToLatLng: projector(stateProjection(feats)),
      style: (f) => style(BY_FIPS[f.id]),
      onEachFeature: (f, l) => {
        const c = BY_FIPS[f.id];
        if (!c) return;
        l.bindTooltip(`<b>${esc(c.label)}</b>${c.data ? `<br>${int(c.data.parcels)} parcels on file` : ""}${nextSaleText(c) ? `<br>Next sale: ${esc(nextSaleText(c))}` : ""}`, { sticky: true });
        l.on("mouseover", () => l.setStyle({ weight: 2 }));
        l.on("mouseout", () => l.setStyle({ weight: 0.7 }));
        l.on("click", () => { location.hash = countyHref(c).slice(1); });
      },
    }).addTo(m);
    if (feats.length) m.fitBounds(layer.getBounds(), { padding: [8, 8] });

    // grouped drill-down chart
    const popTier = (p) => p == null ? "Unknown" : p < 10000 ? "Under 10k" : p < 50000 ? "10k to 50k" : p < 250000 ? "50k to 250k" : p < 1000000 ? "250k to 1M" : "1M and up";
    const groupers = {
      status: { title: "Counties by data on file", key: (c) => c.data ? "Parcel data on file" : c.taxsale ? "Tax sale page known" : "Official site and search links", order: ["Parcel data on file", "Tax sale page known", "Official site and search links"], colors: ["#2a78d6", "#bcd3f3", "#c9d4e5"] },
      month: { title: "Counties by next sale month", key: (c) => c.nextSale ? mlabelOf(c.nextSale) : (c.nextSaleLabel || "No date on file"), order: null },
      pop: { title: "Counties by population tier", key: (c) => popTier(c.pop), order: ["Under 10k", "10k to 50k", "50k to 250k", "250k to 1M", "1M and up", "Unknown"] },
      run: { title: "Counties by who holds the sale", key: (c) => shortRun(c), order: null },
    };
    const mlabelOf = (d) => new Date(d.slice(0, 7) + "-15T12:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" });
    const drawGroup = () => {
      const g = groupers[$("sGroup").value];
      const groups = {};
      for (const c of list) { const k = g.key(c); (groups[k] = groups[k] || []).push(c); }
      let keys = g.order ? g.order.filter((k) => groups[k]) : Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
      if ($("sGroup").value === "month") keys = Object.keys(groups).sort((a, b) => { const da = groups[a][0].nextSale || "9999", db = groups[b][0].nextSale || "9999"; return da.localeCompare(db); });
      new Drill("sChart", "sChartCrumb", { name: "All counties", title: g.title, labels: keys, values: keys.map((k) => groups[k].length), colors: g.colors || "#2a78d6", series: "Counties",
        click: (i) => { const cs = groups[keys[i]].sort((a, b) => (b.pop || 0) - (a.pop || 0)).slice(0, 40); return { name: keys[i], title: `${keys[i]}: population by county${cs.length === 40 ? " (top 40)" : ""}`, labels: cs.map((c) => c.name), values: cs.map((c) => c.pop || 0), horizontal: true, series: "Population", hint: (j) => cs[j].data ? `· ${int(cs[j].data.parcels)} parcels on file` : "", click: (j) => { go(countyHref(cs[j]).slice(1)); } }; } });
    };
    $("sGroup").onchange = drawGroup; drawGroup();

    const cols = [
      { key: "label", label: s.unit.includes("County") ? "County" : s.unit.replace(/ \(.*\)/, ""), html: (c) => `<a href="${countyHref(c)}">${esc(c.label)}</a>` },
      { key: "pop", label: "Population", num: true, html: (c) => int(c.pop) },
      { key: "next", label: "Next sale", val: (c) => c.nextSale || (c.nextSaleLabel ? "9999-" + c.nextSaleLabel : null), html: (c) => nextSaleText(c) ? `${esc(nextSaleText(c))} <span class="pill ${c.nextSaleKind}">${nextSaleKind(c)}</span>` : "" },
      { key: "auctions", label: "Auctions", num: true, val: (c) => c.data ? c.data.auctions : null, html: (c) => c.data ? int(c.data.auctions) : "" },
      { key: "parcels", label: "Parcels", num: true, val: (c) => c.data ? c.data.parcels : null, html: (c) => c.data ? int(c.data.parcels) : "" },
      { key: "run", label: "Who holds the sale", val: shortRun },
      { key: "links", label: "Links", cls: "links", html: linkCell, csv: (c) => c.taxsale || c.site || "" },
    ];
    const draw = () => {
      const q = $("sFilter").value.trim().toLowerCase();
      const rows = q ? list.filter((c) => c.label.toLowerCase().includes(q) || whoRuns(c).toLowerCase().includes(q)) : list;
      makeTable("sTable", cols, rows, { sortKey: "label", sortDir: "asc", rowClass: () => "row", onRow: (c) => { location.hash = countyHref(c).slice(1); } });
    };
    $("sFilter").value = ""; $("sFilter").oninput = draw; draw();
    $("sCsv").onclick = () => downloadCsv(`${slug(s.name)}-counties.csv`, [
      { key: "fips", label: "FIPS" }, { key: "label", label: "County" }, { key: "state", label: "State" }, { key: "pop", label: "Population" },
      { key: "next", label: "Next sale", val: (c) => c.nextSale || c.nextSaleLabel || "" }, { key: "nextSaleKind", label: "Next sale basis" },
      { key: "run", label: "Who holds the sale", val: whoRuns }, { key: "taxsale", label: "Tax sale page" }, { key: "site", label: "Official site" },
      { key: "parcels", label: "Parcels on file", val: (c) => c.data ? c.data.parcels : "" }, { key: "lat", label: "Latitude" }, { key: "lon", label: "Longitude" },
    ], list);
  }

  function rulesHtml(s, full) {
    const rows = [
      ["Sale type", SYS[s.system].label], ["Who holds the sale", s.conducted_by], ["When", s.sale_timing], ["Bidding", s.bidding],
      ["Interest, penalty or return", s.rate], ["Redemption", s.redemption], ["Mortgage foreclosures and sheriff sales", s.sheriff_sales],
      ["Statute", s.statute], ["Platforms", (s.platforms || []).join("; ")],
    ];
    if (full && s.notes) rows.push(["Notes", s.notes]);
    if (s.state_portal) rows.push(["State sale site", `<a href="${esc(s.state_portal)}" target="_blank" rel="noopener">${esc(s.state_portal)}</a>`]);
    return rows.filter((r) => r[1]).map(([k, v]) => `<div${k.length > 20 || String(v).length > 120 ? ' class="wide"' : ""}><b>${esc(k)}</b>${k === "State sale site" ? v : esc(v)}</div>`).join("");
  }

  // ---------- COUNTY ----------
  async function showCounty(c) {
    const s = c.st;
    setView("viewCounty", c.state, c.fips);
    $("cName").textContent = `${c.label}, ${s.name}`;
    $("cSub").innerHTML = `${sysPill(s.system)} &nbsp;<a href="#${c.state.toLowerCase()}">All of ${esc(s.name)}</a> &middot; FIPS ${c.fips}${c.pop ? ` &middot; population ${int(c.pop)}` : ""}${c.landSqmi ? ` &middot; ${int(Math.round(c.landSqmi))} sq mi` : ""}`;
    const info = [
      ["Who holds the sale", esc(whoRuns(c))],
      ["Next sale", nextSaleText(c) ? `${esc(nextSaleText(c))} <span class="pill ${c.nextSaleKind}">${nextSaleKind(c)}</span>` : esc(s.sale_timing)],
      ["Schedule", esc(c.schedule || s.sale_timing)],
      ["Tax sale page", c.taxsale ? `<a href="${esc(c.taxsale)}" target="_blank" rel="noopener">${esc(c.taxsale.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""))}</a>` : `Not on file. <a href="${searchUrl(`${c.label} ${s.name} tax sale`)}" target="_blank" rel="noopener">Search for it</a>`],
      ["Official site", c.site ? `<a href="${esc(c.site)}" target="_blank" rel="noopener">${esc(c.site.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""))}</a>` : `<a href="${searchUrl(`${c.label} ${s.name} official website`)}" target="_blank" rel="noopener">Search for it</a>`],
      ["Parcel lookup", c.parcelLookup ? `<a href="${esc(c.parcelLookup)}" target="_blank" rel="noopener">County parcel records</a>` : `<a href="${searchUrl(`${c.label} ${s.name} property search parcel assessor`)}" target="_blank" rel="noopener">Search the assessor</a>`],
      ["Sheriff and foreclosure sales", `<a href="${searchUrl(`${c.label} ${s.name} sheriff sale`)}" target="_blank" rel="noopener">Search sheriff sales</a> &middot; ${esc(s.foreclosure === "judicial" ? "judicial foreclosure state" : s.foreclosure === "nonjudicial" ? "nonjudicial foreclosure state" : "both judicial and nonjudicial foreclosure")}`],
    ];
    if (c.excess) info.push(["Excess funds", `<a href="${esc(c.excess)}" target="_blank" rel="noopener">Excess funds list</a>`]);
    if (c.platform) info.push(["Platform", esc(c.platform)]);
    if (c.data) info.push(["Data source", `<a href="${esc(COUNTY_CACHE[c.fips]?.sourceUrl || "#")}" id="cSrcLink" target="_blank" rel="noopener">${esc((INDEX?.sources?.[c.data.source]?.label) || c.data.source)}</a> &middot; checked ${esc(fmtDate((c.data.lastChecked || "").slice(0, 10)))}`]);
    $("cInfo").innerHTML = info.map(([k, v]) => `<div><b>${k}</b>${v}</div>`).join("");
    $("cNote").hidden = !c.note; $("cNote").innerHTML = c.note ? `<b>Note:</b> ${esc(c.note)}` : "";
    $("cRulesTitle").textContent = `${s.name} Rules`;
    $("cRules").innerHTML = rulesHtml(s, true);

    $("cPickerWrap").hidden = true; $("cBody").hidden = true; $("cEmpty").hidden = true;
    if (!c.data) {
      $("cEmpty").hidden = false;
      $("cEmpty").innerHTML = `<div class="emptyinfo"><h3>No parcel-level data on file yet</h3><p class="muted">This tracker has the rules, schedule and links for ${esc(c.label)}, but no source that publishes its sale lists in a form that can be read automatically. Use the links above to reach the county's own list.</p><ul class="small muted"><li>${esc(s.summary)}</li><li>${esc(s.sheriff_sales)}</li><li>Know a page that lists this county's sales as a spreadsheet, PDF or JSON? Open an issue or pull request on <a href="https://github.com/ShamarRobinson/us-tax-sale-dashboard" target="_blank" rel="noopener">GitHub</a> and it can be added as a source.</li></ul></div>`;
      return;
    }
    let d = COUNTY_CACHE[c.fips];
    if (!d) {
      try { d = await fetch(`data/counties/${c.fips}.json`).then((r) => r.json()); COUNTY_CACHE[c.fips] = d; }
      catch (e) { $("cEmpty").hidden = false; $("cEmpty").innerHTML = `<p class="muted">The county data file could not be loaded.</p>`; return; }
    }
    const srcLink = $("cSrcLink"); if (srcLink && d.sourceUrl) srcLink.href = d.sourceUrl;
    if (d.info && d.info.auction) {
      const a = d.info.auction;
      const extra = [["Venue", a.venue], ["Address", a.address], ["Time", a.time], ["Registration", a.registration], ["Payment", a.payment], ["Phone", a.phone], ["Email", a.email]].filter((x) => x[1]);
      if (extra.length) $("cInfo").insertAdjacentHTML("beforeend", extra.map(([k, v]) => `<div class="${String(v).length > 120 ? "wide" : ""}"><b>${k}</b>${esc(v)}</div>`).join(""));
    }
    const aucs = (d.auctions || []).filter((a) => a.parcels && a.parcels.length);
    if (!aucs.length) { $("cEmpty").hidden = false; $("cEmpty").innerHTML = `<p class="muted">Sales are on file but none has parcels listed.</p>`; return; }
    $("cPickerWrap").hidden = false; $("cBody").hidden = false;
    const sel = $("cAuction");
    sel.innerHTML = `<option value="all">All auctions on file (${aucs.length})</option>` + aucs.map((a, i) => `<option value="${i}">${esc(a.label)} (${a.parcels.length} parcels${a.status === "upcoming" ? ", upcoming" : ""})</option>`).join("");
    const first = aucs.findIndex((a) => a.status === "upcoming" && a.parcels.length >= 5);
    sel.value = first >= 0 ? String(first) : (aucs.length > 1 ? "all" : "0");
    sel.onchange = () => drawAuction(c, d, aucs, sel.value);
    drawAuction(c, d, aucs, sel.value);
    drawHistory(c, aucs);
  }

  function tiers(parcels) {
    const edges = [0, 1000, 2500, 5000, 10000, 25000, 50000, 100000, Infinity];
    const names = ["Under $1k", "$1k to $2.5k", "$2.5k to $5k", "$5k to $10k", "$10k to $25k", "$25k to $50k", "$50k to $100k", "$100k and up"];
    const out = names.map((n) => ({ name: n, parcels: 0, bids: [], mults: [] }));
    for (const p of parcels) {
      const v = p.minBid; if (v == null) continue;
      const i = edges.findIndex((e, j) => v >= e && v < edges[j + 1]);
      if (i < 0) continue;
      out[i].parcels++; if (p.winningBid) { out[i].bids.push(p.winningBid); if (v > 0) out[i].mults.push(p.winningBid / v); }
    }
    return out.filter((t) => t.parcels);
  }

  function drawAuction(c, d, aucs, which) {
    const chosen = which === "all" ? aucs : [aucs[+which]];
    const parcels = chosen.flatMap((a) => a.parcels.map((p) => ({ ...p, _date: a.date, _auction: a.label, _src: a.source })));
    const sold = parcels.filter((p) => p.status === "Sold");
    const bids = parcels.filter((p) => p.winningBid).map((p) => p.winningBid);
    const mults = parcels.filter((p) => p.winningBid && p.minBid).map((p) => p.winningBid / p.minBid);
    const excess = parcels.reduce((s, p) => s + (p.excess || 0), 0);
    const listed = parcels.filter((p) => p.status === "Listed").length;
    $("cKpis").innerHTML = [
      ["Parcels", int(parcels.length), which === "all" ? `across ${aucs.length} auctions` : chosen[0].label, true],
      ["Sold", int(sold.length), parcels.length ? `${Math.round(100 * sold.length / parcels.length)}% of parcels` : ""],
      ["Listed (not yet sold)", int(listed), "upcoming or outcome not published"],
      ["Average winning bid", bids.length ? money(avg(bids)) : "n/a", bids.length ? `median ${money(median(bids))} on ${int(bids.length)} priced` : "no prices published"],
      ["Typical multiple", mults.length ? median(mults).toFixed(2) + "x" : "n/a", "winning bid over opening bid"],
      ["Excess funds", excess ? money(excess) : "n/a", "sold above what was owed"],
    ].map(([l, v, n, hero]) => `<div class="kpi${hero ? " hero" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${esc(n)}</div></div>`).join("");

    // tiers
    const tr = tiers(parcels);
    $("secTiers").hidden = !tr.length;
    if (tr.length) {
      const tierParcels = (t) => parcels.filter((p) => p.minBid != null && tiers([p])[0]?.name === t.name).sort((a, b) => (b.winningBid || b.minBid || 0) - (a.winningBid || a.minBid || 0)).slice(0, 40);
      new Drill("cTiers", "cTiersCrumb", { name: "All tiers", title: "Parcels by amount owed", labels: tr.map((t) => t.name), values: tr.map((t) => t.parcels), series: "Parcels",
        hint: (i) => tr[i].bids.length ? `· avg winning bid ${money(avg(tr[i].bids))}` : "",
        click: (i) => { const ps = tierParcels(tr[i]); return { name: tr[i].name, title: `${tr[i].name}: opening bid and winning bid per parcel${ps.length === 40 ? " (top 40)" : ""}`, labels: ps.map((p) => p.parcel || p.lot || ""), values: ps.map((p) => p.minBid || 0), values2: ps.map((p) => p.winningBid || 0), series: "Opening bid", series2: "Winning bid", horizontal: true, money: true, hint: (j) => ps[j].address ? `· ${ps[j].address}` : "", click: (j) => { showDetail(c, ps[j]); } }; } });
      $("tTiers").innerHTML = `<thead><tr><th>Amount owed</th><th class="num">Parcels</th><th class="num">With price</th><th class="num">Avg winning bid</th><th class="num">Median multiple</th></tr></thead><tbody>${tr.map((t) => `<tr><td>${t.name}</td><td class="num">${int(t.parcels)}</td><td class="num">${int(t.bids.length)}</td><td class="num">${t.bids.length ? money(avg(t.bids)) : ""}</td><td class="num">${t.mults.length ? median(t.mults).toFixed(2) + "x" : ""}</td></tr>`).join("")}</tbody>`;
    }

    // map
    const geo = parcels.filter((p) => p.lat && p.lon);
    $("secMap").hidden = !geo.length;
    if (geo.length) {
      const m = tileMap("cMap");
      const maxv = Math.max(...geo.map((p) => p.winningBid || p.minBid || 0), 1);
      const group = L.featureGroup();
      for (const p of geo) {
        const v = p.winningBid || p.minBid || 0;
        const r = 4 + 10 * Math.sqrt(v / maxv);
        L.circleMarker([p.lat, p.lon], { radius: r, color: "#000", weight: 1, fillColor: p.status === "Sold" ? "#eb6834" : "#2a78d6", fillOpacity: 0.75 })
          .bindTooltip(`<b>${esc(p.parcel || p.lot || "")}</b><br>${esc(p.address || p.fullAddress || "")}<br>${p.minBid != null ? "Owed " + money(p.minBid) : ""}${p.winningBid ? " · Sold " + money(p.winningBid) : ""}`)
          .on("click", () => showDetail(c, p)).addTo(group);
      }
      group.addTo(m);
      m.fitBounds(group.getBounds().pad(0.15));
      $("mapNote").textContent = `${int(geo.length)} of ${int(parcels.length)} parcels have coordinates. Orange dots sold; blue dots listed or unsold.`;
    }

    // grid
    const cols = [
      { key: "parcel", label: "Parcel", html: (p) => `<b>${esc(p.parcel || p.lot || "")}</b>` },
      { key: "address", label: "Address", wrap: true, val: (p) => p.address || p.fullAddress || "" },
      { key: "area", label: "Area", wrap: true },
      { key: "owner", label: "Owner", wrap: true },
      { key: "type", label: "Type", wrap: true },
      { key: "minBid", label: "Owed / opening bid", num: true, html: (p) => money(p.minBid) },
      { key: "winningBid", label: "Winning bid", num: true, html: (p) => money(p.winningBid) },
      { key: "mult", label: "Multiple", num: true, val: (p) => p.winningBid && p.minBid ? p.winningBid / p.minBid : null, html: (p) => p.winningBid && p.minBid ? (p.winningBid / p.minBid).toFixed(2) + "x" : "" },
      { key: "excess", label: "Excess", num: true, html: (p) => money(p.excess) },
      { key: "status", label: "Status" },
      { key: "buyer", label: "Buyer", wrap: true },
      { key: "value", label: "County value", num: true, html: (p) => money(p.value) },
      { key: "_date", label: "Auction", html: (p) => fmtDate(p._date) },
    ];
    const draw = () => {
      const q = $("fSearch").value.trim().toLowerCase();
      const rows = q ? parcels.filter((p) => [p.parcel, p.lot, p.owner, p.address, p.fullAddress, p.buyer, p.area, p.type].some((v) => v && String(v).toLowerCase().includes(q))) : parcels;
      makeTable("parcelTable", cols, rows, { sortKey: "winningBid", sortDir: "desc", rowClass: () => "row", onRow: (p) => showDetail(c, p) });
      $("tableNote").textContent = `${int(rows.length)} parcels shown. "Not published" means the source has not released the outcome for that parcel.`;
      $("csvBtn").onclick = () => downloadCsv(`${c.state.toLowerCase()}-${c.slug}-parcels.csv`, [...cols, { key: "lat", label: "Latitude" }, { key: "lon", label: "Longitude" }, { key: "_src", label: "Source" }], rows);
    };
    $("fSearch").value = ""; $("fSearch").oninput = draw; draw();
  }

  function drawHistory(c, aucs) {
    const hist = [...aucs].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    const labels = hist.map((a) => (a.date ? fmtDate(a.date) : a.label));
    chart("cHist", { type: "bar", data: { labels, datasets: [{ label: "Parcels", data: hist.map((a) => a.parcels.length), backgroundColor: hist.map((a) => a.status === "upcoming" ? "#8e5ad6" : "#2a78d6"), borderRadius: 4, maxBarThickness: 30 }] },
      options: { maintainAspectRatio: false,
        onClick: (e, els) => { if (!els.length) return; const a = hist[els[0].index]; setTimeout(() => { const sel = $("cAuction"); sel.value = String(aucs.indexOf(a)); sel.dispatchEvent(new Event("change")); $("cKpis").scrollIntoView({ behavior: "smooth", block: "start" }); }, 0); },
        onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
        plugins: { legend: { display: false }, title: { display: true, text: "Parcels per sale (purple = upcoming); click a bar to pick that sale" } }, scales: { y: { beginAtZero: true, grid: { color: "#ebe9e4" }, ticks: { precision: 0 } }, x: { grid: { display: false }, ticks: { maxRotation: 45, autoSkip: true } } } } });
    const avgs = hist.map((a) => { const b = a.parcels.filter((p) => p.winningBid).map((p) => p.winningBid); return b.length ? avg(b) : null; });
    chart("cHistBid", { type: "line", data: { labels, datasets: [{ label: "Average winning bid", data: avgs, borderColor: "#eb6834", backgroundColor: "#eb6834", borderWidth: 2, pointRadius: 4, spanGaps: true, tension: 0.2 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: "Average winning bid per sale" }, tooltip: { callbacks: { label: (x) => money(x.raw) } } }, scales: { y: { beginAtZero: true, grid: { color: "#ebe9e4" }, ticks: { callback: (v) => money(v) } }, x: { grid: { display: false }, ticks: { maxRotation: 45, autoSkip: true } } } } });
    makeTable("tHist", [
      { key: "date", label: "Date", html: (a) => fmtDate(a.date) },
      { key: "label", label: "Sale", wrap: true },
      { key: "status", label: "Status", html: (a) => a.status === "upcoming" ? '<span class="open">Upcoming</span>' : "Past" },
      { key: "n", label: "Parcels", num: true, val: (a) => a.parcels.length },
      { key: "sold", label: "Sold", num: true, val: (a) => a.parcels.filter((p) => p.status === "Sold").length },
      { key: "avg", label: "Avg winning bid", num: true, val: (a) => { const b = a.parcels.filter((p) => p.winningBid).map((p) => p.winningBid); return b.length ? avg(b) : null; }, html: (a) => { const b = a.parcels.filter((p) => p.winningBid).map((p) => p.winningBid); return b.length ? money(avg(b)) : ""; } },
      { key: "source", label: "Source", cls: "links", html: (a) => a.source ? `<a href="${esc(a.source)}" target="_blank" rel="noopener">Open</a>` : "" },
    ], hist, { sortKey: "date", sortDir: "desc" });
  }

  function showDetail(c, p) {
    const rows = [
      ["Parcel", p.parcel], ["Lot", p.lot], ["Owner", p.owner], ["Address", p.fullAddress || p.address], ["Area", p.area], ["Type", p.type],
      ["Owed / opening bid", money(p.minBid)], ["Winning bid", money(p.winningBid)], ["Multiple", p.winningBid && p.minBid ? (p.winningBid / p.minBid).toFixed(2) + "x" : ""],
      ["Excess funds", money(p.excess)], ["Status", p.status], ["Buyer", p.buyer], ["County value", money(p.value)], ["Current taxes", money(p.taxes)],
      ["Acres", p.acres], ["Building sq ft", p.sqft ? int(p.sqft) : ""], ["Year built", p.yearBuilt], ["Years delinquent", p.years], ["Deed recorded", fmtDate(p.deedRecorded)], ["Auction", `${p._auction || ""}`],
    ].filter((r) => r[1] !== undefined && r[1] !== null && r[1] !== "");
    const links = [];
    if (p.lat && p.lon) links.push(`<a href="https://www.google.com/maps?q=${p.lat},${p.lon}" target="_blank" rel="noopener">Google Maps</a>`);
    else if (p.fullAddress || p.address) links.push(`<a href="https://www.google.com/maps/search/${encodeURIComponent((p.fullAddress || p.address) + ", " + c.st.name)}" target="_blank" rel="noopener">Google Maps</a>`);
    if (p.link) links.push(`<a href="${esc(p.link)}" target="_blank" rel="noopener">Listing</a>`);
    if (p._src) links.push(`<a href="${esc(p._src)}" target="_blank" rel="noopener">Source document</a>`);
    if (c.parcelLookup) links.push(`<a href="${esc(c.parcelLookup)}" target="_blank" rel="noopener">County parcel records</a>`);
    $("detailBody").innerHTML = `<h2>${esc(p.parcel || p.lot || "Parcel")}</h2><p class="muted small">${esc(c.label)}, ${esc(c.st.name)}</p>${p.desc ? `<p class="desc">${esc(p.desc)}</p>` : ""}<div class="dgrid">${rows.map(([k, v]) => `<div><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}</div><div class="dlinks">${links.join("")}</div>`;
    $("detail").showModal();
  }

  // ---------- SEARCH ----------
  function parseQuery(q) {
    const terms = { words: [], fields: {} };
    for (const tok of q.match(/\S+/g) || []) {
      const m = tok.match(/^([a-z]+)(:|>=|<=|>|<|=)(.+)$/i);
      if (m) terms.fields[m[1].toLowerCase()] = { op: m[2], v: m[3].toLowerCase() }; else terms.words.push(tok.toLowerCase());
    }
    return terms;
  }
  const num = (v) => { const m = String(v).match(/^([\d.]+)([km]?)$/); if (!m) return NaN; return +m[1] * (m[2] === "k" ? 1e3 : m[2] === "m" ? 1e6 : 1); };
  function runSearch(q) {
    const t = parseQuery(q);
    const sysKey = (v) => Object.keys(SYS).find((k) => k.startsWith(v) || SYS[k].label.toLowerCase().includes(v));
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
      }
      const hay = `${c.label} ${c.st.name} ${c.state} ${whoRuns(c)} ${SYS[c.st.system].label}`.toLowerCase();
      return t.words.every((w) => hay.includes(w));
    });
    for (const v of ["viewNation", "viewState", "viewCounty"]) $(v).hidden = true;
    $("selState").value = "us"; fillCountyDropdown(null);
    const tf = t.fields.type; $("selType").value = tf ? (sysKey(tf.v) || "") : "";
    $("results").hidden = false;
    $("resTitle").textContent = `Search Results: ${int(rows.length)} counties`;
    const cols = [
      { key: "label", label: "County", html: (c) => `<a href="${countyHref(c)}">${esc(c.label)}</a>` },
      { key: "state", label: "State", val: (c) => c.st.name },
      { key: "system", label: "Sale type", val: (c) => c.st.system, html: (c) => sysPill(c.st.system) },
      { key: "run", label: "Who holds the sale", val: shortRun },
      { key: "next", label: "Next sale", val: (c) => c.nextSale || null, html: (c) => nextSaleText(c) ? `${esc(nextSaleText(c))} <span class="pill ${c.nextSaleKind}">${nextSaleKind(c)}</span>` : "" },
      { key: "parcels", label: "Parcels on file", num: true, val: (c) => c.data ? c.data.parcels : null, html: (c) => c.data ? int(c.data.parcels) : "" },
      { key: "pop", label: "Population", num: true, html: (c) => int(c.pop) },
      { key: "links", label: "Links", cls: "links", html: linkCell, csv: (c) => c.taxsale || c.site || "" },
    ];
    makeTable("resTable", cols, rows.slice(0, 1500), { sortKey: "pop", sortDir: "desc", rowClass: () => "row", onRow: (c) => { location.hash = countyHref(c).slice(1); } });
    $("resNote").textContent = rows.length > 1500 ? `Showing the 1,500 most populous of ${int(rows.length)} matches; narrow the search to see the rest.` : "";
    $("resCsv").onclick = () => downloadCsv("tax-sale-search.csv", [{ key: "fips", label: "FIPS" }, ...cols.filter((x) => x.key !== "links"), { key: "taxsale", label: "Tax sale page" }, { key: "site", label: "Official site" }], rows);
    window.scrollTo({ top: 0 });
  }
  $("gSearch").addEventListener("keydown", (e) => { if (e.key === "Enter") { const q = $("gSearch").value.trim(); location.hash = q ? "q=" + q : ""; } });
  $("gSearch").addEventListener("input", () => { if (!$("gSearch").value.trim() && location.hash.startsWith("#q=")) location.hash = ""; });
  document.querySelectorAll(".examples button[data-q]").forEach((b) => b.onclick = () => { $("gSearch").value = b.dataset.q; location.hash = "q=" + b.dataset.q; });
  $("searchHelpBtn").onclick = () => { $("searchHelp").hidden = !$("searchHelp").hidden; };
  $("resClear").onclick = () => { $("gSearch").value = ""; location.hash = ""; };

  load().catch((e) => { $("freshness").textContent = "The data could not be loaded: " + e.message; console.error(e); });
})();
