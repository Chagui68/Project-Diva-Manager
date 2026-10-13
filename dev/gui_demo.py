"""Opens the GUI with demo data (fake game folder, download window with a sample queue) to review the
design. Nothing touches the real game or the network. Run: python dev\\gui_demo.py [segundos]"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from divamgr import app as A, download, paths  # noqa: E402
from synth import make_song  # noqa: E402
from test_pipeline import fake_game  # noqa: E402
from divamgr import songs  # noqa: E402


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 0
    paths.save_settings = lambda s: None
    download.probe = lambda url: {"AAA": ("Canción de ejemplo", "Artista Uno", 204.0),
                                  "BBB": ("Otra canción", "Artista Dos", 187.0)}.get(url[-3:], ("", "", 0.0))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        game = fake_game(tmp)
        wav = make_song(os.path.join(tmp, "demo.wav"), 128.0, duration=30)
        songs.import_song(game, songs.SongRequest(source=wav, title="Canción demo", artist="Diva Manager",
                                                  pv_id=9501), None, None, log=lambda m: None)
        app = A.App()
        app.geometry("1180x760+0+0")
        app.settings["game_dir"] = game
        app.refresh()
        app._log_now("Listo. Demo del diseño.")
        dlg = A.UrlImportDialog(app)
        dlg.geometry("+40+20")
        dlg.add_urls("https://youtu.be/AAA https://youtu.be/BBB https://youtu.be/CCC")
        if seconds:
            app.after(int(seconds * 1000), app.destroy)
        app.mainloop()


if __name__ == "__main__":
    main()
