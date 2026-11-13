/* Headwind page: renders data/snapshot.json. All text from data goes through esc(). */
(function () {
  "use strict";

  function esc(v) {
    return String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pct(v) { return (v > 0 ? "+" : "") + Number(v).toFixed(1) + "%"; }
  function zText(v) { return v === null || v === undefined ? "no baseline" : (v > 0 ? "+" : "") + Number(v).toFixed(1); }
  function rate(v) { return v === null || v === undefined ? "" : Math.round(v * 100) + "%"; }
  function flag(a) { return a ? ' <span class="badge badge-warn">unusual</span>' : ""; }
  function when(iso) {
    try {
      return new Date(iso).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
    } catch (e) { return iso; }
  }
  function table(id, head, rows) {
    var el = document.getElementById(id);
    if (!el) { return; }
    if (!rows.length) { el.outerHTML = '<p class="small muted">No data.</p>'; return; }
    el.innerHTML = "<thead><tr>" + head.map(function (h) { return "<th scope=\"col\">" + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>" + rows.map(function (r) { return "<tr>" + r.map(function (c) { return "<td>" + c + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody>";
  }

  function render(s) {
    var names = s.country_names || {};
    var fx = (s.fx || []).slice().sort(function (a, b) { return Math.abs(b.z || 0) - Math.abs(a.z || 0); });
    var en = s.energy || [], fao = s.fao || [], lf = s.local_food || [];
    var fresh = lf.filter(function (w) { return !w.stale; });

    document.getElementById("asof").textContent = "Collected " + when(s.generated_at) + ". Method " + (s.method_version || "") + ".";

    var an = [];
    fx.forEach(function (f) { if (f.anomaly) { an.push((names[f.country] || f.currency) + " (" + f.currency + "): " + Math.abs(f.change_pct).toFixed(1) + "% " + f.direction + " against the US dollar in 5 business days, z " + zText(f.z)); } });
    en.forEach(function (e) { if (e.anomaly) { an.push(e.name + ": " + pct(e.change_pct) + " in 5 trading days, z " + zText(e.z)); } });
    fao.forEach(function (c) { if (c.anomaly) { an.push(c.name + " (" + c.period + "): " + pct(c.change_pct) + " on the month, z " + zText(c.z)); } });
    fresh.forEach(function (w) { if (w.anomaly) { an.push((names[w.country] || w.country) + ": local food prices " + pct(w.median_change_pct) + " in 3 months, z " + zText(w.z)); } });
    document.getElementById("anomalies").innerHTML = an.length
      ? an.map(function (t) { return '<div class="row">' + esc(t) + "</div>"; }).join("")
      : '<p class="small muted">Nothing is outside its normal range in this collection.</p>';

    document.getElementById("tiles").innerHTML = [
      ["Unusual now", an.length], ["Currencies", fx.length], ["Energy and food series", en.length + fao.length],
      ["Countries with local prices", fresh.length]
    ].map(function (t) { return '<div class="tile"><span class="k">' + esc(t[0]) + '</span><span class="v">' + esc(t[1]) + "</span></div>"; }).join("");

    table("fx-table", ["Currency", "Per US dollar", "5-day change", "z", "Usual flag rate", "As of"], fx.map(function (f) {
      return [esc((names[f.country] || (f.currency === "EUR" ? "Euro area" : "")) + " " + f.currency) + flag(f.anomaly), esc(Number(f.per_usd).toPrecision(5)),
        esc(Math.abs(f.change_pct).toFixed(1) + "% " + f.direction), esc(zText(f.z)), esc(rate(f.flag_rate)), esc(f.date)];
    }));
    table("energy-table", ["Series", "Price", "5-day change", "z", "As of"], en.map(function (e) {
      return [esc(e.name) + flag(e.anomaly), esc(Number(e.price).toFixed(2)), esc(pct(e.change_pct)), esc(zText(e.z)), esc(e.date)];
    }));
    table("fao-table", ["Index", "Value", "On the month", "z", "Month"], fao.map(function (c) {
      return [esc(c.name) + flag(c.anomaly), esc(Number(c.value).toFixed(1)), esc(pct(c.change_pct)), esc(zText(c.z)), esc(c.period)];
    }));
    table("wfp-table", ["Country", "3-month median change", "z", "Series rising", "Price series", "Markets", "Month"],
      fresh.slice().sort(function (a, b) { return b.median_change_pct - a.median_change_pct; }).map(function (w) {
        return [esc(names[w.country] || w.country) + flag(w.anomaly), esc(pct(w.median_change_pct)), esc(zText(w.z)),
          esc(Math.round(w.share_rising * 100) + "%"), esc(w.series), esc(w.markets), esc(w.period)];
      }));
    var gone = lf.filter(function (w) { return w.stale; }).map(function (w) { return (names[w.country] || w.country) + " (newest month " + w.period + ")"; })
      .concat((s.local_food_missing || []).map(function (m) { return (names[m.country] || m.country) + " (" + m.reason + ")"; }));
    document.getElementById("wfp-missing").textContent = gone.length ? "No recent data: " + gone.join("; ") + "." : "";

    document.getElementById("calendar").innerHTML = (s.events || []).map(function (e) {
      return '<div class="row"><div class="row-title"><span>' + esc(e.title) + '</span><span class="badge">' + esc(e.date) + "</span></div></div>";
    }).join("") || '<p class="small muted">No dates collected.</p>';

    var lists = s.sanctions_lists || [];
    document.getElementById("sanction-lists").innerHTML = lists.map(function (l) {
      var types = Object.keys(l.by_type || {}).map(function (k) { return k + " " + Number(l.by_type[k]).toLocaleString(); }).join(", ");
      return '<div class="row"><div class="row-title"><span><a href="' + esc(l.url) + '" rel="noopener">' + esc(l.name) + '</a></span><span class="badge">' + esc(Number(l.total).toLocaleString()) + ' entries</span></div><div class="small muted">' +
        esc(types + ". Read " + when(l.checked_at) + "; compared since " + when(l.baseline_set_at) + ".") + "</div></div>";
    }).join("") || '<p class="small muted">No list has been read yet.</p>';
    function counts(o) { return Object.keys(o || {}).slice(0, 6).map(function (k) { return k + " " + o[k]; }).join(", "); }
    document.getElementById("sanction-deltas").innerHTML = (s.sanctions || []).map(function (d) {
      var lines = [];
      if (d.added) { lines.push("Added by program: " + counts(d.added_by_program) + ". By type: " + counts(d.added_by_type) + "."); }
      if (d.removed) { lines.push("Removed by program: " + counts(d.removed_by_program) + "."); }
      return '<div class="row"><div class="row-title"><span>' + esc(d.list_name + ": " + d.added + " added, " + d.removed + " removed") + '</span><span class="badge">seen ' + esc(when(d.detected_at)) + '</span></div><div class="small muted">' + esc(lines.join(" ")) + "</div></div>";
    }).join("") || (lists.length ? '<p class="small muted">No change seen in the last 30 days of readings.</p>' : "");

    var sl = s.screening_lists || [];
    function day(iso) {
      if (!iso) { return ""; }
      try { return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); } catch (e) { return iso; }
    }
    document.getElementById("screening-deltas").innerHTML = (s.screening || []).map(function (d) {
      var lines = [];
      if (d.added) { lines.push("Added by address country: " + counts(d.added_by_country) + "."); }
      if (d.removed) { lines.push("Removed by address country: " + counts(d.removed_by_country) + "."); }
      return '<div class="row"><div class="row-title"><span>' + esc(d.list_name + ": " + d.added + " added, " + d.removed + " removed") + '</span><span class="badge">seen ' + esc(when(d.detected_at)) + '</span></div><div class="small muted">' + esc(d.publisher + ". " + lines.join(" ")) + "</div></div>";
    }).join("") || (sl.length ? '<p class="small muted">No change seen in the last 30 days of readings. Compared since ' + esc(when(sl[0].baseline_set_at)) + ".</p>" : "");
    table("screening-table", ["List", "Publisher", "Entries", "Publisher's last update"], sl.map(function (l) {
      return ['<a href="' + esc(l.url) + '" rel="noopener">' + esc(l.name) + "</a>", esc(l.publisher), esc(Number(l.total).toLocaleString()), esc(day(l.source_last_updated))];
    }));

    var mn = s.minerals || {};
    if ((mn.import_sources || []).length) {
      document.getElementById("minerals-note").innerHTML = esc("Net import reliance in " + mn.reliance_year + " is imports less exports, adjusted for stock changes, as a share of US consumption. Import shares are for " + mn.sources_period + ". Annual figures, copied as published in the ") +
        '<a href="' + esc(mn.url) + '" rel="noopener">' + esc("USGS Mineral Commodity Summaries " + String(mn.edition || "").replace("MCS", "") + " data release") + "</a>" + esc(mn.published ? " of " + day(mn.published + "T12:00:00Z") + "." : ".") +
        esc(" The table lists the " + mn.import_sources.length + " commodities in the Summaries' import-sources figure; the ") + '<a href="data/minerals.json">data file</a>' + esc(" also has net import reliance for " + (mn.reliance || []).length + " commodities.");
      table("minerals-table", ["Commodity", "Net import reliance", "Import sources and their share"], mn.import_sources.map(function (m) {
        return [esc(m.commodity), esc(m.reliance_text ? m.reliance_text + "%" : "not given"),
          esc((m.shares || []).map(function (x) { return x.source + " " + x.pct + "%"; }).join(", ") || "not given")];
      }));
      var firsts = (mn.by_source || []).filter(function (b) { return b.named_first > 1; }).slice(0, 8).map(function (b) { return b.source + " " + b.named_first; });
      document.getElementById("minerals-first").textContent = firsts.length ? "Named first among major import sources, out of the " + mn.with_sources + " commodities with sources given: " + firsts.join(", ") + "." : "";
    } else {
      table("minerals-table", [], []);
    }

    var ruleRows = (s.controls || []).map(function (r) {
      var bits = [String(r.action || "").replace(/[.;\s]+$/, "")];
      if (r.effective_on) { bits.push("effective " + r.effective_on); }
      if ((r.named_dates || []).length) { bits.push("later dates named: " + r.named_dates.join(", ")); }
      return '<div class="row"><div class="row-title"><span><a href="' + esc(r.url) + '" rel="noopener">' + esc(r.agency + ": " + r.title) + '</a></span><span class="badge">' + esc(r.published_date) + '</span></div><div class="small muted">' + esc(bits.filter(Boolean).join("; ")) + "</div></div>";
    });
    var RULES_SHOWN = 6;
    document.getElementById("rules-list").innerHTML = ruleRows.length
      ? ruleRows.slice(0, RULES_SHOWN).join("") + (ruleRows.length > RULES_SHOWN
        ? '<details class="more"><summary>Show ' + (ruleRows.length - RULES_SHOWN) + " earlier documents</summary>" + ruleRows.slice(RULES_SHOWN).join("") + "</details>" : "")
      : '<p class="small muted">No rules collected.</p>';

    var labels = { sanctions: "Sanctions lists (OFAC, UN Security Council)", screening: "US screening lists (trade.gov)", minerals: "Mineral import reliance (USGS)", controls: "Rules (US Federal Register)", fx: "Exchange rates (ECB)", energy: "Energy prices (EIA via FRED)", fao: "Food indices (FAO)", wfp: "Local food prices (WFP via HDX)", baseline: "Country baselines (World Bank)", calendar: "Calendars (Federal Reserve, ECB)" };
    document.getElementById("lanes").innerHTML = Object.keys(s.lanes || {}).map(function (k) {
      var l = s.lanes[k], ok = l.status === "ok";
      var note = ok ? "collected " + when(l.fetched_at) : (l.from_previous && l.fetched_at ? "failed; showing the copy from " + when(l.fetched_at) : "failed; no data");
      return '<div class="row"><div class="row-title"><span>' + esc(labels[k] || k) + '</span><span class="badge ' + (ok ? "" : "badge-warn") + '">' + esc(ok ? "current" : "not current") + '</span></div><div class="small muted">' + esc(note) + "</div></div>";
    }).join("");
  }

  fetch("data/snapshot.json")
    .then(function (r) { return r.json(); })
    .then(render)
    .catch(function () { document.getElementById("asof").textContent = "The data could not be loaded."; });
})();
