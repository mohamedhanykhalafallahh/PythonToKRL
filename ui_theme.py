"""Look and feel of the KRL Generator: light / dark palettes, fonts and the ttk styles.

The rounded buttons, cards, fields, check boxes and badges are ttk styles built from small
anti-aliased images (ui_images.py). Tk cannot redefine an image element, so every theme gets
its own element names ("light.Card.bg", "dark.Card.bg"); switching only re-points the styles.

    apply(root, name)          ttk styles + fonts for 'light' or 'dark'; returns the palette
    paint_tk(widget, P)        colours plain tk widgets (dialogs, older windows) recursively
    title_bar(win, dark)       dark / light Windows title bar (Windows 10 2004+ / 11)
    load_theme() / save_theme(name)    remembered in app_settings.json next to the program
    window_icon(root)          the app icon for all windows of this Tk
"""
import json
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import ui_images as ui

UI_FONT = "Segoe UI"        # owner's choice (Windows 10 and 11)
CODE_FONT = "Consolas"      # owner's choice
UI_SIZE, CODE_SIZE = 10, 9

THEMES = {
    "light": dict(
        bg="#eef1f5", card="#ffffff", border="#dde3ea", field="#ffffff", field_border="#cfd7e1",
        text="#1f2933", muted="#6b7785", header="#1e3a5f", header_text="#ffffff", header_muted="#b9c7d8",
        accent="#2563eb", accent_hover="#1d4ed8", accent_press="#1e40af", accent_text="#ffffff",
        btn="#f4f6f9", btn_hover="#e6ecf5", btn_press="#d6e0ef", btn_border="#d2dae4",
        code_bg="#fbfcfd", canvas="#ffffff", grid="#f0f3f7", transition="#9333ea", path="#2563eb",
        chip="#e8eefc", chip_text="#1e3a8a", kw="#1d4ed8", cmt="#8a94a0", icon_off="#475569",
        select_bg="#cfe0ff", start="#16a34a", end="#dc2626", axis_text="#555555",
        ramp=["#93c5fd", "#2dd4bf", "#22c55e", "#f59e0b"]),
    "dark": dict(
        bg="#0f172a", card="#1e293b", border="#2c3a50", field="#0f172a", field_border="#3b4a63",
        text="#e2e8f0", muted="#94a3b8", header="#0b1222", header_text="#f1f5f9", header_muted="#8ea3c0",
        accent="#3b82f6", accent_hover="#60a5fa", accent_press="#2563eb", accent_text="#ffffff",
        btn="#273449", btn_hover="#334563", btn_press="#3d5274", btn_border="#3b4a63",
        code_bg="#0b1220", canvas="#0b1220", grid="#162036", transition="#c084fc", path="#60a5fa",
        chip="#1e3a8a", chip_text="#dbeafe", kw="#93c5fd", cmt="#64748b", icon_off="#cbd5e1",
        select_bg="#1e3a8a", start="#22c55e", end="#f87171", axis_text="#94a3b8",
        ramp=["#93c5fd", "#2dd4bf", "#22c55e", "#f59e0b"]),
}
DEFAULT_THEME = "light"


# ------------------------------------------------------------------ settings file

def settings_path():
    import krl_export                      # the program folder (next to the .exe when packaged)
    return os.path.join(krl_export.app_dir(), "app_settings.json")


SETTINGS_PATH = None                       # tests set a temporary path here


def _path():
    return SETTINGS_PATH or settings_path()


def load_theme():
    try:
        with open(_path(), encoding="utf-8") as f:
            name = json.load(f).get("theme", DEFAULT_THEME)
        return name if name in THEMES else DEFAULT_THEME
    except (OSError, ValueError, AttributeError):
        return DEFAULT_THEME


def save_theme(name):
    data = {}
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["theme"] = name
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


# ------------------------------------------------------------------ fonts / icon / title bar

def setup_fonts(root):
    named = lambda n: tkfont.Font(root=root, name=n, exists=True)     # (Python 3.7 compatible)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            named(name).configure(family=UI_FONT, size=UI_SIZE)
        except tk.TclError:
            pass
    try:
        named("TkFixedFont").configure(family=CODE_FONT, size=CODE_SIZE)
    except tk.TclError:
        pass


