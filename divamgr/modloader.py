"""Mod loader integration (DivaLoader, compatible with DivaModLoader mods): install, root config, mod listing and toggling."""
import json
import os
import re
import shutil
import tomllib
from dataclasses import dataclass, field

DM_META = "diva_manager.json"


def is_installed(game_dir):
    return loader_kind(game_dir) is not None


def root_config_path(game_dir):
    return os.path.join(game_dir, "config.toml")


def read_toml(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def mods_dir(game_dir):
    cfg = read_toml(root_config_path(game_dir))
    return os.path.join(game_dir, cfg.get("mods", "mods"))


LOADER_NAME = "DivaLoader"
_LOADER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "loader")
# a fresh local build wins; otherwise the prebuilt copy shipped in the repository
LOADER_BUILD = next((p for p in (os.path.join(_LOADER_DIR, "build", "dinput8.dll"),
                                 os.path.join(_LOADER_DIR, "bin", "dinput8.dll")) if os.path.isfile(p)),
                    os.path.join(_LOADER_DIR, "bin", "dinput8.dll"))
DEFAULT_ROOT_CONFIG = 'enabled = true\nconsole = false\nmods = "mods"\n'


def loader_kind(game_dir):
    """None if no dinput8.dll, "DivaLoader" if it is ours, otherwise "otro" (e.g. DivaModLoader)."""
    path = os.path.join(game_dir, "dinput8.dll")
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return LOADER_NAME if LOADER_NAME.encode() in f.read() else "otro"


def install_loader(game_dir, log=print):
    """Copy the compiled DivaLoader dinput8.dll into the game folder.
    A foreign dinput8.dll is kept as dinput8.dll.bak; an existing config.toml is kept."""
    if not os.path.isfile(LOADER_BUILD):
        raise FileNotFoundError("Falta loader/build/dinput8.dll. Compílalo con loader/build.bat")
    dst = os.path.join(game_dir, "dinput8.dll")
    if loader_kind(game_dir) == "otro":
        shutil.move(dst, dst + ".bak")
        log("dinput8.dll anterior guardado como dinput8.dll.bak")
    shutil.copy2(LOADER_BUILD, dst)
    if not os.path.exists(root_config_path(game_dir)):
        with open(root_config_path(game_dir), "w", encoding="utf-8", newline="\n") as f:
            f.write(DEFAULT_ROOT_CONFIG)
    os.makedirs(mods_dir(game_dir), exist_ok=True)
    log(f"{LOADER_NAME} instalado en {game_dir}")


def uninstall_loader(game_dir, log=print):
    dst = os.path.join(game_dir, "dinput8.dll")
    if loader_kind(game_dir) == LOADER_NAME:
        os.remove(dst)
        if os.path.isfile(dst + ".bak"):
            shutil.move(dst + ".bak", dst)
            log("dinput8.dll anterior restaurado")
        log(f"{LOADER_NAME} desinstalado")


def get_priority(game_dir):
    p = read_toml(root_config_path(game_dir)).get("priority")
    return list(p) if isinstance(p, list) else None


def set_priority(game_dir, folders):
    """Rewrite the `priority` array in the root config.toml, keeping the rest of the file."""
    path = root_config_path(game_dir)
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    arr = "priority = [\n" + "".join(f'  "{_esc(x)}",\n' for x in folders) + "]"
    if re.search(r"(?ms)^priority\s*=\s*\[.*?\]", txt):
        txt = re.sub(r"(?ms)^priority\s*=\s*\[.*?\]", lambda _: arr, txt, count=1)
    else:
        txt = txt.rstrip("\n") + "\n" + arr + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)


def _esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def write_mod_config(mod_path, name, description, version, date, author, enabled=True):
    txt = (f"enabled = {'true' if enabled else 'false'}\n"
           f'include = ["."]\n'
           f'name = "{_esc(name)}"\n'
           f'description = "{_esc(description)}"\n'
           f'version = "{_esc(version)}"\n'
           f'date = "{_esc(date)}"\n'
           f'author = "{_esc(author)}"\n')
    with open(os.path.join(mod_path, "config.toml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)


def set_enabled(mod_path, enabled):
    path = os.path.join(mod_path, "config.toml")
    val = "true" if enabled else "false"
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    if re.search(r"(?m)^enabled\s*=", txt):
        txt = re.sub(r"(?m)^enabled\s*=.*$", f"enabled = {val}", txt, count=1)
    else:
        txt = f"enabled = {val}\n" + txt
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)


@dataclass
class Mod:
    folder: str
    path: str
    name: str
    enabled: bool
    author: str = ""
    version: str = ""
    managed: bool = False
    pv_ids: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


PV_RE = re.compile(r"^pv_(\d+)\.", re.M)


def mod_pv_ids(mod_path):
    ids = set()
    for root, _dirs, files in os.walk(mod_path):
        for fn in files:
            if fn.lower().endswith("pv_db.txt"):
                try:
                    with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as f:
                        ids.update(int(m) for m in PV_RE.findall(f.read()))
                except OSError:
                    pass
    return sorted(ids)


def list_mods(game_dir):
    base = mods_dir(game_dir)
    if not os.path.isdir(base):
        return []
    mods = []
    for folder in sorted(os.listdir(base), key=str.lower):
        path = os.path.join(base, folder)
        cfg_path = os.path.join(path, "config.toml")
        if not os.path.isfile(cfg_path):
            continue
        cfg = read_toml(cfg_path)
        meta = {}
        meta_path = os.path.join(path, DM_META)
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                meta = {}
        mods.append(Mod(folder=folder, path=path, name=str(cfg.get("name", folder)),
                        enabled=bool(cfg.get("enabled", True)), author=str(cfg.get("author", "")),
                        version=str(cfg.get("version", "")), managed=bool(meta),
                        pv_ids=mod_pv_ids(path), meta=meta))
    priority = get_priority(game_dir)
    if priority:
        order = {f: i for i, f in enumerate(priority)}
        mods.sort(key=lambda m: order.get(m.folder, len(order)))
    return mods


def free_pv_id(game_dir, start):
    used = set()
    for m in list_mods(game_dir):
        used.update(m.pv_ids)
    i = int(start)
    while i in used:
        i += 1
    return i
