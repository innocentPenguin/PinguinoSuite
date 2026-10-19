# Chat look editor and split chat (increment 2)

## Editor (`/?type=style`)
Layout: a sticky, big live preview on the right (sample messages or your real recent chat; dark / light / over-a-game / see-through backdrops) and,
on the left, five numbered steps: 1 pick a look (10 ready-made, each shown as a real mini preview), 2 make it yours (font, size, colours, background,
highlight strength, event animation, platform marker, spacing buttons), 3 highlights per person type / stream event (switch, one colour, strength,
"more" for every detail), 4 words to highlight, 5 save / undo / export / import / reset. Advanced (weights, line height, emote size, corner roundness,
logo sizes and platform colours) is tucked away. Everything saves by itself.

Ready-made looks: Pinguino, Compact, Big and readable, Paper (light), High contrast, Minimal, Neon, Cozy, Terminal, On-stream overlay.
Your own looks: saved by name (30 max), kept in the module database. Undo goes back to before the last look picked / imported / reset.
Export is plain JSON text (`{"pinguino_chat_look":1,"style":{...}}`), import validates everything.

New settings: `base.intensity` (0-250 %, scales all highlight backgrounds), `base.anim` (none / pulse / slide-in, stream events only).

## Panes and split modes
A pane is a chat window with its own filter and look: `/?type=chat&pane=<id>`.
Split modes (Setup > Pop-out and split chat):
| Mode | A (top / left) | B (bottom / right) |
|---|---|---|
| flow | older rows continue here | newest messages |
| platform | the platforms you tick | all the others |
| events | chat only | stream events (sub, raid, gift, follow...) |
| people | streamer, mods, VIPs | everyone else |
Each half has its own look overrides (size, background colour and strength, marker, times, highlight strength) layered over the main look.
Pane filters also apply to the priority-card strip. Panes live in `/api/panes`, split setup in `POST /api/splits/apply`.

## Pop-out
Chat and the editor each have a Pop out button; split halves open as pop-outs too. Position is remembered per window label
(`POST /api/geom/<label>`, saved every 3 s by the page itself). Real windows, monitor placement and always-on-top need the shell: see SHELL_WINDOW_SPEC.md.
In a plain browser they open as pop-up windows (allow pop-ups).

## Not built yet
Event criteria beyond the four modes (custom per-pane rules UI), per-viewer look overrides, scheduled looks (e.g. different look per scene),
OBS popout platform markers.
