"""Build the adrinaline brand assets.

    uv run --no-project --python 3.14 \
        --with cairosvg --with shapely --with fonttools --with pillow \
        python assets/brand/src/build.py

Everything is generated from geometry.json (a computed conformer of (R)-adrenaline)
and the OFL fonts in ./fonts. Text is converted to outlines, so no SVG depends on
an installed font.
"""

import io
import json
import shutil
from pathlib import Path

import cairosvg
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from mark import FAVICON_ATOMS, ICON_ATOMS, bounds, build, svg_group, transform
from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent

# ---------------------------------------------------------------- palette
PALETTE = {
    "on-light": dict(
        bond="#9AA1AC",
        hydrogen="#B8BEC8",
        carbon="#1F2329",
        nitrogen="#2F6BFF",
        oxygen="#E8392C",
        ink="#1F2329",
        accent="#E8392C",
        muted="#5B6270",
        bg="#FFFFFF",
        tile="#F4F5F7",
        chip="#EEF0F3",
    ),
    "on-dark": dict(
        bond="#4A515E",
        hydrogen="#7C8494",
        carbon="#ECEEF2",
        nitrogen="#5B8CFF",
        oxygen="#FF4F3F",
        ink="#ECEEF2",
        accent="#FF4F3F",
        muted="#9AA1AC",
        bg="#0E1116",
        tile="#0E1116",
        chip="#1A1F27",
    ),
}
for name, c in (("mono-black", "#000000"), ("mono-white", "#FFFFFF")):
    PALETTE[name] = {
        k: c for k in ("bond", "hydrogen", "carbon", "nitrogen", "oxygen", "ink", "accent")
    }
COLOR_VARIANTS = ("on-light", "on-dark")
ALL_VARIANTS = ("on-light", "on-dark", "mono-black", "mono-white")

TAGLINE = "Git-native Architecture Decision Records for humans and coding agents"
COMMAND = "uvx adrinaline"


# ---------------------------------------------------------------- text
class Font:
    def __init__(self, file):
        self.f = TTFont(SRC / "fonts" / file)
        self.gs = self.f.getGlyphSet()
        self.cmap = self.f.getBestCmap()
        self.upm = self.f["head"].unitsPerEm
        os2 = self.f["OS/2"]
        self.xh, self.cap = os2.sxHeight / self.upm, os2.sCapHeight / self.upm

    def run(self, text, size, x, base, tracking=0.0):
        """Glyph outlines for text. Returns (paths per char, advance, tight bbox)."""
        sc = size / self.upm
        cx, paths, bp = x, [], BoundsPen(self.gs)
        for ch in text:
            g = self.gs[self.cmap[ord(ch)]]
            t = (sc, 0, 0, -sc, cx, base)
            pen = SVGPathPen(self.gs)
            g.draw(TransformPen(pen, t))
            g.draw(TransformPen(bp, t))
            paths.append(pen.getCommands())
            cx += g.width * sc + tracking * size
        return paths, cx - x - tracking * size, bp.bounds

    def width(self, text, size, tracking=0.0):
        return self.run(text, size, 0, 0, tracking)[1]


DISPLAY = Font("space-grotesk-latin-700-normal.woff")
TEXT = Font("space-grotesk-latin-500-normal.woff")
MONO = Font("jetbrains-mono-latin-500-normal.woff")
WORD_TRACK = -0.02


def wordmark(x, base, size, pal):
    """'adr' in accent + 'inaline' in ink. Returns (svg, advance, bbox)."""
    paths, adv, bb = DISPLAY.run("adrinaline", size, x, base, WORD_TRACK)
    svg = (
        f'<path fill="{pal["accent"]}" d="{"".join(paths[:3])}"/>'
        f'<path fill="{pal["ink"]}" d="{"".join(paths[3:])}"/>'
    )
    return svg, adv, bb


def text(font, s, size, x, base, fill, tracking=0.0):
    paths, adv, bb = font.run(s, size, x, base, tracking)
    return f'<path fill="{fill}" d="{"".join(paths)}"/>', adv, bb