def window_icon(root):
    """App icon for every window of this Tk (title bar, task bar)."""
    if getattr(root, "_app_icon", None) is None:
        root._app_icon = [tk.PhotoImage(data=ui.app_icon(s), master=root) for s in (32, 16)]
    try:
        root.iconphoto(True, *root._app_icon)
    except tk.TclError:
        pass


def title_bar(win, dark):
    """Dark or light Windows title bar (no effect elsewhere / on older Windows).

    Changing the frame attribute of a window that is not shown yet can leave its child widgets
    unpainted (seen in the one-file exe, which starts slower). So: wait until the window is
    shown, set the attribute, then ask Windows to repaint the frame and all child widgets."""
    if not win.winfo_ismapped():
        # <Map> on a window also fires for each of its child widgets: wait for the window itself
        def on_map(event):
            if event.widget is win and not getattr(win, "_title_bar_done", False):
                win._title_bar_done = True
                win.after(50, lambda: title_bar(win, getattr(win, "_title_bar_dark", dark)))
        win._title_bar_dark = dark
        if not getattr(win, "_title_bar_bound", False):
            win.bind("<Map>", on_map, add="+")
            win._title_bar_bound = True
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):              # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old Windows builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
        # redraw the frame (title bar): SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        # and the contents: RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME
        user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100 | 0x0400)
    except Exception:
        pass


# ------------------------------------------------------------------ ttk styles

def _elements(root, name, P):
    """Create (once per Tk interpreter and theme) the image elements of theme `name`. ttk
    elements belong to the interpreter, so the cache lives on its root (not on a Toplevel)."""
    root = root._root()
    done = root.__dict__.setdefault("_theme_elements", {})
    if name in done:
        return done[name]
    st = ttk.Style(root)
    imgs = []

    def img(data):
        i = tk.PhotoImage(data=data, master=root)
        imgs.append(i)
        return i
    e = {}

    def element(key, normal, states=(), border=6):
        el = "%s.%s" % (name, key)
        # width/height: the element's MINIMUM size. Without them ttk asks for the (big) image
        # size, and every button / field / card would be as large as its image.
        st.element_create(el, "image", normal, *states, border=border, sticky="nsew",
                          width=2 * border + 1, height=2 * border + 1)
        e[key] = el
        e.setdefault("tiled", []).extend([normal] + [s[-1] for s in states])   # (checked by the tests)
    # PERFORMANCE: every image is OPAQUE (blended onto the colour it sits on) and BIG with a plain
    # middle, so Windows copies a few large pieces per repaint. Small, transparent images made ttk
    # tile thousands of tiny pieces with per-pixel blending: 9 s per full repaint (measured).
    nine = ui.nine_slice
    element("Card.bg", img(nine(640, 640, 8, P["card"], P["border"], bg=P["bg"])), border=11)
    element("Badge.bg", img(nine(480, 40, 6, P["accent"], None, bg=P["header"])), border=8)
    element("Chip.bg", img(nine(320, 36, 6, P["chip"], None, bg=P["bg"])), border=8)
    # buttons on a card ("Btn", "PrimaryCard") and directly on the page background ("BtnBg", "Primary")
    for key, base, n, h, p, b in (("Btn.bg", P["card"], P["btn"], P["btn_hover"], P["btn_press"], P["btn_border"]),
                                  ("BtnBg.bg", P["bg"], P["btn"], P["btn_hover"], P["btn_press"], P["btn_border"]),
                                  ("PrimaryCard.bg", P["card"], P["accent"], P["accent_hover"], P["accent_press"],
                                   P["accent_press"]),
                                  ("Primary.bg", P["bg"], P["accent"], P["accent_hover"], P["accent_press"],
                                   P["accent_press"])):
        i_n, i_h, i_p = (img(nine(560, 64, 5, c, b, bg=base)) for c in (n, h, p))
        i_d = img(nine(560, 64, 5, P["btn"], P["btn_border"], bg=base))
        element(key, i_n, (("disabled", i_d), ("pressed", i_p), ("active", i_h)), border=8)
    i_f = img(nine(240, 48, 4, P["field"], P["field_border"], bg=P["card"]))
    i_ff = img(nine(240, 48, 4, P["field"], P["accent"], bg=P["card"], bw=1.6))
    element("Field.bg", i_f, (("focus", i_ff),), border=6)
    cb = lambda checked, fill, border: img(ui.checkbox(18, checked, fill, border, bg_off=P["field"], bg=P["card"]))
    on, on_h = cb(True, P["accent"], P["field_border"]), cb(True, P["accent_hover"], P["field_border"])
    off, off_h = cb(False, P["accent"], P["field_border"]), cb(False, P["accent"], P["accent"])
    el = "%s.Check.ind" % name
    st.element_create(el, "image", off, ("selected active", on_h), ("selected", on), ("active", off_h), sticky="")
    e["Check.ind"] = el
    e["images"] = imgs
    e["icons"] = {"cuboid_on": img(ui.icon_cuboid(20, P["accent_text"])),
                  "cuboid_off": img(ui.icon_cuboid(20, P["icon_off"])),
                  "cylinder_on": img(ui.icon_cylinder(20, P["accent_text"])),
                  "cylinder_off": img(ui.icon_cylinder(20, P["icon_off"]))}
    done[name] = e
    return e


