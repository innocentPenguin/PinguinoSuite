# PinguinoBot: on-stream cheat sheet

## Before going live (2 minutes)
1. Back up `%AppData%\BVQ` by copying the folder somewhere safe.
2. In Streamer.bot, **disable** the old action instead of deleting it, so you can switch back mid-stream if needed.
3. Make a new action → Execute C# Code → paste `PinguinoBotCore.cs` → click **Compile**. Fix any red errors before going live.
4. Point every command trigger (old ones plus `!win !mode !pick !stats !top`) at the new action.
5. In the action settings, set **Queue = a blocking queue** (for example, make one called "PinguinoBot" with Blocking ticked). This is a second guard against two commands running at once.
6. Open `%AppData%\BVQ\settings.json` and make sure `TrnApiKey` is empty. Revoke the old key on tracker.gg.

## Normal match loop
| Step | Command |
|---|---|
| Open the queue | `!queue open` |
| Make teams (website: **Fill**) | `!balance` or `!match fill` |
| Game over, empty the match (website: **Clear**) | `!match clear` (everyone in it leaves the queue; nobody is pulled in) |
| Undo: put the match back in line (website: **Move all ➜ Queue**) | `!match queue` (back to the FRONT of the queue) |
| Don't like the teams | `!reroll` |
| Someone's missing | `!kick name` then `!reroll` (pulls a replacement) |
| Blue won, run it back King of the Hill style | `!next blue` (records the win **once**, keeps Blue, brings in challengers) |
| Blue won, rotate everyone | `!win blue` then `!next` |
| Done for the night | `!queue close` |

`!win` then `!next blue` is safe: a match can only be scored once.

## Modes
- `!mode balanced`: teams balanced by MMR (default)
- `!mode random`: random teams
- `!mode picks`: run `!balance`, then `!pick name1 name2 name3` (those go Blue) or `!pick auto`
- `!format 2v2` / `3v3` / `4v4`

## If something goes wrong live
- **Bot silent:** check the Streamer.bot log for `[BVQ]` lines.
- **Queue is a mess:** `!queue clear` then `!queue open`. Players keep their registrations and stats.
- **Wrong MMR:** `!setmmr name 1200`, or a rank such as `!setmmr name c2`.
- **Total failure:** disable the new action and re-enable the old one.

## Activities, the streamer seat, and drag & drop (website + chat)
- **One queue, one activity at a time.** `!activity competitive` (balanced teams, stats count), `!activity casual` or `!activity viewers` (random teams, no stats). Starting one **ends the current match** (the players in it leave the queue; **people waiting stay**) and opens the queue for the new one. `!activity end` closes and clears it. On the website: **Make active** / **End activity** (red buttons).
- **Everyone is removed from the queue after they play** (after `!next`). They `!join` again to get back in line. The streamer stays. **`!next blue` / `!next orange` = that team STAYS** for the next match (website: "Blue stays" / "Orange stays"); plain `!next` = everyone out.
- **InnocentPenguin plays every match** (added automatically). `!streamer out` = sitting out (his seat goes to the queue, 6 gold instead of 5). `!streamer in` = back in.
- **Fix a mistake in a past match:** `!matchwin <id> <blue|orange>` changes who won (wins and points are corrected), `!matchdel <id>` removes a match and takes back its stats. Easier on the site: **innocentpenguin.com/matches** (Change winner / Remove match). Every site change is listed in the Mod Hub's **Mod log**.
- **Game modes:** `!gamemode dropshot` or `!gamemode rumble` makes the next matches count on the Dropshot / Rumble tab of the Penguin League standings; `!gamemode standard` goes back to normal (2v2 / 3v3 / 4v4 count under their own size). Also in Master View > Settings.
- **Fortnite:** `!activity boxfights`, `!activity zonewars` (balanced customs, stats count, own standings tabs) and `!activity fnviewers` (Playing with Viewers). Ratings are **SR**: `!setsr @user 1500` (0-5000, default 1000). `!activity competitive` / `casual` / `viewers` switch back to Rocket League (MMR).
- **Casual = competitive without stats:** same teams and team mode (balanced / random / manual); the old group style is retired (`!casual` just says so). Also in Master View. **Add a player by hand** (Master View > Add a player) for YouTube / Kick / TikTok people; Twitch players use `!join` or the website.
- **OBS:** `!scene <name>` switches the OBS scene, `!source <on|off|toggle> <name>` shows / hides an overlay, `!obs auto on|off` makes the scene follow the game (ON by default) (Twitch category, or when you start a Fortnite / Rocket League activity). Also in Master View > OBS.
- **Strikes (0-3):** `!strike @user` / `!unstrike @user` (mods), `!strikes [@user]` (anyone). 3 strikes = can't join customs. Everyone loses one each time the stream goes live. Also on the player's website profile (Mod tools: Give / Remove a strike).
- **KOTH (king of the hill):** `!koth on|off` (off by default). `!finish orange|blue` (the Orange wins / Blue wins buttons under the player lists in Master View) records the result, then everyone is out; with KOTH on the winners stay on and new challengers come in.
- **King of the Hill activity:** `!activity koth`. Queue open to everyone; the first game you pick CLOSES it and the bot announces who is starting. Winners stay on (use the Orange wins / Blue wins buttons). Leaderboard by wins on the site.
- **`!activity rl|fn <activity>`:** e.g. `!activity rl koth`, `!activity fn boxfights`, `!activity fn viewers`. The game prefix also switches the OBS scene and the Twitch category. **`!check`**: self-test; anything wrong shows in RED in the website log. **`!problems`** / **`!problems clear`**: how many problems are open / empty the list (also saved in `problems.json`). The website's Problems tab has Re-check and Clear buttons.
- **Drag & drop (mod page):** `!out name` takes a player out of the match (empty slot; they go to the front of the queue), `!in name blue|orange` fills a slot (or moves someone between teams), `!move name 3` reorders the queue.
- **MMR:** `!setmmr name 1200` = set by a mod. Players can set their own in Settings. Tracker MMR is used otherwise.
