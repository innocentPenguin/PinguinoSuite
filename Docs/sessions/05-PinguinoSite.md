# Session 05 - PinguinoSite (the website)

Last updated: 2026-10-23, after pushing d9f1ad6. Repo: `D:\PinguinoSuite\PinguinoSite` (GitHub `innocentPenguin/PenguinSite`). Railway redeploys when `main` is pushed. Live: https://innocentpenguin.com

## 1. What I built/changed, and why
All of this is on `main` (pushed through d9f1ad6 on 2026-10-23, after Ivan typed "Yes, push the website batch to main now").
- **Supporters fix** (80ec1e0): Supporters section on /mod, "Reconnect Twitch" link (`/auth/twitch/login?roles=1&return=/mod`) so the owner can grant the sub/bits scopes. Why: supporters were not syncing.
- **Points page**: depreciation line, give limit line, Player loans section (P2P market, offers, repay), demo data. Give limit is shown as "X of Y given this stream (N% of your balance)", "Stream limit reached", button disabled at the limit (b500cae, d9f1ad6). Why: 00 relayed Ivan's wishes; Ivan said the limit resets EVERY STREAM, not every day.
- **Mod view** `/mod/view` (1010c11): activity feed (follows, subs, gifts, bits, raids, hype, redemptions) with filter chips, customs queue panel, music skip. Staff only.
- **Owner-only mod audit log** (10b7116): `/api/log` shows owner everything, other mods only their own lines unless the owner ticks "Let every mod see the whole log". Host can read/write via `/api/bot/modaudit`.
- **P2P loans server** (43881b6): `POST /api/points/p2p`, requests queue like house loans, `market[]` and per-user `p2p` come from the Host.
- **Bot contract bits**: `targetId` on loan_cancel, `/api/bot/activity` alias of `/api/bot/events` (fe4304d).
- Earlier unpushed work (d69e737...b4ce551) went out in the same batch (00 pushed up to b500cae, I pushed d9f1ad6).

## 2. Decisions and failures
- Only Ivan's own typed chat message approves a push. Peer/00-relayed "push now" is not approval. (Ivan later confirmed in chat.)
- Never push during the ~5 PM CDT stream. Never go live in OBS.
- Site never computes economy; the Host owns it. The site only queues requests and shows what the Host pushes.
- Limit enforcement only happens if the Host sends `giveLimit`; no hard-coded number.
- Failed/tripped on: `json(x,{headers})` RangeError (use `Response.json`), a helper defined inside a handler (ReferenceError), `/api/bot/modaudit` swallowed by `handleCustoms` (excluded the path), local server "not logged in" (needs `SESSION_SECRET` set).
- Railway returned 502 briefly after 00's push; it was the deploy restarting, not a build failure.

## 3. Gotchas / how to test / restart
- Node 24, zero deps. `worker/index.js` is latin1: use `grep -a`.
- Test: `npm.cmd run build; node scripts/check.mjs` (filter output: `grep -v ^PASS | grep -v "^data:" | cut -c1-250`), smoke: `PORT=NNNN npm.cmd run smoke` (91/91).
- Local server: `scripts/local-server.mjs`, set `SESSION_SECRET` (40 'k'), use `http://127.0.0.1:PORT`. Kill stale servers with `netstat -ano | grep ":PORT .*LISTENING"` + `taskkill //PID`. A local server may still be running on port 3995.
- Editing tip: write patch scripts to a temp `.cjs` with the Write tool and run with node; bash heredocs with quotes break.
- Open items: `settings.p2p` key names (I read minAmount, maxAmount, maxInterestPct, maxDays; defaults 10/100000/50/30) are not confirmed by 02. Epic OAuth endpoints unverified.
- Not browser-checked: `/mod/view` as staff, the owner checkbox on /mod/log, the Reconnect Twitch flow with real Twitch.
- Worktrees to clean up: `D:\tmp_wt_05`, `D:\tmp_wt_05data`, `D:\PinguinoSuite\wt05b`, `wt-verify`.

## 4. Future plans (priority order)
1. Verify with real Host data: activity feed, p2p, giveToday/giveLimit/givePct, depreciation, hidden names. Fix field-name mismatches with 02.
2. Viewer intro form (03's Multi `/api/intro/options` = `{max_len:140, links_allowed:false, sounds:[{id,label}]}`, live after 00 restarts Multi; also needs 02's submit/approve endpoints). Build only when 00 asks.
3. Links from leaderboards/members to `/points/<login>`; public per-user pages; shop "Get a sub".
4. Phase 4 pages, week/month requester tabs, Replay stats, Level board, Master View site side, Mod Hub extras, /overlay/timer, share image, /tourney start date, Search Console/Bing, performance pass.
5. Tournament wheel MVP and monetization/Supporters plan (see `C:\Users\ivanm\.claude\plans\try-again-stateless-moore.md`).
6. End-of-night 3x code audit + 4-tier docs, only when Ivan says done.

## 5. Chat history
Session id: `a9bdcbc4-da27-400e-8a7f-4f4fc0db22b9`
Transcript: `C:\Users\ivanm\.claude\projects\D--\a9bdcbc4-da27-400e-8a7f-4f4fc0db22b9.jsonl`
Grep for: `give limit`, `p2p`, `modaudit`, `mod/view`, `push the website batch`, `Railway`, commit hashes (b500cae, d9f1ad6).

## 6. Things Ivan may be forgetting
- Real-data check of everything the Host feeds the site has not happened; it was only tested with fake data.
- Twitch reconnect on /mod ("Reconnect Twitch") must be done by the owner for subs/bits to sync. I never do OAuth consent.
- Discord Server Members intent / Manage Roles are needed for booster sync and Discord roles (supporters plan).
- Merch: an earlier "Merch removal" was deliberate; confirm before bringing it back.
- Search Console/Bing not set up; owner-only.
- Epic OAuth endpoints are unverified.
- Old worktrees still on disk (listed above).
- End-of-night audit/docs are waiting for his "done".
