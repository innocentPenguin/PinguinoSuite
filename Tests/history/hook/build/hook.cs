using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

public class CPHInline
{
    // ══════════════════════════════════════════════════════════════
    //  LONG-TERM HISTORY HOOK (paste inside class CPHInline of PinguinoChat.cs; see PinguinoChat\HISTORY_HOOK.md for where to call it)
    //  Reads the files built by Pipeline\build-summaries.mjs:  history\daily\<date>.json, history\weekly\<year>-W<nn>.json, history\monthly\<login>\<yyyy-MM>.json
    //  Needs: using System.Linq; System.IO; System.Text; System.Text.RegularExpressions; Newtonsoft.Json.Linq (all already used by PinguinoChat.cs).
    //  The caller passes only people who may be talked about (never viewers with Privacy "forget" / "anon").
    // ══════════════════════════════════════════════════════════════
    static readonly string[] HistMonthNames = { "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december" };

    static string HistIsoWeek(DateTime d)
    {
        int day = ((int)d.DayOfWeek + 6) % 7;                      // Monday = 0
        DateTime thu = d.Date.AddDays(3 - day);                    // the Thursday of this week decides the year
        int week = 1 + (thu.DayOfYear - 1) / 7;
        return thu.Year + "-W" + week.ToString("00");
    }

    static string HistJoin(JToken t) { var a = t as JArray; return a == null ? "" : string.Join("; ", a.Select(x => (string)x).Where(x => !string.IsNullOrEmpty(x))); }

    static JObject HistRead(string path)
    {
        try { return File.Exists(path) ? JObject.Parse(File.ReadAllText(path, Encoding.UTF8)) : null; }
        catch (Exception) { return null; }
    }

    // The history text for a question: the days / weeks / months it refers to, and the monthly highlights of the people it is about. "" when nothing fits.
    string HistoryDeepText(string question, string speaker, IEnumerable<string> others, string dir, DateTime todayCt)
    {
        if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return "";
        string q = (question ?? "").ToLower();
        var days = new List<string>(); var weeks = new List<string>(); var months = new List<string>();
        foreach (Match m in Regex.Matches(q, @"\b20\d\d-\d\d-\d\d\b")) days.Add(m.Value);
        if (q.Contains("yesterday")) days.Add(todayCt.AddDays(-1).ToString("yyyy-MM-dd"));
        if (Regex.IsMatch(q, @"\blast (stream|night)\b"))
        {
            string dd = Path.Combine(dir, "daily");
            if (Directory.Exists(dd)) { string last = Directory.GetFiles(dd, "*.json").Select(Path.GetFileNameWithoutExtension).OrderBy(x => x, StringComparer.Ordinal).LastOrDefault(); if (last != null) days.Add(last); }
        }
        if (Regex.IsMatch(q, @"\blast week\b")) weeks.Add(HistIsoWeek(todayCt.AddDays(-7)));
        if (Regex.IsMatch(q, @"\bthis week\b")) weeks.Add(HistIsoWeek(todayCt));
        for (int i = 0; i < 12; i++)
            if (Regex.IsMatch(q, @"\b" + HistMonthNames[i] + @"\b")) months.Add((i + 1 > todayCt.Month ? todayCt.Year - 1 : todayCt.Year) + "-" + (i + 1).ToString("00"));
        if (Regex.IsMatch(q, @"\blast month\b")) months.Add(todayCt.AddMonths(-1).ToString("yyyy-MM"));
        if (Regex.IsMatch(q, @"\bthis month\b")) months.Add(todayCt.ToString("yyyy-MM"));

        var people = new List<string>();
        if (!string.IsNullOrEmpty(speaker)) people.Add(speaker.ToLower());
        if (others != null) foreach (string o in others) if (!string.IsNullOrEmpty(o) && !people.Contains(o.ToLower())) people.Add(o.ToLower());
        people = people.Take(3).ToList();
        bool aboutPeople = Regex.IsMatch(q, @"\b(remember|do i|am i|did i|what do i|what did i|about me|my favou?rite|what (does|did|do) \w+ (like|play|do)|know about|used to)\b");

        var sb = new StringBuilder();
        foreach (string d in days.Distinct().Take(3))
        {
            var j = HistRead(Path.Combine(dir, "daily", d + ".json")); if (j == null) continue;
            sb.AppendLine("- " + d + ": " + (string)j["summary"] + " Games: " + HistJoin(j["games"]) + ". Topics: " + HistJoin(j["topics"]) + ". Moments: " + HistJoin(j["moments"]));
        }
        foreach (string w in weeks.Distinct().Take(2))
        {
            var j = HistRead(Path.Combine(dir, "weekly", w + ".json")); if (j == null) continue;
            sb.AppendLine("- week " + w + ": " + (string)j["summary"] + " Highlights: " + HistJoin(j["highlights"]));
        }
        var wantMonths = months.Distinct().Take(2).ToList();
        if (wantMonths.Count == 0 && aboutPeople && days.Count == 0 && weeks.Count == 0)
        {   // no date given but the question is about a person: their latest two months
            foreach (string p in people)
            {
                string pd = Path.Combine(dir, "monthly", p);
                if (!Directory.Exists(pd)) continue;
                foreach (string f in Directory.GetFiles(pd, "*.json").OrderByDescending(x => x, StringComparer.Ordinal).Take(2))
                    HistAddMonth(sb, HistRead(f));
            }
        }
        else
            foreach (string mo in wantMonths)
                foreach (string p in people) HistAddMonth(sb, HistRead(Path.Combine(dir, "monthly", p, mo + ".json")));

        string res = sb.ToString().TrimEnd();
        return res.Length > 1800 ? res.Substring(0, 1800) : res;
    }

