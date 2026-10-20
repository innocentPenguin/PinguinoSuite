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
