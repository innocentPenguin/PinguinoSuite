"""OBS browser-source widgets: /obs/chat and /obs/activity. Settings use Synchra's chat-widget field names so a Synchra export imports
as it is (and ours exports back to that shape). Pure functions only; the server stores the result in kv and serves the pages."""
import re

SIZES = {"xs": 16, "s": 20, "m": 24, "l": 30, "xl": 36, "xxl": 44}
PROVIDERS = ("twitch", "youtube", "kick", "discord", "tiktok")
STYLES = ("simple", "bubble", "boxed")
ENTRANCE = ("none", "fade", "slide", "pop")
KINDS = ("chat", "activity", "follow")
FOLLOW_ANIM = ("fade", "slide", "pop", "bounce")
ACT_TYPES = ("follow", "redeem", "sub", "resub", "gift", "cheer", "raid", "announcement", "shoutout", "ban", "timeout", "unban", "mod", "unmod", "raid_out", "poll", "prediction", "hype")
FONTS = {"nunito": "Nunito, 'Segoe UI', sans-serif", "system": "'Segoe UI', Arial, sans-serif", "roboto": "Roboto, Arial, sans-serif",
         "arial": "Arial, sans-serif", "georgia": "Georgia, serif", "consolas": "Consolas, monospace", "comic": "'Comic Sans MS', cursive",
         "impact": "Impact, sans-serif", "trebuchet": "'Trebuchet MS', sans-serif", "verdana": "Verdana, sans-serif"}

CHAT_DEFAULT = {
    "canvas_scale": 1, "size": "xl", "text_color": "#ffffff", "text_shadow_color": "#000000", "background_color": "", "background_opacity": 1,
    "border_width": 0, "border_color": "", "border_radius": 0, "font_family_id": "nunito", "message_fade_duration_seconds": 0,
    "message_delay_seconds": 0, "ignore_names": [], "provider_logo": False, "provider_logo_display": None, "badges": True,
    "username_colon": True, "notices": True, "message_order": "bottom", "message_alignment": "left", "providers": ["all"],
    "style_type": "simple", "entrance_animation_type": "fade", "themes": [], "custom_css": "",
    # ours (ignored by Synchra on export)
    "max_messages": 30, "accent_color": "#ff8a1f", "name_color_mode": "platform",
}
ACTIVITY_DEFAULT = {
    "canvas_scale": 1, "size": "l", "text_color": "#ffffff", "text_shadow_color": "#000000", "background_color": "#14110d", "background_opacity": 0.85,
    "border_width": 0, "border_color": "", "border_radius": 8, "font_family_id": "nunito", "message_fade_duration_seconds": 12,
    "message_delay_seconds": 0, "ignore_names": [], "provider_logo": True, "providers": ["all"], "style_type": "boxed",
    "entrance_animation_type": "slide", "custom_css": "", "max_messages": 6, "message_order": "bottom", "message_alignment": "left",
    "types": list(ACT_TYPES), "show_age": False, "accent_color": "#ff8a1f", "paused": False,
}
FOLLOW_DEFAULT = {
    "canvas_scale": 1, "size": "xxl", "text_color": "#ffffff", "text_shadow_color": "#000000", "background_color": "#14110d", "background_opacity": 0.85,
    "border_width": 3, "border_color": "#ff8a1f", "border_radius": 16, "font_family_id": "nunito", "message_fade_duration_seconds": 0, "message_delay_seconds": 0,
    "ignore_names": [], "provider_logo": False, "providers": ["all"], "style_type": "boxed", "entrance_animation_type": "pop", "custom_css": "",
    "max_messages": 1, "message_order": "bottom", "message_alignment": "center", "accent_color": "#ff8a1f",
    "follow_text": "{user} just followed!", "refollow_text": "{user} followed again", "show_refollow": True, "duration_seconds": 6, "gap_seconds": 1,
    "sound_enabled": True, "sound_volume": 60, "sound_url": "", "image_url": "",
}
DEFAULTS = {"chat": CHAT_DEFAULT, "activity": ACTIVITY_DEFAULT, "follow": FOLLOW_DEFAULT}

