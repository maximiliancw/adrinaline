"""Flat, knock-out ball-and-stick renderer for the adrinaline mark.

Input: geometry.json (projected 2D positions + depth of (R)-adrenaline).
Output: list of (role, shapely geometry) in paint order, all overlaps resolved
geometrically, so every variant is plain filled paths (no masks, no strokes).
"""

import json
import math
from pathlib import Path

from shapely import affinity
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

HERE = Path(__file__).parent
GEOM = json.loads((HERE / "geometry.json").read_text())

STYLE = {
    "full": dict(
        r={"C": 60, "N": 70, "O": 70, "H": 38},
        bond=22,
        gap=11,
        dash=True,
        hydrogens=True,
        depth=0.00028,
    ),
    "skeletal": dict(
        r={"C": 64, "N": 74, "O": 74, "H": 0},
        bond=28,
        gap=13,
        dash=True,
        hydrogens=False,
        depth=0.00022,
    ),
    "icon": dict(
        r={"C": 98, "N": 110, "O": 110, "H": 0},
        bond=46,
        gap=18,
        dash=False,
        hydrogens=False,
        depth=0.0,
    ),
    "favicon": dict(
        r={"C": 48, "N": 128, "O": 128, "H": 0},
        bond=96,
        gap=34,
        dash=False,
        hydrogens=False,
        depth=0.0,
    ),
}


RING = {"Ca", "Cb", "Cc", "Cd", "Ce", "Cf"}


def _role(el):
    return {"C": "carbon", "N": "nitrogen", "O": "oxygen", "H": "hydrogen"}[el]


def build(style="full", keep=None, q=24):
    """Return [(role, geom)] back-to-front. keep: optional set of atom labels to include."""
    st = STYLE[style] if isinstance(style, str) else style
    atoms = {a["i"]: a for a in GEOM["atoms"]}
    if not st["hydrogens"]:
        atoms = {i: a for i, a in atoms.items() if a["el"] != "H"}
    if keep is not None:
        atoms = {i: a for i, a in atoms.items() if a["label"] in keep}
    shapes = []  # dict(role, geom, z, links:set of ids)
    for i, a in atoms.items():
        shapes.append(
            dict(
                id=("a", i),
                role=_role(a["el"]),
                z=a["z"],
                geom=Point(a["x"], a["y"]).buffer(
                    st["r"][a["el"]] * (1 + st.get("depth", 0) * a["z"]), quad_segs=q
                ),
                links=set(),
            )
        )
    ring = [i for i, a in atoms.items() if a["label"] in {"Ca", "Cb", "Cc", "Cd", "Ce", "Cf"}]
    cx = sum(atoms[i]["x"] for i in ring) / max(len(ring), 1)
    cy = sum(atoms[i]["y"] for i in ring) / max(len(ring), 1)
    for b in GEOM["bonds"]:
        ia, ib = b["a"], b["b"]
        if ia not in atoms or ib not in atoms:
            continue
        A, B = atoms[ia], atoms[ib]
        z = (A["z"] + B["z"]) / 2
        line = LineString([(A["x"], A["y"]), (B["x"], B["y"])])
        shapes.append(
            dict(
                id=("b", ia, ib),
                role="bond",
                z=z,
                geom=line.buffer(st["bond"] / 2, quad_segs=q),
                links={("a", ia), ("a", ib)},
            )
        )
        # aromatic inner dashes (only if full ring present)
        if (
            b["arom"]
            and st["dash"]
            and len(ring) == 6
            and atoms[ia]["label"] in RING
            and atoms[ib]["label"] in RING
        ):
            ax, ay, bx, by = A["x"], A["y"], B["x"], B["y"]
            mx, my = (ax + bx) / 2, (ay + by) / 2
            nx, ny = cx - mx, cy - my
            n = math.hypot(nx, ny)
            off = st["bond"] * 2.1
            ox, oy = nx / n * off, ny / n * off
            # shrink toward midpoint, then split into dashes
            t0, t1 = 0.30, 0.70
            pts = [(ax + (bx - ax) * t + ox, ay + (by - ay) * t + oy) for t in (t0, t1)]
            ndash = 3
            seg = 1 / (ndash * 2 - 1)
            for k in range(ndash):
                s0, s1 = 2 * k * seg, (2 * k + 1) * seg
                p0 = (
                    pts[0][0] + (pts[1][0] - pts[0][0]) * s0,
                    pts[0][1] + (pts[1][1] - pts[0][1]) * s0,
                )
                p1 = (
                    pts[0][0] + (pts[1][0] - pts[0][0]) * s1,
                    pts[0][1] + (pts[1][1] - pts[0][1]) * s1,
                )
                shapes.append(
                    dict(
                        id=("d", ia, ib, k),
                        role="bond",
                        z=z - 1,
                        geom=LineString([p0, p1]).buffer(st["bond"] * 0.36, quad_segs=q),
                        links={("b", ia, ib)},
                    )
                )
    shapes.sort(key=lambda s: s["z"])
    out = []
    for k, s in enumerate(shapes):
        cut = [
            t["geom"].buffer(st["gap"], quad_segs=q)
            for t in shapes[k + 1 :]
            if t["id"] not in s["links"] and s["id"] not in t["links"]
        ]
        g = s["geom"].difference(unary_union(cut)) if cut else s["geom"]
        if not g.is_empty:
            out.append((s["role"], g))
    return out


def bounds(parts):
    return unary_union([g for _, g in parts]).bounds


def to_path(geom, prec=1):
    def ring(coords):
        pts = list(coords)[:-1]
        return "M" + "L".join(f"{x:.{prec}f} {y:.{prec}f}" for x, y in pts) + "Z"

    polys = getattr(geom, "geoms", [geom])
    d = []
    for p in polys:
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        d.append(ring(p.exterior.coords))
        d.extend(ring(i.coords) for i in p.interiors)
    return "".join(d)


def transform(parts, scale, dx, dy):
    return [
        (r, affinity.translate(affinity.scale(g, scale, scale, origin=(0, 0)), dx, dy))
        for r, g in parts
    ]


def svg_group(parts, colors, prec=1):
    """Merge geometry per role -> one <path> per role."""
    by = {}
    for r, g in parts:
        by.setdefault(r, []).append(g)
    order = ["bond", "hydrogen", "carbon", "nitrogen", "oxygen"]
    out = []
    for r in order:
        if r in by:
            out.append(f'<path fill="{colors[r]}" d="{to_path(unary_union(by[r]), prec)}"/>')
    return "".join(out)


ICON_ATOMS = {"Ca", "Cb", "Cc", "Cd", "Ce", "Cf", "O2", "O3", "C3"}
FAVICON_ATOMS = {"Ca", "Cb", "Cc", "Cd", "Ce", "Cf", "O2", "O3"}
