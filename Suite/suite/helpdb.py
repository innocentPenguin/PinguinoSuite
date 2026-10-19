"""Help framework: every status the Suite shows (Integrations rows, pre-stream items, Console errors, module health chips, key fields)
can be clicked to open a help panel: what it means, exact steps, a link, and a button that takes you to the place to fix it.

A help entry is a dict:  {title, summary?, steps: [str], link?: {label, url}, fix?: {label, route?, focus?, url?, module_action?}, example?, scopes?: [str]}
Modules supply their own (manifest "help": {"<item id>": {...}, "_module": {...}}, or inline "help" on an integrations / prestream item);
the core supplies the generic ones below. Nothing here ever contains a secret value: examples show the FORMAT only.
Resolution order: item-inline help (done by the caller) -> module manifest help -> core catalog -> Console matcher -> None (the caller shows
"no help written yet" and logs a Console warning once).
"""
import re

MAX_STEPS, MAX_STR = 14, 400


def _s(v, n=MAX_STR):
    return str(v)[:n] if isinstance(v, (str, int, float)) else ""


def _url(u):
    u = _s(u, 300)
    return u if u.startswith(("https://", "http://127.0.0.1", "http://localhost")) else ""


def clean_help(h):
    """Sanitise a help dict coming from a module (plain text only, https/loopback links, bounded size). None if unusable."""
    if not isinstance(h, dict):
        return None
    steps = [_s(x) for x in (h.get("steps") or [])[:MAX_STEPS] if _s(x)]
    out = {"title": _s(h.get("title"), 100), "summary": _s(h.get("summary"), 600), "steps": steps}
    if not (out["title"] or steps or out["summary"]):
        return None
    for k in ("example",):
        if h.get(k):
            out[k] = _s(h[k], 200)
    if isinstance(h.get("scopes"), list):
        out["scopes"] = [_s(x, 80) for x in h["scopes"][:30]]
    link = h.get("link")
    if isinstance(link, dict) and _url(link.get("url")):
        out["link"] = {"label": _s(link.get("label") or "Open", 40), "url": _url(link["url"])}
    fix = h.get("fix")
    if isinstance(fix, dict):
        f = {"label": _s(fix.get("label") or "Fix it", 40)}
        if fix.get("route"):
            f["route"] = _s(fix["route"], 60)
        if fix.get("focus"):
            f["focus"] = _s(fix["focus"], 80)
        if _url(fix.get("url")):
            f["url"] = _url(fix["url"])
        ma = fix.get("module_action")
        if isinstance(ma, dict) and ma.get("action") in ("start", "restart") and re.fullmatch(r"[\w-]{1,30}", str(ma.get("module", ""))):
            f["module_action"] = {"module": ma["module"], "action": ma["action"]}
        if len(f) > 1:
            out["fix"] = f
    return out


def H(title, summary, steps, link=None, fix=None, example=None, scopes=None):
    d = {"title": title, "summary": summary, "steps": steps}
    if link:
        d["link"] = {"label": link[0], "url": link[1]}
    if fix:
        d["fix"] = fix
    if example:
        d["example"] = example
    if scopes:
        d["scopes"] = scopes
    return d


