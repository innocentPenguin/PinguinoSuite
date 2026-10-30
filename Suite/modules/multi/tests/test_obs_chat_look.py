"""OBS chat overlay look options: defaults keep the current look, sanitize clamps, Synchra round trip, show-bots, page hooks."""
import pathlib

import pytest
import obs

NEW = ("font_px", "line_height", "row_padding", "row_gap", "name_size", "badge_size", "width", "show_bots")
HTML = (pathlib.Path(__file__).resolve().parent.parent / "static" / "obs.html").read_text("utf-8")


def test_defaults_are_the_current_look():
    d = obs.sanitize("chat", {})
    assert (d["font_px"], d["line_height"], d["row_padding"], d["row_gap"]) == (23, 1.3, 0, 11)       # ~half of the old 44 px
    assert (d["name_size"], d["badge_size"], d["width"], d["show_bots"], d["provider_logo"]) == (100, 100, 100, False, False)
    old = obs.sanitize("chat", obs.IVAN_CHAT)
    assert all(old[k] == obs.CHAT_DEFAULT[k] for k in NEW) and old["custom_css"] == "" and old["look"] == "synchra"
    for name, p in obs.PRESETS["chat"].items():
        assert obs.sanitize("chat", p["settings"])["show_bots"] is False, name


def test_sanitize_clamps_and_falls_back():
    s = obs.sanitize("chat", {"font_px": 999, "line_height": 9, "row_padding": -5, "row_gap": 500, "name_size": 1, "badge_size": 9999, "width": 0, "show_bots": "yes"})
    assert (s["font_px"], s["line_height"], s["row_padding"], s["row_gap"]) == (140, 2.5, 0, 40)
    assert (s["name_size"], s["badge_size"], s["width"], s["show_bots"]) == (50, 250, 20, False)
    bad = obs.sanitize("chat", {k: "junk" for k in NEW})
    assert all(bad[k] == obs.CHAT_DEFAULT[k] for k in NEW)
    assert obs.sanitize("chat", {"font_px": 4})["font_px"] == 10          # a px size below 10 would be unreadable
    assert obs.sanitize("chat", {"font_px": 30.4, "show_bots": True}) ["font_px"] == 30
    assert obs.sanitize("chat", {"show_bots": True})["show_bots"] is True
    assert not any(k in obs.sanitize("activity", {"font_px": 50}) for k in NEW)


def test_synchra_round_trip_ignores_our_keys():
    st = obs.sanitize("chat", {"font_px": 40, "width": 60, "show_bots": True, "max_messages": 12, "size": "l"})
    doc = obs.to_synchra("chat", st)
    assert not any(k in doc["settings"] for k in NEW) and "max_messages" not in doc["settings"]
    back, err = obs.from_synchra(doc)
    assert not err and back["size"] == "l" and all(back[k] == obs.CHAT_DEFAULT[k] for k in NEW)


def test_show_bots_lifts_ignore_list_for_bots_only():
    m = {"user": "nightbot", "display": "Nightbot", "platform": "twitch", "event": "", "is_bot": True}
    off = obs.sanitize("chat", {"ignore_names": ["nightbot"]})
    on = obs.sanitize("chat", {"ignore_names": ["nightbot"], "show_bots": True})
    assert obs.hidden("chat", off, m) and not obs.hidden("chat", on, m)
    human = dict(m, is_bot=False)
    assert obs.hidden("chat", on, human) and obs.hidden("chat", on, m, muted=("nightbot",))


def test_page_renders_new_keys_without_new_elements():
    for hook in ("--lh", "--rp", "--rg", "--ns", "--bs", "--wd", "S.font_px", "S.show_bots"):
        assert hook in HTML, hook
    assert "S.provider_logo ?" in HTML and "api/obs/' + KIND" in HTML          # logo stays opt-in; settings poll as a safety net
    assert "var(--lh,1.25)" in HTML and "var(--rg,2px)" in HTML                 # fallbacks equal the old fixed values


OLD_SAVED = {"size": "xxl", "font_family_id": "nunito", "ignore_names": ["nightbot"], "text_color": "#ffcc00",
             "custom_css": "@import url('https://use.typekit.net/inf0cul.css'); .chat-message-container{margin:0 !important}"}


def test_migration_unpins_the_old_big_look_and_keeps_the_rest():
    st = obs.sanitize("chat", obs.migrate_chat(OLD_SAVED))
    assert st["font_px"] == 23 and st["custom_css"] == "" and st["look"] == "synchra" and st["font_family_id"] == "nunito"
    assert st["text_color"] == "#ffcc00" and st["ignore_names"] == ["nightbot"]
    assert obs.migrate_chat(dict(OLD_SAVED, font_px=33))["font_px"] == 33        # a hand-set size survives
    once = obs.migrate_chat(OLD_SAVED)
    assert obs.migrate_chat(once) == once                                          # idempotent
    mine = dict(OLD_SAVED, custom_css=".x{color:red}")
    assert obs.migrate_chat(mine)["custom_css"] == ".x{color:red}"                 # own CSS is never dropped


