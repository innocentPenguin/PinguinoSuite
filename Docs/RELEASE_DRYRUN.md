# Release dry run (2026-10-22, by 01) — nothing built, nothing launched, live install untouched

All in a scratch folder. A throwaway Ed25519 key was generated there (it is not the real signing key).

| Step | Result |
|---|---|
| `Installer/Build-Release.mjs --version 1.0.0 --sign-key <scratch seed>` | 192 files, 53 MB zip, manifest.json + manifest.sig, per-part hashes for core, link, listen, multi, spotify, voice, tools, host, shell, lite |
| `install.mjs --local <rel> --pubkey <pub>` (full) | OK, 193 files, 74 MB |
| same, `--profile lite-minimal` | OK, 55 files, 7.8 MB (lite + link + tools) |
| manifest changed after signing | refused: "the release signature does not match the configured key" |
| release unsigned but a key is configured | refused |
| version like `1.0.0-dry` | refused: "bad version" (use plain numbers) |
| minimal install: `check` | lite, link, tools listed; core, listen, multi, spotify, voice, host, shell offered as `optional` |
| `verify` | link.json deleted by hand -> `damaged`; lite `ok` |
| `apply --only spotify` | spotify added (14 files), `parts` in install.json updated |
| `apply --only link --repair` | link.json restored, `verify` -> all ok |
| `eject --part spotify` | 14 files MOVED to `Data/updates/ejected/spotify-<time>/`, nothing deleted |

Notes: the updater's commands come first (`updater.mjs verify --install <dir> --source <rel> --pubkey <k>`). Eject leaves an empty `Suite/modules/spotify` folder behind (harmless).
Still to do by Ivan for real signed releases: create the real key pair once, seal the private seed (`Installer/Seal-InstallKey.bat`), publish the public key in install.json (`pubkey`).
