# 52 - Link (worker under 50 - Tools)
Owns Suite\modules\link. Supervisor 50 (local_0e1e5827-e0dc-4136-863e-75f19f882578). Never pushes, never restarts modules.

## Task log
- Task 1 (2026-10-23): 11 suites pass (remotecheck "hub macro problems" check is timing-flaky under load: 2200 ms sleep; passes alone). Control-file protocol verified against Suite\suite\suite.py process_control: name `<start|stop|restart>-<module id>` in Data\runtime\control, core deletes the file, honours only registered ids. Matches lite.mjs controlModule. controlcheck extended (12 checks, reads suite.py to catch drift). INDEX.md garbled path fixed.
