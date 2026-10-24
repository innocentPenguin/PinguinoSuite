# Setting up Kick, YouTube and TikTok in Multi (for Ivan)

## YouTube fast reading (new, no sign-in needed)
Multi now reads YouTube chat through YouTube's own live-chat feed (the one the website uses): about **1-3 seconds** behind, no Google project, no quota. To switch it on put your channel in Multi's settings: `youtube_channel` = `@YourHandle` (or a `UC...` id or channel link), or pin one stream with `youtube_video_id` (id or watch link). If you already signed in with Google and leave both empty, Multi uses the stream your account is broadcasting. It is **unofficial**: YouTube can change it without notice. Settings: `youtube_read_mode` (`innertube` = fast, default; `api` = official, 10 s or slower), `youtube_innertube_fallback_min` (5): if fast mode keeps failing that long and a Google sign-in exists, Multi reads through the official API until fast mode works again. Sending messages and moderation still need the Google sign-in below.

## YouTube in 5 lines (do this once, then it renews itself)

1. console.cloud.google.com: create a project, then **APIs & Services -> Library -> YouTube Data API v3 -> Enable**.
2. **OAuth consent screen**: user type **External**, then press **Publish app** so it is in **production** (left in "Testing", Google kills the sign-in after 7 days).
3. **Credentials -> Create credentials -> OAuth client ID -> Desktop app**. Copy the client id and secret.
4. Multi launcher, **YouTube sign-in** box: paste the id and secret, press **Save** (the secret goes to Windows Credential Manager).
5. Press **Sign in to YouTube** and approve in the Google tab. Status reads "Signed in (renews itself)", so never paste a token again. Multi connects by itself once you are live on YouTube.

Details, quota maths and troubleshooting are in section 2 below.


You do every click that signs in or approves something. Multi only builds the link and receives the answer. Nothing here needs a password pasted into chat. Client secrets are typed into the Multi card and go to Windows Credential Manager; they are never shown again.

Where it all lives: open Multi's launcher (the home screen). Under "1 Connect your platforms" you will see two boxes, **Kick sign-in** and **YouTube sign-in** (from `static/connect.js`), above the per-platform list.

Each box has: "How to set it up" (a short help), **client id** and **client secret** fields, **Save**, and **Sign in to Kick / Sign in to YouTube**. The Sign in button stays greyed out until both client id and secret are saved. Its status line reads one of:
- `Not set up: client id and client secret missing` (or just one of them)
- `Ready: click Sign in`
- `Signed in (renews itself)` or `Signed in (cannot renew: sign in again when it stops working)`

The redirect address is shown inside "How to set it up" and is filled in by Multi from the address you opened it on (normally `http://127.0.0.1:8766/auth/kick/callback` or `.../auth/youtube/callback`). It is saved when you click Save. If the box says "currently set to ...", that differs from the one shown: click Save again.

---

## 1. Kick

