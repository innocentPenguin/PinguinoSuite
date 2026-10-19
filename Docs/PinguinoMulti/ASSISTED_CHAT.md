# Assisted chat — design (Unit 03, 2026-10-19)

**Goal:** help Ivan while he reads and answers the unified chat. Everything is a *suggestion*; nothing is ever sent without a click.

## Principles
1. **Never auto-send.** AI drafts; Ivan clicks *Use* (fills the reply box so he can edit) or *Send* (one click, to exactly that message's platform).
2. **Works without AI.** Every feature has a local fallback (templates, rule-based question detection). AI is optional and cost-capped.
3. **Cheap and private.** AI calls share the existing daily cap (`ai_daily_cap_usd`), are cached by text, time out fast, and send only the message, the sender's login and up to 4 earlier messages from that sender. Keys come from Credential Manager or the Suite key vault (`MULTI_AI_KEY`), never JSON.
4. **Right account.** Replies go out through Multi's signed-in account per platform (today: Ivan's own). Sending as a bot account is phase 2 and needs a Host send endpoint (02): until then Multi does not pretend to.

## Slice 1 (built now)
| Feature | How |
|---|---|
| Suggested replies | `POST /api/assist/suggest {message_id}` → 3 short drafts (AI, cost-capped, cached). No AI / over cap / error → drafts from the quick-reply templates, labelled "templates". |
| Translate | `POST /api/assist/translate {message_id}` → English text (AI, cached). The 🌐 button shows only on messages that look non-English. |
| Chatter card | `GET /api/chatter/{platform}/{user_id}`: first/last seen, message count, badges seen, answered/missed history, private note, muted?, recent messages. Opens from a click on any name. |
| Notes | existing `GET/POST /api/viewers/{user}/note`, edited inside the chatter card. |
| Quick-reply templates | `GET/POST /api/templates` (≤ 20, `{name}` is replaced by the chatter's name); chips above the reply box. |
| Mark to answer | `POST /api/cards/manual {message_id}` makes a normal priority card from any message (the ★ button). |
| Questions for me | filter chip: messages that look like a question or mention Ivan (uses the existing explainable rules). |
| Moderation | 🔇 mute viewer (local), ⏱ timeout / ⛔ ban / 🗑 delete via Twitch Helix when the moderator scopes are granted (see SITE_SCOPE_PROPOSAL.md). |

## Phase 2 (not built)
- Reply as a bot account through a Host send endpoint (02); per-bot persona.
- Auto-translate toggle for a whole chat, and translating Ivan's reply into the chatter's language.
- Draft style learning from the replies Ivan actually sends (feeds the existing learning view).
- Shoutout / lore snippets from `Data\lore.json` in suggestions.

## Cost and safety
- One suggestion ≈ one small call (≈ 0.0012 USD estimate, 3× the ranking estimate); translate ≈ 0.0006. Both stop at the daily cap and fall back.
- Prompt injection: chat text is passed as quoted data, replies are capped at 200 characters, links are stripped from drafts, and the result is only ever shown to Ivan.
- Console log source `assist` records counts and failures, never message text or keys.