    static void HistAddMonth(StringBuilder sb, JObject j)
    {
        if (j == null) return;
        sb.AppendLine("- " + (string)j["login"] + " in " + (string)j["month"] + " (" + (string)j["messages"] + " messages): interests: " + HistJoin(j["interests"]) +
            ". Highlights: " + HistJoin(j["highlights"]) + (string.IsNullOrEmpty((string)j["vibe"]) ? "" : ". Vibe: " + (string)j["vibe"]));
    }

    public string TestCall(string q, string s, IEnumerable<string> o, string d, DateTime t) { return HistoryDeepText(q, s, o, d, t); }
}

public static class Check
{
    static int fails, passes;
    static void Ok(string name, bool ok, string extra = "") { if (ok) passes++; else { fails++; Console.WriteLine("FAIL: " + name + (extra == "" ? "" : "  -> " + extra)); } }

    public static int Main()
    {
        string dir = Path.Combine(Path.GetTempPath(), "hookcheck_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(dir, "daily")); Directory.CreateDirectory(Path.Combine(dir, "weekly")); Directory.CreateDirectory(Path.Combine(dir, "monthly", "alpha"));
        File.WriteAllText(Path.Combine(dir, "daily", "2026-10-17.json"), "{\"summary\":\"Horror game night.\",\"games\":[\"Rocket League\"],\"topics\":[\"mods\"],\"moments\":[\"19:00 - mod talk\"]}");
        File.WriteAllText(Path.Combine(dir, "daily", "2026-10-18.json"), "{\"summary\":\"Customs day.\",\"games\":[\"Rocket League\"],\"topics\":[],\"moments\":[]}");
        File.WriteAllText(Path.Combine(dir, "weekly", "2026-W42.json"), "{\"summary\":\"A busy week.\",\"highlights\":[\"raids on Friday\"]}");
        File.WriteAllText(Path.Combine(dir, "monthly", "alpha", "2026-08.json"), "{\"login\":\"alpha\",\"month\":\"2026-08\",\"messages\":300,\"interests\":[\"Likes the Cowboys\"],\"highlights\":[\"Won a tourney\"],\"vibe\":\"friendly\"}");
        File.WriteAllText(Path.Combine(dir, "monthly", "alpha", "2026-09.json"), "{\"login\":\"alpha\",\"month\":\"2026-09\",\"messages\":200,\"interests\":[\"Listens to Brent Faiyaz\"],\"highlights\":[],\"vibe\":\"chill\"}");
        var c = new CPHInline();
        var today = new DateTime(2026, 10, 19);

        string r = c.TestCall("what happened on 2026-10-17?", "bob", null, dir, today);
        Ok("explicit date", r.Contains("Horror game night") && r.Contains("mod talk"), r);
        r = c.TestCall("what did we do yesterday", "bob", null, dir, today);
        Ok("yesterday", r.Contains("Customs day"), r);
        r = c.TestCall("how was the stream last night", "bob", null, dir, today);
        Ok("last stream = newest daily file", r.Contains("Customs day"), r);
        r = c.TestCall("what happened last week?", "bob", null, dir, today);
        Ok("last week = ISO week 42", r.Contains("A busy week") && r.Contains("raids on Friday"), r);
        r = c.TestCall("what was alpha into in august", "bob", new[] { "alpha" }, dir, today);
        Ok("a month name gives the person's monthly highlights", r.Contains("Likes the Cowboys") && !r.Contains("Brent"), r);
        r = c.TestCall("do you remember what i like", "alpha", null, dir, today);
        Ok("a question about the speaker gives their latest months", r.Contains("Brent Faiyaz") && r.Contains("Cowboys"), r);
        r = c.TestCall("hello there", "alpha", null, dir, today);
        Ok("small talk gives nothing", r == "", r);
        r = c.TestCall("what happened on 2026-01-01", "bob", null, dir, today);
        Ok("missing day gives nothing", r == "", r);
        r = c.TestCall("do you remember what i like", "bob", null, dir, today);
        Ok("a person without files gives nothing", r == "", r);
        Ok("never longer than 1800 characters", c.TestCall("2026-10-17 2026-10-18 last week august", "alpha", new[] { "alpha" }, dir, today).Length <= 1800);

        try { Directory.Delete(dir, true); } catch (Exception) { }
        Console.WriteLine(fails == 0 ? "ALL " + passes + " HOOK CHECKS PASSED" : fails + " FAILED / " + passes + " passed");
        return fails == 0 ? 0 : 1;
    }
}

