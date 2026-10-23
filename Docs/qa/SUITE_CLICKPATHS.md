# Suite click paths (for 60 - QA & Docs, real window)

Written by 22 - Master View, 2026-10-23. Purpose: walk every page by hand in the real Tauri window.
Each row has the step, the expected result, and what a failure looks like.

Legend
- SAFE = reads only, or changes something local and reversible. Fine on the real Host, live or not.
- CAUTION = writes real Host state (a toggle, a setting, a team name). Reversible, but viewers may see it. Do it off-stream, put it back.
- DO NOT CLICK on a live stream = posts to real chat, spins, switches scenes, or changes what viewers see. Only use when the stream is offline, and only if the step says why.
- NEVER anywhere: go live in OBS, start a stream, use the Start streaming button of any tool, sign in / OAuth. There is no go-live control in Master View; if you ever see one, that is a bug, report it.

Before you start
- The Host pill (top right of Master View) should read "Host" with a ms value (live push = SSE, or polling). Red or "offline" = the Host is down; every write will toast an error and a banner shows. Not a Master View bug.
- Use the mock for anything marked "mock only": `node Tests\master\mock-host.mjs` (port 8798), page `App\src\master\master.html?host=http://127.0.0.1:8798&music=http://127.0.0.1:8798&multi=http://127.0.0.1:8798`. Never point it at the real Host.

---------------------------------------------------------------------------
## 1. Master View (sidebar item "Master View")

### 1.1 Header
| Control | Safe? | Expected | Failure looks like |
|---|---|---|---|
| Pills Live / OBS / Rec / Replay / Chat | SAFE (read only) | Coloured dot + text; grey when unknown; hover shows what each is | Stuck on "…" for more than ~10 s; OBS pill red while OBS is open (check OBS websocket) |
| Host pill | SAFE | "Host NN ms", SSE or polling; updates | Shows offline while Host is up, or ms never updates |
| 🎬 Last stream (Shift+L) | SAFE (read only: GET /api/recap/preview) | Banner with the recap line and the best clip link; ⟳ reloads it | Banner says error with the Host reachable; clip link not https |
| Raid prep (Shift+R, 2nd press confirms) | **DO NOT CLICK on a live stream** | First click arms (label changes, reverts after a few seconds). Second click says the prepare-your-emotes line in real chat once (a second raid-prep within the guard window says "duplicate"). Does not start a raid | One click fires without arming; or fires twice. Test in sim/mock only |
| ? (or the ? key) | SAFE | Shortcut table opens, Esc closes | Table lists a shortcut that does nothing |

### 1.2 Scenes panel (left, top)
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Look at list | SAFE | Scenes with a LIVE badge on the active one; folders collapsible (⇕ collapses/expands all) | Empty list while OBS is connected |
| Click a scene row | **DO NOT CLICK on a live stream** (switches the program scene viewers see) | Scene becomes LIVE, Sources panel follows it | Stays on the old scene, toast with an error |
| Click the eye/toggle on a source row | **DO NOT CLICK on a live stream** (toggles a visible source) | Source shows or hides in OBS | Toggle reverts after a second (OBS refused) |
| ⟲ live in Sources header | SAFE | Sources panel returns to the live scene | Nothing happens |
| Search box at the bottom ( / focuses it) | SAFE | Filters scenes, sources and the Commands list | Typing does not filter |

