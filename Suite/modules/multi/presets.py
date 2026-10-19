"""Ready-made chat looks. Each is a partial style merged over the defaults by chatstyle.sanitize()."""
import chatstyle


def _r(**kw):
    return kw


PRESETS = {
    "Pinguino": {"desc": "The default: dark, orange accents.", "style": {}},
    "Compact": {"desc": "Small and tight: more messages on screen.",
                "style": {"base": {"size": 12, "spacing": 1, "line": 1.2, "timestamps": False, "marker": "logo", "radius": 2, "emoteSize": 130}}},
    "Big and readable": {"desc": "Large text for a second monitor you glance at.",
                         "style": {"base": {"size": 20, "weight": 500, "spacing": 9, "line": 1.5, "nameWeight": 800, "emoteSize": 180,
                                            "marker": "both", "radius": 8}}},
    "Paper (light)": {"desc": "Light background, dark text.",
                      "style": {"base": {"bg": "#f6f2ea", "bgA": 100, "text": "#1d1d1f", "intensity": 120},
                                "role": {"streamer": _r(name="#a85a00", bg="#ff9900", bgA=24), "mod": _r(name="#177a4f"),
                                         "vip": _r(name="#c0306f"), "bot": _r(text="#6d6d73")}}},
    "High contrast": {"desc": "Pure black and white, strong highlights.",
                      "style": {"base": {"bg": "#000000", "bgA": 100, "text": "#ffffff", "weight": 600, "nameWeight": 900,
                                         "intensity": 170, "size": 16}}},
    "Minimal": {"desc": "Just names and words. No times, badges or tags, soft highlights.",
                "style": {"base": {"timestamps": False, "badges": False, "marker": "none", "intensity": 40, "spacing": 3, "radius": 0}}},
    "Neon": {"desc": "Dark purple with glowing colours.",
             "style": {"base": {"bg": "#0b0014", "bgA": 100, "text": "#f4eaff", "family": "Trebuchet MS", "intensity": 150, "anim": "pulse", "size": 15},
                       "role": {"streamer": _r(bg="#ff2bd6", bgA=22, name="#ff7bea"), "mod": _r(bg="#00f0ff", bgA=14, name="#6ff7ff"),
                                "vip": _r(bg="#b86bff", bgA=14, name="#d5a8ff")}}},
    "Cozy": {"desc": "Warm serif text with rounded corners.",
             "style": {"base": {"family": "Georgia", "size": 16, "spacing": 8, "radius": 12, "bg": "#1b1612", "bgA": 100, "text": "#f0e6d8", "line": 1.45}}},
    "Terminal": {"desc": "Green on black, monospace.",
                 "style": {"base": {"family": "Consolas", "size": 14, "spacing": 1, "radius": 0, "bg": "#000000", "bgA": 100, "text": "#39ff14",
                                    "marker": "text", "nameWeight": 400, "intensity": 70}}},
    "On-stream overlay": {"desc": "No background, big bold white text. For OBS.",
                          "style": {"base": {"bgA": 0, "text": "#ffffff", "size": 22, "weight": 600, "nameWeight": 800, "spacing": 7,
                                             "marker": "logo", "timestamps": False, "anim": "slide"}}},
}


def preset_style(name):
    p = PRESETS.get(name)
    return chatstyle.sanitize(p["style"]) if p else None
