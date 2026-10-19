' Runs the log update without opening a window (used by the "PinguinoBot Log Update" scheduled task, every 5 minutes). See Pipeline\update-logs.mjs.
CreateObject("WScript.Shell").Run "cmd /c node ""D:\PinguinoSuite\Pipeline\update-logs.mjs"" > nul 2>&1", 0, False
