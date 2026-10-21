# PinguinoBot commands

The website reads `commands.json`, which is the source of truth (the Host also serves it at `GET /api/commands-doc` with viewer / mod lists and a permission field). This page is generated from it (python Tools/gen-commands-md.py); edit the JSON, not this page.

## Viewer commands

### Chat bot

| Command | Usage | What it does |
|---|---|---|
| `!forgetme` | `!forgetme` | ChattyPinguino forgets everything it remembers about you. |
| `!rememberme` | `!rememberme` | Let ChattyPinguino remember things about you again. |
| `!memory` | `!memory` | Shows what ChattyPinguino remembers about you. |
| `!8ball` | `!8ball <question>` | Ask the magic 8-ball. The bot answers in its own voice and may nod to public things like your sub, watch streak or what chat was just saying. Limited to once every 45 seconds per person. |

### Community Games

| Command | Usage | What it does |
|---|---|---|
| `!pm` | `!pm` | The current private match name and password (one shared setting; mods change it with !lobbyname / !lobbypass). |
| `!register` | `!register <EpicID>  \|  mods: !register @viewer <EpicID>` | Link your Twitch name to your Epic Games name. Mods can register or fix someone else's. |
| `!join` | `!join` | Join the queue (must be registered, queue must be open). |
| `!leave` | `!leave` | Leave the queue. |
| `!pos` | `!pos` | Show your place in the queue. |
| `!myrank` | `!myrank` | Show your MMR on file and where it came from. |
| `!lobby` | `!lobby` | Show the current Blue and Orange teams. |
| `!stats` | `!stats [user]` | Wins, losses and points for you or another player. |
| `!topwins` | `!topwins` | Top 5 community-games players by wins (ties broken by points). |
| `!queue` | `!queue  \|  !queue list  \|  mods: !queue open \| close \| clear` | Queue status. Mods open, close, or clear (clear also closes and ends the lobby). |
| `!mmr` | `!mmr [@user]` | Your own MMR (mods can look up anybody). |
| `!strikes` | `!strikes` | How many strikes you have (3 = cannot join customs), split into permanent (red, never expire) and temporary (orange, one wears off per day). |

### Emotes

| Command | Usage | What it does |
|---|---|---|
| `!emote` | `!emote <name>` | How often an emote from the channel's 7TV set has been used in chat, its rank, the top user and when it was last used. |
| `!topemotes` | `!topemotes [month]` | The most used 7TV emotes in chat, all time or for one month (oct, 2026-10, last). Emotes that are also everyday words are left out. |

### Firsts

| Command | Usage | What it does |
|---|---|---|
| `!first` | `!first` | Your First 5 record (1st-5th place counts and total). |
| `!firsts` | `!firsts` | Top 5 First 5 leaderboard. |
| `(chat message)` | `Just chat when the game is running` | First 5 unique chatters claim 1st-5th. Payout via !addpoints every 5 min: 15000 / 10500 / 7500 / 4500 / 3000. |

### Help

| Command | Usage | What it does |
|---|---|---|
| `!commands` | `!commands` | Link to the website help page with every chat command and a search box. |
| `!helper` | `!helper <question>` | Ask the helper a question about the stream, commands, the queue or the website. It answers in one short line from its knowledge pack and points you to the right page. Once every 30 seconds per person; it stays silent for anyone who opted out or used !unping. |

### Leaderboards

| Command | Usage | What it does |
|---|---|---|
| `!leaderboards` | `!leaderboards` | Link to the website leaderboards (top gifters, bitters, yappers and watch streaks, all time or by month). |
| `!topgifters` | `!topgifters [month]` | Top 5 subscription gifters (subs gifted). Add a month (oct, october, 2026-10, this, last) for that month only. |
| `!topbits` | `!topbits [month]` | Top 5 bit cheerers, all time or for one month. |
| `!topyappers` | `!topyappers [month]` | Top 5 chatters by number of chat messages, all time or for one month. |
| `!gifted` | `!gifted [user]` | How many subs you (or someone) gifted in total, and the rank on the gifters board. |
| `!bits` | `!bits [user]` | Total bits cheered, the bits badge tier and the rank on the bits board. |

### Points

