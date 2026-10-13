"""Game, Steam and tool detection, plus persistent settings."""
import glob
import json
import os
import re
import shutil
import winreg

APP_ID = 1761390
GAME_DIR_NAME = "Hatsune Miku Project DIVA Mega Mix Plus"
GAME_EXE = "DivaMegaMix.exe"

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "game_dir": "",
    "ffmpeg": "",
    "pv_id_start": 9500,
    "video_codec": "h264",
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def steam_libraries():
    roots = []
    for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
        try:
            with winreg.OpenKey(hive, key) as k:
                for name in ("SteamPath", "InstallPath"):
                    try:
                        roots.append(os.path.normpath(winreg.QueryValueEx(k, name)[0]))
                    except OSError:
                        pass
        except OSError:
            pass
    libs = list(roots)
    for root in roots:
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            with open(vdf, encoding="utf-8", errors="replace") as f:
                txt = f.read()
            libs += [os.path.normpath(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', txt)]
    unique = []
    for lib in libs:
        if lib.lower() not in (u.lower() for u in unique):
            unique.append(lib)
    return unique


def is_game_dir(path):
    return bool(path) and os.path.isfile(os.path.join(path, GAME_EXE))


def find_game():
    for lib in steam_libraries():
        d = os.path.join(lib, "steamapps", "common", GAME_DIR_NAME)
        if is_game_dir(d):
            return d
    return None


def find_tool(name, hint=""):
    """Find ffmpeg/ffprobe. `hint` may be the configured ffmpeg.exe path or its folder."""
    exe = name + ".exe"
    cands = []
    if hint:
        cands += [hint, os.path.join(hint, exe), os.path.join(os.path.dirname(hint), exe)]
    which = shutil.which(name)
    if which:
        cands.append(which)
    local = os.environ.get("LOCALAPPDATA", "")
    cands.append(os.path.join(local, "Microsoft", "WinGet", "Links", exe))
    cands += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", exe), recursive=True)
    cands += [os.path.join(APP_DIR, "tools", exe), os.path.join("C:\\ffmpeg", "bin", exe)]
    for c in cands:
        if c and os.path.isfile(c) and os.path.basename(c).lower() == exe:
            return os.path.abspath(c)
    return None
