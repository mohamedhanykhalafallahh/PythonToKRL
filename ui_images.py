"""Small anti-aliased images for the interface, drawn in pure Python (no extra libraries).

Tk cannot round button corners or draw nice checkmarks by itself, but ttk can build widgets
from images. This module draws those images (rounded rectangles, check boxes, shape icons,
the app icon) with 4x4 supersampling and encodes them as PNG (Tk 8.6 reads PNG with alpha).

    png_b64(w, h, sample)       sample(x, y) -> (r, g, b, a) in 0..255 or None (transparent)
    rounded_rect(...)           9-slice button / card backgrounds
    checkbox(...), radio(...)   indicator images
    icon_cuboid(...), icon_cylinder(...), app_icon(...)
    write_ico(path, sizes)      the .exe icon
"""
import base64
import math
import struct
import zlib


# ------------------------------------------------------------------ colours

def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t):
    """Blend two '#rrggbb' colours (t = 0 -> c1, 1 -> c2)."""
    a, b = hex_rgb(c1), hex_rgb(c2)
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def ramp(stops, t):
    """Colour at t in [0, 1] along a list of '#rrggbb' stops (evenly spaced)."""
    t = min(1.0, max(0.0, t))
    seg = t * (len(stops) - 1)
    i = min(int(seg), len(stops) - 2)
    return mix(stops[i], stops[i + 1], seg - i)


def layer_colors(n, stops):
    """n distinct colours for n layers (any n), ordered bottom -> top along the ramp."""
    if n <= 1:
        return [ramp(stops, 0.5)]
    return [ramp(stops, i / (n - 1)) for i in range(n)]


# ------------------------------------------------------------------ PNG

def _png(w, h, rows, rgb=False):
    """PNG from rows of 8-bit values: RGBA (4 per pixel) or, with rgb=True, opaque RGB."""
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2 if rgb else 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _over(rows, bg):
    """RGBA rows composited over the colour bg -> opaque RGB pixel tuples per row."""
    br, bgc, bb = hex_rgb(bg)
    out = []
    for row in rows:
        px = []
        for i in range(0, len(row), 4):
            r, g, b, a = row[i:i + 4]
            t = a / 255.0
            px.append((int(round(r * t + br * (1 - t))), int(round(g * t + bgc * (1 - t))),
                       int(round(b * t + bb * (1 - t)))))
        out.append(px)
    return out


def nine_slice(W, H, r, fill, border, bg, bw=1.0, inset=0.5):
    """Big OPAQUE rounded rectangle (W x H) for ttk image elements, fast to draw:
    - opaque (blended onto the background colour it sits on): Windows copies it in one go,
      instead of blending every pixel again on each repaint;
    - big, with a plain middle: ttk needs only a few tiles to fill a widget.
    Made by drawing a small rounded rectangle and repeating its middle row and column."""
    s = 2 * (int(math.ceil(r)) + 3) + 1
    small = _over(render(s, s, _rrect_cov(s, s, r, fill, border, bw, inset)), bg)
    c = s // 2

    def wide(row):                         # one row stretched to W pixels, as bytes
        return bytes(v for p in row[:c] for v in p) + bytes(row[c]) * (W - s + 1) + \
            bytes(v for p in row[c + 1:] for v in p)
    top = [wide(row) for row in small[:c]]
    mid = wide(small[c])
    bottom = [wide(row) for row in small[c + 1:]]
    rows = top + [mid] * (H - s + 1) + bottom
    return base64.b64encode(_png(W, H, rows, rgb=True)).decode("ascii")


def opaque(size, coverage, bg):
    """Small opaque image (check boxes, icons): coverage drawn over the colour bg."""
    rows = _over(render(size, size, coverage), bg)
    return base64.b64encode(_png(size, size, [[v for p in row for v in p] for row in rows], rgb=True)).decode("ascii")


def render(w, h, coverage, ss=4):
    """RGBA rows. coverage(x, y) -> ((r, g, b), alpha 0..1) or None at sub-pixel (x, y)."""
    rows = []
    inv = 1.0 / (ss * ss)
    for py in range(h):
        row = []
        for px in range(w):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    c = coverage(px + (sx + 0.5) / ss, py + (sy + 0.5) / ss)
                    if c:
                        (cr, cg, cb), ca = c
                        r += cr * ca
                        g += cg * ca
                        b += cb * ca
                        a += ca
            if a > 0:
                row += [int(round(r / a)), int(round(g / a)), int(round(b / a)), int(round(255 * a * inv))]
            else:
                row += [0, 0, 0, 0]
        rows.append(row)
    return rows


def png_bytes(w, h, coverage, ss=4):
    return _png(w, h, render(w, h, coverage, ss))


def png_b64(w, h, coverage, ss=4):
    """Base64 PNG for tk.PhotoImage(data=...)."""
    return base64.b64encode(png_bytes(w, h, coverage, ss)).decode("ascii")


# ------------------------------------------------------------------ shapes

