using System;
using System.Threading.Tasks;

namespace PinguinoHost
{
    /// <summary>sim line "replytest": Twitch native replies in the Host's own senders (ReplyCtx)</summary>
    public static class ReplyTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        public static void Run()
        {
            string id = "6b2c8d5e-1f0a-4c3b-9d7e-5a4f3e2d1c0b", p;
            ReplyCtx.Begin(null, "Bob"); string t = ReplyCtx.Prepare("@Bob hi", out p);
            Check(p == "" && t == "@Bob hi", "no context: plain line, @name kept");
            ReplyCtx.Begin("sim-3", "Bob"); t = ReplyCtx.Prepare("@Bob hi", out p);
            Check(p == "" && t == "@Bob hi", "a simulated / non-Twitch id is not a reply");
            ReplyCtx.Begin(id, "Bob"); t = ReplyCtx.Prepare("@bob you have 500 points", out p);
            Check(p == id && t == "you have 500 points", "real message: reply, @sender dropped (any case): " + t);
            t = ReplyCtx.Prepare("@Bob, ok", out p); Check(t == "ok" && p == id, "comma form dropped");
            t = ReplyCtx.Prepare("@alice you got points from Bob", out p); Check(t == "@alice you got points from Bob" && p == id, "a mention of somebody else stays");
            t = ReplyCtx.Prepare("@Bobby hi", out p); Check(t == "@Bobby hi", "a longer name is not cut");
            t = ReplyCtx.Prepare("Points: 5", out p); Check(t == "Points: 5" && p == id, "a line without @name is still a reply");
            t = ReplyCtx.Prepare("@Bob", out p); Check(t == "@Bob", "a line that is only the mention is left alone");
            var b = ReplyCtx.Body("b1", "s1", "@bob yo");
            Check((string)b["reply_parent_message_id"] == id && (string)b["message"] == "yo" && (string)b["broadcaster_id"] == "b1" && (string)b["sender_id"] == "s1", "Helix body has reply_parent_message_id");
            string seen = null; var task = Task.Run(() => { string q; ReplyCtx.Prepare("x", out q); seen = q; }); task.Wait();
            Check(seen == id, "tasks started from the handler keep the reply");
            ReplyCtx.End(); ReplyCtx.Prepare("x", out p); Check(p == "", "ended: no reply");
            b = ReplyCtx.Body("b1", "s1", "@bob yo"); Check(!b.ContainsKey("reply_parent_message_id") && (string)b["message"] == "@bob yo", "no context: body is plain");
            Console.WriteLine(fails == 0 ? "[replytest] ALL PASS" : "[replytest] " + fails + " FAIL");
        }
    }
}
