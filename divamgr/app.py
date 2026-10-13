"""Tkinter GUI for Diva Manager."""
import os
import queue
import re
import shutil
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from . import __version__, download, media, modloader, paths, pvdb, songs
from . import theme as T
from .chartgen import CHAIN_L, CHAIN_R, SLIDE_L, SLIDE_R
from .dsc import read_targets

BUTTON_STYLE = {0: ("△", "#2fbf71"), 1: ("○", "#ff4d6d"), 2: ("×", "#4d9dff"), 3: ("□", "#e76bd0")}
SLIDE_STYLE = {SLIDE_L: ("◀", "#ffd23f"), SLIDE_R: ("▶", "#ffd23f"), CHAIN_L: ("◂", "#ffb000"),
               CHAIN_R: ("▸", "#ffb000")}
VIDEO_CHOICES = [("H.264 720p (rápido, Windows)", "h264"), ("VP9 720p (Linux/Steam Deck, lento)", "vp9"),
                 ("Sin video", "none")]
STATUS_COLORS = {"pending": T.MUTED, "working": T.INFO, "ok": T.OK, "error": T.DANGER}


def note_style(note_type):
    return SLIDE_STYLE.get(note_type) or BUTTON_STYLE.get(note_type % 4, ("?", T.TEXT))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Diva Manager {__version__}")
        self.geometry("1180x760")
        self.minsize(980, 620)
        T.apply(self)
        self.settings = paths.load_settings()
        if not paths.is_game_dir(self.settings.get("game_dir")):
            self.settings["game_dir"] = paths.find_game() or ""
            paths.save_settings(self.settings)
        self.events = queue.Queue()
        self.busy = False
        self.mods = []
        self._build()
        self.refresh()
        self.after(100, self._poll)

    # ---------- layout ----------
    def _build(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(20, 14))
        header.pack(fill="x")
        titles = ttk.Frame(header, style="Header.TFrame")
        titles.pack(side="left")
        ttk.Label(titles, text="Diva Manager", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Canciones y mods para Hatsune Miku: Project DIVA Mega Mix+",
                  style="Subtitle.TLabel").pack(anchor="w")
        ttk.Button(header, text="▶  Jugar", style="Accent.TButton", command=self.play).pack(side="right")

        # status chips: game / loader / ffmpeg
        chips = ttk.Frame(self, padding=(20, 12, 20, 0))
        chips.pack(fill="x")
        self.chip_vars = {}
        for col, (key, label, action, command) in enumerate((
                ("game", "JUEGO", "Cambiar…", self.pick_game),
                ("loader", "MOD LOADER", "Instalar", self.install_loader),
                ("ffmpeg", "FFMPEG", "Buscar…", self.pick_ffmpeg))):
            card = ttk.Frame(chips, style="Card.TFrame", padding=(14, 10))
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 10, 0))
            chips.columnconfigure(col, weight=1, uniform="chips")
            ttk.Label(card, text=label, style="CardMuted.TLabel", font=(T.FONT, 8, "bold")).grid(row=0, column=0,
                                                                                             sticky="w")
            state = tk.StringVar()
            detail = tk.StringVar()
            state_label = ttk.Label(card, textvariable=state, style="Ok.TLabel")
            state_label.grid(row=1, column=0, sticky="w")
            ttk.Label(card, textvariable=detail, style="CardMuted.TLabel", font=(T.FONT, 8)).grid(
                row=2, column=0, sticky="w")
            button = ttk.Button(card, text=action, style="Small.TButton", command=command)
            button.grid(row=0, column=1, rowspan=3, sticky="e", padx=(10, 0))
            card.columnconfigure(0, weight=1)
            self.chip_vars[key] = (state, detail, state_label, button)

        bar = ttk.Frame(self, padding=(20, 14, 20, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="🌐  Descargar desde URL", style="Accent.TButton",
                   command=self.url_dialog).pack(side="left")
        ttk.Button(bar, text="➕  Importar archivos", command=self.import_dialog).pack(side="left", padx=(8, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        for text, command in (("Activar / Desactivar", self.toggle), ("Regenerar…", self.regen_dialog),
                              ("Vista previa", self.preview)):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="▲", width=3, command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(bar, text="▼", width=3, command=lambda: self.move(1)).pack(side="left", padx=(4, 6))
        ttk.Button(bar, text="Eliminar", style="Danger.TButton", command=self.delete).pack(side="left")
        ttk.Button(bar, text="⟳", width=3, command=self.refresh).pack(side="right")
        ttk.Button(bar, text="Abrir carpeta", command=self.open_folder).pack(side="right", padx=6)
        ttk.Button(bar, text="Actualizar todas", command=self.update_all).pack(side="right")

        mid = ttk.Frame(self, padding=(20, 0, 20, 0))
        mid.pack(fill="both", expand=True)
        cols = ("on", "name", "artist", "pv", "info", "folder")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        for c, label, w, anchor in (("on", "", 40, "center"), ("name", "CANCIÓN / MOD", 260, "w"),
                                    ("artist", "ARTISTA", 170, "w"), ("pv", "PV ID", 70, "center"),
                                    ("info", "DETALLES", 220, "w"), ("folder", "CARPETA", 230, "w")):
            self.tree.heading(c, text=label, anchor=anchor)
            self.tree.column(c, width=w, anchor=anchor, stretch=c in ("name", "info", "folder"))
        self.tree.tag_configure("off", foreground="#62657f")
        self.tree.tag_configure("mod", foreground=T.MUTED)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.toggle())

        bottom = ttk.Frame(self, padding=(20, 10, 20, 16))
        bottom.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, maximum=1000)
        self.progress.pack(fill="x")
        self.log_box = T.text_widget(bottom, height=7, state="disabled", wrap="word")
        self.log_box.pack(fill="x", pady=(8, 0))

    # ---------- helpers ----------
    @property
    def game(self):
        return self.settings.get("game_dir", "")

    def ffmpeg(self):
        return paths.find_tool("ffmpeg", self.settings.get("ffmpeg", ""))

    def ffprobe(self):
        return paths.find_tool("ffprobe", self.settings.get("ffmpeg", ""))

    def log(self, msg):
        self.events.put(("log", msg))

    def _log_now(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                if kind == "log":
                    self._log_now(val)
                elif kind == "progress":
                    self.progress["value"] = val * 1000
                elif kind == "call":
                    val()
                elif kind == "done":
                    self.busy = False
                    self.refresh()
                    if val:
                        messagebox.showerror("Error", val, parent=self)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def run_task(self, fn):
        if self.busy:
            messagebox.showinfo("Ocupado", "Espera a que termine la tarea actual.", parent=self)
            return False
        self.busy = True
        self.progress["value"] = 0

        def worker():
            err = ""
            try:
                fn()
            except Exception as e:  # report every failure in the GUI
                err = str(e) or e.__class__.__name__
                self.log("ERROR: " + err)
                self.log(traceback.format_exc(limit=3))
            self.events.put(("done", err))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selecciona", "Selecciona una canción o mod de la lista.", parent=self)
            return None
        return next((m for m in self.mods if m.folder == sel[0]), None)

    def need_game(self):
        if not paths.is_game_dir(self.game):
            messagebox.showwarning("Juego", "No se encontró DivaMegaMix.exe. Usa «Cambiar…».", parent=self)
            return False
        return True

    def _chip(self, key, ok, state, detail, action=None):
        state_var, detail_var, label, button = self.chip_vars[key]
        state_var.set(state)
        detail_var.set(detail if len(detail) < 60 else "…" + detail[-58:])
        label.configure(style={True: "Ok.TLabel", False: "Bad.TLabel", None: "Warn.TLabel"}[ok])
        if action:
            button.configure(text=action)

    # ---------- actions ----------
    def refresh(self):
        g = self.game
        has_game = paths.is_game_dir(g)
        self._chip("game", has_game, "Encontrado" if has_game else "No encontrado", g or "Selecciona la carpeta")
        if has_game:
            kind = modloader.loader_kind(g)
            if kind == modloader.LOADER_NAME:
                self._chip("loader", True, "DivaLoader activo", "dinput8.dll", "Actualizar")
            elif kind == "otro":
                self._chip("loader", None, "Otro loader", "dinput8.dll ajeno (p. ej. DivaModLoader)", "Instalar")
            else:
                self._chip("loader", False, "No instalado", "El juego no cargará las canciones", "Instalar")
        else:
            self._chip("loader", False, "—", "")
        ff, fp = self.ffmpeg(), self.ffprobe()
        self._chip("ffmpeg", bool(ff and fp), "Disponible" if ff and fp else "No encontrado",
                   ff or "winget install Gyan.FFmpeg")

        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.mods = modloader.list_mods(g) if has_game else []
        for m in self.mods:
            tags = [] if m.enabled else ["off"]
            if m.managed:
                md = m.meta
                diffs = " ".join(pvdb.DIFF_SHORT[d] for d in pvdb.DIFFICULTIES if d in md.get("difficulties", []))
                offset = md.get("offset_ms", 0)
                info = f"{md.get('bpm', '?')} BPM · {diffs}" + (f" · {offset:+.0f} ms" if offset else "")
                artist = md.get("artist", "")
            else:
                info = f"Mod · v{m.version}" if m.version else "Mod"
                artist = m.author
                tags.append("mod")
            pv = ",".join(map(str, m.pv_ids[:3])) + ("…" if len(m.pv_ids) > 3 else "")
            self.tree.insert("", "end", iid=m.folder, tags=tags,
                             values=("●" if m.enabled else "○", m.name, artist, pv, info, m.folder))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])

    def pick_game(self):
        d = filedialog.askdirectory(title="Carpeta de Project DIVA Mega Mix+", parent=self)
        if d:
            if not paths.is_game_dir(d):
                messagebox.showerror("Juego", f"No hay {paths.GAME_EXE} en esa carpeta.", parent=self)
                return
            self.settings["game_dir"] = os.path.normpath(d)
            paths.save_settings(self.settings)
            self.refresh()

    def pick_ffmpeg(self):
        f = filedialog.askopenfilename(title="Selecciona ffmpeg.exe", filetypes=[("ffmpeg.exe", "ffmpeg.exe")],
                                       parent=self)
        if f:
            self.settings["ffmpeg"] = os.path.normpath(f)
            paths.save_settings(self.settings)
            if not self.ffprobe():
                messagebox.showwarning("FFmpeg", "No hay ffprobe.exe junto a ese ffmpeg.exe.", parent=self)
            self.refresh()

    def install_loader(self):
        if not self.need_game():
            return
        if not os.path.isfile(modloader.LOADER_BUILD):
            messagebox.showerror("DivaLoader", "DivaLoader no está compilado. Ejecuta loader\\build.bat.", parent=self)
            return
        extra = ("\n\nEl dinput8.dll actual (otro loader) se guardará como dinput8.dll.bak."
                 if modloader.loader_kind(self.game) == "otro" else "")
        if messagebox.askyesno("DivaLoader", f"Se copiará DivaLoader (dinput8.dll) en:\n{self.game}{extra}\n\n"
                               "¿Continuar?", parent=self):
            modloader.install_loader(self.game, self.log)
            self.refresh()

    def toggle(self):
        m = self.selected()
        if m:
            modloader.set_enabled(m.path, not m.enabled)
            self.refresh()

    def move(self, step):
        m = self.selected()
        if not m:
            return
        prio = modloader.get_priority(self.game)
        if prio is None:
            messagebox.showinfo("Prioridad", "El config.toml del loader no tiene lista de prioridad: "
                                "los mods cargan en orden alfabético.", parent=self)
            return
        folders = [x.folder for x in self.mods]
        i = folders.index(m.folder)
        j = i + step
        if 0 <= j < len(folders):
            folders[i], folders[j] = folders[j], folders[i]
            modloader.set_priority(self.game, folders)
            self.refresh()

    def delete(self):
        m = self.selected()
        if not m:
            return
        if messagebox.askyesno("Eliminar", f"Se borrará permanentemente la carpeta:\n{m.path}\n\n¿Continuar?",
                               icon="warning", parent=self):
            shutil.rmtree(m.path)
            prio = modloader.get_priority(self.game)
            if prio and m.folder in prio:
                modloader.set_priority(self.game, [p for p in prio if p != m.folder])
            self.log(f"Eliminado {m.folder}")
            self.refresh()

    def open_folder(self):
        m = self.tree.selection()
        target = next((x.path for x in self.mods if m and x.folder == m[0]), None)
        target = target or (modloader.mods_dir(self.game) if paths.is_game_dir(self.game) else None)
        if target and os.path.isdir(target):
            os.startfile(target)

    def play(self):
        if paths.is_game_dir(self.game) and not modloader.is_installed(self.game):
            if not messagebox.askyesno("Mod loader", "No hay mod loader instalado: las canciones "
                                       "importadas no aparecerán. ¿Abrir el juego igualmente?", parent=self):
                return
        os.startfile(f"steam://rungameid/{paths.APP_ID}")

    def import_dialog(self):
        if not self.need_game():
            return
        files = filedialog.askopenfilenames(
            title="Selecciona una o varias canciones",
            filetypes=[("Video/Audio", "*.mp4 *.mkv *.webm *.mov *.ogg *.wav *.flac *.mp3 *.m4a"),
                       ("Video MP4", "*.mp4"), ("Todos", "*.*")], parent=self)
        if len(files) == 1:
            ImportDialog(self, files[0])
        elif files:
            BatchImportDialog(self, list(files))

    def url_dialog(self):
        if not self.need_game():
            return
        if not self.ffmpeg():
            messagebox.showerror("FFmpeg", "Se necesita FFmpeg para descargar e importar video.", parent=self)
            return
        if download.available():
            UrlImportDialog(self)
            return
        if messagebox.askyesno("yt-dlp", "Para descargar por URL hace falta yt-dlp (herramienta de código abierto).\n"
                               "¿Instalarlo ahora con pip?", parent=self):
            def task():
                download.install(self.log)
                self.events.put(("call", lambda: UrlImportDialog(self)))

            self.run_task(task)

    def regen_dialog(self):
        m = self.selected()
        if not m:
            return
        if not m.managed:
            messagebox.showinfo("Regenerar", "Solo para canciones importadas con Diva Manager.", parent=self)
            return
        RegenDialog(self, m)

    def update_all(self):
        """Re-analyse every Diva Manager song (new sync, all difficulties incl. Extra Extreme) and
        rebuild its movie when the original file is still there."""
        managed = [m for m in self.mods if m.managed]
        if not managed:
            messagebox.showinfo("Actualizar", "No hay canciones de Diva Manager.", parent=self)
            return
        if not messagebox.askyesno(
                "Actualizar todas",
                f"Se actualizarán {len(managed)} canciones:\n\n"
                "• Sincronización nueva de las notas\n"
                "• Todas las dificultades, incluida Extra Extremo\n"
                "• Video reconvertido a 720p (si el archivo original sigue en su sitio)\n\n"
                "Tarda alrededor de 1 minuto por canción. ¿Continuar?", parent=self):
            return
        ff, fp = self.ffmpeg(), self.ffprobe()

        def task():
            failed = []
            for n, mod in enumerate(managed, 1):
                md = mod.meta
                self.log(f"[{n}/{len(managed)}] {mod.name}")
                try:
                    songs.regenerate(mod, md.get("density", 1.0), md.get("seed", 0), list(pvdb.DIFFICULTIES),
                                     offset_ms=md.get("offset_ms", 0.0), video=md.get("video", "h264"),
                                     ffmpeg=ff, ffprobe=fp, log=self.log,
                                     progress=lambda f, n=n: self.events.put(("progress", (n - 1 + f) / len(managed))))
                except Exception as e:  # keep going with the rest
                    failed.append(mod.name)
                    self.log(f"  ERROR: {e}")
            self.log(f"Actualización terminada: {len(managed) - len(failed)} de {len(managed)} canciones.")
            if failed:
                raise RuntimeError("No se actualizaron: " + ", ".join(failed))

        self.run_task(task)

    def preview(self):
        m = self.selected()
        if m:
            PreviewWindow(self, m)


