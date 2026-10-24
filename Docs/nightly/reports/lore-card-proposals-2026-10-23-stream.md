# Card proposals for new / returning chatters - stream night 2026-10-23 (CDT 18:00-22:00 = UTC 23:00-03:00)

Status: **PROPOSALS ONLY, nothing applied.** Private. Built from the chat logs of the stream (spam accounts filtered, bots excluded). No quotes, no counts shown to bots, nobody opted out in these sources. Automatic cards need 150 messages (`build.mjs`), so all of these would be small hand-written cards in `NOTES` (like the 22 hand-written ones) and are optional; until then the bots simply do not know these people, which is a safe default.

Who counts: 36 chatters spoke in the window. Of those, 5 have no card and 3+ messages, and 2 returned after a week or more. The channel account itself and bots are not people cards.

## Proposed hand-written cards (all `confidence: low`, `era: 2026-10 to 2026-10`)
```json
[
  { "login": "spywobbles", "display": "Spywobbles",
    "vibe": "New this week, very chatty during the Fortnite hour; mostly talks to Piney and wants to team up.",
    "likes": ["Fortnite", "team-ups with Piney and the streamer", "viewer tournaments"],
    "relationships": [{ "login": "pineyapplie", "note": "main chat partner, friendly banter and friendly teasing" }],
    "howBotsUse": "Greet warmly, can mention Fortnite if chat does first. Do not recount who he plays with." },
  { "login": "thoridien_rl", "display": "Thoridien",
    "vibe": "Small streamer who found the channel this week. Curious about the bots themselves: builds his own chat bot and asks how ours works.",
    "likes": ["penguins", "building chat bots", "channel-point rewards"],
    "relationships": [],
    "howBotsUse": "Friendly and curious; fine to chat about bots in general, do not share how our bots are built or any internals. Do not mention his channel size or anything personal." },
  { "login": "daspacechicken", "display": "daspacechicken",
    "vibe": "New this week. Friendly drive-by chatter with Twitch-emote humour and a running 'chicken' bit.",
    "likes": ["FNAF talk", "joining viewer games"],
    "relationships": [],
    "howBotsUse": "Warm light greeting. Do not explain the chicken bit." },
  { "login": "gojo1016", "display": "gojo1016",
    "vibe": "First time tonight: asked to follow, talked anime and games, plays Rocket League.",
    "likes": ["anime", "Rocket League", "Fortnite"],
    "relationships": [],
    "howBotsUse": "Treat as a newcomer: welcome, point to !discord. Too little history for anything else (hold until 20+ messages)." }
]
```
Order of confidence: spywobbles (107 messages overall, clear pattern) > thoridien_rl (55) > daspacechicken (25) > gojo1016 (6, hold).

## Returning chatters
- `speedyy2435` came back after 8 days (has a card, 694 earlier messages): normal short welcome-back line is right. Nothing to change.
- `frvzyplayz` (8 messages overall, back after 13 days): too thin for a card; the welcome-back line already works from the graph.
- Nobody with a card was away 30+ days.

## Edges
- `pineyapplie` + `spywobbles` is the strongest tie with no graph edge yet (an edge needs 30 exchanges; it will appear by itself).
- `thoridien_rl` talks mostly to the bots, not to people: no edge expected.

## How to apply (only if approved)
Add each as an entry in `NOTES` in `Tools/lore-mining/notes.mjs`, back up `Data/lore`, run `build.mjs`, then `verify-apply.mjs` (cards must equal nodes: a hand-written card needs its node, so these only turn into cards once the person passes the 150-message node threshold; until then they are better kept as notes here). Skip anyone who later opts out.
