# Diva Manager

Song manager for **Hatsune Miku: Project DIVA Mega Mix+** (Steam), with its own mod loader,
[DivaLoader](loader/README.md). DivaModLoader mods work too.

- Imports songs from `.mp4` (also `.mkv`, `.webm`, `.mov`, `.mp3`, `.m4a`, `.ogg`, `.wav`, `.flac`) or from a URL.
- Generates the notes automatically from the audio for Easy, Normal, Hard, Extreme and Extra Extreme,
  including multi-notes (2 to 4 buttons at once), L/R slides and chain slides.
- Converts the video to a 720p constant-frame-rate (max 30 fps) `.usm`, the container the game uses.
- Enables, disables, reorders (priority) and deletes mods.
- Installs or updates DivaLoader in the game folder.
- Launches the game through Steam.

The interface is in Spanish; button names below are quoted as they appear in the app.

## Requirements

- Python 3.12 with the packages in `requirements.txt`:
  ```bash
  python -m pip install --user -r requirements.txt
  ```
- FFmpeg (provides `ffmpeg.exe` and `ffprobe.exe`). Required to import `.mp4` files:
  ```bash
  winget install Gyan.FFmpeg
  ```
  If it is not on the PATH, use the **Buscar…** (Browse) button and point it to `ffmpeg.exe`.
- DivaLoader: the repository ships a prebuilt copy in `loader\bin\dinput8.dll`. Install it with the
  **Instalar DivaLoader** button in the manager. You only need to compile it (`loader\build.bat`, with
  Visual Studio Build Tools and C++) if you change the loader code.
- yt-dlp, optional: only needed to download from a URL. The manager offers to install it the first time.

## Usage

Double-click `diva_manager.pyw`, or run:

```bash
python diva_manager.pyw
```

1. **➕ Importar archivos** (Import files): pick one or more files and set title, artist, character, PV ID,
   difficulties, note density and video codec. Several files are imported in one batch with the same settings.
2. **🌐 Descargar desde URL** (Download from URL): paste video URLs. Works with YouTube and the other sites
   supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp). The queue shows title, artist, duration and the
   status of each song. Videos are saved to `downloads/` (max 720p) before being imported. Only use videos you
   have the right to download and use: your own, freely licensed, or with the author's permission.
3. Each song is stored as its own mod in `mods/DivaManager_pv<ID>_<title>/`.
4. **Vista previa** (Preview): shows the generated notes on the game screen and on a timeline.
5. **Regenerar…** (Regenerate): makes another variation (seed), changes the density, shifts the notes by an
   **offset** in ms if they arrive before or after the music, and can rebuild the video.
   **Actualizar todas** (Update all) applies the current sync, Extra Extreme and the 720p video to every song.
6. **▶ Jugar** (Play): starts the game with `steam://rungameid/1761390`.

To play with mods there is nothing extra to run: DivaLoader (`dinput8.dll` in the game folder) is loaded by
the game itself when you start it from Steam or with **▶ Jugar**.

## How the notes are generated

The analysis lives in `divamgr/analysis.py` and only uses numpy and scipy (librosa is avoided because its
`numba` dependency can be blocked by Windows Application Control).

| Element | How it is derived from the song |
|---|---|
| Tempo and beat | Rough tempo from autocorrelation and beat tracking, then period and phase are fitted to the whole song by folding the onsets into 2 ms bins. The bass decides between beat and off-beat, and 16-beat windows verify the fit or follow the drift when the tempo is not constant. |
| Bars | Bar phase where the low hits (kick drum) fall. |
| Note timing | Strong onsets quantised to the grid (quarter, eighth or sixteenth notes depending on difficulty). Louder sections get more notes. |
| Button (△ ○ × □) | The frequency band that stands out on that hit: low = ×, low-mid = ○, high-mid = □, high = △. Fast streams share a button, as in official charts. |
| Holds | Tonal sounds that keep ringing for more than a beat (long vocals or synths). |
| Multi-notes | Accents where every band hits at once (cymbal, kick and chord): 2 buttons from Normal, 3 on Hard and up to 4 on Extreme and Extra Extreme, only on the strongest hits. Two buttons form a row, three a triangle and four a square, so the count can be read from the shape. |
| Slides (L/R) | Bright hits where the highs stand out. The direction follows the melody: rising = R, falling = L. If the sound sustains, it becomes a chain slide. |
| Screen position | Curved paths that follow the phrases; the height follows the brightness and pitch of the melody. |
| Stars | Computed from the notes per second. |
| Song select preview | The loudest 30 s section, aligned to a bar. |

## Files generated per song

```
mods/DivaManager_pv9500_Title/
├── config.toml
├── diva_manager.json            data used to regenerate
└── rom/
    ├── mod_pv_db.txt            song entry (keys sorted)
    ├── script/pv_9500_<difficulty>.dsc
    ├── sound/song/pv_9500.ogg   Vorbis, 44100 Hz
    └── movie/pv_9500.usm        H.264 or VP9 in a CriWare container
```

Charts are Future Tone DSC scripts (`script_format=0x15122517`). Extra Extreme is stored as
`pv_<ID>_extreme_1.dsc`.

## Limitations

- No cover, background, logo or thumbnail sprites are generated; the song shows without a jacket in the menu.
- No lyrics are generated.
- H.264 video does not play on Linux or Steam Deck. Choose VP9 for those, which is slower to convert.
- If a PV ID clashes with a mod that is not installed there will be a conflict; the manager only avoids the
  IDs of the mods present.

## Tests and development tools

| Path | Purpose |
|---|---|
| `tests\test_charts.py` | Tempo, beat alignment, DSC notes, multi-note shapes and `pv_db` ordering on synthetic songs at 97, 128 and 174 BPM. |
| `tests\test_pipeline.py` | Imports a full song into a fake game folder without touching the real game. With FFmpeg it also tests `.mp4` and `.usm`. |
| `tests\test_download.py` | URL → download → import flow with a simulated download (no network). |
| `tests\test_gui.py` | Main window, preview and batch import on a fake game. |
| `tests\test_video.py` | `.usm` conversion: correct frame rate in the header, 720p and exact duration. |
| `loader\tests\build_test.bat` | Tests for DivaLoader's hook engine and TOML reader. |
| `dev\check_env.py` | Checks Python packages, FFmpeg, yt-dlp, DivaLoader (built and installed) and mods. |
| `dev\update_all.py` | Command-line "Update all"; `--sin-video` regenerates only the notes. |
| `dev\sync_report.py` | Tempo, constant-tempo fit and drift of the imported songs. |
| `dev\chart_report.py` | Note statistics per difficulty for the imported songs, without writing anything. |
| `dev\gui_demo.py` and `dev\capture_window.ps1` | Open the interface with sample data and capture a window to review the design. |
| `dev\sigcheck.py` | After a game update, checks that DivaLoader's signatures are still in place in `DivaMegaMix.exe`. |
| `dev\trygame.ps1` | Installs the freshly built loader, starts the game and prints `DivaLoader.log`. `-Skip` disables parts to isolate a crash. |
| `dev\cpk.py` | Lists and extracts files from the game's `.cpk` archives. |

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the projects DivaLoader builds on.
