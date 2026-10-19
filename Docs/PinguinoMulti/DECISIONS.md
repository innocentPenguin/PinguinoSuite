# PinguinoMulti decisions log

- 2026-10-19: Greenfield. No prior PinguinoMulti code existed (verified).
- 2026-10-19: Build as Suite module `Suite\modules\multi` (port 8766), headless core + thin UI shells; native shell (Unit 01) is the long-term target.
- 2026-10-19: Twitch auth reuses the site OAuth via a new broadcaster-only "Connect Multi" flow (do not widen viewer login scopes).
- 2026-10-19: Moved D:\InnocentPenguin-source.zip -> Archive\. Compat links in D:\PinguinoBot and D:\InnocentPenguinSite left until README migration steps are done.
- 2026-10-19: M1 core built and tested (27 tests). Sends target exactly one platform; no broadcast endpoint. Tokens only in Credential Manager. Live Twitch + site Connect Multi still pending.
- 2026-10-19: Connect Multi built in PinguinoSite (own commit). Reuses the existing Twitch redirect URI; tokens handed over via loopback URL fragment. Not yet deployed or live-tested.