def apply(root, name):
    """Set the ttk styles and fonts of theme `name` for this Tk. Returns the palette."""
    P = THEMES[name]
    st = ttk.Style(root)
    if st.theme_use() != "clam":
        st.theme_use("clam")
    setup_fonts(root)
    e = _elements(root, name, P)
    f, fb, fs = (UI_FONT, UI_SIZE), (UI_FONT, UI_SIZE, "bold"), (UI_FONT, UI_SIZE - 1)
    st.configure(".", font=f, background=P["card"], foreground=P["text"], troughcolor=P["bg"],
                 bordercolor=P["border"], lightcolor=P["card"], darkcolor=P["border"],
                 selectbackground=P["select_bg"], selectforeground=P["text"], insertcolor=P["text"],
                 fieldbackground=P["field"])
    st.layout("Card.TFrame", [(e["Card.bg"], {"sticky": "nsew"})])
    st.configure("In.TFrame", background=P["card"])
    st.configure("Bg.TFrame", background=P["bg"])
    st.configure("TFrame", background=P["card"])
    st.configure("TLabel", background=P["card"], foreground=P["text"])
    st.configure("Title.TLabel", font=fb)
    st.configure("Muted.TLabel", foreground=P["muted"], font=fs)
    st.configure("BgMuted.TLabel", background=P["bg"], foreground=P["muted"], font=fs)

    def label_style(style, el, fg, pad):
        st.layout(style, [(el, {"sticky": "nsew", "children": [
            ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
        st.configure(style, foreground=fg, padding=pad, font=fs)
    label_style("Badge.TLabel", e["Badge.bg"], P["accent_text"], (9, 2))
    label_style("Chip.TLabel", e["Chip.bg"], P["chip_text"], (8, 1))

    def button_style(style, el, fg, pad, font=f):
        st.layout(style, [(el, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
        st.configure(style, foreground=fg, padding=pad, anchor="center", font=font)
        st.map(style, foreground=[("disabled", P["muted"])])
    # Rounded / Small.Rounded / SegOn / SegOff / CardPrimary: on a card; BgRounded / Primary: on the page
    button_style("Rounded.TButton", e["Btn.bg"], P["text"], (10, 2))
    button_style("BgRounded.TButton", e["BtnBg.bg"], P["text"], (10, 2))
    button_style("Small.Rounded.TButton", e["Btn.bg"], P["text"], (7, 0), fs)
    button_style("Primary.TButton", e["Primary.bg"], P["accent_text"], (14, 6), (UI_FONT, UI_SIZE + 1, "bold"))
    button_style("CardPrimary.TButton", e["PrimaryCard.bg"], P["accent_text"], (14, 4), (UI_FONT, UI_SIZE, "bold"))
    button_style("SegOn.TButton", e["PrimaryCard.bg"], P["accent_text"], (12, 3))
    button_style("SegOff.TButton", e["Btn.bg"], P["text"], (12, 3))
    st.layout("Field.TEntry", [(e["Field.bg"], {"sticky": "nsew", "children": [
        ("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]})]})])
    st.configure("Field.TEntry", padding=(6, 1), fieldbackground=P["field"], foreground=P["text"],
                 insertcolor=P["text"])
    st.layout("Check.TCheckbutton", [("Checkbutton.padding", {"sticky": "nsew", "children": [
        (e["Check.ind"], {"side": "left", "sticky": ""}),
        ("Checkbutton.label", {"side": "left", "sticky": "nsew"})]})])
    st.configure("Check.TCheckbutton", padding=(0, 3), background=P["card"], foreground=P["text"])
    st.map("Check.TCheckbutton", background=[("active", P["card"])])
    for s in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        st.configure(s, background=P["btn"], troughcolor=P["card"], bordercolor=P["card"],
                     arrowcolor=P["muted"], lightcolor=P["btn"], darkcolor=P["btn"])
        st.map(s, background=[("active", P["btn_hover"])])
    st.configure("TCombobox", fieldbackground=P["field"], foreground=P["text"], background=P["btn"],
                 arrowcolor=P["text"])
    st.map("TCombobox", fieldbackground=[("readonly", P["field"])], foreground=[("readonly", P["text"])],
           selectbackground=[("readonly", P["field"])], selectforeground=[("readonly", P["text"])],
           background=[("active", P["btn_hover"])])
    st.configure("TLabelframe", background=P["card"], bordercolor=P["border"])
    st.configure("TLabelframe.Label", background=P["card"], foreground=P["text"], font=fb)
    st.configure("TNotebook", background=P["bg"], bordercolor=P["border"])
    st.configure("TNotebook.Tab", background=P["btn"], foreground=P["text"], padding=(10, 3))
    st.map("TNotebook.Tab", background=[("selected", P["card"]), ("active", P["btn_hover"])])
    st.configure("TMenubutton", background=P["btn"], foreground=P["text"], arrowcolor=P["text"])
    st.map("TMenubutton", background=[("active", P["btn_hover"])])
    st.configure("TButton", background=P["btn"], foreground=P["text"], bordercolor=P["btn_border"],
                 lightcolor=P["btn"], darkcolor=P["btn_border"])
    st.map("TButton", background=[("active", P["btn_hover"]), ("pressed", P["btn_press"])])
    st.configure("TCheckbutton", background=P["card"], foreground=P["text"], indicatorbackground=P["field"])
    root.option_add("*TCombobox*Listbox.background", P["field"])
    root.option_add("*TCombobox*Listbox.foreground", P["text"])
    for w in {root, root._root()}:          # the window asked for, and the interpreter root
        w._theme_name, w._palette, w._icons = name, P, e["icons"]
    return P


# ------------------------------------------------------------------ plain tk widgets

def paint_tk(widget, P, canvases=False):
    """Colour plain tk widgets of a window (and its children) with palette P. Canvases (drawing
    areas) are left alone unless canvases=True."""
    cls = widget.winfo_class()
    opts = {
        "Frame": dict(bg=P["card"]), "Toplevel": dict(bg=P["card"]), "Tk": dict(bg=P["card"]),
        "Label": dict(bg=P["card"], fg=P["text"]),
        "Button": dict(bg=P["btn"], fg=P["text"], activebackground=P["btn_hover"], activeforeground=P["text"],
                       relief="flat", bd=0, highlightthickness=1, highlightbackground=P["btn_border"]),
        "Checkbutton": dict(bg=P["card"], fg=P["text"], activebackground=P["card"], activeforeground=P["text"],
                            selectcolor=P["field"]),
        "Radiobutton": dict(bg=P["card"], fg=P["text"], activebackground=P["card"], activeforeground=P["text"],
                            selectcolor=P["field"]),
        "Entry": dict(bg=P["field"], fg=P["text"], insertbackground=P["text"], relief="flat",
                      highlightthickness=1, highlightbackground=P["field_border"], highlightcolor=P["accent"]),
        "Text": dict(bg=P["code_bg"], fg=P["text"], insertbackground=P["text"], relief="flat",
                     highlightthickness=1, highlightbackground=P["border"]),
        "Scale": dict(bg=P["card"], fg=P["text"], troughcolor=P["bg"], activebackground=P["accent"],
                      highlightthickness=0),
        "Canvas": dict(bg=P["canvas"]) if canvases else None,
    }.get(cls)
    if opts:
        for k, v in opts.items():
            try:
                widget.configure(**{k: v})
            except tk.TclError:
                pass
    for child in widget.winfo_children():
        if isinstance(child, tk.Menu):
            continue
        paint_tk(child, P, canvases)


def light_touch(root, name=None):
    """Older windows (manual / free-form editors): theme fonts and colours, layout unchanged.
    Their drawing canvases stay white so the existing line colours stay readable."""
    name = name or load_theme()
    P = apply(root, name)
    window_icon(root)
    paint_tk(root, P)
    title_bar(root, name == "dark")
    return P
