/* Headwind UI — renders snapshot.json */
(function () {
  "use strict";

  function render(snap) {
    var san = snap.sanctions || [];
    var ctl = snap.controls || [];
    var com = snap.commodities || [];

    var tiles = document.getElementById("tiles");
    if (tiles) {
      var vCount = san.reduce(function (s, x) { return s + (x.vessels_added || 0); }, 0);
      tiles.innerHTML = [
        '<div class="tile"><span class="k">OFAC Batches</span><span class="v">' + san.length + "</span></div>",
        '<div class="tile"><span class="k">Designated Vessels</span><span class="v">' + vCount + "</span></div>",
        '<div class="tile"><span class="k">Tracked Rule Deadlines</span><span class="v">' + ctl.length + "</span></div>",
        '<div class="tile"><span class="k">Commodity Indices</span><span class="v">' + com.length + "</span></div>"
      ].join("");
    }

    var sanEl = document.getElementById("sanctions");
    if (sanEl) {
      sanEl.innerHTML = san.map(function (s) {
        var vList = (s.vessels || []).map(function (v) {
          return v.name + " (IMO " + v.imo + ", MMSI " + v.mmsi + ")";
        }).join(" · ");
        return '<div class="row">' +
          '<div class="row-title"><strong>' + s.title + '</strong> <span class="badge badge-warn">+' + s.entities_added + ' entities / ' + s.vessels_added + ' vessels</span></div>' +
          '<div class="small">' + s.summary + '</div>' +
          (vList ? '<div class="small muted">Vessels: ' + vList + '</div>' : '') +
        '</div>';
      }).join("");
    }

    var ctlEl = document.getElementById("controls");
    if (ctlEl) {
      ctlEl.innerHTML = ctl.map(function (c) {
        var warn = c.days_to_deadline <= 14;
        return '<div class="row">' +
          '<div class="row-title"><strong>' + c.agency + ': ' + c.title + '</strong> <span class="badge ' + (warn ? "badge-warn" : "") + '">' + c.deadline_date + ' (' + c.days_to_deadline + 'd)</span></div>' +
          '<div class="small">' + c.summary + '</div>' +
        '</div>';
      }).join("");
    }

    var comEl = document.getElementById("commodities");
    if (comEl) {
      comEl.innerHTML = com.map(function (c) {
        var sign = c.mom_pct >= 0 ? "+" : "";
        return '<div class="row">' +
          '<div class="row-title"><strong>' + c.name + ' (' + c.period + ')</strong> <span class="badge">' + c.current_value + ' (' + sign + c.mom_pct + '%)</span></div>' +
          '<div class="small">' + c.summary + '</div>' +
        '</div>';
      }).join("");
    }
  }

  fetch("data/snapshot.json")
    .then(function (r) { return r.json(); })
    .then(render)
    .catch(function () {});
})();