def guess_meta(ffprobe, source):
    """(title, artist) from the file's tags, or from an "Artist - Title" file name."""
    stem = os.path.splitext(os.path.basename(source))[0]
    title, artist = stem, ""
    if ffprobe:
        try:
            info = media.media_info(ffprobe, source)
            title, artist = info["title"] or title, info["artist"]
        except media.MediaError:
            pass
    if not artist and " - " in title:
        artist, title = [s.strip() for s in title.split(" - ", 1)]
    title = re.sub(r"\s*\[[A-Za-z0-9_-]{11}\]$", "", title)  # yt-dlp video id
    title = re.sub(r"\s*[\[(](official|mv|pv|video|lyrics?|audio)[^\])]*[\])]", "", title, flags=re.I).strip()
    return title, artist


def build_shared_settings(dlg, parent, app):
    """Character, difficulties, density and video settings shared by the batch dialogs, in a card."""
    card = ttk.Frame(parent, style="Card.TFrame", padding=14)
    ttk.Label(card, text="AJUSTES DE LAS CANCIONES", style="Section.TLabel").grid(row=0, column=0, columnspan=2,
                                                                              sticky="w", pady=(0, 8))
    dlg.chara_var = tk.StringVar(value="MIK — Hatsune Miku")
    ttk.Label(card, text="Personaje", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 14))
    ttk.Combobox(card, textvariable=dlg.chara_var, state="readonly", width=26,
                 values=[f"{k} — {v}" for k, v in pvdb.CHARACTERS.items()]).grid(row=1, column=1, sticky="w")
    ttk.Label(card, text="Dificultades", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=4)
    df = ttk.Frame(card, style="Card.TFrame")
    df.grid(row=2, column=1, sticky="w")
    dlg.diff_vars = {}
    for d in pvdb.DIFFICULTIES:
        v = tk.BooleanVar(value=True)
        dlg.diff_vars[d] = v
        ttk.Checkbutton(df, text=pvdb.DIFF_LABELS[d], variable=v, style="Card.TCheckbutton").pack(side="left",
                                                                                                 padx=(0, 10))
    ttk.Label(card, text="Densidad de notas", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=4)
    dens = ttk.Frame(card, style="Card.TFrame")
    dens.grid(row=3, column=1, sticky="w")
    dlg.density_var = tk.DoubleVar(value=1.0)
    ttk.Scale(dens, from_=0.6, to=1.5, variable=dlg.density_var, length=240).pack(side="left")
    value = ttk.Label(dens, text="1.00×", style="CardMuted.TLabel", width=6)
    value.pack(side="left", padx=8)
    dlg.density_var.trace_add("write", lambda *_: value.configure(text=f"{dlg.density_var.get():.2f}×"))
    ttk.Label(card, text="Video", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=4)
    dlg.video_var = tk.StringVar(value=next(lbl for lbl, k in VIDEO_CHOICES
                                            if k == app.settings.get("video_codec", "h264")))
    ttk.Combobox(card, textvariable=dlg.video_var, state="readonly", width=36,
                 values=[lbl for lbl, _ in VIDEO_CHOICES]).grid(row=4, column=1, sticky="w")
    return card


