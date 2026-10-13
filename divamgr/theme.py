"""Dark ttk theme for Diva Manager (Miku teal accent)."""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#14151f"
SURFACE = "#1d1f2d"
SURFACE_2 = "#262940"
BORDER = "#34375a"
TEXT = "#e8e9f3"
MUTED = "#9a9db8"
ACCENT = "#39c5bb"
ACCENT_HOVER = "#55d8ce"
ACCENT_TEXT = "#0b1f1d"
DANGER = "#ff5c7a"
WARN = "#ffb454"
OK = "#5be38f"
INFO = "#7aa7ff"

FONT = "Segoe UI"
MONO = "Consolas"


def apply(root):
    """Configure ttk styles on `root` and return the Style."""
    root.configure(bg=BG)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT, size=10)
        except tk.TclError:
            pass
    root.option_add("*TCombobox*Listbox.background", SURFACE_2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_TEXT)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE_2, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER, troughcolor=SURFACE, focuscolor=ACCENT,
                selectbackground=ACCENT, selectforeground=ACCENT_TEXT, insertcolor=TEXT, font=(FONT, 10))

    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=SURFACE, relief="flat")
    s.configure("Header.TFrame", background=SURFACE)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    s.configure("Title.TLabel", background=SURFACE, foreground=TEXT, font=(FONT, 17, "bold"))
    s.configure("Subtitle.TLabel", background=SURFACE, foreground=MUTED, font=(FONT, 10))
    s.configure("Section.TLabel", background=SURFACE, foreground=ACCENT, font=(FONT, 10, "bold"))
    s.configure("DialogTitle.TLabel", background=BG, foreground=TEXT, font=(FONT, 15, "bold"))
    for name, color in (("Ok", OK), ("Warn", WARN), ("Bad", DANGER)):
        s.configure(f"{name}.TLabel", background=SURFACE, foreground=color, font=(FONT, 10, "bold"))

    s.configure("TButton", background=SURFACE_2, foreground=TEXT, bordercolor=BORDER, lightcolor=SURFACE_2,
                darkcolor=SURFACE_2, padding=(12, 6), focusthickness=0)
    s.map("TButton", background=[("pressed", BORDER), ("active", "#30334e"), ("disabled", SURFACE)],
          foreground=[("disabled", "#5d607a")])
    s.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_TEXT, bordercolor=ACCENT,
                lightcolor=ACCENT, darkcolor=ACCENT, font=(FONT, 10, "bold"), padding=(16, 7))
    s.map("Accent.TButton", background=[("pressed", "#2aa59c"), ("active", ACCENT_HOVER), ("disabled", "#2a4a48")],
          foreground=[("disabled", "#6f8f8c")])
    s.configure("Danger.TButton", background=SURFACE_2, foreground=DANGER)
    s.map("Danger.TButton", background=[("active", "#3a2433")])
    s.configure("Small.TButton", padding=(8, 3))

    s.configure("TEntry", fieldbackground=SURFACE_2, foreground=TEXT, bordercolor=BORDER, padding=6)
    s.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
    s.configure("TSpinbox", fieldbackground=SURFACE_2, foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER,
                padding=4)
    s.configure("TCombobox", fieldbackground=SURFACE_2, foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER,
                padding=4)
    s.map("TCombobox", fieldbackground=[("readonly", SURFACE_2)], foreground=[("readonly", TEXT)],
          selectbackground=[("readonly", SURFACE_2)], selectforeground=[("readonly", TEXT)])
    for base in ("TCheckbutton", "Card.TCheckbutton"):
        bg = SURFACE if base.startswith("Card") else BG
        s.configure(base, background=bg, foreground=TEXT, indicatorbackground=SURFACE_2,
                    indicatorforeground=ACCENT, focuscolor=bg)
        s.map(base, background=[("active", bg)], indicatorbackground=[("selected", ACCENT)],
              indicatorforeground=[("selected", ACCENT_TEXT)])
    s.configure("Horizontal.TScale", background=SURFACE, troughcolor=SURFACE_2, bordercolor=BORDER)
    s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=SURFACE_2, bordercolor=SURFACE_2,
                lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)

    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, bordercolor=BORDER,
                rowheight=30)
    s.map("Treeview", background=[("selected", "#2c4d5a")], foreground=[("selected", TEXT)])
    s.configure("Treeview.Heading", background=SURFACE_2, foreground=MUTED, bordercolor=BORDER, relief="flat",
                font=(FONT, 9, "bold"), padding=(8, 6))
    s.map("Treeview.Heading", background=[("active", BORDER)])
    s.configure("Vertical.TScrollbar", background=SURFACE_2, troughcolor=SURFACE, bordercolor=SURFACE,
                arrowcolor=MUTED, lightcolor=SURFACE_2, darkcolor=SURFACE_2)
    s.configure("TSeparator", background=BORDER)
    return s


def text_widget(parent, **kw):
    """tk.Text styled like the theme."""
    opts = dict(bg=SURFACE, fg=TEXT, insertbackground=TEXT, relief="flat", highlightthickness=1,
                highlightbackground=BORDER, highlightcolor=ACCENT, selectbackground=ACCENT,
                selectforeground=ACCENT_TEXT, padx=8, pady=6, font=(MONO, 9))
    opts.update(kw)
    return tk.Text(parent, **opts)


def dialog(root, title):
    """Themed Toplevel with padding frame; returns (window, body)."""
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=BG)
    win.transient(root)
    body = ttk.Frame(win, padding=18)
    body.pack(fill="both", expand=True)
    return win, body