def wrap(font, s, size, maxw):
    lines, cur = [], ""
    for w in s.split():
        t = f"{cur} {w}".strip()
        if cur and font.width(t, size) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur]


# ---------------------------------------------------------------- marks
MARKS = {
    "full": build("full"),
    "skeletal": build("skeletal"),
    "icon": build("icon", ICON_ATOMS),
    "favicon": build("favicon", FAVICON_ATOMS),
}


def place(name, x, y, w, h, align="center"):
    """Fit a mark into box; returns (parts, actual box)."""
    p = MARKS[name]
    x0, y0, x1, y1 = bounds(p)
    s = min(w / (x1 - x0), h / (y1 - y0))
    mw, mh = (x1 - x0) * s, (y1 - y0) * s
    ox = x if align == "left" else x + w - mw if align == "right" else x + (w - mw) / 2
    oy = y + (h - mh) / 2
    return transform(p, s, ox - x0 * s, oy - y0 * s), (ox, oy, mw, mh)


def mark_size(name, h):
    x0, y0, x1, y1 = bounds(MARKS[name])
    return (x1 - x0) / (y1 - y0) * h, h


def svg_doc(w, h, body, bg=None, rx=0, title="adrinaline"):
    rect = f'<rect width="{w:g}" height="{h:g}" rx="{rx:g}" fill="{bg}"/>' if bg else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" '
        f'width="{w:g}" height="{h:g}" role="img" aria-label="{title}"><title>{title}</title>'
        f"{rect}{body}</svg>\n"
    )


# ---------------------------------------------------------------- writers
written = []


def write_svg(rel, svg):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(svg)
    written.append(rel)


def png_bytes(svg, width=None, height=None):
    return cairosvg.svg2png(bytestring=svg.encode(), output_width=width, output_height=height)


def write_png(rel, svg, width=None, height=None, flatten=None):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    data = png_bytes(svg, width, height)
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    if flatten:
        bg = Image.new("RGB", im.size, flatten)
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im.save(p, optimize=True)
    written.append(rel)


# ---------------------------------------------------------------- compositions
def comp_mark(name, variant, pad=0.04):
    x0, y0, x1, y1 = bounds(MARKS[name])
    w, h = x1 - x0, y1 - y0
    m = max(w, h) * pad
    parts, _ = place(name, m, m, w, h)
    return svg_doc(
        w + 2 * m, h + 2 * m, svg_group(parts, PALETTE[variant]), title="adrinaline mark"
    )


def comp_wordmark(variant, size=200):
    pal = PALETTE[variant]
    _, adv, bb = DISPLAY.run("adrinaline", size, 0, 0, WORD_TRACK)
    pad = size * 0.06
    svg, _, _ = wordmark(pad - bb[0], pad - bb[1], size, pal)
    return svg_doc(bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad, svg)


def comp_horizontal(variant, size=200):
    """Icon + wordmark. Icon height = 1.55 x cap height, centred on x-height band."""
    pal = PALETTE[variant]
    _, adv, bb = DISPLAY.run("adrinaline", size, 0, 0, WORD_TRACK)
    ih = DISPLAY.cap * size * 1.55
    iw, _ = mark_size("icon", ih)
    pad = size * 0.08
    gap = size * 0.26
    top = pad
    # place text: mid of x-height aligned with icon centre (slightly raised for optical balance)
    centre = top + ih / 2
    base = centre + DISPLAY.xh * size * 0.5 + size * 0.03
    text_top = base + bb[1]
    text_bot = base + bb[3]
    y_min, y_max = min(top, text_top), max(top + ih, text_bot)
    shift = pad - y_min
    parts, _ = place("icon", pad, top + shift, iw, ih)
    word, _, _ = wordmark(pad + iw + gap - bb[0], base + shift, size, pal)
    return svg_doc(
        pad + iw + gap + bb[2] - bb[0] + pad, y_max - y_min + 2 * pad, svg_group(parts, pal) + word
    )