def read_shared_settings(dlg):
    """-> (difficulties, chara, density, video) or None after showing an error."""
    diffs = [d for d, v in dlg.diff_vars.items() if v.get()]
    if not diffs:
        messagebox.showerror("Dificultades", "Elige al menos una dificultad.", parent=dlg)
        return None
    video = dict(VIDEO_CHOICES)[dlg.video_var.get()]
    dlg.app.settings["video_codec"] = video
    paths.save_settings(dlg.app.settings)
    return diffs, dlg.chara_var.get()[:3], round(dlg.density_var.get(), 2), video


def import_queue(app, items, diffs, chara, density, video, on_status=None):
    """Imports (source, title, artist, is_url) items one after another; URLs are downloaded first.
    A failure is logged and the rest continue. Runs inside App.run_task.
    on_status(index, text, kind, fraction) reports per-item progress (kind: working/ok/error)."""
    status = on_status or (lambda *a: None)
    done, failed = 0, []
    total = len(items)
    for n, (source, title, artist, is_url) in enumerate(items, 1):
        def report(f, lo=0.0, hi=1.0, label="", n=n):
            app.events.put(("progress", (n - 1 + lo + (hi - lo) * f) / total))
            if label:
                status(n - 1, f"{label} {int(f * 100)} %", "working", lo + (hi - lo) * f)

        try:
            share = 0.0
            if is_url:
                app.log(f"[{n}/{total}] Descargando {source}")
                share = 0.4
                status(n - 1, "Descargando…", "working", 0.0)
                source, title, artist = download.download(
                    source, app.settings.get("download_dir") or download.DEFAULT_DIR, app.ffmpeg(),
                    lambda f: report(f, 0.0, share, "Descargando"), app.log)
                app.log(f"  guardado en {source}")
            pv_id = modloader.free_pv_id(app.game, app.settings.get("pv_id_start", 9500))
            req = songs.SongRequest(source=source, title=title or "Sin título", artist=artist, chara=chara,
                                    pv_id=pv_id, difficulties=diffs, density=density, video=video)
            app.log(f"[{n}/{total}] «{req.title}» como pv_{pv_id}")
            status(n - 1, "Importando…", "working", share)
            songs.import_song(app.game, req, app.ffmpeg(), app.ffprobe(), app.log,
                              lambda f: report(f, share, 1.0, "Importando"))
            done += 1
            status(n - 1, f"✔ Importada como pv_{pv_id}", "ok", 1.0)
        except Exception as e:  # keep importing the rest
            failed.append(os.path.basename(str(source)))
            app.log(f"  ERROR: {e}")
            status(n - 1, f"✖ {str(e)[:80]}", "error", 1.0)
    app.log(f"Lote terminado: {done} importadas" + (f", fallaron: {', '.join(failed)}" if failed else ""))
    if failed:
        raise RuntimeError(f"{len(failed)} canción(es) no se importaron. Revisa el registro.")


