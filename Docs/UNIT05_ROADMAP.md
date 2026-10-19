# Unit 05 — PinguinoSite roadmap

Site: `D:\PinguinoSuite\PinguinoSite` (innocentpenguin.com, Railway). Nothing is pushed to `main` without explicit approval.

## Done in this pass (local, unpushed)
- Security headers (nosniff, frame-ancestors, referrer-policy, permissions-policy, HSTS on https).
- 500s logged (method, path, message only).
- JSON stores: corrupt reads logged, `.bak` kept, atomic write via `.tmp` + rename.
- `robots.txt`, `sitemap.xml` (honours `SITE_ORIGIN`), og/twitter tags on the homepage.
- Tests: `scripts/check.mjs` covers robots/sitemap/social tags.

## Still open from the audit
- Mandatory Origin check on state-changing browser POSTs (exempt `/api/bot/*`, `/api/multi/refresh`).
- Per-IP rate limits on `/auth/*/login` and `/api/emotes`.
- Session revocation (sessions are stateless HMAC cookies).
- `index.html` ~580 KB with base64 images: extract images, gzip, cache headers.
- Strict CSP (needs inline scripts moved out first).

## Tournament Wheel (next build; design in the Unit 05 plan)
- Core (C#) owns the session and the single seeded draw; site mirrors via `POST /api/bot/wheel` into `env.WHEEL`. Supersedes the pull model in `WHEEL_CONTRACT.md`.
- Packages: B Core module + `!me`; C site backend; D mod page + `/overlay/wheel`; E fake-bot + checks; F release.
- Open questions: `!me` for all viewers or subs only; default `oddPolicy` (proposed: waitlist); dry-run mode for the dev bot.

## Later
- Viewer dashboard (profile, queue, MMR, history) from server-validated bot state.
- Compact Twitch chat: official embed first; authenticated send only if wanted.
- Event bridge: add "last updated / bot offline" badges.
- Games section: data-driven registry; Rocket League and Minecraft stay Coming Soon until approved.
- Content/SEO/performance, PWA (manifest + service worker, no native app).
- Monetization: merch, supporter perks, sponsorships; nothing intrusive.
- Brackets, seeding, check-in, captains, presets.
