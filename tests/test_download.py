"""URL import flow without network: yt-dlp's download is replaced by a local synthetic video.
Run: python tests\\test_download.py"""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from divamgr import app as A, download, paths  # noqa: E402
from synth import make_song  # noqa: E402
from test_pipeline import fake_game  # noqa: E402


def main():
    urls, invalid = download.parse_urls("https://youtu.be/AAA\n https://www.youtube.com/watch?v=BBB  nope\n"
                                        "https://youtu.be/AAA")
    assert urls == ["https://youtu.be/AAA", "https://www.youtube.com/watch?v=BBB"] and invalid == ["nope"]
    assert download.split_title("Autor - Mi Canción [Official MV]") == ("Mi Canción", "Autor")
    assert download.split_title("Mi Canción (PV)", "Autor") == ("Mi Canción", "Autor")

    ff = paths.find_tool("ffmpeg")
    assert ff, "hace falta FFmpeg para esta prueba"
    paths.save_settings = lambda s: None
    with tempfile.TemporaryDirectory() as tmp:
        game = fake_game(tmp)
        wav = make_song(os.path.join(tmp, "s.wav"), 140.0, duration=35)
        mp4 = os.path.join(tmp, "video.mp4")
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=size=640x360:rate=30", "-i", wav, "-shortest", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", mp4], check=True)

        calls = []

        def fake_download(url, out_dir, ffmpeg, progress=lambda f: None, log=print):
            calls.append(url)
            progress(1.0)
            if url.endswith("ROTO"):
                raise RuntimeError("video no disponible")
            return mp4, f"Canción {len(calls)}", "Autor"

        download.download = fake_download
        download.probe = lambda url: (f"Título {url[-3:]}", "Autor", 185.0)
        app = A.App()
        app.settings["game_dir"] = game
        app.refresh()
        dlg = A.UrlImportDialog(app)
        invalid = dlg.add_urls("https://youtu.be/UNO\nhttps://youtu.be/ROTO https://youtu.be/UNO\nnada\n")
        dlg.url_var.set("https://youtu.be/DOS")  # left in the entry: start adds it too
        assert invalid == ["nada"]
        for _ in range(20):
            app.update()
            time.sleep(0.05)
        rows = [dlg.tree.item(i["iid"], "values") for i in dlg.items]
        assert rows[0][1] == "Título UNO" and rows[0][3] == "3:05", rows[0]
        dlg.rights_var.set(True)
        dlg.ok()
        assert len(dlg.items) == 3
        deadline = time.time() + 240
        while app.busy and time.time() < deadline:
            app.update()
            time.sleep(0.05)
        for _ in range(10):
            app.update()
            time.sleep(0.05)
        status = [dlg.tree.set(i["iid"], "status") for i in dlg.items]
        imported = sorted(m.name for m in app.mods if m.managed)
        print("descargas:", calls)
        print("estado:", status)
        print("importadas:", imported)
        assert calls == ["https://youtu.be/UNO", "https://youtu.be/ROTO", "https://youtu.be/DOS"]
        assert imported == ["Canción 1", "Canción 3"], "un fallo no debe frenar el resto"
        assert status[0].startswith("✔") and status[1].startswith("✖") and status[2].startswith("✔")
        app.destroy()
    print("\nTODO OK")


if __name__ == "__main__":
    main()
