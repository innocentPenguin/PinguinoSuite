using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

public static class Harness
{
    static CPHInline bot = new CPHInline();
    static string dir;
    static int failed = 0;

    static void Run(string user, string cmd, string input = "", bool mod = false)
    {
        CPHProxy.Args.Clear();
        CPHProxy.Args["command"] = cmd;
        CPHProxy.Args["rawInput"] = input;
        CPHProxy.Args["user"] = user;
        CPHProxy.Args["userName"] = user;
        CPHProxy.Args["userId"] = "id_" + user;
        CPHProxy.Args["role"] = mod ? 3 : 1;
        CPHProxy.Args["isModerator"] = mod;
        CPHProxy.Args["isBroadcaster"] = false;
        CPHProxy.Sent.Clear();
        bot.Execute();
    }
    static JObject State() { return JObject.Parse(File.ReadAllText(Path.Combine(dir, "live_state.json"))); }
    static JObject Players() { return JObject.Parse(File.ReadAllText(Path.Combine(dir, "players.json"))); }
    static void Check(bool ok, string what)
    {
        Console.WriteLine((ok ? "PASS " : "FAIL ") + what);
        if (!ok) { failed++; Console.WriteLine("   chat: " + string.Join(" || ", CPHProxy.Sent)); }
    }
    static string[] Q() { return State()["queue"].Select(x => (string)x["user"]).ToArray(); }
    static string[] Team(string side) { return State()["currentMatch"][side].Select(x => (string)x["Username"]).ToArray(); }