CATALOG = {
    "obs": H("OBS WebSocket", "PinguinoSuite (Link macros, Host scene control) talks to OBS through OBS's built-in WebSocket server. Red/yellow here means OBS is closed or its WebSocket server is off or the password is not in the vault.",
             ["Open OBS Studio on the PC that streams.", "Menu: Tools > WebSocket Server Settings.", "Tick \"Enable WebSocket server\". Leave the port at 4455 (this PC uses 4455).",
              "Tick \"Enable Authentication\", press \"Generate Password\" (or type your own), then press Show Connect Info to read it. Click Apply, then OK.",
              "In PinguinoSuite open Integrations > Key vault, find \"OBS WebSocket password\" (OBS_WS_PASSWORD) and press Set. Paste the password. It is stored encrypted and never shown again.",
              "Press Test next to it. If OBS runs on another PC, use that PC's LAN address in Link's OBS setting instead of 127.0.0.1 (this PC's LAN address is 192.168.0.70)."],
             example="a 16-30 character password, for example from Generate Password",
             fix={"label": "Enter the OBS password", "route": "integrations", "focus": "OBS_WS_PASSWORD"}),
    "streamerbot": H("Streamer.bot connection", "Streamer.bot is the old bot engine. It is optional: PinguinoHost replaces it. Yellow means its WebSocket server is not running; that is fine once Host does the work.",
                     ["If you still use Streamer.bot: open it, go to Servers/Clients > WebSocket Server, tick Auto Start and press Start Server (default 127.0.0.1:8080).",
                      "If you are not using Streamer.bot any more you can ignore this item.", "Do not expose port 8080 beyond this PC; enable authentication in the same screen if you can."]),
    "site": H("innocentpenguin.com", "The website is checked from this PC. Red means this PC cannot reach it or the server answers with an error.",
              ["Open https://innocentpenguin.com in a browser. If it loads, press Refresh here.", "If it does not load, check this PC's internet connection, then the Railway project's Deployments tab for a failed deploy.",
               "Things that need the site (Spotify requests, WebSync) pause and retry on their own once it is back."],
              link=("Open the site", "https://innocentpenguin.com")),
    "disk": H("Disk space", "Free space on the drive that holds the Suite. Yellow under 5 GB, red under 1 GB.",
              ["Open File Explorer > this drive > properties to see what is using space.", "Safe to delete: old folders in Data\\backups and Data\\exports, and Suite\\logs\\*.log.N rotated logs.",
               "Chat logs (Data\\chat_logs) and the Listen audio (Suite\\modules\\listen\\data\\audio) are the big ones; move them to another drive and keep a copy before deleting."]),
    "errors": H("Errors in the last 30 minutes", "Some module logged an error recently. The pre-stream check warns so you look before going live.",
                ["Open the Console page and tick \"Errors only\".", "Click an error line: the help panel explains it and links to the fix.", "Once nothing new appears for 30 minutes this item turns green by itself."],
                fix={"label": "Open the Console", "route": "console"}),
    "keys": H("Missing API keys", "A module needs a key or token that is not in the key vault yet.",
              ["Open Integrations > Key vault. Rows marked Missing need a value.", "Press Set on a row, follow the instructions shown under it, paste the key, Save.", "Press Test if the row has a Test button."],
              fix={"label": "Open the key vault", "route": "integrations"}),
    "vault_key": H("Key vault entry", "One API key or token, stored encrypted on this PC. Values are never shown again after saving.",
                   ["Press Set (or Rotate) on the row and follow the numbered instructions shown under the field.", "Paste only the key itself, with no quotes or spaces.", "Press Save, then Test if available.",
                    "To replace a leaked or expired key: create a new one at the provider, Rotate here, then delete the old one at the provider."],
                   fix={"label": "Open the key vault", "route": "integrations"}),
    "vault_plaintext": H("Keys still in plain files", "Some old config files still contain keys in plain text. The vault can import them, then the plain copies should be removed.",
                         ["Integrations > Key vault > \"Import into vault\" copies them (the files are not changed).", "Restart or Update the module that uses them and check it works (its status is green).",
                          "Only then press \"Remove plaintext from <file>\". It blanks only values the vault holds identically."],
                         fix={"label": "Open the key vault", "route": "integrations"}),
    "module_down": H("A module is not running", "Modules are separate programs the Suite starts. Off/stopped means this one is not running right now.",
                     ["Press Start on its dashboard row (or Restart).", "If it stops again, open the Console and look for lines from that module; click an error for its fix.",
                      "After changing a module's code, run App\\Update-Module.bat <module id> instead of restarting the whole app.", "Modules marked \"always start\" are restarted automatically after a crash (up to 5 times in 5 minutes)."],
                     fix={"label": "Open the dashboard", "route": "dashboard"}),
    "module_failed": H("A module keeps crashing", "The core restarted it automatically and gave up after 5 crashes in 5 minutes.",
                       ["Open the Console, filter by that module and read the last error lines (click them for a fix).", "Fix the cause (a missing key, a port already in use, a bad setting).",
                        "Then press Restart on its dashboard row, or run App\\Update-Module.bat <module id>."], fix={"label": "Open the Console", "route": "console"}),
    "module_starting": H("A module is starting", "It was launched but its health URL is not answering yet. Heavy modules (Listen loads the speech model) can take a minute.",
                         ["Wait a minute and watch the dashboard.", "If it stays on \"starting\", open the Console and look for errors from it."], fix={"label": "Open the Console", "route": "console"}),
    "tailscale": H("Tailscale and device linking", "Tailscale is the private network that lets your PCs (streaming PC, gaming PC, Mac) reach each other. Link uses it to pair devices.",
                   ["Install Tailscale on every device (tailscale.com/download) and sign in with the SAME account on all of them.", "Make sure the Tailscale icon says Connected.",
                    "Open the Link page > Devices, press \"Pair\" on the master, enter the 6-digit code on the other device within 5 minutes.", "Paired devices appear in the dashboard device strip."],
                   link=("Get Tailscale", "https://tailscale.com/download"), fix={"label": "Open Link", "route": "m:link"}),
    "tailscale_peer": H("A paired device is offline", "That device has not answered recently (turned off, asleep, or Tailscale not running).",
                        ["Wake the device and make sure Tailscale is Connected there.", "If it stays offline, unpair and pair again from the Link page."], fix={"label": "Open Link", "route": "m:link"}),
    "device": H("Master and auxiliary devices", "Exactly one online device is the master and runs the bots, Spotify and the pre-stream checks. Others are auxiliary helpers.",
                ["The streaming PC is master by default (priority 100), then the gaming PC (70), then the Mac (50). A device that is streaming wins.", "To move control now, press \"Take control here\" on the device strip of the device you want.",
                 "Change a device's name or priority in Settings > This device."], fix={"label": "Open Settings", "route": "settings"}),
    "listen_model": H("Speech model", "Listen needs its speech-to-text model loaded before it can hear you. It loads when Listen starts and can take a minute.",
                      ["Wait for \"ready\" in Listen. If it says error, open the Console and read the Listen line.", "Common cause: no GPU libraries. Listen then falls back to the CPU automatically (slower).", "Restart Listen from the dashboard after fixing."],
                      fix={"label": "Open Listen", "route": "m:listen"}),
    "listen_mic": H("Microphone", "Listen needs an input device. Red means none was found or the selected one is unplugged.",
                    ["Plug the microphone in and check Windows Sound settings > Input shows it.", "Open Listen and choose the device in its device picker, or clear the choice to use the default.", "Restart Listen if Windows only just detected the device."],
                    fix={"label": "Open Listen", "route": "m:listen"}),
    "listen_listening": H("Listening state", "Listen starts the microphone automatically when you go live. \"Idle\" before the stream is normal.",
                          ["Nothing to do. To test before going live press \"Start listening\" on the dashboard.", "Stop it again afterwards if you do not want to record."], fix={"label": "Open the dashboard", "route": "dashboard"}),
    "voice_commands": H("How voice commands work", "Say a phrase on stream and Listen recognises it. Commands are silent: they never write in chat.",
                        ["Open Voice Studio > Voice commands. Turn \"Commands on\" ON (it is off by default) and switch on the commands you want.", "Each command has phrases (write alternatives with |). The built-in one skips the Spotify song: \"skip the song\", \"skip this song\", \"I want this song skipped\".",
                         "Optional: set a wake word (for example \"pinguino\") so only \"pinguino skip the song\" counts.", "Use Test to try a sentence without speaking; \"Run for real\" actually fires it.",
                         "Every heard command and its result (matched command, score, fired / ignored / failed) is listed in Voice Studio and in the Console under source \"voice\" so you can review accuracy."],
                        fix={"label": "Open Voice Studio", "route": "voice"}),
    "console": H("How the Console works", "One live log for the Suite and every module. Click any warning or error line for what it means and how to fix it.",
                 ["Filter by module, level, or search text; Pause and Clear only affect your view.", "Modules write to Data\\runtime\\console\\<module>.jsonl; the core also adds its own events and captured error output.", "Secrets are hidden as •••• automatically."]),
    "prestream": H("How the pre-stream check works", "At 4:30 pm and 4:45 pm Central (stream at 5:00) the Suite checks everything and posts pass / warn / fail per item. You can also press Run now.",
                   ["Red (fail) = fix before going live. Yellow (warn) = degraded or optional.", "Click any row for what it means and the fix.", "If another device is green for an item this device has as warn/fail, the merged view shows green and says which device."],
                   fix={"label": "Open the Console", "route": "console"}),
    "integrations": H("How Integrations works", "One list of every outside connection: chat platforms, Spotify, Tailscale devices, OBS, Streamer.bot, the site, and the key vault.",
                      ["Green = connected. Yellow = needs sign-in or a key. Red = a problem. Grey = off.", "Press ⓘ on any row, even a green one, for how it works and how to set it up again.", "Keys live in the Key vault card: press Set, follow the steps under the field, paste, Save."]),
    "dashboard": H("How the dashboard works", "A summary of the stream, devices, modules, pre-stream check and recent errors.",
                   ["Tiles are clickable: Pre-stream and Errors open the Console.", "The device strip shows which device is master; press \"Take control here\" to move control.", "Press Start / Restart on a module row; click its state for help."]),
    "vault": H("How the key vault works", "Every API key and token is stored in one encrypted file on this PC (Windows DPAPI, tied to your Windows user). Modules ask the core for a key by name; values are never shown or logged.",
               ["Modules list the keys they need; missing ones show as Missing.", "Set / Rotate stores a new value (encrypted). Delete removes it.", "Backup: export an encrypted file with a passphrase to move the vault to another PC.",
                "Only the master device holds the vault."], fix={"label": "Open the key vault", "route": "integrations"}),
}

