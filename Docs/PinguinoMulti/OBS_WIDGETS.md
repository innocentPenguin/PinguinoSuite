# PinguinoMulti OBS widgets (Synchra replacement)

Two browser sources served by Multi itself, separate from the app UI:

| Address | What |
|---|---|
| `http://127.0.0.1:8766/obs/chat` | Chat widget (messages, badges, notices) |
| `http://127.0.0.1:8766/obs/activity` | Activity widget (follow / redeem / sub / gift / cheer / raid rows) |

Editor with live test preview: Multi > chat page > Settings > "OBS chat widget" / "OBS activity widget", or `/?type=obs&widget=chat|activity`.
Settings change in OBS instantly (WebSocket `obs.changed`), no refresh.

## Settings (Synchra field names)
size (xs..xxl), canvas_scale, text_color, text_shadow_color, background_color/opacity, border_width/color/radius, font_family_id,
message_fade_duration_seconds, message_delay_seconds, ignore_names, provider_logo, badges, username_colon, notices, message_order (bottom/top),
message_alignment, providers, style_type (simple/bubble/boxed), entrance_animation_type (none/fade/slide/pop), custom_css.
Ours on top: max_messages, accent_color, name_color_mode; activity: types, show_age.
CSS classes for custom CSS: `.chat-message-container .chat-username .chat-text .chat-badge .chat-provider .chat-notice`,
activity `.activity-row .act-pill .act-user .act-chip .act-age`.

## Import / export
Import accepts a Synchra widget export (`{"kind":"synchra.widget","settings":{...}}`) or the bare settings object; export writes the same shape.
Reference: `Docs/imports/synchra-chat-widget.json` (Ivan's export) is the first-run default for the chat widget, with its bot ignore list and Unkempt CSS.
Presets: Ivan (saved Synchra look), Simple, Penguino, Big and readable (chat); Penguino, Minimal (activity).

## Notes
- Ignore list (nightbot, StreamElements, PinguinoB0t, ...) and Multi's muted viewers never reach OBS. Activity rows come from event messages (Twitch events + Host follow/redeem feed).
- Settings stored in Multi's kv (`obs:chat`, `obs:activity`); no secrets.
- Custom CSS `@import` loads web fonts (Ivan's Typekit font needs internet in OBS).

## Dashboard (Synchra-style app layout)
`/?type=dash` (also Settings panel > Dashboard): profile / edit layout / add / lock bar, source tabs (platform logo, channel, status dot with tooltip, menu), Activity Feed panel (alerts bar: pause, next, skip, show all; rows with age, platform logo, type pill, user, chips such as "13 viewers" / "25 points", links under redeems, row menu), Chat panel (date divider, logos, badges, name colours, dimmed notices, message box with ONE platform picker, emoji, send), Ctrl+K search, per-panel settings gear (opens the Settings panel) and pop-out (`&panel=chat|activity`).
Layout choices are remembered in this browser (localStorage). "Alerts" pause queues new activity rows; next/skip/all work on that queue. Alert sounds/animations on stream belong to the Host, not Multi.
Not done: ban/unmod notices (needs moderation events from Twitch), custom emote picker.

## Moderation notices (Host feed)
Multi reads `ban`, `shoutout` (and `unban`/`unmod`/`mod` once the Host emits them) from the Host activity feed. Rows read "<moderator> banned <user>" when the item carries `moderator`, else "<user> was banned / timed out". They show dimmed inline in chat (dashboard + OBS chat notices) and as pills in the activity feed/widget. Never scored or dinged.
Ask to the Host (02): include `moderator` in ban items (ctx already has it, HostLatest.Record drops it) and emit `unban`, `mod`, `unmod` (EventSub channel.unban, channel.moderator.add/remove, or channel.moderate).

## Dashboard profiles
Saved on the server (kv `dash` in Multi's data dir): GET/POST /api/dash, POST /api/dash/active, DELETE /api/dash/{name}. Built-ins: Default, Chat only, Wide chat. Layout edits save into the active profile. Only the lock stays per browser.

## Widget editor
Tabs: Theme (presets), General, Appearance, Timing, Custom CSS; URL/export/import always on top.

## Follow alert (`/obs/follow`, editor `/?type=obs&widget=follow`)
One alert at a time (queued), Synchra-style options: size, canvas scale, font, colours, box/border, entrance animation (fade/slide/pop/bounce), custom CSS (`.follow-alert .follow-text .follow-user .follow-image .follow-tag`), show-for seconds, gap, text templates (`{user}`), optional image/GIF, sound (built-in chime or your own file address, volume; OBS: tick "Control audio via OBS").
- New follow: alert plus sound.
- Refollow (`flags: ["refollow"]`, from the Host follow item field `refollow: true`; missing = false): smaller alert, tagged "refollow", NO sound; can be turned off entirely.
- /obs/activity and the dashboard feed show a small "refollow" chip on those rows.
- The widget only reacts to live follows (no replay on reload). Test buttons in the editor preview: new follow, refollow, sound.

## Dashboard: viewer counts, text size, resizing, split halves
- **Live viewers**: `viewers.py` polls every 30 s (Twitch Helix streams, YouTube concurrentViewers, TikTok room count) and pushes `{"type":"viewers","counts":{...}}` on the WebSocket (also in `hello`, and `GET /api/viewers`). The dashboard shows `👁 N` on each source tab and a total in the top bar; blank when a platform is offline or gives no number. Needs a live stream; Kick/Discord have none.
- **Text size**: `A−` / `A+` in each panel header (10-40 px), saved with the profile.
- **Resize**: unlock (padlock) and drag the bar between the two panels; saved with the profile. Edit layout swaps/removes panels; each panel pops out to its own window.
- **Split chat in halves** (⫻ button in the Chat header): flow (older rows continue in the first half, newest in the second; side by side or top/bottom), one platform per half, or chat vs events. "Open the two halves as separate windows" reuses the pane split (/api/splits/apply) for two monitors. Saved with the profile.
