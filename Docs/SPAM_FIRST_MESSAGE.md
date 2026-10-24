# Spam in the first message: survey and proposed design

Written by 11 on 2026-10-23 for 10. Design only; nothing is implemented. Toggle must ship OFF until Ivan says.

## 1. What happened tonight (from Data\chat_logs and Data\boards)

| Time (CDT) | Account | Message | What the bots did | What happened to the account |
|---|---|---|---|---|
| 22:27:01 | succeedingsteelbqdzvkxr | `Best viewers with viewers streamboo .org` | ChattyPinguino greeted them in the same second ("hey, welcome to the chat!") | `* succeedingsteelbqdzvkxr was banned` in the same second |
| 22:27:16 | dramaticlacencjhwz | the same text | Chatty greeted them ("welcome in, first time here?") | `* dramaticlacencjhwz was banned` in the same second |

- Both were banned by something else, within the same second as the post, so it is automatic and not one of our bots. Our logs only record "was banned", with no actor (the EventSub channel.ban subscription gets a 403 for lack of scopes, so no actor is recorded either). Who or what banned them (Twitch's own filters, a mod tool, a mod) has to be checked in Twitch's mod view.
- Our side did NOT time out, delete or hold anything. The Host has no spam rule.
- Two real problems on our side: (1) Chatty welcomed both accounts; (2) `Welcome.OnChat` (HostWelcome.cs) paid each one the 100-point welcome bonus about 45 s later (`ap:welcome:<login>` in Data\boards\metric_events.jsonl, both logins are in Data\economy\points.json) although they had already been banned. A spam account that is banned in the same second ends up with points and a place in the boards.
- I could not tell from our data whether AutoMod held either message; the bans are what shows.

## 2. What exists today

| Piece | What it does about spam |
|---|---|
| Twitch AutoMod / Shield / mod tools | Does the real work (the two bans above). We only listen: `AutomodHeld` (HostAutomod.cs) keeps held messages so a mod can `!allow` one. |
| `ChannelControl.Timeout(user, seconds, reason)` (HostChannel.cs) | A working timeout through Helix `/moderation/bans`. Refuses the broadcaster, our bot accounts, mods and VIPs (mod check also asks Twitch). Used by the mod API in HostAutoApi.cs:149. No sub check. |
| Message delete | None. Scope `moderator:manage:chat_messages` is listed as OPTIONAL in HostAccount.cs; it is in the `Scopes` string in HostApi.cs, so it may or may not be on the current token. Needs a check before a delete is promised. |
| `Roster` (HostCredits.cs) | Remembers every chatter that spoke while the Host ran: first/last seen, message count, role, sub. `Roster.Note` runs first in `Program.Dispatch`, so "no prior chat memory" can be read from it right before the note is made (see below). |
| Twitch first-message flag | `firstMsg` is already passed into `Program.Dispatch` and used by Welcome and by Chatty's `FirstMessage`. |
| PinguinoB0t (the Core bot) | Has no spam logic at all; nor have Chatty or the Helper. Chatty only decides tone. |

## 3. Where detection should live

**In the Host, in `Program.Dispatch`, as the first step after `ReplyCtx.Begin`** (before `Roster.Note`, `Welcome.OnChat`, `Economy.OnChat`, the chat log feeds and every bot).

Why there and not elsewhere:
- Every chat line already passes through it, with `role`, `isSub`, `firstMsg` and `userId`, and a `return` there keeps the bots from ever seeing the line. That fixes problem (1) and (2) above for free: no greeting, no welcome bonus, no board entry.
- The Host owns Twitch credentials and `ChannelControl.Timeout`. The B0t cannot call Helix moderation itself.
- AutoMod settings are Ivan's and live on Twitch; our rule is an extra net for what AutoMod lets through, not a replacement.
- Chatty has the "first message" knowledge but is a language bot and must stay out of moderation decisions.

## 4. Minimal safe design

New small class `FirstMsgSpam` (own file, `HostFirstMsgSpam.cs`), config `Data\config\spam_first.json`:

```json
{ "enabled": false, "timeoutSeconds": 600, "deleteMessage": true, "dryRun": true,
  "phrases": ["best viewers", "cheap viewers", "streamboo", "buy followers"],
  "domains": ["streamboo.org"] }
```

Rules (all must hold, otherwise the line is untouched):

1. `enabled` is true (default **false**). With `dryRun` true (default) it only logs what it would have done.
2. The line is the account's first message: Twitch's `firstMsg` flag is true AND `Roster` has no entry for the login yet (no chat memory), AND no chat-log history for it (cheap lookup in the live log index).
3. Never for: broadcaster, mods (`role >= 3`), VIP (`role == 2`), subs (`isSub`/`subTier > 0`), our bot accounts and the `ProtectedLogins` (`ChannelControl.Timeout` already refuses these, but the check is done first so we do not even spend a Helix call).
4. The text matches one of: a URL (`https?://`, `www.`), a domain-like token (`word[ .]*(com|org|net|io|gg|tv|ly|xyz|...)` including the spaced form "streamboo .org" and "dot" spellings, after lowercase and removing zero-width characters), or a configured spam phrase.
5. Then, in this order: skip all further handling of the line (`return` from Dispatch before Welcome/bots), `ChannelControl.Timeout(user, timeoutSeconds, "first-message link spam (auto)")`, and (if the optional delete scope is present) delete that message by `msgId` through `DELETE /moderation/chat?broadcaster_id=&moderator_id=&message_id=`. A timeout alone also clears the visible message on Twitch for most clients; delete is a bonus.
6. Log every decision (match or dry run) to `Data\logs\spam_first.log` with login, matched rule, the first 80 characters of the text and the result; also `Clog.Info("spam", ...)`. Nothing is said in chat.
7. One timeout per login per 10 minutes (a small in-memory set) so a retry cannot stack calls.

Safeguards:
- Dry run first: Ivan flips `enabled` on with `dryRun` true, watches the log for a stream, then sets `dryRun` false.
- A real new viewer who pastes a link in message one is the cost: the timeout is 10 minutes, not a ban, and the log shows it so a mod can untimeout. A `!spamfree <user>` mod command (untimeout and add to a per-login allowlist) is a cheap follow-up.
- The bots stay silent on a matched line, so a spammer gets no greeting, no 100 points and no board entry.
- It never runs for `Control.Synthetic` lines or in `--sim` unless a test sets `PINGUINO_SPAM_TEST=1` (tests use a mock Helix, like the other Host tests).

## 5. Related small fix (independent of the toggle, recommend doing it regardless)

`Welcome.OnChat` pays the bonus after a 45 s delay without checking the account is still allowed to chat. Add a check just before `Economy.Credit`: skip when a ban/timeout notice for that login was seen in those 45 s. The Host already sees the IRC `CLEARCHAT`/"was banned" notices (they land in Data\chat_logs\...\notices); a simple in-memory "banned recently" set fed from that notice stream is enough. Chatty's greeting is sent in the same second as the message, so it cannot be avoided this way; only rule 5 above stops the greeting.

## 6. Open points for Ivan

- Should it also cover first messages with a spam phrase but no link? (Default in the design: yes, via the phrase list.)
- Timeout length (default 10 min) and whether deleting should be required (needs the `moderator:manage:chat_messages` scope on the token).
- Whether subs-by-gift, new followers or accounts younger than N days should also be exempt or, the other way round, more suspicious. Twitch's account age is not read today.

## 7. Suggested tests (for when it is implemented)

Sim Host with a mock Helix: first message with link → timeout call, no bot reply, no welcome credit; same text from a mod, a sub, a VIP, a bot, a chatter with Roster history → untouched; `dryRun` → log line only; `enabled` false → untouched; spaced domain "streamboo .org" and zero-width characters match; one timeout per login in 10 minutes.