ALIASES = {
    "core:obs": "obs", "core:streamer.bot": "streamerbot", "core:streamerbot": "streamerbot", "site:web": "site", "core:site": "site", "core:disk": "disk",
    "core:errors": "errors", "vault:plaintext": "vault_plaintext", "link:tailscale": "tailscale", "listen:model": "listen_model", "listen:mic": "listen_mic", "listen:listening": "listen_listening",
}
CATALOG["settings"] = H("How Settings works", "This device, backup and move, start-with-Windows, and per-module options.",
                        ["This device: its name, priority and whether it may become the master.", "Backup & move: export your config as a zip (secrets only if you tick it and set a passphrase) and import it on another PC.",
                         "Modules: choose which start with the Suite and which are always on."])
CATALOG["module_switch"] = H("Module on/off switch and lock", "Each module has an on/off switch. On = it starts with the Suite and runs now; off = it stops now and stays off after restarts. The choice is saved.",
                             ["The padlock next to the switch protects it from accidental clicks. Click the padlock to unlock; it locks again after one change or 30 seconds.",
                              "Modules the Suite needs (Host, Multi) can be switched off too, but only after unlocking. Turning one off stops the bots / chat until you switch it back on.",
                              "To restart a module without changing the switch, use Restart on the dashboard."],
                             fix={"label": "Open Settings", "route": "settings"})
