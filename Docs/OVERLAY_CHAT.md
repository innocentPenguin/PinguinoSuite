# Overlay chat + overlay folder + live OBS tree (Plan 6) - Host side (02)

Everything below is served by PinguinoHost on 127.0.0.1:8770. State changes (POST) need same-origin or the module/API token like every Host write. The home PC is never exposed: the site talks to the Host only through the outbound-only poll described in "Site bridge".

## A. Live OBS tree (HostObs.cs)
- `GET /api/obs/tree[?scene=NAME]` -> `{connected, current, scene, scenes:[{name,folder,label,current}], folders:[...], items:[{id,name,kind,enabled,group,children?}]}`. `items` are the sources of `scene` (default: the live scene), top-first, real OBS Groups nested in `children`. OBS offline -> `{connected:false, scenes:[], folders:[], items:[]}`. Cached 2 s.
- Folders: scene names `A / B`, `[tag] x`, and `A - B` (only when 2+ scenes share the prefix); overrides in `Data\config\obs_folders.json` `{"scenes":{"Scene Name":"Folder"}}`. OBS scene folders are not visible to obs-websocket, so this convention is the folder source.
- `POST /api/obs/scene {scene}` and `POST /api/obs/item {scene, itemId, enabled|toggle}` -> `{ok, enabled?}` or `{ok:false, error}`. Only scene names and item ids OBS really reports are accepted (group members are toggled through their group). Every call is audit-logged in `Data\runtime\mod_audit.log`.
- The Host rewrites `Data\runtime\obs_tree.json` every 5 s while OBS is connected; the bot's published state (`obs.tree`, same shape without `scene`) carries it when the copy is under 30 s old, otherwise `tree` is null and the old `scenes`/`sources` lists still apply.

## C. Overlay folder (HostOverlays.cs)
Root = `settings.json` OverlayDir, else `PinguinoB0t\overlays`. Paths are relative with `/`, no `..`, no drive letters, allowed types html css js json svg txt (text) and png jpg jpeg webp gif mp3 wav ogg webm mp4 woff woff2 ttf (base64), text up to 2 MB, binary up to 12 MB, no `settings.json`, no names containing `secret`, trash folder hidden.
- `GET /api/overlays` -> `{ok, files:[{path,size,mtime,ext,text,url}]}`; `GET /api/overlays/file?path=` -> `{ok, text}` (binary: `{binary:true,size}`).
- `POST /api/overlays/write {path, text | base64}` (new file or replace, valid JSON enforced for .json), `POST /api/overlays/rename {from,to}` (never overwrites, same type), `POST /api/overlays/delete {path}` (moves to `Data\runtime\overlay_trash\<time>-<why>\`). Replacing and deleting keep a backup there.

## D. Overlay assistant (HostOverlayChat.cs)
- Off until `Data\config\overlaychat.json` has `"enabled": true` (file is created with `enabled:false`, `model`, `dailyCalls` 40, `maxTokens`). Claude key: vault name `ANTHROPIC_API_KEY` (01 must add it to the module manifest), else env, else host_secrets.json `AnthropicKey`. Never logged.
- Four tools only, all confined to the overlay folder: list_files, read_file, write_file, undo_file. A new file is written at once; replacing an existing file creates a **proposal** `{id, path, diff}` that must be applied: `POST /api/overlaychat/apply {id,user}`. Proposals live in memory (last 20).
- `POST /api/overlaychat/ask {user,text}` -> `{ok, text, proposals:[{id,path,diff}], files:[{path,created|restored}]}`; `GET /api/overlaychat/status`. Log: `Data\runtime\overlaychat.jsonl`; usage: `overlaychat_usage.json`.

### Site bridge (for 05)
The Host polls (every min(PINGUINO_SITE_POLL_SEC,10) s, bearer = the bot key, like teach/shop):
- `GET /api/bot/overlaychat?status=pending` -> `{"items":[{"id":"m1","user":"ivan","text":"make a goal bar"}, {"id":"m2","user":"ivan","apply":"p1a2b3c4"}]}` (`apply` = proposal id to apply instead of asking). Staff-only filtering is the site's job; the Host trusts what the authenticated site lists.
- The Host answers `POST /api/bot/overlaychat/reply {"id":"m1","reply":{"text":"...","proposals":[{id,path,diff}],"files":[{path,created}],"error":null}}`. The Host remembers answered ids (`overlaychat_done.json`) and re-posts the same reply if the site still lists the message, so the site should drop it from `pending` once the reply arrives.