def comp_stacked(variant, size=200):
    """Full molecule above centred wordmark."""
    pal = PALETTE[variant]
    _, adv, bb = DISPLAY.run("adrinaline", size, 0, 0, WORD_TRACK)
    ww = bb[2] - bb[0]
    mw_, mh_ = mark_size("full", ww * 1.25 / mark_size("full", 1)[0])
    pad = size * 0.25
    W = max(mw_, ww) + 2 * pad
    parts, (mx, my, _, mh2) = place("full", (W - mw_) / 2, pad, mw_, mh_)
    base = pad + mh2 + size * 0.45 - bb[1]
    word, _, _ = wordmark((W - ww) / 2 - bb[0], base, size, pal)
    H = base + bb[3] + pad
    return svg_doc(W, H, svg_group(parts, pal) + word)


def comp_tile(name, variant, size=1024, radius=0.2235, inset=0.18, bg=None):
    pal = PALETTE[variant]
    if name == "favicon":  # solid ring: grey bonds disappear at 16 px
        pal = dict(pal, bond=pal["carbon"])
    m = size * inset
    parts, _ = place(name, m, m, size - 2 * m, size - 2 * m)
    return svg_doc(
        size,
        size,
        svg_group(parts, pal),
        bg=bg or pal["tile"],
        rx=size * radius,
        title="adrinaline icon",
    )


def comp_icon(name, variant, size=1024, inset=0.04):
    m = size * inset
    pal = PALETTE[variant]
    if name == "favicon":
        pal = dict(pal, bond=pal["carbon"])
    parts, _ = place(name, m, m, size - 2 * m, size - 2 * m)
    return svg_doc(size, size, svg_group(parts, pal), title="adrinaline icon")


def comp_favicon_svg():
    """Adaptive favicon: follows the browser colour scheme."""
    size = 64
    parts, _ = place("favicon", 2, 2, size - 4, size - 4)
    roles = ["bond", "carbon", "oxygen"]
    L = dict(PALETTE["on-light"], bond=PALETTE["on-light"]["carbon"])
    D = dict(PALETTE["on-dark"], bond=PALETTE["on-dark"]["carbon"])
    body = svg_group(parts, {r: f"var(--{r})" for r in roles} | {"nitrogen": "x", "hydrogen": "x"})
    body = body.replace('fill="var(--', 'class="').replace(')"', '"')
    style = (
        "<style>"
        + "".join(f".{r}{{fill:{L[r]}}}" for r in roles)
        + "@media (prefers-color-scheme:dark){"
        + "".join(f".{r}{{fill:{D[r]}}}" for r in roles)
        + "}</style>"
    )
    return svg_doc(size, size, style + body, title="adrinaline")


