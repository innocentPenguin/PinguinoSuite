# HelperPinguino facts and wordings

HelperPinguino answers Minecraft, Discord and "how do I join" questions from `Data\runtime\helper_facts.json`.
The file is created on first use (seeded from what Nightbot and the other chatbots said in the chat logs of 2026-10-16) and **should be checked once**.

| Key | Meaning |
|---|---|
| McSmpIp | the 24/7 SMP server address (Java needs only this) |
| McHardcoreIp | the stream-only hardcore server |
| McBedrockPort / McHardcoreBedrockPort | the Bedrock ports (SMP 19132, hardcore 9216) |
| McRules | one short rules line |
| Discord | the invite link |
| Website | main site |

- **Website override:** every 10 minutes the helper reads `FactsUrl` (default `https://innocentpenguin.com/api/faq`, in `helper_settings.json`). The site serves `{"faq":[{"key","question","answer","url"}...]}` (05 owns it, data in the site repo `content/faq.json`); the helper uses the `minecraft_ip` entry (both IPs and both Bedrock ports are parsed from its text) and the `discord` entry. A flat `{"McSmpIp":"..."}` also works. A site value wins; a missing or failing endpoint is ignored.
- **Minecraft flow:** an "ip" or "minecraft" question with no edition makes the helper ask Java or Bedrock. Java gets the IP, Bedrock gets the IP and the port.
- **AI, then repeat:** the first `PhraseBankSize` (3) answers per question are worded by the AI from the facts (each is rejected unless it contains the exact IP, port or link), stored in `helper_phrases.json`, and from then on the stored wordings repeat with no AI call. Changing a fact clears that question's stored wordings.
- **Key words** that bring the helper in unprompted: how, join, ip, !discord, minecraft, lobby, code, password, register, queue.

## Training mode (2026-10-20): the Helper is the only chatting bot

ChattyPinguino's own chatting is OFF (`ChatReplies: false` in `chat_settings.json`; set `true` to bring it back). It still logs and studies chat, and `!8ball`, `!forgetme` and the mod commands still work. HelperPinguino answers **only when somebody really needs help**, in **one or two short lines**, and points to the website for anything longer. Banter, statements, passing mentions, questions meant for another viewer, and repeats are left alone.

### Where the helper sends people (real site links, `SiteBase` in `helper_settings.json`)

| Question about | Answer points to |
|---|---|
| chat commands, "what can the bot do" | https://innocentpenguin.com/help#commands |
| leaderboards, top gifters/bitters/yappers/streaks, rankings | https://innocentpenguin.com/leaderboards |
| my profile, my stats/strikes, "what does the bot know about me" | https://innocentpenguin.com/members |
| rules, what a strike is, common questions | https://innocentpenguin.com/faq |
| 7TV emotes, emote search | https://innocentpenguin.com/emotes |
| Minecraft, Discord, lobby, joining, registering | the facts above (IP, port, invite, lobby) |

### Training cases (kept as tests in `Tests/helper/harness.cs`)

- **Should answer:** "what commands are there?", "is there a list of commands?", "where can i see the leaderboards?", "who has gifted the most subs?", "where do i find my profile?", "what are the rules?", "what are strikes?", "which emotes are there? 7tv".
- **Should stay silent:** "lol the commands in this game are crazy", "i love the leaderboards on this site", "gg that was a good round", "my commands are broken on my keyboard haha", "the rules of rocket league are weird", and "@Someone what commands are there?" (meant for somebody else).
- **Short + link:** every site answer is one line, under 160 characters, with the https link.

### Help-review log (private, never pushed to the website)

`Data\helpereview.jsonl` records every helper answer and every probably-missed question (it looks like a help request, the helper stayed quiet). Each entry has the chat from ALL chatters before it (`ReviewBefore`, default 8) and after it (`ReviewAfter`, default 8, up to `ReviewAfterSec` = 300 s), the helper's reply or the silence reason ("not a real question", "someone else already answered", "cooldown", "no pattern or AI intent matched"...), and a note field for Ivan. Browse it at `http://127.0.0.1:8770/helper-review` (JSON: `GET /api/helper/review?kind=missed|answered&q=&limit=`; save a note with `POST /api/helper/review {id, note}`; notes live in `Data\helpereview_notes.json`). Loopback only.
