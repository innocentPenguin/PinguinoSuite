// ══════════════════════════════════════════════════════════════════════
//  PinguinoBotFirsts — one Streamer.bot C# action for the "First 5" game
//
//  Replaces 3 separate actions:
//    1. Personal record command   (e.g. !firsts)       -> ShowUserRecord
//    2. Leaderboard command       (e.g. !firstsboard)  -> ShowLeaderboard
//    3. Chat Message trigger      (every chat line)    -> HandleChatMessage
//
//  SETUP: point all 3 triggers at this one action. How it decides what to do:
//    - Triggered by a command whose name is in LeaderboardCommands -> leaderboard
//    - Triggered by any other command                              -> user's record
//    - Triggered by a chat message (no "command" arg)              -> first-chatter claim
//  Put YOUR leaderboard command name(s) in LeaderboardCommands below.
//
//  ⚠ QUEUE: the payout uses CPH.Wait for 25 minutes in total. Keep this action
//  on a NON-blocking queue (the default), NOT on PinguinoBot's blocking queue,
//  or it will freeze the matchmaking commands for 25 minutes.
// ══════════════════════════════════════════════════════════════════════

using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;

public class CPHInline
{
    // ── Settings ────────────────────────────────────────────────────
    // Never the same line twice: shares the record "pinguino.said.recent" with the other bots (30 s window).
    void Say(string msg)
    {
        try
        {
            string n = System.Text.RegularExpressions.Regex.Replace((msg ?? "").ToLowerInvariant(), @"\s+", " ").Trim();
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); var keep = new List<string>(); bool dup = false;
            foreach (string row in (CPH.GetGlobalVar<string>("pinguino.said.recent", false) ?? "").Split(new[] { '\n' },StringSplitOptions.RemoveEmptyEntries))
            {
                int bar = row.IndexOf('|'); long t; if (bar < 1 || !long.TryParse(row.Substring(0, bar), out t) || now - t > 30) continue;
                if (row.Substring(bar + 1) == n) dup = true;
                keep.Add(row);
            }
            if (dup) return;
            keep.Add(now + "|" + n); if (keep.Count > 40) keep.RemoveRange(0, keep.Count - 40);
            CPH.SetGlobalVar("pinguino.said.recent", string.Join("\n", keep), false);
        }
        catch (Exception) { }
        CPH.SendMessage(msg);
    }

    static readonly string[] LeaderboardCommands = { "!firsts" };   // !first = your own record, !firsts = leaderboard

    static readonly string[] IgnoredBots = { "sery_bot", "soundalerts", "pinguinob0t", "streamelements", "nightbot" };

    // Global var names, in place order (1st..5th). Unchanged from the old actions, so existing stats carry over.
    static readonly string[] PlaceStatVars =
        { "firstPlaceStats", "secondPlaceStats", "thirdPlaceStats", "fourthPlaceStats", "fifthPlaceStats" };

    static readonly string[] PlaceLabels = { "🥇", "🥈", "🥉", "4th:", "5th:" };

    static readonly int[] PlacePoints = { 15000, 10500, 7500, 4500, 3000 };

    const int PayoutDelayMs = 5 * 60 * 1000;

    // ── Entry point ─────────────────────────────────────────────────
    public bool Execute()
    {
        string command = CPH.TryGetArg("command", out string cmdArg) && cmdArg != null ? cmdArg.ToLower() : "";

        if (string.IsNullOrEmpty(command))
            return HandleChatMessage();

        if (LeaderboardCommands.Contains(command))
            return ShowLeaderboard();

        return ShowUserRecord();
    }

    // ── 1. Personal record ──────────────────────────────────────────
    bool ShowUserRecord()
    {
        string username = GetArg("user");
        if (string.IsNullOrWhiteSpace(username))
            return true;

        string key = username.ToLower();
        int[] counts = PlaceStatVars.Select(v =>
        {
            var stats = LoadStats(v);
            return stats.ContainsKey(key) ? stats[key] : 0;
        }).ToArray();

        Say($"{username}'s First Record: 🥇 {counts[0]} | 🥈 {counts[1]} | 🥉 {counts[2]} | 4th: {counts[3]} | 5th: {counts[4]} | Total: {counts.Sum()}");
        return true;
    }

    // ── 2. Leaderboard ──────────────────────────────────────────────
    bool ShowLeaderboard()
    {
        var totals = new Dictionary<string, int>();
        foreach (string v in PlaceStatVars)
        {
            foreach (var item in LoadStats(v))
            {
                if (string.IsNullOrWhiteSpace(item.Key))
                    continue;
                totals[item.Key] = (totals.ContainsKey(item.Key) ? totals[item.Key] : 0) + item.Value;
            }
        }

        if (totals.Count == 0)
        {
            Say("No First 5 records yet.");
            return true;
        }

        // Most total placements first; ties sorted alphabetically (same as before)
        var top = totals.OrderByDescending(t => t.Value)
                        .ThenBy(t => t.Key, StringComparer.Ordinal)
                        .Take(5).ToList();

        var parts = top.Select((t, i) => $"{PlaceLabels[i].TrimEnd(':')} {t.Key}: {t.Value}");
        Say("🏆 First Leaderboard: " + string.Join(" | ", parts));
        return true;
    }

    // ── 3. First-chatter claim (Chat Message trigger) ───────────────
    bool HandleChatMessage()
    {
        string username = GetArg("user");
        string userId = GetArg("userId");

        if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(userId))
            return true;

        if (IgnoredBots.Contains(username.ToLower()))
            return true;

        // 0 = game not running; 1..5 = next place to hand out
        int place = CPH.GetGlobalVar<int>("firstChatterPlace", true);
        if (place == 0)
            return true;

        var claimedUsers = LoadJson<List<string>>("firstChatterClaimedUserIds") ?? new List<string>();
        if (claimedUsers.Contains(userId))
            return true;

        var winners = LoadJson<Dictionary<int, string>>("firstChatterWinners") ?? new Dictionary<int, string>();

        claimedUsers.Add(userId);
        winners[place] = username;

        CPH.SetGlobalVar("firstChatterClaimedUserIds", JsonConvert.SerializeObject(claimedUsers), true);
        CPH.SetGlobalVar("firstChatterWinners", JsonConvert.SerializeObject(winners), true);

        if (place < 5)
        {
            CPH.SetGlobalVar("firstChatterPlace", place + 1, true);
            return true;
        }

        // All 5 places claimed: lock in, record stats, announce, pay out
        CPH.SetGlobalVar("firstChatterPlace", 0, true);

        string[] names = Enumerable.Range(1, 5)
            .Select(p => winners.ContainsKey(p) ? winners[p] : "N/A").ToArray();

        for (int i = 0; i < 5; i++)
            TrackPlace(names[i], PlaceStatVars[i]);

        Say($"🏁 Firsts are locked in! 🥇 {names[0]} | 🥈 {names[1]} | 🥉 {names[2]} | 4th: {names[3]} | 5th: {names[4]}");

        // payouts every PayoutDelayMs, on their own thread so the chat is never held up (a restart before they finish drops the rest)
        System.Threading.Tasks.Task.Run(() =>
        {
            for (int i = 0; i < 5; i++)
            {
                System.Threading.Thread.Sleep(PayoutDelayMs);
                CPH.SendMessage($"!addpoints {names[i]} {PlacePoints[i]}");
            }
        });

        return true;
    }

    // ── Helpers ─────────────────────────────────────────────────────
    string GetArg(string name)
    {
        return CPH.TryGetArg(name, out string argVal) && argVal != null ? argVal : "";
    }

    T LoadJson<T>(string globalVar) where T : class
    {
        string json = CPH.GetGlobalVar<string>(globalVar, true);
        if (string.IsNullOrWhiteSpace(json))
            return null;
        try { return JsonConvert.DeserializeObject<T>(json); }
        catch (Exception ex)
        {
            CPH.LogWarn("[Firsts] Bad JSON in " + globalVar + ": " + ex.Message);
            return null;
        }
    }

    Dictionary<string, int> LoadStats(string statVarName)
    {
        return LoadJson<Dictionary<string, int>>(statVarName) ?? new Dictionary<string, int>();
    }

    void TrackPlace(string username, string statVarName)
    {
        if (string.IsNullOrWhiteSpace(username) || username == "N/A")
            return;

        var stats = LoadStats(statVarName);
        string key = username.ToLower();
        stats[key] = (stats.ContainsKey(key) ? stats[key] : 0) + 1;
        CPH.SetGlobalVar(statVarName, JsonConvert.SerializeObject(stats), true);
    }
}