| Command | Usage | What it does |
|---|---|---|
| `!points` | `!points [user]` | Your points balance and rank (earned by watching, imported from StreamElements). |
| `!watchtime` | `!watchtime [user]` | How long you have watched the channel, and your rank. |
| `!toppoints` | `!toppoints [month]` | Top points holders, all time or for one month. |
| `!topwatch` | `!topwatch [month]` | Most watch time, all time or for one month. |

### Rocket League

| Command | Usage | What it does |
|---|---|---|
| `!rank` | `!rank [epic name] [1s\|2s\|3s\|4s\|hoops\|rumble\|dropshot\|snowday\|heatseeker]` | Rocket League ranks. With no name it shows Innocentpenguin_'s 1v1, 2v2 and 3v3; add a playlist (2s, 2v2, dropshot, heatseek, rumble, hoops...) for just that one. Every playlist is pulled in one tracker call per Epic account and cached for 15 minutes, so extra lookups cost nothing. |

### Stream

| Command | Usage | What it does |
|---|---|---|
| `!uptime` | `!uptime` | How long the stream has been live. |
| `!downtime` | `!downtime` | How long ago the last stream ended. |

### Subscribers

| Command | Usage | What it does |
|---|---|---|
| `!sub` | `!sub [user]` | Subscription tier, months, streak and Founder status from the subscriber list. |
| `!founders` | `!founders` | Lists the Founders (Twitch Founders Badge holders). |

### Timers

| Command | Usage | What it does |
|---|---|---|
| `!remindme` | `!remindme <time> <what>` | The bot @mentions you in chat when the time is up (1 minute to 24 hours, up to 3 open reminders). Survives restarts. |
| `!reminders` | `!reminders` | Your open reminders and when they are due. |
| `!cancelreminder` | `!cancelreminder [number]` | Cancel one of your reminders (number from !reminders). |

### Tournament

| Command | Usage | What it does |
|---|---|---|
| `!me` | `!me` | Join the tournament wheel while sign-ups are open (also a Join button on the website tournament page). |

### Watch Streaks

| Command | Usage | What it does |
|---|---|---|
| `!topstreak` | `!topstreak [month]` | Top 5 watch streaks people have shared in chat (best streak), all time or for one month. Only people who shared a streak are on the board. |
| `!streak` | `!streak [user]` | The last watch streak someone shared (and their best). Twitch only shows a watch streak when the viewer shares it. |
| `!streakrecord` | `!streakrecord [user]` | The best watch streak someone has shared, with the date. |


## Moderator commands

### Bot care

| Command | Usage | What it does |
|---|---|---|
| `!problems` | `!problems [clear]` | List what the bot found wrong, or clear the list. |
| `!check` | `!check` | Self-test: problems go to the website log. |
| `!pg` | `!pg status \| core\|chat\|helper on\|off \| test \| cutover` | Quick control of the bots from chat. Everyone else gets no answer. |

### Channel control (mods)

| Command | Usage | What it does |
|---|---|---|
| `!poll` | `!poll "question" a\|b\|c [seconds]` | Starts a Twitch poll (2-5 options, 15-1800 s). The result is said in chat when it ends. |
| `!predict` | `!predict "question" a\|b [seconds]` | Starts a Twitch prediction. Streamer and mods the streamer allows. |
| `!lock` | `!lock` | Locks the open prediction (no more votes). |
| `!resolve` | `!resolve <number or name>` | Pays out the prediction to the winning outcome. |
| `!cancel` | `!cancel` | Cancels the prediction and refunds the points. |
| `!slow` | `!slow [seconds\|off]` | Slow mode (3-120 s, default 30). |
| `!emote-only` | `!emote-only [off]` | Emote-only chat on or off. |
| `!followers` | `!followers [minutes\|off]` | Followers-only chat. |
| `!subs-only` | `!subs-only [off]` | Subscriber-only chat on or off. |
| `!title` | `!title <new stream title>` | Changes the stream title. |
| `!game` | `!game <category name>` | Changes the stream category (game). |
| `!allow` | `!allow [user]` | Releases a message AutoMod is holding (the newest one, or the newest from that user). |
| `!announce` | `!announce [blue\|green\|orange\|purple] <text>` | Posts a highlighted Twitch announcement. |
| `!marker` | `!marker [note]` | Adds a stream marker at this moment. |
| `!shield` | `!shield on\|off` | Shield mode on or off (streamer only). |
| `!ad` | `!ad [30\|60\|90\|120\|150\|180]` | Runs an ad break after a 30 second warning in chat (streamer only). |
| `!vip` | `!vip <name>` | Makes someone a VIP (streamer only). |
| `!unvip` | `!unvip <name>` | Removes someone's VIP (streamer only). |
| `!raid` | `!raid <channel>` | Streamer only, and only channels on the raid list. The bot asks you to say !confirm raid within 20 seconds. Never starts by itself. |
| `!confirm` | `!confirm raid` | Confirms the pending raid. Must be typed in Twitch chat. |
| `!unraid` | `!unraid` | Cancels the pending raid, or the raid that is counting down. |

