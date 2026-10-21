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
                    if (!Economy.Credit(id, login, amount, "welcome bonus")) return;
                    say("@" + user + " here's " + amount + " " + Economy.CurrencyName + ": you can gamble them, buy stuff from !shop, and compete!");
                }
                catch (Exception ex) { Clog.Warn("welcome", "welcome bonus failed: " + ex.Message); }
            });
        }
        static long Amount() { try { var v = Economy.SettingsView()["WelcomeBonus"]; return v == null ? 100 : (long)v; } catch (Exception) { return 100; } }
    }
}