class UrlImportDialog(tk.Toplevel):
    """Download window: a queue of URLs with title/artist/duration read up front, per-item status,
    shared song settings and a rights confirmation. Downloads go through yt-dlp."""

    COLUMNS = (("n", "#", 34, "center"), ("title", "TÍTULO", 260, "w"), ("artist", "ARTISTA", 150, "w"),
               ("dur", "DURACIÓN", 96, "center"), ("status", "ESTADO", 200, "w"))

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Descargar canciones")
        self.configure(bg=T.BG)
        self.transient(app)
        self.minsize(820, 560)
        self.items = []  # dicts: url, title, artist, duration, iid
        self.inbox = queue.Queue()
        self.running = False

        body = ttk.Frame(self, padding=(20, 16))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Descargar canciones", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Pega enlaces de YouTube u otros sitios. Se descargan en 720p, se generan las notas "
                             "y se añaden al juego.", style="Muted.TLabel").pack(anchor="w", pady=(2, 10))

        # footer first (side=bottom) so it stays visible on small screens
        footer = ttk.Frame(body)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        self.overall = ttk.Progressbar(footer, maximum=1000)
        self.overall.pack(side="left", fill="x", expand=True, padx=(0, 14))
        ttk.Button(footer, text="Cerrar", command=self.destroy).pack(side="right")
        self.start_btn = ttk.Button(footer, text="⬇  Descargar e importar", style="Accent.TButton", command=self.ok)
        self.start_btn.pack(side="right", padx=(0, 8))
        self.rights_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, variable=self.rights_var,
                        text="Tengo derecho a descargar y usar estos videos (míos, con licencia libre o con permiso "
                             "del autor) y respeto los términos del sitio."
                        ).pack(side="bottom", anchor="w", pady=(10, 0))
        build_shared_settings(self, body, app).pack(side="bottom", fill="x")

        row = ttk.Frame(body)
        row.pack(fill="x")
        self.url_var = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.url_var, font=(T.FONT, 11))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.add_from_entry())
        self.paste_btn = ttk.Button(row, text="Pegar", command=self.paste)
        self.paste_btn.pack(side="left", padx=(8, 0))
        self.add_btn = ttk.Button(row, text="Añadir", style="Accent.TButton", command=self.add_from_entry)
        self.add_btn.pack(side="left", padx=(8, 0))

        lst = ttk.Frame(body)
        lst.pack(fill="both", expand=True, pady=(10, 0))
        self.tree = ttk.Treeview(lst, columns=[c[0] for c in self.COLUMNS], show="headings", height=6)
        for key, label, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor, stretch=key in ("title", "status"))
        for kind, color in STATUS_COLORS.items():
            self.tree.tag_configure(kind, foreground=color)
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.empty = ttk.Label(self.tree, text="La cola está vacía. Pega una URL arriba.", style="CardMuted.TLabel")
        self.empty.place(relx=0.5, rely=0.5, anchor="center")

        tools = ttk.Frame(body)
        tools.pack(fill="x", pady=(6, 8))
        self.count_var = tk.StringVar(value="0 canciones")
        ttk.Label(tools, textvariable=self.count_var, style="Muted.TLabel").pack(side="left")
        self.clear_btn = ttk.Button(tools, text="Vaciar", style="Small.TButton", command=self.clear)
        self.clear_btn.pack(side="right")
        self.remove_btn = ttk.Button(tools, text="Quitar seleccionada", style="Small.TButton", command=self.remove)
        self.remove_btn.pack(side="right", padx=6)

        self.entry.focus_set()
        self.after(100, self._drain)

    # ---- queue management ----
    def add_urls(self, text):
        urls, invalid = download.parse_urls(text)
        known = {i["url"] for i in self.items}
        for url in urls:
            if url in known:
                continue
            iid = self.tree.insert("", "end", tags=("pending",),
                                   values=(len(self.items) + 1, url, "", "", "Leyendo datos…"))
            item = {"url": url, "title": "", "artist": "", "duration": 0.0, "iid": iid}
            self.items.append(item)
            threading.Thread(target=self._probe, args=(item,), daemon=True).start()
        self._update_count()
        return invalid

    def _probe(self, item):
        try:
            title, artist, duration = download.probe(item["url"])
            self.inbox.put(("meta", item, (title, artist, duration)))
        except Exception as e:  # unknown site, private video, no network...
            self.inbox.put(("meta_error", item, str(e).splitlines()[-1][:90] if str(e) else "error"))

    def add_from_entry(self):
        text = self.url_var.get().strip()
        if not text:
            return
        invalid = self.add_urls(text)
        self.url_var.set(" ".join(invalid))
        if invalid:
            messagebox.showwarning("URL", "No es una URL válida:\n" + "\n".join(invalid[:5]), parent=self)

    def paste(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        invalid = self.add_urls(text)
        if invalid and not self.items:
            messagebox.showwarning("URL", "El portapapeles no contiene URLs.", parent=self)

    def remove(self):
        for iid in self.tree.selection():
            self.items = [i for i in self.items if i["iid"] != iid]
            self.tree.delete(iid)
        self._renumber()

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.items = []
        self._renumber()

    def _renumber(self):
        for n, item in enumerate(self.items, 1):
            self.tree.set(item["iid"], "n", n)
        self._update_count()

    def _update_count(self):
        n = len(self.items)
        self.count_var.set(f"{n} canción" + ("" if n == 1 else "es"))
        if n:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def _set_status(self, index, text, kind, fraction):
        if 0 <= index < len(self.items) and self.tree.exists(self.items[index]["iid"]):
            iid = self.items[index]["iid"]
            self.tree.set(iid, "status", text)
            self.tree.item(iid, tags=(kind,))
            self.overall["value"] = (index + fraction) / len(self.items) * 1000
        if kind in ("ok", "error") and index == len(self.items) - 1:
            self._finish()

    def _drain(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                kind, item, data = self.inbox.get_nowait()
                if not self.tree.exists(item["iid"]):
                    continue
                if kind == "meta":
                    item["title"], item["artist"], item["duration"] = data
                    minutes, seconds = divmod(int(item["duration"]), 60)
                    self.tree.item(item["iid"], tags=("pending",), values=(
                        self.tree.set(item["iid"], "n"), item["title"] or item["url"], item["artist"],
                        f"{minutes}:{seconds:02d}" if item["duration"] else "", "En cola"))
                elif kind == "meta_error":
                    self.tree.set(item["iid"], "status", f"⚠ {data}")
                    self.tree.item(item["iid"], tags=("error",))
                elif kind == "status":
                    self._set_status(*data)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _finish(self):
        self.running = False
        for w in (self.start_btn, self.add_btn, self.paste_btn, self.remove_btn, self.clear_btn):
            w.state(["!disabled"])

    # ---- start ----
    def ok(self):
        if self.url_var.get().strip():
            self.add_from_entry()
        if not self.items:
            messagebox.showerror("URLs", "Añade al menos una URL.", parent=self)
            return
        if not self.rights_var.get():
            messagebox.showwarning("Derechos", "Confirma que tienes derecho a descargar y usar estos videos.",
                                   parent=self)
            return
        settings = read_shared_settings(self)
        if not settings:
            return
        items = [(i["url"], i["title"], i["artist"], True) for i in self.items]
        for item in self.items:
            self.tree.set(item["iid"], "status", "En cola")
            self.tree.item(item["iid"], tags=("pending",))

        def on_status(index, text, kind, fraction):
            self.inbox.put(("status", {"iid": self.items[index]["iid"]} if index < len(self.items) else {"iid": ""},
                            (index, text, kind, fraction)))

        if self.app.run_task(lambda: import_queue(self.app, items, *settings, on_status=on_status)):
            self.running = True
            for w in (self.start_btn, self.add_btn, self.paste_btn, self.remove_btn, self.clear_btn):
                w.state(["disabled"])


class BatchImportDialog(tk.Toplevel):
    """Imports several files in a row with shared settings; titles come from tags or file names
    and PV IDs are assigned automatically."""

    def __init__(self, app, sources):
        super().__init__(app)
        self.app = app
        self.title(f"Importar {len(sources)} canciones")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.transient(app)
        body = ttk.Frame(self, padding=20)
        body.pack(fill="both")
        ttk.Label(body, text=f"Importar {len(sources)} canciones", style="DialogTitle.TLabel").pack(anchor="w")

        fp = app.ffprobe()
        self.items = [(src, *guess_meta(fp, src)) for src in sources]
        tree = ttk.Treeview(body, columns=("title", "artist"), show="headings", height=min(8, len(sources)))
        tree.heading("title", text="TÍTULO", anchor="w")
        tree.heading("artist", text="ARTISTA", anchor="w")
        tree.column("title", width=320)
        tree.column("artist", width=220)
        for src, title, artist in self.items:
            tree.insert("", "end", values=(title, artist))
        tree.pack(fill="x", pady=(12, 12))

        build_shared_settings(self, body, app).pack(fill="x")
        b = ttk.Frame(body)
        b.pack(fill="x", pady=(14, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Importar todas", style="Accent.TButton", command=self.ok).pack(side="right", padx=8)
        self.grab_set()

    def ok(self):
        settings = read_shared_settings(self)
        if settings:
            app, items = self.app, self.items
            self.destroy()
            app.run_task(lambda: import_queue(app, [(src, title, artist, False) for src, title, artist in items],
                                              *settings))


class ImportDialog(tk.Toplevel):
    def __init__(self, app, source):
        super().__init__(app)
        self.app, self.source = app, source
        self.title("Importar canción")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.transient(app)
        title, artist = guess_meta(app.ffprobe(), source)
        body = ttk.Frame(self, padding=20)
        body.pack(fill="both")
        ttk.Label(body, text="Importar canción", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text=os.path.basename(source), style="Muted.TLabel").pack(anchor="w", pady=(2, 12))

        info = ttk.Frame(body, style="Card.TFrame", padding=14)
        info.pack(fill="x", pady=(0, 10))
        self.title_var = tk.StringVar(value=title)
        self.artist_var = tk.StringVar(value=artist)
        free = modloader.free_pv_id(app.game, app.settings.get("pv_id_start", 9500))
        self.pv_var = tk.StringVar(value=str(free))
        for r, (label, var, width) in enumerate((("Título", self.title_var, 44), ("Artista", self.artist_var, 44),
                                                 ("PV ID", self.pv_var, 10))):
            ttk.Label(info, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=4, padx=(0, 14))
            ttk.Entry(info, textvariable=var, width=width).grid(row=r, column=1, sticky="w")

        build_shared_settings(self, body, app).pack(fill="x")
        b = ttk.Frame(body)
        b.pack(fill="x", pady=(14, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Importar", style="Accent.TButton", command=self.ok).pack(side="right", padx=8)
        self.grab_set()

    def ok(self):
        try:
            pv_id = int(self.pv_var.get())
            if not 1 <= pv_id <= 99999:
                raise ValueError
        except ValueError:
            messagebox.showerror("PV ID", "El PV ID debe ser un número entre 1 y 99999.", parent=self)
            return
        used = {i for m in self.app.mods for i in m.pv_ids}
        if pv_id in used and not messagebox.askyesno("PV ID", f"pv_{pv_id} ya lo usa otro mod. ¿Usarlo igual?",
                                                     parent=self):
            return
        settings = read_shared_settings(self)
        if not settings:
            return
        diffs, chara, density, video = settings
        req = songs.SongRequest(source=self.source, title=self.title_var.get().strip() or "Sin título",
                                artist=self.artist_var.get().strip(), chara=chara, pv_id=pv_id,
                                difficulties=diffs, density=density, video=video)
        app = self.app
        self.destroy()
        app.log(f"Importando «{req.title}» como pv_{req.pv_id}…")
        app.run_task(lambda: songs.import_song(app.game, req, app.ffmpeg(), app.ffprobe(), app.log,
                                               lambda f: app.events.put(("progress", f))))


class RegenDialog(tk.Toplevel):
    """Regenerate a song's notes (density, variation, sync offset, difficulties) and optionally
    rebuild its movie from the original file."""

    def __init__(self, app, mod):
        super().__init__(app)
        self.app, self.mod = app, mod
        md = mod.meta
        self.title("Regenerar canción")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.transient(app)
        body = ttk.Frame(self, padding=20)
        body.pack(fill="both")
        ttk.Label(body, text=mod.name, style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"{md.get('artist', '')} · {md.get('bpm', '?')} BPM", style="Muted.TLabel").pack(
            anchor="w", pady=(2, 12))

        card = ttk.Frame(body, style="Card.TFrame", padding=14)
        card.pack(fill="x")
        ttk.Label(card, text="NOTAS", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w",
                                                                 pady=(0, 8))
        self.density = tk.DoubleVar(value=float(md.get("density", 1.0)))
        ttk.Label(card, text="Densidad", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 14))
        ttk.Scale(card, from_=0.6, to=1.5, variable=self.density, length=240).grid(row=1, column=1, sticky="w")
        dens_value = ttk.Label(card, text=f"{self.density.get():.2f}×", style="CardMuted.TLabel", width=6)
        dens_value.grid(row=1, column=2, sticky="w", padx=8)
        self.density.trace_add("write", lambda *_: dens_value.configure(text=f"{self.density.get():.2f}×"))
        self.seed = tk.IntVar(value=int(md.get("seed", 0)) + 1)
        ttk.Label(card, text="Variación (semilla)", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(card, from_=0, to=9999, textvariable=self.seed, width=8).grid(row=2, column=1, sticky="w")
        self.offset = tk.IntVar(value=int(md.get("offset_ms", 0)))
        ttk.Label(card, text="Desfase de notas (ms)", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        off = ttk.Frame(card, style="Card.TFrame")
        off.grid(row=3, column=1, columnspan=2, sticky="w")
        ttk.Spinbox(off, from_=-500, to=500, increment=5, textvariable=self.offset, width=8).pack(side="left")
        ttk.Label(off, text="  + si las notas llegan antes que la música, − si llegan tarde",
                  style="CardMuted.TLabel").pack(side="left")
        ttk.Label(card, text="Dificultades", style="Card.TLabel").grid(row=4, column=0, sticky="nw", pady=4)
        df = ttk.Frame(card, style="Card.TFrame")
        df.grid(row=4, column=1, columnspan=2, sticky="w")
        self.diff_vars = {}
        for d in pvdb.DIFFICULTIES:
            v = tk.BooleanVar(value=d in md.get("difficulties", pvdb.DIFFICULTIES) or d == "extra")
            self.diff_vars[d] = v
            ttk.Checkbutton(df, text=pvdb.DIFF_LABELS[d], variable=v, style="Card.TCheckbutton").pack(side="left",
                                                                                                     padx=(0, 10))

        vcard = ttk.Frame(body, style="Card.TFrame", padding=14)
        vcard.pack(fill="x", pady=(10, 0))
        ttk.Label(vcard, text="VIDEO", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w",
                                                                  pady=(0, 8))
        has_source = os.path.isfile(md.get("source", ""))
        self.rebuild = tk.BooleanVar(value=has_source and md.get("video", "h264") != "none")
        chk = ttk.Checkbutton(vcard, text="Reconvertir el video (720p, velocidad correcta)", variable=self.rebuild,
                              style="Card.TCheckbutton")
        chk.grid(row=1, column=0, columnspan=2, sticky="w")
        if not has_source:
            chk.state(["disabled"])
            ttk.Label(vcard, text="No se encuentra el archivo original:\n" + md.get("source", "?"),
                      style="CardMuted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.video_var = tk.StringVar(value=next(lbl for lbl, k in VIDEO_CHOICES[:2]
                                                 if k == (md.get("video") if md.get("video") in ("h264", "vp9")
                                                          else "h264")))
        ttk.Combobox(vcard, textvariable=self.video_var, state="readonly", width=36,
                     values=[lbl for lbl, _ in VIDEO_CHOICES[:2]]).grid(row=3, column=0, sticky="w", pady=(6, 0))

        b = ttk.Frame(body)
        b.pack(fill="x", pady=(14, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Regenerar", style="Accent.TButton", command=self.ok).pack(side="right", padx=8)
        self.grab_set()

    def ok(self):
        diffs = [d for d, v in self.diff_vars.items() if v.get()]
        if not diffs:
            messagebox.showerror("Dificultades", "Elige al menos una dificultad.", parent=self)
            return
        try:
            offset = float(self.offset.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Desfase", "El desfase debe ser un número de milisegundos.", parent=self)
            return
        app, mod = self.app, self.mod
        dens, seed = round(self.density.get(), 2), int(self.seed.get())
        video = dict(VIDEO_CHOICES)[self.video_var.get()] if self.rebuild.get() else None
        self.destroy()
        app.log(f"Regenerando «{mod.name}» (densidad {dens}, semilla {seed}, desfase {offset:+.0f} ms)…")
        app.run_task(lambda: songs.regenerate(mod, dens, seed, diffs, offset_ms=offset, video=video,
                                              ffmpeg=app.ffmpeg(), ffprobe=app.ffprobe(), log=app.log,
                                              progress=lambda f: app.events.put(("progress", f))))


class PreviewWindow(tk.Toplevel):
    """Shows the generated notes on a scaled 1920x1080 field plus a timeline."""
    W, H = 768, 432

    def __init__(self, app, mod):
        super().__init__(app)
        self.title(f"Vista previa — {mod.name}")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        script_dir = os.path.join(mod.path, "rom", "script")
        files = sorted(fn for fn in os.listdir(script_dir) if fn.endswith(".dsc")) if os.path.isdir(script_dir) else []
        if not files:
            ttk.Label(self, text="Este mod no tiene charts .dsc", padding=20).pack()
            return
        self.files = {fn: os.path.join(script_dir, fn) for fn in files}
        top = ttk.Frame(self, padding=(12, 12, 12, 6))
        top.pack(fill="x")
        self.file_var = tk.StringVar(value=next((f for f in files if "hard" in f), files[0]))
        cb = ttk.Combobox(top, textvariable=self.file_var, values=files, state="readonly", width=30)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.load())
        self.info = ttk.Label(top, style="Muted.TLabel")
        self.info.pack(side="left", padx=12)
        self.canvas = tk.Canvas(self, width=self.W, height=self.H, bg="#0e0f17", highlightthickness=0)
        self.canvas.pack(padx=12)
        self.timeline = tk.Canvas(self, width=self.W, height=60, bg=T.SURFACE, highlightthickness=0)
        self.timeline.pack(padx=12, pady=(6, 0))
        self.t_var = tk.DoubleVar(value=0)
        self.scale = ttk.Scale(self, from_=0, to=1, variable=self.t_var, length=self.W,
                               command=lambda _v: self.draw())
        self.scale.pack(padx=12, pady=12)
        self.load()

    def load(self):
        self.notes = read_targets(self.files[self.file_var.get()])
        end = max((n[0] for n in self.notes), default=1) + 3
        self.scale.configure(to=end)
        holds = sum(1 for n in self.notes if 4 <= n[1] < 8)
        slides = sum(1 for n in self.notes if n[1] in (SLIDE_L, SLIDE_R))
        times = [n[0] for n in self.notes]
        multi = sum(1 for i, t in enumerate(times) if i and abs(t - times[i - 1]) < 1e-4)
        self.info.configure(text=f"{len(self.notes)} objetivos · {holds} holds · {slides} deslizamientos · "
                                 f"{multi} notas en múltiples")
        self.t_var.set(min(self.t_var.get(), end))
        self.draw()

    def draw(self):
        c, tl = self.canvas, self.timeline
        c.delete("all")
        tl.delete("all")
        t = self.t_var.get()
        sx, sy = self.W / 1920, self.H / 1080
        window = 3.0
        for start, typ, x, y in self.notes:
            sym, color = note_style(typ)
            if t - 0.3 <= start <= t + window:
                age = (start - t) / window
                r = 9 if typ in (CHAIN_L, CHAIN_R) else 19 if 4 <= typ < 8 else 16
                px, py = x * sx, y * sy
                c.create_oval(px - r, py - r, px + r, py + r, outline=color, width=3 if 4 <= typ < 8 else 2,
                              fill="#23253a" if age > 0 else color)
                c.create_text(px, py, text=sym, fill="#fff", font=(T.FONT, 10 if r < 12 else 11, "bold"))
            dt = start - t
            if -2 <= dt <= 10:
                tx = 40 + (dt + 2) / 12 * (self.W - 40)
                lane = 4 if typ >= 12 else typ % 4
                tl.create_text(tx, 8 + lane * 11, text=sym, fill=color, font=(T.FONT, 8, "bold"))
        marker = 40 + 2 / 12 * (self.W - 40)
        tl.create_line(marker, 0, marker, 60, fill=T.ACCENT)
        c.create_text(10, 10, anchor="nw", fill=T.MUTED,
                      text=f"notas a golpear en los próximos 3 s  ·  t = {t:6.2f} s")


def main():
    App().mainloop()