IVAN_CHAT = {
    "canvas_scale": 1, "size": "xxl", "text_color": "#ffffff", "text_shadow_color": "#000000", "background_color": "", "background_opacity": 1,
    "border_width": 0, "border_color": "", "border_radius": 0, "font_family_id": "nunito", "message_fade_duration_seconds": 0,
    "message_delay_seconds": 0,
    "ignore_names": ["nightbot", "StreamElements", "PinguinoB0t", "SoundAlerts", "potatbotat", "sery_bot", "synchrabot", "PinguinoHelper", "ChattyPinguino"],
    "provider_logo": False, "badges": True, "username_colon": True, "notices": True, "message_order": "bottom", "message_alignment": "left",
    "providers": ["all"], "style_type": "simple", "entrance_animation_type": "fade",
    "custom_css": "@import url('https://use.typekit.net/inf0cul.css');\n\n.chat-message-container {\n    margin: 0 !important;\n    padding: 0px 4px !important;\n}\n\n"
                  ".chat-message-container,\n.chat-message-container * {\n    font-family: \"Unkempt\", cursive !important;\n    font-weight: 400;\n"
                  "    font-style: normal;\n    line-height: 1.35 !important;\n    margin-top: -4px !important;\n    margin-bottom: -4px !important;\n}",
}
PRESETS = {
    "chat": {
        "Ivan (saved Synchra look)": {"desc": "Your Synchra settings and the Unkempt font CSS, with the bot ignore list.", "settings": IVAN_CHAT},
        "Simple": {"desc": "Synchra's simple theme: white text, soft shadow, no box.", "settings": {}},
        "Penguino": {"desc": "Dark box, orange accent, rounded.", "settings": {"size": "xl", "background_color": "#14110d", "background_opacity": 0.8,
                     "border_width": 2, "border_color": "#ff8a1f", "border_radius": 12, "style_type": "bubble", "provider_logo": True,
                     "entrance_animation_type": "slide", "ignore_names": IVAN_CHAT["ignore_names"]}},
        "Big and readable": {"desc": "Large text, strong shadow, fades after 40 s.", "settings": {"size": "xxl", "message_fade_duration_seconds": 40,
                             "text_shadow_color": "#000000", "ignore_names": IVAN_CHAT["ignore_names"]}},
    },
    "follow": {
        "Penguino": {"desc": "Dark card, orange border, pop-in, chime.", "settings": {}},
        "Text only": {"desc": "Big text, no box.", "settings": {"style_type": "simple", "background_color": "", "border_width": 0, "entrance_animation_type": "fade"}},
        "Quiet": {"desc": "Same card, no sound.", "settings": {"sound_enabled": False}},
    },
    "activity": {
        "Penguino": {"desc": "Dark cards, orange accent.", "settings": {}},
        "Minimal": {"desc": "Text only, no boxes.", "settings": {"style_type": "simple", "background_color": "", "provider_logo": False}},
    },
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _color(v, default=""):
    return v if isinstance(v, str) and (_HEX.match(v) or v == "") else default


def _num(v, lo, hi, default):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, x))


def _names(v):
    out, seen = [], set()
    for n in (v if isinstance(v, list) else []):
        n = str(n).strip()[:60]
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out[:200]


