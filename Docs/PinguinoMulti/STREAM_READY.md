# PinguinoMulti: ready for stream (checked 2026-10-19)

## Verified live on port 8766
- Twitch connected (as `innocentpenguin_`), real messages arriving, emotes show as images (fixed today), badges, bot rows dimmed.
- Reply box (sends to the platform you pick, only that one), priority cards strip (Answered / Reply / Snooze / Dismiss), pins, search, Questions-for-me filter, assist (suggest replies, translate, who-is-this card).
- Settings panel on the chat page (orange tab on the right edge): text size/font/spacing/density/background, platform logos, highlights, sounds, split chat and pop-out.
- Pre-stream list: Twitch pass; Discord, YouTube, TikTok now say "Optional - skipped" (green), never a failure.

## Defaults after this change (needs an Update-Module restart of Multi)
- One saved window ("Chat", main screen) and a ready split (flow: newest in B, older rows continue in A) are created on first run when none exist. Pre-stream "windows" turns green.
- Ding and chat pop are OFF by default with sane volumes when switched on (ding 24 %, returning 50 %, pop Twitch 50 / YouTube 76, master 100 %).
- Follows and channel point redeems from the Host activity feed show as event rows (fixed a bug in that reader today).

## Keys
| Key | Needed? | How |
|---|---|---|
| `MULTI_TWITCH_TOKENS` | **Required** (already stored on this PC, status "connected") | If Twitch ever says "needs auth": Multi > Setup > Twitch card > **Connect Twitch**, sign in as the channel owner, approve. |
| `MULTI_DISCORD_TOKEN` | optional | Discord developer portal bot token, then Setup > Discord card > paste > Save. |
| `MULTI_YOUTUBE_TOKEN` | optional | YouTube OAuth token, then Setup > YouTube card. |
| `MULTI_AI_KEY` | optional (local ranking works without it) | Setup > Smart features > AI settings. |

## Ivan, for tonight (exact clicks)
1. Open Multi chat (Chat page). It should already show Twitch messages. Orange **Settings** tab on the right edge opens the settings.
2. Sounds (optional): Settings > Sounds > tick Twitch under "New-chatter ding" > Save; same under "Chat pop" if wanted. Use the Test buttons first.
3. Second monitor: Settings > Split chat and pop-out > choose how to split and the monitors > **Open split chat** (works inside the app only). Or **Pop out the chat** for one window.
4. Nothing else is required. Tokens for Discord/YouTube/TikTok can wait.

Not verified: real split/pop-out windows on two monitors, sounds at normal volume, YouTube/Discord/TikTok traffic, moderator actions (need extra Twitch scopes, see SITE_SCOPE_PROPOSAL.md).
