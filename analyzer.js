/* Property Deal Analyzer: every parcel from data/master.json, rescored with the viewer's own assumptions. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (v) => (v == null || isNaN(v)) ? "" : (v < 0 ? "-" : "") + "$" + Math.round(Math.abs(v)).toLocaleString("en-US");
  const int = (v) => (v == null) ? "" : Number(v).toLocaleString("en-US");
  const fmtDate = (s) => { if (!s) return ""; const d = new Date(s + "T12:00:00"); return isNaN(d) ? s : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); };
  const median = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const TODAY = new Date().toISOString().slice(0, 10);
  const RATING = (s) => s >= 70 ? "Strong" : s >= 50 ? "Good" : s >= 35 ? "Fair" : "Weak";
  const RCOLOR = { Strong: "#159c6c", Good: "#2a78d6", Fair: "#eda100", Weak: "#c9d4e5" };
  const SYSTEM_RED = { "Tax deed": 0, "Tax lien": 36, "Redeemable deed": 12, "Hybrid (lien then deed)": 24 };

  let ALL = [], VIEW = [];
  const maps = {}, charts = {};
  const store = { get: (k, d) => { try { const v = localStorage.getItem("dealAnalyzer." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem("dealAnalyzer." + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } } };
  const WATCH = window.TS.WATCH, STATES = {};
  let COUNTIES = [], HOME = null;
  const haversine = (a, b, c, d) => { const R = 3958.8, toR = (x) => x * Math.PI / 180, dLat = toR(c - a), dLon = toR(d - b); const h = Math.sin(dLat / 2) ** 2 + Math.cos(toR(a)) * Math.cos(toR(c)) * Math.sin(dLon / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); };

  // ---------- load ----------
  async function load() {
    const [m, idx, reg] = await Promise.all([fetch("data/master.json", { cache: "no-cache" }).then((r) => r.json()), fetch("data/index.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => null), fetch("data/registry.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => null)]);
    if (reg) { for (const s of reg.states) STATES[s.abbr] = s; COUNTIES = reg.counties; }
    const cols = m.columns;
    ALL = m.rows.map((r) => { const o = {}; cols.forEach((c, i) => { o[c] = r[i]; }); return o; });
    const CL = {}; for (const c of COUNTIES) CL[c.fips] = c;
    for (const p of ALL) { p.id = `${p.fips}|${p.auctionDate}|${String(p.parcel || p.lot || p.caseNo || "").toUpperCase().replace(/\s+/g, " ").trim()}`; const c = CL[p.fips]; p.clat = p.lat || (c && c.lat); p.clon = p.lon || (c && c.lon); p.geoKind = p.lat ? "parcel" : "county"; }
    $("fHome").innerHTML = `<option value="">Anywhere</option><option value="geo">My location</option>` + COUNTIES.filter((c) => c.pop >= 20000).sort((a, b) => a.state.localeCompare(b.state) || a.name.localeCompare(b.name)).map((c) => `<option value="${c.fips}">${esc(c.label)}, ${c.state}</option>`).join("");
    const gen = idx && idx.generated ? new Date(idx.generated) : null;
    $("freshness").innerHTML = `<span class="dotlive"></span><b>${int(ALL.length)} parcels across ${int(new Set(ALL.map((p) => p.fips)).size)} counties</b> &middot; data generated ${gen ? gen.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "unknown"} &middot; refreshed on the 1st of every month`;
    fillSelect("fState", [...new Set(ALL.map((p) => p.state))].sort());
    fillSelect("fSystem", [...new Set(ALL.map((p) => p.system))].sort());
    fillSelect("fKind", [...new Set(ALL.map((p) => p.saleKind))].sort(), kindLabel);
    restore();
    bind();
    run();
  }
  const kindLabel = (k) => ({ taxdeed: "Tax deed sale (Clerk portal)", foreclosure: "Foreclosure sale (Clerk portal)", sheriff: "Sheriff sale", list: "County sale list", results: "County results", excess: "Excess funds list" }[k] || k);
  function fillSelect(id, vals, label) { const s = $(id); s.innerHTML = `<option value="">All</option>` + vals.map((v) => `<option value="${esc(v)}">${esc(label ? label(v) : v)}</option>`).join(""); }
  function fillCounties() {
    const st = $("fState").value; const s = $("fCounty");
    const cs = [...new Set(ALL.filter((p) => !st || p.state === st).map((p) => p.county))].sort();
    s.disabled = !st; s.innerHTML = `<option value="">All</option>` + cs.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  }

  const A = ["aDiscount", "aAllow", "aBudget", "aFallback", "aScore", "aUpcoming", "aHeadroom"];
  const F = ["fState", "fCounty", "fSystem", "fKind", "fStatus", "fType", "fMin", "fMax", "fValMin", "fSince", "fPhoto", "fGeo", "fValue", "fExcess", "fWatch", "fHome", "fMiles"];
  const URLKEYS = { state: "fState", county: "fCounty", system: "fSystem", kind: "fKind", status: "fStatus", type: "fType", min: "fMin", max: "fMax", valmin: "fValMin", since: "fSince", photo: "fPhoto", geo: "fGeo", value: "fValue", excess: "fExcess", watch: "fWatch", home: "fHome", miles: "fMiles", discount: "aDiscount", allow: "aAllow", budget: "aBudget", fallback: "aFallback", score: "aScore", upcoming: "aUpcoming", headroom: "aHeadroom", q: "q", sort: "sortBy" };
  const val = (id) => { const e = $(id); return e.type === "checkbox" ? e.checked : e.value; };
  function restore() {
    const saved = store.get("settings", null) || {};
    const h = new URLSearchParams(location.hash.replace(/^#/, ""));
    if (h.get("show") === "watch") { saved.fWatch = true; }
    for (const [k, id] of Object.entries(URLKEYS)) if (h.has(k)) saved[id] = $(id).type === "checkbox" ? h.get(k) === "1" : h.get(k);
    for (const id of [...A, ...F, "q", "sortBy"]) { if (id in saved) { const e = $(id); if (e.type === "checkbox") e.checked = !!saved[id]; else e.value = saved[id]; } }
    fillCounties(); if (saved.fCounty) $("fCounty").value = saved.fCounty;
  }
  function shareUrl() {
    const h = new URLSearchParams();
    for (const [k, id] of Object.entries(URLKEYS)) { const e = $(id); const v = e.type === "checkbox" ? (e.checked ? "1" : "") : e.value; if (v) h.set(k, v); }
    return `${location.origin}${location.pathname}#${h.toString()}`;
  }
  function persist() { const o = {}; for (const id of [...A, ...F]) o[id] = val(id); store.set("settings", o); }
  function bind() {
    for (const id of [...A, ...F]) $(id).addEventListener(["fType", "fMin", "fMax", "fValMin", "fMiles"].includes(id) ? "input" : "change", () => { if (id === "fState") fillCounties(); run(); });
    $("q").addEventListener("input", run);
    $("sortBy").addEventListener("change", run);
    $("aReset").onclick = () => { $("aDiscount").value = 40; $("aAllow").value = 5000; $("aBudget").value = 50000; $("aFallback").value = 4; $("aScore").value = 0; $("aUpcoming").checked = false; $("aHeadroom").checked = false; run(); };
    $("fClear").onclick = () => { for (const id of F) { const e = $(id); if (e.type === "checkbox") e.checked = false; else e.value = ""; } fillCounties(); $("q").value = ""; run(); };
    $("csvBtn").onclick = () => downloadCsv();
    $("fShare").onclick = (e) => { navigator.clipboard?.writeText(shareUrl()).then(() => { e.target.textContent = "Link copied"; setTimeout(() => { e.target.textContent = "Copy link to this view"; }, 1500); }); };
    $("wExport").onclick = () => WATCH.exportCsv();
    $("fGeo2").onclick = () => { if (!navigator.geolocation) return; navigator.geolocation.getCurrentPosition((pos) => { HOME = { lat: pos.coords.latitude, lon: pos.coords.longitude, label: "my location" }; $("fHome").value = "geo"; if (!$("fMiles").value) $("fMiles").value = 100; run(); }, () => alert("Location is not available in this browser.")); };
    document.addEventListener("watchlist-change", () => { if ($("fWatch").checked) run(); else grid(); });
    $("gFilter").onchange = () => { G.page = 0; gallery(); };
    $("gPrev").onclick = () => { G.page = Math.max(0, G.page - 1); gallery(); };
    $("gNext").onclick = () => { G.page++; gallery(); };
  }

  // ---------- scoring with the viewer's assumptions ----------
  function rescore(p, a) {
    const v = p.value || (p.minBid != null ? p.minBid * a.fallback : null);
    p.valueUsed = v; p.valueIsFallback = !p.value && v != null;
    p.maxBid = v != null ? Math.max(0, v * (1 - a.discount / 100) - a.allow) : null;
    p.headroom = p.maxBid != null && p.minBid != null ? p.maxBid - p.minBid : null;
    p.overBudget = p.minBid != null && a.budget > 0 && p.minBid > a.budget;
    // value part of the score follows the viewer's discount target; the rest comes from the master file
    let s = p.dealScore;
    if (v != null && p.minBid != null) {
      const ratio = p.minBid / v, base = 40 * Math.max(0, Math.min(1, 1 - ratio / 0.5));
      const want = 40 * Math.max(0, Math.min(1, (1 - a.discount / 100 - ratio) / (1 - a.discount / 100) + 0.5));
      s = s - base + Math.min(40, want);
    }
    if (p.overBudget) s -= 15;
    p.score = Math.max(0, Math.min(100, Math.round(s)));
    p.rating = RATING(p.score);
    return p;
  }

  // ---------- run ----------
  function run() {
    persist();
    const a = { discount: +$("aDiscount").value || 0, allow: +$("aAllow").value || 0, budget: +$("aBudget").value || 0, fallback: +$("aFallback").value || 4, minScore: +$("aScore").value || 0, upcoming: $("aUpcoming").checked, headroom: $("aHeadroom").checked };
    const f = { state: $("fState").value, county: $("fCounty").value, system: $("fSystem").value, kind: $("fKind").value, status: $("fStatus").value, type: $("fType").value.trim().toLowerCase(), min: +$("fMin").value || null, max: +$("fMax").value || null, valMin: +$("fValMin").value || null, since: $("fSince").value, photo: $("fPhoto").checked, geo: $("fGeo").checked, value: $("fValue").checked, excess: $("fExcess").checked, watch: $("fWatch").checked, miles: +$("fMiles").value || null };
    const q = $("q").value.trim().toLowerCase();
    const homeSel = $("fHome").value;
    let home = null;
    if (homeSel === "geo" && HOME) home = HOME; else if (homeSel && homeSel !== "geo") { const c = COUNTIES.find((x) => x.fips === homeSel); if (c) home = { lat: c.lat, lon: c.lon, label: c.label }; }
    const watched = f.watch ? WATCH.load() : null;
    VIEW = [];
    for (const p0 of ALL) {
      const p = rescore(p0, a);
      p.miles = home && p.clat ? Math.round(haversine(home.lat, home.lon, p.clat, p.clon)) : null;
      if (home && f.miles && !(p.miles != null && p.miles <= f.miles)) continue;
      if (f.excess && !(p.excess > 0)) continue;
      if (watched && !watched[p.id]) continue;
      if (f.state && p.state !== f.state) continue;
      if (f.county && p.county !== f.county) continue;
      if (f.system && p.system !== f.system) continue;
      if (f.kind && p.saleKind !== f.kind) continue;
      if (f.status && p.status !== f.status) continue;
      if (f.type && !(p.type || "").toLowerCase().includes(f.type)) continue;
      if (f.min != null && !(p.minBid >= f.min)) continue;
      if (f.max != null && !(p.minBid <= f.max)) continue;
      if (f.valMin != null && !(p.value >= f.valMin)) continue;
      if (f.since && (!p.auctionDate || p.auctionDate < f.since)) continue;
      if (f.photo && !p.photo) continue;
      if (f.geo && !(p.lat && p.lon)) continue;
      if (f.value && !p.value) continue;
      if (a.upcoming && p.auctionStatus !== "upcoming") continue;
      if (a.headroom && !(p.headroom > 0)) continue;
      if (p.score < a.minScore) continue;
      if (q && !`${p.parcel} ${p.lot} ${p.caseNo} ${p.address} ${p.fullAddress} ${p.owner} ${p.buyer} ${p.county} ${p.area} ${p.type}`.toLowerCase().includes(q)) continue;
      VIEW.push(p);
    }
    const key = $("sortBy").value;
    VIEW.sort((x, y) => { const a1 = x[key], b1 = y[key]; if (a1 == null && b1 == null) return 0; if (a1 == null) return 1; if (b1 == null) return -1; return typeof a1 === "number" ? b1 - a1 : String(b1).localeCompare(String(a1)); });
    kpis(a); drills(); scatter(); mapView(); grid(); G.page = 0; gallery();
  }

  function kpis(a) {
    const up = VIEW.filter((p) => p.auctionStatus === "upcoming");
    const pos = VIEW.filter((p) => p.headroom > 0);
    const sold = VIEW.filter((p) => p.winningBid);
    const strong = VIEW.filter((p) => p.rating === "Strong");
    const b2v = VIEW.filter((p) => p.value && p.minBid != null).map((p) => p.minBid / p.value);
    $("kpis").innerHTML = [
      ["Parcels in view", int(VIEW.length), `of ${int(ALL.length)} on file`, true],
      ["Upcoming", int(up.length), "listed for a sale still to come"],
      ["Positive headroom", int(pos.length), `max bid above opening bid at ${a.discount}% off`],
      ["Strong deals", int(strong.length), "score 70 and up"],
      ["Median opening bid", VIEW.length ? money(median(VIEW.filter((p) => p.minBid != null).map((p) => p.minBid))) : "n/a", "amount owed or opening bid"],
      ["Median bid to value", b2v.length ? Math.round(100 * median(b2v)) + "%" : "n/a", `on ${int(b2v.length)} with a county value`],
      ["Median sold multiple", sold.length ? (median(sold.filter((p) => p.minBid).map((p) => p.winningBid / p.minBid)) || 0).toFixed(2) + "x" : "n/a", `${int(sold.length)} sold with a price`],
      ["Excess funds in view", money(VIEW.reduce((s, p) => s + (p.excess || 0), 0)) || "$0", `${int(VIEW.filter((p) => p.excess > 0).length)} parcels sold above what was owed`],
      ["On my watchlist", int(WATCH.count()), VIEW.filter((p) => WATCH.has(p.id)).length + " in view"],
    ].map(([l, v, n, hero]) => `<div class="kpi${hero ? " hero" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${esc(n)}</div></div>`).join("");
  }

  // ---------- drill charts ----------
  Chart.defaults.font.family = "Inter, system-ui, sans-serif"; Chart.defaults.color = "#52514e";
  function chart(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart($(id), cfg); }
  class Drill {
    constructor(canvasId, crumbId, root) { this.id = canvasId; this.crumb = $(crumbId); this.stack = [root]; this.render(); }
    push(l) { this.stack.push(l); this.render(); }
    pop(i) { this.stack.length = i + 1; this.render(); }
    render() {
      const lv = this.stack[this.stack.length - 1];
      this.crumb.innerHTML = this.stack.map((l, i) => i < this.stack.length - 1 ? `<button type="button" data-i="${i}">${esc(l.name)}</button><span class="sep">&rsaquo;</span>` : `<span class="here">${esc(l.name)}</span>`).join("");
      this.crumb.querySelectorAll("button").forEach((b) => b.onclick = () => this.pop(+b.dataset.i));
      const box = $(this.id).parentElement; box.style.height = lv.horizontal ? Math.max(280, lv.labels.length * 22 + 70) + "px" : "";
      const fmt = lv.money ? money : int;
      chart(this.id, { type: "bar", data: { labels: lv.labels, datasets: [{ label: lv.series || "", data: lv.values, backgroundColor: lv.colors || "#2a78d6", borderRadius: 4, maxBarThickness: 34 }] },
        options: { indexAxis: lv.horizontal ? "y" : "x", maintainAspectRatio: false,
          onClick: (e, els) => { if (!els.length) return; const i = els[0].index; setTimeout(() => { const n = lv.click && lv.click(i); if (n) this.push(n); }, 0); },
          onHover: (e, els) => { e.native.target.style.cursor = els.length && lv.click ? "pointer" : "default"; },
          plugins: { legend: { display: false }, title: { display: true, text: lv.title }, tooltip: { callbacks: { label: (c) => `${fmt(c.raw)}${lv.hint ? " " + lv.hint(c.dataIndex) : ""}` } } },
          scales: { [lv.horizontal ? "x" : "y"]: { beginAtZero: true, grid: { color: "#ebe9e4" }, ticks: { callback: (v) => fmt(v), precision: 0 } }, [lv.horizontal ? "y" : "x"]: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: lv.horizontal ? 0 : 45 } } } } });
    }
  }
  const group = (rows, key) => { const g = {}; for (const p of rows) { const k = key(p); (g[k] = g[k] || []).push(p); } return g; };
  function parcelLevel(name, rows) {
    const ps = [...rows].sort((a, b) => b.score - a.score).slice(0, 40);
    return { name, title: `${name}: deal score by parcel (top 40)`, labels: ps.map((p) => `${p.parcel || p.lot || p.caseNo || "?"} · ${p.county.replace(/ County$/, "")}`), values: ps.map((p) => p.score), colors: ps.map((p) => RCOLOR[p.rating]), horizontal: true, series: "Score", hint: (i) => `· opening ${money(ps[i].minBid)}${ps[i].value ? " · value " + money(ps[i].value) : ""}`, click: (i) => { showDetail(ps[i]); } };
  }
  function drills() {
    const byS = group(VIEW, (p) => p.state); const sk = Object.keys(byS).sort((a, b) => byS[b].length - byS[a].length);
    new Drill("byState", "byStateCrumb", { name: "All states", title: "Parcels in view by state", labels: sk, values: sk.map((k) => byS[k].length), series: "Parcels", hint: (i) => `· ${byS[sk[i]].filter((p) => p.rating === "Strong").length} strong`,
      click: (i) => { const byC = group(byS[sk[i]], (p) => p.county); const ck = Object.keys(byC).sort((a, b) => byC[b].length - byC[a].length).slice(0, 40); return { name: sk[i], title: `Parcels by county in ${sk[i]}`, labels: ck.map((c) => c.replace(/ County$/, "")), values: ck.map((c) => byC[c].length), horizontal: true, series: "Parcels", hint: (j) => `· ${byC[ck[j]].filter((p) => p.rating === "Strong").length} strong`, click: (j) => parcelLevel(ck[j], byC[ck[j]]) }; } });
    const byB = group(VIEW.filter((p) => p.buyer), (p) => p.buyer.toUpperCase().trim()); const bk = Object.keys(byB).sort((a, b) => byB[b].length - byB[a].length).slice(0, 25);
    new Drill("byBuyer", "byBuyerCrumb", { name: "Top buyers", title: "Most active buyers in view (parcels won)", labels: bk.map((b) => b.length > 28 ? b.slice(0, 26) + "…" : b), values: bk.map((b) => byB[b].length), horizontal: true, series: "Parcels", colors: "#eb6834", hint: (i) => `· spent ${money(byB[bk[i]].reduce((s, p) => s + (p.winningBid || 0), 0))}`, click: (i) => parcelLevel(bk[i], byB[bk[i]]) });
    const byM = group(VIEW.filter((p) => p.auctionDate), (p) => p.auctionDate.slice(0, 7)); const mk = Object.keys(byM).sort(); const ml = (k) => new Date(k + "-15T12:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" });
    new Drill("byMonth", "byMonthCrumb", { name: "All months", title: "Parcels by sale month", labels: mk.map(ml), values: mk.map((k) => byM[k].length), colors: mk.map((k) => k >= TODAY.slice(0, 7) ? "#8e5ad6" : "#2a78d6"), series: "Parcels", click: (i) => parcelLevel(ml(mk[i]), byM[mk[i]]) });
    const bands = ["Strong", "Good", "Fair", "Weak"]; const byR = group(VIEW, (p) => p.rating);
    new Drill("byScore", "byScoreCrumb", { name: "All ratings", title: "Parcels in view by deal rating", labels: bands, values: bands.map((b) => (byR[b] || []).length), colors: bands.map((b) => RCOLOR[b]), series: "Parcels",
      click: (i) => { const rows = byR[bands[i]] || []; const byC = group(rows, (p) => `${p.county}, ${p.state}`); const ck = Object.keys(byC).sort((a, b) => byC[b].length - byC[a].length).slice(0, 40); return { name: bands[i], title: `${bands[i]} deals by county`, labels: ck, values: ck.map((c) => byC[c].length), horizontal: true, series: "Parcels", click: (j) => parcelLevel(ck[j], byC[ck[j]]) }; } });
  }

  function scatter() {
    const pts = VIEW.filter((p) => p.value && (p.winningBid || p.minBid != null)).slice(0, 4000);
    const ds = (name) => ({ label: name, data: pts.filter((p) => p.rating === name).map((p) => ({ x: p.value, y: p.winningBid || p.minBid, p })), backgroundColor: RCOLOR[name], borderColor: "#000", borderWidth: 0.5, pointRadius: 4, pointHoverRadius: 7 });
    const maxv = Math.max(1000, ...pts.map((p) => p.value));
    const minv = Math.max(10, Math.min(...pts.map((p) => Math.min(p.value, p.winningBid || p.minBid || p.value)).filter((v) => v > 0), maxv));
    const logTick = (v) => /^[125]0*$/.test(String(Math.round(v))) ? money(v) : "";
    chart("scatter", { type: "scatter", data: { datasets: [...["Strong", "Good", "Fair", "Weak"].map(ds), { type: "line", label: "Bid equals value", data: [{ x: minv, y: minv }, { x: maxv, y: maxv }], borderColor: "#000", borderDash: [6, 4], borderWidth: 1, pointRadius: 0 }] },
      options: { maintainAspectRatio: false, parsing: false, onClick: (e, els) => { if (els.length && els[0].element.$context.raw.p) setTimeout(() => showDetail(els[0].element.$context.raw.p), 0); }, onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
        plugins: { tooltip: { callbacks: { label: (c) => { const p = c.raw.p; return p ? `${p.parcel || p.lot || ""} ${p.county}: value ${money(p.value)}, ${p.winningBid ? "sold " + money(p.winningBid) : "opening " + money(p.minBid)}` : ""; } } } },
        scales: { x: { type: "logarithmic", min: minv, title: { display: true, text: "County value (log scale)" }, grid: { color: "#ebe9e4" }, ticks: { callback: logTick, autoSkip: false } }, y: { type: "logarithmic", min: minv, title: { display: true, text: "Bid (log scale)" }, grid: { color: "#ebe9e4" }, ticks: { callback: logTick, autoSkip: false } } } } });
  }

  function mapView() {
    if (maps.map) maps.map.remove();
    const m = L.map("map", { scrollWheelZoom: false }); maps.map = m;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(m);
    const geo = VIEW.filter((p) => p.lat && p.lon).slice(0, 3000);
    if (!geo.length) { m.setView([39.5, -98.35], 4); return; }
    const g = L.featureGroup();
    for (const p of geo) L.circleMarker([p.lat, p.lon], { radius: 5, color: "#000", weight: 0.7, fillColor: RCOLOR[p.rating], fillOpacity: 0.85 }).bindTooltip(`<b>${esc(p.parcel || p.lot || "")}</b> ${esc(p.county)}<br>${esc(p.address || p.fullAddress || "")}<br>Score ${p.score} · opening ${money(p.minBid)}${p.winningBid ? " · sold " + money(p.winningBid) : ""}`).on("click", () => showDetail(p)).addTo(g);
    g.addTo(m); m.fitBounds(g.getBounds().pad(0.1));
  }

  const watchInfo = (p) => ({ county: p.county, state: p.state, parcel: p.parcel || p.lot || p.caseNo, address: p.address || p.fullAddress, date: p.auctionDate, minBid: p.minBid, link: `${location.origin}${location.pathname.replace(/analyzer\.html$/, "")}#c/${p.fips}` });
  const COLS = [
    { key: "watch", label: "Watch", html: (p) => WATCH.btn(p.id, watchInfo(p)) },
    { key: "score", label: "Score", html: (p) => `<span class="pill r-${p.rating.toLowerCase()}">${p.score} ${p.rating}</span>` },
    { key: "parcel", label: "Parcel", html: (p) => `<b>${esc(p.parcel || p.lot || p.caseNo || "")}</b>` },
    { key: "county", label: "County", html: (p) => `${esc(p.county)}, ${esc(p.state)}` },
    { key: "address", label: "Address", wrap: true, val: (p) => p.address || p.fullAddress || "" },
    { key: "type", label: "Type", wrap: true },
    { key: "auctionDate", label: "Sale", html: (p) => `${fmtDate(p.auctionDate)}${p.auctionStatus === "upcoming" ? ' <span class="pill posted">Upcoming</span>' : ""}` },
    { key: "status", label: "Status" },
    { key: "minBid", label: "Opening bid", num: true, html: (p) => money(p.minBid) },
    { key: "value", label: "County value", num: true, html: (p) => p.value ? money(p.value) : (p.valueUsed ? `<span class="muted">${money(p.valueUsed)}*</span>` : "") },
    { key: "bidToValue", label: "Bid to value", num: true, html: (p) => p.value && p.minBid != null ? Math.round(100 * p.minBid / p.value) + "%" : "" },
    { key: "maxBid", label: "Your max bid", num: true, html: (p) => money(p.maxBid) },
    { key: "headroom", label: "Headroom", num: true, html: (p) => p.headroom == null ? "" : `<span class="pill ${p.headroom > 0 ? "pos" : "neg"}">${money(p.headroom)}</span>` },
    { key: "winningBid", label: "Winning bid", num: true, html: (p) => money(p.winningBid) },
    { key: "multiple", label: "Multiple", num: true, html: (p) => p.multiple ? p.multiple.toFixed(2) + "x" : "" },
    { key: "redemptionMonths", label: "Redemption", num: true, html: (p) => p.redemptionMonths == null ? "" : p.redemptionMonths === 0 ? "none" : p.redemptionMonths + " mo" },
    { key: "photo", label: "Image", html: (p) => p.photo ? "Photo" : (p.lat && p.lon) ? "Street View" : "" },
    { key: "miles", label: "Miles", num: true, html: (p) => p.miles != null ? `${int(p.miles)}${p.geoKind === "county" ? "*" : ""}` : "" },
  ];
  function grid() {
    const rows = VIEW.slice(0, 500);
    $("resTitle").textContent = `Parcels (${int(VIEW.length)} in view${VIEW.length > 500 ? ", first 500 shown" : ""})`;
    $("grid").innerHTML = `<thead><tr>${COLS.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("")}</tr></thead><tbody>${rows.map((p, i) => `<tr class="row" data-i="${i}">${COLS.map((c) => `<td class="${c.num ? "num" : ""}${c.wrap ? " wrap" : ""}">${c.html ? c.html(p) : esc(c.val ? c.val(p) : p[c.key])}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${COLS.length}" class="muted">No parcels match</td></tr>`}</tbody>`;
    $("grid").querySelectorAll("tr.row").forEach((tr) => tr.onclick = (e) => { if (e.target.closest("button.star")) return; showDetail(rows[+tr.dataset.i]); });
    $("gridNote").textContent = "* county value not published (the value fallback multiple from your assumptions is used), or distance measured to the county center because the parcel has no coordinates. Use Download CSV for every parcel in view.";
  }

  function downloadCsv() {
    const cols = ["score", "rating", "maxBid", "headroom", "miles", "fips", "county", "state", "system", "saleKind", "source", "auctionDate", "auctionStatus", "parcel", "caseNo", "certificate", "lot", "address", "fullAddress", "area", "zip", "owner", "buyer", "plaintiff", "type", "status", "soldAt", "minBid", "winningBid", "multiple", "excess", "value", "bidToValue", "taxes", "acres", "sqft", "yearBuilt", "lat", "lon", "photo", "listing", "sourceDoc", "countyPage", "redemptionMonths", "rate"];
    const q = (v) => { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const lines = [cols.join(",")]; for (const p of VIEW) lines.push(cols.map((c) => q(c === "maxBid" || c === "headroom" ? (p[c] == null ? "" : Math.round(p[c])) : p[c])).join(","));
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = "deal-analyzer.csv"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  // ---------- gallery ----------
  const G = { page: 0, per: 24 };
  const svUrl = (p) => (p.lat && p.lon) ? `https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d${(+p.lat).toFixed(6)}!2d${(+p.lon).toFixed(6)}!5f1!6d150!7e1` : null;
  function gallery() {
    const f = $("gFilter").value;
    const items = VIEW.filter((p) => f === "all" ? (p.photo || svUrl(p)) : f === "photo" ? p.photo : (!p.photo && svUrl(p)));
    const pages = Math.max(1, Math.ceil(items.length / G.per)); G.page = Math.min(G.page, pages - 1);
    const page = items.slice(G.page * G.per, (G.page + 1) * G.per);
    $("gPage").textContent = `${int(items.length)} with an image · page ${G.page + 1} of ${pages}`;
    $("gGrid").innerHTML = page.map((p, i) => `<div class="gtile" data-i="${i}"><div class="media">${p.photo ? `<img loading="lazy" src="${esc(p.photo)}" alt="Photo of ${esc(p.address || p.parcel || "")}">` : `<iframe loading="lazy" src="${svUrl(p)}" title="Street View" tabindex="-1"></iframe>`}<span class="badge">${p.photo ? "Photo" : "Street View"} · ${p.score} ${p.rating}</span></div><div class="cap"><b>${esc(p.address || p.fullAddress || p.parcel || "")}</b>${esc(p.county)}, ${esc(p.state)} · opening ${money(p.minBid)}${p.winningBid ? " · sold " + money(p.winningBid) : ""}</div></div>`).join("");
    $("gGrid").querySelectorAll(".gtile").forEach((t) => t.onclick = () => showDetail(page[+t.dataset.i]));
    $("gGrid").querySelectorAll("img").forEach((im) => im.addEventListener("error", () => { const p = page[+im.closest(".gtile").dataset.i]; const sv = svUrl(p); im.outerHTML = sv ? `<iframe loading="lazy" src="${sv}" tabindex="-1"></iframe>` : `<div class="na">Image N/A</div>`; }));
  }

  // ---------- detail ----------
  function showDetail(p) {
    const rows = [["Deal score", `${p.score} (${p.rating})`], ["Your max bid", money(p.maxBid)], ["Headroom", money(p.headroom)], ["County", `${p.county}, ${p.state}`], ["Sale type", p.system], ["Sale", `${fmtDate(p.auctionDate)} · ${p.auctionLabel || ""}`], ["Status", p.status],
      ["Parcel", p.parcel], ["Case", p.caseNo], ["Certificate", p.certificate], ["Lot", p.lot], ["Address", p.fullAddress || p.address], ["Area", p.area], ["ZIP", p.zip], ["Owner", p.owner], ["Plaintiff", p.plaintiff], ["Type", p.type], ["Sold at", p.soldAt], ["Opening bid", money(p.minBid)], ["Winning bid", money(p.winningBid)], ["Multiple", p.multiple ? p.multiple.toFixed(2) + "x" : ""], ["Buyer", p.buyer], ["Excess funds", money(p.excess)],
      ["County value", p.value ? money(p.value) : (p.valueUsed ? money(p.valueUsed) + " (fallback)" : "")], ["Bid to value", p.value && p.minBid != null ? Math.round(100 * p.minBid / p.value) + "%" : ""], ["Judgment", money(p.judgment)], ["Current taxes", money(p.taxes)], ["Acres", p.acres], ["Building sq ft", p.sqft ? int(p.sqft) : ""], ["Year built", p.yearBuilt], ["Years delinquent", p.years],
      ["Redemption", p.redemptionMonths == null ? "" : p.redemptionMonths === 0 ? "None after the sale" : `${p.redemptionMonths} months`], ["Rate or penalty", p.rate], ["County median multiple", p.countyMedianMultiple ? p.countyMedianMultiple + "x" : ""], ["Source", p.source]].filter((r) => r[1] !== undefined && r[1] !== null && r[1] !== "");
    const gm = (p.lat && p.lon) ? `https://www.google.com/maps?q=${p.lat},${p.lon}` : (p.fullAddress || p.address) ? `https://www.google.com/maps/search/${encodeURIComponent((p.fullAddress || p.address) + ", " + p.state)}` : null;
    const links = [gm && `<a href="${gm}" target="_blank" rel="noopener">Google Maps</a>`, p.listing && `<a href="${esc(p.listing)}" target="_blank" rel="noopener">Listing</a>`, p.sourceDoc && `<a href="${esc(p.sourceDoc)}" target="_blank" rel="noopener">Source document</a>`, p.countyPage && `<a href="${esc(p.countyPage)}" target="_blank" rel="noopener">County tax sale page</a>`, `<a href="index.html#c/${p.fips}">County page in the tracker</a>`].filter(Boolean);
    const media = p.photo ? `<div class="lbmedia"><img src="${esc(p.photo)}" alt="Photo"></div>${p.photoCredit ? `<p class="small muted">${esc(p.photoCredit)}</p>` : ""}` : svUrl(p) ? `<div class="lbmedia"><iframe src="${svUrl(p)}" title="Street View" allowfullscreen></iframe></div><p class="small muted">Live Google Street View near the parcel.</p>` : "";
    const w = WATCH.get(p.id), st = STATES[p.state];
    links.push(`<a href="sheet.html?fips=${p.fips}&id=${encodeURIComponent(p.id)}" target="_blank" rel="noopener">Print deal sheet</a>`);
    if (p.parcelRecord) links.push(`<a href="${esc(p.parcelRecord)}" target="_blank" rel="noopener">Parcel record</a>`);
    if (p.countyMap) links.push(`<a href="${esc(p.countyMap)}" target="_blank" rel="noopener">County map</a>`);
    $("detailBody").innerHTML = `<h2>${esc(p.parcel || p.lot || p.caseNo || "Parcel")} ${WATCH.btn(p.id, watchInfo(p))}</h2><p class="muted small">${esc(p.county)}, ${esc(p.state)}${p.miles != null ? ` · ${int(p.miles)} miles away` : ""}</p>${media}<div class="dgrid">${rows.map(([k, v]) => `<div><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}</div>
      <div class="watchnote"><label>Watchlist note <textarea id="dNote" rows="2" placeholder="Your notes on this parcel (kept in this browser)">${esc(w ? w.note : "")}</textarea></label></div>
      ${st ? `<h3 class="mt">If The Owner Redeems</h3>${window.TS.redemptionTable(st, p.winningBid || p.minBid || 0)}` : ""}
      <div class="dlinks">${links.join("")}</div>`;
    $("dNote").oninput = () => { if (!WATCH.has(p.id)) WATCH.toggle(p.id, watchInfo(p)); WATCH.note(p.id, $("dNote").value); document.querySelectorAll(`button.star[data-watch="${CSS.escape(p.id)}"]`).forEach((x) => { x.classList.add("on"); x.textContent = "★"; }); };
    $("detail").showModal();
  }

  load().catch((e) => { $("freshness").textContent = "The data could not be loaded: " + e.message; console.error(e); });
})();
