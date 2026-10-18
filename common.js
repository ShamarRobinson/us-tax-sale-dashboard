/* Shared helpers for the US Tax Sale Tracker pages: formatting, charts, tables, parcel enrichment, deal score,
   watchlist, calendar export and the redemption calculator. Exposed as window.TS. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (v) => (v == null || isNaN(v)) ? "" : (v < 0 ? "-" : "") + "$" + Math.round(Math.abs(v)).toLocaleString("en-US");
  const money2 = (v) => (v == null || isNaN(v)) ? "" : "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const short = (v) => v == null || isNaN(v) ? "" : Math.abs(v) >= 1e6 ? "$" + (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : Math.abs(v) >= 1e3 ? "$" + Math.round(v / 1e3) + "K" : "$" + Math.round(v);
  const int = (v) => (v == null || isNaN(v)) ? "" : Number(v).toLocaleString("en-US");
  const pct = (v) => (v == null || isNaN(v)) ? "" : Math.round(v * 100) + "%";
  const sum = (a) => a.reduce((s, v) => s + (v || 0), 0);
  const avg = (a) => { const b = a.filter((v) => v != null && !isNaN(v)); return b.length ? sum(b) / b.length : null; };
  const median = (a) => { const b = a.filter((v) => v != null && !isNaN(v)).sort((x, y) => x - y); if (!b.length) return null; const m = b.length >> 1; return b.length % 2 ? b[m] : (b[m - 1] + b[m]) / 2; };
  const mode = (vals) => { const m = new Map(); vals.forEach((v) => m.set(v, (m.get(v) || 0) + 1)); return [...m].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0] || null; };
  const fmtDate = (s, o) => { if (!s) return ""; const d = new Date(String(s).length === 10 ? s + "T12:00:00" : s); return isNaN(d) ? String(s) : d.toLocaleDateString("en-US", Object.assign({ month: "short", day: "numeric", year: "numeric" }, o || {})); };
  const slug = (s) => String(s).toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const searchUrl = (q) => "https://duckduckgo.com/?q=" + encodeURIComponent(q);
  const TODAY = new Date().toISOString().slice(0, 10);
  const NOWYEAR = new Date().getFullYear();
  const clamp = (x) => Math.max(0, Math.min(1, x));

  // ---------- charts ----------
  const charts = {};
  if (window.Chart) { Chart.defaults.font.family = "Inter, system-ui, sans-serif"; Chart.defaults.color = "#52514e"; }
  function chart(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart($(id), cfg); return charts[id]; }
  const RCOLOR = { Strong: "#159c6c", Good: "#2a78d6", Fair: "#eda100", Weak: "#c9d4e5" };

  // A level is { name, title, labels, values, values2?, colors?, horizontal?, money?, series, series2, hint(i), click(i) -> level | undefined }.
  class Drill {
    constructor(canvasId, crumbId, root) { this.id = canvasId; this.crumb = $(crumbId); this.stack = [root]; this.render(); }
    push(l) { this.stack.push(l); this.render(); }
    pop(i) { this.stack.length = i + 1; this.render(); }
    render() {
      const lv = this.stack[this.stack.length - 1];
      if (this.crumb) {
        this.crumb.innerHTML = this.stack.map((l, i) => i < this.stack.length - 1 ? `<button type="button" data-i="${i}">${esc(l.name)}</button><span class="sep">&rsaquo;</span>` : `<span class="here">${esc(l.name)}</span>`).join("");
        this.crumb.querySelectorAll("button").forEach((b) => b.onclick = () => this.pop(+b.dataset.i));
      }
      const box = $(this.id).parentElement;
      box.style.height = lv.horizontal ? Math.max(box.classList.contains("short") ? 230 : 280, lv.labels.length * 22 + 70) + "px" : "";
      const fmt = lv.money ? money : int;
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

  // ---------- tables and CSV ----------
  function makeTable(tableId, cols, rows, opts = {}) {
    const t = $(tableId);
    const state = t._sort || (t._sort = { key: opts.sortKey || null, dir: opts.sortDir || "desc" });
    const sorted = [...rows];
    if (state.key) {
      const col = cols.find((c) => c.key === state.key);
      if (col) sorted.sort((a, b) => {
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
    if (t.classList.contains("sortable")) {
      t.querySelectorAll("th").forEach((th) => th.onclick = () => {
        const k = th.dataset.key;
        if (state.key === k) state.dir = state.dir === "asc" ? "desc" : "asc"; else { state.key = k; state.dir = (cols.find((c) => c.key === k) || {}).num ? "desc" : "asc"; }
        makeTable(tableId, cols, rows, opts);
      });
    }
    if (opts.onRow) t.querySelectorAll("tbody tr[data-i]").forEach((tr) => tr.onclick = (e) => { if (e.target.closest("a, button")) return; opts.onRow(sorted[+tr.dataset.i]); });
    return sorted;
  }
  function downloadText(name, text, type = "text/csv") {
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function downloadCsv(name, cols, rows) {
    const q = (v) => { v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    const lines = [cols.map((c) => q(c.label)).join(",")];
    for (const r of rows) lines.push(cols.map((c) => q(c.csv ? c.csv(r) : (c.val ? c.val(r) : r[c.key]))).join(","));
    downloadText(name, lines.join("\n"));
  }

  // ---------- links, images, addresses ----------
  const gq = (q) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
  const gmapUrl = (p, countyLabel, stateName) => p.fullAddress && p.addrNum ? gq(p.fullAddress) : (p.lat && p.lon) ? gq(`${p.lat},${p.lon}`) : p.fullAddress ? gq(p.fullAddress) : p.address ? gq(`${p.address}, ${countyLabel || ""}, ${stateName || ""}`) : null;
  const svUrl = (p) => {
    if (p.sv && p.sv.length >= 2) { let [la, lo, h, m] = p.sv; if (h != null) { const d = Math.min(30, Math.max(8, m || 30)), r = h * Math.PI / 180, k = Math.cos(la * Math.PI / 180); la += d * Math.cos(r) / 110540; lo += d * Math.sin(r) / (111320 * k); } return `https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d${la.toFixed(6)}!2d${lo.toFixed(6)}!5f1!6d${Math.round(Math.min(300, Math.max(100, (m || 0) + 60)))}!7e1`; }
    if (p.lat && p.lon) return `https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d${(+p.lat).toFixed(6)}!2d${(+p.lon).toFixed(6)}!5f1!6d150!7e1`;
    return null;
  };
  const photos = (p) => p.photos && p.photos.length ? p.photos : p.photo ? [p.photo] : [];
  const addrText = (p) => p.fullAddress || p.address || "";
  const copyBtn = (t) => t ? ` <button type="button" class="copy" data-copy="${esc(t)}" title="Copy the full address">Copy</button>` : "";
  function copyText(t, btn) {
    const done = () => { const o = btn.textContent; btn.textContent = "Copied"; btn.classList.add("ok"); setTimeout(() => { btn.textContent = o; btn.classList.remove("ok"); }, 1300); };
    const fallback = () => { const ta = document.createElement("textarea"); ta.value = t; ta.style.position = "fixed"; ta.style.opacity = "0"; (btn.closest("dialog") || document.body).appendChild(ta); ta.select(); try { document.execCommand("copy"); done(); } catch (e) { /* nothing more to try */ } ta.remove(); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(t).then(done, fallback); else fallback();
  }
  document.addEventListener("click", (e) => { const b = e.target.closest("button.copy"); if (b) { e.stopPropagation(); e.preventDefault(); copyText(b.dataset.copy, b); } }, true);

  // ---------- parcel classification ----------
  const TYPES = ["Single-family home", "Condo or townhouse", "Multi-family", "Manufactured home", "Commercial or industrial", "Agricultural", "Vacant land", "Other or unknown"];
  function typeCat(p) {
    const t = String(p.type || "");
    const code = parseFloat(t);
    if (!isNaN(code) && /^\d/.test(t)) { // Clark County Assessor land-use codes
      if (code >= 10 && code < 20) return "Vacant land";
      if (code >= 20 && code < 21) return "Single-family home";
      if ((code >= 21 && code < 22) || (code >= 24 && code < 25)) return "Condo or townhouse";
      if (code >= 22 && code < 24) return "Manufactured home";
      if (code >= 30 && code < 40) return "Multi-family";
      if (code >= 40 && code < 60) return "Commercial or industrial";
      return "Other or unknown";
    }
    if (/mobile|manufactured/i.test(t)) return "Manufactured home";
    if (/condo|town ?ho|duplex/i.test(t)) return "Condo or townhouse";
    if (/multi|apartment|units|plex/i.test(t)) return "Multi-family";
    if (/commercial|retail|office|industrial|warehouse|business|building(?!\s*lot)/i.test(t)) return "Commercial or industrial";
    if (/agric|farm|timber|conservation/i.test(t)) return "Agricultural";
    if (/vacant|land|^lot\b|acre|waterfront lot|exempt|utility/i.test(t)) return "Vacant land";
    if (/single|home|house|cottage|residential|sfr|dwelling|water ?front home/i.test(t)) return "Single-family home";
    if (p.sqft > 0 || p.yearBuilt > 0) return "Single-family home";
    return "Other or unknown";
  }
  const TIERS = [[0, 1000, "Under $1k"], [1000, 2500, "$1k to $2.5k"], [2500, 5000, "$2.5k to $5k"], [5000, 10000, "$5k to $10k"], [10000, 25000, "$10k to $25k"], [25000, 50000, "$25k to $50k"], [50000, 100000, "$50k to $100k"], [100000, Infinity, "$100k and up"]];
  const tierOf = (v) => v == null ? "Not stated" : (TIERS.find((t) => v >= t[0] && v < t[1]) || TIERS[TIERS.length - 1])[2];

  // ---------- deal score (0 to 100) with its parts ----------
  const PT = { "Single-family home": 20, "Multi-family": 20, "Condo or townhouse": 16, "Commercial or industrial": 16, "Agricultural": 10, "Vacant land": 8, "Manufactured home": 6 };
  function dealScore(p, ctx) {
    if (p._ds) return p._ds;
    const parts = [], cost = p.winningBid || p.minBid || null;
    let v;
    if (p.value > 0 && cost) { const r = cost / p.value; v = Math.round(40 * clamp((0.6 - r) / 0.55)); parts.push(["Value", v, 40, `Cost is ${Math.round(r * 100)}% of the county value (${money(p.value)})`]); }
    else if (cost) { v = cost < 2500 ? 24 : cost < 10000 ? 19 : cost < 25000 ? 14 : cost < 75000 ? 9 : 5; parts.push(["Value", v, 40, `No county value published, so scored on entry cost (${money(cost)})`]); }
    else { v = 10; parts.push(["Value", v, 40, "No amount owed or county value published"]); }
    const cat = p.cat || typeCat(p), ad = (p.address || "").trim();
    const mh = /MH$|MOBILE|PERSONAL PROP/i.test(`${p.parcel || ""} ${p.type || ""} ${p.desc || ""}`);
    let t = PT[cat];
    let why = `${cat} (county records)`;
    if (t == null) { t = mh ? 3 : /^[1-9]\d*[A-Z]?\s+\S/.test(ad) ? 14 : /^0\s/.test(ad) ? 8 : ad ? 10 : 8; why = mh ? "Mobile home or personal property" : t === 14 ? "Numbered street address (likely a built lot)" : t === 8 && ad ? "Address starts with 0 (usually vacant land)" : ad ? "Street or legal description only (often vacant land)" : "No address or property type published"; }
    parts.push(["Property", t, 20, why]);
    const pop = ctx && ctx.pop || 0, mk = pop >= 1e6 ? 15 : pop >= 250000 ? 13 : pop >= 100000 ? 11 : pop >= 40000 ? 9 : 6;
    parts.push(["Market", mk, 15, pop ? `${ctx.label} has ${int(pop)} residents` : "County population unknown"]);
    const m = p.multiple || (ctx && ctx.medianMultiple) || null, co = !m ? 8 : m <= 1.005 ? 15 : m < 2 ? 11 : m < 5 ? 7 : 3;
    parts.push(["Competition", co, 15, p.multiple ? `Sold for ${p.multiple.toFixed(1)}x the amount owed` : m ? `County median is ${m.toFixed(1)}x the amount owed` : "No winning bids published for this county"]);
    const pr = p.priors || [], n = pr.length, nb = pr.some((x) => x.status === "No bid"), h = nb ? 2 : n === 0 ? 10 : n === 1 ? 6 : 3;
    parts.push(["History", h, 10, nb ? "Drew no bid at an earlier auction" : n ? `Listed at ${n} earlier auction${n > 1 ? "s" : ""}` : "First time on file"]);
    const score = sum(parts.map((x) => x[1]));
    return (p._ds = { score, rating: score >= 70 ? "Strong" : score >= 50 ? "Good" : score >= 35 ? "Fair" : "Weak", parts });
  }
  const scoreHtml = (p, ctx) => { const d = dealScore(p, ctx); return `<span class="pill r-${d.rating.toLowerCase()}" title="${esc(d.parts.map((x) => `${x[0]} ${x[1]}/${x[2]}`).join(" · "))}">${d.score} ${d.rating}</span>`; };

  // ---------- enrich a county data file: flat parcel list with priors, multiples, categories, scores ----------
  const pkey = (p) => String(p.parcel || p.lot || p.caseNo || "").toUpperCase().replace(/\s+/g, " ").trim();
  function prepCounty(d, c) {
    const aucs = (d.auctions || []).filter((a) => a.parcels && a.parcels.length).map((a) => ({ ...a }));
    const all = [];
    for (const a of aucs) {
      a.parcels = a.parcels.map((p0) => {
        const p = { ...p0 };
        p._date = a.date || ""; p._auction = a.label; p._kind = a.saleKind || a.kind; p._src = a.source; p._upcoming = a.status === "upcoming"; p._aid = a.id;
        p.sold = p.status === "Sold" || (p.winningBid > 0);
        p.multiple = p.winningBid && p.minBid ? p.winningBid / p.minBid : null;
        p.war = !!(p.winningBid && p.minBid && p.winningBid > p.minBid * 1.005);
        p.cat = typeCat(p);
        p.tier = tierOf(p.minBid);
        p.area = p.area || "Not stated";
        p.key = pkey(p);
        p.id = `${c.fips}|${p._date}|${p.key}`;
        all.push(p);
        return p;
      });
    }
    // priors: the same parcel at an earlier sale on file (one record per date, preferring the one with a price)
    const by = {};
    for (const p of all) if (p.key) (by[p.key] = by[p.key] || []).push(p);
    for (const g of Object.values(by)) {
      const dates = {};
      for (const p of g) { const d0 = dates[p._date]; if (!d0 || (!d0.winningBid && p.winningBid) || (d0._kind === "list" && p._kind !== "list")) dates[p._date] = p; }
      const list = Object.values(dates).sort((a, b) => a._date.localeCompare(b._date));
      for (const p of g) p.priors = list.filter((x) => x._date < p._date);
    }
    const ctx = { label: c.label, pop: c.pop, medianMultiple: median(all.map((p) => p.multiple)) };
    for (const p of all) { p.ds = dealScore(p, ctx); p.score = p.ds.score; p.rating = p.ds.rating; }
    return { aucs, all, ctx };
  }

  // ---------- watchlist (per browser) ----------
  const WKEY = "ts.watchlist.v1";
  const WATCH = {
    load() { try { return JSON.parse(localStorage.getItem(WKEY) || "{}"); } catch (e) { return {}; } },
    save(w) { try { localStorage.setItem(WKEY, JSON.stringify(w)); } catch (e) { /* storage unavailable */ } },
    has(id) { return !!WATCH.load()[id]; },
    get(id) { return WATCH.load()[id] || null; },
    toggle(id, info) { const w = WATCH.load(); if (w[id]) delete w[id]; else w[id] = { ...info, added: new Date().toISOString().slice(0, 10), note: "" }; WATCH.save(w); return !!w[id]; },
    note(id, note) { const w = WATCH.load(); if (w[id]) { w[id].note = note; WATCH.save(w); } },
    all() { return Object.entries(WATCH.load()).map(([id, v]) => ({ id, ...v })); },
    count() { return Object.keys(WATCH.load()).length; },
    btn(id, info) { return `<button type="button" class="star${WATCH.has(id) ? " on" : ""}" data-watch="${esc(id)}" data-info="${esc(JSON.stringify(info || {}))}" title="${WATCH.has(id) ? "Remove from watchlist" : "Add to watchlist"}">${WATCH.has(id) ? "★" : "☆"}</button>`; },
    exportCsv() { const rows = WATCH.all(); downloadCsv("watchlist.csv", [{ key: "id", label: "Id" }, { key: "county", label: "County" }, { key: "state", label: "State" }, { key: "parcel", label: "Parcel" }, { key: "address", label: "Address" }, { key: "date", label: "Sale date" }, { key: "minBid", label: "Opening bid" }, { key: "added", label: "Added" }, { key: "note", label: "Note" }, { key: "link", label: "Link" }], rows); },
  };
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button.star"); if (!b) return;
    e.stopPropagation(); e.preventDefault();
    let info = {}; try { info = JSON.parse(b.dataset.info || "{}"); } catch (x) { /* ignore */ }
    const on = WATCH.toggle(b.dataset.watch, info);
    document.querySelectorAll(`button.star[data-watch="${CSS.escape(b.dataset.watch)}"]`).forEach((x) => { x.classList.toggle("on", on); x.textContent = on ? "★" : "☆"; x.title = on ? "Remove from watchlist" : "Add to watchlist"; });
    document.dispatchEvent(new CustomEvent("watchlist-change", { detail: { id: b.dataset.watch, on } }));
  }, true);

  // ---------- calendar export ----------
  function ics(events, calName) {
    const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
    const esc2 = (s) => String(s || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
    const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//US Tax Sale Tracker//EN", `X-WR-CALNAME:${esc2(calName || "Tax sales")}`];
    for (const ev of events) {
      if (!ev.date) continue;
      const d = ev.date.replace(/-/g, ""), next = new Date(ev.date + "T12:00:00"); next.setDate(next.getDate() + 1);
      lines.push("BEGIN:VEVENT", `UID:${esc2(ev.uid || ev.date + "-" + slug(ev.title))}@ustaxsale`, `DTSTAMP:${stamp}`, `DTSTART;VALUE=DATE:${d}`, `DTEND;VALUE=DATE:${next.toISOString().slice(0, 10).replace(/-/g, "")}`,
        `SUMMARY:${esc2(ev.title)}`, ev.desc ? `DESCRIPTION:${esc2(ev.desc)}` : "", ev.url ? `URL:${esc2(ev.url)}` : "", ev.location ? `LOCATION:${esc2(ev.location)}` : "", "END:VEVENT");
    }
    lines.push("END:VCALENDAR");
    return lines.filter(Boolean).join("\r\n");
  }

  // ---------- redemption return calculator ----------
  function redemptionTable(st, principal) {
    if (!principal || !st) return "";
    const rate = st.rate_pct || 0, pen = st.penalty_pct || 0, step = st.penalty_step_pct || 0, months = st.redemption_months || 0;
    if (!months || (!rate && !pen)) return `<p class="muted small">${esc(st.name)} is a ${esc((st.systemLabel || st.system || "").toLowerCase())} state: there is no redemption return to calculate; the buyer keeps the property${months ? " after the redemption period" : ""}.</p>`;
    const at = (m) => principal * (pen + step * Math.floor(Math.max(0, m - 1) / 12) + rate * m / 12) / 100;
    const pts = [...new Set([1, 6, 12, months].filter((m) => m <= months))].sort((a, b) => a - b);
    return `<table class="data mini"><thead><tr><th>Redeemed after</th><th class="num">You receive back</th><th class="num">Return</th><th class="num">Annualized</th></tr></thead><tbody>${pts.map((m) => { const r = at(m); return `<tr><td>${m} month${m > 1 ? "s" : ""}</td><td class="num">${money(principal + r)}</td><td class="num">${(100 * r / principal).toFixed(1)}%</td><td class="num">${(100 * r / principal * 12 / m).toFixed(1)}%</td></tr>`; }).join("")}</tbody></table><p class="muted small">Based on ${esc(st.name)}'s statutory terms: ${rate ? rate + "% per year interest" : ""}${rate && pen ? " plus " : ""}${pen ? `a ${pen}% penalty${step ? ` rising ${step}% each year` : ""}` : ""}, over a ${months}-month redemption period, on ${money(principal)} paid at the sale. Fees, subsequent taxes and county practice change the real figure.</p>`;
  }

  // ---------- auto-recheck: reload when a refresh has landed ----------
  function autoRefresh(generated) {
    setInterval(async () => {
      try { const j = await fetch("data/index.json", { cache: "no-store" }).then((r) => r.json()); if (j.generated && generated && j.generated !== generated) location.reload(); } catch (e) { /* offline */ }
    }, 30 * 60 * 1000);
  }

  window.TS = { $, esc, money, money2, short, int, pct, sum, avg, median, mode, fmtDate, slug, searchUrl, TODAY, NOWYEAR, clamp, chart, charts, Drill, RCOLOR, makeTable, downloadCsv, downloadText,
    gmapUrl, svUrl, photos, addrText, copyBtn, TYPES, typeCat, TIERS, tierOf, dealScore, scoreHtml, prepCounty, WATCH, ics, redemptionTable, autoRefresh };
})();
