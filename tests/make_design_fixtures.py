"""Writes the small design files used by the import tests into tests/fixtures/designs/.

They are committed; run this again only to change them (then check the IMP_* goldens and
update them on purpose with regression.py --update).
"""
import math
import os
import struct

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "designs")


def write(name, text):
    with open(os.path.join(OUT, name), "w", newline="\n") as f:
        f.write(text)


def dxf(entities, units=4):
    out = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", str(units), "0", "ENDSEC",
           "0", "SECTION", "2", "ENTITIES"]
    for e in entities:
        out += [str(x) for x in e]
    out += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(out) + "\n"


def frustum(r0, r1, h, n):
    tris = []
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        b0, b1 = (r0 * math.cos(a0), r0 * math.sin(a0), 0.0), (r0 * math.cos(a1), r0 * math.sin(a1), 0.0)
        t0, t1 = (r1 * math.cos(a0), r1 * math.sin(a0), h), (r1 * math.cos(a1), r1 * math.sin(a1), h)
        tris += [(b0, b1, t1), (b0, t1, t0), ((0.0, 0.0, 0.0), b1, b0), ((0.0, 0.0, h), t0, t1)]
    return tris


def main():
    os.makedirs(OUT, exist_ok=True)
    # a smooth free shape (Bezier curves) in a rotated group, real size in mm, plus a small circle
    write("blob.svg", '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="200mm" viewBox="0 0 200 200">\n'
          '  <g transform="translate(100,100) rotate(15)">\n'
          '    <path d="M -80 0 C -80 -60 -30 -80 0 -50 S 80 -70 80 0 S 40 80 0 60 S -80 60 -80 0 Z"/>\n'
          '  </g>\n'
          '  <circle cx="20" cy="20" r="5"/>\n'
          '</svg>\n')
    # sharp corners, no real size (pixels), relative commands and an arc
    write("corners_px.svg", '<svg xmlns="http://www.w3.org/2000/svg">\n'
          '  <polygon points="0,0 400,0 400,300 0,300"/>\n'
          '  <path d="M 10 10 l 50 0 a 20 20 0 0 1 20 20 v 40 h -70 z"/>\n'
          '  <path d="M 500 0 L 550 0 L 550 50"/>\n'
          '</svg>\n')
    # a plate made of loose lines and arcs in mixed order, with a hole (circle)
    write("plate.dxf", dxf([
        (0, "LINE", 8, "0", 10, -50, 20, -30, 11, 50, 21, -30),
        (0, "ARC", 8, "0", 10, -50, 20, 0, 40, 30, 50, 90, 51, 270),
        (0, "LINE", 8, "0", 10, 50, 20, 30, 11, -50, 21, 30),
        (0, "ARC", 8, "0", 10, 50, 20, 0, 40, 30, 50, 270, 51, 90),
        (0, "CIRCLE", 8, "0", 10, 0, 20, 0, 40, 12)]))
    # a closed polyline with bulges (rounded square 4 x 4, radius 0.8), drawn in INCHES
    r, s, b = 0.8, 4.0, math.tan(math.pi / 8)
    write("rounded_inch.dxf", dxf([(0, "LWPOLYLINE", 8, "0", 90, 8, 70, 1,
                                    10, r, 20, 0, 10, s - r, 20, 0, 42, b, 10, s, 20, r, 10, s, 20, s - r, 42, b,
                                    10, s - r, 20, s, 10, r, 20, s, 42, b, 10, 0, 20, s - r, 10, 0, 20, r, 42, b)],
                                  units=1))
    # a cone (frustum) as a binary STL: radius 60 -> 45 over 12 mm, 64 facets
    tris = frustum(60.0, 45.0, 12.0, 64)
    with open(os.path.join(OUT, "cone.stl"), "wb") as f:
        f.write(b"KRL Generator test cone".ljust(80, b"\0") + struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<12fH", 0.0, 0.0, 0.0, *(t[0] + t[1] + t[2] + (0,))))
    # a box as an ASCII STL
    L, W, H = 120.0, 80.0, 6.0
    v = [(x, y, z) for z in (0.0, H) for y in (0.0, W) for x in (0.0, L)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (1, 5, 7, 3), (3, 7, 6, 2), (2, 6, 4, 0)]
    box = [t for a, b_, c, d in quads for t in ((v[a], v[b_], v[c]), (v[a], v[c], v[d]))]
    write("box_ascii.stl", "solid box\n" + "".join(
        "facet normal 0 0 0\n outer loop\n" + "".join("  vertex %r %r %r\n" % p for p in t) + " endloop\nendfacet\n"
        for t in box) + "endsolid box\n")
    print("written to", OUT)


if __name__ == "__main__":
    main()
