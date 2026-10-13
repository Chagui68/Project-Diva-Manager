"""GUI smoke test on a fake game folder: main window, preview, single and batch import dialogs.
Run: python tests\\test_gui.py"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from divamgr import app as A, paths  # noqa: E402
from synth import make_song  # noqa: E402
from test_pipeline import fake_game  # noqa: E402


def main():
    paths.save_settings = lambda s: None  # never touch the real settings.json
    with tempfile.TemporaryDirectory() as tmp:
        game = fake_game(tmp)
        files = [make_song(os.path.join(tmp, f"Artista {i} - Canción {i}.wav"), bpm, duration=40)
                 for i, bpm in ((1, 110.0), (2, 150.0))]

        app = A.App()
        app.settings["game_dir"] = game
        app.refresh()
        app.update()

        dlg = A.ImportDialog(app, files[0])
        app.update()
        assert dlg.title_var.get() == "Canción 1" and dlg.artist_var.get() == "Artista 1"
        dlg.destroy()

        batch = A.BatchImportDialog(app, files)
        app.update()
        assert [i[1] for i in batch.items] == ["Canción 1", "Canción 2"]
        batch.ok()
        deadline = time.time() + 180
        while app.busy and time.time() < deadline:
            app.update()
            time.sleep(0.05)
        app.update()

        songs_ = [m for m in app.mods if m.managed]
        print("importadas:", [(m.name, m.pv_ids) for m in songs_])
        assert len(songs_) == 2, "deben importarse las dos canciones"
        assert sorted(i for m in songs_ for i in m.pv_ids) == [9501, 9502], "IDs automáticos distintos"

        pw = A.PreviewWindow(app, songs_[0])
        pw.t_var.set(10)
        pw.draw()
        app.update()
        assert pw.canvas.find_all(), "la vista previa debe dibujar notas"
        app.destroy()
    print("\nTODO OK")


if __name__ == "__main__":
    main()
