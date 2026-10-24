using System;
using System.Text.RegularExpressions;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Twitch native replies for everything the Host says. Program.Dispatch opens a ReplyCtx for a real chat message (its Twitch message id, a dashed UUID); every send made while handling it,
    /// on the same thread or on tasks it starts, goes out as a reply to that message (Helix reply_parent_message_id) and the leading "@sender " is dropped from the text, because the reply already shows who it answers.
    /// A mention of anybody else stays. No message id (timers, events, deck buttons, simulated chat) or a context older than 90 s (a background loop that started inside a handler): the line is sent as it is, "@name" included.
    /// The duplicate-line guard (HostApi.SaidRecently) still sees the original text, so the same line is never said twice.</summary>
    public static class ReplyCtx
    {
        sealed class C { public string Id, Login; public DateTime At; }
        static readonly AsyncLocal<C> Cur = new AsyncLocal<C>();
        static readonly Regex RxId = new Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", RegexOptions.Compiled);
        internal static bool AllowAnyId;   // test switch: accept simulated ids too

        public static bool Real(string id) { return !string.IsNullOrEmpty(id) && (AllowAnyId || RxId.IsMatch(id)); }
        /// <summary>start a context for this message; dispose (or Clear) when the handler is done</summary>
        public static void Begin(string msgId, string login) { Cur.Value = Real(msgId) ? new C { Id = msgId, Login = (login ?? "").TrimStart('@'), At = DateTime.UtcNow } : null; }
        public static void End() { Cur.Value = null; }
        /// <summary>event / timer work (alerts, raid lines, stream online ...): never a reply, whatever chat message this thread last handled; restores the context when disposed. Tasks and timers started inside inherit "no reply".</summary>
        public static IDisposable Plain() { var old = Cur.Value; Cur.Value = null; return new Restore(old); }
        sealed class Restore : IDisposable { readonly C _old; public Restore(C old) { _old = old; } public void Dispose() { Cur.Value = _old; } }

        /// <summary>the text to send and the message to reply to ("" = a plain message)</summary>
        public static string Prepare(string text, out string parentId)
        {
            parentId = ""; var c = Cur.Value;
            if (c == null || string.IsNullOrEmpty(text) || (DateTime.UtcNow - c.At).TotalSeconds > 90) return text;
            parentId = c.Id;
            if (c.Login != "")
            {
                var m = Regex.Match(text, "^@" + Regex.Escape(c.Login) + "(?![A-Za-z0-9_])[,:]?\\s*", RegexOptions.IgnoreCase);
                if (m.Success && text.Length > m.Length) return text.Substring(m.Length).TrimStart();
            }
            return text;
        }

        /// <summary>the Helix chat/messages body for this line</summary>
        public static JObject Body(string broadcasterId, string senderId, string text)
        {
            string parent; string line = Prepare(text, out parent);
            var b = new JObject { { "broadcaster_id", broadcasterId }, { "sender_id", senderId }, { "message", line } };
            if (parent != "") b["reply_parent_message_id"] = parent;
            return b;
        }
    }
}
