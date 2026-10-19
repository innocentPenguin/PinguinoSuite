"""Single source of truth for every setting: defaults, labels, one-line help, presets, chat message templates.
The Settings tab is generated from SCHEMA, rules.DEFAULTS is derived from it."""

# placeholders usable in message templates, with a sample for the live preview
VARS = {"user": "Ann", "song": "Song 1 - Artist", "title": "Song 1", "artist": "Artist", "pos": 3, "eta": ", plays in ~8 min", "by": " (requested by Ann)", "limit": 2,
        "max_min": 10, "min_s": 30, "votes": 1, "need": 3, "link": "https://open.spotify.com/track/abc", "requester": "Ann",
        "count": 5, "next": "1. Song 2 - Artist | 2. Song 3 - Artist", "cooldown": 60, "cmds": "!sr !song !queue !skip !oops",
        "last": "Song 0 - Artist", "vol": 40, "volmax": 80, "mine": "Song 4 - Artist, Song 7 - Artist", "wait": 120}

MSGS = {
    "added": ("Song added", "@{user} added '{song}' (#{pos} in queue{eta}).", "Viewer request accepted."),
    "pending": ("Waiting for approval", "@{user} '{song}' is waiting for approval.", "Request held in the inbox."),
    "closed": ("Requests closed", "Song requests are closed right now.", "Requests are off."),
    "mod_only": ("Mods only", "Only mods can request songs right now.", "Mods-only mode."),
    "sub_only": ("Subs only", "Song requests are for subscribers right now.", "Subs-only mode."),
    "blocked": ("Blocked song", "@{user} that song/artist isn't allowed on stream.", "On the blocklist."),
    "explicit": ("Explicit", "@{user} explicit songs aren't allowed right now.", "Explicit songs refused."),
    "too_long": ("Too long", "@{user} that song is too long (max {max_min} min).", "Over the length limit."),
    "too_short": ("Too short", "@{user} that song is too short (min {min_s} s).", "Under the minimum length."),
    "full": ("Queue full", "The queue is full.", "Queue at its maximum."),
    "dup_queue": ("Already queued", "@{user} that song is already queued or playing.", "Duplicate protection."),
    "dup_recent": ("Played recently", "@{user} that song was played recently.", "Replay cooldown."),
    "limit": ("Viewer limit", "@{user} you already have {limit} request(s) in the queue.", "Per-viewer limit reached."),
    "cooldown": ("Request cooldown", "@{user} wait {wait}s before requesting again.", "Per-viewer cooldown."),
    "artist_cap": ("Artist cap", "@{user} there are already enough songs by {artist} in the queue.", "Too many songs from one artist."),
    "user_blocked": ("Viewer blocked", "@{user} you can't request songs.", "Blocked viewer."),
    "no_links": ("Links off", "@{user} Spotify links aren't accepted, just type the song name.", "Links disabled."),
    "no_search": ("Search off", "@{user} please paste a Spotify link instead of a name.", "Name search disabled."),
    "none": ("No result", "@{user} no song found for that.", "Search found nothing."),
    "usage": ("Usage hint", "@{user} usage: !sr <song name or Spotify link>", "Empty !sr."),
    "offline": ("Spotify offline", "Song requests aren't available right now.", "Not connected to Spotify."),
    "lookup": ("Lookup failed", "@{user} couldn't reach Spotify, try again.", "Spotify error during search."),
    "song": ("!song", "Now playing: {song}{by} {link}", "Current song ({by} is ' (requested by X)' or empty)."),
    "song_idle": ("!song idle", "Nothing is playing right now.", "Nothing playing."),
    "last": ("!last", "Previous song: {last}", "Previous song."),
    "last_none": ("!last empty", "No previous song yet.", "No history yet."),
    "queue": ("!queue", "{count} in queue. Next: {next}", "Queue summary."),
    "queue_empty": ("!queue empty", "The queue is empty. Request a song with !sr <song or link>.", "Empty queue."),
    "mine": ("!mysongs", "@{user} your requests: {mine}", "A viewer's pending requests."),
    "mine_none": ("!mysongs none", "@{user} you have no requests in the queue.", "None pending."),
    "vote": ("Skip vote", "Skip vote {votes}/{need}.", "Skip vote counted."),
    "skipped": ("Skipped", "Skipped.", "Mod/broadcaster skip."),
    "vote_skipped": ("Skip passed", "Skip vote passed ({votes}/{need}). Skipping.", "Vote reached the threshold."),
    "skip_none": ("Skip nothing", "Nothing is playing.", "Nothing to skip."),
    "removed": ("!oops", "@{user} removed '{title}'.", "Viewer removed their request."),
    "oops_none": ("!oops none", "@{user} you have nothing to remove.", "Nothing to remove."),
    "toggle_open": ("Opened", "Song requests are now open! Use !sr <song or link>.", "A mod opened requests."),
    "toggle_closed": ("Closed", "Song requests are now closed.", "A mod closed requests."),
    "cleared": ("Cleared", "Viewer requests cleared.", "A mod cleared the queue."),
    "blocked_song": ("Blocked + skipped", "Blocked '{title}' and skipped it.", "!blocksong."),
    "session_limit": ("Session limit", "@{user} you've used all {limit} requests for this stream.", "Per-stream request cap reached."),
    "volume": ("!volume", "Volume is {vol}%.", "Mods: current volume."),
    "volume_set": ("!volume set", "Volume set to {vol}%.", "Mods: volume changed."),
    "playnext": ("!playnext", "Playing '{title}' next.", "A mod put a song first in line."),
    "help": ("!songhelp", "Song commands: {cmds}", "List of commands."),
}

