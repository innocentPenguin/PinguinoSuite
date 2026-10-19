# PinguinoBot commands

The website reads `commands.json`, which is the source of truth. This page is the human-readable copy of it.

## Community Games: everyone
| Command | What it does |
|---|---|
| `!register <EpicID>` | Link your Epic name |
| `!join` / `!leave` | Join or leave the queue |
| `!pos` | Your place in the queue |
| `!myrank` | Your MMR |
| `!lobby` | Current teams |
| `!stats [user]` | Wins, losses and points |
| `!topwins` | Wins leaderboard |
| `!queue` / `!queue list` | Queue status and list |

## Community Games: mods
| Command | What it does |
|---|---|
| `!queue open\|close\|clear` | Manage the queue |
| `!balance` | Make new teams |
| `!match clear\|fill\|queue` | Clear = game over, empty the match (they leave the queue). Fill = make teams / fill empty slots. Queue = match back to the front of the queue |
| `!reroll` | Different teams with the same players, refilling anyone who left |
| `!win blue\|orange` | Record the winner (only once per match) |
| `!next` / `!next blue` | Rotate everyone out / the winner stays on |
| `!mode balanced\|random\|picks` | How teams are made |
| `!pick a b c` / `!pick auto` | Choose Blue in picks mode |
| `!format 2v2\|3v3\|4v4` | Team size |
| `!kick @user` | Remove someone from the queue |
| `!mmr @user` | Look up a player's MMR |
| `!setmmr @user <mmr\|rank\|auto>` | Set a player's MMR, or `auto` to go back to Tracker Network |
| `!register @user <EpicID>` | Register or fix someone else's Epic name |

## Firsts
| Command | What it does |
|---|---|
| `!first` | Your First 5 record |
| `!firsts` | First 5 leaderboard |
| *(any chat message)* | The first 5 unique chatters claim 1st to 5th place, paid out every 5 minutes |
