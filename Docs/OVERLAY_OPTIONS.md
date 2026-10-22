# Overlay fit options (OBS)

Every overlay in `PinguinoB0t\overlays` loads one shared script, `overlay-options.js`, so a fit problem in OBS is fixed with a setting, not by editing HTML. With nothing set, every overlay looks exactly as before.

## Quick use (in the OBS browser-source URL)
`queue.html?scale=1.2` · `players.html?scale=0.9&anchor=tc&pad=30` · `wheel.html?fit=1&pad=40`

| option | meaning |
|---|---|
| `scale` 0.2-4 | size of the whole overlay |
| `anchor` tl tc tr cl c cr bl bc br | the point of the source the overlay grows/shrinks from (default `tl`; a card on the right side wants `tr`) |
| `pad` px | safe margin, moves the picture away from the anchored edge(s) |
| `x`, `y` px | nudge right / down |
| `maxw`, `maxh` px | never bigger than this on screen (scaled down to fit) |
| `fit=1` | scale down until everything fits inside the safe area (source minus `pad`) |
| `overflow=hidden\|visible` | crop or show anything outside the source |
| `guides=1` | with `?preview=1` in a normal browser tab: red = source, green = safe area (pad, or 5%), blue = overlay box, plus a size label |

## Saved settings (no URL editing)
`Data\runtime\overlay_options.json`: `{"*": {"pad": 20}, "queue": {"scale": 1.2, "anchor": "tr"}}` (key = file name without `.html`; `*` = every overlay; the URL wins over the file). The overlay re-reads it every 5 s, so changes show live in OBS.
Host API (for the Suite): `GET /api/overlay-options[?name=queue]`, `POST /api/overlay-options {"name":"queue","options":{"scale":1.2}}` (a `null` value removes an option, `"options":null` clears the overlay). Values are validated and clamped.

## Notes
- It moves/scales the page body with a transform; the overlays' own layout code is untouched. `subroll.html` keeps its own `size` option too (text size); `scale` scales the whole overlay.
- Fitting steps: 1) open the overlay in a browser with `?preview=1&guides=1`, 2) pick `scale`/`anchor`/`pad` until the blue box sits inside the green one, 3) save them in `overlay_options.json` (or the URL).
