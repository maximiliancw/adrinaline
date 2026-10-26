# ruff: noqa  -- one-off provenance script for geometry.json, kept as run
import json
import sys

import cv2
import numpy as np

img = cv2.imread(sys.argv[1] if len(sys.argv) > 1 else "assets/adrenaline-molecule-large.png")
s = 5703 / 2000
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
H, S, V = cv2.split(hsv)
fg = (img.min(axis=2) < 245).astype(np.uint8)
P = 400
fg = cv2.copyMakeBorder(fg, P, P, P, P, cv2.BORDER_CONSTANT, 0)
guess = {
    "C1": (268, 415),
    "C2": (608, 390),
    "C3": (880, 545),
    "Ca": (1152, 565),
    "Cb": (1280, 295),
    "Cc": (1535, 315),
    "Cd": (1660, 605),
    "Ce": (1530, 880),
    "Cf": (1275, 855),
    "N": (522, 570),
    "O1": (790, 845),
    "O2": (1910, 620),
    "O3": (1655, 1160),
    "H1a": (340, 178),
    "H1b": (68, 400),
    "H1c": (198, 550),
    "H2a": (678, 150),
    "H2b": (405, 372),
    "H3": (945, 405),
    "HN": (455, 790),
    "HO1": (620, 822),
    "Hb": (1185, 65),
    "Hc": (1638, 100),
    "Hf": (1175, 1065),
    "HO2": (1962, 840),
    "HO3": (1820, 1125),
}
dt = cv2.distanceTransform(fg, cv2.DIST_L2, 5)
out = {}
for k, (x, y) in guess.items():
    X, Y = int(x * s) + P, int(y * s) + P
    r = int(60 * s)
    win = dt[Y - r : Y + r, X - r : X + r]
    # weight toward guess
    yy, xx = np.mgrid[-r:r, -r:r]
    w = win - 0.15 * np.sqrt(xx**2 + yy**2)
    iy, ix = np.unravel_index(np.argmax(w), w.shape)
    out[k] = dict(
        x=round((X - P - r + ix) / s, 1),
        y=round((Y - P - r + iy) / s, 1),
        r=round(float(win[iy, ix]) / s, 1),
    )
    print(k, out[k])
json.dump(out, open("detected.json", "w"), indent=1)
