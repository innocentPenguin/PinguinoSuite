# Who says what about music (Ivan 10-24: "if the text is about music, the sender is PinguinoHelper")

Audit by 11. Effective at the next Host restart (the saved-automation migration runs once, marker `songhelper1`, dated backup `automations.json.before-songhelper-*.bak`).

| Path | Before | Now |
|---|---|---|
| !song / !np / !songqueue / !vol / !skip / !voteskip | Helper (96f3dfc), Host presets removed (0c21b85) | Helper |
| !sr (preset `spotify-sr`, module reply: added / queue full / blocked / closed) | core | **helper** |
| !oops (`spotify-oops`) | helper | helper |
| !blocksong (`spotify-block`), !srclear (`spotify-clear`) | core | **helper** |
| Channel-point "Song Request" (`spotify-redeem`): confirmations and refund-reason lines | helper (saved file), core (fresh seed) | helper both |
| Channel-point "Skip Song": no Host automation existed; the redeem was answered by an old action ("Skipping current song..." by the Core bot, 3x last stream) | core / not handled by the Host | **new preset `spotify-skip-redeem`** (redeem "Skip Song" -> module `skip` with redeem=true, says as helper) |
| Spotify announcements relayed by the Host (`SpotifyAnnounce`, now-playing, queue lines) | "As" default core, any of core/chat/helper | **always helper** (settings read and save are forced) |
| Refund failed ("could not refund, a mod will sort it", HostRedeem.cs) | core | **helper** |
| Any `module_command` step for a music command (sr, oops, blocksong, srclear, skip, song, queue, volume, last, pos) | the step's own "as", default core | **helper** (`SongSender.Role`), whatever the step says |
| "Speak" redeem (text-to-speech via the same module) | core | core (not music, left alone) |

Not in this commit (other owners): PinguinoChat.cs (12) prompt already says song asks go to the Helper; HostCanned.cs (12) only reserves the song command names; PinguinoBotCore.cs has no song text.
Test: `Tools/test-host-songsender.py`.