1. On kick.com: **Settings -> Developer** and create an app. (Kick's own docs do not name the exact buttons, so follow what the page shows.)
2. In the app's settings, set the **redirect URI** to exactly the address shown in Multi's Kick box ("Redirect address"). It must match character for character, including `127.0.0.1` (not `localhost`) and the port.
3. Copy the app's **client id** and **client secret**.
4. In Multi's **Kick sign-in** box paste the id and secret and click **Save**. The secret field empties itself (that is correct). Status becomes "Ready: click Sign in".
5. Click **Sign in to Kick**. A Kick tab opens (an "Open again" link appears if the browser blocked it). Approve there. The tab then says "Signed in. You can close this tab."
6. Reopen the launcher page. Status says "Signed in (renews itself)".

Permissions Multi asks for (the default list, no need to change it): `user:read channel:read channel:write chat:write events:subscribe`. They allow reading your channel info, setting title/category, sending chat as you, and subscribing to events.

**Follows, subs, gifts and KICKs need Kick's webhooks.** Chat alone also works without them through the unofficial live feed (see the table). Kick can only call a public https address, so the Site receives them:
- Webhook URL to paste in the Kick app's **Enable Webhooks** box: `https://innocentpenguin.com/api/kick/webhook`
- The Site stores each signed event. **The Host pulls them** (`GET /api/bot/kick/events?since=...`, with the bot key) and hands them to Multi, which re-checks Kick's signature itself, so the Site is never trusted.
- Until the Host (or a Multi poller) is running this pull, webhook events wait on the Site and do not show in Multi. Ask 100 or 40 whether it is switched on.

## 2. YouTube

1. Go to console.cloud.google.com and create a **project**.
2. **APIs & Services -> Library**: enable **YouTube Data API v3**.
3. **OAuth consent screen**: type **External**, fill the required names, add your own Google account as a test user.
4. **Then click Publish app so it says "In production".** This step matters: while it stays in "Testing", Google kills the sign-in every **7 days** and Multi will ask you to sign in again. The "Google has not verified this app" warning at sign-in is normal for your own app: choose Advanced, then continue.
5. **Credentials -> Create credentials -> OAuth client ID**, type **Desktop app**. Copy the client id and client secret.
6. In Multi's **YouTube sign-in** box paste both, click **Save**, then **Sign in to YouTube**. Approve in the Google tab (permission: YouTube `youtube.force-ssl`, needed to read and send live chat).
7. Reopen the launcher. Status: "Signed in (renews itself)". Multi finds your active live broadcast by itself.

**Quota maths (only matters in `api` mode or while the fallback is active):** Google gives 10,000 units a day. Each chat read costs 5 units. Multi reads at most every 10 s (setting `youtube_min_poll_s`, and never faster than YouTube suggests): 6 reads a minute = 30 units a minute = **about 5.5 hours of live chat per day**. Past that Google answers "quota", Multi backs off 10 to 60 minutes and the card shows "Lost the connection, retrying automatically". To stretch it, raise `youtube_min_poll_s` (20 s doubles it to about 11 hours).

## 3. TikTok

TikTok has no official chat API. It is read-only, off by default, and **waiting on you**:
- **Needed from Ivan:** (a) your TikTok **@handle**; (b) a yes to installing the third-party `TikTokLive` package into Multi's Python (not installed yet; Multi shows "TikTokLive is not installed (optional package; ask to install)").
- **Then:** in the launcher's TikTok card tick "Read my TikTok LIVE chat", type the username (no @ needed) and click **Save TikTok**.
- **Risk:** it reverse-engineers TikTok and sends requests through a **third-party signing server** (Euler Stream by default; the setting `tiktok_sign_url` swaps it). That server sees your @handle and request metadata, it can break any day, and it may go against TikTok's rules. It never sends chat and uses no password. Euler's paid API is the proper route if this matters.

---

## 4. When a card says something odd

Status words come from the platform list on the launcher (the dot and label next to each platform name) plus a detail line under it.

| What you see | Meaning | What to do |
|---|---|---|
| **Connected - reading chat** | Working. | Nothing. |
| **Connecting...** | Opening the connection. | Wait 10 s; if it stays, see the next row. |
| **Lost the connection, retrying automatically** | Network or platform hiccup; Multi retries by itself. Detail may say `YouTube 401` or `403/429 (quota/rate limit): backing off`. | 401: the token died, sign in again. 403/429: quota used up, it recovers alone in 10-60 min. Otherwise ignore. |
| **Not set up yet**, detail "Add a YouTube OAuth token" | No YouTube sign-in saved. | Do section 2. |
| **Not set up yet**, detail "TikTokLive is not installed" | Package missing. | Tell 40 you said yes, or leave TikTok off. |
| **Turned off**, Kick "Off by default" | Kick feed not enabled and no webhook yet. | Chat only: set `kick_enabled` and `kick_chatroom_id`. Everything: do the webhook part of section 1. |
| **Turned off**, TikTok "Off by default" | Not enabled. | Section 3. |
| **Not connected** | Platform never started. | Read the detail line on the launcher. |
| **Problem - see details** | A hard error (for example channel not found). | Read the detail line; fix the name or id. |
| Box: `Not set up: client id ... missing` | Not saved yet. | Paste and click Save. |
| Sign in button greyed out | Needs both id and secret. | Save both first. |
| Google: `redirect_uri_mismatch` | Wrong OAuth client type or a mistyped address. | Make sure the Google client type is **Desktop app**, then click Save in Multi so it re-learns the address. |
| Kick: invalid redirect | Kick's app has a different redirect than Multi's box. | Copy it from "How to set it up" exactly. |
| Tab: `Sign-in failed: unknown or expired sign-in (start again)` | Multi restarted, or too long passed after clicking Sign in. | Click Sign in again and finish in one go. |
| Tab: `Sign-in failed: ... token endpoint ...` | Usually a wrong client secret. | Paste the secret again, Save, Sign in. |
| YouTube asks to sign in every week | Consent screen still in "Testing". | Publish it to **Production** (section 2, step 4), sign in once more. |
| YouTube "no active YouTube broadcast" (waiting) | You are not live on YouTube yet. | Nothing; it finds the stream when you go live. (Fast mode shows "not live on YouTube right now".) |

Never paste real tokens into any chat, issue or document. If something stays stuck, tell 100 the exact label and detail line you see.