COMMANDS = {"sr": ["sr", "request", "songrequest"], "skip": ["skip", "voteskip"], "queue": ["queue", "q", "songqueue", "srqueue"],
            "song": ["song", "currentsong", "nowplaying", "np"], "oops": ["oops", "wrongsong"], "blocksong": ["blocksong"],
            "clear": ["srclear"], "last": ["lastsong", "previoussong"], "mine": ["mysongs", "myrequests"], "help": ["songhelp"],
            "volume": ["volume", "vol"], "playnext": ["playnext"]}
COMMAND_HELP = {"sr": "request a song (and mods: open/close/clear)", "skip": "vote to skip (mods: instant)", "queue": "show the next songs",
                "song": "what is playing", "oops": "remove your last request", "blocksong": "mods: block + skip the current song",
                "clear": "mods: clear viewer requests", "volume": "mods: show or set the volume", "playnext": "mods: put a song first in line", "last": "the previous song", "mine": "your pending requests", "help": "list commands"}

# kinds: bool int str list choice color msgs cmds
SCHEMA = [
    {"id": "requests", "title": "Who can request", "items": [
        ("requests_open", "bool", False, "Requests open", "Master switch; ships closed. Mods can flip it with !sr open / !sr close."),
        ("mod_only", "bool", False, "Mods only", "Only mods and the broadcaster may request."),
        ("sub_only", "bool", False, "Subs / VIPs only", "Only subs, VIPs and mods may request."),
        ("stream_safe", "bool", False, "Stream-safe mode", "Blocks explicit songs and sends every request (even mods') to the approval inbox."),
        ("require_approval", "bool", False, "Approve requests first", "Requests wait in the Requests tab until you approve them."),
        ("approval_for", "choice:everyone|non_subs|non_staff", "non_staff", "Who needs approval", "With approval on: everyone, everyone except subs/VIPs, or everyone except mods."),
        ("queue_max", "int", 50, "Max queue length", "No more requests when this many songs are queued (mods can still add)."),
        ("allow_links", "bool", True, "Accept Spotify links", "Off = viewers must type a song name."),
        ("allow_search", "bool", True, "Accept song names", "Off = viewers must paste a Spotify link."),
        ("session_limit", "int", 0, "Requests per viewer per stream", "Total accepted requests per viewer since requests were opened (0 = no cap; mods exempt)."),
        ("queue_max_minutes", "int", 0, "Max queue length (minutes)", "Stop taking requests when the queue holds this many minutes of music (0 = off)."),
        ("priority_users", "list", [], "Priority viewers", "One name per line: their requests rank like subs (eg. friends, regulars)."),
        ("trusted_users", "list", [], "Trusted viewers", "One name per line: never held for approval."),
        ("autoskip_blocked", "bool", False, "Auto-skip blocked songs", "If a blocklisted song (or an explicit one in stream-safe mode) starts playing from ANY source, skip it."),
    ]},
    {"id": "limits", "title": "Limits per role", "items": [
        ("per_user_limit", "int", 2, "Pending per viewer", "How many songs a normal viewer may have waiting at once (0 = unlimited)."),
        ("sub_extra", "int", 2, "Extra for subs / VIPs", "Added to the viewer limit for subs and VIPs."),
        ("limit_vip", "int", -1, "VIP limit override", "Exact limit for VIPs; -1 = viewer limit + extra."),
        ("limit_sub", "int", -1, "Sub limit override", "Exact limit for subs; -1 = viewer limit + extra."),
        ("mods_bypass_limits", "bool", True, "Mods skip the limits", "Mods ignore the per-viewer limit and cooldown."),
        ("cooldown_s", "int", 0, "Cooldown between requests (s)", "Seconds a viewer must wait after a request (0 = none)."),
        ("cooldown_sub_s", "int", -1, "Sub cooldown (s)", "Cooldown for subs/VIPs; -1 = same as viewers."),
        ("max_per_artist", "int", 0, "Max songs per artist in queue", "Keeps variety: 0 = no cap."),
    ]},
    {"id": "songs", "title": "Which songs", "items": [
        ("min_length_s", "int", 0, "Minimum length (s)", "Refuse tracks shorter than this (0 = none)."),
        ("max_length_s", "int", 600, "Maximum length (s)", "Refuse longer tracks (0 = none)."),
        ("max_length_sub_s", "int", 0, "Sub max length (s)", "Longer limit for subs/VIPs; 0 = same as viewers."),
        ("block_explicit", "bool", False, "Block explicit songs", "Refuse tracks Spotify marks explicit."),
        ("dup_cooldown_min", "int", 60, "Replay cooldown (min)", "A song can't be requested again within this many minutes of playing (0 = off)."),
        ("blocklist", "list", [], "Blocklist", "One per line: a word in the title/artist, or a Spotify track link/URI."),
        ("blocked_users", "list", [], "Blocked viewers", "One name per line; these viewers can't request."),
    ]},
    {"id": "fair", "title": "Order & priority", "items": [
        ("fair_queue", "bool", True, "Fair queue", "Round-robin: everyone's first request before anyone's second. Off = plain first-come order."),
        ("sub_priority", "bool", True, "Subs / VIPs go first", "Within the same round subs and VIPs are ahead."),
        ("redeem_priority", "bool", True, "Channel-point requests go first", "Redeem requests jump to the front of their round."),
    ]},
    {"id": "skip", "title": "Skipping", "items": [
        ("skip_votes", "int", 3, "Votes to skip", "Different viewers needed for !skip to pass."),
        ("skip_mod_instant", "bool", True, "Mods skip instantly", "Mod/broadcaster !skip skips without a vote."),
    ]},
    {"id": "chat", "title": "Chat wording", "items": [
        ("chat_replies", "bool", True, "Reply in chat", "Off = commands work silently."),
        ("prefix", "str", "!", "Command prefix", "The character(s) before a command."),
        ("reply_prefix", "str", "", "Text before every reply", "Eg. a music-note emoji. Empty = nothing."),
        ("cmd_aliases", "cmds", COMMANDS, "Command names", "Words that trigger each command, comma separated. Add your own (eg. !tune)."),
        ("msgs", "msgs", {k: v[1] for k, v in MSGS.items()}, "Replies", "What the bot says. Use {placeholders}; an empty reply = stay silent."),
    ]},
    {"id": "schedule", "title": "Schedule & background music", "items": [
        ("schedule_enabled", "bool", False, "Open/close requests on a schedule", "Opens and closes requests automatically (this PC's clock). Manual toggles still work in between."),
        ("schedule_open", "str", "17:00", "Open at", "24h time, eg. 17:00."),
        ("schedule_close", "str", "21:00", "Close at", "24h time; may be after midnight, eg. 01:00."),
        ("schedule_days", "str", "mon,tue,wed,thu,fri,sat,sun", "Days", "Comma separated: mon,tue,wed,thu,fri,sat,sun."),
        ("autostart_queue", "bool", False, "Start the queue when idle", "If Spotify is idle and songs are queued, start playing them."),
        ("fallback_playlist", "str", "", "Background playlist", "A Spotify playlist/album link or URI played when nothing is queued (empty = off)."),
        ("fallback_shuffle", "bool", True, "Shuffle background playlist", ""),
        ("fallback_after_s", "int", 20, "Idle seconds before background music", ""),
        ("fallback_only_open", "bool", True, "Only while requests are open", "Safety: no surprise music when you are not streaming."),
    ]},
    {"id": "player", "title": "Playback & text files", "items": [
        ("volume_min", "int", 0, "Minimum volume", "Volume controls never go below this."),
        ("volume_max", "int", 100, "Maximum volume", "Volume controls (and !volume) never go above this."),
        ("json_file", "bool", True, "Write nowplaying.json", "A JSON file with the current song for other tools (Streamer.bot etc.)."),
        ("queue_file_lines", "int", 0, "Queue text file lines", "Writes the next N songs to queue.txt for an OBS text source (0 = off)."),
        ("jit_ms", "int", 25000, "Send next song this early (ms)", "How long before the end the next song goes to Spotify's queue."),
        ("close_on_offline", "bool", True, "Close requests when stream ends", "Closes song requests when the stream goes offline."),
        ("np_template", "str", "{title} - {artist}", "Text file template", "Written to nowplaying.txt: {title} {artist} {album} {requester}."),
        ("np_idle_text", "str", "", "Text file when idle", "Written when nothing is playing."),
    ]},
    {"id": "overlay", "title": "OBS overlay look", "items": [
        ("overlay_show_next", "int", 2, "Up-next rows", "How many upcoming songs to show (0 = none)."),
        ("ov_theme", "choice:dark|light|glass|minimal", "dark", "Theme", "dark, light, glass (translucent) or minimal (text only)."),
        ("ov_accent", "color", "#ff9900", "Accent colour", "Progress bar and highlights."),
        ("ov_show_art", "bool", True, "Show cover art", ""),
        ("ov_show_requester", "bool", True, "Show who requested", ""),
        ("ov_show_progress", "bool", True, "Show progress bar", ""),
        ("ov_hide_paused", "bool", False, "Hide when paused", "Fade the overlay out while music is paused."),
        ("ov_width", "int", 460, "Width (px)", ""),
        ("ov_size", "int", 100, "Text size (%)", "Scales the whole card."),
        ("ov_radius", "int", 14, "Corner radius (px)", ""),
        ("ov_font", "str", "", "Font", "A font installed on this PC (empty = Segoe UI)."),
    ]},
]