def comp_social(variant, W=1280, H=640, cmd=True, tagline=True, safe=40):
    """Left: wordmark, tagline, command chip. Right: full molecule."""
    pal = PALETTE[variant]
    left = W * 0.075
    col = W * 0.40
    wsize = col / (DISPLAY.width("adrinaline", 1, WORD_TRACK)) * 0.98
    _, _, bb = DISPLAY.run("adrinaline", wsize, 0, 0, WORD_TRACK)
    lines = (
        ["Git-native Architecture Decision Records", "for humans and coding agents"]
        if tagline
        else []
    )
    tsize = min(wsize * 0.26, col * 1.08 / TEXT.width(lines[0], 1)) if tagline else wsize * 0.26
    lh = tsize * 1.38
    csize = tsize * 0.92
    chip_h = csize * 2.3
    block = (
        (bb[3] - bb[1])
        + (wsize * 0.28 + len(lines) * lh if lines else 0)
        + (tsize * 1.1 + chip_h if cmd else 0)
    )
    y = (H - block) / 2 - bb[1]
    body = []
    w, _, _ = wordmark(left - bb[0], y, wsize, pal)
    body.append(w)
    y += bb[3] + wsize * 0.28
    for ln in lines:
        y += tsize * 0.95 if ln is lines[0] else lh
        body.append(text(TEXT, ln, tsize, left, y, pal["muted"])[0])
    if cmd:
        top = y + tsize * 1.1 if lines else y
        pw = MONO.width("$ " + COMMAND, csize) + csize * 1.8
        body.append(
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{pw:.1f}" height="{chip_h:.1f}" '
            f'rx="{chip_h * 0.28:.1f}" fill="{pal["chip"]}"/>'
        )
        bl = top + chip_h / 2 + MONO.cap * csize / 2
        body.append(text(MONO, "$", csize, left + csize * 0.9, bl, pal["accent"])[0])
        body.append(
            text(
                MONO, COMMAND, csize, left + csize * 0.9 + MONO.width("$ ", csize), bl, pal["ink"]
            )[0]
        )
    mx0 = left + col + W * 0.05
    parts, _ = place("full", mx0, safe + H * 0.06, W - mx0 - W * 0.05, H - 2 * safe - H * 0.12)
    body.insert(0, svg_group(parts, pal))
    return svg_doc(W, H, "".join(body), bg=pal["bg"])


def comp_banner(variant, W=1280, H=320, transparent=True):
    """README header: molecule left, wordmark + tagline right, centred as a group."""
    pal = PALETTE[variant]
    mh = H * 0.78
    mw, _ = mark_size("full", mh)
    wsize = H * 0.36
    _, adv, bb = DISPLAY.run("adrinaline", wsize, 0, 0, WORD_TRACK)
    tsize = wsize * 0.24
    gap = W * 0.035
    tw = max(bb[2] - bb[0], TEXT.width(TAGLINE, tsize))
    lines = [TAGLINE]
    if tw > W - mw - gap - W * 0.1:
        lines = wrap(TEXT, TAGLINE, tsize, bb[2] - bb[0] + wsize * 0.6)
        tw = max(bb[2] - bb[0], max(TEXT.width(t, tsize) for t in lines))
    total = mw + gap + tw
    x0 = (W - total) / 2
    parts, _ = place("full", x0, (H - mh) / 2, mw, mh)
    lh = tsize * 1.35
    block = (bb[3] - bb[1]) + wsize * 0.22 + tsize * 0.75 + (len(lines) - 1) * lh
    base = (H - block) / 2 - bb[1]
    tx = x0 + mw + gap
    body = [svg_group(parts, pal), wordmark(tx - bb[0], base, wsize, pal)[0]]
    y = base + bb[3] + wsize * 0.22 + tsize * 0.75
    for ln in lines:
        body.append(text(TEXT, ln, tsize, tx, y, pal["muted"])[0])
        y += lh
    return svg_doc(W, H, "".join(body), bg=None if transparent else pal["bg"])


