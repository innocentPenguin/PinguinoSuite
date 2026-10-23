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

## Presets
`preset=safe` (5% margin), `preset=tv` (10%), `preset=fit-safe` (5% + fit). An explicit `pad`/`fit` next to it wins. Works in the URL and in the saved file.

## Contract for the Suite sliders page (owner: 01)
- `GET /api/overlay-options/schema` -> `{overlays:[...], options:[{key,label,type:number|enum|bool,min,max,step,values,default,help}]}`: draw one control per option, per overlay name (plus `*` for all).
- `GET /api/overlay-options?name=queue` -> `{options:{...merged "*" + queue}}`; `GET /api/overlay-options` -> the raw file (all names).
- `POST /api/overlay-options {"name":"queue","options":{"scale":1.2}}` (token like other POSTs) merges; `null` value removes one option; `"options":null` resets the overlay. Reply = the merged options. Errors: `{ok:false,error}`.
- Overlays pick changes up within 5 s, no reload. For a preview pane embed `<overlay>.html?preview=1&guides=1&mock` (queue/subroll/players have mock data).

## Sub anniversary (Subs! card)
A sub whose subscribe date (month/day) falls within the last day to the next 6 days, with at least 1 full year, gets a pulsing white outline and an "N YR" tag on the Subs! card.

## Pre-stream check

`GET /api/overlay-options/health` -> `{ok, scriptPresent, folder, pages:[{page,hasOptions}], missing:[...]}`.
`ok` is false when `overlay-options.js` is missing from the overlay folder or any overlay page (backup pages are ignored) lacks the `<script src="overlay-options.js">` tag. Call it before going live; `missing` names the pages to fix.

## New-subs idle card

Queue idle item `{"metric":"newsubs","period":"all","days":30,"top":8}` shows subscribers from the last `days` days, newest first (gifted included), titled "NEW SUBS · LAST 30 DAYS", values "N d ago". Config version 3 adds it to existing sequences (backup `.bak-v2`).