def sanitize(kind, src):
    """Clamp every field of a widget settings dict; unknown keys are dropped."""
    d = dict(DEFAULTS[kind])
    s = src if isinstance(src, dict) else {}
    d["canvas_scale"] = round(_num(s.get("canvas_scale", d["canvas_scale"]), 0.25, 4, d["canvas_scale"]), 2)
    d["size"] = s.get("size") if s.get("size") in SIZES else d["size"]
    for k in ("text_color", "text_shadow_color", "background_color", "border_color", "accent_color"):
        d[k] = _color(s.get(k, d[k]), d[k])
    d["background_opacity"] = round(_num(s.get("background_opacity", d["background_opacity"]), 0, 1, d["background_opacity"]), 2)
    d["border_width"] = int(_num(s.get("border_width", d["border_width"]), 0, 20, d["border_width"]))
    d["border_radius"] = int(_num(s.get("border_radius", d["border_radius"]), 0, 60, d["border_radius"]))
    d["font_family_id"] = s.get("font_family_id") if s.get("font_family_id") in FONTS else d["font_family_id"]
    d["message_fade_duration_seconds"] = round(_num(s.get("message_fade_duration_seconds", d["message_fade_duration_seconds"]), 0, 3600, 0), 1)
    d["message_delay_seconds"] = round(_num(s.get("message_delay_seconds", d["message_delay_seconds"]), 0, 60, 0), 1)
    d["ignore_names"] = _names(s.get("ignore_names", d["ignore_names"]))
    for k in ("provider_logo", "badges", "username_colon", "notices", "show_age", "paused"):
        if k in d:
            d[k] = bool(s.get(k, d[k]))
    d["message_order"] = s.get("message_order") if s.get("message_order") in ("bottom", "top") else d["message_order"]
    d["message_alignment"] = s.get("message_alignment") if s.get("message_alignment") in ("left", "right", "center") else d["message_alignment"]
    pv = [p for p in (s.get("providers") if isinstance(s.get("providers"), list) else d["providers"]) if p == "all" or p in PROVIDERS]
    d["providers"] = pv or ["all"]
    d["style_type"] = s.get("style_type") if s.get("style_type") in STYLES else d["style_type"]
    d["entrance_animation_type"] = s.get("entrance_animation_type") if s.get("entrance_animation_type") in ENTRANCE else d["entrance_animation_type"]
    if kind == "follow":
        d["follow_text"] = str(s.get("follow_text", d["follow_text"]))[:120] or d["follow_text"]
        d["refollow_text"] = str(s.get("refollow_text", d["refollow_text"]))[:120] or d["refollow_text"]
        d["show_refollow"] = bool(s.get("show_refollow", d["show_refollow"]))
        d["duration_seconds"] = round(_num(s.get("duration_seconds", d["duration_seconds"]), 1, 60, 6), 1)
        d["gap_seconds"] = round(_num(s.get("gap_seconds", d["gap_seconds"]), 0, 30, 1), 1)
        d["sound_enabled"] = bool(s.get("sound_enabled", d["sound_enabled"]))
        d["sound_volume"] = int(_num(s.get("sound_volume", d["sound_volume"]), 0, 100, 60))
        for k in ("sound_url", "image_url"):                       # http(s) or a path on this server only
            v = str(s.get(k, "") or "").strip()[:500]
            d[k] = v if re.match(r"^(https?://|/)[^\s\"'<>]*$", v) else ""
        d["entrance_animation_type"] = s.get("entrance_animation_type") if s.get("entrance_animation_type") in FOLLOW_ANIM else "pop"
    d["max_messages"] = int(_num(s.get("max_messages", d["max_messages"]), 1, 100, d["max_messages"]))
    css = s.get("custom_css", d["custom_css"])
    d["custom_css"] = re.sub(r"</?style", "", str(css), flags=re.I)[:20000] if isinstance(css, str) else ""
    if kind == "chat":
        d["themes"] = s.get("themes") if isinstance(s.get("themes"), list) else []
        d["provider_logo_display"] = s.get("provider_logo_display") if isinstance(s.get("provider_logo_display"), str) else None
        d["name_color_mode"] = s.get("name_color_mode") if s.get("name_color_mode") in ("platform", "own", "none") else "platform"
    elif kind == "activity":
        ty = [t for t in (s.get("types") if isinstance(s.get("types"), list) else d["types"]) if t in ACT_TYPES]
        d["types"] = ty
    return d


def from_synchra(doc):
    """Accepts Synchra's export ({"kind":"synchra.widget","settings":{...}}) or the bare settings object. Returns (settings, error)."""
    if not isinstance(doc, dict):
        return None, "not a JSON object"
    if "settings" in doc and isinstance(doc["settings"], dict):
        if doc.get("kind") not in (None, "synchra.widget", "pinguino.obs"):
            return None, "not a Synchra widget export"
        s = doc["settings"]
    else:
        s = doc
    # Synchra provider names can be capitalised
    if isinstance(s.get("providers"), list):
        s = dict(s, providers=[str(p).lower() for p in s["providers"]])
    return sanitize("chat", s), ""


def to_synchra(kind, settings, name="Chat"):
    keys = [k for k in CHAT_DEFAULT if k not in ("max_messages", "accent_color", "name_color_mode")] if kind == "chat" else list(settings)
    return {"kind": "synchra.widget", "version": 1, "type": {"chat": "chat_widget", "activity": "activity_widget", "follow": "follow_alert_widget"}[kind], "name": name,
            "settings": {k: settings[k] for k in keys if k in settings}}


def hidden(kind, settings, m, muted=()):
    """True when this message must not appear in the widget."""
    user = (m.get("user") or "").lower()
    disp = (m.get("display") or "").lower()
    ig = {n.lower() for n in settings["ignore_names"]}
    if user in ig or disp in ig or user in muted or m.get("raw_type") == "dev":
        return True
    if "all" not in settings["providers"] and m.get("platform") not in settings["providers"]:
        return True
    ev = m.get("event") or ""
    if kind == "chat":
        return bool(ev) and not settings["notices"]
    if kind == "follow":
        return ev != "follow" or (bool(m.get("flags") and "refollow" in m["flags"]) and not settings["show_refollow"])
    return ev not in settings["types"]