    public static int Main(string[] a)
    {
        dir = Path.Combine(Path.GetTempPath(), "bvqtest_" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(dir);
        Environment.SetEnvironmentVariable("PINGUINO_DATA_DIR", dir);
        Environment.SetEnvironmentVariable("BVQ_WHEEL_FAST", "1");
        // 12 registered players with a set MMR (so no Tracker/network lookups happen).
        var players = new JObject();
        foreach (var n in new[] { "innocentpenguin_", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11" })
            players[n] = JObject.FromObject(new { Username = n, Platform = "epic", GameId = n + "_rl", PeakMmr = 1000, MmrSource = "manual", Wins = 0, Losses = 0, Points = 0 });
        File.WriteAllText(Path.Combine(dir, "players.json"), players.ToString());

        // ---- competitive ----
        Run("mod1", "!activity", "competitive", true);
        Check(State()["activity"].ToString() == "competitive" && (bool)State()["queueOpen"], "activity competitive opens the queue");
        Check(Q().SequenceEqual(new[] { "innocentpenguin_" }), "streamer is auto-added at #1");
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8" }) Run(n, "!join");
        Check(Q().Length == 9, "9 in queue (streamer + 8)");
        Run("mod1", "!balance", "", true);
        var blue = Team("blue"); var orange = Team("orange");
        Check(blue.Length == 3 && orange.Length == 3, "3v3 teams made");
        Check(blue.Concat(orange).Contains("innocentpenguin_"), "streamer is in the match");
        Check(Q().Length == 3, "3 left waiting after 6 pulled: " + string.Join(",", Q()));
        Check(State()["currentMatch"]["blue"][0]["MmrSource"].ToString() == "mod", "teams carry the MMR source");
        Check(State()["queue"][0]["mmr"].ToString() == "1000" && State()["queue"][0]["mmrSource"].ToString() == "mod", "queue carries mmr + source");

        // ---- drag: out / in / move ----
        string victim = blue.First(x => x != "innocentpenguin_");
        Run("mod1", "!out", victim, true);
        Check(State()["currentMatch"]["blue"].Count() == 2, "dragging a player out leaves an empty slot");
        Check(Q()[0] == victim, "the removed player goes to the FRONT of the queue (" + Q()[0] + ")");
        string filler = Q().First(x => x != victim);
        Run("mod1", "!in", filler + " blue", true);
        Check(Team("blue").Length == 3 && Team("blue").Contains(filler), "queued player dragged into the empty slot");
        string extra = Q().First();
        Run("mod1", "!in", extra + " blue", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("no empty slot")), "full team refuses another player");
        var q0 = Q();
        Run("mod1", "!move", q0.Last() + " 1", true);
        Check(Q()[0] == q0.Last(), "queue reorder moves a player to #1");
        string first = Q()[0];
        Run("p3", "!move", Q().Last() + " 1", false);
        Check(Q()[0] == first, "non-mods cannot reorder");

        // ---- result + kick after play ----
        Run("mod1", "!win", "blue", true);
        var ps = Players();
        var winners = Team("blue");
        Check(ps[winners[0]]["Wins"].ToString() == "1" && ps[winners[0]]["Points"].ToString() == "3", "competitive win records wins + points");
        var played = Team("blue").Concat(Team("orange")).ToList();
        Check(!Q().Any(x => played.Contains(x) && x != "innocentpenguin_"), "as soon as the result is recorded, everyone who played is out of the queue: " + string.Join(",", Q()));
        foreach (var n in new[] { "p9", "p10", "p11" }) Run(n, "!join");
        Run("mod1", "!next", "", true);
        var nextMatch = State()["currentMatch"] == null ? new string[0] : Team("blue").Concat(Team("orange")).ToArray();
        Check(nextMatch.Length == 6, "next match is made (" + nextMatch.Length + " players)");
        Check(nextMatch.Contains("innocentpenguin_"), "streamer plays the next match automatically");
        Check(!nextMatch.Except(new[] { "innocentpenguin_" }).Any(x => played.Contains(x)), "nobody who just played is back in the next match (kicked, must !join)");
        Run("mod1", "!win", "orange", true);
        Run("mod1", "!next", "", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("Not enough players")), "after playing, not enough waiting: " + string.Join(" | ", CPHProxy.Sent));
        Check(!Q().Any(x => (played.Contains(x) || nextMatch.Contains(x)) && x != "innocentpenguin_"), "everyone who played is out of the queue: " + string.Join(",", Q()));

        // ---- casual: no stats ----
        var waitingBefore = Q().Where(x => x != "innocentpenguin_").ToArray();
        Run("mod1", "!activity", "casual", true);
        Check(State()["activity"].ToString() == "casual", "casual is now the activity");
        Check(State()["currentMatch"] == null || State()["currentMatch"].Type == Newtonsoft.Json.Linq.JTokenType.Null, "switching activity ends the current match");
        Check(!nextMatch.Except(new[] { "innocentpenguin_" }).Any(x => Q().Contains(x)), "players who were in the match are removed on switch");
        Check(waitingBefore.All(x => Q().Contains(x)), "people waiting in the queue stay (" + string.Join(",", waitingBefore) + ")");
        string pointsBefore = Players()["p1"]["Points"].ToString(), winsBefore = Players()["p1"]["Wins"].ToString();
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        Check(!(bool)State()["currentMatch"]["group"], "casual makes teams now (the group style is retired)");
        Check(CPHProxy.Sent.Any(m => m.Contains("Blue [avg")), "casual announces Blue / Orange teams");
        Run("mod1", "!win", "orange", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("casual: no points")), "casual result says no points");
        Check(Players()["p1"]["Points"].ToString() == pointsBefore && Players()["p1"]["Wins"].ToString() == winsBefore, "casual does not change stats");

        // ---- end activity ----
        Run("mod1", "!activity", "end", true);
        Check(State()["activity"].ToString() == "none" && !(bool)State()["queueOpen"] && State()["queue"].Count() == 0, "end activity closes and clears the queue");
        Run("p1", "!join");
        Check(CPHProxy.Sent.Any(m => m.Contains("closed")), "nobody can join when no activity is running");
        Run("p1", "!activity", "casual", false);
        Check(State()["activity"].ToString() == "none", "viewers cannot start an activity");

        // ---- MMR sources ----
        Run("mod1", "!activity", "viewers", true);
        Run("mod1", "!setmmr", "@p2 1500 self", true);
        Check(Players()["p2"]["MmrSource"].ToString() == "self" && Players()["p2"]["PeakMmr"].ToString() == "1500", "self-set MMR keeps its source");
        Run("p2", "!join");
        Check(State()["queue"].First(x => (string)x["user"] == "p2")["mmrSource"].ToString() == "self", "state shows source 'self'");

        // ---- "Blue stays" (next-match mode): that team stays, everyone else who played is kicked ----
        Run("mod1", "!activity", "end", true);
        Run("mod1", "!activity", "casual", true);
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        var firstBlue = Team("blue").Where(x => x != "innocentpenguin_").ToArray();
        var firstOrange = Team("orange").Where(x => x != "innocentpenguin_").ToArray();
        Run("mod1", "!win", "blue", true);
        Run("mod1", "!next", "blue", true);
        var secondMatch = Team("blue").Concat(Team("orange")).ToArray();
        Check(secondMatch.Length == 6, "next match made after Blue stays (" + secondMatch.Length + ")");
        Check(firstBlue.All(x => secondMatch.Contains(x)), "Blue stays: the blue players are still in the next match");
        Check(!firstOrange.Any(x => secondMatch.Contains(x)), "Blue stays: the orange players were kicked");
        Run("mod1", "!win", "orange", true);
        Run("mod1", "!next", "orange", true);
        var thirdMatch = Team("blue").Concat(Team("orange")).ToArray();
        Check(thirdMatch.Length == 6 || CPHProxy.Sent.Any(m => m.Contains("Not enough")), "Orange stays is handled (match or not-enough-players)");

        // ---- MATCH HISTORY FIXES: change the winner / remove a match; stats are reversed and re-applied ----
        Run("mod1", "!activity", "end", true);
        Run("mod1", "!activity", "competitive", true);
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        var histBlue = Team("blue").Where(x => x != "innocentpenguin_").ToArray();
        var histOrange = Team("orange").Where(x => x != "innocentpenguin_").ToArray();
        int histId = (int)State()["currentMatch"]["id"];
        Run("mod1", "!win", "blue", true);
        Run("mod1", "!next", "", true);   // the next match is now the current lobby; match histId is history
        string pb = histBlue[0], po = histOrange[0];
        int Stat(string who, string key) { return (int)Players()[who][key]; }
        int bw = Stat(pb, "Wins"), bl = Stat(pb, "Losses"), bp = Stat(pb, "Points");
        int ow = Stat(po, "Wins"), ol = Stat(po, "Losses"), op = Stat(po, "Points");
        Run("p3", "!matchwin", histId + " orange", false);
        Check(Stat(pb, "Wins") == bw, "non-mods cannot fix matches");
        Run("mod1", "!matchwin", histId + " orange", true);
        Check(Stat(pb, "Wins") == bw - 1 && Stat(pb, "Losses") == bl + 1 && Stat(pb, "Points") == bp - 3 + 1, "winner changed: the old winner loses the win + points and gets a loss + loss points");
        Check(Stat(po, "Wins") == ow + 1 && Stat(po, "Losses") == ol - 1 && Stat(po, "Points") == op - 1 + 3, "winner changed: the new winner gets the win + points and loses the loss");
        Run("mod1", "!matchwin", histId + " orange", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("already")), "same winner again is a no-op");
        Run("mod1", "!matchwin", histId + " blue", true);
        Check(Stat(pb, "Wins") == bw && Stat(pb, "Points") == bp && Stat(po, "Losses") == ol && Stat(po, "Points") == op, "changing it back restores the original stats exactly");
        int liveId = (int)State()["currentMatch"]["id"];
        Run("mod1", "!matchdel", liveId.ToString(), true);
        Check(CPHProxy.Sent.Any(m => m.Contains("current lobby")), "the live lobby match can't be removed");
        Run("mod1", "!matchdel", histId.ToString(), true);
        Check(Stat(pb, "Wins") == bw - 1 && Stat(pb, "Points") == bp - 3 && Stat(po, "Losses") == ol - 1 && Stat(po, "Points") == op - 1, "removing a match takes back its wins, losses and points");
        var hist = Newtonsoft.Json.Linq.JArray.Parse(File.ReadAllText(Path.Combine(dir, "matches.json")));
        Check(!hist.Any(m => (int)m["Id"] == histId), "the removed match is gone from the history file");
        Run("mod1", "!matchwin", "9999 blue", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("isn't in the history")), "unknown match id is refused");

        // ---- GAME MODES: separate standings per mode (3v3 / dropshot / rumble) ----
        int Mode(string who, string cat, string key) { var m = Players()[who]["Modes"]; return m == null || m.Type != Newtonsoft.Json.Linq.JTokenType.Object || m[cat] == null ? 0 : (int)m[cat][key]; }
        // The two matches above were standard 3v3: they count under "3v3" (and the fixes were reversed there too).
        Check(Mode(pb, "3v3", "Wins") == Stat(pb, "Wins"), "standard games count under the format (3v3)");
        Run("p3", "!gamemode", "dropshot", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("Only mods")), "non-mods cannot change the game mode");
        Run("mod1", "!gamemode", "bogus", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("Usage: !gamemode")), "bad game mode is refused");
        Run("mod1", "!gamemode", "dropshot", true);
        Check((string)State()["gameMode"] == "dropshot", "game mode is published in the state");
        Run("mod1", "!win", "orange", true);           // finishes the live 3v3 lobby (counts as 3v3: it started before the switch)
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8" }) Run(n, "!join");
        Run("mod1", "!next", "", true);                 // new lobby is a dropshot match
        var dsBlue = Team("blue").Where(x => x != "innocentpenguin_").ToArray();
        string dsw = dsBlue[0];
        int d3 = Mode(dsw, "3v3", "Wins"), dAllW = Stat(dsw, "Wins");
        Run("mod1", "!win", "blue", true);
        Check(Mode(dsw, "dropshot", "Wins") == 1 && Mode(dsw, "dropshot", "Points") == 3, "a dropshot result counts under dropshot");
        Check(Mode(dsw, "3v3", "Wins") == d3 && Stat(dsw, "Wins") == dAllW + 1, "...not under 3v3, but in the overall total");
        int dsId = (int)State()["currentMatch"]["id"];
        Run("mod1", "!matchwin", dsId + " orange", true);
        Check(Mode(dsw, "dropshot", "Wins") == 0 && Mode(dsw, "dropshot", "Losses") == 1, "fixing a dropshot match moves the dropshot stats");
        Run("mod1", "!gamemode", "standard", true);
        Check((string)State()["gameMode"] == "standard", "back to standard");
        Run("mod1", "!format", "2v2", true);
        Run("mod1", "!gamemode", "rumble", true);
        Check((string)State()["format"] == "3v3", "switching to rumble starts at 3v3");
        Run("mod1", "!format", "1v1", true);
        Check((string)State()["format"] == "1v1", "1v1 is a valid size in a special mode");
        Run("mod1", "!gamemode", "rumble", true);
        Check((string)State()["format"] == "1v1", "choosing the same game mode again keeps the size you picked");
        Run("mod1", "!format", "4v4", true);
        Check((string)State()["format"] == "4v4", "4v4 still works");
        Run("mod1", "!gamemode", "standard", true);
        Run("mod1", "!format", "3v3", true);

        // ---- STREAMER SWITCH: turning "playing" back ON puts him straight back into the queue ----
        Run("mod1", "!activity", "competitive", true);
        Check(Q().Contains("innocentpenguin_"), "streamer is in the queue when an activity starts");
        Run("mod1", "!streamer", "out", true);
        Check(!Q().Contains("innocentpenguin_"), "sitting out takes him out of the queue");
        Run("mod1", "!streamer", "in", true);
        Check(Q().Contains("innocentpenguin_") && Q()[0] == "innocentpenguin_", "turning the switch back ON puts him back in the queue at #1");
        CPHProxy.Sent.Clear(); Run("p3", "!queue", "", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("1. innocentpenguin_")), "!queue lists the first players, not only a count");
        CPHProxy.Sent.Clear(); Run("p3", "!mmr", "", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("MMR") || m.Contains("not registered")) && !CPHProxy.Sent.Any(m => m.Contains("Only mods")), "a viewer may look up their own MMR");
        CPHProxy.Sent.Clear(); Run("p3", "!mmr", "@p1", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("own MMR")), "a viewer may not look up somebody else's MMR");
        Run("mod1", "!queue", "close", true);
        Run("mod1", "!streamer", "out", true);
        Run("mod1", "!streamer", "in", true);
        Check(Q().Contains("innocentpenguin_"), "...even while the queue is closed");
        Run("mod1", "!activity", "end", true);
        Run("mod1", "!streamer", "out", true);
        Run("mod1", "!streamer", "in", true);
        Check(Q().Contains("innocentpenguin_"), "...and with no activity running");
        Run("mod1", "!activity", "end", true);

        // streamer sits out, a match starts without him and has an empty seat: switching back ON puts him in that seat
        Run("mod1", "!activity", "competitive", true);
        Run("mod1", "!streamer", "out", true);
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        Check(!State()["currentMatch"]["blue"].Concat(State()["currentMatch"]["orange"]).Any(x => (string)x["Username"] == "innocentpenguin_"), "the match started without the streamer");
        Run("mod1", "!out", "p6", true);
        Run("mod1", "!streamer", "in", true);
        Check(State()["currentMatch"]["blue"].Concat(State()["currentMatch"]["orange"]).Any(x => (string)x["Username"] == "innocentpenguin_"), "switching back ON puts him straight into the empty seat of the running match");
        Run("mod1", "!activity", "end", true);

        // ---- OBS CONTROL: scenes, sources and the auto switch ----
        CPHProxy.Obs.Clear();
        Run("p3", "!scene", "fortnite", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("Only mods")) && CPHProxy.Obs.Count == 0, "non-mods cannot switch scenes");
        Run("mod1", "!scene", "nonsense", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("Usage: !scene")) && CPHProxy.Obs.Count == 0, "unknown scene label is refused");
        Run("mod1", "!scene", "rocket league", true);
        Check(CPHProxy.Obs.Contains("scene:Rocket League"), "!scene switches the OBS scene (case/space insensitive)");
        Check((string)State()["obs"]["scene"] == "Rocket League" && (bool)State()["obs"]["connected"], "the state reports the scene and that OBS is connected");
        Run("mod1", "!source", "off queue overlay", true);
        Check(CPHProxy.Obs.Contains("hide:Rocket League/PinguinoBot Queue") && CPHProxy.Obs.Contains("hide:Fortnite/PinguinoBot Queue"), "a source without a scene is hidden in every scene");
        Check(State()["obs"]["sources"].Any(x => (string)x["label"] == "Queue overlay" && x["visible"].Type == Newtonsoft.Json.Linq.JTokenType.Boolean && !(bool)x["visible"]), "the state shows the source as OFF");
        CPHProxy.Obs.Clear();
        Run("mod1", "!source", "toggle queue overlay", true);
        Check(CPHProxy.Obs.Contains("show:Rocket League/PinguinoBot Queue"), "toggle turns it back on");
        CPHProxy.ObsConnected = false;
        Run("mod1", "!scene", "fortnite", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("Could not switch OBS")), "a failed switch says so (OBS not connected)");
        CPHProxy.ObsConnected = true;
        // auto switch: ON by default: the scene follows the game when a mod starts an activity
        Check((bool)State()["obs"]["auto"], "auto switch is ON by default");
        Check(!((Newtonsoft.Json.Linq.JArray)State()["obs"]["scenes"]).Any(x => (string)x == "Starting Soon" || (string)x == "Be Right Back"), "no Starting Soon / Be Right Back scenes any more");
        CPHProxy.Obs.Clear();
        Run("mod1", "!activity", "boxfights", true);
        Check(CPHProxy.Obs.Contains("scene:Fortnite"), "starting a Fortnite activity while on Rocket League switches to the Fortnite scene");
        CPHProxy.Obs.Clear();
        Run("mod1", "!activity", "zonewars", true);
        Check(!CPHProxy.Obs.Any(x => x.StartsWith("scene:")), "already on the Fortnite scene: no second switch");
        Run("mod1", "!activity", "competitive", true);
        Check(CPHProxy.Obs.Contains("scene:Rocket League"), "starting a Rocket League activity switches back");
        Run("p3", "!obs", "auto off", false);
        Check((bool)State()["obs"]["auto"], "non-mods cannot turn the auto switch off");
        Run("mod1", "!obs", "auto off", true);
        Check(!(bool)State()["obs"]["auto"], "a mod can turn it off");
        CPHProxy.Obs.Clear();
        Run("mod1", "!activity", "boxfights", true);
        Check(!CPHProxy.Obs.Any(x => x.StartsWith("scene:")), "with the auto switch OFF the scene is left alone");
        Run("mod1", "!obs", "auto on", true);
        Run("mod1", "!activity", "end", true);
        Run("mod1", "!activity", "end", true);

        // ---- CASUAL STYLE: group (default) or random teams ----
        Run("mod1", "!activity", "casual", true);
        Check((string)State()["casualStyle"] == "teams", "casual always uses teams");
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6" }) Run(n, "!join");
        CPHProxy.Sent.Clear();
        Run("mod1", "!balance", "", true);
        Check(!(bool)State()["currentMatch"]["group"], "a casual TEAMS match is not a group");
        Check(CPHProxy.Sent.Any(m => m.Contains("Blue [avg")), "casual teams announce Blue / Orange");
        {
            var s = CPHProxy.Sent;
            int ib = s.FindIndex(m => m.StartsWith("#") && m.Contains("Blue [avg"));
            int io = s.FindIndex(m => m.StartsWith("🔶 Orange [avg"));
            Check(ib >= 0 && ib < io, "teams are two plain messages, Blue then Orange: " + string.Join(" | ", s));
            Check(!s.Any(m => m.StartsWith("[announce")), "no announcements");
            Check(!s.Any(m => m.StartsWith("/color")), "no /color text is ever posted in chat");
            Check(!s.Any(m => m.Contains("Blue [avg") && m.Contains("Orange [avg")), "Blue and Orange are separate messages");
        }
        Run("mod1", "!casual", "group", true);
        Check((string)State()["casualStyle"] == "teams", "!casual group is ignored: casual stays on teams");
        Run("mod1", "!activity", "end", true);

        // ---- FORTNITE: Boxfights / Zone Wars customs, SR instead of MMR, own stats ----
        Run("mod1", "!activity", "boxfights", true);
        Check((string)State()["activity"] == "boxfights", "boxfights is an activity");
        Check((string)State()["game"] == "fortnite", "state says the game is fortnite");
        Run("p3", "!setsr", "p1 1500", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("Only mods")), "non-mods cannot set SR");
        Run("mod1", "!setsr", "p1 1500", true);
        Run("mod1", "!setsr", "p2 99999", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("Usage: !setsr")), "bad SR is refused");
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5" }) Run(n, "!join");
        Check(Players()["p1"]["Sr"].ToString() == "1500" && Players()["p1"]["SrSource"].ToString() == "manual", "SR is saved on the player (mod-set)");
        var fq = State()["queue"].Where(x => (string)x["user"] == "p1").FirstOrDefault();
        Check(fq != null && (int)fq["mmr"] == 1500 && (string)fq["mmrSource"] == "mod", "the queue shows SR as the rating in Fortnite");
        int rlWins = Stat("p1", "Wins"), rlPts = Stat("p1", "Points");
        Run("mod1", "!balance", "", true);
        Check(State()["currentMatch"] != null && State()["currentMatch"].Type != Newtonsoft.Json.Linq.JTokenType.Null, "Fortnite teams are made like in Rocket League");
        var fnTeams = State()["currentMatch"]["blue"].Concat(State()["currentMatch"]["orange"]).ToList();
        Check(fnTeams.Any(x => (string)x["Username"] == "p1" && (int)x["Mmr"] == 1500), "balancing uses SR (p1 = 1500)");
        Check(fnTeams.Any(x => (string)x["Username"] != "p1" && (string)x["Username"] != "innocentpenguin_" && (int)x["Mmr"] == 1000), "unrated players default to SR 1000");
        string fnWinner = State()["currentMatch"]["blue"].Any(x => (string)x["Username"] == "p1") ? "blue" : "orange";
        Run("mod1", "!win", fnWinner, true);
        Check(Mode("p1", "boxfights", "Wins") == 1 && Mode("p1", "boxfights", "Points") == 3, "a boxfights win counts under boxfights");
        Check(Stat("p1", "Wins") == rlWins && Stat("p1", "Points") == rlPts, "...and does not touch the Rocket League wins/points");
        Run("mod1", "!activity", "zonewars", true);
        Check((string)State()["activity"] == "zonewars", "zone wars is an activity");
        Run("mod1", "!activity", "fnviewers", true);
        Check((string)State()["game"] == "fortnite", "fortnite playing with viewers is a fortnite activity");
        Run("mod1", "!activity", "competitive", true);
        Check((string)State()["game"] == "rocket-league", "back to Rocket League: MMR again");
        Run("mod1", "!activity", "end", true);

        // ---- STRIKES ----
        Run("mod1", "!activity", "competitive", true);
        Run("p1", "!join");
        Check(Q().Contains("p1"), "p1 is in the queue before any strikes");
        Run("p3", "!strike", "@p1", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("Only mods")) && Players()["p1"]["Strikes"].ToString() == "0", "non-mods cannot give strikes");
        Run("mod1", "!strike", "@p1", true);
        Run("mod1", "!strike", "@p1", true);
        Check(Players()["p1"]["Strikes"].ToString() == "2", "a mod gives strikes");
        Run("mod1", "!strike", "@p1", true);
        Check(Players()["p1"]["Strikes"].ToString() == "3" && !Q().Contains("p1"), "3 strikes also takes them out of the queue");
        Run("mod1", "!strike", "@p1", true);
        Check(Players()["p1"]["Strikes"].ToString() == "3" && CPHProxy.Sent.Any(m => m.Contains("maximum")), "strikes never go above 3");
        Run("p1", "!join");
        Check(!Q().Contains("p1") && CPHProxy.Sent.Any(m => m.Contains("3 strikes")), "3 strikes = can't join");
        Run("p1", "!strikes");
        Check(CPHProxy.Sent.Any(m => m.Contains("3/3")), "!strikes shows the count");
        Run("mod1", "!unstrike", "@p1", true);
        Run("p1", "!join");
        Check(Players()["p1"]["Strikes"].ToString() == "2" && Q().Contains("p1"), "removing a strike lets them join again");
        Run("mod1", "!unstrike", "@p2", true);
        Check(Players()["p2"]["Strikes"].ToString() == "0" && CPHProxy.Sent.Any(m => m.Contains("no strikes")), "strikes never go below 0");
        Run("mod1", "!strike", "@p2 half", true);
        Check(Players()["p2"]["HalfStrike"].ToString() == "1" && Players()["p2"]["Strikes"].ToString() == "0" && CPHProxy.Sent.Any(m => m.Contains("Half strike given")), "a half strike is not yet a full strike");
        Run("mod1", "!strike", "@p2 half", true);
        Check(Players()["p2"]["HalfStrike"].ToString() == "0" && Players()["p2"]["Strikes"].ToString() == "1", "two half strikes make one strike");
        Run("mod1", "!strike", "@p2 half", true); Run("mod1", "!unstrike", "@p2 half", true);
        Check(Players()["p2"]["HalfStrike"].ToString() == "0" && Players()["p2"]["Strikes"].ToString() == "1", "!unstrike half takes the half back");
        Run("mod1", "!unstrike", "@p2", true);
        Check(Players()["p2"]["Strikes"].ToString() == "0", "back to zero");
        var decay = typeof(CPHInline).GetMethod("DecayStrikes", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        long dayLater = DateTimeOffset.UtcNow.ToUnixTimeSeconds() + 86400 + 30;
        decay.Invoke(bot, new object[] { dayLater });
        Check(Players()["p1"]["Strikes"].ToString() == "1", "a temporary strike wears off after a day");
        decay.Invoke(bot, new object[] { dayLater + 60 });
        Check(Players()["p1"]["Strikes"].ToString() == "1", "only one per day");
        decay.Invoke(bot, new object[] { dayLater + 86400 });
        Check(Players()["p1"]["Strikes"].ToString() == "0", "the next day takes the last one");
        Run("mod1", "!strike", "@p1", true);
        Run("mod1", "!strike", "@p1 toxicity", true);
        Check(Players()["p1"]["Strikes"].ToString() == "1" && Players()["p1"]["PermaStrikes"].ToString() == "1" && CPHProxy.Sent.Any(m => m.Contains("Permanent strike given to p1")), "a toxicity strike is permanent");
        decay.Invoke(bot, new object[] { dayLater + 30L * 86400 });
        Check(Players()["p1"]["Strikes"].ToString() == "0" && Players()["p1"]["PermaStrikes"].ToString() == "1", "permanent strikes never wear off");
        Run("p1", "!strikes");
        Check(CPHProxy.Sent.Any(m => m.Contains("1/3 strikes (1 permanent, 0 temporary)")), "!strikes tells the two kinds apart");
        Run("mod1", "!unstrike", "@p1", true);
        Check(Players()["p1"]["PermaStrikes"].ToString() == "1" && CPHProxy.Sent.Any(m => m.Contains("only has permanent strikes")), "!unstrike alone does not remove a permanent strike");
        Run("mod1", "!unstrike", "@p1 perma", true);
        Check(Players()["p1"]["PermaStrikes"].ToString() == "0", "!unstrike @user perma removes one");
        Run("mod1", "!strike", "@p1", true);   // back to 1 temporary like before
        Run("mod1", "!strike", "@p1 slurs", true); Run("mod1", "!strike", "@p1 racist", true);
        Check(Players()["p1"]["Strikes"].ToString() == "1" && Players()["p1"]["PermaStrikes"].ToString() == "2" && !Q().Contains("p1"), "2 permanent + 1 temporary = 3: out of the queue");
        Run("mod1", "!unstrike", "@p1 perma", true); Run("mod1", "!unstrike", "@p1 perma", true);
        Run("mod1", "!activity", "end", true);

        // ---- KOTH + !finish ----
        var holdUntil = typeof(CPHInline).GetField("_holdUntil", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
        Run("mod1", "!activity", "competitive", true);
        Check(!(bool)State()["koth"], "KOTH is off by default");
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        var fMatch = State()["currentMatch"]; var fOrange = Team("orange"); var fBlue = Team("blue");
        Run("p1", "!finish", "orange", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("Only mods")), "non-mods cannot finish a match");
        Run("mod1", "!finish", "green", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("Usage: !finish")), "bad team refused");
        Run("mod1", "!finish", "orange", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("wins match")), "!finish records the result");
        Check(State()["currentMatch"].Type != Newtonsoft.Json.Linq.JTokenType.Null && (string)State()["currentMatch"]["status"] == "finished" && (string)State()["currentMatch"]["winner"] == "orange", "the website/OBS still show the finished match with the winner during the hold");
        Check((bool)State()["hold"] && State()["liveMatch"].Type == Newtonsoft.Json.Linq.JTokenType.Null, "meanwhile the real state (mod view) is already clear: KOTH off removes everybody");
        Check(!Q().Any(x => fOrange.Concat(fBlue).Contains(x) && x != "innocentpenguin_"), "KOTH off: everyone who played is out of the queue");
        holdUntil.SetValue(null, 0L);
        Run("mod1", "!koth", "off", true);   // publishes the state again; the hold has run out
        Check(!(bool)State()["hold"] && State()["currentMatch"].Type == Newtonsoft.Json.Linq.JTokenType.Null, "after the hold the public state is clear too");
        Run("p3", "!koth", "on", false);
        Check(!(bool)State()["koth"], "non-mods cannot turn KOTH on");
        Run("mod1", "!koth", "on", true);
        Check((bool)State()["koth"], "a mod can turn KOTH on");
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        var kBlue = Team("blue");
        var kOrange = Team("orange");
        Run("mod1", "!finish", "blue", true);
        Check((bool)State()["hold"] && (string)State()["currentMatch"]["status"] == "finished" && (string)State()["currentMatch"]["winner"] == "blue", "KOTH on: the public view holds the finished match too");
        Check((string)State()["liveMatch"]["status"] == "live", "KOTH on: the mod view moves on to the next match at once");
        var kNextBlue = State()["liveMatch"]["blue"].Select(x => (string)x["Username"]).ToArray();
        var kNextOrange = State()["liveMatch"]["orange"].Select(x => (string)x["Username"]).ToArray();
        Check(kBlue.All(x => kNextBlue.Contains(x)), "KOTH on: the winners stay together on Blue");
        Check(kOrange.All(x => Q().Contains(x)), "KOTH on: the losers are recycled to the back of the queue (nobody has to !join again)");
        Check(!kNextOrange.Any(x => kBlue.Contains(x)), "KOTH on: the losers are replaced by challengers");
        Run("mod1", "!koth", "off", true);
        Run("mod1", "!activity", "end", true);

        // ---- KING OF THE HILL (the activity) ----
        holdUntil.SetValue(null, 0L);   // the previous test left a finished match on hold
        Run("mod1", "!activity", "koth", true);
        Check((string)State()["activity"] == "koth" && (bool)State()["queueOpen"], "King of the Hill opens the queue for everyone");
        Check((bool)State()["koth"], "the King of the Hill activity is KOTH mode");
        foreach (var n in new[] { "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10" }) Run(n, "!join");
        int kWinsBefore = Stat("p1", "Wins"), kPtsBefore = Stat("p1", "Points");
        Run("mod1", "!balance", "", true);
        Check(!(bool)State()["queueOpen"], "the first game being picked CLOSES the queue");
        Check(CPHProxy.Sent.Any(m => m.Contains("KING OF THE HILL IS STARTING") && m.Contains("picked by mod1") && m.Contains("@")), "it warns who is starting the game: " + string.Join(" | ", CPHProxy.Sent));
        Run("p11", "!join");
        Check(CPHProxy.Sent.Any(m => m.Contains("closed")), "nobody can join after the first game");
        var kaBlue = Team("blue");
        Run("mod1", "!finish", "blue", true);
        Check(State()["liveMatch"]["blue"].Select(x => (string)x["Username"]).Intersect(kaBlue).Count() == kaBlue.Length, "King of the Hill: winners stay on without turning KOTH on");
        var kaWinner = kaBlue.First(x => x != "innocentpenguin_");
        Check(Mode(kaWinner, "koth", "Wins") == 1, "a King of the Hill win counts on its own leaderboard (" + kaWinner + ")");
        Check(Stat("p1", "Wins") == kWinsBefore && Stat("p1", "Points") == kPtsBefore, "...and does not touch the overall Rocket League wins / points");
        Run("mod1", "!activity", "end", true);

        // ---- PROBLEMS (shown in red on the website log) + !check ----
        var probs = (System.Collections.Generic.List<string>)typeof(CPHInline).GetField("_problems", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static).GetValue(null);
        probs.Clear();
        Run("p1", "!bogusthing");
        Check(probs.Any(x => x.Contains("Unknown command") && x.Contains("!bogusthing")), "an unknown command is reported as a problem: " + string.Join(" | ", probs));
        Run("p1", "!check", "", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("Only mods")), "non-mods cannot run !check");
        probs.Clear();
        Run("mod1", "!activity", "none", true);
        Run("mod1", "!check", "", true);
        Check(CPHProxy.Sent.Any(m => m.Contains("Check")), "!check answers in chat: " + string.Join(" | ", CPHProxy.Sent));
        Check(probs.Any(x => x.StartsWith("Check:")), "!check reports what is wrong as problems (the stub has no website): " + string.Join(" | ", probs));
        {   // problems.json: every problem + check result is kept in a file that can be edited / cleared
            string pf = System.IO.Path.Combine(Environment.GetEnvironmentVariable("PINGUINO_DATA_DIR"), "problems.json");
            string txt = System.IO.File.Exists(pf) ? System.IO.File.ReadAllText(pf) : "";
            Check(txt.Contains("\"Kind\": \"check\"") && txt.Contains("\"Status\": \"open\""), "problems.json lists the open check problems: " + txt.Length);
            Run("mod1", "!problems", "", true);
            Check(CPHProxy.Sent.Any(m => m.Contains("open problem")), "!problems shows the open count");
            Run("p1", "!problems", "clear", false);
            Check(System.IO.File.ReadAllText(pf).Contains("Check:"), "non-mods cannot clear the problem list");
            Run("mod1", "!problems", "clear", true);
            Check(System.IO.File.ReadAllText(pf).Trim().Length <= 4, "!problems clear empties problems.json: " + System.IO.File.ReadAllText(pf));
        }
        CPHProxy.ObsConnected = false;
        probs.Clear();
        Run("mod1", "!scene", "Rocket League", true);
        CPHProxy.ObsConnected = true;
        Check(probs.Any(x => x.Contains("OBS")), "a failed OBS switch is a problem: " + string.Join(" | ", probs));

        // ---- !activity rl|fn <activity>: the game prefix also switches the scene and the Twitch category ----
        Run("mod1", "!obs", "auto off", true);
        CPHProxy.Obs.Clear(); CPHProxy.Games.Clear();
        Run("mod1", "!activity", "fn boxfights", true);
        Check((string)State()["activity"] == "boxfights" && (string)State()["game"] == "fortnite", "!activity fn boxfights starts Fortnite Boxfights");
        Check(CPHProxy.Obs.Contains("scene:Fortnite"), "the prefix switches the OBS scene even with the auto switch OFF");
        Check(CPHProxy.Games.Contains("Fortnite"), "...and sets the Twitch category to Fortnite");
        CPHProxy.Games.Clear();
        Run("mod1", "!activity", "fn viewers", true);
        Check((string)State()["activity"] == "fnviewers", "!activity fn viewers = Fortnite playing with viewers");
        Check(CPHProxy.Games.Count == 0, "same game: the category isn't set again");
        Run("mod1", "!activity", "rl viewers", true);
        Check((string)State()["activity"] == "viewers" && CPHProxy.Games.Contains("Rocket League") && CPHProxy.Obs.Contains("scene:Rocket League"), "!activity rl viewers goes back to Rocket League (scene + category)");
        Run("mod1", "!activity", "fn koth", true);
        Check((string)State()["activity"] == "viewers" && CPHProxy.Sent.Any(m => m.Contains("Usage: !activity rl")), "a Rocket League activity with the fn prefix is refused");
        Run("mod1", "!activity", "rl boxfights", true);
        Check((string)State()["activity"] == "viewers", "a Fortnite activity with the rl prefix is refused");
        Run("mod1", "!activity", "koth", true);
        Check((string)State()["activity"] == "koth", "no prefix still works");
        Run("mod1", "!activity", "rl end", true);
        Check((string)State()["activity"] == "none", "!activity rl end ends it");
        CPHProxy.Games.Clear(); CPHProxy.GameOk = false; probs.Clear();
        Run("mod1", "!activity", "fn zonewars", true);
        CPHProxy.GameOk = true;
        Check(probs.Any(x => x.Contains("Twitch category")), "a failed category change is a problem (red in the log)");
        Run("mod1", "!activity", "end", true);
        Run("mod1", "!obs", "auto on", true);

        // ===== [NEW][WHEEL] tournament wheel: picks are made live, one per spin =====
        Func<JObject> WS = () => JObject.Parse(File.ReadAllText(Path.Combine(dir, "wheel_session.json")));
        Func<string, JObject> priv = name => JObject.FromObject(typeof(CPHInline).GetMethod(name, System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance).Invoke(bot, null));
        Func<string, int, string[]> signUp = (prefix, n) => { var l = new System.Collections.Generic.List<string>(); for (int i = 1; i <= n; i++) { l.Add(prefix + i); Run(prefix + i, "!me"); } return l.ToArray(); };
        var wlog = new System.Collections.Generic.List<string>();
        Action<string, string> wheel = (sub, arg) => { Run("mod1", "!wheel", (sub + " " + arg).Trim(), true); wlog.AddRange(CPHProxy.Sent); };
        Action<int> fresh = size => { wheel("end", ""); wheel("new", ""); wheel("size", size.ToString()); wheel("auto", "off"); };
        Action spinAll = () => { for (int i = 0; i < 80 && !(bool)WS()["Final"]; i++) wheel("spin", ""); };
        var stepField = typeof(CPHInline).GetField("_wheelStepMs", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);

        Run("p1", "!wheel", "new");
        Check(CPHProxy.Sent.Any(m => m.Contains("only mods")), "wheel: non-mods cannot run !wheel");
        Run("p2", "!me");
        Check(CPHProxy.Sent.Any(m => m.Contains("closed")), "wheel: !me with no session says sign-ups are closed");

        fresh(2);
        signUp("w", 6);
        Run("w1", "!me");
        Check(WS()["Entrants"].Count() == 6, "wheel: !me twice by the same viewer counts once");
        wheel("close", "");
        Run("late1", "!me");
        Check(WS()["Entrants"].Count() == 6 && CPHProxy.Sent.Any(m => m.Contains("closed")), "wheel: nobody can join after sign-ups close");
        wheel("open", "");
        wheel("eligibility", "subs");
        Run("late2", "!me");
        Check(WS()["Entrants"].Count() == 6 && CPHProxy.Sent.Any(m => m.Contains("subscribers")), "wheel: subs-only refuses non-subs");
        wheel("eligibility", "all");

        // strikes: 3 strikes cannot join, and are dropped when the round starts
        int sNow = int.Parse(Players()["p3"]["Strikes"].ToString());
        for (int i = sNow; i < 3; i++) Run("mod1", "!strike", "@p3", true);
        Run("p3", "!me");
        Check(WS()["Entrants"].Count() == 6 && CPHProxy.Sent.Any(m => m.Contains("3 strikes, so you can't join the tournament")), "wheel: a player with 3 strikes cannot join");
        Run("mod1", "!unstrike", "@p3", true);
        Run("p3", "!me");
        Check(WS()["Entrants"].Count() == 7, "wheel: after losing a strike they can join");
        Run("mod1", "!strike", "@p3", true);
        wheel("spin", "");
        Check((string)WS()["Status"] == "open" && WS()["Entrants"].Count() == 6 && CPHProxy.Sent.Any(m => m.Contains("Removed from the tournament")), "wheel: a 3-strike entrant is removed at the first spin, no pick yet");
        Run("mod1", "!unstrike", "@p1", true);

        wlog.Clear();
        // live picks: ONE pick exists after ONE spin, nothing about later picks exists anywhere
        wheel("spin", "");
        var ws = WS();
        Check((string)ws["Status"] == "drawing" && ws["Picks"].Count() == 1, "wheel: one spin = exactly one pick");
        Check(ws["Teams"].Sum(t => t["Members"].Count()) == 1 && ws["Msgs"].Count() == 0, "wheel: after the first pick there is one team member and nothing queued");
        var snap = priv("WheelSnapshot");
        Check((string)snap["status"] == "spinning" && snap["finalTeams"].Count() == 0 && snap["queue"].Count() == 6 && snap["waitlist"].Count() == 0 && snap["picks"] == null && snap["teams"] == null, "wheel: the site snapshot has only queue + status while drawing: " + snap.ToString(Newtonsoft.Json.Formatting.None));
        wheel("mode", "balanced");
        Check(CPHProxy.Sent.Any(m => m.Contains("round is running")), "wheel: mode can't change mid-round");
        wheel("spin", "");
        wheel("spin", "");
        wheel("spin", "");
        ws = WS();
        Check((string)ws["Status"] == "drawing" && ws["Picks"].Count() == 4 && !(bool)ws["Final"], "wheel: four spins = four picks, still drawing");
        wheel("spin", "");   // the 5th spin places the last two (the last entrant needs no spin of their own)
        ws = WS();
        Check((bool)ws["Final"] && (string)ws["Status"] == "drawn" && ws["Picks"].Count() == 6 && ws["Teams"].Count() == 3, "wheel: the last spin lands 2 picks and finalizes: 3 teams");
        var all = ws["Teams"].SelectMany(t => t["Members"]).Select(x => (string)x).ToArray();
        Check(all.Length == 6 && all.Distinct().Count() == 6, "wheel: every player is in exactly one team");
        snap = priv("WheelSnapshot");
        Check((string)snap["status"] == "final" && snap["finalTeams"].Count() == 3, "wheel: the site gets final teams only after the last reveal");
        var said = wlog.ToList();
        Check(said.Count(m => m.StartsWith("Team ")) == 3 && said.Any(m => m.Contains("TOURNAMENT TEAMS")) && said.All(m => m.Length <= 450), "wheel: one line per team plus the roster paragraph, each under 450 chars");
        Check((string)WS()["AnnState"] == "done", "wheel: announcements done");
        wheel("tick", ""); wheel("tick", "");
        Check(CPHProxy.Sent.Count == 0, "wheel: nothing is sent twice");
        wheel("spin", "");
        Check(CPHProxy.Sent.Any(m => m.Contains("finished")), "wheel: spinning a finished round is refused");

        // seeded determinism of the PRNG (private type, by reflection)
        var rt = typeof(CPHInline).GetNestedType("WheelRng", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public);
        Func<string, string> seq = seed => { var r = Activator.CreateInstance(rt, new object[] { seed }); var m = rt.GetMethod("Below"); return string.Join(",", Enumerable.Range(0, 20).Select(i => m.Invoke(r, new object[] { 1000 }))); };
        Check(seq("abc") == seq("abc") && seq("abc") != seq("abd"), "wheel: same seed = same sequence, different seed differs");

        // a new round: the placed leave, late joiners stay, !me works during the hold
        Run("latecomer", "!me");
        wheel("new", "");
        ws = WS();
        Check((string)ws["Status"] == "open" && ws["Picks"].Count() == 0 && ws["Teams"].Count() == 0 && ws["Entrants"].Count() == 1 && (int)ws["Round"] == 1, "wheel: !wheel new opens the next round, the late joiner is waiting");

        // overlay timing: with a real spin time the chat line waits until the pick has landed
        stepField.SetValue(null, 1500);
        fresh(2); signUp("o", 2);
        wheel("spin", "");
        Check(!(bool)WS()["Final"] && !CPHProxy.Sent.Any(m => m.StartsWith("Team ")), "wheel timing: nothing is announced while the wheel is still turning");
        var pub = priv("WheelPublic");
        Check((string)pub["status"] == "drawing" && pub["spin"]["landing"].Count() == 2, "wheel timing: the overlay file carries the landing pick(s)");
        wheel("spin", "");
        Check(WS()["Picks"].Count() == 2, "wheel timing: a spin pressed while turning is ignored");
        stepField.SetValue(null, 1);

        // join / leave at any time, including mid-round
        fresh(2); signUp("x", 4);
        wheel("spin", "");
        string firstPick = (string)WS()["Picks"][0]["Login"];
        Run(firstPick, "!notme");
        ws = WS();
        Check(ws["Picks"].Count() == 0 && ws["Entrants"].Count() == 3 && CPHProxy.Sent.Any(m => m.Contains("off the wheel")), "wheel: leaving mid-round removes their pick; the wheel text is separate from the queue text");
        Run("xjoin", "!me");
        Check(WS()["Entrants"].Count() == 4, "wheel: joining mid-round works");
        spinAll();
        ws = WS();
        Check((bool)ws["Final"] && ws["Teams"].Count() == 2 && ws["Teams"].All(t => t["Members"].Count() == 2), "wheel: join + leave mid-round still finishes with full teams");
        // someone leaves after the teams are final: the first waiting player takes the slot
        fresh(2); signUp("y", 5);
        spinAll();
        ws = WS();
        Check((bool)ws["Final"] && ws["Waitlist"].Count() == 1, "wheel: 5 players -> 2 teams + 1 on the waitlist");
        string leaver = (string)ws["Picks"][0]["Login"];
        wlog.Clear();
        Run("zz1", "!not", "me"); Run(leaver, "!notme."); wheel("tick", "");
        ws = WS();
        Check(ws["Teams"].All(t => t["Members"].Count() == 2) && ws["Waitlist"].Count() == 0 && wlog.Any(m => m.Contains("takes the spot")), "wheel: a leaver after the draw is replaced from the waitlist");

        // automatic new round after the hold
        fresh(2); wheel("auto", "on"); wheel("hold", "0"); signUp("z", 2);
        spinAll();
        wheel("tick", ""); wheel("tick", "");
        ws = WS();
        Check((string)ws["Status"] == "open" && ws["Picks"].Count() == 0 && (int)ws["Round"] >= 1, "wheel: a new round opens by itself after the finished round");
        wheel("auto", "off");

        // odd policies
        fresh(2); signUp("o", 5); spinAll();
        ws = WS();
        Check(ws["Teams"].Count() == 2 && ws["Waitlist"].Count() == 1, "wheel: odd=waitlist -> 2 teams + 1 waiting");
        fresh(2); wheel("odd", "trio"); signUp("o", 5); spinAll();
        ws = WS();
        Check(ws["Teams"].Count() == 2 && ws["Teams"].Select(t => t["Members"].Count()).OrderBy(x => x).SequenceEqual(new[] { 2, 3 }) && ws["Waitlist"].Count() == 0, "wheel: odd=trio -> a team of 3, nobody waits");
        fresh(2); wheel("odd", "partial"); signUp("o", 5); spinAll();
        ws = WS();
        Check(ws["Teams"].Count() == 3 && ws["Teams"].Count(t => (bool)t["Partial"]) == 1, "wheel: odd=partial -> an extra partial team");
        fresh(2); wheel("odd", "hold"); signUp("o", 5); wheel("spin", "");
        Check((string)WS()["Status"] == "open" && CPHProxy.Sent.Any(m => m.Contains("more")), "wheel: odd=hold refuses to spin");

        // balanced: teams form at the last reveal
        fresh(2); wheel("mode", "balanced"); signUp("b", 4);
        wheel("mmr", "b1 2000"); wheel("mmr", "b2 1000"); wheel("mmr", "b3 1900"); wheel("mmr", "b4 1100");
        wheel("spin", "");
        Check(WS()["Teams"].Count() == 0 && WS()["Picks"].Count() == 1, "wheel balanced: no teams exist until the last pick");
        spinAll();
        ws = WS();
        Check(ws["Teams"].Count() == 2 && (int)ws["Teams"][0]["Avg"] == (int)ws["Teams"][1]["Avg"], "wheel balanced: 2000/1000/1900/1100 split into equal averages");

        // roster paragraphs split under 450 characters
        fresh(1); for (int i = 1; i <= 60; i++) Run("averyveryverylongtwitchname" + i, "!me");
        spinAll(); wheel("announce", "");
        Check(CPHProxy.Sent.Count(m => m.StartsWith("TOURNAMENT TEAMS")) >= 3 && CPHProxy.Sent.All(m => m.Length <= 450), "wheel: a long roster splits into paragraphs under 450 characters");
        wheel("end", "");

        // ===== [NEW][PRACTICE] fake players: used by matchmaking and the wheel, never saved =====
        Func<string, bool> onDisk = needle => new[] { "players.json", "queue.json", "matches.json", "current_match.json", "wheel_session.json" }
            .Any(f => File.Exists(Path.Combine(dir, f)) && File.ReadAllText(Path.Combine(dir, f)).Contains(needle));
        Func<JToken> LiveM = () => (bool)State()["hold"] ? State()["liveMatch"] : State()["currentMatch"];
        Run("p1", "!practice", "on", false);
        Check(CPHProxy.Sent.Any(m => m.Contains("Only mods can use !practice")), "practice: non-mods cannot start it");
        Run("mod1", "!queue", "clear", true);
        Run("mod1", "!format", "2v2", true);
        fresh(2); signUp("real", 2);
        Run("mod1", "!practice", "on 6", true);
        Check(State()["queue"].Count(q => (bool)q["practice"]) == 6 && (bool)State()["practice"], "practice: 6 fake players fill the queue and the state flags them");
        Check(!onDisk("practice0"), "practice: no fake player reaches players/queue/wheel files");
        Check(WS()["Entrants"].Count() == 2, "practice: the saved wheel sign-ups hold only the real viewers");
        wheel("spin", "");
        Check(WS()["Status"].ToString() == "open", "practice: a practice spin is not written to the wheel file");
        Run("mod1", "!next", "", true);
        Check(LiveM()["blue"].Concat(LiveM()["orange"]).All(p => (bool)p["Practice"] == ((string)p["Username"]).StartsWith("practice")) && LiveM()["blue"].Concat(LiveM()["orange"]).Any(p => (bool)p["Practice"]), "practice: matchmaking used fake players and flags exactly them");
        Check(!onDisk("practice0"), "practice: the practice lobby is not saved");
        Run("mod1", "!win", "blue", true);
        Check(!onDisk("practice0") && JObject.Parse(File.ReadAllText(Path.Combine(dir, "players.json"))).Properties().All(pr => (int)pr.Value["Wins"] == 0 || !pr.Name.StartsWith("practice")), "practice: a practice result changes no stats");
        Run("mod1", "!practice", "off", true);
        Check(State()["queue"].Count(q => (bool)q["practice"]) == 0 && !(bool)State()["practice"], "practice: off removes the fake players");
        wheel("close", "");
        Check(WS()["Entrants"].Count() == 2 && !onDisk("practice0"), "practice: after off the real wheel sign-ups are back");
        wheel("end", "");

        // ===== [NEW] recycler, !incomplete, inactivity timeout =====
        Run("mod1", "!activity", "competitive", true);
        Run("mod1", "!queue", "clear", true); Run("mod1", "!queue", "open", true);
        Run("mod1", "!format", "2v2", true); Run("mod1", "!streamer", "out", true);
        for (int i = 1; i <= 5; i++) Run("rc" + i, "!register", "epicrc" + i);
        Run("rc1", "!recycle", "on"); Run("rc2", "!recycle", "on");
        Check(Players()["rc1"]["Recycler"].ToString() == "True", "recycler: !recycle on sets the flag");
        Run("rc3", "!recycle", "on", false); Run("rc3", "!recycle", "off");
        foreach (var n in new[] { "rc1", "rc2", "rc3", "rc4" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        Check(State()["currentMatch"] != null && State()["currentMatch"].Type != Newtonsoft.Json.Linq.JTokenType.Null, "recycler test: a 2v2 game is live");
        Run("mod1", "!incomplete", "", true);
        Check((string)State()["currentMatch"]["status"] == "incomplete", "incomplete: the match shows status incomplete");
        Check(Q().OrderBy(x => x).SequenceEqual(new[] { "rc1", "rc2" }) && State()["queue"].All(q => (bool)q["recycle"]), "incomplete: only the recycler players are back, with the recycle marker: " + string.Join(",", Q()));
        var mjs = JArray.Parse(File.ReadAllText(Path.Combine(dir, "matches.json"))).Last;
        Check((bool)mjs["Incomplete"] && mjs["Winner"].Type == Newtonsoft.Json.Linq.JTokenType.Null && Players()["rc4"]["Wins"].ToString() == "0" && Players()["rc4"]["Losses"].ToString() == "0", "incomplete: no winner and no wins/losses recorded");
        Run("rc1", "!join");
        Check(CPHProxy.Sent.Any(m => m.Contains("already in the queue")), "recycler: a recycled player is simply in the queue");
        // any strike ends recycling
        Run("mod1", "!strike", "@rc1", true);
        Check(!Q().Contains("rc1") && Players()["rc1"]["Recycler"].ToString() == "False", "recycler: a strike removes the player from the recycler queue and turns the flag off");
        Run("rc1", "!recycle", "on");
        Check(Players()["rc1"]["Recycler"].ToString() == "False" && CPHProxy.Sent.Any(m => m.Contains("strike")), "recycler: with a strike the recycler can't be turned on");
        Run("mod1", "!unstrike", "@rc1", true);
        // a normal finished game: the recycler player comes back, the others leave
        foreach (var n in new[] { "rc3", "rc4", "rc5" }) Run(n, "!join");
        Run("mod1", "!balance", "", true);
        var rcPlayers = Team("blue").Concat(Team("orange")).ToList();
        Run("mod1", "!win", "blue", true);
        Check(Q().Contains("rc2") && State()["queue"].First(q => (string)q["user"] == "rc2")["recycle"].ToString() == "True" && !Q().Contains("rc3") && !Q().Contains("rc5"), "recycler: after a win only the recycler player is queued again: " + string.Join(",", Q()));
        Run("rc2", "!leave");
        Check(!Q().Contains("rc2") && Players()["rc2"]["Recycler"].ToString() == "False", "recycler: !leave removes the player and ends recycling");
        // inactivity timeout
        var botT = typeof(CPHInline);
        var setF = botT.GetField("_settings", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        var actF = botT.GetField("_lastCustomsActivity", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
        Run("mod1", "!queue", "open", true);
        var idleM = botT.GetMethod("CustomsIdleTick", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        idleM.Invoke(bot, null);
        Check((bool)State()["queueOpen"] && !(bool)State()["timedOut"], "timeout: a fresh queue is not closed");
        actF.SetValue(null, 1L);
        CPHProxy.Sent.Clear();
        idleM.Invoke(bot, null);
        Check(!(bool)State()["queueOpen"] && (bool)State()["timedOut"] && (long)State()["timedOutAt"] > 0 && CPHProxy.Sent.Count == 1 && CPHProxy.Sent[0].Contains("15 minutes"), "timeout: idle customs close after 15 minutes with ONE chat line: " + string.Join("|", CPHProxy.Sent));
        Run("mod1", "!queue", "open", true);
        Check((bool)State()["queueOpen"] && !(bool)State()["timedOut"], "timeout: opening the queue clears the timed-out flag");
        Run("mod1", "!streamer", "in", true);
        { var qBefore = Q(); Run("curious", "!next");
          Check(CPHProxy.Sent.Count == 1 && CPHProxy.Sent[0].StartsWith("@curious ") && !CPHProxy.Sent[0].Contains("Only mods") && (CPHProxy.Sent[0].Contains("Next up") || CPHProxy.Sent[0].Contains("queue is empty")) && Q().SequenceEqual(qBefore), "a viewer's !next is a short read-only 'who is next' line and never advances the queue: " + string.Join("|", CPHProxy.Sent)); }
        Console.WriteLine(failed == 0 ? "ALL BOT CHECKS PASSED" : failed + " BOT CHECK(S) FAILED");
        try { Directory.Delete(dir, true); } catch { }
        return failed == 0 ? 0 : 1;
    }
}