DEFAULTS = {}
META = {}
for _g in SCHEMA:
    for _k, _kind, _d, _label, _help in _g["items"]:
        DEFAULTS[_k] = _d
        META[_k] = {"kind": _kind, "label": _label, "help": _help, "group": _g["id"]}

PRESETS = {
    "relaxed": ("Relaxed", "Open-door: more songs per viewer, no cooldown, long songs ok.",
                {"per_user_limit": 3, "cooldown_s": 0, "max_length_s": 900, "block_explicit": False, "stream_safe": False, "require_approval": False, "queue_max": 100}),
    "balanced": ("Balanced", "Sensible everyday defaults.",
                 {"per_user_limit": 2, "sub_extra": 2, "cooldown_s": 30, "max_length_s": 600, "block_explicit": False, "stream_safe": False,
                  "require_approval": False, "sub_only": False, "mod_only": False, "fair_queue": True, "queue_max": 50}),
    "strict": ("Strict", "One at a time, short songs, no explicit, cooldown, artist cap.",
               {"per_user_limit": 1, "sub_extra": 1, "cooldown_s": 120, "max_length_s": 420, "block_explicit": True, "max_per_artist": 2, "queue_max": 25}),
    "subs": ("Subs only", "Only subscribers, VIPs and mods can request.", {"sub_only": True, "mod_only": False}),
    "mods": ("Mods only", "Only mods can request.", {"mod_only": True, "sub_only": False}),
    "safe": ("Stream-safe", "No explicit songs and every request needs your approval.", {"stream_safe": True, "block_explicit": True, "require_approval": True}),
    "closed": ("Closed", "Stop taking requests.", {"requests_open": False}),
}
