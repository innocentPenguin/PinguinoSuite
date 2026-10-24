# Tomorrow: Twitch + TikTok + YouTube at once (steps for Ivan)

Priority order: Twitch, then TikTok, then YouTube. Each platform runs on its own: if one fails, the other two keep working.
Sending the video to three platforms (OBS multistream) is your side and is not covered here. Multi only reads chat and alerts.
**Nothing in this guide asks you to go live to test.** The checks below are done from another account or with the platform's own preview, before you press Start Streaming.

## What Multi needs, per platform

| Platform | Needed | How it reads | If it fails |
|---|---|---|---|
| Twitch | already connected | official, about 1 s | nothing else is affected |
| TikTok | your `@handle`, "Read my TikTok LIVE chat" ticked | unofficial (TikTokLive 7.0.1, Euler Stream sign server) | only TikTok chat/gifts are missing |
| YouTube | your `@handle` in `youtube_channel` (no sign-in to read) | unofficial fast feed, 1-3 s | falls back to the official API (about 10 s) if you signed in with Google |

## Steps, in order

### A. Before you stream (any time today, about 10 minutes)
1. **Restart Multi** (100 does this) so the TikTok and chat changes are loaded. Open the Multi launcher.
2. **Twitch**: check the Twitch card says connected. Nothing to do.
3. **TikTok**: in the launcher TikTok card tick **Read my TikTok LIVE chat**, type your **@handle** (the one you stream from), press **Save**. Status should read `@handle is not live yet` (waiting). If it says `Set the TikTok @handle you stream from`, the handle is empty.
4. **YouTube**: in the YouTube card fill **channel** with your `@handle` (or `UC...` id or channel link). Optional: **live video** to pin one stream. Status reads "not live on YouTube right now" until you are live: that is correct.
5. **YouTube sign-in is optional**. Only do it (docs/IVAN_SETUP.md, section 2: Google project, OAuth client, consent screen set to Production) if you want Multi to send messages, moderate, or have the official fallback. Reading chat does not need it.
6. Open the unified chat window (`/?type=chat`). It keeps its history through restarts, and hides bots and `!` commands (side panel toggle "Show bots and !commands" if you want them).

### B. Check each platform's chat reaches the dashboard BEFORE going live
Do these one at a time, in the priority order, and only once that platform is actually live (or in its own pre-live/preview state if it has one). You must NOT start a real public stream just for this.
- **Twitch**: post a line from another account. It should appear in the Multi chat window within about 1-2 seconds, tagged Twitch.
- **TikTok**: the card must turn `connected: @handle (unofficial)` within about 1 minute of your TikTok LIVE starting. Post a comment from another account: it appears tagged TikTok. A first-time chatter should trigger the first-time ding.
- **YouTube**: when your YouTube stream is live the card shows `connected: live chat <id> (fast mode)`. Post from another account: it appears within about 3 seconds. If it only appears after about 10 s the card is in `api` fallback: still working, just slower.

If a platform does not show up, leave it and carry on: read "What happens when something fails" below. Do not delay the other two.

### C. Once all three are live
1. Watch the unified chat for a minute: all three platform tags should appear.
2. TikTok: a follow should show an alert; a streakable gift should alert **once**, at the end of its streak (coins = diamonds x count). Likes are not alerts.
3. Dings and the chat pop fire for new chatters on all three (TikTok is added automatically while it is enabled).

## What happens when something fails (graceful degradation)
- **TikTok sign server (Euler Stream) down or rate limited**: only TikTok degrades. The card shows reconnecting and retries (10 s, doubling up to every 5 minutes). TikTok chat and gifts are missing until it recovers. Twitch and YouTube are unaffected.
- **TikTok not live yet**: waiting, retries every 30-60 s. Normal, not an error.
- **YouTube fast feed breaks** (YouTube changed something): after `youtube_innertube_fallback_min` minutes (5) Multi switches to the official API if you signed in with Google, about 10 s behind and using quota (about 5.5 hours of chat per day). Without a Google sign-in YouTube chat is simply missing; Twitch and TikTok are unaffected. You can force `youtube_read_mode` = `api`.
- **TikTok and YouTube fast mode are unofficial** and can break without notice. They are read-only anyway.
- **Kick**: not part of tomorrow.
- **Multi restarts**: chat history is kept, platforms reconnect on their own.

## Not tested yet (be aware)
TikTok and the YouTube fast feed have been tested with recorded/fake events and the real library classes, never against a real live stream. The first live minutes tomorrow are the real test. If something looks wrong, tell 100 what the card says.
