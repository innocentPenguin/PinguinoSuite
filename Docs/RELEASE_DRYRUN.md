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

## Signed releases: step by step (added 2026-10-23 by 21-Lite; verified with a throwaway key in a scratch folder)
Signing is optional but recommended. It proves a release came from you; the updater refuses anything else once a public key is configured. Two different secrets exist, do not mix them up: the **signing seed** (Ed25519, signs `manifest.json`) and the **install key** (`install.key.enc`, a sealed read-only GitHub token, only for a PRIVATE repo; `Seal-InstallKey` seals that token, not the signing seed).

One-time, by Ivan:
1. `node Installer\Make-SigningKey.mjs` creates `%USERPROFILE%\.pinguino\signing-seed.txt` (private, never printed, refuses to run inside the repo or over an existing seed) and prints the public key (also saved as `signing-pubkey.txt` there). Back the seed file up somewhere safe; losing it means a new key and reinstalling the public key everywhere.
2. Private repo only: create a fine-grained read-only token and run `Installer\Seal-InstallKey.bat` (steps in `Docs\INSTALL.md`). Public Lite repo: skip this.
3. Every release: `node Installer\Build-Release.mjs --version X.Y.Z --sign-key %USERPROFILE%\.pinguino\signing-seed.txt`, then attach `manifest.json`, `manifest.sig`, `suite-X.Y.Z.zip` to the GitHub release (`Docs\LITE_RELEASE.md`).
4. Every new install gets the public key: `install.mjs ... --pubkey <public key>` writes `"pubkey"` into `install.json`; the updater then uses it for check/apply/verify (`--pubkey` on the command line overrides). An install made without `--pubkey` verifies nothing; add `"pubkey": "<key>"` to its `install.json` by hand to switch checking on.

Verified (scratch key, release 1.0.0, minimal install): `install.json` carries `pubkey`; check and verify OK; manifest edited after signing -> "the release signature does not match the configured key; refusing it"; `manifest.sig` removed -> "this release is not signed but a signing key is configured; refusing it"; a different public key -> signature mismatch; `Make-SigningKey` refuses to overwrite an existing seed or to write inside the repo.

Re-run table (2026-10-23, after the `spike-cfg`/`lockfile` skip rule in `components.mjs`, commit 927a625): updater tests 39/39 pass; Build-Release signed OK (225 files, parts core, link, listen, multi, spotify, voice, tools, host, shell, lite); lite-minimal install 57 files; tamper/unsigned/wrong-key refusals unchanged.

## Update and rollback dry run (2026-10-23, 21-Lite, scratch folder, throwaway key)
Setup: signed Build-Release 1.0.0 and 1.0.1 (231 files, 66 MB each), `install.mjs --local <1.0.0> --pubkey <k> --profile lite-minimal` (59 files). The updater calls used `--source <folder>` and `--core-port 59999` (so the real Suite on 8760 is not mistaken for "app running").
| Step | Result |
|---|---|
| `check --source <1.0.1>` | available 1.0.0 -> 1.0.1; parts: link changed (34 files), lite and tools unchanged |
| `apply` | "updated 1.0.0 -> 1.0.1", backup `Data/updates/backup/1.0.0-<time>`, install.json version 1.0.1 |
| `verify --source <1.0.1>` | all parts ok |
| `rollback` | "rolled back to 1.0.0"; `status` 1.0.0; `verify --source <1.0.0>` all ok |
| `apply` from a copy of the release whose zip has 8 bytes flipped inside a changed link file | refused: "suite-1.0.1.zip failed its sha256 check; nothing was changed"; file hash and install.json untouched, `verify` 1.0.0 ok |
| `apply` of the good release right after | OK again, `check` says no update |
Notes: (1) A previously staged good zip in `Data/updates/staging/<ver>` is reused only if its size and sha256 match the manifest, so a corrupted served zip cannot slip in; for a meaningful corruption test clear `staging` first (my first try was fooled by that cache, harmless). (2) Corrupting bytes in a part the install does not keep (for example host/core data in a minimal install) is not even read, so it is not detected and not needed. (3) A plain `http://127.0.0.1` update source is NOT usable: `allowHttpLocal` exists in sources.mjs but no caller sets it, so only https, a local folder or a local zip work. That is intended (the installs have a real https source); for dry runs use a folder. (4) Not covered here: a failure in the middle of the swap (the restore path is unit-tested in Suite/updater/test).
