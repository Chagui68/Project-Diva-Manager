# DivaLoader

Mod loader for **Hatsune Miku: Project DIVA Mega Mix+** (Steam). It is loaded as `dinput8.dll` and is
compatible with the DivaModLoader mod layout:

```
mods/<Mod>/config.toml
mods/<Mod>/rom/...
```

## What it does

| Feature | How |
|---|---|
| Loose mod files | Puts the `include` folders of every enabled mod in front of the game's `rom` search paths. |
| `mod_*` databases (`mod_pv_db.txt`, `mod_spr_db.bin`, ...) | Adds each mod to the game's database prefix list and resolves their paths. |
| PV IDs above 999 | Patches the `pv_db` parsing loop so it walks the IDs actually present in the file. |
| Extreme and Extra Extreme unlocked on custom songs | Sets byte `0x11D` of their score entry (the same flag used by [ExPatch](https://github.com/nastys/ExPatch), MIT). With `unlock_extreme = "all"` the ExPatch patch is applied to every song. |
| Scores for new songs | Provides score slots for IDs the game's save data has no room for, stored in `DivaLoader_scores.bin`. |
| Loose `.txt` files the game would only read from a CPK | File-open hook. |
| Module (1035) and costume (498) limits, `pv_db` date check | Byte patches. |
| DLL mods | Loads each mod's `dll = [...]` and calls its exported `PreInit`, `Init` and `PostInit`. `D3DInit`, `OnFrame` and `OnResize` are not supported. |
| Starting outside Steam | Redirects `SteamAPI_RestartAppIfNecessary` and writes `steam_appid.txt`. |
| Diagnostics | Writes `DivaLoader.log` next to the game, including fatal exceptions and where they happened. |

The hook engine (`src/Hook.cpp`) is self-contained and does not use Detours or MinHook. Each hook states how
many bytes it replaces and where relative jumps need relocating.

## Building

Requires Visual Studio Build Tools 2022 with the "Desktop development with C++" workload.

```bash
loader\build.bat
```

The output is `loader\build\dinput8.dll`. The repository also ships a prebuilt copy in `loader\bin\dinput8.dll`,
so building is not needed to use it. The **Instalar DivaLoader** button in Diva Manager copies the local build
to the game if it exists, otherwise the one in `loader\bin`. An existing foreign `dinput8.dll` is kept as
`dinput8.dll.bak`.

Tests for the hook engine and the TOML reader, without the game:

```bash
loader\tests\build_test.bat
```

## config.toml (game folder)

```toml
enabled = true      # false disables the loader
console = false     # true opens a console with the log
mods = "mods"       # mods folder
priority = [        # optional: load order, the first one has the highest priority
  "MyMod",
]
unlock_extreme = "custom"  # "custom" (new songs), "all" (every song) or "none"
debug_skip = []     # diagnostics: "patches", "scores", "pv", "cpk", "db", "rom"
```

Without `priority`, mods load in alphabetical order. With `priority`, only the listed mods are loaded.

## Compatibility

Addresses are found by byte pattern. Each one is first checked at its address in the current Steam build and,
if it does not match, searched for in the whole executable. If a game update changes the code, the loader
shows a warning and the game starts without mods.

## Credits

Byte patterns, patch offsets and the `rom` path / database prefix technique come from
[DivaModLoader](https://github.com/blueskythlikesclouds/DivaModLoader) (MIT License), as does the empty score
template (`src/EmptyScore.inc`). The loader code itself is a new implementation. See
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
