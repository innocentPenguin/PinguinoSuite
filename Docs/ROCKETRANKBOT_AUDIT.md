# RocketRankBot removal audit

Written by 999 for 00, 2026-10-20. Read-only: nothing was built, launched, pushed or changed. No secrets in this file.

**Evidence base:** chat logs `Data\chat_logs\2026\` (666,891 parsed lines, 2026-02-15 .. 2026-10-20), `Data\runtime\chat_profiles.json`, `Data\profile_bots.json`, `Data\nickname-overrides.json`, `Docs\SYNCHRABOT_AUDIT.md`, `Docs\TRIAL_REPORT.md`, `Docs\imports\nightbot-custom-commands.txt`, and the Host source (`PinguinoHost\HostBoards.cs`, `HostProfileSync.cs`, `HostCredits.cs`) plus `Shared\PinguinoRouter.cs`.

**Method.** The logs record sender and text only, with no badges or tags. A "use" is a viewer line starting with `!rank`. A bot post is credited to the viewer's `!rank` if it follows within 8 seconds.

## Verdict

**Safe to remove once our own `!rank` exists. Do not remove it first.** RocketRankBot does exactly one job: it answers `!rank` with Ivan's three ranked playlists. That is 172 matched uses by 97 viewers, still used last on 10-19. The Host has no `!rank` reply (`TRIAL_REPORT.md`: `!rank` "PASS (no reply)"), so removing the bot today leaves `!rank` to Nightbot's hand-typed line only. Nothing else it does needs replacing. It posts nothing on its own.

## 1. What it is and how it got here

- Twitch chat bot (login `rocketrankbot`) that looks up Rocket League ranks and exposes them as a per-channel custom command. Its owner is not shown anywhere in our data; I did not look it up (no network).
- **Added by Ivan, in chat, 2026-03-02 06:13.** He typed `@RocketRankBot !join` and it answered "The bot has already joined your channel. You can add a rank command using !addcom." So it is a public join-by-command bot, not a mod grant, VIP or Twitch extension. Pinguinob0t greeted it in chat a second later.
- Setup that night: `!addcom !rank steam innocentpinguino`, then three `!editcom !rank format ...` edits to shorten the text.
- **Roles:** `chat_profiles.json` records `mod: false, vip: false, sub: false, bot: false`. The logs can't show a mod badge, but nothing here says it was ever modded. Check the Twitch mod/VIP list anyway (section 6).
- **Account trouble.** Steam lookup failed ("Player innocentpinguino could not be found on steam") on 05-26, 05-31, 06-02, 06-04, 06-06 and once more on 06-07. Ivan re-added the command that day and later switched it to `account epic innocentpenguin`. Three "Internal error occurred" replies on 04-10 and 04-12. Nine error replies in total.
- It can be configured by Ivan only through chat commands: `!join`, `!addcom`, `!delcom`, `!editcom [command] [account/action/cooldown/format]`, `!setplatform`. These are the only controls seen in the logs.

## 2. What it posts, and how often

200 bot lines in total, over 114 days, 2026-03-02 .. 2026-10-19.

| Kind | Lines |
|---|---|
| `!rank` answers: `Ranked 1v1: ... (mmr) \| Ranked 2v2: ... \| Ranked 3v3: ...` | 178 (172 matched to a viewer's `!rank`, 2 unmatched, rest setup replies) |
| Setup replies to Ivan (`Command successfully added`, `Updated command`, `Invalid property`) | 12 |
| Errors (`Internal error`, `could not be found on steam`) | 9 |
| Other | 1 |

- **No automatic posts.** Every rank post follows a viewer `!rank` within seconds. Viewer question "is this auto updated?" (yoohoo15, 03-21) confirms people don't see it as automatic. The only repeating `!rank` is the Nightbot timer that promotes the command (`SYNCHRABOT_AUDIT.md` line 58).
- The only extra bot-side noise was the early March setup spam and the error replies above.
- Posts by month: Mar 24, Apr 15, May 18, Jun 20, Jul 28, Aug 53, Sep 30, Oct 12 (to the 19th).

## 3. Who uses it

Viewer `!rank` lines: 223 (114 users). RocketRankBot answered 172 of them. Nightbot's own `!rank` text answers some of the rest ("Peak GC2, Current C3", 13 answers per `SYNCHRABOT_AUDIT.md`), so both bots can answer the same command.

By month: Feb 3, Mar 30, Apr 20, May 20, Jun 19, Jul 32, Aug 57, Sep 30, Oct 12. It is growing, not dying; August was the peak.

Top triggerers: innocentpenguin_ 31, aceislosst 14, cups0ftea 9, shadowrlttv 7, lvlmarshmello 6, yoohoo15 6, fiayir 4, zylorocketleague 4. Other chatters mentioning it: oatsyontop, penguindads, sn0wmanny_, cups0ftea, xryvok (just a bot list).

Other commands answered: none. No other `!` command ever got a RocketRankBot reply (the matched triggers were `!rank` only; four one-off mismatches were other bots' commands).

## 4. Does our Host already cover it?

**No.**

| Need | State |
|---|---|
| `!rank` reply with live ranks | **Missing.** No `!rank` in the Host (`grep` finds none); `TRIAL_REPORT.md` shows it gets no reply. |
| `!mmr` | BVQ (custom lobby) MMR, not Rocket League ranked. Not a substitute. |
| `!peak` / `!realrank` | Nightbot hand-typed text (`!realrank` returns "Silver 2 Div 3"). Stale by design. |
| PinguinoLink matchmaking | Lobby/matchmaking only. Does not read Rocket League rank. |
| Rank history, rank-up announcements | Not offered by RocketRankBot either; nothing lost. |

**What is lost on removal:** only the live Rocket League rank lookup. Everything else (Nightbot `!peak`, `!rl` lore, BVQ `!mmr`) is separate and unaffected.

## 5. Replacement plan

1. **Step 1, zero dependencies (do first).** A Host `!rank` command that replies from a small file, e.g. `Data\settings.json` or `Data\config\rank.json`: `{ "1v1": "...", "2v2": "...", "3v3": "...", "peak": "...", "updated": "..." }`. Ivan (or a mod command like `!setrank 2v2 GC1 Div3`) updates it. Same output shape as the bot: `1v1: ... | 2v2: ... | 3v3: ...`. No network, no keys, nothing to break. Also retire Nightbot's `!realrank` text so one owner remains (`SYNCHRABOT_AUDIT.md` recommended a single owner for `!rank`).
2. **Step 2, optional auto-update.** Add a fetch that refreshes the file from a rank source. I did not verify any source or API from here (no network, no keys). It needs a decision: which service, which account (epic `innocentpenguin` per Ivan's last setup), and a stored credential if the service needs one. Steam lookups already failed repeatedly for the bot, so use the Epic account first. Keep Step 1 as the fallback if the fetch fails.
3. Keep the 3 playlists and the shortened wording Ivan chose on 03-02 so viewers see no change.
4. Test with the same trigger tests as `TRIAL_REPORT.md` (`!rank` should now reply).

## 6. Removal steps (after the replacement works)

All of this needs Ivan or a Twitch mod. I did none of it.

1. In chat: `@RocketRankBot !delcom !rank`. Its `!delcom` replied "Command successfully deleted." on 03-02, so this works. (A `!part` / leave command is the usual way to make a join-by-command bot leave. It does not appear in our logs, so unverified; check the bot's own page, `twitch.tv/rocketrankbot`, which Ivan linked on 05-09.)
2. If Twitch shows it as mod or VIP: `/unmod rocketrankbot` and/or `/unvip rocketrankbot`. (The data suggests it holds neither.)
3. Optional hard stop: `/ban rocketrankbot` (or `/block` on Ivan's account). A ban also stops it from re-joining by command. Do this only after the leave attempt, because the bot's own setup page may have a button for it.
4. Check Twitch Creator Dashboard > Settings > Moderation / Roles and Streamer.bot / Nightbot settings for any bot-list or chat-ignore entry that names it. There is no sign of one in our files.
5. Remove from any copied "bot list" Ivan keeps by hand (the sub-list shown in chat, `xryvok` posted one on 03-25).

## 7. Is it excluded from boards, XP and bot-ignore lists?

**Mostly yes by accident, and not everywhere.** Not safe to rely on.

| Place | State |
|---|---|
| `HostBoards.cs:102` `BotName` regex `(bot\|b0t)$` | Matches `rocketrankbot`, so `Boards.IsBot()` is **true**. Economy, emotes, lore, site bridge and board filters that call `IsBot` already skip it. |
| `HostBoards.cs:94` `KnownBots` | **Not listed.** The regex is the only reason. |
| `Data\profile_bots.json` (written by `HostProfileSync.WriteBots` from `Boards.AllBots()`, i.e. `KnownBots` + extras) | **Not listed.** The site's `isBot` flag therefore does not mark it. |
| `Data\runtime\chat_profiles.json` | `bot: false` for RocketRankBot (198 msgs, 112 active days). `ExtraBots()` reads this flag, so it also isn't picked up there. |
| `HostCredits.cs:72` credits `Exclude` | Not listed. Also missing: potatbotat, synchrabot and the other bots, so the credits roll may list it. |
| `Shared\PinguinoRouter.cs:305` `OtherBots` | **Not listed.** Our bots' other-bot handling may treat it as a viewer. |
| `Data\nickname-overrides.json` | Already in `skip`, and `remove` has `["rank"]`. Fine. |
| Others' chat profiles | It shows up in other users' `talks` maps (e.g. 16 for one user). Harmless. |

**Fix list (for the code owner, not done here):** add `"rocketrankbot"` to `KnownBots` (this alone puts it in `profile_bots.json` after the next profile sync), to `OtherBots`, and to the credits `Exclude`; and set `bot: true` in the chat profile. Do this even before removal, so boards never rank it. After the bot is gone these entries are harmless.

## 8. Limits of this audit

- Logs have no badge or tag data: whether it held mod/VIP is not proven.
- Owner, leave command and the bot's data source are not shown in our files; nothing was looked up online.
- Matching is by 8-second window; 2 of 178 answers had no viewer trigger within 8 s (likely a trigger from a line the log dropped).
- Counts of `!rank` per viewer include Nightbot-answered uses, so 223 is the demand and 172 is what this bot answered.

## 9. Addendum: looking up ANY viewer's ranks (`!rank <name>`, `!rank 2s/3s`, `!rankme`)

Added 2026-10-20 at 00's request. Sources: web search results (forum posts, secondary pages; **not** verified against the live services, nothing was called from here) plus our own code. Read-only.

### 9.1 Data sources, what actually works

| Source | Verdict |
|---|---|
| **Tracker Network (tracker.gg) official Rocket League API** | **No key available.** Tracker staff say in their developer forum they run no public Rocket League API, only for their own projects, because of agreements with the game developer, and point developers to Psyonix ([forum: RL public API](https://feedback.tracker.gg/t/rocket-league-public-api/9214), [403 thread](https://feedback.tracker.gg/t/rocket-league-api-error-403-you-cannot-consume-this-service/3971), [API access thread](https://feedback.tracker.gg/t/is-there-anyway-to-get-api-access/21648)). Reported to return 403 to outside callers. Using it also goes against their stance. |
| **Unofficial tracker.gg web endpoint** (`api.tracker.gg/api/v2/rocket-league/standard/profile/<platform>/<id>`) | **What our B0t already does, and it is fragile.** `PinguinoBotCore.cs:2389` `LookupEpicProfile` calls it by curl, 1 request per 2 s, 24 h cache per `id|playlist`, **off by default** (`TrackerLookupEnabled`), auto-pauses 1 h after a block (`_trnPausedUntil`). Not documented, no key, can be blocked (Cloudflare/403) at any time; ToS-grey. Fine for a few lookups per stream with caching, not a foundation. |
| **Psyonix / Epic official** | No public rank/MMR endpoint found. Secondary source says none exists. The only real fix is asking Psyonix for access, which is slow and not guaranteed. |
| **ballchasing.com API** | Token-based, documented, but it is a **replay** database. It gives match stats for uploaded replays, **not live rank/MMR**. Wrong tool for `!rank`. Rate limits depend on a Patreon tier. |
| **RLTracker.pro API / npm wrappers, other public trackers** | One old npm wrapper says a rate-limited RLTracker.pro API exists (last published about 7 years ago). Current docs and terms **not found**; treat as unverified/dead until checked by hand. Other sites (rl.insider.gg etc.) show ranks but have no stated API. Scraping them is ToS-risky. |
| **Our own data** | Works today, no external service: BVQ `Player` records hold `GameId` (Epic/platform name), `PeakMmr`, `MmrSource` (manual/self/api), `Sr`, `TwitchId`, win/loss/points (`PinguinoBotCore.cs:327,1900`). |

**Season history:** none of the verified paths gives it. Only the tracker web pages show it. Do not promise `!rank season`.

### 9.2 Platform ids

- Tracker's profile URLs use `epic / steam / psn / xbl` plus the platform name or id. **Epic needs the display name**, not the account id. PSN/Xbox need the gamertag. **Steam needs the 17-digit id or vanity name.** This is exactly why the old bot failed on `steam innocentpinguino`.
- Our registration stores one free-text `GameId` per login with **no platform**. For a lookup we would need `platform + id` per viewer.
- Display names can change; a lookup that fails should say "couldn't find X on Y" and never guess another platform.

### 9.3 What the Host/PinguinoLink already has to reuse

- **No RL stats code in the Host or Shared** (greps for tracker/ballchasing/rank lookup there were empty).
- **BVQ in `PinguinoB0t\PinguinoBotCore.cs` has the pieces:** `!register <epic>` linking (regexes at lines 305-306 even parse "my epic is ..."), per-login `_players` with `GameId`/`TwitchId`, `ResolveMmr` with the cache and mod/self override (line 2339), the throttled tracker fetch (line 2389), and `!mmr`. Reuse this, do not write a second one.
- BVQ MMR is a matchmaking number (peak/self-set/API), so label replies clearly: `!mmr` = lobby MMR, `!rank` = ranked playlists.

### 9.4 Linking accounts to Twitch logins

1. `!link epic|steam|psn|xbox <name or id>` (or reuse `!register`), stored as `{ twitchLogin, twitchId, platform, id, linkedAt }` keyed by **Twitch user id** (logins can change; `Player.TwitchId` already exists).
2. Chat can't prove a viewer owns that account. Accept this: self-reported, so fine for display, **never** for balancing without the existing mod override. Mods can `!unlink <user>`.
3. `!rankme` = look up the caller's linked account. `!rank <name>` = look up a Twitch login's linked account, else treat `<name>` as an Epic name with a flag. `!rank 2s|3s` selects the playlist.
4. Per-user cooldown (e.g. 30 s), global cooldown (one lookup per 2 s, same as today), 24 h cache, "last updated" in the reply, and a stale-cache fallback when blocked.

### 9.5 Recommendation (realistic)

1. **Do Step 1 first** (section 5): Ivan's own `!rank` from a file. Needs no dependency, and removes the bot.
2. **Viewer lookups = reuse the BVQ tracker lookup behind the `TrackerLookupEnabled` flag**, with the platform-aware link record above, long cache, and strict throttling. It is the only free source that returns live ranks. Be honest in the docs that it is an unofficial endpoint that can disappear.
3. **Design for failure:** when blocked, reply "rank lookup is down, here's the last known <date>" or the self-reported rank (`!setmyrank 2s GC1` stored with `MmrSource=self`). Self-reported ranks are the fallback that always works.
4. **Do not build** on ballchasing (wrong data), a made-up Tracker key (none exists), or a hammered scrape without cache.
5. **Optional long shot:** ask Psyonix/Epic whether any partner rank endpoint exists; low odds.
6. Decision for Ivan: accept an unofficial, breakable lookup (cheap, works now) versus self-reported-only (always works, not live).

### 9.6 Limits of this addendum

- Web results were sparse and partly low quality; nothing here was tested against a live endpoint. Before building, check by hand in a browser that the tracker profile page still loads and that tracker.gg terms allow your use.
- Rate limits for the unofficial endpoint are our own 2 s guard, not a published number.
