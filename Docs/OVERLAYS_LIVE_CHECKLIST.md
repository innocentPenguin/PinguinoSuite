# Overlays - live check after the next Host restart

Owner: 13 Overlays. Never go live in OBS to run this: use the browser pane / a plain browser tab on the Host port (8770). Nothing here needs a stream.
The static pages (`?part=` modes, wheel look) are served from disk and work before the restart; the items marked **[restart]** need the rebuilt Host.

## 1. Host is up with the new build
1. `http://127.0.0.1:8770/api/scene-widgets` lists 20 widgets incl. `wheel_only, wheel_teams, players_teams, players_header, queue_list, queue_idle, customs_status, customs_info`, all `available:true`. **[restart]**
2. `http://127.0.0.1:8770/api/scene-layouts?profile=h` answers with `currentGame` and `resolvedBy`. **[restart]**
3. `http://127.0.0.1:8770/api/overlay-options/health` has an empty `missing` list.

## 2. Wheel (37d214b) - needs a running tournament wheel session (mod page /mod/wheel, or a dry spin)
- [ ] Spin eases out slowly at the end (tail setting in Suite > Tune > Tournament wheel), no hard stop.
- [ ] An unrevealed slot shows `???`, the real name appears when the pick lands.
- [ ] Team box is double width; names do not clip.
- [ ] Portrait source (`wheel.html?layout=vertical`, 1080x1920): wheel on top, team box below.
- [ ] `wheel.html?part=wheel` shows only the wheel and title, centred, no camera gap. `?part=teams` shows only the team box, filling the source.

## 3. Scenes
1. `http://127.0.0.1:8770/scene-editor.html` loads both profiles, saves, activates. **[restart]**
2. In the editor switch on `wheel_only` and `wheel_teams` (instead of `wheel`); both are takeover widgets: other widgets hide while the wheel has something to show (stage polls /api/wheel/public every 2 s), come back within ~1 s of it ending.
3. Switch on `players_teams` or `queue_list` etc. and check each draws only its part (`players_header` = MATCH READY block, `queue_idle` = leaderboards/subs cards, `customs_status` / `customs_info` = the two halves of the customs card).
4. HUD widgets (`goal, latest, subfooter, chat, customs, nowplaying`) are off by default; switch each on once and check data shows. `nowplaying` is blank unless the Spotify module (8771) runs.
5. Open `http://127.0.0.1:8770/scene.html?profile=h&preview=1` (1920x1080) and `?profile=v` (1080x1920): outlines match the editor.

## 4. Game fallback (setgame) **[restart]**
- Tag layouts with games in the editor (Clone to games), switch **Auto-switch** on.
- Change the Twitch category (channel editor or Twitch): within ~35 s (bot poll 30 s + Host 5 s) `GET /api/scene-layouts?profile=h` shows `currentGame` = the new category and `resolvedBy:"game"` when a layout carries that tag. The stage follows within 5 s.
- Master View's activity selector still wins when you set the game yourself: the Host only reacts to a *change* of the Twitch category, never re-asserts it.
- Audit line: `ChannelControl.Audit scenes/setgame twitch category <name>`.

## 5. OBS (by hand, with the stream OFF)
- [ ] Two browser sources exist: `http://127.0.0.1:8770/scene.html?profile=h` (1920x1080) and `?profile=v` (1080x1920). If not, create them; nothing creates them for you.
- [ ] Alerts stay a standalone 800x600 source (alerts widget off).
- [ ] Remember the default layout positions are first guesses: arrange them in the editor.

## Known / not mine
- `PinguinoB0t/overlays/live_state.js` is bot-generated runtime output but tracked in git: do not commit it (proposal to 10: `git rm --cached` + .gitignore).
- `moderator:read:chatters` needs Ivan's streamer re-sign-in.
- Tests (sim Host): `Tools/test-host-scenes.py`, `test-host-wheelpublic.py`, `test-host-gamewatch.py` (build a temp copy of PinguinoHost, pass its dll).
