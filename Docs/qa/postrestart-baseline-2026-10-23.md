# Post-restart baseline 2026-10-23 (live Host, stream offline per decapi, 22:10 CDT)

Source: `python Tools\post-restart-check.py` against http://127.0.0.1:8770 (GET only). Host uptime 18429 s, sim=false.

```
       CHECK                                 DETAIL
PASS   host answers /api/status              uptime 18436s, sim=False, chat=True, eventsub=True, obs=False
PASS   status ok flag                        True
PASS   /api/live-state                       HTTP 200 offlineMode=False
PASS   prestream: chat                       Chat connected (reading #innocentpenguin_)
PASS   prestream: eventsub                   EventSub connected (follows, subs, raids)
PASS   prestream: master                     This device is the master (only the master runs the bots)
PASS   prestream: streamer                   Streamer account signed in (innocentpenguin_) - 55 d left
PASS   prestream: scopes                     Streamer permissions complete (events, clips, ads, shoutouts)
PASS   prestream: latency                    Twitch events arrive fast - median 581 ms, worst 685 ms over 60 messages
PASS   prestream: bot-core                   PinguinoB0t speaks as pinguinob0t - 51 d left
PASS   prestream: bot-chat                   ChattyPinguino speaks as chattypinguino - 51 d left
PASS   prestream: bot-helper                 PinguinoHelper speaks as pinguinohelper - 49 d left
PASS   prestream: mod                        PinguinoB0t is a channel mod (needed for timeouts)
PASS   prestream: modules                    Bot modules loaded (core, chat, helper, router)
FAIL   prestream: obs                        OBS connected - OBS WebSocket not reachable (is OBS open, WebSocket on?)
PASS   prestream: overlays                   Overlay pages carry the fit-options script
PASS   prestream: scenes                     Scene layouts have something to show
PASS   prestream: streamerbot                Streamer.bot reachable (legacy engine) - running on port 8080
PASS   prestream: ai                         AI key present for chat and helper - claude / claude-haiku-5-5
PASS   prestream: faq                        Helper facts (innocentpenguin.com/api/faq) - 33 entries
PASS   prestream: vault                      Key vault readable (API keys and tokens)
WARN   prestream: errors                     Last warning or error - 6 min ago: obs: OBS connection lost
PASS   prestream has items                   19 items, overall fail
PASS   scene health                          no problems
PASS   scene layout h                        resolvedBy=active game=Rocket League
PASS   scene layout v                        resolvedBy=active game=Rocket League
PASS   scene widgets                         20 widgets
PASS   page chat.html                        has overlay-options.js
PASS   page customs.html                     has overlay-options.js
PASS   page players.html                     has overlay-options.js
PASS   page players_vertical.html            has overlay-options.js
PASS   page queue.html                       has overlay-options.js
PASS   page scene-editor.html                stage/backup page, tag not required
PASS   page scene.html                       stage/backup page, tag not required
PASS   page subroll.html                     has overlay-options.js
PASS   page wheel.html                       has overlay-options.js
PASS   page wheel_v3_backup.html             stage/backup page, tag not required
PASS   asset /overlay-options.js             HTTP 200, 8993 bytes
PASS   asset /overlay/latest                 HTTP 200, 2356 bytes
PASS   asset /overlay/goal?id=followers      HTTP 200, 1884 bytes
PASS   asset /overlay/subfooter              HTTP 200, 3095 bytes
PASS   asset /live_state.js                  HTTP 200, 1236 bytes
PASS   /api/overlay-options/health           missing: []
PASS   /api/overlay-options/schema           profiles ['1080p', '1440p', '4k', 'vertical']
PASS   economy preview /api/economy/preview  HTTP 200 (answers)
PASS   intro /api/intro                      HTTP 200 (answers)
PASS   new routes since a1af1140             0 probed, 0 skipped on purpose ()

SUMMARY: 45 PASS, 1 WARN, 1 FAIL  (http://127.0.0.1:8770)
```

Only open item: OBS WebSocket not reachable (OBS closed after the stream; the Host log shows 'OBS connection lost' 6 min before the run). Everything else PASS, including the 14 pre-stream items besides obs.