### Chat bot

| Command | Usage | What it does |
|---|---|---|
| `!chatbot` | `!chatbot on\|off` | Switch ChattyPinguino on or off. |
| `!golive` | `!golive [time]` | Set when the stream starts, for the countdown message. |
| `!opinion` | `!opinion <user> \| !opinion reset <user> \| !opinion refresh <user\|all> \| !opinion status` | The bot's private weekly note on what it thinks of a regular (used only to colour its tone; never shown in chat or on the website). <user> whispers you the note. Alias accounts are merged; people who used !forgetme or !optmeout get none. |

### Community Games

| Command | Usage | What it does |
|---|---|---|
| `!balance` | `!balance` | Rotate current players out and build new teams from the queue using the current mode. |
| `!match` | `!match <clear\|fill\|queue>` | clear = game over: everyone in the match leaves the queue, nobody is pulled in. fill = make teams from the queue, or fill empty slots. queue = put everyone in the match back at the front of the queue. Website: Clear / Fill / Move all ➜ Queue under the teams. |
| `!reroll` | `!reroll` | Different teams with the same players. Refills anyone kicked/left from the queue. |
| `!win` | `!win <blue\|orange>` | Record the winner and award points. A match can only be scored once. |
| `!next` | `!next  \|  !next <blue\|orange>` | Viewers: shows who is next in the queue (read-only). Mods: !next = everyone rotates out. !next blue = record Blue win (if not already) and Blue stays on vs new challengers. |
| `!mode` | `!mode <balanced\|random\|picks>` | How teams are made. |
| `!pick` | `!pick <names for Blue>  \|  !pick auto` | In picks mode, after !balance: listed players go Blue, the rest Orange. 'auto' balances instead. |
| `!format` | `!format <2v2\|3v3\|4v4>` | Team size for the next match. |
| `!kick` | `!kick @user` | Remove someone from the queue. Follow with !reroll if they were in the lobby. |
| `!setmmr` | `!setmmr @user <mmr\|rank\|auto>` | Manually set MMR (number or rank like gc1, c2, d3). 'auto' goes back to Tracker Network. |
| `!koth` | `!koth on\|off` | Switch King of the Hill on or off. |
| `!strike` | `!strike @user [perma\|toxicity\|slurs]` | Give a temporary strike (wears off after a day). Add perma, toxicity or slurs for a PERMANENT strike (red, never expires). |
| `!unstrike` | `!unstrike @user [perma]` | Take a temporary strike away. Add perma to remove a permanent one. |
| `!finish` | `!finish <blue\|orange>` | End the King of the Hill game: record the winner and rotate the queue. |
| `!activity` | `!activity [rl\|fn] competitive\|casual\|koth\|viewers\|boxfights\|zonewars\|end` | Pick what kind of game the stream is running. |
| `!gamemode` | `!gamemode standard\|dropshot\|rumble` | Rocket League game mode for stats. |
| `!setsr` | `!setsr @user <0-5000>` | Set a Fortnite skill rating. |
| `!matchwin` | `!matchwin <id> blue\|orange` | Fix the winner of a past match (stats are corrected). |
| `!matchdel` | `!matchdel <id>` | Remove a past match and take its wins back. |
| `!move` | `!move <user> <position>` | Move someone in the queue. |
| `!out` | `!out <user>` | Take a player out of the current match. |
| `!in` | `!in <user> <blue\|orange>` | Put a player into a team. |

### Helper