CATALOG["activity"] = H("How the Activity feed works", "Every event on your channel in one live list: follows, subs, resubs, gifts, cheers, raids, redeems, bans, clips and more. It is served by PinguinoHost.",
                        ["Click the type chips to filter (Raid, Sub...); search by name or message. Pause freezes the view while you read.", "If it says the Host is not serving the feed: make sure PinguinoHost is on (Settings > Modules) and updated, and that Twitch is connected (Integrations).",
                         "Big raids, gifts and cheers are highlighted."], fix={"label": "Open Integrations", "route": "integrations"})
CATALOG["popout"] = H("Pop-out windows", "Send any page (Chat, Console, Activity, a module) to its own window, on any monitor, or on half of one: for example the top half of the chat on the monitor above and the bottom half on the monitor below.",
                      ["Settings > Pop-out windows: pick the page, the monitor and how much of it to fill (whole monitor, top / bottom / left / right half), then Open window.", "The \"Pop out\" button in the top bar opens the page you are on in its own window.",
                       "Windows remember their position, size, monitor and always-on-top, and reopen where you left them next launch (close one with its X to stop that).", "Always on top keeps a window above the game; Pin / Unpin it in the list.", "Only available in the PinguinoSuite app, not in a plain browser."],
                      fix={"label": "Open Settings", "route": "settings"})
CATALOG["personalize"] = H("Personalize", "Make the Suite yours: theme and accent colour, sidebar, menu order, dashboard cards, sounds, notifications and saved looks. Saved on this device only.",
                           ["Theme: pick a look, then optionally a custom accent colour. Module pages follow it.", "Menu order / Dashboard: use the arrows to reorder and Hide to remove things you do not use.", "Sounds are off by default; turn them on, pick a tone, and press Test next to each event.",
                            "Saved looks: save the current setup under a name; Apply it later, or choose looks that switch automatically when you go live / offline.", "Export to file moves your look to another PC; Reset everything goes back to the defaults; Undo reverts the last change."],
                           fix={"label": "Open Personalize", "route": "personalize"})
CATALOG["comm"] = H("PenguinComm", "One place for talking with your bots: Listen (the microphone: you speaking to the bots) and Speak (PinguinoVoice: the bots speaking out loud). Two sections, one page.",
                    ["Choose Both, Listen or Speak at the top. Each section has its own on/off switch (unlock the padlock first), Restart and help.", "Listen hears you, turns it into text and runs voice commands (Voice Studio button). It is always on, live or not.",
                     "Speak is the bot voice: what the bots say, which voice, volume and when. Its own settings are in the Speak section.", "A yellow or red item at the top is a pre-stream problem for Listen or Speak: click it for the fix."],
                    fix={"label": "Open PenguinComm", "route": "comm"})
