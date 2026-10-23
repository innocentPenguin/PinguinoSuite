# PinguinoMulti docs

PinguinoMulti is the chat, alerts and overlay module of the Pinguino Suite (code in `Suite/modules/multi`, port 8766). Start here.

| File | What it is |
|---|---|
| [INDEX.md](INDEX.md) | Code map: which file does what, with the nightly change log. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the pieces fit together. |
| [API_ROUTES.md](API_ROUTES.md) | Every HTTP route, generated from `server.py` and `platform_api.py`. |
| [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) | Every environment variable and settings key. |
| [IVAN_SETUP.md](IVAN_SETUP.md) | The things only Ivan can do: sign-ins, developer apps, consent clicks. |
| [PLATFORMS.md](PLATFORMS.md) | Twitch, YouTube, Kick, TikTok and Discord: what each supports and how it connects. |
| [ALERTS.md](ALERTS.md) | The alert engine: types, queue, editor, Host bridge, media, goals. |
| [OBS_WIDGETS.md](OBS_WIDGETS.md) | The OBS browser sources (chat, activity, alerts, goal, hype bar) and their editors. |
| [STREAM_READY.md](STREAM_READY.md) | Checklist before going live. |
| [E2E_RESULTS.md](E2E_RESULTS.md) | Results of the end-to-end and rehearsal runs, with the bugs they found. |
| [SOAK_RESULTS.md](SOAK_RESULTS.md) | Long-run (soak) test results. |
| [../MULTISTREAM_PLAN.md](../MULTISTREAM_PLAN.md) | The plan for streaming to several platforms at once. |
| [CONTRACTS.md](CONTRACTS.md), [DECISIONS.md](DECISIONS.md), [PLAN.md](PLAN.md) | Interfaces with other modules, decisions taken, original plan. |
| [ASSISTED_CHAT.md](ASSISTED_CHAT.md), [LOOK_AND_SPLIT.md](LOOK_AND_SPLIT.md) | Assisted replies; chat look and split windows. |
| [SHELL_WINDOW_SPEC.md](SHELL_WINDOW_SPEC.md), [ROUTER_HOOK_PROPOSAL.md](ROUTER_HOOK_PROPOSAL.md), [SITE_SCOPE_PROPOSAL.md](SITE_SCOPE_PROPOSAL.md) | Proposals to the shell, router and website owners. |

Tests: `cd Suite/modules/multi` then `..\..\.venv\Scripts\python.exe -m pytest tests -q --deselect tests/test_cards_fuzz.py`.
Safe test server: set `MULTI_PORT`, `MULTI_DB` (temp file), `PINGUINO_DATA_DIR` (temp folder), `MULTI_NO_KEYRING=1` and `MULTI_NO_SEND=1` so it cannot touch the real vault or send chat.
