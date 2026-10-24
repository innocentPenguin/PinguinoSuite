using System; using System.Linq; using System.Collections.Generic; using Newtonsoft.Json.Linq; using PinguinoHost;
static class T { static int bad = 0;
 static void C(bool ok, string m) { if (!ok) { bad++; Console.WriteLine("FAIL " + m); } }
 static int Main() {
  C(WelcomeBack.Band(1) == "" && WelcomeBack.Band(2) == "short" && WelcomeBack.Band(7) == "week" && WelcomeBack.Band(30) == "month" && WelcomeBack.Band(90) == "long", "bands");
  var g = JObject.Parse("{\"edges\":[{\"a\":\"duoa\",\"b\":\"duob\",\"mutual\":300},{\"a\":\"bud\",\"b\":\"duob\",\"mutual\":40},{\"a\":\"acq\",\"b\":\"duob\",\"mutual\":3}],\"groups\":[{\"members\":[\"grp1\",\"grp2\"]}]}");
  C(WelcomeBack.Standing(g, "duoa") == "core", "core"); C(WelcomeBack.Standing(g, "bud") == "regular", "regular");
  C(WelcomeBack.Standing(g, "duob") == "core", "duob core"); C(WelcomeBack.Standing(g, "acq") == "known", "known edge");
  C(WelcomeBack.Standing(g, "grp1") == "known", "known group"); C(WelcomeBack.Standing(g, "nobody") == "", "unknown"); C(WelcomeBack.Standing(null, "x") == "", "no graph");
  var r = new Random(1);
  C(WelcomeBack.IsSpamLogin("succeedingsteelbqdzvkxr") && WelcomeBack.IsSpamLogin("dramaticlacencjhwz") && WelcomeBack.IsSpamLogin("auxiliarygamblingmtkxvs") && WelcomeBack.IsSpamLogin("goddambalance2g3l2"), "viewbot logins are spam");
  foreach (var ok in new[] { "lvlmarshmello", "snowyroses_", "spongefredcircleshorts", "t1cklem0n3ter324", "nxghtmare_rl_", "penguinslittlebro", "im_just_a_pineapple", "carteriscool898", "imnotmelloiswarghhh" }) C(!WelcomeBack.IsSpamLogin(ok), "real login is not spam: " + ok);
  C(WelcomeBack.Pick("succeedingsteelbqdzvkxr", 10, "core", null, r) == "", "no welcome-back line for a spam login");
  C(WelcomeBack.IsSpamText("Ai viewers stre𝓪mboo .com") && WelcomeBack.IsSpamText("Cheapest Viewers boosttask.ru"), "fancy letters / other domains");
  C(!WelcomeBack.IsSpamText("who tf is streamboo", true) && !WelcomeBack.IsSpamText("how do i get viewers like you bro?", true) && !WelcomeBack.IsSpamText("https://open.spotify.com/track/abc", true), "talk about spam is not spam");
  C(WelcomeBack.IsSpamText("Best viewers with viewers streamboo .org") && WelcomeBack.IsSpamText("Ai vIewers streamboo . Com") && WelcomeBack.IsSpamText("cheap followers at foo.xyz") && WelcomeBack.IsSpamText("hi check bar.com", true), "spam texts");
  C(!WelcomeBack.IsSpamText("check google.com for the rank") && !WelcomeBack.IsSpamText("hi chat how are the viewers today") && !WelcomeBack.IsSpamText("yo peng", true) && !WelcomeBack.IsSpamText("https://clips.twitch.tv/x", true), "normal texts are not spam");
  C(WelcomeBack.Pick("Zed", 1, "core", null, r) == "", "too recent -> no line");
  foreach (int d in new[] { 3, 10, 45, 200 }) foreach (var s in new[] { "", "known", "regular", "core" }) for (int i = 0; i < 40; i++) {
    string l = WelcomeBack.Pick("Zed", d, s, null, r); C(l.Contains("Zed") && !l.Contains("{") && !l.Any(char.IsDigit), "line ok d=" + d + " s=" + s + ": " + l); }
  var warm = new HashSet<string>(); for (int i = 0; i < 300; i++) warm.Add(WelcomeBack.Pick("Zed", 10, "core", null, r));
  var cold = new HashSet<string>(); for (int i = 0; i < 300; i++) cold.Add(WelcomeBack.Pick("Zed", 10, "", null, r));
  C(warm.Count > cold.Count && cold.Count >= 4, "warm pool bigger: " + warm.Count + " vs " + cold.Count);
  C(!warm.Except(cold).Any() == false, "warm adds lines");
  var seen = new HashSet<string>(); var got = new List<string>();
  for (int i = 0; i < 4; i++) { string l = WelcomeBack.Pick("Zed", 10, "", x => seen.Contains(x), r); got.Add(l); seen.Add(l); }
  C(got.Distinct().Count() == 4, "no repeat while fresh left: " + string.Join(" | ", got));
  var ex = JObject.Parse("{\"week\":[\"{u} custom line\",\"no placeholder here\"]}");
  var all = new HashSet<string>(); for (int i = 0; i < 400; i++) all.Add(WelcomeBack.Pick("Zed", 10, "", null, r, ex));
  C(all.Contains("Zed custom line") && !all.Contains("no placeholder here"), "extra lines merged, bad ones dropped");
  var th = new HashSet<string>(); for (int i = 0; i < 100; i++) th.Add(WelcomeBack.Thanks("Zed", null, r)); C(th.Count == 3 && th.All(x => x.Contains("Zed")), "thanks pool");
  Console.WriteLine(bad == 0 ? "PASS welcomeback" : "FAILED " + bad); return bad; } }