| Command | Usage | What it does |
|---|---|---|
| `!lobbyname` | `!lobbyname <name> \| off` | Set (or clear) the private match name PinguinoHelper tells viewers to search. |
| `!lobbypass` | `!lobbypass <password> \| off` | Set (or clear) the private match password PinguinoHelper shares. |

### Leaderboards (mods)

| Command | Usage | What it does |
|---|---|---|
| `!alias` | `!alias add <old login> <main login> \| !alias remove <old login> \| !alias list` | One person with several accounts: their gifts, bits, messages and streaks are combined under the main login on the boards. Edits Data\boards\aliases.json. |
| `!boards` | `!boards refresh \| !boards status` | refresh = recompute every leaderboard now and push it to the website. status = people, months and the last push result. |
| `!subs` | `!subs import \| !subs status` | import = read any new subscriber-list*.csv (Downloads or Data\subs\incoming) into the subscriber list. status = counts by tier, lapsed, founders. |
| `!streaks` | `!streaks backfill \| !streaks status` | backfill = read old chat logs for watch streaks people shared (safe to repeat). status = how many people shared one. |
| `!names` | `!names refresh` | Ask Twitch again for everyone's real display name (capital letters) and update the boards. |
| `!lookup` | `!lookup <user>` | Shows everything on record for a person: aliases, subscription, gifts, bits, messages and watch streak. |

### OBS

| Command | Usage | What it does |
|---|---|---|
| `!scene` | `!scene <name>` | Switch the OBS scene. |
| `!source` | `!source on\|off\|toggle <name>` | Show or hide an OBS source. |
| `!obs` | `!obs auto on\|off \| !obs status` | Automatic OBS scene switching and status. |

### Points

| Command | Usage | What it does |
|---|---|---|
| `!addpoints` | `!addpoints <@user\|all> <n>` | Broadcaster only, silent. Adds points (a negative number takes them, never below 0). Hidden: no chat reply, logged. |
| `!editpoints` | `!editpoints @user <n>` | Broadcaster only, silent. Sets someone's points to exactly this number. Hidden: no chat reply, logged. |
| `!removepoints` | `!removepoints @user <n>` | Take points away from someone. |
| `!economy` | `!economy status\|import\|apply <id>` | Points system status; import from StreamElements (dry run, then apply with the report id). |

### Rocket League

| Command | Usage | What it does |
|---|---|---|
| `!setrank` | `!setrank 1v1\|2v2\|3v3\|peak <rank text>` | Mods update the rank !rank shows. You can also paste a whole 'Ranked 1v1: ... \| Ranked 2v2: ...' line. |

### Timers

| Command | Usage | What it does |
|---|---|---|
| `!timer` | `!timer list \| on <name> \| off <name> \| add <minutes> <message> \| remove <name> \| now <name> \| gap <seconds>` | Chat timers: repeating messages that only run while live, after enough chat, and never closer together than the gap. Survive restarts. |
| `!remind` | `!remind @user <time> <what>` | Set a reminder for someone else; the bot @mentions them when it is due. |
| `!countdown` | `!countdown <time> [label] \| pause \| resume \| stop` | Start the on-stream countdown (the site timer overlay shows it); says a line at zero. |
| `!stopwatch` | `!stopwatch start [label] \| stop \| reset` | On-stream stopwatch. |
| `!addtime` | `!addtime <time>` | Add (or with a minus, take off) time on the running countdown. |
| `!stoptimer` | `!stoptimer` | Clear every on-stream timer. |

### Tournament

| Command | Usage | What it does |
|---|---|---|
| `!wheel` | `!wheel new\|open\|close\|draw\|spin [n]\|undo\|reset\|announce\|end \| mode random\|balanced \| size 1-4 \| odd waitlist\|trio\|partial\|hold\|mod \| eligibility all\|subs \| remove <user> \| mmr <user> <n>` | Run the tournament wheel: sign-ups, the draw, one spin per pick (the last pick reveals itself), team announcements go to chat by themselves. |
| `!spin` | `!spin [n]` | Shortcut for !wheel spin: reveal the next pick (or up to pick n). |
| `!practice` | `!practice on [n] \| add [n] \| off` | Rehearse with fake players (practice01...). They fill the queue, matchmaking and the wheel but are never saved or counted anywhere. |

