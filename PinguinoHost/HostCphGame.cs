using System;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    // Twitch category for the bot core. The core (PinguinoBotCore.SetTwitchGame) looks up SetChannelGame by reflection on the CPH object; Streamer.bot used to
    // provide it. The Host talks to Twitch directly (Helix PATCH /channels through ChannelControl, streamer token with channel:manage:broadcast), so it provides it here.
    public partial class HostCPH
    {
        /// <summary>test hook: replaces the Helix call (category name -> success)</summary>
        public static Func<string, bool> TestSetGame;

        /// <summary>Sets the channel's Twitch category by name. false = Twitch refused or the category is unknown or ambiguous (reason goes to the Host log).
        /// In --sim nothing leaves the machine: it answers true so the activity commands can be tested.</summary>
        public bool SetChannelGame(string game)
        {
            if (string.IsNullOrWhiteSpace(game)) return false;
            if (TestSetGame != null) return TestSetGame(game);
            if (HostApi.SimMode) return true;
            try
            {
                var r = ChannelControl.Update(null, game);
                if ((bool?)r["ok"] == true) { ChannelControl.Audit("bot", "game", game); return true; }
                Console.WriteLine("Twitch category not set to '" + game + "': " + (string)r["error"]);
            }
            catch (Exception e) { Console.WriteLine("Twitch category not set to '" + game + "': " + e.Message); }
            return false;
        }
    }
}
