/* PinguinoB0t overlay fit options, shared by every overlay (queue, players, players_vertical, wheel, subroll ...).
   Add  <script src="overlay-options.js"></script>  at the end of <body>. With NO options set nothing is touched: every overlay looks exactly as before.

   WHERE the options come from (later wins):  1) Data\runtime\overlay_options.json  "*" (all overlays)  2) the same file, this overlay's name (file name without .html)  3) the URL.
   The Host serves the saved ones (GET /api/overlay-options?name=queue&js=1, edit with POST /api/overlay-options) and this page re-reads them every 5 s, so a change shows live in OBS.
   OPTIONS (URL form  ?scale=1.2&anchor=tr&pad=30 ):
     scale     0.2 - 4     size of the whole overlay (1 = as designed)
     anchor    tl tc tr cl c cr bl bc br   which corner/edge stays put while it grows or shrinks (default tl)
     pad       px          safe margin: the picture is moved this far away from the anchored edge(s)
     x, y      px          nudge right / down (negative = left / up)
     maxw maxh px          never wider / taller than this on screen: scaled down until it fits
     fit       1           scale down until the whole overlay fits inside the safe area (viewport minus pad)
     overflow  hidden|visible    what happens to anything outside the source (hidden crops it)
     preset    safe | tv | fit-safe   ready-made safe areas: safe = 5% margin (title-safe), tv = 10% margin (action-safe), fit-safe = 5% margin + scaled down to fit. pad / fit given next to it win.
     guides    1           draw the guides (viewport, safe area, overlay box, size label). Use with ?preview=1 in a normal browser tab.
     overlay   name        use another overlay name for the saved options (default: the file name)
   Works by moving/scaling the page body (transform), so it never edits an overlay's own layout code. */