def _rbox_d(x, y, cx, cy, hw, hh, r):
    """Signed distance to a rounded box (negative inside)."""
    qx, qy = abs(x - cx) - (hw - r), abs(y - cy) - (hh - r)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def _seg_d(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def _rrect_cov(w, h, r, fill, border=None, bw=1.0, inset=0.5):
    f, b = hex_rgb(fill), hex_rgb(border) if border else None
    cx, cy, hw, hh = w / 2, h / 2, w / 2 - inset, h / 2 - inset

    def cov(x, y):
        d = _rbox_d(x, y, cx, cy, hw, hh, r)
        if d > 0:
            return None
        return ((b if b and d > -bw else f), 1.0)
    return cov


def rounded_rect(w, h, r, fill, border=None, bw=1.0, inset=0.5):
    """Rounded rectangle (fill + optional border) as base64 PNG with transparency."""
    return png_b64(w, h, _rrect_cov(w, h, r, fill, border, bw, inset))


def checkbox(size, checked, fill, border, mark="#ffffff", bg_off="#ffffff", r=None, bg=None):
    """Check box: rounded square; checked = filled with a white checkmark. With bg: opaque
    (drawn over that background colour), which is much faster for Tk to paint."""
    if bg is not None:
        return opaque(size, _checkbox_cov(size, checked, fill, border, mark, bg_off, r), bg)
    return png_b64(size, size, _checkbox_cov(size, checked, fill, border, mark, bg_off, r))


def _checkbox_cov(size, checked, fill, border, mark, bg_off, r):
    r = size * 0.22 if r is None else r
    f, b, m, bo = hex_rgb(fill), hex_rgb(border), hex_rgb(mark), hex_rgb(bg_off)
    c, hw = size / 2, size / 2 - 1.0
    th = size * 0.075   # half thickness of the checkmark stroke
    p1, p2, p3 = (size * 0.27, size * 0.52), (size * 0.43, size * 0.68), (size * 0.74, size * 0.34)

    def cov(x, y):
        d = _rbox_d(x, y, c, c, hw, hw, r)
        if d > 0:
            return None
        if not checked:
            return ((b if d > -1.2 else bo), 1.0)
        if min(_seg_d(x, y, *p1, *p2), _seg_d(x, y, *p2, *p3)) <= th:
            return (m, 1.0)
        return (f, 1.0)
    return cov


def icon_cuboid(size, color, stroke=None):
    """Rounded-rectangle outline (a cuboid seen from above)."""
    col = hex_rgb(color)
    st = size * 0.1 if stroke is None else stroke
    cx, cy, hw, hh, r = size / 2, size / 2, size * 0.42, size * 0.30, size * 0.12

    def cov(x, y):
        d = _rbox_d(x, y, cx, cy, hw, hh, r)
        return (col, 1.0) if abs(d + st / 2) <= st / 2 else None
    return png_b64(size, size, cov)


def icon_cylinder(size, color, stroke=None):
    """Ring outline (a cylinder seen from above)."""
    col = hex_rgb(color)
    st = size * 0.1 if stroke is None else stroke
    c, rad = size / 2, size * 0.40

    def cov(x, y):
        d = math.hypot(x - c, y - c) - rad
        return (col, 1.0) if abs(d + st / 2) <= st / 2 else None
    return png_b64(size, size, cov)


def app_icon_cov(size, back="#1e3a5f", rings=("#93c5fd", "#3b82f6", "#ffffff"), dot="#f59e0b"):
    """Coverage function of the app icon: three stacked rounded loops + the print head (dot)."""
    bg, rc, dc = hex_rgb(back), [hex_rgb(c) for c in rings], hex_rgb(dot)
    s = float(size)

    def cov(x, y):
        dot_d = math.hypot(x - s * 0.78, y - s * 0.24) - s * 0.09
        if dot_d <= 0:
            return (dc, 1.0)
        for i, col in enumerate(rc):
            o = i * s * 0.075
            d = _rbox_d(x, y + o - s * 0.07, s * 0.5, s * 0.55, s * 0.36, s * 0.22, s * 0.1)
            if abs(d) <= s * 0.035:
                return (col, 1.0)
        if _rbox_d(x, y, s / 2, s / 2, s / 2 - 0.5, s / 2 - 0.5, s * 0.2) <= 0:
            return (bg, 1.0)
        return None
    return cov


def app_icon(size, **kw):
    return png_b64(size, size, app_icon_cov(size, **kw))


def export_icon_files(folder, png_sizes=(16, 32, 48, 64, 128, 256, 512)):
    """Write the app icon as PNG files (KRL_Generator_icon_<size>.png) and as a Windows .ico
    (KRL_Generator.ico) into `folder`. Returns the list of written paths."""
    import os
    os.makedirs(folder, exist_ok=True)
    paths = []
    for s in png_sizes:
        p = os.path.join(folder, "KRL_Generator_icon_%d.png" % s)
        with open(p, "wb") as f:
            f.write(png_bytes(s, s, app_icon_cov(s), ss=3 if s >= 128 else 4))
        paths.append(p)
    ico = os.path.join(folder, "KRL_Generator.ico")
    write_ico(ico)
    paths.append(ico)
    return paths


def write_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256), **kw):
    """Windows .ico with PNG-compressed images (Vista+), for the .exe."""
    pngs = [png_bytes(s, s, app_icon_cov(s, **kw), ss=3 if s >= 128 else 4) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, data in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(head + entries + b"".join(pngs))
