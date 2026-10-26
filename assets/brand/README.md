# adrinaline brand assets

The mark is a flat ball-and-stick drawing of **(R)-adrenaline** (L-epinephrine), the
naturally occurring enantiomer, in the same pose as the reference renders in `assets/`.
The geometry was computed from scratch (RDKit conformer, MMFF-optimised, fitted to the
reference view), not traced from the renders. Overlaps are cut out geometrically, so
every SVG is plain filled paths: no masks, strokes, filters or fonts.

The wordmark is set in Space Grotesk Bold, converted to outlines. **adr** is in oxygen
red because it is the command name.

## Which file to use

| Need | File |
|---|---|
| README header (switches with GitHub's light/dark theme) | `svg/banner-on-light.svg` + `svg/banner-on-dark.svg` |
| Docs site / nav bar logo | `svg/logo-horizontal-on-*.svg` |
| Hero, title slide, poster | `svg/logo-stacked-on-*.svg`, `svg/mark-on-*.svg` |
| Square avatar (GitHub org, PyPI, Discord, Bluesky, …) | `social/avatar-on-dark.png` (1024²) |
| GitHub *Settings → Social preview* | `social/github-social-preview-on-dark.png` (1280×640) |
| Open Graph / link cards | `social/og-image-on-*.png` (1200×630) |
| Profile header (X, Bluesky, Mastodon) | `social/header-1500x500-on-*.png` |
| Small UI logo (docs header, app bars, 20–48 px) | `svg/icon-small-tile-on-*.svg` |
| App icon, rounded tile | `svg/icon-tile-on-*.svg`, `png/icon-tile-on-*-{256,512,1024}.png` |
| Favicon, PWA, Apple touch icon | `favicon/` |
| One-colour use (print, engraving, stamps, embroidery) | `*-mono-black.*`, `*-mono-white.*` |

`on-light` means *for light backgrounds*, `on-dark` *for dark backgrounds*. All `svg/`
and `png/` files have transparent backgrounds except the tiles; files in `social/` are opaque
except `readme-banner-*`.

### Mark sizes

Each mark is drawn for a size range; don't scale one outside it.

| Variant | Contents | Use from |
|---|---|---|
| `mark` | full molecule with hydrogens | ≥ 200 px wide |
| `mark-skeletal` | heavy atoms only | ≥ 120 px wide |
| `icon` | catechol ring with side-chain stub | ≥ 48 px |
| `icon-small` / `favicon` | catechol ring, solid bonds | 16–48 px |

## Snippets

README header:

```html
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/svg/banner-on-dark.svg">
    <img alt="adrinaline: Git-native Architecture Decision Records for humans and coding agents"
         src="assets/brand/svg/banner-on-light.svg" width="640">
  </picture>
</p>
```

HTML head:

```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
```

`favicon.svg` follows the browser's colour scheme on its own.

## Palette

| Token | On light | On dark |
|---|---|---|
| Carbon / ink | `#1F2329` | `#ECEEF2` |
| Oxygen / accent | `#E8392C` | `#FF4F3F` |
| Nitrogen | `#2F6BFF` | `#5B8CFF` |
| Hydrogen | `#B8BEC8` | `#7C8494` |
| Bond | `#9AA1AC` | `#4A515E` |
| Muted text | `#5B6270` | `#9AA1AC` |
| Background | `#FFFFFF` | `#0E1116` |

Machine-readable: `palette.json`. Atom colours follow the CPK convention (O red, N blue,
C dark, H light), so chemists will read the molecule correctly.

## Clear space and misuse

- Keep clear space of at least the height of the wordmark's "a" around every lockup.
- Don't recolour individual atoms, add shadows or gradients, or stretch the mark.
- Don't set the wordmark in another font or in all caps; use the outlined files.
- Don't put the colour logo on mid-tone or busy backgrounds; use a mono variant there.

## Rebuilding

```bash
uv run --no-project --with cairosvg --with shapely --with fonttools --with pillow \
    python assets/brand/src/build.py
```

- `src/build.py`: layouts and exports; tweak palette, sizes and copy here.
- `src/mark.py`: the flat renderer (atom radii, bond widths, knock-out gaps).
- `src/geometry.json`: projected 2D coordinates plus depth for all 26 atoms.
- `src/geometry/`: the one-off scripts that produced `geometry.json` (needs `rdkit`,
  `opencv-python-headless`, `scipy` and the original render).
- `src/fonts/`: Space Grotesk and JetBrains Mono, both SIL Open Font License 1.1.
