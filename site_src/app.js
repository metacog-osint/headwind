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
  var T = window.TicTime;
  function when(iso) {
    // House rule: the viewer's own zone by default, the zone always named, changed from the Time menu.
    if (T && iso) { try { return T.format(iso, { year: true }); } catch (e) { /* fall through */ } }
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
    (s.sanctions || []).concat(s.screening || []).forEach(function (d) { if (d.anomaly) { an.push(d.list_name + ": a designation batch larger than the list's usual (" + (d.national ? d.national.added + " national" : d.added) + " added, seen " + String(d.detected_at).slice(0, 10) + ")"); } });
    fresh.forEach(function (w) { if (w.anomaly) { an.push((names[w.country] || w.country) + ": local food prices " + pct(w.median_change_pct) + " in 3 months, z " + zText(w.z)); } });
    (s.fx_official || []).forEach(function (o) { if (o.anomaly) { an.push((names[o.country] || o.country) + ": official exchange rate " + Math.abs(o.change_pct).toFixed(1) + "% " + o.direction + " against the US dollar in " + o.period + ", z " + zText(o.z)); } });
    (s.market_fx || []).forEach(function (w) { if (w.anomaly) { an.push((names[w.country] || w.country) + ": " + (w.unofficial ? "unofficial " : "") + "market exchange rate " + Math.abs(w.median_change_pct).toFixed(1) + "% " + w.direction + " against the US dollar in " + w.period + ", z " + zText(w.z)); } });
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
    function num(v) { return v === null || v === undefined ? "" : Number(v).toLocaleString(undefined, { maximumSignificantDigits: 6 }); }
    function cell(x, level, change, period, extra) {
      if (!x) { return '<span class="muted">none</span>'; }
      var bits = [change, x.z === null || x.z === undefined ? "" : "z " + zText(x.z)].filter(function (b) { return b; });
      return esc(level + (bits.length ? " (" + bits.join(", ") + ")" : "")) + flag(x.anomaly && !x.stale) +
        '<br><span class="small muted">' + esc(period + (x.stale ? ", old data" : "") + (extra ? "; " + extra : "")) + "</span>";
    }
    table("country-table", ["Country", "Daily rate (ECB)", "Official, monthly (World Bank)", "Market, monthly (WFP)", "Market against official", "Local food, 3 months"],
      (s.country_view || []).map(function (r) {
        var d = r.daily, o = r.official, m = r.market, f = r.local_food, g = r.market_vs_official;
        return [esc(r.name) + ((r.indicators_present || []).length ? ' <span class="badge badge-warn">' + esc(r.indicators_present.join(", ")) + "</span>" : ""),
          cell(d, d ? d.currency + " " + num(d.per_usd) : "", d ? pct(d.change_pct) + " in 5 days" : "", d ? d.date : "", d && d.note),
          cell(o, o ? num(o.per_usd) : "", o ? pct(o.change_pct) + " on the month" : "", o ? o.period : ""),
          cell(m, m ? (m.split ? num(m.per_usd_low) + " to " + num(m.per_usd_high) : num(m.per_usd_median)) : "", m ? pct(m.median_change_pct) + " on the month" : "", m ? m.period : "",
            m ? m.markets + " market" + (m.markets === 1 ? "" : "s") + (m.unofficial ? ", unofficial" : "") + (m.split ? ", too far apart to be one market" : "") : ""),
          g ? esc(pct(g.pct)) + (g.caveat ? ' <span class="badge">caveat</span>' : "") + '<br><span class="small muted">' + esc(g.period) + (g.caveat ? "; " + esc(g.caveat) : "") + "</span>" : '<span class="muted">none</span>',
          f ? cell(f, pct(f.median_change_pct), "", f.period) : '<span class="muted">' + esc(r.local_food_missing || "none") + "</span>"];
      }));
    document.getElementById("country-note").textContent = "No official monthly rate: " + ((s.fx_official_missing || []).map(function (m) { return names[m.country] || m.country; }).join(", ") || "none") +
      ". A badge names the HW-WP-2 indicators present (HW-IND-4 a currency, HW-IND-6 local food). The World Bank last updated its monthly rates " + (s.fx_official_updated || "on a date it does not give") + ".";
    var gone = lf.filter(function (w) { return w.stale; }).map(function (w) { return (names[w.country] || w.country) + " (newest month " + w.period + ")"; })
      .concat((s.local_food_missing || []).map(function (m) { return (names[m.country] || m.country) + " (" + m.reason + ")"; }));
    document.getElementById("wfp-missing").textContent = gone.length ? "No recent data: " + gone.join("; ") + "." : "";

    document.getElementById("calendar").innerHTML = (s.events || []).map(function (e) {
      return '<div class="row"><div class="row-title"><span>' + esc(e.title) + '</span><span class="badge">' + esc(e.date) + "</span></div></div>";
    }).join("") || '<p class="small muted">No dates collected.</p>';

    var lists = s.sanctions_lists || [];
    document.getElementById("sanction-lists").innerHTML = lists.map(function (l) {
      var types = Object.keys(l.by_type || {}).map(function (k) { return k + " " + Number(l.by_type[k]).toLocaleString(); }).join(", ");
      var note = l.error ? " Not read on the last run (" + when(l.failed_at) + "): " + l.error + ". These figures are from the reading before." : "";
      return '<div class="row"><div class="row-title"><span><a href="' + esc(l.url) + '" rel="noopener">' + esc(l.name) + '</a></span><span class="badge">' + esc(Number(l.total).toLocaleString()) + ' entries</span></div><div class="small muted">' +
        esc(types + ". Read " + when(l.checked_at) + "; compared since " + when(l.baseline_set_at) + "." + note) + "</div></div>";
    }).join("") || '<p class="small muted">No list has been read yet.</p>';
    var listName = {};
    lists.forEach(function (l) { listName[l.id] = l.name; });
    function alsoOn(v) { return (v.also_on || []).length ? ", also on " + v.also_on.map(function (l) { return listName[l] || l; }).join(" and ") : ""; }
    var vc = s.vessel_crosslist || {};
    document.getElementById("vessel-cross").innerHTML = vc.imo_numbers ? '<p class="small muted">' + esc(
      "Ships matched by IMO number: " + Number(vc.imo_numbers).toLocaleString() + " numbers, " +
      Number(vc.on_both).toLocaleString() + " on both the OFAC and UK lists, " +
      (vc.on_two_or_more !== undefined ? Number(vc.on_two_or_more).toLocaleString() + " on two or more of the OFAC, UK, French and Canadian lists, " : "") +
      Number((vc.only || {})["ofac-sdn"] || 0).toLocaleString() + " on OFAC's only, " +
      Number((vc.only || {})["uk-sanctions"] || 0).toLocaleString() + " on the UK's only, " +
      Number((vc.only || {})["france-gels"] || 0).toLocaleString() + " on France's only, " +
      Number((vc.only || {})["canada-sema"] || 0).toLocaleString() + " on Canada's only; " +
      Number((vc.without_imo || {})["ofac-sdn"] || 0) + " OFAC, " + Number((vc.without_imo || {})["uk-sanctions"] || 0) +
      " UK, " + Number((vc.without_imo || {})["france-gels"] || 0) + " French and " + Number((vc.without_imo || {})["canada-sema"] || 0) +
      " Canadian entries give no IMO number." + ((vc.from_earlier_run || []).length ? " From an earlier reading: " + vc.from_earlier_run.join(", ") + "." : "")) +
      ' <a href="data/vessels.json">Every ship, with each list\'s entry ids, name and flag</a>.</p>' : "";
    function counts(o) { return Object.keys(o || {}).slice(0, 6).map(function (k) { return k + " " + o[k]; }).join(", "); }
    function batchLine(lines, d) {
      var b = d.batches || [];
      if (!b.length) { return; }
      lines.push("Designation batches: " + b.map(function (x) {
        var z = x.z === null || x.z === undefined ? "no baseline yet" : "z " + zText(x.z);
        return x.basis === "designation date"
          ? x.date + ", " + x.size + " entries with that date (" + x.added + " in this change; " + z + " against " + x.baseline_n + " earlier dates" + (x.anomaly ? ", unusual" : "") + ")"
          : x.added + " added at once (" + z + " against " + x.baseline_n + " earlier changes Headwind saw" + (x.anomaly ? ", unusual" : "") + ")";
      }).join("; ") + ".");
    }
    function edited(lines, d) {
      if (!d.changed) { return; }
      var bits = ["Changed " + d.changed + " that stayed on the list"];
      if (Object.keys(d.programs_gained || {}).length) { bits.push("programs gained: " + counts(d.programs_gained)); }
      if (Object.keys(d.programs_lost || {}).length) { bits.push("programs lost: " + counts(d.programs_lost)); }
      lines.push(bits.join("; ") + ".");
    }
    document.getElementById("sanction-deltas").innerHTML = (s.sanctions || []).map(function (d) {
      var lines = [], nat = d.national, rest = d.restated, base = nat || d;
      if (base.added) { lines.push((nat ? "National freezes added" : "Added") + " by program: " + counts(base.added_by_program) + ". By type: " + counts(base.added_by_type) + "."); }
      if (base.removed) { lines.push((nat ? "National freezes removed" : "Removed") + " by program: " + counts(base.removed_by_program) + "."); }
      if (rest) { lines.push("Restating EU and UN measures (read on those lists too, so counted, not scored): " + rest.added + " added, " + rest.removed + " removed, " + rest.changed + " changed."); }
      function ships(word, vs) {
        if (!vs || !vs.length) { return; }
        lines.push("Vessels " + word + ": " + vs.map(function (v) {
          return (v.name || "unnamed") + " (" + (v.name_is_alias ? "alias, " : "") + (v.imo ? "IMO " + v.imo : "no IMO number given") + (v.flag ? ", flag " + v.flag : "") + alsoOn(v) + ")";
        }).join("; ") + ".");
      }
      ships("added", d.vessels_added); ships("removed", d.vessels_removed);
      if ((d.vessels_rekeyed || []).length) {
        lines.push("Vessels removed and listed again under a new entry id with the same IMO number, counted as the same entry: " + d.vessels_rekeyed.map(function (v) {
          return (v.name || "unnamed") + " (IMO " + v.imo + ", " + v.old_id + " to " + v.list_id + ")";
        }).join("; ") + ".");
      }
      edited(lines, base);
      if ((d.vessels_changed || []).length) {
        lines.push("Vessels still listed whose details changed: " + d.vessels_changed.map(function (v) {
          return (v.name || "unnamed") + (v.imo ? " (IMO " + v.imo + ")" : "") + ": " + Object.keys(v.changed).map(function (f) {
            return f + " " + (v.changed[f][0] || "none") + " to " + (v.changed[f][1] || "none");
          }).join(", ");
        }).join("; ") + ".");
      }
      batchLine(lines, d);
      var head = nat ? d.list_name + ": " + nat.added + " national freezes added, " + nat.removed + " removed" + (nat.changed ? ", " + nat.changed + " changed" : "") + "; " + rest.added + " added and " + rest.removed + " removed restating EU and UN measures"
        : d.list_name + ": " + d.added + " added, " + d.removed + " removed" + (d.changed ? ", " + d.changed + " changed" : "") + (d.rekeyed ? ", " + d.rekeyed + " under a new id" : "");
      return '<div class="row"><div class="row-title"><span>' + esc(head) + flag(d.anomaly) + '</span><span class="badge">seen ' + esc(when(d.detected_at)) + '</span></div><div class="small muted">' + esc(lines.join(" ")) + "</div></div>";
    }).join("") || (lists.length ? '<p class="small muted">No change seen in the last 30 days of readings.</p>' : "");

    var up = s.un_press || {}, ur = s.un_committee_releases || [];
    document.getElementById("un-releases").innerHTML = (ur.length ? '<p class="small muted">' + ur.map(function (r) {
      return '<a href="' + esc(r.url) + '" rel="noopener">' + esc(r.id) + "</a> (" + esc(r.published.slice(0, 10)) + ")";
    }).join(", ") + ".</p>" : '<p class="small muted">None seen in the last 60 days.</p>') +
      '<p class="small muted">' + esc("Document number, date and link only (UN terms of use). The UN's press feed holds its ten newest releases of every kind, so a release can come and go between two of Headwind's readings" +
      (up.checked_at ? "; on the last reading (" + when(up.checked_at) + ") the feed reached back to " + when(up.oldest) + (!up.previous_read ? " (the first reading, so nothing to compare)." : up.may_have_missed ? ", after the reading before it (" + when(up.previous_read) + "): a release in between may be missed." : ", which covers the time since the reading before.") : ".")) + "</p>";

    var tr = s.mineral_trade || {};
    function usd(v) { return v === null || v === undefined ? "" : "$" + (v >= 1e9 ? (v / 1e9).toFixed(2) + " bn" : v >= 1e6 ? (v / 1e6).toFixed(1) + " m" : Math.round(v).toLocaleString()); }
    if ((tr.codes || []).length) {
      document.getElementById("trade-note").textContent = "General imports, customs value, for HS codes that stand for minerals on the 2025 List of Critical Minerals; the last 12 months to " +
        (tr.newest_month || "") + " against the 12 before. An HS heading can hold more than one mineral, and ores, metals and compounds are separate codes, so a row is not a mineral's whole trade. " + (tr.notice || "");
      table("trade-table", ["HS code", "For", "Last 12 months", "Against the 12 before", "China's share (before)", "Leading sources"], tr.codes.filter(function (c) { return c.newest_month; }).map(function (c) {
        return [esc(c.hs + " " + (c.description || "")), esc((c.minerals || []).join(", ")), esc(usd(c.imports_12m_usd)), esc(c.change_pct !== null && c.change_pct !== undefined ? pct(c.change_pct) : c.imports_prior_12m_usd === 0 ? "none the year before" : "no earlier year"),
          esc(c.china_share_pct === null ? "" : c.china_share_pct + "%" + (c.china_share_prior_pct === null || c.china_share_prior_pct === undefined ? "" : " (" + c.china_share_prior_pct + "%)")),
          esc((c.sources || []).map(function (x) { return x.country + " " + x.share_pct + "%"; }).join(", "))];
      }));
    }
    var sl = s.screening_lists || [];
    function day(iso) {
      if (!iso) { return ""; }
      try { return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); } catch (e) { return iso; }
    }
    document.getElementById("screening-deltas").innerHTML = (s.screening || []).map(function (d) {
      var lines = [];
      if (d.added) { lines.push("Added by address country: " + counts(d.added_by_country) + "."); }
      if (d.removed) { lines.push("Removed by address country: " + counts(d.removed_by_country) + "."); }
      edited(lines, d);
      if (d.rekeyed) { lines.push(d.rekeyed + " came back under a new id with the same name and type, counted as the same entry."); }
      batchLine(lines, d);
      return '<div class="row"><div class="row-title"><span>' + esc(d.list_name + ": " + d.added + " added, " + d.removed + " removed" + (d.changed ? ", " + d.changed + " changed" : "") + (d.rekeyed ? ", " + d.rekeyed + " under a new id" : "")) + flag(d.anomaly) + '</span><span class="badge">seen ' + esc(when(d.detected_at)) + '</span></div><div class="small muted">' + esc(d.publisher + ". " + lines.join(" ")) + "</div></div>";
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
      var cl = mn.critical_list;
      if (cl) {
        var listed = mn.import_sources.filter(function (m) { return (m.critical || []).length; }).length;
        var relRows = (mn.reliance || []).filter(function (r) { return (r.critical || []).length; }).length;
        document.getElementById("minerals-list").innerHTML = esc((listed === mn.import_sources.length ? "Every commodity in this table is" : listed + " of these " + mn.import_sources.length + " commodities are") + " on the ") +
          '<a href="' + esc(cl.url) + '" rel="noopener">' + esc(cl.title) + "</a>" +
          esc(" (" + cl.count + " minerals, " + cl.citation + ", published " + day(cl.published + "T12:00:00Z") + "). USGS reports fourteen of them together as rare earths." +
            (cl.not_in_import_sources.length ? " Not in this table: " + cl.not_in_import_sources.join(", ") + "." : "") +
            " In the net import reliance table, " + relRows + " of " + (mn.reliance || []).length + " rows are list minerals; that table has no row for " + cl.not_in_reliance_table.join(", ") + ".");
      }
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

    function paceLine(p, noun) {
      if (!p || p.count === undefined || p.count === null) { return ""; }
      var z = p.z === null || p.z === undefined ? "no baseline yet" : "z " + (p.z >= 0 ? "+" : "") + p.z.toFixed(1);
      return '<div class="row"><div class="row-title"><span>' + esc(p.count + " " + noun + " from " + p.from + " to " + p.to) + "</span>" +
        (p.anomaly ? '<span class="badge badge-warn">unusual</span>' : "") + '</div><div class="small muted">' +
        esc("Median of the " + p.baseline_windows + " windows before: " + p.median + "; " + z + (p.flag_rate !== null && p.flag_rate !== undefined ? "; flag rate " + p.flag_rate : "")) + "</div></div>";
    }
    var hts = s.hts_releases || {};
    var revs = (hts.revisions || []).slice(0, 4).map(function (r) {
      return r.title + " (posted " + r.posted + (r.in_effect_from ? ", in effect from " + r.in_effect_from : "") + ")";
    });
    var years = Object.keys(hts.by_year || {}).slice(-4).map(function (y) { return y + " " + hts.by_year[y]; });
    var pending = (s.signed_actions || []).filter(function (a) { return !a.fr_document; }).map(function (a) {
      return '<div class="row"><div class="row-title"><span><a href="' + esc(a.url) + '" rel="noopener">' + esc("The White House: " + a.title) + '</a></span><span class="badge">' + esc(a.date) + '</span></div><div class="small muted">Signed; not yet in the Federal Register.</div></div>';
    });
    document.getElementById("tariffs-list").innerHTML =
      paceLine(s.tariff_pace, "presidential tariff actions published") +
      paceLine(s.hts_pace, "tariff schedule revisions posted") +
      (revs.length ? '<p class="small muted">' + esc("Newest revisions: " + revs.join("; ") + ". Revisions a year: " + years.join(", ") + ".") + "</p>" : "") +
      pending.join("") +
      (s.signed_error ? '<p class="small muted">The White House feed could not be read this run.</p>' : "");

    var counted = {};
    (s.inspection || []).forEach(function (r) { if (r.counted_only) { counted[r.agency] = (counted[r.agency] || 0) + 1; } });
    var stateWord = { present: "HW-IND-2 met", absent: "HW-IND-2 not met", no_data: "HW-IND-2 not measured" };
    var piRows = (s.inspection || []).filter(function (r) { return !r.counted_only; }).map(function (r) {
      var t = r.text || {}, bits = [];
      bits.push("filed " + (r.filed_at_utc ? when(r.filed_at_utc) : "in the issue of " + r.issue) + (r.publication_date ? ", to be published " + r.publication_date : ""));
      if (t.action && t.action.toLowerCase() !== "notice") { bits.push(t.action); }
      (r.matches || []).slice(0, 3).forEach(function (m) {
        bits.push("scheduled date " + m.date + " (" + (m.days === 0 ? "the day it was filed" : m.days + " days after the filing") + "; " +
          (m.sentence ? "the filing says it was scheduled" : m.basis + ", document " + m.doc) + ")");
      });
      if (r.withdrawn) { bits.push("withdrawn after it was filed"); }
      if (r.text_error) { bits.push("its text could not be read"); }
      var badge = r.indicator_state ? '<span class="badge' + (r.indicator_state === "present" ? " badge-warn" : "") + '">' + esc(stateWord[r.indicator_state]) + "</span>" : "";
      return '<div class="row"><div class="row-title"><span><a href="' + esc(r.url) + '" rel="noopener">' + esc(r.agency + ": " + r.title) + "</a></span>" + badge + '</div><div class="small muted">' + esc(bits.join("; ")) + "</div></div>";
    });
    var piLane = (s.lanes || {}).inspection || {};
    var countedText = Object.keys(counted).map(function (k) { return k + " " + counted[k]; }).join(", ");
    document.getElementById("inspection-list").innerHTML = (piRows.length ? piRows.join("")
      : '<p class="small muted">' + (piLane.status === "ok" ? "No BIS, OFAC or USTR rule, and no USTR notice, on public inspection in the last 30 days."
        : "Public inspection could not be read this run; see Sources and their state.") + "</p>")
      + (countedText ? '<p class="small muted">Also on public inspection in the last 30 days, counted only because their titles can name people and companies: notices, ' + esc(countedText) + ".</p>" : "");

    var labels = { sanctions: "Sanctions lists (OFAC, UN Security Council, EU, UK, France, Canada)", unpress: "UN sanctions committee press releases", inspection: "Public inspection (Office of the Federal Register)", screening: "US screening lists (trade.gov)", minerals: "Mineral import reliance (USGS)", trade: "Mineral imports by country (US Census Bureau)", tariffs: "Tariff schedule revisions (USITC) and signed actions (White House)", controls: "Rules and USTR notices (US Federal Register)", fx: "Exchange rates (ECB)", gem: "Official monthly exchange rates (World Bank)", energy: "Energy prices (EIA)", fao: "Food indices (FAO)", wfp: "Local food prices (WFP via HDX)", baseline: "Country baselines (World Bank)", calendar: "Calendars (Federal Reserve, ECB)" };
    var health = s.health || {};
    var stateText = { fresh: "fresh", late: "late", stale: "stale", failing: "not read", up: "read", never: "never read" };
    document.getElementById("lanes").innerHTML = Object.keys(s.lanes || {}).map(function (k) {
      var l = s.lanes[k], ok = l.status === "ok";
      var note = ok ? "collected " + when(l.fetched_at) : (l.from_previous && l.fetched_at ? "failed; showing the copy from " + when(l.fetched_at) : "failed; no data");
      var subs = Object.keys(health).filter(function (h) { return health[h].lane === k; }).map(function (h) {
        var e = health[h], good = e.state === "fresh" || e.state === "up";
        var bits = [e.detail];
        if (e.data_as_of) { bits.push("newest data " + e.data_as_of); }
        if (e.state === "failing") { bits.push("not read since " + (e.last_ok ? when(e.last_ok) : "it began") + (e.failures > 1 ? " (" + e.failures + " runs)" : "")); }
        (e.warnings || []).forEach(function (w) { bits.push("note: " + w); });
        return '<div class="small"><span class="badge ' + (good ? "" : "badge-warn") + '">' + esc(stateText[e.state] || e.state) + "</span> " + esc(h) + ": " + esc(bits.filter(Boolean).join("; ")) + "</div>";
      }).join("");
      return '<div class="row"><div class="row-title"><span>' + esc(labels[k] || k) + '</span><span class="badge ' + (ok ? "" : "badge-warn") + '">' + esc(ok ? "current" : "not current") + '</span></div><div class="small muted">' + esc(note) + "</div>" + subs + "</div>";
    }).join("");
  }

  fetch("data/snapshot.json")
    .then(function (r) { return r.json(); })
    .then(function (s) {
      render(s);
      if (T) {
        var slot = document.getElementById("time-settings");
        if (slot) { T.mountSettings(slot); }
        T.onChange(function () { render(s); });
      }
    })
    .catch(function () { document.getElementById("asof").textContent = "The data could not be loaded."; });
})();