(function () {
  "use strict";
  var Q = new URLSearchParams(location.search);
  var NAME = String(window.OVERLAY_NAME || Q.get("overlay") || location.pathname.split("/").pop().replace(/\.html?$/i, "") || "overlay").toLowerCase().replace(/[^a-z0-9_-]/g, "");
  var HOST = /[?&]host=([^&]+)/.test(location.search) ? decodeURIComponent(RegExp.$1) : (location.protocol.indexOf("http") === 0 ? location.origin : "http://127.0.0.1:8770");
  var ANCHORS = ["tl", "tc", "tr", "cl", "c", "cr", "bl", "bc", "br"], saved = {}, fetching = false, guideEl = null;

  function num(v, lo, hi) { if (v === null || v === undefined || v === "") return null; var d = Number(v); if (!isFinite(d)) return null; return Math.max(lo, Math.min(hi, d)); }
  function clean(src) {
    var o = {}, d;
    if ((d = num(src.scale, 0.2, 4)) !== null) o.scale = d;
    if ((d = num(src.pad, 0, 600)) !== null) o.pad = d;
    if ((d = num(src.x, -4000, 4000)) !== null) o.x = d;
    if ((d = num(src.y, -4000, 4000)) !== null) o.y = d;
    if ((d = num(src.maxw, 50, 8000)) !== null) o.maxw = d;
    if ((d = num(src.maxh, 50, 8000)) !== null) o.maxh = d;
    if (src.fit !== undefined && src.fit !== null && src.fit !== "") o.fit = (String(src.fit) === "1" || String(src.fit).toLowerCase() === "true") ? 1 : 0;
    var a = String(src.anchor || "").toLowerCase(); if (ANCHORS.indexOf(a) >= 0) o.anchor = a;
    var pr = String(src.preset || "").toLowerCase(); if (pr === "safe" || pr === "tv" || pr === "fit-safe") o.preset = pr;
    var ov = String(src.overflow || "").toLowerCase(); if (ov === "hidden" || ov === "visible") o.overflow = ov;
    return o;
  }
  function fromUrl() { var s = {}; ["scale", "anchor", "pad", "x", "y", "maxw", "maxh", "fit", "overflow", "preset"].forEach(function (k) { if (Q.has(k)) s[k] = Q.get(k); }); return clean(s); }
  function effective() {
    var o = clean(saved || {}), u = fromUrl(); for (var k in u) o[k] = u[k];
    if (o.preset) {   // presets only fill what is not set explicitly
      var m = Math.min(window.innerWidth, window.innerHeight);
      if (o.pad === undefined) o.pad = Math.round(m * (o.preset === "tv" ? 0.10 : 0.05));
      if (o.fit === undefined && o.preset === "fit-safe") o.fit = 1;
    }
    return o;
  }

  function box(el, css) { el.style.cssText = "position:fixed;pointer-events:none;box-sizing:border-box;" + css; return el; }
  function guides(o, rect) {
    if (Q.get("guides") !== "1" && Q.get("guides") !== "true") return;
    if (!guideEl) { guideEl = document.createElement("div"); guideEl.id = "ovo-guides"; guideEl.style.cssText = "position:fixed;left:0;top:0;right:0;bottom:0;z-index:2147483647;pointer-events:none"; document.documentElement.appendChild(guideEl); }
    var vw = window.innerWidth, vh = window.innerHeight, pad = o.pad || 0, sx = pad > 0 ? pad : Math.round(Math.min(vw, vh) * 0.05);
    guideEl.innerHTML = "";
    var m = function (css) { var e = document.createElement("div"); guideEl.appendChild(box(e, css)); return e; };
    m("left:0;top:0;right:0;bottom:0;border:2px dashed #ff3b30");                                        // the source (viewport)
    m("left:" + sx + "px;top:" + sx + "px;right:" + sx + "px;bottom:" + sx + "px;border:2px dashed #34c759");   // safe area
    m("left:" + (vw / 2 - 12) + "px;top:" + (vh / 2) + "px;width:24px;height:0;border-top:1px solid #ffffff99"); m("left:" + (vw / 2) + "px;top:" + (vh / 2 - 12) + "px;width:0;height:24px;border-left:1px solid #ffffff99");
    if (rect) m("left:" + rect.left + "px;top:" + rect.top + "px;width:" + rect.width + "px;height:" + rect.height + "px;border:2px solid #0ac8ff");   // where the overlay body ends up
    var t = m("left:" + (sx + 6) + "px;top:" + (sx + 6) + "px;background:#000c;color:#fff;font:12px/1.35 Consolas,monospace;padding:4px 8px;border-radius:4px;white-space:pre");
    t.textContent = NAME + "  " + vw + " x " + vh + "\nscale " + (o.scale || 1) + "  anchor " + (o.anchor || "tl") + "  pad " + pad + "  x/y " + (o.x || 0) + "/" + (o.y || 0) + (o.maxw || o.maxh ? "  max " + (o.maxw || "-") + "x" + (o.maxh || "-") : "") + (o.fit ? "  fit" : "") + "\nred = source, green = safe area, blue = overlay";
  }
  function apply() {
    var o = effective(), b = document.body, h = document.documentElement; if (!b) return;
    var any = Object.keys(o).length > 0;
    if (!any) { if (b.getAttribute("data-ovo")) { b.style.transform = ""; b.style.transformOrigin = ""; b.style.minHeight = ""; b.removeAttribute("data-ovo"); } guides(o, null); return; }
    var vw = window.innerWidth, vh = window.innerHeight, pad = o.pad || 0, s = o.scale || 1, a = o.anchor || "tl";
    if (o.maxw) s = Math.min(s, o.maxw / vw);
    if (o.maxh) s = Math.min(s, o.maxh / vh);
    if (o.fit) s = Math.min(s, (vw - 2 * pad) / vw, (vh - 2 * pad) / vh);
    s = Math.max(0.05, s);
    var row = a === "c" ? "c" : a.charAt(0), col = a === "c" ? "c" : a.charAt(1);
    var ox = col === "l" ? "0%" : col === "r" ? "100%" : "50%", oy = row === "t" ? "0%" : row === "b" ? "100%" : "50%";
    var tx = (col === "l" ? pad : col === "r" ? -pad : 0) + (o.x || 0), ty = (row === "t" ? pad : row === "b" ? -pad : 0) + (o.y || 0);
    b.setAttribute("data-ovo", "1"); b.style.minHeight = "100vh"; b.style.transformOrigin = ox + " " + oy;
    b.style.transform = "translate(" + tx + "px," + ty + "px) scale(" + s.toFixed(4) + ")";
    if (o.overflow) h.style.overflow = o.overflow;
    var r = b.getBoundingClientRect(); guides(o, { left: r.left, top: r.top, width: r.width, height: r.height });
  }
  function load() {
    if (fetching) return; fetching = true;
    var sc = document.createElement("script");
    sc.src = HOST + "/api/overlay-options?js=1&name=" + encodeURIComponent(NAME) + "&t=" + Date.now();
    sc.onload = function () { fetching = false; var j = window.OVERLAY_OPTIONS; if (j && j.ok && j.options) { var n = JSON.stringify(j.options); if (n !== JSON.stringify(saved)) { saved = j.options; apply(); } } sc.remove(); };
    sc.onerror = function () { fetching = false; sc.remove(); };   // Host not running: the URL options still work
    document.body.appendChild(sc);
  }
  window.OverlayOptions = { name: NAME, get: effective, apply: apply };
  window.addEventListener("resize", apply);
  apply(); load(); setInterval(load, 5000);
})();
