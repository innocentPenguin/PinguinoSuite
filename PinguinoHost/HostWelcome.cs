using System;
using System.Threading.Tasks;

namespace PinguinoHost
{
    /// <summary>Welcome bonus: a brand-new chatter (Twitch's first-message flag) gets WelcomeBonus points a little AFTER the welcome line, never in the same message.
    /// One grant per login ever (ledger id "welcome:login", so a restart or a repeat flag cannot pay twice). Economy setting WelcomeBonus (0 = off, default 100);
    /// PINGUINO_WELCOME_DELAY_SEC changes the 45 s delay (tests). Bots, the streamer and simulated players never get it.</summary>
    public static class Welcome
    {
        public static void OnChat(string user, bool firstMsg, Action<string> say)
        {
            if (!firstMsg || string.IsNullOrEmpty(user) || Control.Synthetic) return;
            string login = user.Trim().TrimStart('@').ToLowerInvariant();
            if (Sim.IsSim(login) || Boards.IsBot(login) || Boards.AllBots().Contains(login)) return;
            string ch = ""; try { ch = ((string)HostApi.StreamerCreds()["Channel"] ?? "").ToLowerInvariant(); } catch (Exception) { }
            if (login == ch) return;
            Sounds.OnFirstChat(login);   // the welcome chime is its own setting (alerts_settings.json), independent of the bonus
            long amount = Amount(); if (amount <= 0) return;
            string id = "welcome:" + login; if (Economy.Applied(id)) return;
            int delay; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_WELCOME_DELAY_SEC"), out delay) || delay < 0) delay = 45;
            Task.Run(async () =>
            {
                try
                {
                    await Task.Delay(delay * 1000);
                    if (SpamFirst.BannedNow(login)) { Clog.Info("welcome", login + " was banned or timed out during the delay: no welcome bonus"); return; }
                    if (!Economy.Credit(id, login, amount, "welcome bonus")) return;
                    say("@" + user + " here's " + amount + " " + Economy.CurrencyName + ": you can gamble them, buy stuff from !shop, and compete!");
                }
                catch (Exception ex) { Clog.Warn("welcome", "welcome bonus failed: " + ex.Message); }
            });
        }
        /// <summary>a brand-new YouTube / TikTok viewer (first line ever seen, see PlatformUsers.TakeFresh): welcomed once, a few seconds AFTER the answer to their first line (so it never rides along with it: YouTube takes about one message a second),
        /// with the WelcomeBonus paid at that moment (ledger "welcome:key", so never twice). Setting ForeignGreeting (default on) turns it off; TikTok has no reply path, so there the bonus is paid silently.
        /// PINGUINO_FOREIGN_WELCOME_DELAY_MS changes the 3 s wait (tests).</summary>
        public static void OnForeign(string key, string platform, string text, Action<string> say)
        {
            try
            {
                if (Control.Synthetic || string.IsNullOrEmpty(key)) return;
                try { var g = Economy.SettingsView()["ForeignGreeting"]; if (g != null && !(bool)g) return; } catch (Exception) { }
                if (WelcomeBack.IsSpamText(text, true) || WelcomeBack.IsSpamLogin(PlatformUsers.Display(key))) { Clog.Info("welcome", key + " looks like spam: no greeting, no bonus"); return; }
                if (Economy.Applied("welcome:" + key)) return;
                int ms; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_FOREIGN_WELCOME_DELAY_MS"), out ms) || ms < 0) ms = 3000;
                Task.Run(async () =>
                {
                    try
                    {
                        await Task.Delay(ms);
                        long amount = Amount(); string id = "welcome:" + key; if (Economy.Applied(id)) return;
                        bool paid = amount > 0 && Economy.Credit(id, key, amount, "welcome bonus");
                        Clog.Info("welcome", platform + " newcomer " + PlatformUsers.Display(key) + " (" + key + ")" + (paid ? ": " + amount + " " + Economy.CurrencyName + " paid" : ""));
                        ReplyCtx.BeginForeign(platform, "", key, false);
                        try { say("Welcome to the stream! 🐧" + (paid ? " +" + amount + " " + Economy.CurrencyName + " to gamble or spend in !shop." : "")); } finally { ReplyCtx.End(); }
                    }
                    catch (Exception ex) { Clog.Warn("welcome", "foreign welcome failed: " + ex.Message); }
                });
            }
            catch (Exception ex) { Clog.Warn("welcome", "foreign welcome failed: " + ex.Message); }
        }
        static long Amount() { try { var v = Economy.SettingsView()["WelcomeBonus"]; return v == null ? 100 : (long)v; } catch (Exception) { return 100; } }
    }
}
