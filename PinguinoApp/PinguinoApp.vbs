' PinguinoApp (no console flash): runs PinguinoApp.bat hidden.
Set sh = CreateObject("WScript.Shell")
sh.Run """" & Replace(WScript.ScriptFullName, "PinguinoApp.vbs", "PinguinoApp.bat") & """", 0, False
