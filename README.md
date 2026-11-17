# FF XIII language switcher

A small standalone Windows x64 application for switching the supported PC builds of **FINAL FANTASY XIII**, **FINAL FANTASY XIII-2**, and **LIGHTNING RETURNS: FINAL FANTASY XIII** between their built-in Traditional Chinese and English text.

The current native build is approximately **15.5 KiB**. It needs no Python, .NET, third-party runtime, or extra DLLs at runtime. This repository contains source, build instructions, tests, and optional batch entry points; game files and generated binaries are excluded.

## Use

1. Build `FF13LanguageSwitch.exe` and copy it into the game's main folder.
2. Close the game and its launcher, then double-click the switcher.
3. Check the detected game and folder. Choose **Yes** for Traditional Chinese, **No** for English, or **Cancel** to leave it unchanged.

The switcher detects the game **beside its own EXE**, independently of the shell's working directory. There are no default installation paths or directory picker. An empty or unrecognized folder is rejected without searching for another installation.

Detection uses `FFXiiiLauncher.exe`, `FFXiii2Launcher.exe`, or `LRFF13.exe`. The optional `.cmd` entry points must be placed beside the built switcher.

### Backups are opt-in

By default, switching creates **no backup files or backup directory**. Enable backups explicitly:

```powershell
.\FF13LanguageSwitch.exe zh --backup
.\FF13LanguageSwitch.exe en --backup-dir "my-backups"
```

`--backup` uses the selected game's `original\language_switcher` directory, with a title-specific subdirectory for XIII-2 and LR. A custom `--backup-dir` also enables backups. Existing backup contents are verified and never overwritten. Only files requiring a change are backed up.

### Other command-line options

```powershell
.\FF13LanguageSwitch.exe zh
.\FF13LanguageSwitch.exe en
.\FF13LanguageSwitch.exe status
```

- `--quiet`: suppress dialogs; exit code `0` means success and `1` means failure.
- `--game-dir "folder"`: explicitly override the EXE's folder.
- `--game xiii`, `xiii2`, or `lr`: select a format within the target folder; this never redirects to another installation. `lr-zh` and `lr-en` are compatibility aliases for `lr`.

## What changes

| Game | Modified files | Behavior |
| --- | --- | --- |
| XIII | Launcher and game EXE | Seven differing bytes enable the existing Chinese language/font selectors. English restores the original binaries. |
| XIII-2 | Launcher and game EXE | Seven differing bytes enable the existing Chinese language selectors. English restores the original binaries. |
| Lightning Returns | `steam_api.ini` | Changes only `Language=tchinese` / `Language=english`; both supported original INI layouts retain all other bytes. `LRFF13.exe` is verified but never modified. |

The tool accepts only the executable and configuration hashes listed in the source. It does not add translations, modify game resources, change voice settings, or edit saves. Some built-in graphical labels remain English. It refuses unknown files or a running target game, stages writes, and attempts to restore changes after ordinary write failures even when disk backups are disabled. Power loss or forced termination can interrupt a multi-file switch.

## Build

Requirements for building only:

- Windows x64
- Visual Studio or Build Tools with the C++ x64 toolchain
- Windows SDK

From the repository root:

```powershell
.\language_switcher\native\build.ps1
```

The script locates MSVC using `vswhere` and produces `language_switcher\FF13LanguageSwitch.exe`. The C implementation has no C runtime dependency and imports only Windows system DLLs. The build uses size optimizations and retains ASLR/DEP.

## Tests

Python 3 is needed **only for development tests**. The tests use temporary copies of original game files, never distribute those files, and do not mutate actual installations.

Provide your original fixtures through these environment variables, or the corresponding ignored `language_switcher/test_data` directories:

| Environment variable | Default directory | Required contents |
| --- | --- | --- |
| `FF13_ORIGINAL_DIR` | `test_data/xiii` | Original `FFXiiiLauncher.exe` and `white_data/prog/win/bin/ffxiiiimg.exe` |
| `FF13_2_ORIGINAL_DIR` | `test_data/xiii2` | Original `FFXiii2Launcher.exe` and `alba_data/prog/win/bin/ffxiii2img.exe` |
| `FF13_LR_ORIGINAL_DIR` | `test_data/lr` | `zh-source` and `en-source`, each containing the original `LRFF13.exe` and `steam_api.ini` |

Then run:

```powershell
Set-Location .\language_switcher
python -m unittest -v test_native_switcher test_lr_switcher
```

With all supported fixtures, the suite covers **74 cases**: language roundtrips, exact output hashes, default no-backup behavior, explicit backups, corrupt or unavailable backups, locked files and rollback, running processes, Unicode paths, independent EXE-folder routing, drive-root handling, and standalone execution with an empty `PATH`. Missing fixture sets are reported as skipped. The drive-root regression temporarily maps an unused DOS drive and removes only its own mapping.
