# Chatty stream-end recap: wording for a mod to approve

The recap is one line, posted once when the stream ends (`RecapOnStreamEnd`, **off** until a mod approves a wording and flips it on). It uses only the stream's own totals (follows, subs incl. gifted, bits, raids). It never names a viewer, never repeats a remembered fact, and when nothing happened it falls back to the plain thank-you.

Tell 10 / the coordinator which option to use (A, B or C, or your own wording). Until then the code keeps the current wording (= option A).

## Option A - plain (current)
- Quiet night: `thanks for hanging out tonight, everyone! 🐧 See you next stream.`
- With totals: `thanks for hanging out tonight, everyone! 🐧 Tonight: 3 new follows, 2 subs, 500 bits, 1 raid. See you next stream.`

## Option B - warmer, igloo flavour
- Quiet night: `that's a wrap, igloo crew! 🐧 Thanks for spending the evening here, sleep well and come back soon.`
- With totals: `that's a wrap, igloo crew! 🐧 Tonight we picked up 3 new follows, 2 subs, 500 bits, 1 raid. Thank you all, sleep well and come back soon.`

## Option C - short and light
- Quiet night: `stream's over, thank you for coming! 🐧`
- With totals: `stream's over, thank you for coming! 🐧 Tonight: 3 follows, 2 subs, 500 bits, 1 raid. See you next time.`

## Notes for the approver
- Totals are only listed when above zero, in the order follows, subs, bits, raids.
- One line only, sent through the normal chat path (no duplicate if the Host also says goodbye; the Host's own end line stays separate).
- Preview without posting: `POST /api/recap/test` (loopback); `{post:true}` really posts, only while live.
- Switch on: `RecapOnStreamEnd: true` in `chat_settings.json` (never paste that file anywhere, it holds the AI key).

## Sample from tonight (2026-10-23, 17:14-22:02 CDT)
Totals from the Host event log (`chat_events.json`): 2 new follows, 0 subs, 20 bits (5 cheers), 0 raids. The live `POST /api/recap/test` needs the Host token, so this was rendered by hand with the same rules (only totals above zero, in the order follows, subs, bits, raids). Raids would read 0 anyway: the EventSub `channel.raid` subscription is refused (HTTP 409) until Ivan signs in to Twitch again.

- A: `thanks for hanging out tonight, everyone! 🐧 Tonight: 2 new follows, 20 bits. See you next stream.`
- B: `that's a wrap, igloo crew! 🐧 Tonight we picked up 2 new follows, 20 bits. Thank you all, sleep well and come back soon.`
- C: `stream's over, thank you for coming! 🐧 Tonight: 2 follows, 20 bits. See you next time.`

Suggestion: B, it fits the channel's tone; A if the mods want it plain.