### 1.3 Customs tab
Everything here talks to the real Host. Use the 🧪 Simulator button first (fake players; nothing is sent to the Host) for all of it. Real-Host runs only when the stream is offline.
| Control | Safe? | Expected | Failure |
|---|---|---|---|
| 🧪 Simulator toggle | SAFE | "Simulator" mode, banner, fake queue appears | Real queue mixes with fake players |
| Simulator Chat: ON | **DO NOT CLICK on a live stream** (speaks the simulator's events in REAL Twitch chat through Chatty) | Button flips to ON, simulator events are said in chat | Chat lines appear without pressing it. Leave it OFF always |
| + Player, + 4, + 8, Remove one, Reset sim | SAFE (simulator only) | Queue count changes | Count off by one, or Host state changed |
| Streamer In / Out | CAUTION | Button highlights, queue shows streamer marker | Highlight flips back (Host refused) |
| Queue Open / Close | CAUTION (viewers see the queue state) | Highlight changes, next queue poll agrees | Reverts after a second |
| Queue Clear | CAUTION, two clicks (armed) | Queue empties | Single click clears it (no arming) |
| Match: ▶ Start / Fill empty slots / Move all → Queue | CAUTION | Teams fill from the queue | Wrong number of seats (RL 2v2 = 4, Fortnite size n = 2n) |
| Match: Clear match | CAUTION, two clicks | Match ends without a winner | One click clears |
| Orange wins / Blue wins (names follow team names) | CAUTION; posts a real result line in chat | Match finishes, wins counted | Wrong team credited; enabled while no game runs |
| Teams: Balanced / Random / Manual, Reroll, Balance, Set Blue / Auto | CAUTION | Mode highlight; team columns change | Manual input accepted for a player who is not in the match |
| Activity: Competitive, Casual, KOTH, Viewers, End activity | CAUTION (changes the live customs mode, two clicks) | Active one lit; the overlay game follows (Rocket League) | Fortnite buttons switch the overlay to Rocket League |
| Fortnite: Box fights, Zone wars, Viewers, KOTH | CAUTION (two clicks) | Active one lit; overlay game becomes Fortnite; team sizes become 1/2/3 + custom 1..16 | Overlay still on Rocket League |
| Settings: Team size, Fortnite size 1/2/3 + Set, Game mode | CAUTION | Highlight; size shows next to the heading | Size 17 accepted |
| Team names & colours (swatches, colour picker, Reset) | CAUTION (public: overlays/site tint) | Name and colour update in panels and overlays; chat lines keep 🔶 Orange / 🔷 Blue | Name saved but colour lost, or the picker snaps back to the old colour |
| Strike buttons next to a player (✕, + I, + I perma, −) | CAUTION (real strikes, real players) | Popup, counters change | Counter does not change, or "−" enabled on 0 strikes |
| Ask panel (Remove them / Put back in queue / Leave as is / ✕) | CAUTION | Appears when a size/mode change would disturb players; ✕ changes nothing | Appears but a choice does nothing |
| Wheel: Spin | **DO NOT CLICK on a live stream** (public spin, posts the winner) | Spin starts, winner shown | — |
| Wheel: New round, Reset | **DO NOT CLICK on a live stream** (Reset: two clicks) | Entrants cleared | — |
| Wheel: Queue / Undo | CAUTION | Queue copies waiting players onto the wheel, button becomes Undo; Undo removes exactly those | Duplicates on the wheel |
| Wheel: Tourney | CAUTION (opens tournament sign-ups in chat) | Wheel status becomes open | — |

### 1.4 Feed tab
| Control | Safe? | Expected | Failure |
|---|---|---|---|
| Chips All / Chat / Players / Backend / Events | SAFE | Filters the log; scroll sticks to the bottom only if you were at the bottom | Filter hides everything, or scroll jumps while reading |
| Clear / any send box | SAFE (if present: it only clears the local list). Any "say" box = **DO NOT CLICK on a live stream** | — | — |

### 1.5 Commands tab
| Control | Safe? | Expected | Failure |
|---|---|---|---|
| List | SAFE | Every chat command with a switch | Empty list while the Host is up |
| Switch / name click | CAUTION (turns a chat command on or off for everyone) | Switch flips; the chat command answers or stops answering | Switch flips back (Host refused) |
| Search box (bottom) | SAFE | Filters the list | — |

### 1.6 Overlays tab
| Control | Safe? | Expected | Failure |
|---|---|---|---|
| Files list | SAFE | The overlay files the Host serves | "not connected yet" while Host is up |
| Open (opens its own window) | SAFE (browser view only, does not touch OBS) | Preview window with the overlay | Blank window, or a 404 |
| Copy URL | SAFE | URL on the clipboard | — |

### 1.7 Stream tab (text only; never starts a stream)
| Control | Safe? | Expected | Failure |
|---|---|---|---|
| Load current | SAFE (reads from the platforms) | Fields fill from Twitch/YouTube/Kick; YouTube without a token says so in the note | Fields blank without an error note |
| Title / Game / Description / Tags edits | SAFE until pushed | Tag counter updates | — |
| Push to selected | CAUTION (changes the public title/category/tags of the ticked platforms) | Per-platform result in the note; Twitch category changes drive the overlay game | A platform ticked but not updated and no error shown |
| YouTube Schedule (time, privacy) | CAUTION, two clicks. Creates a scheduled broadcast; does not go live | Result with link, or a warning text | The broadcast starts (that would be a bug: stop and tell 20) |
| Preview recap | SAFE | Shows the recap text and clip | — |
| Post in chat (recap) | **DO NOT CLICK on a live stream** (real Twitch chat; 30 s duplicate guard; two clicks) | Recap said once | Said twice within 30 s |

### 1.8 Player (bottom right, music)
| Control | Safe? | Expected | Failure |
|---|---|---|---|
| ▶ / ⏮ / ⏭ | CAUTION (changes what plays on stream) | State follows within about 2 s | Button state out of sync with Spotify |
| 👍 | SAFE-ish (adds to Spotify liked songs) | Toast | — |
| 🚫 Ban song / Ban artist | CAUTION, two clicks (permanent ban list) | Skips and bans | One click bans |
| 🔊 volume / Device | CAUTION | Pick device; list loads (may 429 once: wait) | List empty with Spotify connected |
| – (shrink) | SAFE | Collapses the player | — |

### 1.9 Test go-live (not in Master View; Suite simulator)
The "Test go-live" control of the core runs /api/simulate. It does NOT touch OBS or chat, but it starts the live-reactive modules and "End test" closes song requests. **DO NOT CLICK on a live stream.**

---------------------------------------------------------------------------
## 2. Suite pages (sidebar)

### Economy
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Open the page | SAFE | Points settings load with a preview calculation | "Host did not answer" with the Host up |
| Change a number, watch the preview | SAFE until saved | Preview updates without saving | Preview does not move |
| Save | CAUTION (real economy for everyone) | Toast saved; reload shows the same values | Values revert after reload |

### Timers
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Open | SAFE | List of timers with global gap | Empty with the Host up |
| Switch a timer on | **DO NOT CLICK on a live stream** (timers speak in real chat on a schedule) | Timer runs | Speaks closer than the global gap |
| Edit text / interval, Save | CAUTION | Saved | Reverts |
| Add timer | CAUTION | New row, off by default | Starts speaking immediately |

### Canned commands
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Open | SAFE | List | "older build" text with a new Host: restart the Host |
| Test button | **DO NOT CLICK on a live stream** (says it in real chat) | Posts once | Posts twice |
| Add / edit / cooldown / switch off | CAUTION | Saved; no delete (turn off instead) | Delete exists |

### Overlay fit
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Open | SAFE | Option groups from /api/overlay-options/schema | Blank page |
| Change an option, Save | CAUTION (visible on stream) | Overlay updates | Reverts, or the overlay ignores it |

### Problem reports
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Open | SAFE | Reports sent with "Report a problem", newest first; badge in the sidebar counts unhandled | Badge disagrees with the list (only the 30 newest are listed) |
| Mark handled / unhandled | SAFE (local file flag) | Row moves, badge drops | Does not persist after a reload |

### Report a problem (⚑ button, bottom of every page)
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Click ⚑, type a note, paste a screenshot (Ctrl+V), send | SAFE (saved on this PC only: Data\feedback) | Confirmation; a report appears in Problem reports with the page name and the screenshot | Send fails, or the report has no screenshot |
| Send with an empty note | SAFE | Refused politely | Saves an empty report |

### Personalize
| Step | Safe? | Expected | Failure |
|---|---|---|---|
| Menu order up/down, hide items | SAFE (per device, saved in the core) | Sidebar reorders; Dashboard/Settings/Personalize cannot be hidden | Hidden item cannot be brought back |
| Reset | SAFE | Default order | — |

---------------------------------------------------------------------------
## 3. Log what you find
Put results in Docs\qa\<date>-clickpaths.md: row, PASS / FAIL, what you saw, screenshot name. Report each FAIL to 20 with the page, the step and the toast text.
