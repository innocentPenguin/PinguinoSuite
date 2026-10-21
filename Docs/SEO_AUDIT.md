# SEO audit: innocentpenguin.com (2026-10-21, unit 05)

Status: implemented and committed LOCALLY, not pushed (waiting for 00/Ivan to approve a batched push, never during stream).

## 1. State before (crawl of every route)
| Finding | Before |
|---|---|
| Title | generic "Page | InnocentPenguin", some 25-30 chars, no keywords |
| Description | missing on /members, /settings, /privacy, /terms, mod pages |
| Canonical | none anywhere |
| Open Graph / Twitter | home only (no image) |
| JSON-LD | none |
| 404 | empty plain-text body, no robots header |
| Mod pages (403/401 gates) | no noindex |
| H1 | exactly one per page (good) |
| Images | all `<img>` have alt (good) |
| Page weight | 200-410 KB HTML per page (inline CSS/JS, base64 avatar) |
| sitemap/robots | present, sitemap from PAGES minus noindex, robots blocks /api /auth /mod /draft /overlay |

## 2. What changed (all central, one writer)
- `content/seo.json`: ONE table of title + description + type for every page. Edit it to retune copy. Titles <= 59 chars, descriptions 85-160, all unique.
- `worker/index.js` `seoWrap()`: wraps the whole router; for every public HTML page it writes `<title>`, description, canonical, Open Graph (type, site_name, locale, title, description, url, image + alt), Twitter card tags and JSON-LD. `/mod/seo` overrides (env.SEO) still win for title/description.
- JSON-LD: home = WebSite + Person (channel links only from content/links.json); every other page = WebPage + BreadcrumbList; /help = FAQPage (the public FAQ); /esports about SportsTeam "PENGU eSports"; Rocket League / Fortnite pages carry `about: VideoGame`.
- Hidden = `X-Robots-Tag: noindex` header on: /mod*, /draft*, /overlay*, /auth*, /shop, every member profile (noindex, follow), 401/403/404 responses, and the pages marked `noindex` in the table (/members, /settings, /privacy, /terms, /help/ticket). Never in sitemap or robots.txt, no private URLs in either.
- 404 is a friendly penguin page (noindex).
- `scripts/check.mjs` SEO block guards all of the above (unique title/description, canonical, OG/Twitter, JSON-LD parse, sitemap only lists public table pages, robots names no private page, hidden pages noindex, lore/internals words banned in seo.json).

## 3. Per-page table (live copy in content/seo.json)
See the JSON; keywords used are what viewers search: Rocket League customs, join the queue, tournaments/cash tourney, leaderboards, standings, match history, song requests, 7TV emotes, chat commands, play with viewers, Fortnite customs.

## 4. Competitor / best-practice notes
Web search results were thin (streamer sites rarely rank for much beyond the channel name). What does carry weight for small creator sites: one clear H1 per page, keyword-matching title under ~60 chars, unique 120-160 char description, canonical, OG image for link previews (Discord/X), Person/WebSite schema tying the site to Twitch/YouTube/TikTok profiles, fast mobile pages (LCP < 2.5 s, INP < 200 ms, CLS < 0.1), internal links between related pages, a sitemap. Live-stream rich results (BroadcastEvent/VideoObject with isLiveBroadcast) need an embedded video with real start/end times; left out on purpose until we can emit it only while live. Semrush was not used (no paid-account actions without telling 00).

## 5. Priority list still open
1. **Share image (needs Ivan):** a 1200x630 orange/dark penguin banner. Until then pages use the 512px icon with a `summary` Twitter card. Drop it in `assets/` and set `site.image` in seo.json (and switch twitter:card to summary_large_image).
2. **Performance:** ~200 KB of inline CSS/JS per page and a base64 avatar on the home page. Move shared CSS/JS and the avatar to cached assets (a separate, bigger task; touches every page, one writer).
3. **Event schema for /tourney:** needs a real start date from Ivan before we emit `Event`.
4. **Live schema:** emit BroadcastEvent/VideoObject only while the Twitch embed is live.
5. **Google Search Console + Bing Webmaster:** Ivan verifies the domain (DNS or meta tag), submits sitemap.xml. We can add the verification meta tag when he gives the code.
6. **Member directory:** kept noindex on purpose (profiles list chatters by name). Say so if you want it indexed.
7. Internal linking: footer/nav already cross-link customs, tourney, leaderboards; add "related" links on /help and /rocket-league later.

## 6. Other sessions' SEO needs
None received yet beyond 00's brief; fold in when 00 forwards the collected list.
