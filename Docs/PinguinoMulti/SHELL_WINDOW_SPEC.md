# Pop-out windows: what Multi needs from the shell (Unit 01)

Multi opens its own extra windows (chat, look editor, split-chat halves) by asking the shell with `parent.postMessage`. Everything works in a
plain browser too (it falls back to `window.open` pop-ups), so this spec is only about the app giving real windows.

## Messages Multi sends (from an iframe inside the shell)
```js
parent.postMessage({pinguino: 'window', op: 'monitors'}, '*')       // reply: {pinguino:'monitors', monitors:[{index,name,width,height,x,y,primary}]}
parent.postMessage({pinguino: 'window', op: 'open',
  label: 'pane-split-a',            // stable id; opening an existing label focuses it instead of making a second window
  url: 'http://127.0.0.1:8766/?type=chat&pane=split-a&pop=pane-split-a',
  title: 'Chat (newest messages)',
  remember: true,                   // shell persists x/y/w/h/monitor per label and restores them next time
  always_on_top: false,
  monitor: 1,                       // optional: monitor index to open on
  place: 'full',                    // optional: with `monitor`, fill that monitor's work area (used when there is no remembered position)
  bounds: {x, y, w, h},             // optional: last known position Multi remembers (virtual-desktop pixels); wins over `place`
  size: {w: 560, h: 520}}, '*')     // optional default size when nothing else is known
parent.postMessage({pinguino: 'window', op: 'close', label: 'pane-split-a'}, '*')
```
Labels used: `chat-main`, `look-editor`, `pane-split-a`, `pane-split-b`.

## What the shell should do
1. Real native windows (frameless or framed, user's choice) that can be dragged to any monitor and resized.
2. `remember: true`: persist geometry and monitor by `label`; restore it on the next open. If the saved monitor is gone, snap to the nearest monitor
   and restore the original when it comes back (same rule as the Multi window manager).
3. `always_on_top` per window, changeable at runtime (optional extra: `{op:'set', label, always_on_top}`).
4. Optional: tell Multi when a window moves (`{pinguino:'window.moved', label, x,y,w,h}`); Multi already saves position itself every 3 s from
   `screenX/screenY/outerWidth/outerHeight` into `POST /api/geom/<label>`, so this is a nice-to-have only.
5. Optional: `op: 'list'` so the setup page can show which pop-outs are open.

Security: Multi only sends loopback URLs of its own origin; the shell should refuse other origins for `op:'open'`.