# ---------------------------------------------------------------- build
def main():
    for d in ("svg", "png", "favicon", "social"):
        shutil.rmtree(OUT / d, ignore_errors=True)

    # vector masters
    for v in ALL_VARIANTS:
        write_svg(f"svg/logo-horizontal-{v}.svg", comp_horizontal(v))
        write_svg(f"svg/wordmark-{v}.svg", comp_wordmark(v))
        write_svg(f"svg/mark-{v}.svg", comp_mark("full", v))
        write_svg(f"svg/mark-skeletal-{v}.svg", comp_mark("skeletal", v))
        write_svg(f"svg/icon-{v}.svg", comp_icon("icon", v))
        write_svg(f"svg/icon-small-{v}.svg", comp_icon("favicon", v))
        write_svg(f"svg/logo-stacked-{v}.svg", comp_stacked(v))
    for v in COLOR_VARIANTS:
        write_svg(f"svg/icon-tile-{v}.svg", comp_tile("icon", v))
        write_svg(
            f"svg/icon-small-tile-{v}.svg",
            comp_tile("favicon", v, size=64, inset=0.08, radius=0.22),
        )
        write_svg(f"svg/banner-{v}.svg", comp_banner(v))

    # raster exports
    for v in ALL_VARIANTS:
        for w in (512, 1024, 2048):
            write_png(f"png/logo-horizontal-{v}-{w}w.png", comp_horizontal(v), width=w)
            write_png(f"png/logo-stacked-{v}-{w}w.png", comp_stacked(v), width=w)
            write_png(f"png/mark-{v}-{w}w.png", comp_mark("full", v), width=w)
        for s in (256, 512, 1024):
            write_png(f"png/icon-{v}-{s}.png", comp_icon("icon", v), width=s)
    for v in COLOR_VARIANTS:
        for w in (512, 1024, 2048):
            write_png(f"png/wordmark-{v}-{w}w.png", comp_wordmark(v), width=w)
        for s in (256, 512, 1024):
            write_png(f"png/icon-tile-{v}-{s}.png", comp_tile("icon", v), width=s)

    # favicons & app icons (dark tile is the primary app icon)
    write_svg("favicon/favicon.svg", comp_favicon_svg())
    small = comp_tile("favicon", "on-dark", size=64, inset=0.08, radius=0.22)
    for s in (16, 32, 48):
        write_png(f"favicon/favicon-{s}.png", small, width=s)
    ico_imgs = [Image.open(io.BytesIO(png_bytes(small, s, s))) for s in (16, 32, 48)]
    ico_imgs[-1].save(
        OUT / "favicon/favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=ico_imgs[:-1],
    )
    written.append("favicon/favicon.ico")
    # Apple: square, opaque, iOS applies its own mask
    write_png(
        "favicon/apple-touch-icon.png",
        comp_tile("icon", "on-dark", size=180, radius=0, inset=0.16),
        width=180,
        flatten=PALETTE["on-dark"]["bg"],
    )
    for s in (192, 512):
        write_png(
            f"favicon/icon-{s}.png", comp_tile("icon", "on-dark", size=s, inset=0.14), width=s
        )
    # maskable: content within the 80 % safe circle, full-bleed background
    write_png(
        "favicon/icon-maskable-512.png",
        comp_tile("icon", "on-dark", size=512, radius=0, inset=0.24),
        width=512,
        flatten=PALETTE["on-dark"]["bg"],
    )
    (OUT / "favicon/site.webmanifest").write_text(
        json.dumps(
            {
                "name": "adrinaline",
                "short_name": "adrinaline",
                "icons": [
                    {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {
                        "src": "icon-maskable-512.png",
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                ],
                "theme_color": PALETTE["on-dark"]["bg"],
                "background_color": PALETTE["on-dark"]["bg"],
                "display": "standalone",
            },
            indent=2,
        )
        + "\n"
    )
    written.append("favicon/site.webmanifest")

    # social
    for v in COLOR_VARIANTS:
        write_png(
            f"social/github-social-preview-{v}.png",
            comp_social(v, 1280, 640),
            width=1280,
            flatten=PALETTE[v]["bg"],
        )
        write_png(
            f"social/og-image-{v}.png",
            comp_social(v, 1200, 630),
            width=1200,
            flatten=PALETTE[v]["bg"],
        )
        write_png(
            f"social/header-1500x500-{v}.png",
            comp_social(v, 1500, 500, cmd=False, safe=30),
            width=1500,
            flatten=PALETTE[v]["bg"],
        )
        write_png(
            f"social/avatar-{v}.png",
            comp_tile("icon", v, size=1024, radius=0, inset=0.2),
            width=1024,
            flatten=PALETTE[v]["tile"],
        )
        write_png(f"social/readme-banner-{v}.png", comp_banner(v), width=2560)

    (OUT / "palette.json").write_text(
        json.dumps({k: v for k, v in PALETTE.items() if k in COLOR_VARIANTS}, indent=2) + "\n"
    )
    print(f"{len(written)} files")


if __name__ == "__main__":
    main()