CATALOG["help"] = H("How Help works", "Every ? button and every red / yellow row opens the same kind of panel: what it means, the steps to fix or set it up, and a button to the place to do it.",
                    ["Click any pre-stream row, Integrations row, Console warning / error, module name or key row.", "Green items have instructions too, for setting them up again.", "This page lists all topics."])
ALIASES["voice"] = "voice_commands"

# Console lines: first matching rule wins. Pattern is searched in "module source message".
MATCHERS = [
    (r"(401|unauthori[sz]ed|bad token|forbidden)", "vault_key"),
    (r"key (not declared|not set)|undeclared key|api key.*(missing|invalid)|invalid.*api key", "vault_key"),
    (r"vault.*unavailable|dpapi", "vault"),
    (r"crashed \d+ times|state=failed|keeps? crash", "module_failed"),
    (r"not answering|connection refused|max retries|never answered|not running", "module_down"),
    (r"obs", "obs"),
    (r"tailscale|peer|pair", "tailscale"),
    (r"speech model|asr|whisper", "listen_model"),
    (r"microphone|input device|portaudio|sounddevice", "listen_mic"),
    (r"voice command|voice ", "voice_commands"),
    (r"disk|no space", "disk"),
]


def canonical(key):
    k = (key or "").strip().lower()
    if k in ALIASES:
        return ALIASES[k]
    if k.endswith((":module", ":up")):
        return "module_down"
    if k.endswith(":keys"):
        return "keys"
    if k.startswith("key:"):
        return "vault_key"
    if k.startswith("link:peer"):
        return "tailscale_peer"
    if re.match(r"^module:[\w-]+:(failed|crashed)$", k):
        return "module_failed"
    if re.match(r"^module:[\w-]+:starting$", k):
        return "module_starting"
    if re.match(r"^module:[\w-]+:(stopped|off|unknown)$", k):
        return "module_down"
    return k if k in CATALOG else None


def module_generic(spec):
    name = spec.get("name", spec.get("id", "module"))
    return H(name, spec.get("desc", ""), ["Open it from the sidebar (Modules).", "Start or Restart it from the dashboard row; click its state for help.",
                                          "Its log lines are in the Console (filter by module).", f"After changing its code: App\\Update-Module.bat {spec.get('id', '<id>')} (no app restart)."],
             fix={"label": "Open the dashboard", "route": "dashboard"})


def resolve(key="", module="", item="", source="", msg="", specs=None):
    """Returns (help dict, key used) or (None, key). specs = {module id: manifest} for module-supplied help."""
    specs = specs or {}
    key = key or ""
    # 1. the module's own manifest help: by full key, by item id, or "_module"
    for mid in ([module] if module in specs else []) + [m for m in specs if key.startswith(m + ":")]:
        mh = (specs[mid].get("help") or {})
        for k in (key, item, key.split(":", 1)[-1], key.split(":", 1)[-1].lower()):
            if k and clean_help(mh.get(k)):
                return clean_help(mh[k]), key
    # 2. a module overview ("module:<id>" or "module:<id>:running"): its own _module text, else a generic one
    m = re.match(r"^module:([\w-]+)(?::running)?$", key)
    if m and m.group(1) in specs:
        c = clean_help((specs[m.group(1)].get("help") or {}).get("_module"))
        return (c or module_generic(specs[m.group(1)])), key
    # 3. core catalog
    c = canonical(key)
    if c:
        return CATALOG[c], key
    # 4. console line
    if msg or source:
        hay = f"{module} {source} {msg}".lower()
        for rx, cid in MATCHERS:
            if re.search(rx, hay):
                return CATALOG[cid], key or f"console:{cid}"
    return None, key


def topics(specs):
    """Everything that has help, for the Help index page: [{key, title, group}]."""
    out = [{"key": k, "title": v["title"], "group": "Suite"} for k, v in CATALOG.items() if k not in ("vault_key",)]
    for mid, sp in sorted(specs.items()):
        out.append({"key": f"module:{mid}", "title": sp.get("name", mid), "group": "Modules"})
        for k, v in (sp.get("help") or {}).items():
            c = clean_help(v)
            if c and k != "_module":
                out.append({"key": f"{mid}:{k}" if ":" not in k else k, "title": c["title"] or k, "group": sp.get("name", mid), "module": mid})
    return out
