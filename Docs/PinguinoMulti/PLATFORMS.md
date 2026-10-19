# PinguinoMulti — Platform feasibility

Status: Twitch implemented; others are researched from prior knowledge and **must be re-verified against live docs before coding**.

| Platform | Read | Send/reply | Auth | Label |
|---|---|---|---|---|
| Twitch | EventSub WS `channel.chat.message` (`user:read:chat`) | Helix `POST /chat/messages`, `reply_parent_message_id` (`user:write:chat`) | OAuth + refresh via site | Official — **built** (untested with a live token) |
| YouTube | `liveChat.messages` polling/stream, quota-heavy | `liveChatMessages.insert`, no threads | Google OAuth (sensitive scopes) | Official, M3 |
| Kick | Official API + webhooks (needs public URL) or Pusher WS | chat send via OAuth | Kick OAuth PKCE | Official/UNOFFICIAL fallback, M3 |
| Discord | Gateway bot, MESSAGE_CONTENT intent | send/reply | bot token | Official, M3 |
| TikTok | no official LIVE chat API | none | n/a | UNOFFICIAL, read-only, off by default, M4 |

Rules: connectors declare capabilities; UI never offers what a platform cannot do; ids are `platform:channel:id`; one reader per platform.
