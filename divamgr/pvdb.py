"""mod_pv_db.txt generation. Keys must be sorted lexicographically ascending or the game fails to parse."""
from datetime import date

from .dsc import SIGNATURE

DIFFICULTIES = ("easy", "normal", "hard", "extreme", "extra")
DIFF_LABELS = {"easy": "Fácil", "normal": "Normal", "hard": "Difícil", "extreme": "Extremo", "extra": "Extra Extremo"}
DIFF_SHORT = {"easy": "F", "normal": "N", "hard": "D", "extreme": "E", "extra": "EX"}


def script_name(pv_id, difficulty):
    """DSC file name: Extra Extreme is the game's second Extreme chart (pv_XXX_extreme_1.dsc)."""
    return f"pv_{pv_id:03d}_{'extreme_1' if difficulty == 'extra' else difficulty}.dsc"
CHARACTERS = {
    "MIK": "Hatsune Miku", "RIN": "Kagamine Rin", "LEN": "Kagamine Len", "LUK": "Megurine Luka",
    "KAI": "KAITO", "MEI": "MEIKO", "HAK": "Yowane Haku", "NER": "Akita Neru",
    "SAK": "Sakine Meiko", "TET": "Kasane Teto",
}


def level_str(stars):
    """6.5 -> PV_LV_06_5"""
    stars = round(stars * 2) / 2
    whole = int(stars)
    return f"PV_LV_{whole:02d}_{5 if stars - whole else 0}"


def _clean(s):
    return " ".join(str(s).replace("=", "-").split())


def build(pv_id, title, artist, bpm, charts, sabi_start, sabi_len, chara="MIK", has_movie=True):
    """charts: {difficulty: stars} for the difficulties that have a DSC file."""
    p = f"pv_{pv_id:03d}"
    title, artist = _clean(title) or p, _clean(artist)
    kv = {
        f"{p}.bpm": str(int(round(bpm))),
        f"{p}.date": date.today().strftime("%Y%m%d"),
        f"{p}.performer.0.chara": chara,
        f"{p}.performer.0.type": "VOCAL",
        f"{p}.performer.num": "1",
        f"{p}.sabi.play_time": f"{sabi_len:.3f}",
        f"{p}.sabi.start_time": f"{sabi_start:.3f}",
        f"{p}.song_file_name": f"rom/sound/song/{p}.ogg",
        f"{p}.song_name": title,
        f"{p}.song_name_en": title,
        f"{p}.song_name_reading": title,
    }
    if artist:
        for k in ("songinfo", "songinfo_en"):
            kv[f"{p}.{k}.lyrics"] = artist
            kv[f"{p}.{k}.music"] = artist
    if has_movie:
        # The game swaps .mp4 for the .usm container on load.
        kv[f"{p}.movie_file_name"] = f"rom/movie/{p}.mp4"
        kv[f"{p}.movie_surface"] = "FRONT"
    def chart(group, index, d):
        q = f"{p}.difficulty.{group}.{index}"
        kv[f"{q}.edition"] = "1" if d == "extra" else "0"
        kv[f"{q}.level"] = level_str(charts[d])
        kv[f"{q}.level_sort_index"] = "20"
        kv[f"{q}.script_file_name"] = f"rom/script/{script_name(pv_id, d)}"
        kv[f"{q}.script_format"] = f"0x{SIGNATURE:08X}"
        kv[f"{q}.version"] = "1"
        if d == "extra":
            kv[f"{q}.attribute.extra"] = "1"
            kv[f"{q}.attribute.original"] = "0"
            kv[f"{q}.attribute.slide"] = "1"

    for d in ("easy", "normal", "hard"):
        if d in charts:
            chart(d, 0, d)
        kv[f"{p}.difficulty.{d}.length"] = "1" if d in charts else "0"
    # Extreme and Extra Extreme share the "extreme" group; Extra Extreme is the entry with attribute.extra
    extremes = [d for d in ("extreme", "extra") if d in charts]
    for index, d in enumerate(extremes):
        chart("extreme", index, d)
    kv[f"{p}.difficulty.extreme.length"] = str(len(extremes))
    keys = sorted(kv, key=lambda k: k.encode("utf-8"))
    return "".join(f"{k}={kv[k]}\n" for k in keys)
