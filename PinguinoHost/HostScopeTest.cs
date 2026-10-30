using System;
using System.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "scopetest": the one scope list and the missing-scopes computation (what Twitch returned at validate vs what the Host asks for) and prints PASS/FAIL lines</summary>
    public static class ScopeTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        public static void Run()
        {
            var all = HostApi.ScopeInfo.Select(i => i[0]).ToList();
            Check(all.Count == all.Distinct().Count(), "no scope listed twice");
            Check(HostApi.ScopeInfo.All(i => i.Length == 3 && i[1].Length > 3), "every scope names the feature that uses it");
            Check(HostApi.Scopes.Split(' ').SequenceEqual(all), "the sign-in string is the list, in order");
            Check(HostApi.MissingScopes(all).Count == 0 && HostApi.MissingScopesText(all) == "", "full token: nothing missing, no text");
            var old = all.Where(s => s != "clips:edit" && s != "channel:manage:raids").ToList();
            var m = HostApi.MissingScopes(old);
            Check(m.Count == 2 && m[0] == "clips:edit" && m[1] == "channel:manage:raids", "two lacking: " + string.Join(",", m));
            Check(HostApi.MissingScopesText(old).StartsWith("missing scopes: clips:edit, channel:manage:raids"), "text names them: " + HostApi.MissingScopesText(old));
            Check(HostApi.MissingScopes(new string[0]).Count == all.Count, "empty token: all missing");
            Check(HostApi.MissingScopes(null).Count == all.Count, "null (not validated) is all missing, no crash");
            Check(HostApi.MissingScopes(all.Concat(new[] { "channel:read:editors" })).Count == 0, "extra scopes on the token are fine");
            Console.WriteLine(fails == 0 ? "[scopetest] ALL PASS" : "[scopetest] FAIL " + fails);
        }
    }
}
