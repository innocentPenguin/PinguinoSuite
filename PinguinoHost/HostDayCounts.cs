using System;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Per stream-day history for a counter, so it answers today / this week / this month / all-time separately. A "days" object maps a day key (YYYY-MM-DD) to a count; the keys come from the SAME Periods helper the boards use
    /// (Chicago stream day, ISO week, month), so a counter and a board always agree on what "today" and "this week" mean. Every counter in the Host should use this (see Docs\HOST_CONVENTIONS.md).</summary>
    public static class DayCounts
    {
        public static readonly string[] PeriodNames = { "today", "week", "month", "all" };
        public static string ParsePeriod(string s)
        {
            switch ((s ?? "").Trim().ToLowerInvariant())
            {
                case "today": case "day": case "daily": case "session": return "today";
                case "week": case "weekly": case "thisweek": return "week";
                case "month": case "monthly": case "thismonth": return "month";
                case "all": case "alltime": case "all-time": case "total": case "ever": return "all";
                default: return "";
            }
        }
        public static string Label(string period) { return period == "today" ? "today" : period == "week" ? "this week" : period == "month" ? "this month" : "all-time"; }
        public static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        public static string DayOf(long ts) { return Periods.DayKey(ts); }
        /// <summary>the ISO week key ("2026-W44") of a day key, in the format Periods.WeekKey uses</summary>
        public static string WeekOf(string day)
        {
            DateTime d; if (!DateTime.TryParseExact(day ?? "", "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out d)) return "";
            return ISOWeek.GetYear(d).ToString("0000") + "-W" + ISOWeek.GetWeekOfYear(d).ToString("00");
        }
        /// <summary>days-object total for today | week | month (all = every day); a null object counts as empty</summary>
        public static int Sum(JObject days, string period, long ts)
        {
            if (days == null) return 0; long sum = 0; string td = Periods.DayKey(ts), wk = Periods.WeekKey(ts), mo = Periods.MonthKey(ts);
            foreach (var p in days.Properties())
            {
                int n = (int?)p.Value ?? 0; string k = p.Name;
                if (period == "all" || (period == "today" && k == td) || (period == "month" && k.StartsWith(mo, StringComparison.Ordinal)) || (period == "week" && WeekOf(k) == wk)) sum += n;
            }
            return (int)Math.Min(int.MaxValue, sum);
        }
        public static void Add(JObject days, string day, int n)
        {
            int v = Math.Max(0, ((int?)days[day] ?? 0) + n);
            if (v == 0) days.Remove(day); else days[day] = v;
        }
        /// <summary>per-month totals of a days object (YYYY-MM -> n), sorted</summary>
        public static JObject PerMonth(JObject days)
        {
            var m = new SortedDictionary<string, int>(StringComparer.Ordinal);
            if (days != null) foreach (var p in days.Properties()) { if (p.Name.Length < 7) continue; string k = p.Name.Substring(0, 7); int o; m.TryGetValue(k, out o); m[k] = o + ((int?)p.Value ?? 0); }
            var r = new JObject(); foreach (var kv in m) r[kv.Key] = kv.Value; return r;
        }
        /// <summary>"Feb 2026" from "2026-02-04"</summary>
        public static string MonthYear(string day)
        {
            DateTime d; return DateTime.TryParseExact(day ?? "", "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out d) ? d.ToString("MMM yyyy", CultureInfo.InvariantCulture) : (day ?? "");
        }
    }
}