def test_look_keys_and_commands():
    s = obs.sanitize("chat", {"look": "x", "badge_style": "y", "platform_pill": "no", "hide_commands": 3})
    assert (s["look"], s["badge_style"], s["platform_pill"], s["hide_commands"]) == ("synchra", "image", False, True)
    assert obs.sanitize("chat", {"look": "classic", "badge_style": "pill"})["look"] == "classic"
    cmd = {"user": "x", "platform": "twitch", "event": "", "text": "!lurk"}
    assert obs.hidden("chat", s, cmd) and not obs.hidden("chat", s, dict(cmd, text="hi !lurk"))
    assert not obs.hidden("chat", obs.sanitize("chat", {"hide_commands": False}), cmd)
    doc = obs.to_synchra("chat", s)["settings"]
    assert not any(k in doc for k in ("look", "badge_style", "platform_pill", "hide_commands"))


def test_twitch_badges_parse_and_cache():
    import twitch_badges as tb
    class R:
        def __init__(s, j, c=200): s.j, s.status_code = j, c
        def json(s): return s.j
    calls = []
    def get(url, **kw):
        calls.append(url)
        if url.endswith("/global"):
            return R({"data": [{"set_id": "moderator", "versions": [{"id": "1", "image_url_2x": "https://x/mod.png"}]},
                               {"set_id": "subscriber", "versions": [{"id": "0", "image_url_2x": "https://x/g.png"}]}]})
        return R({"data": [{"set_id": "subscriber", "versions": [{"id": "0", "image_url_2x": "https://x/s0.png"}, {"id": "3", "image_url_2x": "http://bad"}]}]})
    d = tb.fetch({}, "42", get)
    assert d == {"moderator": {"1": "https://x/mod.png"}, "subscriber": {"0": "https://x/s0.png"}}
    class C:
        def tokens(s): return {"access_token": "t"}
        def _headers(s, t): return {}
        broadcaster_id = "42"
    tb._cache.update(at=0.0, ttl=0.0, data={})
    assert tb.badges(C(), now=lambda: 100.0, get=get) == d and tb.badges(C(), now=lambda: 200.0, get=get) == d
    assert len(calls) == 4                                                          # 2 calls once, second read from the cache
    tb._cache.update(at=0.0, ttl=0.0, data={})
    assert tb.badges(None) == {}


def test_font_default_is_nunito_bundled_and_hand_picked_fonts_survive():
    assert obs.sanitize("chat", {})["font_family_id"] == "nunito" and obs.sanitize("chat", obs.IVAN_CHAT)["font_family_id"] == "nunito"
    for old in ("rubik", "inter"):
        assert obs.migrate_chat({"look": "synchra", "font_family_id": old})["font_family_id"] == "nunito"
        assert obs.migrate_chat({"font_family_id": old})["font_family_id"] == "nunito"
    assert obs.migrate_chat({"look": "synchra", "font_family_id": "georgia"})["font_family_id"] == "georgia"
    assert obs.migrate_chat({"font_family_id": "impact"})["font_family_id"] == "impact"
    root = pathlib.Path(__file__).resolve().parent.parent / "static"
    assert (root / "fonts" / "Nunito.woff2").read_bytes()[:4] == b"wOF2" and (root / "fonts" / "OFL.txt").stat().st_size > 1000
    html = (root / "obs.html").read_text("utf-8")
    assert "url(/assets/fonts/Nunito.woff2)" in html and "letter-spacing:.05em" in html and "1px 1px 1px" in html and "http" not in html.split("@font-face")[1].split(chr(10))[0]


def test_page_has_synchra_notice_markup():
    html = (pathlib.Path(__file__).resolve().parent.parent / "static" / "obs.html").read_text(encoding="utf-8")
    assert "pill ev" in html and "nchip" in html


def test_platform_pill_off_by_default_and_migrated_once():
    assert obs.CHAT_DEFAULT["platform_pill"] is False
    old = obs.migrate_chat({"look": "synchra", "platform_pill": True, "font_family_id": "nunito"})
    assert old["platform_pill"] is False and old["names_v"] == 1
    assert obs.migrate_chat(old) == old                                         # idempotent
    hand = obs.sanitize("chat", dict(old, platform_pill=True))                  # a save after the migration is kept as set
    assert hand["platform_pill"] is True and obs.migrate_chat(hand)["platform_pill"] is True
    assert obs.migrate_chat({"font_px": 40})["platform_pill"] is False


def test_page_has_handle_names():
    html = (pathlib.Path(__file__).resolve().parent.parent / "static" / "obs.html").read_text(encoding="utf-8")
    assert "function shownName" in html and "hashCol" in html and "'@' +" in html


def test_shown_names_three_platforms_and_fallbacks():
    import json
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    html = (pathlib.Path(__file__).resolve().parent.parent / "static" / "obs.html").read_text(encoding="utf-8")
    fn = re.search(r"function shownName\(m\) \{.*?\n\}\n", html, re.S).group(0)
    cases = [({"platform": "youtube", "user": "@ann_yt", "display": "Ann Channel"}, "@ann_yt"),
             ({"platform": "youtube", "user": "ann channel", "display": "Ann Channel"}, "@AnnChannel"),
             ({"platform": "tiktok", "user": "bob.tt", "display": "Bob Nick"}, "@bob.tt"),
             ({"platform": "tiktok", "user": "", "display": "Bob"}, "@Bob"),
             ({"platform": "twitch", "user": "cy", "display": "Cy"}, "Cy")]
    js = fn + "const S={look:'synchra'};console.log(JSON.stringify(" + json.dumps([c for c, _ in cases]) + ".map(shownName)));"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [w for _, w in cases]
