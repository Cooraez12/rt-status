(function () {
  var WORDS = { up: "Working", slow: "Slow", down: "Down" };
  var RANK = { up: 0, slow: 1, down: 2 };
  var data = { status: null, history: null, incidents: [] };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function get(name) {
    return fetch("data/" + name + "?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }
  function when(iso) {
    var d = new Date(iso);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function ago(iso) {
    var m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    var h = Math.round(m / 60);
    return h + (h === 1 ? " hour ago" : " hours ago");
  }
  function dayKey(d) { return d.toISOString().slice(0, 10); }

  function banner() {
    var b = document.getElementById("banner"), h = document.getElementById("headline"), p = document.getElementById("checked");
    var s = data.status;
    if (!s) { b.className = "banner b-wait"; h.textContent = "We could not load the latest status"; p.textContent = "Please refresh in a minute."; return; }
    var open = data.incidents.filter(function (i) { return !i.resolved_at; }).length;
    var worst = s.components.reduce(function (w, c) { return RANK[c.status] > RANK[w] ? c.status : w; }, "up");
    var stale = Date.now() - new Date(s.checked_at) > 45 * 60000;
    if (worst === "down") { b.className = "banner b-down"; h.textContent = "Some services are down"; }
    else if (worst === "slow") { b.className = "banner b-slow"; h.textContent = "Some services are slow"; }
    else if (open) { b.className = "banner b-slow"; h.textContent = "We are working on an issue"; }
    else { b.className = "banner b-up"; h.textContent = "All services are working"; }
    p.textContent = "Last checked " + ago(s.checked_at) + (stale ? ". Checks are delayed; the status may be out of date." : ".");
  }

  function components() {
    var box = document.getElementById("components");
    box.textContent = "";
    var s = data.status;
    if (!s) { box.appendChild(el("div", "empty", "Status is not available right now.")); return; }
    var days = window.matchMedia("(max-width:600px)").matches ? 30 : 90;
    var today = new Date();
    s.components.forEach(function (c) {
      var hist = (data.history && data.history[c.id] && data.history[c.id].days) || {};
      var row = el("div", "comp");
      var top = el("div", "row");
      var left = el("div");
      left.appendChild(el("div", "name", c.name));
      left.appendChild(el("div", "about", c.about));
      top.appendChild(left);
      top.appendChild(el("div", "state s-" + c.status, WORDS[c.status]));
      row.appendChild(top);

      var bars = el("div", "bars"), n = 0, ok = 0;
      for (var i = days - 1; i >= 0; i--) {
        var d = new Date(today.getTime() - i * 86400000), k = dayKey(d), v = hist[k], bar = el("i");
        var label = d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + ": ";
        if (v && v.n) {
          n += v.n; ok += v.up + v.slow;
          bar.className = v.down > 1 ? "down" : (v.slow || v.down) ? "slow" : "up";
          label += (Math.floor(((v.up + v.slow) / v.n) * 10000) / 100).toFixed(2) + "% working";
        } else { label += "no data"; }
        bar.title = label;
        bars.appendChild(bar);
      }
      bars.setAttribute("aria-label", c.name + " daily history");
      row.appendChild(bars);
      var legend = el("div", "legend");
      legend.appendChild(el("span", null, days + " days ago"));
      legend.appendChild(el("span", null, n ? (Math.floor((ok / n) * 10000) / 100).toFixed(2) + "% working" : ""));
      legend.appendChild(el("span", null, "Today"));
      row.appendChild(legend);
      box.appendChild(row);
    });
  }

  function incidents() {
    var box = document.getElementById("incidents");
    box.textContent = "";
    var list = data.incidents || [];
    if (!list.length) { box.appendChild(el("div", "empty", "No incidents in the last 30 days.")); return; }
    list.forEach(function (i) {
      var row = el("div", "inc");
      var h = el("h3", null, i.title);
      h.appendChild(el("span", "tag " + (i.resolved_at ? "t-done" : "t-open"), i.resolved_at ? "Resolved" : "Ongoing"));
      row.appendChild(h);
      row.appendChild(el("div", "meta", "Started " + when(i.opened_at) + (i.resolved_at ? " · Resolved " + when(i.resolved_at) : "")));
      if (i.text) row.appendChild(el("div", "txt", i.text));
      (i.updates || []).slice().reverse().forEach(function (u) {
        var up = el("div", "upd");
        up.appendChild(el("div", "meta", "Update " + when(u.at)));
        up.appendChild(el("div", "txt", u.text));
        row.appendChild(up);
      });
      box.appendChild(row);
    });
  }

  function render() { banner(); incidents(); components(); }

  function load() {
    Promise.all([get("status.json"), get("history.json"), get("incidents.json")]).then(function (r) {
      data.status = r[0]; data.history = r[1]; data.incidents = r[2] || [];
      render();
    });
  }
  load();
  setInterval(load, 60000);
  window.matchMedia("(max-width:600px)").addEventListener("change", components);
})();
