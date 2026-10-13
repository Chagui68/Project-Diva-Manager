"""Full import pipeline on a fake game folder (the real game is never touched).
With FFmpeg available it also builds an .mp4 and checks the .usm conversion.
Run: python tests\\test_pipeline.py"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from divamgr import dsc, modloader, paths, songs  # noqa: E402
from synth import make_song  # noqa: E402


def fake_game(base):
    game = os.path.join(base, "game")
    os.makedirs(os.path.join(game, "mods", "OtherMod", "rom"))
    open(os.path.join(game, paths.GAME_EXE), "w").close()
    with open(os.path.join(game, "config.toml"), "w") as f:
        f.write('enabled = true\nconsole = false\nmods = "mods"\npriority = [\n  "OtherMod",\n]\n')
    with open(os.path.join(game, "mods", "OtherMod", "config.toml"), "w") as f:
        f.write('enabled = true\ninclude = ["."]\nname = "Other"\n')
    with open(os.path.join(game, "mods", "OtherMod", "rom", "mod_pv_db.txt"), "w") as f:
        f.write("pv_9500.bpm=120\n")
    return game


def main():
    ff, fp = paths.find_tool("ffmpeg"), paths.find_tool("ffprobe")
    with tempfile.TemporaryDirectory() as tmp:
        game = fake_game(tmp)
        source = make_song(os.path.join(tmp, "song.wav"))
        if ff:
            mp4 = os.path.join(tmp, "Tester - Prueba.mp4")
            subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=30", "-i", source, "-shortest", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", mp4], check=True)
            source = mp4

        pid = modloader.free_pv_id(game, 9500)
        assert pid == 9501, "debe saltar el ID usado por otro mod"
        req = songs.SongRequest(source=source, title="Prueba Síntesis", artist="Tester", pv_id=pid)
        path = songs.import_song(game, req, ff, fp, log=print)

        p = f"pv_{pid}"
        expect = [f"rom/mod_pv_db.txt", f"rom/sound/song/{p}.ogg"] + [f"rom/script/{p}_{d}.dsc" for d in
                                                                         ("easy", "normal", "hard", "extreme")]
        if ff:
            expect.append(f"rom/movie/{p}.usm")
        for rel in expect:
            assert os.path.isfile(os.path.join(path, rel)), rel
        if ff:
            with open(os.path.join(path, "rom", "movie", p + ".usm"), "rb") as f:
                assert f.read(4) == b"CRID", "USM inválido"

        prio = modloader.get_priority(game)
        assert prio[0] == os.path.basename(path), "el mod nuevo debe ir primero en la prioridad"
        mod = next(m for m in modloader.list_mods(game) if m.managed)
        modloader.set_enabled(mod.path, False)
        assert not next(m for m in modloader.list_mods(game) if m.managed).enabled
        modloader.set_enabled(mod.path, True)

        songs.regenerate(mod, 1.2, 3, ["hard"], log=print)
        assert os.listdir(os.path.join(path, "rom", "script")) == [f"{p}_hard.dsc"]
        assert dsc.read_targets(os.path.join(path, "rom", "script", f"{p}_hard.dsc"))
    print("\nTODO OK" + ("" if ff else " (sin FFmpeg: no se probó el video)"))


if __name__ == "__main__":
    main()
